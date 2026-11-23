"""Saved chats: the few calls the app needs to list, create, rename and delete a user's chats, and to save their messages.

Every call is made AS the signed-in user, with their login token, so the database's privacy rules decide what they can reach.
Someone else's chat looks exactly like a chat that does not exist. The secret key is never used here.
"""
import logging

from app.supabase.auth import User
from app.supabase.client import SupabaseError, request

log = logging.getLogger(__name__)

DEFAULT_TITLE = "New chat"  # the same default as supabase/schema.sql
TITLE_CHARS = 50  # a chat is named after its first question, cut here (and "…" is added when it was longer)
MAX_TITLE = 200  # the limits below are the ones in supabase/schema.sql
MAX_CONTENT = 10000
CHAT_COLUMNS = "id,title,created_at,updated_at"
MESSAGE_COLUMNS = "id,role,content,source_used,citations,trace,latency_ms,created_at"
RETURN_ROWS = {"Prefer": "return=representation"}  # without it a change answers with nothing, and "nothing changed" looks like "done"
EXPIRED = "Your session has expired. Please sign in again."
UNREACHABLE = "Your chats could not be reached right now. Please try again in a moment."


class ChatStoreError(Exception):
    """Supabase could not do what we asked. status 401 = the user's login token was refused (sign in again), 503 = anything else.
    The message is plain text for the user and never contains a key or a token."""

    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.status = status


def _why(reply) -> str:
    """The error code and message Supabase gave, for the log. Never its "details": those can quote the user's own text."""
    try:
        body = reply.json()
    except ValueError:
        return ""
    return f"{body.get('code', '')} {body.get('message', '')}".strip() if isinstance(body, dict) else ""


def _call(user: User, method: str, path: str, **kwargs):
    """One call as this user. Returns the JSON answer ([] when there is no body). Anything but success is a ChatStoreError."""
    try:
        reply = request(method, path, token=user.token, **kwargs)
    except SupabaseError as exc:
        log.warning("%s %s: %s", method, path, exc)
        raise ChatStoreError(UNREACHABLE) from exc
    if reply.status_code == 401:
        raise ChatStoreError(EXPIRED, 401)
    if reply.status_code >= 300:
        log.warning("Supabase answered HTTP %s to %s %s: %s", reply.status_code, method, path, _why(reply))
        raise ChatStoreError(UNREACHABLE)
    try:
        return reply.json() if reply.content else []
    except ValueError as exc:
        raise ChatStoreError(UNREACHABLE) from exc


# ---- titles and history ---------------------------------------------------------------------------------------------------


def clean_title(text: str) -> str:
    """One line, at most MAX_TITLE characters."""
    return " ".join(text.split())[:MAX_TITLE]


def make_title(question: str) -> str:
    """The name a chat gets from its first question: the question, cut at TITLE_CHARS with "…" when it was longer."""
    text = " ".join(question.split())
    return text if len(text) <= TITLE_CHARS + 2 else text[:TITLE_CHARS].rstrip() + "…"


def history_from(messages: list[dict]) -> list[dict]:
    """The earlier question-and-answer pairs of a chat, oldest first, in the shape ask() wants. A question that has no answer is skipped."""
    pairs, asked = [], None
    for message in messages:
        if message["role"] == "user":
            asked = message["content"]
        elif asked is not None:
            pairs.append({"question": asked, "answer": message["content"]})
            asked = None
    return pairs


# ---- chats ----------------------------------------------------------------------------------------------------------------


def list_chats(user: User, limit: int = 50) -> list[dict]:
    """The user's chats, the most recently used first."""
    return _call(user, "GET", "/rest/v1/conversations", params={"select": CHAT_COLUMNS, "order": "updated_at.desc", "limit": limit})


def create_chat(user: User, title: str | None = None) -> dict:
    """A new, empty chat. The database sets the owner from the login token."""
    rows = _call(
        user, "POST", "/rest/v1/conversations", params={"select": CHAT_COLUMNS}, json={"title": clean_title(title or "") or DEFAULT_TITLE}, headers=RETURN_ROWS
    )
    if not rows:
        raise ChatStoreError(UNREACHABLE)
    return rows[0]


def get_chat(user: User, chat_id: str, last: int) -> dict | None:
    """The chat with its newest `last` messages (oldest first), in one call. None if the user has no such chat."""
    rows = _call(
        user,
        "GET",
        "/rest/v1/conversations",
        params={"id": f"eq.{chat_id}", "select": f"{CHAT_COLUMNS},messages({MESSAGE_COLUMNS})", "messages.order": "id.desc", "messages.limit": last},
    )
    if not rows:
        return None
    chat = rows[0]
    chat["messages"].reverse()  # they came newest first
    return chat


def rename_chat(user: User, chat_id: str, title: str) -> dict | None:
    """The renamed chat, or None if the user has no such chat."""
    rows = _call(user, "PATCH", "/rest/v1/conversations", params={"id": f"eq.{chat_id}", "select": CHAT_COLUMNS}, json={"title": clean_title(title)}, headers=RETURN_ROWS)
    return rows[0] if rows else None


def delete_chat(user: User, chat_id: str) -> bool:
    """Delete the chat and (in the database) all its messages. False if the user has no such chat."""
    return bool(_call(user, "DELETE", "/rest/v1/conversations", params={"id": f"eq.{chat_id}", "select": "id"}, headers=RETURN_ROWS))


# ---- messages -------------------------------------------------------------------------------------------------------------


def save_exchange(user: User, chat_id: str, question: str, result: dict, latency_ms: int) -> None:
    """Save a question and the agent's answer (`result` is what ask() returned). One request saves both, so a chat never holds a
    question without its answer. The database moves the chat to the top of the list."""
    rows = [
        {"conversation_id": chat_id, "role": "user", "content": question, "source_used": None, "citations": None, "trace": None, "latency_ms": None},
        {
            "conversation_id": chat_id,
            "role": "assistant",
            "content": result["answer"][:MAX_CONTENT],
            "source_used": result["source_used"],
            "citations": result["citations"],
            "trace": result["trace"],
            "latency_ms": latency_ms,
        },
    ]
    _call(user, "POST", "/rest/v1/messages", json=rows, headers={"Prefer": "return=minimal"})


def name_if_new(user: User, chat_id: str, question: str) -> str | None:
    """Name a chat that still has the default title after its first question. A title the user chose is never replaced.
    Returns the new title, or None if the chat already had a title of its own."""
    rows = _call(
        user,
        "PATCH",
        "/rest/v1/conversations",
        params={"id": f"eq.{chat_id}", "title": f"eq.{DEFAULT_TITLE}", "select": "title"},
        json={"title": make_title(question)},
        headers=RETURN_ROWS,
    )
    return rows[0]["title"] if rows else None
