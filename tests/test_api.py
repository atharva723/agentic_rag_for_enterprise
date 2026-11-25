import asyncio
import re
import threading
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app.api.streaming import stream
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


def test_no_page_loads_two_scripts_that_declare_the_same_name():
    """The scripts of one page share one global space. A second `function send` silently replaces the first (vault.js had one), so a helper
    added to common.js could break a page that still looked fine."""
    top_level = re.compile(r"^(?:async\s+)?function\*?\s+(\w+)|^(?:const|let|var|class)\s+(\w+)", re.MULTILINE)
    for page in sorted((ROOT / "ui").glob("*.html")):
        declared = {}
        for src in re.findall(r'<script src="([^"]+)"', page.read_text(encoding="utf-8")):
            if src.startswith("vendor/"):
                continue
            for fn, var in top_level.findall((ROOT / "ui" / src).read_text(encoding="utf-8")):
                declared.setdefault(fn or var, []).append(src)
        assert not {name: files for name, files in declared.items() if len(files) > 1}, page.name


def policy_of(response):
    """The Content-Security-Policy as {directive: value}."""
    parts = (part.strip().partition(" ") for part in response.headers["content-security-policy"].split(";"))
    return {name: value for name, _, value in parts}


def test_every_page_file_carries_the_security_headers_and_a_strict_content_security_policy():
    for path in ("/", "/chat.html", "/login.html", "/app.js", "/style.css"):
        res = client.get(path)
        policy = policy_of(res)
        assert policy["default-src"] == "'self'" and policy["script-src"] == "'self'", path  # no inline script, no eval, no other site
        assert policy["frame-ancestors"] == "'none'" and policy["object-src"] == "'none'" and policy["base-uri"] == "'self'", path
        assert "'unsafe-inline'" not in policy["script-src"] and "'unsafe-eval'" not in res.headers["content-security-policy"], path
        assert res.headers["x-content-type-options"] == "nosniff" and res.headers["x-frame-options"] == "DENY", path
        assert res.headers["referrer-policy"] == "no-referrer" and "camera=()" in res.headers["permissions-policy"], path


def test_the_policy_lets_the_sign_in_talk_to_the_supabase_project_and_nothing_else(monkeypatch):
    settings = get_settings()
    for configured, expected in (
        ("https://abc.supabase.co/", "'self' https://abc.supabase.co"),
        ("http://127.0.0.1:54321", "'self' http://127.0.0.1:54321"),
        ("", "'self'"),  # accounts switched off: only our own server
        ("https://abc.supabase.co; script-src *", "'self'"),  # a damaged setting must not be able to add rules
        ("javascript:alert(1)", "'self'"),
    ):
        monkeypatch.setattr(settings, "supabase_url", configured)
        assert policy_of(client.get("/login.html"))["connect-src"] == expected, configured


def test_the_page_policy_does_not_break_the_api_docs():
    """FastAPI's /docs page loads its script from a CDN, so the page policy is only for the files in ui/."""
    assert client.get("/docs").status_code == 200 and "content-security-policy" not in client.get("/docs").headers


def test_the_pages_obey_their_own_content_security_policy():
    """The policy lets a page run only scripts from its own files and load only its own files and Google Fonts. These checks fail when a
    page or script would break under it, so a change that the browser would block is found here and not by a person."""
    allowed_hosts = {"fonts.googleapis.com", "fonts.gstatic.com"}
    for page in sorted((ROOT / "ui").glob("*.html")):
        html = page.read_text(encoding="utf-8")
        assert not re.search(r"<script(?![^>]*\ssrc=)", html), f"{page.name} has an inline script"
        assert not re.search(r"\son[a-z]+\s*=", html, re.I), f"{page.name} has an inline event handler"
        assert "<style" not in html and "javascript:" not in html, f"{page.name} has a <style> block or a javascript: link"
        for url in re.findall(r'<(?:link|script|img)\b[^>]*\b(?:src|href)="(https?://[^"]+)"', html):
            assert urlsplit(url).netloc in allowed_hosts, f"{page.name} loads {url}, which the policy does not allow"
    for script in sorted((ROOT / "ui").glob("*.js")):  # our own scripts. The library in vendor/ is not ours
        found = re.search(r"\.(?:inner|outer)HTML\b|insertAdjacentHTML|document\.write|\beval\(|new Function\(", script.read_text(encoding="utf-8"))
        assert not found, f"{script.name} uses {found.group()}: text from answers and the web must only go in with textContent"


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


def test_start_up_trims_the_audit_log_before_the_first_request(monkeypatch):
    trimmed = []
    monkeypatch.setattr("app.main.audit.prune", lambda: trimmed.append(True) or 0)
    monkeypatch.setattr("app.main.store.warm_up", lambda: None)
    with TestClient(app):  # entering the block runs the start-up steps
        assert trimmed == [True]


def test_shutting_down_waits_for_an_answer_that_is_still_being_made(monkeypatch):
    """A page that closes does not stop its answer, but the process ends right after the shut-down step. So that step has to wait for the
    answer to finish and save, or a restart loses it."""
    monkeypatch.setattr("app.main.store.warm_up", lambda: None)
    monkeypatch.setattr("app.main.audit.prune", lambda: 0)
    release, saved = threading.Event(), []

    def job(emit):
        assert release.wait(5)
        saved.append("the answer was saved")
        return {}

    async def an_answer_whose_page_has_gone():
        stream(job)

    with TestClient(app):  # leaving the block runs the shut-down steps
        asyncio.run(an_answer_whose_page_has_gone())
        threading.Timer(0.3, release.set).start()
    assert saved == ["the answer was saved"]


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
