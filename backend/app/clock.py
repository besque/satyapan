"""The system's 'today'. Normally the real date; the demo pins it inside the approval cycle and can move it forward."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from . import settings

IST = timezone(timedelta(hours=5, minutes=30))


def today() -> date:
    t = settings.get()["cycle"].get("today")
    return date.fromisoformat(t) if t else datetime.now(IST).date()


def is_demo() -> bool:
    return bool(settings.get()["cycle"].get("today"))


def stamp(on: date | None = None) -> str:
    """Timestamp for a record made 'on' a business date: that date plus the current time of day."""
    on = on or today()
    t = datetime.now(IST)
    return datetime(on.year, on.month, on.day, t.hour, t.minute, t.second, t.microsecond // 1000 * 1000, tzinfo=IST).isoformat(timespec="milliseconds")


def d(s: str | date | None) -> date | None:
    if s is None or s == "":
        return None
    return s if isinstance(s, date) else date.fromisoformat(str(s)[:10])


def iso(x: date | None) -> str | None:
    return x.isoformat() if x else None


def add_months(x: date, n: int) -> date:
    m = x.month - 1 + n
    y, m = x.year + m // 12, m % 12 + 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(x.day, last))


def add_years(x: date, n: int) -> date:
    return add_months(x, 12 * n)
