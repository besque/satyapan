"""Configuration: settings.yaml plus administrator overrides kept in the database."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from functools import lru_cache

import yaml

from . import db
from .config import SETTINGS_YAML


@lru_cache(maxsize=1)
def base() -> dict:
    return yaml.safe_load(SETTINGS_YAML.read_text(encoding="utf-8"))


_cache: dict | None = None


def get() -> dict:
    """Effective settings. Overrides are dotted paths, e.g. 'stages.evc.days'."""
    global _cache
    if _cache is None:
        s = copy.deepcopy(base())
        for row in db.q("SELECT key, value FROM settings_override"):
            node = s
            parts = row["key"].split(".")
            for p in parts[:-1]:
                node = node.setdefault(p, {})
            node[parts[-1]] = db.unj(row["value"])
        _cache = s
    return _cache


def lookup(key: str):
    node = get()
    for p in key.split("."):
        if not isinstance(node, dict) or p not in node:
            raise KeyError(key)
        node = node[p]
    return node


def put(key: str, value, actor: str, reason: str = "") -> None:
    global _cache
    db.insert("settings_override", {"key": key, "value": db.j(value), "updated_by": actor,
                                    "updated_at": datetime.now(timezone.utc).isoformat(), "reason": reason}, replace=True)
    _cache = None


def overrides() -> list[dict]:
    return db.q("SELECT * FROM settings_override ORDER BY updated_at DESC")


def invalidate() -> None:
    global _cache
    _cache = None


def stage(k: str) -> dict:
    return get()["stages"][k]


def nature(k: str) -> dict:
    return get()["natures"][k]


def cite(k: str | None) -> dict | None:
    if not k:
        return None
    c = get()["cites"].get(k)
    return {"key": k, **c} if c else None
