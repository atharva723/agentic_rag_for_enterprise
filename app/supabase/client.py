"""The one place that talks HTTP to Supabase. The rest of app/supabase/ calls request() and never builds a header itself.

A call is made as one of two people:
- nobody: only the publishable key. The database sees the "anon" role.
- a signed-in user: the publishable key plus that user's login token. The database sees "authenticated" and that user's id,
  so the row-level security rules in supabase/schema.sql decide what the call can reach.
The secret key skips those rules. Only the check command passes it in. The running app never does.
"""
import base64
import json
from functools import lru_cache

import httpx

from app.config import get_settings

TIMEOUT = 15  # seconds


class SupabaseError(RuntimeError):
    """Supabase is not set up, or could not be reached. The message is plain text and never contains a key."""


@lru_cache
def _http() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT)


def configured() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url and settings.supabase_publishable_key)


def key_kind(key: str) -> str:
    """"publishable", "secret" or "unknown". Only the kind of key is read: the key itself is never shown or logged."""
    if key.startswith("sb_publishable_"):
        return "publishable"
    if key.startswith("sb_secret_"):
        return "secret"
    try:  # an old-style key is a token that names its own role
        part = key.split(".")[1]
        role = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("role")
    except (IndexError, ValueError, AttributeError):
        return "unknown"
    return {"anon": "publishable", "service_role": "secret"}.get(role, "unknown")


def headers(key: str, token: str | None = None) -> dict:
    """apikey says which key is calling. A user's token says who is asking.

    The new sb_ keys are not tokens, so they go only in apikey, never in Authorization. An old-style key is itself a token, so it goes in both.
    """
    out = {"apikey": key}
    bearer = token or (None if key.startswith("sb_") else key)
    if bearer:
        out["Authorization"] = f"Bearer {bearer}"
    return out


def request(method: str, path: str, *, token: str | None = None, key: str | None = None, **kwargs) -> httpx.Response:
    """Call Supabase and return the response whatever its status, so the caller decides what a 4xx means.

    path starts with /rest/v1/ (the database) or /auth/v1/ (accounts). Other keyword arguments (json, params, headers) go to httpx.
    Raises SupabaseError if Supabase is not set up or cannot be reached.
    """
    if not configured():
        raise SupabaseError("Supabase is not set up. Put SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY in .env (see supabase/README.md).")
    settings = get_settings()
    extra = kwargs.pop("headers", {})
    try:
        return _http().request(
            method,
            settings.supabase_url.rstrip("/") + path,
            headers={**headers(key or settings.supabase_publishable_key, token), **extra},
            **kwargs,
        )
    except httpx.HTTPError as exc:  # no internet, DNS failure, timeout
        raise SupabaseError(f"Supabase could not be reached ({type(exc).__name__}).") from exc
