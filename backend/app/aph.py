"""Where each cited clause sits in the Approval Process Handbook 2024-27 (located once by scripts/build_real_data.py)."""
from __future__ import annotations

import json
from functools import lru_cache

from . import settings
from .config import REAL


@lru_cache(maxsize=1)
def locations() -> dict:
    p = REAL / "aph_locs.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def cite(key: str) -> dict | None:
    c = settings.cite(key)
    if not c:
        return None
    return {**c, "loc": locations().get(key)}


def page_file(n: int):
    p = REAL / "aph" / f"p{n}.png"
    return p if p.exists() else None
