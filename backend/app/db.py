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

-- Institution master (in production: the AICTE institution records, keyed by Permanent ID).
CREATE TABLE IF NOT EXISTS institutions (
    permanent_id TEXT PRIMARY KEY,
    name TEXT, aliases TEXT, city TEXT, district TEXT, state TEXT, region TEXT,
    inst_type TEXT, society TEXT, est_year INTEGER
);

CREATE TABLE IF NOT EXISTS officers (
    id TEXT PRIMARY KEY, name TEXT, bureau TEXT, rank TEXT, region TEXT
);

-- One complaint / case as held by the bureau that is handling it.
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY, bureau TEXT, ext_ref TEXT, source TEXT,
    received_on TEXT, complainant TEXT, complainant_type TEXT, contact_hash TEXT,
    inst_text TEXT, permanent_id TEXT, match TEXT, match_state TEXT,
    category TEXT, category_ai TEXT, subject TEXT, description TEXT, lang TEXT,
    status TEXT, officer_id TEXT, last_action TEXT, last_action_on TEXT,
    next_action TEXT, next_due TEXT, due_on TEXT, disposed_on TEXT, outcome TEXT,
    esc_level INTEGER DEFAULT -1, created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_cases_inst ON cases(permanent_id);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, ts TEXT, kind TEXT,
    bureau TEXT, actor TEXT, remarks TEXT, to_bureau TEXT, extra TEXT
);
CREATE INDEX IF NOT EXISTS ix_actions_case ON actions(case_id);

-- Officer decisions about whether two cases are the same matter.
CREATE TABLE IF NOT EXISTS links (
    a TEXT, b TEXT, kind TEXT, actor TEXT, reason TEXT, ts TEXT, PRIMARY KEY (a, b)
);

-- Overlap alerts raised by the system and how the bureaus responded.
CREATE TABLE IF NOT EXISTS coordination (
    id TEXT PRIMARY KEY, permanent_id TEXT, kind TEXT, rule TEXT, title TEXT, why TEXT,
    cases TEXT, reasons TEXT, lead TEXT, status TEXT, acks TEXT,
    created_at TEXT, updated_at TEXT, closed_note TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE, to_bureau TEXT, to_role TEXT,
    kind TEXT, case_id TEXT, coord_id TEXT, text TEXT, created_at TEXT, read_by TEXT DEFAULT '[]'
);

-- Language-model vectors for case text, cached so each text is read once.
CREATE TABLE IF NOT EXISTS vectors (
    case_id TEXT PRIMARY KEY, sha TEXT, vec BLOB
);

CREATE TABLE IF NOT EXISTS settings_override (
    key TEXT PRIMARY KEY, value TEXT, updated_by TEXT, updated_at TEXT
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


def unj(v: str | None, default: Any = None) -> Any:
    if v is None or v == "":
        return default
    return json.loads(v)


def insert(table: str, row: dict[str, Any], replace: bool = False) -> None:
    cols = ",".join(row)
    qs = ",".join("?" for _ in row)
    verb = "INSERT OR REPLACE" if replace else "INSERT"
    vals = [j(v) if isinstance(v, (dict, list)) else v for v in row.values()]
    with tx() as c:
        c.execute(f"{verb} INTO {table} ({cols}) VALUES ({qs})", vals)


def update(table: str, key: str, key_val: Any, fields: dict[str, Any]) -> None:
    sets = ",".join(f"{k}=?" for k in fields)
    vals = [j(v) if isinstance(v, (dict, list)) else v for v in fields.values()]
    with tx() as c:
        c.execute(f"UPDATE {table} SET {sets} WHERE {key}=?", [*vals, key_val])
