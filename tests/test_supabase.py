import base64
import json

import httpx
import pytest

from app.config import get_settings
from app.supabase import client
from app.supabase.client import SupabaseError

SECRET = "sb_secret_test"


def test_a_call_from_nobody_sends_the_publishable_key_in_apikey_and_no_token(supabase):
    client.request("GET", "/rest/v1/conversations", params={"select": "id"})
    (sent,) = supabase.requests
    assert str(sent.url) == "https://abc.supabase.co/rest/v1/conversations?select=id"
    assert sent.headers["apikey"] == supabase.publishable
    assert "authorization" not in sent.headers  # the new sb_ keys are not tokens


def test_a_signed_in_call_adds_the_users_token_and_keeps_the_callers_own_headers(supabase):
    client.request("POST", "/rest/v1/messages", token="user-token", json=[{"content": "hi"}], headers={"Prefer": "return=representation"})
    (sent,) = supabase.requests
    assert sent.headers["apikey"] == supabase.publishable and sent.headers["authorization"] == "Bearer user-token"
    assert sent.headers["prefer"] == "return=representation" and json.loads(sent.content) == [{"content": "hi"}]


def test_the_secret_key_is_used_only_when_the_caller_passes_it_in(supabase):
    client.request("GET", "/auth/v1/admin/users", key=SECRET)
    client.request("GET", "/auth/v1/settings")
    secret_call, normal_call = supabase.requests
    assert secret_call.headers["apikey"] == SECRET and "authorization" not in secret_call.headers
    assert normal_call.headers["apikey"] == supabase.publishable


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
    assert "ConnectError" in str(caught.value) and supabase.publishable not in str(caught.value)


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
def test_a_publishable_key_is_told_apart_from_a_secret_key(key, expected):
    """A secret key pasted into the publishable slot would be handed to every visitor of the sign-in page, so it must be caught."""
    assert client.key_kind(key) == expected
