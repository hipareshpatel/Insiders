from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


def now_iso() -> str:
    return now_ist().isoformat(timespec="seconds")


def today_ist() -> date:
    return now_ist().date()


def utc_day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def parse_bse_datetime(value: str | None) -> datetime | None:
    """BSE sends naive IST timestamps like '2026-10-13T17:42:10.153'."""
    if not value:
        return None
    text = value.strip().replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%d/%m/%YT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=IST)


def iso_ist(dt: datetime) -> str:
    return dt.astimezone(IST).isoformat(timespec="seconds")


def daterange(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)
