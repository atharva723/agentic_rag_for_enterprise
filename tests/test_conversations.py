"""Saved chats: the six routes and the data layer behind them, against a small in-memory stand-in for Supabase's database.

The stand-in enforces the same privacy rule as supabase/schema.sql (a signed-in user sees and changes only their own chats), so
"someone else's chat is a 404" is tested here. The real database is checked by `python -m app.supabase.check --full`.
"""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from conftest import parse_events
from fastapi.testclient import TestClient

from app import audit
from app.api import conversations as routes
from app.api import limits
from app.api.account import current_user
from app.api.streaming import INTERNAL_ERROR
from app.config import get_settings
from app.main import app
from app.supabase import conversations as chats
from app.supabase.auth import User

ANA, BEN = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
TOKENS = {"token-ana": ANA, "token-ben": BEN}
CHAT_COLUMNS = ["id", "title", "created_at", "updated_at"]
NOBODYS_CHAT = "00000000-0000-4000-8000-000000000000"  # a well-formed chat id that no one has
web = TestClient(app)


# ---- a small PostgREST in memory, with the privacy rules ------------------------------------------------------------------


def parse_select(select, default):
    """'id,title,messages(id,role)' -> (['id', 'title'], ['id', 'role']). The second part is None when no messages are asked for."""
    match = re.fullmatch(r"([^()]*?)(?:,?messages\(([^)]*)\))?", select or "")
    columns = [c for c in match.group(1).split(",") if c]
    return columns or default, (match.group(2).split(",") if match.group(2) is not None else None)


class ChatStore:
    """Answers the calls app/supabase/conversations.py makes, the way the real database does for a signed-in user:
    SELECT, UPDATE and DELETE only ever touch the caller's own rows, and a message can only go into the caller's own chat."""

    def __init__(self):
        self.chats: dict[str, dict] = {}
        self.messages: list[dict] = []
        self.failing: dict[tuple[str, str], int] = {}  # (method, path) -> HTTP status: make that call fail
        self.seconds = self.next_message_id = 0

    def now(self):
        self.seconds += 1
        return (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self.seconds)).isoformat()

    def handle(self, request: httpx.Request) -> httpx.Response:
        if (request.method, request.url.path) in self.failing:
            return httpx.Response(self.failing[(request.method, request.url.path)], json={"code": "XX000", "message": "something broke"})
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if token == "token-expired":
            return httpx.Response(401, json={"code": "PGRST301", "message": "JWT expired"})
        user = TOKENS.get(token)
        if user is None:
            return httpx.Response(401, json={"code": "PGRST301", "message": "JWT invalid"})
        table = request.url.path.removeprefix("/rest/v1/")
        handler = getattr(self, f"{table}_{request.method.lower()}", None)
        if handler is None:
            return httpx.Response(404, json={"message": "no such route"})
        body = json.loads(request.content) if request.content else None
        return handler(user, dict(request.url.params), body, "return=representation" in request.headers.get("prefer", ""))

    def mine(self, user, params):
        rows = [c for c in self.chats.values() if c["user_id"] == user]
        for column in ("id", "title"):
            if column in params:
                rows = [c for c in rows if c[column] == params[column].removeprefix("eq.")]
        return rows

    @staticmethod
    def pick(row, columns):
        return {c: row[c] for c in columns}

    def conversations_get(self, user, params, body, wants_rows):
        columns, embedded = parse_select(params.get("select"), CHAT_COLUMNS)
        rows = self.mine(user, params)
        if params.get("order") == "updated_at.desc":
            rows.sort(key=lambda c: c["updated_at"], reverse=True)
        out = []
        for row in rows[: int(params.get("limit", 1000))]:
            item = self.pick(row, columns)
            if embedded is not None:
                thread = sorted((m for m in self.messages if m["conversation_id"] == row["id"]), key=lambda m: m["id"], reverse=params.get("messages.order") == "id.desc")
                item["messages"] = [self.pick(m, embedded) for m in thread[: int(params.get("messages.limit", 1000))]]
            out.append(item)
        return httpx.Response(200, json=out)

    def conversations_post(self, user, params, body, wants_rows):
        stamp = self.now()
        row = {"id": str(uuid.uuid4()), "user_id": user, "title": body.get("title", "New chat"), "created_at": stamp, "updated_at": stamp}
        self.chats[row["id"]] = row
        columns, _ = parse_select(params.get("select"), CHAT_COLUMNS)
        return httpx.Response(201, json=[self.pick(row, columns)] if wants_rows else None)

    def conversations_patch(self, user, params, body, wants_rows):
        rows = self.mine(user, params)
        for row in rows:
            row.update(body)
        columns, _ = parse_select(params.get("select"), CHAT_COLUMNS)
        return httpx.Response(200, json=[self.pick(r, columns) for r in rows] if wants_rows else None)

    def conversations_delete(self, user, params, body, wants_rows):
        rows = self.mine(user, params)
        for row in rows:
            del self.chats[row["id"]]
            self.messages = [m for m in self.messages if m["conversation_id"] != row["id"]]  # on delete cascade
        return httpx.Response(200, json=[self.pick(r, ["id"]) for r in rows] if wants_rows else None)

    def messages_post(self, user, params, body, wants_rows):
        rows = body if isinstance(body, list) else [body]
        if any(r["conversation_id"] not in {c["id"] for c in self.chats.values() if c["user_id"] == user} for r in rows):
            return httpx.Response(403, json={"code": "42501", "message": 'new row violates row-level security policy for table "messages"'})
        for row in rows:
            self.next_message_id += 1
            self.messages.append({**row, "id": self.next_message_id, "user_id": user, "created_at": self.now()})
        for chat_id in {r["conversation_id"] for r in rows}:
            self.chats[chat_id]["updated_at"] = self.now()  # what the database trigger does
        return httpx.Response(201)


class Agent:
    """Stands in for the AI agent: it records what it was asked and answers without spending a token.
    When watched (on_step given), it reports the steps in `steps`, the way the real graph does."""

    def __init__(self):
        self.calls = []
        self.web_flags = []  # for each call: did the person turn web search on?
        self.steps = [
            {"step": "route_question", "status": "start", "label": "Understanding your question…"},
            {"step": "route_question", "status": "done", "lines": ["Router → KB"]},
            {"step": "generate_answer", "status": "start", "label": "Writing the answer from the company documents…"},
            {"step": "generate_answer", "status": "done", "lines": ["Answer generated from PRIVATE KB"]},
        ]

    def __call__(self, question, history, on_step=None, web=False):
        self.calls.append((question, history))
        self.web_flags.append(web)
        for event in self.steps if on_step else []:
            on_step(event)
        return {
            "answer": f"Answer to: {question}",
            "source_used": "private_kb",
            "citations": [{"source": "vpn.md", "type": "kb", "title": "VPN Guide"}],
            "trace": ["Router → KB", "Answer generated from PRIVATE KB"],
        }


@pytest.fixture(autouse=True)
def world(supabase, monkeypatch, tmp_path):
    """Every test here gets a fake database, a fake agent and a temporary audit file, and starts signed out."""
    store, agent = ChatStore(), Agent()
    supabase.router = store.handle
    monkeypatch.setattr("app.api.chat.ask", agent)
    monkeypatch.setattr(get_settings(), "audit_db", tmp_path / "audit.db")
    yield store, agent
    app.dependency_overrides.clear()


@pytest.fixture
def store(world):
    return world[0]


@pytest.fixture
def agent(world):
    return world[1]


def as_(name, token=None):
    """Sign in as Ana or Ben. current_user is replaced here (test_auth.py covers real tokens); the token is still passed on to the database."""
    app.dependency_overrides[current_user] = lambda: User(id=TOKENS[f"token-{name}"], email=f"{name}@example.com", token=token or f"token-{name}")


def new_chat(name="ana", title=None):
    as_(name)
    reply = web.post("/api/conversations", json={"title": title} if title else None)
    assert reply.status_code == 201
    return reply.json()["id"]


def say(chat_id, question, name="ana", **extra):
    as_(name)
    return web.post(f"/api/conversations/{chat_id}/messages", json={"question": question, **extra})


def titles(name="ana"):
    as_(name)
    return [chat["title"] for chat in web.get("/api/conversations").json()]


# ---- a chat: create, list, rename, delete -----------------------------------------------------------------------------------


def test_every_call_is_made_as_the_signed_in_user_and_never_with_the_secret_key(supabase):
    chat_id = new_chat()
    say(chat_id, "How do I connect to the VPN?")
    assert supabase.requests
    for request in supabase.requests:
        assert request.headers["authorization"] == "Bearer token-ana"
        assert request.headers["apikey"] == supabase.publishable


def test_a_new_chat_is_empty_and_has_the_default_title():
    as_("ana")
    reply = web.post("/api/conversations")
    assert reply.status_code == 201
    assert set(reply.json()) == {"id", "title", "created_at", "updated_at"} and reply.json()["title"] == "New chat"


def test_a_title_given_at_the_start_is_tidied_and_a_blank_or_huge_one_is_refused():
    as_("ana")
    assert web.post("/api/conversations", json={"title": "  VPN \n  help  "}).json()["title"] == "VPN help"
    for title in ("   ", "x" * 201):
        assert web.post("/api/conversations", json={"title": title}).status_code == 422


def test_the_list_shows_the_most_recently_used_chat_first():
    first, _ = new_chat(title="first"), new_chat(title="second")
    assert titles() == ["second", "first"]
    say(first, "Use the first chat again")  # saving a message moves a chat to the top
    assert titles() == ["first", "second"]


def test_a_user_sees_only_their_own_chats():
    new_chat("ana")
    new_chat("ben", title="Ben's chat")
    assert titles("ana") == ["New chat"] and titles("ben") == ["Ben's chat"]


def test_the_list_can_be_limited_and_the_limit_is_checked():
    for _ in range(3):
        new_chat()
    assert len(web.get("/api/conversations", params={"limit": 2}).json()) == 2
    assert web.get("/api/conversations", params={"limit": 0}).status_code == 422
    assert web.get("/api/conversations", params={"limit": 101}).status_code == 422


def test_a_chat_can_be_renamed_and_the_new_title_must_be_real():
    chat_id = new_chat()
    reply = web.patch(f"/api/conversations/{chat_id}", json={"title": " My VPN chat "})
    assert reply.status_code == 200 and reply.json()["title"] == "My VPN chat" and titles() == ["My VPN chat"]
    assert web.patch(f"/api/conversations/{chat_id}", json={"title": "  "}).status_code == 422
    assert web.patch("/api/conversations/not-an-id", json={"title": "x"}).status_code == 422


def test_a_chat_is_deleted_together_with_its_messages(store):
    chat_id = new_chat()
    say(chat_id, "How do I connect to the VPN?")
    assert store.messages
    assert web.delete(f"/api/conversations/{chat_id}").status_code == 204
    assert titles() == [] and store.messages == []
    assert web.delete(f"/api/conversations/{chat_id}").status_code == 404  # already gone


# ---- reading the messages of a chat -----------------------------------------------------------------------------------------


def test_the_messages_come_back_oldest_first_with_what_each_answer_was_based_on():
    chat_id = new_chat()
    say(chat_id, "First question")
    say(chat_id, "Second question")
    messages = web.get(f"/api/conversations/{chat_id}/messages").json()
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "First question"),
        ("assistant", "Answer to: First question"),
        ("user", "Second question"),
        ("assistant", "Answer to: Second question"),
    ]
    answer = messages[1]
    assert answer["source_used"] == "private_kb" and answer["citations"][0]["source"] == "vpn.md"
    assert answer["trace"][0] == "Router → KB" and answer["latency_ms"] >= 0
    assert "user_id" not in answer and "conversation_id" not in answer


def test_only_the_newest_messages_are_returned_when_asked_for_fewer():
    chat_id = new_chat()
    for n in (1, 2, 3):
        say(chat_id, f"Question {n}")
    messages = web.get(f"/api/conversations/{chat_id}/messages", params={"limit": 3}).json()
    assert [m["content"] for m in messages] == ["Answer to: Question 2", "Question 3", "Answer to: Question 3"]
    assert web.get(f"/api/conversations/{chat_id}/messages", params={"limit": 501}).status_code == 422


def test_a_chat_with_no_messages_is_an_empty_list_not_a_404():
    chat_id = new_chat()
    reply = web.get(f"/api/conversations/{chat_id}/messages")
    assert reply.status_code == 200 and reply.json() == []


# ---- asking a question in a chat: memory comes from the database ------------------------------------------------------------


def test_the_first_message_has_no_history_and_the_chat_is_named_after_it(agent):
    chat_id = new_chat()
    reply = say(chat_id, "How do I connect to the company VPN from home?")
    body = reply.json()
    assert reply.status_code == 200 and agent.calls == [("How do I connect to the company VPN from home?", [])]
    assert body["answer"] == "Answer to: How do I connect to the company VPN from home?"
    assert body["source_used"] == "private_kb" and body["citations"][0]["source"] == "vpn.md" and body["trace"][0] == "Router → KB"
    assert body["saved"] is True and body["warnings"] == [] and body["title"] == "How do I connect to the company VPN from home?"
    assert titles() == ["How do I connect to the company VPN from home?"]


def test_a_long_first_question_gives_a_shorter_title():
    chat_id = new_chat()
    body = say(chat_id, "How do I connect to the company VPN from home when I am abroad?").json()
    assert body["title"] == "How do I connect to the company VPN from home when…"


def test_a_follow_up_gets_the_earlier_messages_from_the_database(agent):
    chat_id = new_chat()
    say(chat_id, "How do I connect to the VPN?")
    say(chat_id, "What if it keeps dropping?")
    assert agent.calls[1] == ("What if it keeps dropping?", [{"question": "How do I connect to the VPN?", "answer": "Answer to: How do I connect to the VPN?"}])


def test_a_history_sent_by_the_client_is_ignored(agent):
    chat_id = new_chat()
    say(chat_id, "How do I connect to the VPN?")
    say(chat_id, "And on my phone?", history=[{"question": "invented", "answer": "invented"}])
    assert [pair["question"] for pair in agent.calls[1][1]] == ["How do I connect to the VPN?"]


def test_only_the_last_few_messages_are_loaded(agent, supabase):
    chat_id = new_chat()
    for n in range(1, 8):
        say(chat_id, f"Question {n}")
    loads = [r for r in supabase.requests if r.method == "GET" and "messages.limit" in r.url.params]
    assert {r.url.params["messages.limit"] for r in loads} == {"8"}  # the last 3 pairs, and a little extra. The agent itself keeps only 3
    assert [pair["question"] for pair in agent.calls[-1][1]] == ["Question 3", "Question 4", "Question 5", "Question 6"]


def test_two_chats_never_see_each_others_messages(agent):
    one, two = new_chat(), new_chat()
    say(one, "A question about the VPN")
    say(two, "A follow-up in another chat")
    assert agent.calls[1] == ("A follow-up in another chat", [])


def test_the_first_question_names_the_chat_but_a_title_the_user_chose_is_kept():
    named = new_chat()
    assert say(named, "First question").json()["title"] == "First question"
    assert say(named, "Second question").json()["title"] == "First question"  # only the first question names it
    chosen = new_chat(title="My VPN chat")
    assert say(chosen, "How do I connect to the VPN?").json()["title"] == "My VPN chat"
    assert "My VPN chat" in titles()


def test_the_audit_log_records_who_asked_and_in_which_chat():
    chat_id = new_chat()
    say(chat_id, "How do I connect to the VPN?")
    (row,) = audit.recent()
    assert (row["question"], row["user_id"], row["conversation_id"]) == ("How do I connect to the VPN?", ANA, chat_id)


def test_a_question_is_only_a_question_between_2_and_3000_characters(agent):
    chat_id = new_chat()
    for question in ("?", "x" * 3001):
        assert say(chat_id, question).status_code == 422
    assert agent.calls == []


def test_web_search_is_off_unless_the_page_turns_it_on(agent):
    chat_id = new_chat()
    say(chat_id, "What is the price of MAFANG?")  # the page says nothing
    say(chat_id, "And the price of NVDA?", web=False)
    assert agent.web_flags == [False, False]


def test_the_web_search_switch_of_the_page_reaches_the_agent_on_both_routes(agent):
    chat_id = new_chat()
    assert say(chat_id, "What is the price of MAFANG?", web=True).status_code == 200
    streamed = stream(chat_id, "And the price of NVDA?", web=True)
    assert parse_events(streamed.text)[-1][0] == "answer"
    assert agent.web_flags == [True, True]
    say(chat_id, "A question with the switch off again")
    assert agent.web_flags[-1] is False  # it is the page's choice for each question, never remembered by the server


def test_a_web_search_switch_that_is_not_true_or_false_is_refused_before_anything_runs(agent):
    chat_id = new_chat()
    assert say(chat_id, "What is the price of MAFANG?", web="maybe").status_code == 422
    assert stream(chat_id, "What is the price of MAFANG?", web="maybe").status_code == 422
    assert agent.calls == []


# ---- someone else's chat ----------------------------------------------------------------------------------------------------


def test_someone_elses_chat_is_a_404_and_costs_no_ai_tokens(store, agent):
    chat_id = new_chat("ana")
    say(chat_id, "Ana's private question")
    agent.calls.clear()
    reply = say(chat_id, "Ben tries to use Ana's chat", name="ben")
    assert reply.status_code == 404 and agent.calls == []
    assert len(store.messages) == 2 and audit.recent()[0]["user_id"] == ANA  # nothing was added, and nothing audited for Ben


def test_ben_cannot_read_rename_or_delete_anas_chat():
    chat_id = new_chat("ana", title="Ana's chat")
    as_("ben")
    assert web.get(f"/api/conversations/{chat_id}/messages").status_code == 404
    assert web.patch(f"/api/conversations/{chat_id}", json={"title": "hacked"}).status_code == 404
    assert web.delete(f"/api/conversations/{chat_id}").status_code == 404
    assert titles("ana") == ["Ana's chat"]


def test_a_chat_that_does_not_exist_looks_the_same_as_someone_elses(agent):
    assert say(NOBODYS_CHAT, "Anyone there?").status_code == 404 and agent.calls == []
    as_("ana")
    assert web.get(f"/api/conversations/{NOBODYS_CHAT}/messages").status_code == 404


# ---- when Supabase has a problem --------------------------------------------------------------------------------------------


def test_when_the_chat_cannot_be_read_the_question_is_still_answered_on_its_own_with_a_warning(store, agent):
    chat_id = new_chat()
    say(chat_id, "An earlier question")
    store.failing[("GET", "/rest/v1/conversations")] = 503
    reply = say(chat_id, "What if it keeps dropping?")
    body = reply.json()
    assert reply.status_code == 200 and body["answer"].startswith("Answer to:")
    assert agent.calls[-1] == ("What if it keeps dropping?", [])  # it could not see the earlier question
    assert routes.NO_MEMORY in body["warnings"] and body["saved"] is True


def test_when_supabase_is_down_the_answer_is_still_returned_with_two_warnings(supabase, agent):
    chat_id = new_chat()
    supabase.error = httpx.ConnectError("down")
    reply = say(chat_id, "Is anybody there?")
    body = reply.json()
    assert reply.status_code == 200 and body["answer"].startswith("Answer to:") and agent.calls[-1] == ("Is anybody there?", [])
    assert body["saved"] is False and body["warnings"] == [routes.NO_MEMORY, routes.NOT_SAVED] and body["title"] is None


def test_when_only_saving_fails_the_answer_is_still_returned_and_nothing_is_half_saved(store):
    chat_id = new_chat()
    store.failing[("POST", "/rest/v1/messages")] = 500
    body = say(chat_id, "An answer that cannot be saved").json()
    assert body["saved"] is False and body["warnings"] == [routes.NOT_SAVED] and body["answer"].startswith("Answer to:")
    store.failing.clear()
    as_("ana")
    assert web.get(f"/api/conversations/{chat_id}/messages").json() == []


def test_a_failed_rename_does_not_make_a_saved_answer_look_unsaved(store):
    chat_id = new_chat()
    store.failing[("PATCH", "/rest/v1/conversations")] = 500
    body = say(chat_id, "A question").json()
    assert body["saved"] is True and body["warnings"] == [] and body["title"] == "New chat"


def test_an_expired_login_is_a_401_on_every_route_and_costs_no_ai_tokens(agent):
    as_("ana", token="token-expired")
    replies = [
        web.get("/api/conversations"),
        web.post("/api/conversations"),
        web.patch(f"/api/conversations/{NOBODYS_CHAT}", json={"title": "x"}),
        web.delete(f"/api/conversations/{NOBODYS_CHAT}"),
        web.get(f"/api/conversations/{NOBODYS_CHAT}/messages"),
        web.post(f"/api/conversations/{NOBODYS_CHAT}/messages", json={"question": "hello there"}),
        web.post(f"/api/conversations/{NOBODYS_CHAT}/messages/stream", json={"question": "hello there"}),
    ]
    assert [r.status_code for r in replies] == [401] * 7 and agent.calls == []
    assert all(r.headers["www-authenticate"] == "Bearer" and "expired" in r.json()["detail"] for r in replies)


def test_when_supabase_is_down_the_chat_routes_say_503_and_try_again(supabase):
    chat_id = new_chat()
    supabase.error = httpx.ConnectError("down")
    replies = [
        web.get("/api/conversations"),
        web.post("/api/conversations"),
        web.patch(f"/api/conversations/{chat_id}", json={"title": "x"}),
        web.delete(f"/api/conversations/{chat_id}"),
        web.get(f"/api/conversations/{chat_id}/messages"),
    ]
    assert [r.status_code for r in replies] == [503] * 5 and all("try again" in r.json()["detail"] for r in replies)


# ---- the agent has a problem ------------------------------------------------------------------------------------------------


def test_the_ai_being_busy_is_a_plain_429_and_nothing_is_saved_or_audited(store, monkeypatch):
    chat_id = new_chat()

    class Busy(Exception):
        status_code = 429

    def busy(question, history):
        raise Busy("tokens per day limit reached")

    monkeypatch.setattr("app.api.chat.ask", busy)
    reply = say(chat_id, "A question")
    assert reply.status_code == 429 and "busy" in reply.json()["detail"] and "tokens per day" not in reply.text
    assert store.messages == [] and audit.recent() == []


def test_an_agent_crash_is_a_plain_500_and_nothing_is_saved(store, monkeypatch):
    chat_id = new_chat()

    def broken(question, history):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr("app.api.chat.ask", broken)
    reply = TestClient(app, raise_server_exceptions=False).post(f"/api/conversations/{chat_id}/messages", json={"question": "A question"})
    assert reply.status_code == 500 and "secret internal detail" not in reply.text
    assert store.messages == []


# ---- sign-in is required ----------------------------------------------------------------------------------------------------

ROUTES = [
    ("get", "/api/conversations", None),
    ("post", "/api/conversations", None),
    ("patch", f"/api/conversations/{NOBODYS_CHAT}", {"title": "x"}),
    ("delete", f"/api/conversations/{NOBODYS_CHAT}", None),
    ("get", f"/api/conversations/{NOBODYS_CHAT}/messages", None),
    ("post", f"/api/conversations/{NOBODYS_CHAT}/messages", {"question": "hello there"}),
    ("post", f"/api/conversations/{NOBODYS_CHAT}/messages/stream", {"question": "hello there"}),
]


@pytest.mark.parametrize("method, url, body", ROUTES)
def test_every_route_needs_a_sign_in(method, url, body, agent):
    reply = getattr(web, method)(url, **({"json": body} if body else {}))
    assert reply.status_code == 401 and reply.json() == {"detail": "Please sign in."} and agent.calls == []


def test_with_accounts_switched_off_the_routes_say_so(monkeypatch):
    monkeypatch.setattr(get_settings(), "supabase_url", "")
    reply = web.get("/api/conversations", headers={"Authorization": "Bearer some-token"})
    assert reply.status_code == 503 and "switched off" in reply.json()["detail"]


# ---- per-person limits ------------------------------------------------------------------------------------------------------


def set_limits(monkeypatch, per_minute=0, per_day=0):
    monkeypatch.setattr(get_settings(), "rate_limit_per_minute", per_minute)
    monkeypatch.setattr(get_settings(), "rate_limit_per_day", per_day)


def test_a_person_can_ask_only_so_many_questions_a_minute(store, agent, monkeypatch):
    set_limits(monkeypatch, per_minute=2)
    chat_id = new_chat()
    assert [say(chat_id, f"Question {n}").status_code for n in (1, 2)] == [200, 200]
    reply = say(chat_id, "Question 3")
    assert reply.status_code == 429 and 1 <= int(reply.headers["retry-after"]) <= 60
    assert "The limit is 2 questions a minute" in reply.json()["detail"] and "Please wait" in reply.json()["detail"]
    assert len(agent.calls) == 2 and len(store.messages) == 4 and len(audit.recent()) == 2  # the refused question ran, saved and audited nothing


def test_the_daily_limit_says_so_and_how_long_to_wait(monkeypatch):
    set_limits(monkeypatch, per_day=1)
    chat_id = new_chat()
    assert say(chat_id, "Question 1").status_code == 200
    reply = say(chat_id, "Question 2")
    assert reply.status_code == 429 and int(reply.headers["retry-after"]) > 86_000
    assert reply.json()["detail"] == "You have asked 1 question in the last 24 hours, which is the limit. You can ask again in 24 hours."


def test_each_person_has_their_own_allowance(monkeypatch):
    set_limits(monkeypatch, per_minute=1)
    ana_chat, ben_chat = new_chat("ana"), new_chat("ben")
    assert say(ana_chat, "Ana asks").status_code == 200
    assert say(ana_chat, "Ana asks again").status_code == 429
    assert say(ben_chat, "Ben asks", name="ben").status_code == 200


def test_the_other_chat_routes_still_work_when_the_questions_are_used_up(monkeypatch):
    set_limits(monkeypatch, per_minute=1)
    chat_id = new_chat()
    say(chat_id, "Question 1")
    assert say(chat_id, "Question 2").status_code == 429
    as_("ana")
    assert web.get("/api/conversations").status_code == 200
    assert web.get(f"/api/conversations/{chat_id}/messages").status_code == 200
    assert web.patch(f"/api/conversations/{chat_id}", json={"title": "Renamed"}).status_code == 200
    assert web.delete(f"/api/conversations/{chat_id}").status_code == 204


def test_waiting_is_enough_and_a_refused_question_does_not_make_the_wait_longer(clock, monkeypatch):
    monkeypatch.setattr(limits.questions, "clock", clock)
    set_limits(monkeypatch, per_minute=1)
    chat_id = new_chat()
    assert say(chat_id, "One").status_code == 200
    clock.now += 30
    assert [say(chat_id, "Too soon").status_code for _ in range(3)] == [429] * 3
    clock.now += 30
    assert say(chat_id, "Two").status_code == 200


def test_a_question_the_ai_was_too_busy_to_answer_does_not_count(agent, monkeypatch):
    set_limits(monkeypatch, per_minute=1)
    chat_id = new_chat()

    class Busy(Exception):
        status_code = 429

    def busy(question, history):
        raise Busy("tokens per day limit reached")

    monkeypatch.setattr("app.api.chat.ask", busy)
    assert "busy" in say(chat_id, "One").json()["detail"]
    monkeypatch.setattr("app.api.chat.ask", agent)
    assert say(chat_id, "Two").status_code == 200  # the busy one was given back
    assert "The limit is 1 question a minute" in say(chat_id, "Three").json()["detail"]


def test_a_refused_question_does_nothing_else_not_even_a_database_call(supabase, agent, monkeypatch):
    set_limits(monkeypatch, per_minute=1)
    chat_id = new_chat()
    say(chat_id, "One")
    before = len(supabase.requests)
    assert say(chat_id, "Two").status_code == 429
    assert len(supabase.requests) == before and len(agent.calls) == 1


def test_a_missing_login_is_a_401_never_a_429(agent, monkeypatch):
    set_limits(monkeypatch, per_minute=1)
    replies = [web.post(f"/api/conversations/{NOBODYS_CHAT}/messages", json={"question": "hello there"}) for _ in range(3)]
    assert [r.status_code for r in replies] == [401] * 3 and agent.calls == []


@pytest.mark.parametrize("method, url, body", ROUTES)
def test_every_chat_route_counts_towards_the_request_limit(method, url, body, agent, monkeypatch):
    monkeypatch.setattr(limits, "REQUESTS_PER_MINUTE", 1)
    as_("ana")
    assert web.get("/api/conversations").status_code == 200  # the one allowed request
    reply = getattr(web, method)(url, **({"json": body} if body else {}))
    assert reply.status_code == 429 and reply.json()["detail"].startswith("Too many requests. Please wait") and agent.calls == []
    assert reply.headers["retry-after"].isdigit()
    as_("ben")
    assert web.get("/api/conversations").status_code == 200  # someone else is not affected


# ---- streaming: the same question, with the steps shown as they happen -------------------------------------------------------


def stream(chat_id, question, name="ana", **extra):
    as_(name)
    return web.post(f"/api/conversations/{chat_id}/messages/stream", json={"question": question, **extra})


def test_the_stream_sends_each_step_as_it_happens_and_then_the_answer(agent):
    chat_id = new_chat()
    res = stream(chat_id, "How do I connect to the VPN?")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/event-stream")
    assert res.headers["cache-control"] == "no-cache, no-transform" and res.headers["x-accel-buffering"] == "no"
    events = parse_events(res.text)
    assert [name for name, _ in events] == ["step"] * 4 + ["answer"]
    assert [data for name, data in events if name == "step"] == agent.steps
    assert events[-1][1]["answer"] == "Answer to: How do I connect to the VPN?"


def test_the_streamed_answer_is_exactly_what_the_plain_route_returns():
    plain_chat, streamed_chat = new_chat(), new_chat()
    plain = say(plain_chat, "How do I connect to the VPN?").json()
    assert parse_events(stream(streamed_chat, "How do I connect to the VPN?").text)[-1] == ("answer", plain)


def test_a_streamed_question_is_saved_audited_and_remembered_like_any_other(store, agent):
    chat_id = new_chat()
    stream(chat_id, "How do I connect to the VPN?")
    assert [m["role"] for m in store.messages] == ["user", "assistant"]
    (row,) = audit.recent()
    assert (row["user_id"], row["conversation_id"], row["trace"]) == (ANA, chat_id, ["Router → KB", "Answer generated from PRIVATE KB"])
    assert titles() == ["How do I connect to the VPN?"]
    stream(chat_id, "What if it keeps dropping?")
    assert agent.calls[-1][1] == [{"question": "How do I connect to the VPN?", "answer": "Answer to: How do I connect to the VPN?"}]  # from the database, as ever


def test_a_chat_that_is_not_yours_is_a_plain_404_before_anything_streams_and_costs_no_ai_tokens(agent):
    chat_id = new_chat("ana")
    res = stream(chat_id, "Ben tries Ana's chat", name="ben")
    assert res.status_code == 404 and res.headers["content-type"] == "application/json" and res.json() == {"detail": "Chat not found."}
    assert stream(NOBODYS_CHAT, "Anyone there?").status_code == 404
    assert agent.calls == []


def test_a_used_up_limit_is_a_plain_429_before_anything_streams(agent, monkeypatch):
    set_limits(monkeypatch, per_minute=1)
    chat_id = new_chat()
    assert stream(chat_id, "One").status_code == 200
    res = stream(chat_id, "Two")
    assert res.status_code == 429 and res.headers["content-type"] == "application/json" and res.headers["retry-after"].isdigit()
    assert len(agent.calls) == 1


def test_a_busy_ai_service_ends_the_stream_with_an_error_event_and_the_question_does_not_count(store, agent, monkeypatch):
    set_limits(monkeypatch, per_minute=1)
    chat_id = new_chat()

    class Busy(Exception):
        status_code = 429

    def busy(question, history, on_step=None):
        on_step(agent.steps[0])  # the first step had started when the AI said no
        raise Busy("tokens per day limit reached")

    monkeypatch.setattr("app.api.chat.ask", busy)
    res = stream(chat_id, "One")
    assert res.status_code == 200  # the stream had begun
    (first, last) = parse_events(res.text)
    assert first == ("step", agent.steps[0]) and last[0] == "error" and last[1]["status"] == 429
    assert "busy" in last[1]["detail"] and "tokens per day" not in res.text  # no provider details leak
    assert store.messages == [] and audit.recent() == []
    monkeypatch.setattr("app.api.chat.ask", agent)
    assert parse_events(stream(chat_id, "Two").text)[-1][0] == "answer"  # the busy one was given back, so the limit of 1 still has room


def test_an_agent_crash_ends_the_stream_with_a_plain_error_and_no_details(store, monkeypatch, caplog):
    chat_id = new_chat()

    def broken(question, history, on_step=None):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr("app.api.chat.ask", broken)
    res = stream(chat_id, "A question")
    assert parse_events(res.text) == [("error", {"status": 500, "detail": INTERNAL_ERROR})]
    assert "secret internal detail" not in res.text and store.messages == []
    assert "secret internal detail" in caplog.text  # only in our own log


def test_a_streamed_answer_is_still_returned_when_it_cannot_be_saved(store):
    chat_id = new_chat()
    store.failing[("POST", "/rest/v1/messages")] = 500
    name, body = parse_events(stream(chat_id, "An answer that cannot be saved").text)[-1]
    assert name == "answer" and body["saved"] is False and body["warnings"] == [routes.NOT_SAVED]


# ---- the small helpers ------------------------------------------------------------------------------------------------------


def row(role, content):
    return {"role": role, "content": content}


def test_history_pairs_each_question_with_its_answer():
    rows = [row("user", "q1"), row("assistant", "a1"), row("user", "q2"), row("assistant", "a2")]
    assert chats.history_from(rows) == [{"question": "q1", "answer": "a1"}, {"question": "q2", "answer": "a2"}]


def test_history_skips_an_answer_whose_question_was_cut_off_and_a_question_with_no_answer():
    rows = [row("assistant", "a0"), row("user", "q1"), row("user", "q2"), row("assistant", "a2"), row("user", "q3")]
    assert chats.history_from(rows) == [{"question": "q2", "answer": "a2"}]


@pytest.mark.parametrize(
    "question, title",
    [("Short question", "Short question"), ("  spaced \n out  ", "spaced out"), ("x" * 52, "x" * 52), ("x" * 53, "x" * 50 + "…")],
)
def test_a_chat_is_named_after_its_first_question_cut_to_50_characters(question, title):
    assert chats.make_title(question) == title
