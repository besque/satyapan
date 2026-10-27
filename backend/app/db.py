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

-- Institutional records "already available in authorised AICTE systems".
-- Bootstrapped from real, publicly posted EoA letters (source='public_eoa') plus synthetic test institutions.
CREATE TABLE IF NOT EXISTS institutions (
    permanent_id TEXT PRIMARY KEY,
    name TEXT, trust TEXT, address TEXT, state TEXT, region TEXT, inst_type TEXT,
    est_year INTEGER, lat REAL, lon REAL, source TEXT, extra TEXT
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permanent_id TEXT, academic_year TEXT, application_id TEXT, fno TEXT,
    date_of_approval TEXT, letter_printed TEXT, letter_kind TEXT,
    source_sha TEXT, source_url TEXT, source_pages TEXT, deficiencies TEXT,
    UNIQUE(permanent_id, academic_year, application_id)
);
CREATE TABLE IF NOT EXISTS approval_courses (
    approval_id INTEGER, level TEXT, program TEXT, course TEXT, shift TEXT,
    affiliating_body TEXT, intake_prev INTEGER, intake_curr INTEGER, nri TEXT, fn TEXT, is_new INTEGER
);

CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY, permanent_id TEXT, category TEXT, academic_year TEXT,
    form TEXT, status TEXT, lane TEXT, risk REAL, summary TEXT,
    created_at TEXT, processed_at TEXT, source TEXT
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, application_id TEXT, declared_type TEXT, doc_type TEXT,
    filename TEXT, sha256 TEXT, mime TEXT, pages INTEGER, page_sizes TEXT,
    classification TEXT, extraction TEXT, forensics TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY, application_id TEXT, document_id TEXT, rule_id TEXT,
    kind TEXT, severity TEXT, status TEXT, title TEXT, detail TEXT,
    evidence TEXT, citation TEXT, remedy TEXT, confidence REAL, created_at TEXT
);
CREATE TABLE IF NOT EXISTS verifications (
    id TEXT PRIMARY KEY, application_id TEXT, document_id TEXT, connector TEXT,
    status TEXT, source TEXT, simulated INTEGER, request TEXT, response TEXT,
    detail TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS entities (
    entity_type TEXT, key TEXT, display TEXT, permanent_id TEXT, application_id TEXT,
    document_id TEXT, page INTEGER, bbox TEXT, extra TEXT
);
CREATE INDEX IF NOT EXISTS ix_entities_key ON entities(entity_type, key);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT, finding_id TEXT, application_id TEXT,
    actor TEXT, role TEXT, decision TEXT, reason TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, role TEXT,
    action TEXT, target TEXT, payload TEXT, prev_hash TEXT, hash TEXT
);
CREATE TABLE IF NOT EXISTS rule_overrides (
    rule_id TEXT PRIMARY KEY, enabled INTEGER, params TEXT, updated_by TEXT, updated_at TEXT
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
