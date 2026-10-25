"""Simulated issuing-authority registries (state fire services, SHCIL e-stamp, municipal OC,
ICAI UDIN, structural-engineer councils).

They sit behind the same connector interface a real API/portal integration would use, and
every response is marked `simulated=True` in the UI so nobody mistakes them for live sources.
Availability can be toggled per source to exercise the 'source unavailable' path.
"""
from __future__ import annotations

import json
import sqlite3
import threading

from ..config import ISSUERS_PATH

PATH = ISSUERS_PATH
_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (name TEXT PRIMARY KEY, label TEXT, available INTEGER, kind TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS records (source TEXT, key TEXT, data TEXT, PRIMARY KEY (source, key));
"""

SOURCES = {
    "fire_ts": ("Telangana State Fire & Emergency Services - NOC verification", "portal"),
    "fire_mh": ("Maharashtra Fire Services - e-NOC verification", "api"),
    "fire_tn": ("Tamil Nadu Fire and Rescue Services - NOC verification", "portal"),
    "estamp": ("SHCIL e-Stamp certificate verification", "portal"),
    "oc_ts": ("HMDA / DTCP Telangana - building permission & OC", "api"),
    "oc_mh": ("PMRDA - occupancy certificate register", "portal"),
    "oc_tn": ("DTCP Tamil Nadu - completion certificate register", "portal"),
    "udin": ("ICAI UDIN verification", "api"),
    "engineers": ("Structural engineer licence register (ULB)", "register"),
    "fire_ka": ("Karnataka State Fire & Emergency Services", "not connected"),
    "oc_ka": ("BBMP / BDA building licence records", "not connected"),
}
NOT_CONNECTED = {k for k, (_, kind) in SOURCES.items() if kind == "not connected"}


def _c():
    c = sqlite3.connect(PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    for k, (label, kind) in SOURCES.items():   # make sure every known source has a row
        c.execute("INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?)",
                  (k, label, 0 if kind == "not connected" else 1, kind, "real source, manual" if kind == "not connected" else "simulated"))
    c.commit()
    return c


def reset() -> None:
    with _lock:
        c = _c()
        c.execute("DELETE FROM records"); c.execute("DELETE FROM sources")
        for k, (label, kind) in SOURCES.items():
            c.execute("INSERT INTO sources VALUES (?,?,?,?,?)", (k, label, 0 if kind == "not connected" else 1, kind,
                                                                 "real source, manual" if kind == "not connected" else "simulated"))
        c.commit()


def put(source: str, key: str, data: dict) -> None:
    with _lock:
        c = _c()
        c.execute("INSERT OR REPLACE INTO records VALUES (?,?,?)", (source, key.upper(), json.dumps(data, default=str)))
        c.commit()


def set_available(source: str, available: bool) -> None:
    with _lock:
        c = _c()
        c.execute("UPDATE sources SET available=? WHERE name=?", (int(available), source))
        c.commit()


def sources() -> list[dict]:
    with _lock:
        return [dict(r) for r in _c().execute("SELECT * FROM sources ORDER BY name")]


def lookup(source: str, key: str) -> dict:
    """Returns {'available': bool, 'found': bool, 'record': dict|None, 'source': label}."""
    with _lock:
        c = _c()
        s = c.execute("SELECT * FROM sources WHERE name=?", (source,)).fetchone()
        if not s:
            return {"available": False, "found": False, "record": None, "source": source}
        if source in NOT_CONNECTED:
            return {"available": False, "found": False, "record": None, "source": s["label"] + " (no online verification connected)"}
        if not s["available"]:
            return {"available": False, "found": False, "record": None, "source": s["label"]}
        r = c.execute("SELECT data FROM records WHERE source=? AND key=?", (source, (key or "").upper().strip())).fetchone()
        return {"available": True, "found": bool(r), "record": json.loads(r["data"]) if r else None, "source": s["label"]}
