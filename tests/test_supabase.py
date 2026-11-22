import base64
import json

import httpx
import pytest

from app.config import get_settings
from app.supabase import check, client
from app.supabase.client import SupabaseError

PUBLISHABLE = "sb_publishable_test"
SECRET = "sb_secret_test"


class FakeSupabase:
    """Stands in for the Supabase server. Set what it answers, then read what it was sent."""

    def __init__(self):
        self.status, self.payload, self.error, self.requests = 200, [], None, []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error:
            raise self.error
        return httpx.Response(self.status, json=self.payload)


@pytest.fixture
def supabase(monkeypatch):
    """Swap the network for a fake Supabase. The real request() still runs, so URL and header handling are tested."""
    fake = FakeSupabase()
    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", "https://abc.supabase.co/")  # the trailing slash must not double up
    monkeypatch.setattr(settings, "supabase_publishable_key", PUBLISHABLE)
    real_client = httpx.Client
    monkeypatch.setattr(client.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(fake.handle), **kwargs))
    client._http.cache_clear()
    yield fake
    client._http.cache_clear()


def test_a_call_from_nobody_sends_the_publishable_key_in_apikey_and_no_token(supabase):
    client.request("GET", "/rest/v1/conversations", params={"select": "id"})
    (sent,) = supabase.requests
    assert str(sent.url) == "https://abc.supabase.co/rest/v1/conversations?select=id"
    assert sent.headers["apikey"] == PUBLISHABLE
    assert "authorization" not in sent.headers  # the new sb_ keys are not tokens


def test_a_signed_in_call_adds_the_users_token_and_keeps_the_callers_own_headers(supabase):
    client.request("POST", "/rest/v1/messages", token="user-token", json=[{"content": "hi"}], headers={"Prefer": "return=representation"})
    (sent,) = supabase.requests
    assert sent.headers["apikey"] == PUBLISHABLE and sent.headers["authorization"] == "Bearer user-token"
    assert sent.headers["prefer"] == "return=representation" and json.loads(sent.content) == [{"content": "hi"}]


def test_the_secret_key_is_used_only_when_the_caller_passes_it_in(supabase):
    client.request("GET", "/auth/v1/admin/users", key=SECRET)
    client.request("GET", "/auth/v1/settings")
    secret_call, normal_call = supabase.requests
    assert secret_call.headers["apikey"] == SECRET and "authorization" not in secret_call.headers
    assert normal_call.headers["apikey"] == PUBLISHABLE


def test_an_old_style_key_is_a_token_so_it_is_sent_both_ways():
    assert client.headers("eyJhbGciOi.old.key") == {"apikey": "eyJhbGciOi.old.key", "Authorization": "Bearer eyJhbGciOi.old.key"}


def test_an_error_status_is_returned_for_the_caller_to_judge(supabase):
    supabase.status, supabase.payload = 401, {"code": "42501", "message": "permission denied for table conversations"}
    assert client.request("GET", "/rest/v1/conversations").status_code == 401


def test_it_refuses_to_call_when_supabase_is_not_set_up(supabase, monkeypatch):
    monkeypatch.setattr(get_settings(), "supabase_url", "")
    with pytest.raises(SupabaseError, match="SUPABASE_URL"):
        client.request("GET", "/auth/v1/settings")
    assert supabase.requests == []


def test_an_unreachable_supabase_is_a_plain_error_that_never_contains_the_key(supabase):
    supabase.error = httpx.ConnectError("boom")
    with pytest.raises(SupabaseError) as caught:
        client.request("GET", "/auth/v1/settings")
    assert "ConnectError" in str(caught.value) and PUBLISHABLE not in str(caught.value)


def old_style_key(role):
    part = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{part}.signature"


@pytest.mark.parametrize(
    "key, expected",
    [
        ("sb_publishable_x", "publishable"),
        ("sb_secret_x", "secret"),
        (old_style_key("anon"), "publishable"),
        (old_style_key("service_role"), "secret"),
        ("not a key", "unknown"),
        ("a.b.c", "unknown"),
    ],
)
def test_the_check_can_tell_a_publishable_key_from_a_secret_key(key, expected):
    """A secret key pasted into the publishable slot would one day be shown in a browser, so the check must catch it."""
    assert check.kind(key) == expected
