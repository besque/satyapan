"""Tamper-evident audit trail: every entry stores the SHA-256 of the previous entry.

Editing or deleting any past row breaks the chain, which `verify_chain` reports with the
first broken sequence number.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from . import db

GENESIS = "0" * 64


def _digest(seq: int, ts: str, actor: str, role: str, action: str, target: str, payload: str, prev: str) -> str:
    material = "|".join([str(seq), ts, actor, role, action, target, payload, prev])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def log(actor: str, role: str, action: str, target: str, payload: Any = None, ts: str | None = None) -> dict:
    ts = ts or datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    body = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False, default=str)
    with db.tx() as c:
        last = c.execute("SELECT seq, hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else GENESIS
        seq = (last["seq"] + 1) if last else 1
        h = _digest(seq, ts, actor, role, action, target, body, prev)
        c.execute(
            "INSERT INTO audit (seq, ts, actor, role, action, target, payload, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?)",
            (seq, ts, actor, role, action, target, body, prev, h),
        )
    return {"seq": seq, "hash": h}


def verify_chain() -> dict:
    rows = db.q("SELECT * FROM audit ORDER BY seq")
    prev = GENESIS
    for r in rows:
        expect = _digest(r["seq"], r["ts"], r["actor"], r["role"], r["action"], r["target"], r["payload"], prev)
        if r["prev_hash"] != prev or r["hash"] != expect:
            return {"ok": False, "entries": len(rows), "broken_at": r["seq"]}
        prev = r["hash"]
    return {"ok": True, "entries": len(rows), "head": prev}
