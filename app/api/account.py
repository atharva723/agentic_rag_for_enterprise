"""Accounts: who is signed in, and what the sign-in page needs to know."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.supabase import auth
from app.supabase.client import configured, key_kind

router = APIRouter()
bearer = HTTPBearer(auto_error=False)  # a missing token is answered below, in plain words


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> auth.User:
    """The signed-in user. Add `user: auth.User = Depends(current_user)` to a route to make it need a sign-in.

    The browser sends `Authorization: Bearer <login token>`. Answers 401 when there is no valid token (sign in, or sign in again),
    and 503 when the check cannot be done right now (accounts are switched off, or Supabase cannot be reached).
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Please sign in.", headers={"WWW-Authenticate": "Bearer"})
    try:
        return auth.verify_token(credentials.credentials)
    except auth.AuthError as exc:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
        raise HTTPException(status_code=exc.status, detail=str(exc), headers=headers) from exc


@router.get("/me")
def me(user: auth.User = Depends(current_user)):
    return {"id": user.id, "email": user.email}


@router.get("/config")
def sign_in_settings():
    """What the sign-in page needs to talk to Supabase. It is all safe to show to anyone, so no sign-in is needed to read it."""
    if not configured():
        return {"supabase": None}  # accounts are switched off: the page works without a sign-in
    settings = get_settings()
    if key_kind(settings.supabase_publishable_key) != "publishable":  # a secret key here would be handed to every visitor
        raise HTTPException(
            status_code=503,
            detail="SUPABASE_PUBLISHABLE_KEY in .env is not a publishable key (sb_publishable_...). The secret key must never be shown in a browser.",
        )
    return {"supabase": {"url": settings.supabase_url.rstrip("/"), "publishable_key": settings.supabase_publishable_key}}
