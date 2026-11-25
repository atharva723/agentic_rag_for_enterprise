"""Saved chats: a signed-in user's conversations and their messages. Every route here needs a sign-in."""
import time
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, StringConstraints
from starlette.concurrency import run_in_threadpool

from app.api.account import current_user
from app.api.chat import run_agent
from app.api.limits import allow_question, allow_requests, refund_question
from app.api.streaming import stream
from app.audit import write_audit
from app.config import get_settings
from app.supabase import conversations as chats
from app.supabase.auth import User
from app.supabase.conversations import ChatStoreError

router = APIRouter(prefix="/conversations", dependencies=[Depends(allow_requests)])  # every chat route has a per-person request limit

NO_MEMORY = "Your earlier messages in this chat could not be loaded, so this answer treats your question on its own."
NOT_SAVED = "This answer could not be saved to your chat history."

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=chats.MAX_TITLE)]


class NewChat(BaseModel):
    title: Title | None = None  # leave it out and the first question names the chat


class Rename(BaseModel):
    title: Title


class MessageRequest(BaseModel):
    """Only the question. The earlier messages come from the database, never from the request, so nobody can invent a chat history."""

    question: str = Field(min_length=2, max_length=3000)


def failure(exc: ChatStoreError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc), headers={"WWW-Authenticate": "Bearer"} if exc.status == 401 else None)


@contextmanager
def store_errors():
    """Turn "Supabase could not do it" into the plain HTTP answer: 401 sign in again, 503 try again in a moment."""
    try:
        yield
    except ChatStoreError as exc:
        raise failure(exc) from exc


def not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Chat not found.")  # also what someone else's chat looks like


@router.get("")
def list_chats(limit: int = Query(50, ge=1, le=100), user: User = Depends(current_user)):
    with store_errors():
        return chats.list_chats(user, limit)


@router.post("", status_code=201)
def create_chat(req: NewChat | None = None, user: User = Depends(current_user)):
    with store_errors():
        return chats.create_chat(user, req.title if req else None)


@router.patch("/{chat_id}")
def rename_chat(chat_id: UUID, req: Rename, user: User = Depends(current_user)):
    with store_errors():
        chat = chats.rename_chat(user, str(chat_id), req.title)
    if chat is None:
        raise not_found()
    return chat


@router.delete("/{chat_id}", status_code=204)
def delete_chat(chat_id: UUID, user: User = Depends(current_user)):
    with store_errors():
        deleted = chats.delete_chat(user, str(chat_id))
    if not deleted:
        raise not_found()
    return Response(status_code=204)


@router.get("/{chat_id}/messages")
def read_messages(chat_id: UUID, limit: int = Query(200, ge=1, le=500), user: User = Depends(current_user)):
    """The newest `limit` messages of the chat, oldest first."""
    with store_errors():
        chat = chats.get_chat(user, str(chat_id), last=limit)
    if chat is None:
        raise not_found()
    return chat["messages"]


def open_chat(user: User, chat_id: UUID) -> tuple[str, dict | None, list[str]]:
    """Check that the chat is the user's and load its last few messages for the agent. Everything here that can be a plain HTTP answer
    (sign in again, not found) happens BEFORE anything is streamed and before any AI token is spent, so a chat that is not theirs costs
    nothing. Returns (the chat id, the chat or None when it could not be read, warnings)."""
    chat_key, warnings = str(chat_id), []
    try:
        chat = chats.get_chat(user, chat_key, last=2 * max(get_settings().memory_turns, 1) + 2)  # the agent reads the last few pairs. A little extra covers an odd start
    except ChatStoreError as exc:
        if exc.status == 401:
            raise failure(exc) from exc
        chat = None
        warnings.append(NO_MEMORY)
    else:
        if chat is None:
            raise not_found()
    return chat_key, chat, warnings


def answer_in_chat(user: User, chat_key: str, chat: dict | None, warnings: list[str], question: str, on_step=None) -> dict:
    """Run the agent on the question, then audit and save the exchange. on_step hears about each step of the agent as it happens.
    Raises a 429 HTTPException when the AI service is busy. Returns what the page needs (see send_message)."""
    started = time.perf_counter()
    try:
        result = run_agent(question, chats.history_from(chat["messages"]) if chat else [], on_step)
    except HTTPException:  # the AI service is busy (run_agent's only HTTP error): not the person's doing, so it does not count against them
        refund_question(user)
        raise
    latency_ms = round((time.perf_counter() - started) * 1000)
    write_audit(question, result["source_used"], result["trace"], user_id=user.id, conversation_id=chat_key)

    title, saved = chat["title"] if chat else None, False
    try:
        chats.save_exchange(user, chat_key, question, result, latency_ms)
        saved = True
    except ChatStoreError:
        warnings.append(NOT_SAVED)
    if saved:
        try:
            title = chats.name_if_new(user, chat_key, question) or title
        except ChatStoreError:
            pass  # the chat keeps its old title until the next message
    return {
        "answer": result["answer"],
        "source_used": result["source_used"],
        "citations": result["citations"],
        "trace": result["trace"],
        "saved": saved,
        "title": title,
        "warnings": warnings,
    }


@router.post("/{chat_id}/messages")
def send_message(chat_id: UUID, req: MessageRequest, user: User = Depends(allow_question)):
    """Ask a question in a saved chat. The chat's earlier messages are loaded from the database so a follow-up makes sense, the
    agent answers, and the question and answer are saved. The chat must belong to the user, and that is checked BEFORE the agent
    runs, so a chat that is not theirs costs no AI tokens.

    Each person may ask only so many questions a minute and a day (429 and a Retry-After header after that, checked before anything
    else runs). A question the AI service was too busy to answer does not count.

    If the chat cannot be read (a Supabase problem), the question is still answered, on its own, with a warning. If the answer
    cannot be saved, it is still returned, with saved=false and a warning."""
    chat_key, chat, warnings = open_chat(user, chat_id)
    return answer_in_chat(user, chat_key, chat, warnings, req.question)


@router.post("/{chat_id}/messages/stream")
async def stream_message(chat_id: UUID, req: MessageRequest, user: User = Depends(allow_question)):
    """The same as the route above (same sign-in, same limits, same saving), but the reply arrives as Server-Sent Events so the page can
    show the path while the agent works instead of a blank spinner:

        event: step     {"step": "retrieve_kb", "status": "start", "label": "Searching the company documents…"}
        event: step     {"step": "retrieve_kb", "status": "done", "lines": ["Private KB retrieval → 4 chunks"]}
        ...
        event: answer   what the route above returns: {"answer", "source_used", "citations", "trace", "saved", "title", "warnings"}
        event: error    {"status": 429, "detail": "..."}  instead of "answer", when the AI service is busy or something broke

    A chat that is not yours, a missing sign-in and a limit that is used up are still plain HTTP answers (404, 401, 429), sent before
    anything is streamed. The job runs in its own thread, so a page that closes mid-answer does not stop it: the answer is still saved."""
    chat_key, chat, warnings = await run_in_threadpool(open_chat, user, chat_id)  # blocking database calls: not on the event loop
    return stream(lambda emit: answer_in_chat(user, chat_key, chat, warnings, req.question, lambda event: emit("step", event)))
