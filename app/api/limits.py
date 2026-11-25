"""Per-person limits on the saved-chat routes. In a route, `user: User = Depends(allow_question)` replaces `current_user`.

Both limits are counted per signed-in person (the user id in the verified login token), so signing in again does not reset them:
- questions: the calls that run the AI agent and spend the free AI tokens. RATE_LIMIT_PER_MINUTE and RATE_LIMIT_PER_DAY in .env.
- requests: every call to a chat route, so one account cannot hammer the database. Fixed, and far above what the pages need.
A refused call answers 429 with a plain message and a Retry-After header. It is not counted, and nothing else runs: no database call, no AI call.
"""
from fastapi import Depends, HTTPException

from app.api.account import current_user
from app.config import get_settings
from app.ratelimit import RateLimiter, Refused, wait_text
from app.supabase.auth import User

MINUTE, DAY = 60, 86_400
REQUESTS_PER_MINUTE = 120

questions, calls = RateLimiter(), RateLimiter()  # questions: the AI ones. calls: every chat route


def too_many(refused: Refused, what: str) -> HTTPException:
    wait = wait_text(refused.wait)
    n = f"{refused.most} question" + ("" if refused.most == 1 else "s")
    if what == "request":
        message = f"Too many requests. Please wait {wait} and try again."
    elif refused.window == MINUTE:
        message = f"You are asking too fast. The limit is {n} a minute. Please wait {wait} and ask again."
    else:
        message = f"You have asked {n} in the last 24 hours, which is the limit. You can ask again in {wait}."
    return HTTPException(status_code=429, detail=message, headers={"Retry-After": str(refused.wait)})


def allow_requests(user: User = Depends(current_user)) -> User:
    """The signed-in user, if they are not calling the chat routes too often. Every chat route has this (see the router)."""
    refused = calls.take(user.id, {MINUTE: REQUESTS_PER_MINUTE})
    if refused:
        raise too_many(refused, "request")
    return user


def allow_question(user: User = Depends(allow_requests)) -> User:
    """The signed-in user, if they have questions left. Only the route that asks the AI uses this."""
    settings = get_settings()
    refused = questions.take(user.id, {MINUTE: settings.rate_limit_per_minute, DAY: settings.rate_limit_per_day})
    if refused:
        raise too_many(refused, "question")
    return user


def refund_question(user: User) -> None:
    """The AI service was busy, so no answer came: that question should not count against the person."""
    questions.give_back(user.id)
