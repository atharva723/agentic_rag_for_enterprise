import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from app import audit
from app import main as app_main
from app.config import get_settings

USER = "11111111-1111-4111-8111-111111111111"
CHAT = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def audit_file(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "audit_db", tmp_path / "audit.db")
    monkeypatch.setattr(get_settings(), "audit_retention_days", 90)  # the default, written out so the tests below read clearly
    return tmp_path / "audit.db"


def days_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def add_row(audit_file, question, days_old):
    """A row written straight into the file with a chosen age, as if it had been saved that many days ago."""
    audit.recent()  # makes the file and its columns when they are not there yet
    with closing(sqlite3.connect(audit_file)) as con, con:
        con.execute("INSERT INTO query_audit (created_at, question, source_used, trace_json) VALUES (?, ?, 'direct', '[]')", (days_ago(days_old), question))


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
    old.execute(
        "INSERT INTO query_audit (created_at, question, source_used, trace_json) VALUES (?, 'an old question', 'direct', '[]')",
        (days_ago(1),),  # old for the file format, but still inside the retention period
    )
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


# ---- retention --------------------------------------------------------------------------------------------------------------


def test_saving_a_question_deletes_the_rows_older_than_the_retention_period(audit_file):
    add_row(audit_file, "91 days ago", 91)
    add_row(audit_file, "89 days ago", 89)
    audit.write_audit("today", "direct", [])
    assert [row["question"] for row in audit.recent()] == ["today", "89 days ago"]


def test_the_retention_period_is_a_setting(audit_file, monkeypatch):
    monkeypatch.setattr(get_settings(), "audit_retention_days", 30)
    add_row(audit_file, "40 days ago", 40)
    add_row(audit_file, "20 days ago", 20)
    audit.write_audit("today", "direct", [])
    assert [row["question"] for row in audit.recent()] == ["today", "20 days ago"]


def test_a_retention_of_zero_keeps_everything(audit_file, monkeypatch):
    monkeypatch.setattr(get_settings(), "audit_retention_days", 0)
    add_row(audit_file, "ages ago", 3000)
    audit.write_audit("today", "direct", [])
    assert audit.prune() == 0
    assert [row["question"] for row in audit.recent()] == ["today", "ages ago"]


def test_prune_deletes_the_old_rows_and_says_how_many(audit_file):
    for days in (200, 100, 91, 10, 0):
        add_row(audit_file, f"{days} days ago", days)
    assert audit.prune() == 3
    assert audit.prune() == 0  # nothing left to delete
    assert sorted(row["question"] for row in audit.recent()) == ["0 days ago", "10 days ago"]


def test_prune_does_not_make_a_file_that_is_not_there(audit_file):
    assert audit.prune() == 0
    assert not audit_file.exists()  # the file appears when the first question is saved, not before


def test_start_up_trims_the_audit_log(audit_file):
    add_row(audit_file, "a year ago", 365)
    add_row(audit_file, "yesterday", 1)
    app_main.trim_audit()
    assert [row["question"] for row in audit.recent()] == ["yesterday"]


def test_a_clean_up_problem_at_start_up_is_only_a_warning(monkeypatch, caplog):
    def broken():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(audit, "prune", broken)
    app_main.trim_audit()  # must not raise
    assert "Audit clean-up skipped: database is locked" in caplog.text
