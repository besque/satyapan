"""Configuration: settings.yaml plus administrator overrides kept in the database."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from functools import lru_cache

import yaml

from . import db
from .config import SETTINGS_YAML


@lru_cache(maxsize=1)
def _base() -> dict:
    return yaml.safe_load(SETTINGS_YAML.read_text(encoding="utf-8"))


_cache: dict | None = None


def get() -> dict:
    """Effective settings. Overrides are dotted paths, e.g. 'categories.fee_refund.days'."""
    global _cache
    if _cache is None:
        s = copy.deepcopy(_base())
        for row in db.q("SELECT key, value FROM settings_override"):
            node = s
            parts = row["key"].split(".")
            for p in parts[:-1]:
                node = node.setdefault(p, {})
            node[parts[-1]] = db.unj(row["value"])
        _cache = s
    return _cache


def put(key: str, value, actor: str) -> None:
    global _cache
    db.insert("settings_override", {"key": key, "value": db.j(value), "updated_by": actor,
                                    "updated_at": datetime.now(timezone.utc).isoformat()}, replace=True)
    _cache = None


def overrides() -> list[dict]:
    return db.q("SELECT * FROM settings_override ORDER BY updated_at DESC")


def clear() -> None:
    global _cache
    with db.tx() as c:
        c.execute("DELETE FROM settings_override")
    _cache = None


def category(cid: str) -> dict:
    return get()["categories"].get(cid) or {"label": cid, "bureau": "PGRC", "days": 30, "describe": []}


def bureau_name(b: str) -> str:
    return (get()["bureaus"].get(b) or {}).get("name", b)
