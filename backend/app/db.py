"""SQLite storage. Plain sqlite3 + JSON columns keeps deployment dependency-free."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from .config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

-- Institution master (in production: AICTE institution records, keyed by Permanent ID).
CREATE TABLE IF NOT EXISTS institutions (
    pid TEXT PRIMARY KEY, name TEXT, city TEXT, state TEXT, region TEXT, inst_type TEXT, trust TEXT,
    est_year INTEGER, ownership TEXT, land TEXT, lease_until TEXT, building_year INTEGER,
    programmes TEXT, source TEXT, source_url TEXT, extra TEXT
);

-- Approval letters on record (previous cycles). Real ones come from public copies posted by institutions.
CREATE TABLE IF NOT EXISTS letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT, pid TEXT, ay TEXT, kind TEXT, application_no TEXT,
    issued_on TEXT, printed_on TEXT, deficiencies TEXT, courses TEXT, source TEXT, source_url TEXT, sha256 TEXT
);
CREATE INDEX IF NOT EXISTS ix_letters_pid ON letters(pid);

-- One application of the cycle. `stage`/`phase`/`holder` describe the step it is waiting on.
CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY, pid TEXT, ay TEXT, nature TEXT, submitted_on TEXT, region TEXT,
    status TEXT, stage TEXT, phase TEXT, holder TEXT, step_id INTEGER, officer TEXT,
    decided_on TEXT, decision TEXT, deficiencies TEXT, carried TEXT, detail TEXT,
    risk TEXT, spare INTEGER, esc_level INTEGER DEFAULT -1, source TEXT
);
CREATE INDEX IF NOT EXISTS ix_apps_pid ON applications(pid);

-- Every stage the application has been through (scrutiny, compliance, EVC, ...), including repeats.
CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT, app_id TEXT, stage TEXT, attempt INTEGER,
    opened_on TEXT, closed_on TEXT, phase TEXT, holder TEXT, due_on TEXT,
    meeting_on TEXT, mode TEXT, members TEXT, outcome TEXT, deficiencies TEXT, remarks TEXT,
    actor TEXT, esc_level INTEGER DEFAULT -1, extra TEXT
);
CREATE INDEX IF NOT EXISTS ix_steps_app ON steps(app_id);

-- Who held the ball, from when to when (application or compliance item).
CREATE TABLE IF NOT EXISTS holds (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT, holder TEXT, from_on TEXT, to_on TEXT
);
CREATE INDEX IF NOT EXISTS ix_holds_ref ON holds(ref);

-- Readable history of applications and compliance items (the audit table is the tamper-evident copy).
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, app_id TEXT, item_id TEXT, on_date TEXT, ts TEXT,
    kind TEXT, actor TEXT, text TEXT, extra TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_app ON events(app_id);
CREATE INDEX IF NOT EXISTS ix_events_item ON events(item_id);

-- Compliance items: undertakings, document renewals, security deposits, lease extensions.
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY, kind TEXT, pid TEXT, app_id TEXT, title TEXT, detail TEXT,
    doc_type TEXT, cond TEXT, cite TEXT, consequence TEXT,
    opened_on TEXT, due_on TEXT, status TEXT, holder TEXT, verify_by TEXT,
    submitted_on TEXT, closed_on TEXT, closed_by TEXT, evidence TEXT, note TEXT,
    esc_level INTEGER DEFAULT -1, source TEXT, source_url TEXT, extra TEXT
);
CREATE INDEX IF NOT EXISTS ix_items_pid ON items(pid);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, pid TEXT, doc_type TEXT, number TEXT, issuer TEXT, issued_on TEXT,
    valid_until TEXT, status TEXT, file_id TEXT, note TEXT, source TEXT, source_url TEXT
);
CREATE INDEX IF NOT EXISTS ix_docs_pid ON documents(pid);

-- Reminders, escalations and notices, exactly as sent (one row per message).
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE, on_date TEXT, to_office TEXT, audience TEXT,
    channels TEXT, kind TEXT, level INTEGER, app_id TEXT, item_id TEXT, pid TEXT, text TEXT,
    read_by TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS ix_alerts_office ON alerts(to_office);

CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY, name TEXT, mime TEXT, path TEXT, sha256 TEXT, size INTEGER, uploaded_by TEXT, uploaded_on TEXT
);

CREATE TABLE IF NOT EXISTS settings_override (
    key TEXT PRIMARY KEY, value TEXT, updated_by TEXT, updated_at TEXT, reason TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, role TEXT,
    action TEXT, target TEXT, payload TEXT, prev_hash TEXT, hash TEXT
);
"""

_lock = threading.RLock()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


_conn: sqlite3.Connection | None = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = connect()
        _conn.executescript(SCHEMA)
    return _conn


def reset() -> None:
    """Drop everything (used by the demo seeder)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
        for suffix in ("", "-wal", "-shm"):
            p = DB_PATH.with_name(DB_PATH.name + suffix)
            if p.exists():
                p.unlink()


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    with _lock:
        c = conn()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


def q(sql: str, args: tuple | list = ()) -> list[dict[str, Any]]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


def q1(sql: str, args: tuple | list = ()) -> dict[str, Any] | None:
    rows = q(sql, args)
    return rows[0] if rows else None


def j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def unj(v: Any, default: Any = None) -> Any:
    if v is None or v == "":
        return default
    if not isinstance(v, (str, bytes)):
        return v        # already decoded
    return json.loads(v)


def insert(table: str, row: dict[str, Any], replace: bool = False, ignore: bool = False) -> int:
    cols = ",".join(row)
    qs = ",".join("?" for _ in row)
    verb = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE" if ignore else "INSERT"
    vals = [j(v) if isinstance(v, (dict, list)) else v for v in row.values()]
    with tx() as c:
        cur = c.execute(f"{verb} INTO {table} ({cols}) VALUES ({qs})", vals)
        return cur.lastrowid if cur.rowcount else 0


def update(table: str, key: str, key_val: Any, fields: dict[str, Any]) -> None:
    if not fields:
        return
    sets = ",".join(f"{k}=?" for k in fields)
    vals = [j(v) if isinstance(v, (dict, list)) else v for v in fields.values()]
    with tx() as c:
        c.execute(f"UPDATE {table} SET {sets} WHERE {key}=?", [*vals, key_val])
