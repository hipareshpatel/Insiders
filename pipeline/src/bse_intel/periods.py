"""Indian fiscal-period arithmetic (FY runs April to March)."""

from __future__ import annotations

import calendar
import re
from datetime import date

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}


def _fy_end_year(token: str) -> int:
    year = int(token)
    return year + 2000 if year < 100 else year


def due_date(text: str | None) -> date | None:
    """Last day of the period a guidance deadline refers to, if parseable.

    "FY27" -> 2027-03-31, "Q3FY27" -> 2026-12-31, "H1 FY27" -> 2026-09-30,
    "Dec-2026" / "December 2026" -> 2026-12-31, "2026-11-15" -> itself,
    "CY2026" / "2026" -> 2026-12-31.
    """
    if not text:
        return None
    s = text.strip().upper().replace("’", "'")
    if m := re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", s):
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    if m := re.search(r"\bQ([1-4])\s*FY\s*'?(\d{2,4})\b", s):
        end_year = _fy_end_year(m[2])
        q = int(m[1])
        month, year = ((6, end_year - 1), (9, end_year - 1), (12, end_year - 1), (3, end_year))[q - 1]
        return date(year, month, calendar.monthrange(year, month)[1])
    if m := re.search(r"\b9M\s*FY\s*'?(\d{2,4})\b", s):
        return date(_fy_end_year(m[1]) - 1, 12, 31)
    if m := re.search(r"\bH([12])\s*FY\s*'?(\d{2,4})\b", s):
        end_year = _fy_end_year(m[2])
        return date(end_year - 1, 9, 30) if m[1] == "1" else date(end_year, 3, 31)
    if m := re.search(r"\bFY\s*'?(\d{2})(?:\s*[-/]\s*(\d{2}))?\b", s):
        end = _fy_end_year(m[2] or m[1]) if m[2] else _fy_end_year(m[1])
        return date(end, 3, 31)
    if m := re.search(r"\bFY\s*(20\d{2})\b", s):
        return date(int(m[1]), 3, 31)
    if m := re.search(r"\b([A-Z]{3})[A-Z]*[\s,'-]*(20\d{2})\b", s):
        month = _MONTHS.get(m[1].lower())
        if month:
            year = int(m[2])
            return date(year, month, calendar.monthrange(year, month)[1])
    if m := re.search(r"\b(?:CY\s*)?(20\d{2})\b", s):
        return date(int(m[1]), 12, 31)
    return None


def prior_year_period(period: str) -> str | None:
    """Same period one year earlier: Q2FY27 -> Q2FY26, H1FY27 -> H1FY26, FY27 -> FY26, SEP-2026 -> SEP-2025."""
    s = period.upper().replace(" ", "")
    if m := re.fullmatch(r"(Q[1-4]|H[12]|9M)?FY(\d{2}|\d{4})", s):
        prefix, year = m[1] or "", int(m[2])
        width = len(m[2])
        prev = year - 1
        return f"{prefix}FY{prev:0{width}d}" if width == 2 else f"{prefix}FY{prev}"
    if m := re.fullmatch(r"([A-Z]{3})-?(20\d{2})", s):
        return f"{m[1]}-{int(m[2]) - 1}"
    return None


def prior_quarter_period(period: str) -> str | None:
    """The quarter before: Q2FY27 -> Q1FY27, Q1FY27 -> Q4FY26."""
    m = re.fullmatch(r"Q([1-4])FY(\d{2}|\d{4})", period.upper().replace(" ", ""))
    if not m:
        return None
    q, year, width = int(m[1]), int(m[2]), len(m[2])
    if q > 1:
        return f"Q{q - 1}FY{m[2]}"
    return f"Q4FY{year - 1:0{width}d}"
