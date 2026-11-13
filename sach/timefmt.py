"""Times shown to people are in IST (UTC+05:30). Machine-readable data (JSON, ledger, store, snapshots, sitemap) stays ISO 8601 UTC.

India has no daylight saving, so a fixed offset is exact and needs no tzdata on the server.
Date-only inputs (a fact-checker's review date, a PIB release date) stay date-only: we never invent a time or shift a date."""
from __future__ import annotations
import re
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _parse(value):
    """-> (datetime|None, date_only: bool). Naive values are taken as UTC. Never raises."""
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, date):
            return datetime(value.year, value.month, value.day), True
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            dt = datetime.fromtimestamp(float(value), timezone.utc)
        else:
            s = str(value or "").strip()
            if not s:
                return None, False
            if _DATE_ONLY.match(s):
                d = date.fromisoformat(s)
                return datetime(d.year, d.month, d.day), True
            dt = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" UTC", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt, False
    except (ValueError, OverflowError, OSError, TypeError):
        return None, False


def to_ist(value):
    """datetime in IST, or None for anything unparseable."""
    dt, only = _parse(value)
    return None if dt is None else (dt if only else dt.astimezone(IST))


def _day(dt: datetime) -> str:
    return f"{dt.day} {_MONTHS[dt.month - 1]} {dt.year}"


def fmt_ist(value, time: bool = True) -> str:
    """'13 Nov 2026, 1:09 pm IST'. A date-only input gives '13 Nov 2026' (no time, no zone). Garbage gives ''."""
    dt, only = _parse(value)
    if dt is None:
        return ""
    if only or not time:
        return _day(dt if only else dt.astimezone(IST))
    dt = dt.astimezone(IST)
    h12 = dt.hour % 12 or 12
    return f"{_day(dt)}, {h12}:{dt.minute:02d} {'am' if dt.hour < 12 else 'pm'} IST"


def fmt_ist_date(value) -> str:
    """'13 Nov 2026' (a timestamp is converted to its IST calendar day)."""
    return fmt_ist(value, time=False)
