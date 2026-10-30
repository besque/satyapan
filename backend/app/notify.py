"""Messages to institutions and offices. Each message is stored once (its key) with the channels it went by."""
from __future__ import annotations

from datetime import date

from . import clock, db, settings


def send(key: str, on: date, to_office: str, kind: str, text: str, level: int = 0, app_id: str | None = None,
         item_id: str | None = None, pid: str | None = None) -> bool:
    audience = "institution" if to_office.startswith("INST:") else "aicte"
    channels = settings.get()["alerts"]["channels"].get(audience, ["portal"])
    return bool(db.insert("alerts", {"key": key, "on_date": clock.iso(on), "to_office": to_office, "audience": audience,
                                     "channels": channels, "kind": kind, "level": level, "app_id": app_id, "item_id": item_id,
                                     "pid": pid, "text": text}, ignore=True))
