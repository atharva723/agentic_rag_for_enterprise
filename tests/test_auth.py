"""Login tokens. All offline: the keys are made inside the tests, and a fake Supabase serves their public halves.

First every kind of token the server must refuse, then how the public keys are kept, then the routes that use them.
"""
import base64
import hashlib
import hmac
import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from app.config import get_settings
from app.main import app
from app.supabase import auth

USER = "11111111-1111-4111-8111-111111111111"
EMAIL = "ana@example.com"
ISSUER = "https://abc.supabase.co/auth/v1"
JWKS = "/auth/v1/.well-known/jwks.json"
web = TestClient(app)


# ---- helpers: keys, the key list Supabase publishes, and tokens ---------------------------------------------------------


@pytest.fixture(scope="module")
def key():
    """Supabase's signing key (the private half stays here, the public half is published)."""
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="module")
def other_key():
    """NOT Supabase's key. Nothing signed with it may be accepted."""
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwk(private_key, kid="k1"):
    """The public half of a key, the way Supabase lists it at /auth/v1/.well-known/jwks.json."""
    is_ec = isinstance(private_key, ec.EllipticCurvePrivateKey)
    to_jwk = (ECAlgorithm if is_ec else RSAAlgorithm).to_jwk
    return {**json.loads(to_jwk(private_key.public_key())), "kid": kid, "alg": "ES256" if is_ec else "RS256", "use": "sig"}


def claims(**changes):
    now = int(time.time())
    base = {"iss": ISSUER, "aud": "authenticated", "sub": USER, "role": "authenticated", "email": EMAIL, "is_anonymous": False, "iat": now, "exp": now + 3600}
    return {name: value for name, value in {**base, **changes}.items() if value is not None}  # pass None to leave a claim out


def token(private_key, *, kid="k1", alg="ES256", **changes):
    return jwt.encode(claims(**changes), private_key, algorithm=alg, headers={"kid": kid} if kid else {})


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unsigned():
    """A token with no signature at all, which says so itself ("alg": "none")."""
    return jwt.encode(claims(), None, algorithm="none", headers={"kid": "k1"})


def forged_hs256(private_key):
    """The classic trick: sign with HS256 using the PUBLIC key as the secret. A server that believes the token's own "alg" accepts it."""
    secret = private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    signing_input = f"{b64(json.dumps({'alg': 'HS256', 'typ': 'JWT', 'kid': 'k1'}).encode())}.{b64(json.dumps(claims()).encode())}"
    return f"{signing_input}.{b64(hmac.new(secret, signing_input.encode(), hashlib.sha256).digest())}"


def another_user_under_the_same_signature(good):
    """Someone else's id, with the signature of the real token."""
    head, _, signature = good.split(".")
    return f"{head}.{b64(json.dumps(claims(sub='22222222-2222-4222-8222-222222222222')).encode())}.{signature}"


@pytest.fixture(autouse=True)
def isolated(supabase):
    """Every test here talks to the fake Supabase, never the real one, and starts with an empty key cache."""
    auth.forget_keys()
    yield
    auth.forget_keys()


@pytest.fixture
def published(supabase, key):
    """Supabase publishes the public half of `key`."""
    supabase.payload = {"keys": [jwk(key)]}
    return supabase


@pytest.fixture
def clock(monkeypatch):
    """A clock for the key cache that the test moves by hand: clock[0] += 61 is 61 seconds later."""
    now = [1000.0]
    monkeypatch.setattr(auth, "_now", lambda: now[0])
    return now


# ---- the token ----------------------------------------------------------------------------------------------------------


def test_a_good_token_gives_the_signed_in_user(published, key):
    user = auth.verify_token(token(key))
    assert (user.id, user.email) == (USER, EMAIL)
    assert user.token not in repr(user)  # so a log line or an error page can never show it


def test_a_token_signed_with_rsa_is_accepted_too(supabase, rsa_key):
    supabase.payload = {"keys": [jwk(rsa_key, "r1")]}
    assert auth.verify_token(token(rsa_key, kid="r1", alg="RS256")).id == USER


def test_a_clock_that_is_a_few_seconds_off_is_forgiven(published, key):
    now = int(time.time())
    assert auth.verify_token(token(key, exp=now - 10)).id == USER  # a little late
    assert auth.verify_token(token(key, iat=now + 10)).id == USER  # a little early


REFUSED = {
    "expired": lambda k, o: token(k, exp=int(time.time()) - 120),
    "issued in the future": lambda k, o: token(k, iat=int(time.time()) + 120),
    "for another audience": lambda k, o: token(k, aud="somebody-else"),
    "from another project": lambda k, o: token(k, iss="https://evil.supabase.co/auth/v1"),
    "signed with another key": lambda k, o: token(o),
    "contents changed after signing": lambda k, o: another_user_under_the_same_signature(token(k)),
    "a key id that was never published": lambda k, o: token(k, kid="nope"),
    "no key id": lambda k, o: token(k, kid=None),
    "unsigned (alg none)": lambda k, o: unsigned(),
    "HS256 signed with the public key": lambda k, o: forged_hs256(k),
    "no expiry": lambda k, o: token(k, exp=None),
    "no user": lambda k, o: token(k, sub=None),
    "a user id that is not an id": lambda k, o: token(k, sub="not-an-id"),
    "the anon role": lambda k, o: token(k, role="anon"),
    "the service role": lambda k, o: token(k, role="service_role"),
    "an anonymous guest": lambda k, o: token(k, is_anonymous=True),
    "not a token": lambda k, o: "not.a.token",
    "empty": lambda k, o: "",
    "the publishable key": lambda k, o: "sb_publishable_test",
}


@pytest.mark.parametrize("name", REFUSED)
def test_a_token_that_must_not_be_trusted_is_refused(name, published, key, other_key):
    with pytest.raises(auth.AuthError) as caught:
        auth.verify_token(REFUSED[name](key, other_key))
    assert caught.value.status == 401


def test_a_token_that_names_the_wrong_algorithm_for_its_key_is_refused(published, rsa_key):
    with pytest.raises(auth.AuthError) as caught:  # k1 is an ES256 key, the token claims RS256
        auth.verify_token(token(rsa_key, kid="k1", alg="RS256"))
    assert caught.value.status == 401


def test_an_expired_token_says_so_and_an_anonymous_guest_is_told_to_sign_in_with_an_account(published, key):
    with pytest.raises(auth.AuthError, match="expired"):
        auth.verify_token(token(key, exp=int(time.time()) - 120))
    with pytest.raises(auth.AuthError, match="with an account"):
        auth.verify_token(token(key, is_anonymous=True))


def test_junk_is_refused_before_any_key_is_fetched(supabase, key):
    for junk in ("not.a.token", "", "sb_publishable_test", unsigned(), forged_hs256(key), token(key, kid=None)):
        with pytest.raises(auth.AuthError):
            auth.verify_token(junk)
    assert supabase.requests == []  # a stranger cannot make us call Supabase with these


def test_a_refused_token_is_never_written_to_the_log(published, key, caplog):
    caplog.set_level("DEBUG")
    bad = token(key, aud="somebody-else")
    with pytest.raises(auth.AuthError):
        auth.verify_token(bad)
    assert "InvalidAudienceError" in caplog.text  # the reason is logged...
    assert bad not in caplog.text and bad.split(".")[1] not in caplog.text  # ...the token is not


def test_with_accounts_switched_off_every_token_gets_503_and_no_call_is_made(supabase, key, monkeypatch):
    monkeypatch.setattr(get_settings(), "supabase_url", "")
    with pytest.raises(auth.AuthError, match="switched off") as caught:
        auth.verify_token(token(key))
    assert caught.value.status == 503 and supabase.requests == []


# ---- the public keys: when they are fetched, and what happens when Supabase is down -------------------------------------


def test_the_keys_are_fetched_once_and_kept(published, key):
    for _ in range(5):
        auth.verify_token(token(key))
    assert [request.url.path for request in published.requests] == [JWKS]


def test_the_keys_are_fetched_again_when_they_get_old(published, key, clock):
    auth.verify_token(token(key))
    clock[0] += auth.KEYS_FRESH_FOR - 1
    auth.verify_token(token(key))
    assert len(published.requests) == 1
    clock[0] += 2
    auth.verify_token(token(key))
    assert len(published.requests) == 2


def test_a_key_that_supabase_added_is_picked_up_but_never_more_than_once_a_minute(published, key, other_key, clock):
    auth.verify_token(token(key))
    published.payload = {"keys": [jwk(key), jwk(other_key, "k2")]}  # Supabase rotated: a second key appears
    new = token(other_key, kid="k2")
    clock[0] += 10
    with pytest.raises(auth.AuthError):  # too soon to look again
        auth.verify_token(new)
    assert len(published.requests) == 1
    clock[0] += auth.RETRY_AFTER
    assert auth.verify_token(new).id == USER
    assert len(published.requests) == 2


def test_junk_with_made_up_key_ids_cannot_make_us_hammer_supabase(published, key, clock):
    auth.verify_token(token(key))
    for i in range(50):
        with pytest.raises(auth.AuthError):
            auth.verify_token(token(key, kid=f"made-up-{i}"))
    assert len(published.requests) == 1
    clock[0] += auth.RETRY_AFTER + 1
    for i in range(50):
        with pytest.raises(auth.AuthError):
            auth.verify_token(token(key, kid=f"more-{i}"))
    assert len(published.requests) == 2  # one more look in the next minute, not fifty


def test_when_supabase_is_down_at_the_start_the_answer_is_503_not_401(published, key, clock):
    published.error = httpx.ConnectError("down")
    with pytest.raises(auth.AuthError, match="try again") as first:
        auth.verify_token(token(key))
    assert first.value.status == 503
    with pytest.raises(auth.AuthError) as second:  # still down, and we do not ask again for a minute
        auth.verify_token(token(key))
    assert second.value.status == 503 and len(published.requests) == 1
    published.error = None
    clock[0] += auth.RETRY_AFTER + 1
    assert auth.verify_token(token(key)).id == USER  # and it recovers by itself


def test_keys_that_were_loaded_keep_working_while_supabase_is_down(published, key, clock):
    auth.verify_token(token(key))
    published.error = httpx.ConnectError("down")
    clock[0] += auth.KEYS_FRESH_FOR + 1  # due for a refresh, which now fails
    assert auth.verify_token(token(key)).id == USER
    assert len(published.requests) == 2  # it did try


@pytest.mark.parametrize(
    "status, payload",
    [
        (500, {}),
        (200, {"keys": []}),
        (200, {"keys": [{"kty": "oct", "kid": "k1", "k": "c2VjcmV0"}]}),
        (200, {"nothing": "here"}),
        (200, ["not", "a", "key", "list"]),
    ],
    ids=["supabase error", "no keys", "only a shared secret", "no key list", "not a key list"],
)
def test_a_key_list_we_cannot_use_is_503(supabase, key, status, payload):
    supabase.status, supabase.payload = status, payload
    with pytest.raises(auth.AuthError) as caught:
        auth.verify_token(token(key))
    assert caught.value.status == 503


def test_a_key_we_do_not_use_does_not_spoil_the_others(supabase, key):
    odd = [{"kty": "OKP", "crv": "Ed25519", "x": "AAAA", "kid": "e1"}, {"kty": "oct", "k": "c2VjcmV0", "kid": "s1"}, "junk"]
    supabase.payload = {"keys": [*odd, jwk(key)]}
    assert auth.verify_token(token(key)).id == USER


# ---- the routes ---------------------------------------------------------------------------------------------------------


def bearer(login_token):
    return {"Authorization": f"Bearer {login_token}"}


def test_me_with_a_good_token_gives_the_id_and_email(published, key):
    reply = web.get("/api/me", headers=bearer(token(key)))
    assert reply.status_code == 200 and reply.json() == {"id": USER, "email": EMAIL}


def test_me_without_a_token_asks_for_a_sign_in_and_calls_nobody(published):
    reply = web.get("/api/me")
    assert reply.status_code == 401 and reply.json() == {"detail": "Please sign in."}
    assert reply.headers["www-authenticate"] == "Bearer" and published.requests == []


def test_me_ignores_any_other_kind_of_authorization(published, key):
    assert web.get("/api/me", headers={"Authorization": f"Basic {token(key)}"}).status_code == 401


def test_me_with_a_bad_token_says_why_in_plain_words(published, key):
    reply = web.get("/api/me", headers=bearer(token(key, exp=int(time.time()) - 120)))
    assert reply.status_code == 401 and "expired" in reply.json()["detail"]
    assert reply.headers["www-authenticate"] == "Bearer"


def test_me_says_503_when_the_check_cannot_be_done_right_now(published, key):
    published.error = httpx.ConnectError("down")
    reply = web.get("/api/me", headers=bearer(token(key)))
    assert reply.status_code == 503 and "try again" in reply.json()["detail"] and "www-authenticate" not in reply.headers


def test_me_says_accounts_are_switched_off_when_supabase_is_not_set_up(key, monkeypatch):
    monkeypatch.setattr(get_settings(), "supabase_url", "")
    reply = web.get("/api/me", headers=bearer(token(key)))
    assert reply.status_code == 503 and "switched off" in reply.json()["detail"]


def test_config_gives_the_sign_in_page_the_project_address_and_the_publishable_key():
    assert web.get("/api/config").json() == {"supabase": {"url": "https://abc.supabase.co", "publishable_key": "sb_publishable_test"}}


def test_config_says_there_are_no_accounts_when_supabase_is_not_set_up(monkeypatch):
    monkeypatch.setattr(get_settings(), "supabase_url", "")
    reply = web.get("/api/config")
    assert reply.status_code == 200 and reply.json() == {"supabase": None}


def test_config_never_hands_out_the_secret_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_secret_key", "sb_secret_SENTINEL")
    assert "sb_secret_SENTINEL" not in web.get("/api/config").text
    monkeypatch.setattr(settings, "supabase_publishable_key", "sb_secret_SENTINEL")  # pasted into the wrong place in .env
    reply = web.get("/api/config")
    assert reply.status_code == 503 and "not a publishable key" in reply.json()["detail"]
    assert "sb_secret_SENTINEL" not in reply.text
