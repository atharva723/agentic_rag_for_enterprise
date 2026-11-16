import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)
ADMIN = {"X-Admin-Key": "secret"}


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_api_key", "secret")
    monkeypatch.setattr(settings, "audit_db", tmp_path / "audit.db")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_chat_page_is_served():
    assert "<title>" in client.get("/").text


def test_admin_routes_need_the_right_key():
    assert client.get("/api/audit").status_code == 401
    assert client.get("/api/audit", headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert client.get("/api/audit", headers=ADMIN).json() == []


def test_admin_routes_are_off_when_no_key_is_set(monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_api_key", "")
    assert client.get("/api/audit", headers={"X-Admin-Key": ""}).status_code == 401


def test_upload_saves_the_file_and_ingests_it(monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.admin.ingest_file", lambda path: 3)
    res = client.post("/api/ingest", headers=ADMIN, files={"file": ("vpn.md", b"# VPN")})
    assert res.json() == {"file": "vpn.md", "chunks": 3}
    assert (tmp_path / "uploads" / "vpn.md").exists()


def test_upload_rejects_unsupported_types():
    res = client.post("/api/ingest", headers=ADMIN, files={"file": ("tool.exe", b"x")})
    assert res.status_code == 400


def test_an_unreadable_upload_is_a_clear_422_and_leaves_no_file(monkeypatch, tmp_path):
    def refuse(path):
        raise ValueError("No readable text found in blank.md")

    monkeypatch.setattr("app.api.admin.ingest_file", refuse)
    res = client.post("/api/ingest", headers=ADMIN, files={"file": ("blank.md", b" ")})
    assert res.status_code == 422
    assert "No readable text" in res.json()["detail"]
    assert not (tmp_path / "uploads" / "blank.md").exists()


def fake_result(**extra):
    return {"answer": "Open NovaConnect.", "source_used": "private_kb", "citations": [{"source": "vpn.md", "type": "kb"}], "trace": ["Router → KB"], **extra}


def test_chat_returns_the_answer_sources_and_trace_and_writes_the_audit(monkeypatch):
    monkeypatch.setattr("app.api.chat.ask", lambda question: fake_result())
    res = client.post("/api/chat", json={"question": "How do I connect to the VPN?"})
    assert res.status_code == 200
    assert res.json() == {
        "answer": "Open NovaConnect.",
        "source_used": "private_kb",
        "citations": [{"source": "vpn.md", "type": "kb"}],
        "trace": ["Router → KB"],
    }
    (entry,) = client.get("/api/audit", headers=ADMIN).json()
    assert entry["question"] == "How do I connect to the VPN?" and entry["trace"] == ["Router → KB"]


def test_chat_says_busy_when_the_ai_provider_rate_limit_is_hit(monkeypatch):
    class RateLimited(Exception):
        status_code = 429

    def busy(question):
        raise RateLimited("tokens per day limit reached")

    monkeypatch.setattr("app.api.chat.ask", busy)
    res = client.post("/api/chat", json={"question": "anything"})
    assert res.status_code == 429
    assert "busy" in res.json()["detail"] and "tokens per day" not in res.json()["detail"]  # no provider details leak


def test_chat_other_failures_are_a_plain_500_without_details(monkeypatch):
    def broken(question):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr("app.api.chat.ask", broken)
    res = TestClient(app, raise_server_exceptions=False).post("/api/chat", json={"question": "anything"})
    assert res.status_code == 500
    assert "secret internal detail" not in res.text
