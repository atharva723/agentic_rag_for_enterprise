import sqlite3

import pytest

from app import audit
from app.config import get_settings

USER = "11111111-1111-4111-8111-111111111111"
CHAT = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def audit_file(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "audit_db", tmp_path / "audit.db")
    return tmp_path / "audit.db"


def test_a_question_asked_with_an_account_records_who_asked_and_in_which_chat(audit_file):
    audit.write_audit("How do I reset my password?", "private_kb", ["Router → KB"], user_id=USER, conversation_id=CHAT)
    (row,) = audit.recent()
    assert (row["user_id"], row["conversation_id"], row["trace"]) == (USER, CHAT, ["Router → KB"])


def test_a_question_asked_without_an_account_leaves_both_empty(audit_file):
    audit.write_audit("Hello!", "direct", ["Router → DIRECT"])
    (row,) = audit.recent()
    assert row["user_id"] is None and row["conversation_id"] is None


def test_an_audit_file_from_before_accounts_is_upgraded_in_place_and_keeps_its_rows(audit_file):
    old = sqlite3.connect(audit_file)
    old.execute(
        "CREATE TABLE query_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, question TEXT NOT NULL,"
        " source_used TEXT NOT NULL, trace_json TEXT NOT NULL)"
    )
    old.execute("INSERT INTO query_audit (created_at, question, source_used, trace_json) VALUES ('2026-01-01T00:00:00+00:00', 'an old question', 'direct', '[]')")
    old.commit()
    old.close()
    audit.write_audit("a new question", "direct", [], user_id=USER, conversation_id=CHAT)
    new, kept = audit.recent()  # newest first
    assert (new["question"], new["user_id"], new["conversation_id"]) == ("a new question", USER, CHAT)
    assert (kept["question"], kept["user_id"], kept["conversation_id"]) == ("an old question", None, None)


def test_opening_an_upgraded_file_again_is_harmless(audit_file):
    audit.write_audit("one", "direct", [])
    audit.write_audit("two", "direct", [], user_id=USER)
    assert [row["question"] for row in audit.recent()] == ["two", "one"]
