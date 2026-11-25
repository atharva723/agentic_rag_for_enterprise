"""Is the Supabase project set up right? Run it after you edit .env, and again after you run supabase/schema.sql.

    python -m app.supabase.check          a quick read-only check (a few calls, nothing is created)
    python -m app.supabase.check --full   also makes two throwaway users and proves, with their real login tokens, that sign-in
                                          works, that OUR server accepts the tokens and refuses forged ones, that saved chats work
                                          through our routes, and that one user cannot see or change another user's chats

--full uses the secret key to make the two users, then deletes both and everything they made. It is not part of pytest: it needs your
project and your keys. It spends no AI tokens (the agent is replaced by a stand-in). No key or token is ever printed.
"""
import argparse
import secrets
import sys
from datetime import datetime

from app.config import get_settings
from app.supabase import auth
from app.supabase.client import SupabaseError, configured, key_kind, request

failed: list[str] = []


def step(ok: bool, text: str, hint: str = "") -> bool:
    print(f"  {'ok  ' if ok else 'FAIL'} {text}")
    if not ok:
        failed.append(text)
        if hint:
            print(f"       -> {hint}")
    return ok


def why(reply) -> str:
    """The reason Supabase gave for a failed call. It never contains a key."""
    body = reply.json() if reply.content else {}
    return str(body.get("message") or body.get("msg") or body.get("error_description") or "") if isinstance(body, dict) else ""


def quick() -> None:
    """The read-only checks."""
    print("Settings")
    if not step(configured(), "SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY are set", "put them in .env (Project Settings in the Supabase dashboard)"):
        return
    step(
        key_kind(get_settings().supabase_publishable_key) == "publishable",
        "SUPABASE_PUBLISHABLE_KEY is a publishable key",
        "that value is not a publishable key. If it is the secret key, swap them: only the publishable key may ever be shown in a browser",
    )

    print("Project")
    reply = request("GET", "/auth/v1/settings")
    if not step(reply.status_code == 200, "the project answers", f"HTTP {reply.status_code}: check SUPABASE_URL and the publishable key"):
        return
    project = reply.json()
    print(
        f"       email login: {'on' if project.get('external', {}).get('email') else 'OFF'}"
        f" | sign-ups: {'closed' if project.get('disable_signup') else 'open'}"
        f" | email confirmation: {'off (a new user can sign in at once)' if project.get('mailer_autoconfirm') else 'on (a new user must click an emailed link first)'}"
    )
    reply = request("GET", "/auth/v1/.well-known/jwks.json")
    algorithms = sorted({key.get("alg", "?") for key in reply.json().get("keys", [])}) if reply.status_code == 200 else []
    step(
        bool(algorithms) and set(algorithms) <= set(auth.ALGORITHMS),
        f"login tokens are signed with a public key ({', '.join(algorithms) or 'none'}), so our server can check them without calling Supabase",
        f"our server accepts {' and '.join(auth.ALGORITHMS)}. If this project still uses the old shared secret, switch to the new signing keys in Project Settings > JWT Keys",
    )

    print("Tables (supabase/schema.sql)")
    for table in ("conversations", "messages"):
        reply = request("GET", f"/rest/v1/{table}", params={"select": "id", "limit": 1})
        if not step(reply.status_code != 404, f"{table} exists", "run supabase/schema.sql in the Supabase SQL editor"):
            continue
        nothing = reply.status_code in (401, 403) or (reply.status_code == 200 and reply.json() == [])
        step(nothing, f"{table}: someone who is not signed in gets nothing", f"HTTP {reply.status_code}: the table is open to anyone. Run supabase/schema.sql again")


def login_tokens(ids: list[str], tokens: list[str], emails: list[str]) -> None:
    """Our own server's check of two REAL login tokens: the same code every protected route runs."""
    print("Login tokens (checked by our own server, with no call to Supabase)")
    (a, b), (ta, tb) = ids, tokens

    def verdict(token):
        """The User our server accepts for this token, or the AuthError that refuses it."""
        try:
            return auth.verify_token(token)
        except auth.AuthError as exc:
            return exc

    def accepted(token, user_id, email=None):
        got = verdict(token)
        return isinstance(got, auth.User) and got.id == user_id and (email is None or got.email == email)

    def refused(token):
        return isinstance(verdict(token), auth.AuthError)

    head, body, sig = ta.split(".")
    changed = f"{head}.{body}.{sig[:20]}{'A' if sig[20] != 'A' else 'B'}{sig[21:]}"  # one letter in the middle of A's signature is different
    step(accepted(ta, a, emails[0]), "A's real login token is accepted, and A's id and email are read from it", str(verdict(ta)))
    step(accepted(tb, b), "B's token gives B's id, not A's", str(verdict(tb)))
    step(refused(f"{head}.{tb.split('.')[1]}.{sig}"), "B's details under A's signature are refused")
    step(refused(changed), "A's token with its signature changed is refused")
    step(refused(get_settings().supabase_publishable_key), "the publishable key on its own is not a login token")

    # the same thing through the real web route, with only the account routes mounted (the whole app is not needed here)
    from fastapi import FastAPI  # imported here so the quick check starts fast
    from fastapi.testclient import TestClient

    from app.api import account

    mini = FastAPI()
    mini.include_router(account.router, prefix="/api")
    web, bearer = TestClient(mini), lambda token: {"Authorization": f"Bearer {token}"}
    me = web.get("/api/me", headers=bearer(ta))
    step(me.status_code == 200 and me.json() == {"id": a, "email": emails[0]}, "GET /api/me with A's token answers with A's id and email", f"HTTP {me.status_code}: {me.text[:100]}")
    step(web.get("/api/me").status_code == 401, "GET /api/me with no token answers 401")
    step(web.get("/api/me", headers=bearer(changed)).status_code == 401, "GET /api/me with a forged token answers 401")
    config = web.get("/api/config")
    shown = config.json().get("supabase") or {} if config.status_code == 200 else {}
    settings = get_settings()
    step(
        shown.get("url") == settings.supabase_url.rstrip("/") and shown.get("publishable_key") == settings.supabase_publishable_key and settings.supabase_secret_key not in config.text,
        "GET /api/config gives the page the project address and the publishable key, and never the secret key",
        f"HTTP {config.status_code}",
    )


def saved_chats(ids: list[str], tokens: list[str]) -> None:
    """Saved chats through OUR routes, with two real login tokens. The AI agent is replaced by a stand-in that answers for free, so
    this spends no AI tokens. Everything else is real: the login check, the routes, and the database with its privacy rules."""
    print("Saved chats (through our own routes)")
    import tempfile  # imported here so the quick check starts fast
    from pathlib import Path
    from unittest import mock

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app import audit
    from app.api import conversations, limits

    (a, _), (ta, tb) = ids, tokens
    settings, asked = get_settings(), []

    def stand_in(question, history):
        asked.append((question, history))
        return {
            "answer": f"Answer to: {question}",
            "source_used": "private_kb",
            "citations": [{"source": "vpn.md", "type": "kb", "title": "VPN Guide"}],
            "trace": ["Router → KB", "Answer generated from PRIVATE KB"],
        }

    mini = FastAPI()
    mini.include_router(conversations.router, prefix="/api")
    web, as_a, as_b = TestClient(mini), {"Authorization": f"Bearer {ta}"}, {"Authorization": f"Bearer {tb}"}
    first_question = "How do I connect to the company VPN from home?"
    # Three questions a minute, whatever .env says, so the fourth one below runs into the limit.
    with tempfile.TemporaryDirectory() as folder, mock.patch("app.api.chat.ask", stand_in), mock.patch.multiple(settings, audit_db=Path(folder) / "audit.db", rate_limit_per_minute=3, rate_limit_per_day=0):
        limits.questions.reset()
        limits.calls.reset()
        made = web.post("/api/conversations", headers=as_a)
        if not step(made.status_code == 201 and made.json().get("title") == "New chat", "A creates a chat: POST /api/conversations", f"HTTP {made.status_code}: {made.text[:120]}"):
            return
        cid = made.json()["id"]
        base = f"/api/conversations/{cid}"
        first = web.post(f"{base}/messages", headers=as_a, json={"question": first_question})
        body = first.json() if first.status_code == 200 else {}
        step(
            body.get("saved") is True and body.get("warnings") == [] and body.get("title") == first_question,
            "A asks a question: it is answered, saved, and the chat is named after it",
            f"HTTP {first.status_code}: {first.text[:160]}",
        )
        invented = [{"question": "invented", "answer": "invented"}]
        second = web.post(f"{base}/messages", headers=as_a, json={"question": "What if it keeps dropping?", "history": invented})
        remembered = [{"question": first_question, "answer": f"Answer to: {first_question}"}]
        step(second.status_code == 200 and len(asked) == 2 and asked[1][1] == remembered, "a follow-up gets the first exchange from the database, and a history made up by the client is ignored")
        thread = web.get(f"{base}/messages", headers=as_a).json()
        step([m["role"] for m in thread] == ["user", "assistant"] * 2 and thread[1]["source_used"] == "private_kb" and thread[1]["citations"][0]["source"] == "vpn.md", "A reads the thread back: 4 messages in order, with their sources")
        step([c["id"] for c in web.get("/api/conversations", headers=as_a).json()] == [cid], "A's chat list shows the chat")
        renamed = web.patch(base, headers=as_a, json={"title": "My VPN chat"})
        step(renamed.status_code == 200 and renamed.json()["title"] == "My VPN chat", "A renames the chat")
        step(web.post(f"{base}/messages", headers=as_a, json={"question": "Thanks, that helped!"}).json().get("title") == "My VPN chat", "a title A chose is kept when A asks again")

        calls_before = len(asked)
        step(cid not in [c["id"] for c in web.get("/api/conversations", headers=as_b).json()], "A's chat is not in B's chat list")
        step(web.get(f"{base}/messages", headers=as_b).status_code == 404, "B cannot read A's chat: 404")
        step(web.post(f"{base}/messages", headers=as_b, json={"question": "B uses A's chat"}).status_code == 404 and len(asked) == calls_before, "B cannot ask in A's chat: 404, and the agent is never called")
        step(web.patch(base, headers=as_b, json={"title": "hacked"}).status_code == 404, "B cannot rename A's chat: 404")
        step(web.delete(base, headers=as_b).status_code == 404, "B cannot delete A's chat: 404")
        step(len(web.get(f"{base}/messages", headers=as_a).json()) == 6 and web.get("/api/conversations", headers=as_a).json()[0]["title"] == "My VPN chat", "A's chat is exactly as it was after B's attempts")
        step(web.get("/api/conversations").status_code == 401, "without a login token the chat list answers 401")

        rows = audit.recent()
        step(len(rows) == 3 and all(r["user_id"] == a and r["conversation_id"] == cid for r in rows), "the audit log has A's 3 questions with A's id and the chat id, and nothing for B (a temporary file)")

        over = web.post(f"{base}/messages", headers=as_a, json={"question": "One question more than the limit"})
        step(over.status_code == 429 and over.headers.get("retry-after", "").isdigit() and len(asked) == 3, "A's 4th question in a minute is refused: 429 with Retry-After, and the agent is never called", f"HTTP {over.status_code}: {over.text[:120]}")
        b_chat = web.post("/api/conversations", headers=as_b)
        b_reply = web.post(f"/api/conversations/{b_chat.json()['id']}/messages", headers=as_b, json={"question": "B asks while A is out of questions"}) if b_chat.status_code == 201 else b_chat
        step(b_reply.status_code == 200 and len(asked) == 4, "B can still ask: each person is counted on their own, by the user id in their real login token", f"HTTP {b_reply.status_code}: {b_reply.text[:120]}")
        step(web.get("/api/conversations", headers=as_a).status_code == 200 and web.get(f"{base}/messages", headers=as_a).status_code == 200, "A can still read and manage chats while out of questions")
        step(web.delete(base, headers=as_a).status_code == 204 and web.get("/api/conversations", headers=as_a).json() == [], "A deletes the chat: DELETE answers 204")
        left = request("GET", "/rest/v1/messages", key=settings.supabase_secret_key, params={"conversation_id": f"eq.{cid}"})
        step(left.status_code == 200 and left.json() == [], "its messages are gone too (looked at with the secret key)")


def full() -> None:
    """Two throwaway users: sign-in, our server's token check, and a try at each other's chats. The secret key is used only to make
    and delete the users and to look behind the privacy rules."""
    print("Two throwaway users")
    secret = get_settings().supabase_secret_key
    if not step(key_kind(secret) == "secret", "SUPABASE_SECRET_KEY is set and is a secret key", "only this test needs it (Project Settings > API Keys). The running app never does"):
        return

    def admin(method, path, **kw):
        return request(method, path, key=secret, **kw)

    def rest(method, table, token=None, **kw):
        return request(method, f"/rest/v1/{table}", token=token, **kw)

    def rows(reply):
        return reply.json() if reply.status_code < 300 and reply.content else []

    def blocked(reply):  # refused outright, or allowed but it touched nothing. Any other answer (400, 404...) is a surprise, not a pass
        return reply.status_code in (401, 403) or (reply.status_code < 300 and rows(reply) == [])

    ids, tokens, emails, label, back = [], [], [], secrets.token_hex(3), {"Prefer": "return=representation"}
    try:
        for name in ("a", "b"):
            email, password = f"rls-check-{label}-{name}@example.com", secrets.token_urlsafe(18)
            made = admin("POST", "/auth/v1/admin/users", json={"email": email, "password": password, "email_confirm": True})
            if not step(made.status_code == 200, f"user {name.upper()} created", f"HTTP {made.status_code}: {why(made)}"):
                return
            ids.append(made.json()["id"])
            emails.append(email)
            login = request("POST", "/auth/v1/token", params={"grant_type": "password"}, json={"email": email, "password": password})
            if not step(login.status_code == 200, f"user {name.upper()} signs in with email and password", f"HTTP {login.status_code}: {why(login)}"):
                return
            tokens.append(login.json()["access_token"])
        (a, b), (ta, tb) = ids, tokens
        login_tokens(ids, tokens, emails)

        print("Privacy between the two users")
        made = rest("POST", "conversations", ta, json={"title": "isolation check"}, headers=back)
        chat = rows(made)[0] if rows(made) else {}
        if not step(chat.get("user_id") == a, "A creates a chat, and the database stamps it with A's id", f"HTTP {made.status_code}: {why(made)}"):
            return
        cid = chat["id"]
        pair = [  # the same keys in both rows, so both fill the same columns
            {"conversation_id": cid, "role": "user", "content": "hello", "source_used": None, "citations": None, "trace": None, "latency_ms": None},
            {"conversation_id": cid, "role": "assistant", "content": "hi", "source_used": "direct", "citations": [], "trace": ["Direct answer (no search)"], "latency_ms": 5},
        ]
        saved = rest("POST", "messages", ta, json=pair, headers=back)
        step(saved.status_code == 201 and len(rows(saved)) == 2, "A saves a question and its answer in one request", f"HTTP {saved.status_code}: {why(saved)}")
        now = rows(rest("GET", "conversations", ta, params={"id": f"eq.{cid}"}))
        step(bool(now) and datetime.fromisoformat(now[0]["updated_at"]) > datetime.fromisoformat(chat["updated_at"]), "saving messages moves the chat to the top of A's list")
        thread = rows(rest("GET", "messages", ta, params={"conversation_id": f"eq.{cid}", "order": "id"}))
        step([m["role"] for m in thread] == ["user", "assistant"], "A reads the messages back in order")

        step(rows(rest("GET", "conversations", tb)) == [], "B's chat list is empty: B cannot see A's chat")
        step(rows(rest("GET", "messages", tb, params={"conversation_id": f"eq.{cid}"})) == [], "B cannot read A's messages")
        step(blocked(rest("POST", "messages", tb, json={"conversation_id": cid, "role": "user", "content": "intruder"}, headers=back)), "B cannot add a message to A's chat")
        step(blocked(rest("PATCH", "conversations", tb, params={"id": f"eq.{cid}"}, json={"title": "hacked"}, headers=back)), "B cannot rename A's chat")
        step(blocked(rest("DELETE", "conversations", tb, params={"id": f"eq.{cid}"}, headers=back)), "B cannot delete A's chat")
        again = rows(rest("GET", "conversations", ta, params={"id": f"eq.{cid}"}))
        step(bool(again) and again[0]["title"] == "isolation check", "after B's attempts, A's chat is exactly as it was")
        renamed = rows(rest("PATCH", "conversations", ta, params={"id": f"eq.{cid}"}, json={"title": "renamed"}, headers=back))
        step(bool(renamed) and renamed[0]["title"] == "renamed", "A renames A's own chat (the same request B's attempt used)")

        step(blocked(rest("POST", "conversations", ta, json={"user_id": b, "title": "forged"}, headers=back)), "A cannot create a chat in B's name")
        step(blocked(rest("POST", "messages", ta, json={"conversation_id": cid, "user_id": b, "role": "user", "content": "forged"}, headers=back)), "A cannot create a message in B's name")
        step(blocked(rest("PATCH", "messages", ta, params={"conversation_id": f"eq.{cid}"}, json={"content": "edited"}, headers=back)), "nobody can edit a saved message, not even its owner")
        step(blocked(rest("DELETE", "messages", ta, params={"conversation_id": f"eq.{cid}"}, headers=back)), "nobody can delete a single message, not even its owner")
        for table in ("conversations", "messages"):
            step(blocked(rest("GET", table)), f"{table}: someone who is not signed in sees nothing")

        step(len(rows(rest("POST", "conversations", tb, json={"title": "B's own chat"}, headers=back))) == 1, "B creates B's own chat (so deleting B's account has something to remove too)")
        step(len(rows(rest("DELETE", "conversations", ta, params={"id": f"eq.{cid}"}, headers=back))) == 1, "A deletes A's own chat")
        step(rows(admin("GET", "/rest/v1/messages", params={"conversation_id": f"eq.{cid}"})) == [], "deleting a chat deletes its messages too (looked at with the secret key)")
        saved_chats(ids, tokens)
    except Exception as exc:  # an odd reply or a dropped connection: say so, and still clean up below
        step(False, "the test stopped early", f"{type(exc).__name__}: {exc}")
    finally:
        deleted = [admin("DELETE", f"/auth/v1/admin/users/{user}").status_code for user in ids]
        if ids:
            owned = {"user_id": f"in.({','.join(ids)})"}
            left = rows(admin("GET", "/rest/v1/conversations", params=owned)) + rows(admin("GET", "/rest/v1/messages", params=owned))
            step(all(code == 200 for code in deleted) and not left, "both test users and everything they made are deleted", "delete the users whose email starts with rls-check- in Authentication > Users")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that the Supabase project is set up right.")
    parser.add_argument("--full", action="store_true", help="also make two test users and prove sign-in, our server's token check, and that users cannot reach each other's chats")
    args = parser.parse_args()
    try:
        quick()
        if args.full and failed:
            print("\nSkipping the full test until the checks above pass.")
        elif args.full:
            full()
    except SupabaseError as exc:
        step(False, "Supabase could not be used", str(exc))
    if failed:
        print(f"\n{len(failed)} problem(s). Fix the FAIL lines above, then run this again.")
        return 1
    print("\nAll good." + ("" if args.full else " Add --full to prove sign-in works and that users cannot see each other's chats."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
