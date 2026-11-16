"""Saves every question and its decision path to a small SQLite file (basic audit trail)."""
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
    trace_json TEXT NOT NULL
)"""


def _connect() -> sqlite3.Connection:
    path = get_settings().audit_db
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute(SCHEMA)
    return con


def write_audit(question: str, source_used: str, trace: list[str]) -> None:
    with closing(_connect()) as con, con:
        con.execute(
            "INSERT INTO query_audit (created_at, question, source_used, trace_json) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), question, source_used, json.dumps(trace)),
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
