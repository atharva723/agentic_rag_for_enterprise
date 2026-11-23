"""Who is calling? Checks the login token of a signed-in user, on our own server, with no call to Supabase for each request.

Supabase gives a signed-in user a login token (a JWT) that it signed with a PRIVATE key. It publishes the matching PUBLIC keys at
/auth/v1/.well-known/jwks.json. Anyone can check a signature with a public key, but nobody can forge one without the private key.
So we fetch the public keys once, keep them in memory, and check every token against them: the signature, who issued it, that it
is for signed-in users, and that it has not expired.

A token cannot be called back. After sign-out it still passes until it expires (Supabase's default is 1 hour).
"""
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

import jwt

from app.config import get_settings
from app.supabase.client import SupabaseError, configured, request

log = logging.getLogger(__name__)

ALGORITHMS = ("ES256", "RS256")  # public-key signatures only. A token that names any other algorithm (none, HS256...) is refused
SIGNED_IN = "authenticated"  # the audience AND the database role of a signed-in user's token. The publishable key's "anon" role is neither
LEEWAY = 30  # seconds of clock difference between Supabase and this machine that we forgive
KEYS_FRESH_FOR = 600  # seconds before the key list is fetched again. Supabase itself caches it for about 10 minutes
RETRY_AFTER = 60  # seconds. Whatever tokens arrive, we ask Supabase for its key list at most once in this time

SIGN_IN_AGAIN = "Could not verify your sign-in. Please sign in again."
EXPIRED = "Your session has expired. Please sign in again."
NOT_NOW = "Sign-in could not be checked right now. Please try again in a moment."
NEED_ACCOUNT = "Please sign in with an account."
SWITCHED_OFF = "Accounts are switched off. Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY in .env (see supabase/README.md)."


class AuthError(Exception):
    """This token must not be accepted. The message is plain text for the user and never contains the token.

    status 401 = sign in (again). status 503 = we cannot check right now: accounts are not set up, or Supabase cannot be reached.
    """

    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class User:
    id: str
    email: str
    token: str = field(repr=False)  # the login token itself. It is passed on to Supabase so the database applies THIS user's rules. Never log it


# ---- the public keys ----------------------------------------------------------------------------------------------

_lock = threading.Lock()
_keys: dict[str, jwt.PyJWK] = {}  # key id -> public key
_loaded_at = _asked_at = float("-inf")  # when the key list last loaded, and when we last asked for it (whether or not that worked)


def _now() -> float:
    return time.monotonic()


def forget_keys() -> None:
    """Empty the key cache, so the next token makes us ask Supabase again. The tests use this."""
    global _keys, _loaded_at, _asked_at
    with _lock:
        _keys, _loaded_at, _asked_at = {}, float("-inf"), float("-inf")


def _download_keys() -> dict[str, jwt.PyJWK]:
    """Ask Supabase for its public keys. Raises AuthError (503) if that does not work."""
    try:
        reply = request("GET", "/auth/v1/.well-known/jwks.json")
    except SupabaseError as exc:
        log.warning("Could not fetch Supabase's public keys: %s", exc)
        raise AuthError(NOT_NOW, 503) from exc
    if reply.status_code != 200:
        log.warning("Supabase's key list answered HTTP %s", reply.status_code)
        raise AuthError(NOT_NOW, 503)
    try:
        listed = reply.json()["keys"]
        keys = {}
        for item in listed:
            try:
                key = jwt.PyJWK(item)
            except (jwt.PyJWTError, AttributeError, TypeError):  # a kind of key we do not use
                continue
            if key.key_id and key.algorithm_name in ALGORITHMS:
                keys[key.key_id] = key
    except (ValueError, KeyError, TypeError):
        log.warning("Supabase's key list could not be read")
        raise AuthError(NOT_NOW, 503) from None
    if not keys:
        log.warning("Supabase listed no public signing keys. Switch the project to the new JWT signing keys (Project Settings > JWT Keys)")
    return keys


def _signing_key(kid: str) -> jwt.PyJWK:
    """The public key with this id. The list is kept in memory and fetched again only when it is due, or when a token names a key we
    do not know (Supabase may have rotated its keys). Even then it is at most once in RETRY_AFTER seconds, so junk tokens cannot make
    us hammer Supabase."""
    global _keys, _loaded_at, _asked_at
    with _lock:
        now = _now()
        due = now - _loaded_at > KEYS_FRESH_FOR or kid not in _keys
        if due and now - _asked_at > RETRY_AFTER:
            _asked_at = now
            try:
                _keys, _loaded_at = _download_keys(), now
            except AuthError:
                if not _keys:  # nothing to fall back on
                    raise
                log.warning("Using the Supabase keys loaded earlier")  # an old list still checks signatures just as well
        key = _keys.get(kid)
        loaded_any = bool(_keys)
    if key is None:
        if loaded_any:
            raise AuthError(SIGN_IN_AGAIN)  # a key id we do not know: a forged token, or Supabase rotated its keys a moment ago
        raise AuthError(NOT_NOW, 503)  # we never managed to load any key
    return key


# ---- the token ------------------------------------------------------------------------------------------------------


def verify_token(token: str) -> User:
    """The signed-in user this login token belongs to. Raises AuthError if the token must not be accepted."""
    if not configured():
        raise AuthError(SWITCHED_OFF, 503)
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:  # not a token at all (for example the publishable key)
        raise AuthError(SIGN_IN_AGAIN) from None
    alg, kid = header.get("alg"), header.get("kid")
    if alg not in ALGORITHMS or not isinstance(kid, str) or not kid:  # "none" and HS256 end here, before any key is looked at
        raise AuthError(SIGN_IN_AGAIN)
    key = _signing_key(kid)
    if key.algorithm_name != alg:  # a token must use the algorithm its key was made for
        raise AuthError(SIGN_IN_AGAIN)
    try:
        claims = jwt.decode(
            token,
            key.key,
            algorithms=[alg],
            audience=SIGNED_IN,
            issuer=get_settings().supabase_url.rstrip("/") + "/auth/v1",  # the project that signed it must be OUR project
            leeway=LEEWAY,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthError(EXPIRED) from None
    except jwt.PyJWTError as exc:
        log.info("Login token refused: %s", type(exc).__name__)
        raise AuthError(SIGN_IN_AGAIN) from None
    if claims.get("role") != SIGNED_IN or claims.get("is_anonymous"):  # no "anon" or "service_role" tokens, and no anonymous guests
        raise AuthError(NEED_ACCOUNT)
    try:
        user_id = str(uuid.UUID(str(claims["sub"])))  # a real user id, so it is safe to put in a database filter later
    except ValueError:
        raise AuthError(SIGN_IN_AGAIN) from None
    return User(id=user_id, email=str(claims.get("email") or ""), token=token)
