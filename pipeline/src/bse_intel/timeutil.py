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


# NSE cash-market trading holidays (NSE /api/holiday-master?type=trading, measured 2026-10-22: 20 days for 2026). The
# list for a new year is published in December; a year not listed here counts weekdays as trading days, as before. The
# web keeps the same list (web/src/lib/format.ts NSE_HOLIDAYS). Diwali Laxmi Pujan has a one-hour Muhurat session only.
NSE_HOLIDAYS = frozenset({
    "2026-01-15", "2026-01-26", "2026-02-15", "2026-03-03", "2026-03-21", "2026-03-26", "2026-03-31", "2026-04-03",
    "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26", "2026-08-15", "2026-09-14", "2026-10-02", "2026-10-20",
    "2026-11-08", "2026-11-10", "2026-11-24", "2026-12-25",
})


def market_session(filed_at: str) -> str:
    """LIVE_MARKET (09:15-15:30 IST on a trading day), PRE_MARKET, AFTER_MARKET or NON_TRADING (a weekend or an NSE
    trading holiday: data chain audit B4, 22 Oct 2026)."""
    dt = datetime.fromisoformat(filed_at).astimezone(IST)
    if dt.weekday() >= 5 or dt.date().isoformat() in NSE_HOLIDAYS:
        return "NON_TRADING"
    minutes = dt.hour * 60 + dt.minute
    if minutes < 9 * 60 + 15:
        return "PRE_MARKET"
    return "LIVE_MARKET" if minutes <= 15 * 60 + 30 else "AFTER_MARKET"


def iso_ist(dt: datetime) -> str:
    return dt.astimezone(IST).isoformat(timespec="seconds")


def daterange(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)
