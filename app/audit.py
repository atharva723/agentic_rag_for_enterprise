"""Saves every question and its decision path to a small SQLite file (basic audit trail).

user_id and conversation_id say who asked and in which saved chat. They are empty on rows written before accounts existed (when anyone could
ask through the old /api/chat). A file made before they existed is upgraded in place, so it keeps its rows.
"""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from app.config import get_settings

SCHEMA = """CREATE TABLE IF NOT EXISTS query_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    question TEXT NOT NULL,
    source_used TEXT NOT NULL,
    trace_json TEXT NOT NULL,
    user_id TEXT,
    conversation_id TEXT
)"""
ADDED_LATER = ("user_id", "conversation_id")  # not in the first version of the file


def _connect() -> sqlite3.Connection:
    path = get_settings().audit_db
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute(SCHEMA)
    have = {row["name"] for row in con.execute("PRAGMA table_info(query_audit)")}
    for name in ADDED_LATER:
        if name not in have:
            try:
                with con:
                    con.execute(f"ALTER TABLE query_audit ADD COLUMN {name} TEXT")
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc):  # another request added it a moment ago
                    raise
    return con


def write_audit(question: str, source_used: str, trace: list[str], user_id: str | None = None, conversation_id: str | None = None) -> None:
    with closing(_connect()) as con, con:
        con.execute(
            "INSERT INTO query_audit (created_at, question, source_used, trace_json, user_id, conversation_id) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), question, source_used, json.dumps(trace), user_id, conversation_id),
        )


def recent(limit: int = 50) -> list[dict]:
    with closing(_connect()) as con:
        rows = con.execute("SELECT * FROM query_audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        row = dict(r)
        row["trace"] = json.loads(row.pop("trace_json"))
        out.append(row)
    return out
