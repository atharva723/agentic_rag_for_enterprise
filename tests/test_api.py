import re
import threading

import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app.config import ROOT, get_settings
from app.main import app

client = TestClient(app)
ADMIN = {"X-Admin-Key": "secret"}
LOCAL_LINK = re.compile(r'(?:href|src)="(?!https?:|//|#|data:|mailto:)([^"#?]+)')  # a page, script, style or image next to the page


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


def test_admin_routes_are_off_when_no_key_is_set_and_say_so(monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_api_key", "")
    for headers in ({}, {"X-Admin-Key": ""}, {"X-Admin-Key": "anything"}):  # an empty key must never match an empty header
        res = client.get("/api/audit", headers=headers)
        assert res.status_code == 403 and "ADMIN_API_KEY" in res.json()["detail"]
    assert client.post("/api/ingest", files={"file": ("a.md", b"# A")}).status_code == 403


def test_the_page_files_are_served_and_always_rechecked_by_the_browser():
    for path in ("/", "/app.js", "/style.css"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert res.headers["cache-control"] == "no-cache", path  # an updated page must not run an old, cached script


def test_every_page_is_served_and_every_file_the_pages_load_exists():
    """The pages link to each other and load scripts, styles and images by relative path. One missing file breaks a page."""
    pages = sorted((ROOT / "ui").glob("*.html"))
    assert {p.name for p in pages} >= {"index.html", "chat.html", "login.html", "vault.html", "settings.html"}
    for page in pages:
        assert client.get(f"/{page.name}").status_code == 200, page.name
        for target in LOCAL_LINK.findall(page.read_text(encoding="utf-8")):
            assert client.get(f"/{target}").status_code == 200, f"{page.name} links to {target}"


def test_sign_in_pages_load_the_library_then_auth_then_their_own_script_and_staff_pages_do_not_load_auth():
    """auth.js needs the library, and a page script needs auth.js the moment it starts, so the order matters. The staff pages use the
    admin key: if they loaded auth.js, a wrong key (401) would send a staff member to the login page."""
    for page, own in (("chat.html", "app.js"), ("login.html", "login.js")):
        scripts = re.findall(r'<script src="([^"]+)"', (ROOT / "ui" / page).read_text(encoding="utf-8"))
        assert scripts == ["vendor/supabase.js", "common.js", "auth.js", own], page
    for page in ("vault.html", "settings.html"):
        assert "auth.js" not in (ROOT / "ui" / page).read_text(encoding="utf-8"), page


def test_start_up_warms_the_knowledge_base_in_the_background(monkeypatch):
    warmed = threading.Event()
    monkeypatch.setattr("app.main.store.warm_up", warmed.set)
    with TestClient(app) as started:  # entering the block runs the start-up steps
        assert started.get("/api/health").status_code == 200
        assert warmed.wait(timeout=5)


def test_a_warm_up_problem_is_only_a_warning(monkeypatch, caplog):
    def refuse():
        raise RuntimeError("no index yet")

    monkeypatch.setattr("app.main.store.warm_up", refuse)
    app_main.warm_up()  # must not raise
    assert "Warm-up skipped: no index yet" in caplog.text


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


def test_the_open_chat_route_is_gone_so_every_question_needs_a_sign_in():
    """/api/chat took questions from anyone and spent AI tokens on them. Chats now go through /api/conversations, which needs a sign-in."""
    assert client.post("/api/chat", json={"question": "anything"}).status_code in (404, 405)
    assert client.get("/api/chat").status_code == 404
