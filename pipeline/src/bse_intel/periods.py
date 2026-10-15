"""Indian fiscal-period arithmetic (FY runs April to March)."""

from __future__ import annotations

import calendar
import re
from datetime import date

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}


def _fy_end_year(token: str) -> int:
    year = int(token)
    return year + 2000 if year < 100 else year


_MON = r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?"
_QUARTER_END = {6: 1, 9: 2, 12: 3, 3: 4}


def _fy_from_span(text: str) -> int | None:
    """End year of a fiscal year written "FY27", "FY 2027", "FY2026-27", "FY 26-27", "2026-27"."""
    if m := re.search(r"(20\d{2})\s*[-/–]\s*(\d{2,4})\b", text):
        return _fy_end_year(m[2]) if len(m[2]) == 4 else int(m[1][:2] + m[2])
    if m := re.search(r"(\d{2})\s*[-/–]\s*(\d{2})\b", text):
        return _fy_end_year(m[2])
    if m := re.search(r"(20\d{2}|\d{2})\b", text):
        return _fy_end_year(m[1])
    return None


def explicit_date(text: str | None) -> date | None:
    """A calendar date written out: 2026-11-15, 15-11-2026, 15.11.2026, 15 November 2026, November 15, 2026."""
    if not text:
        return None
    s = text.strip().upper()
    try:
        if m := re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", s):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b", s):  # Indian day-month-year
            return date(int(m[3]), int(m[2]), int(m[1]))
        if m := re.search(r"\b(\d{1,2})(?:ST|ND|RD|TH)?\s+" + _MON + r",?\s+(20\d{2})\b", s):
            return date(int(m[3]), _MONTHS[m[2].lower()], int(m[1]))
        if m := re.search(_MON + r"\s+(\d{1,2})(?:ST|ND|RD|TH)?,?\s+(20\d{2})\b", s):
            return date(int(m[3]), _MONTHS[m[1].lower()], int(m[2]))
    except ValueError:
        return None
    return None


def canonical_period(text: str) -> str:
    """One spelling per period, so the same quarter is one dossier row whatever the filing wrote:
    "Q2 FY 2026-27", "Q2-FY27", "Q2FY2027", "quarter ended 30.09.2026" -> "Q2FY27";
    "FY2026-27" -> "FY27"; "H1 FY27" -> "H1FY27"; "September 2026", "Sep-26" -> "SEP-2026".
    Anything else is returned upper-cased without spaces."""
    s = text.strip().upper().replace("’", "'")
    compact = re.sub(r"\s+", "", s)
    if m := re.search(r"\b(Q[1-4]|H[12]|9M)\s*[-–]?\s*FY\s*'?([\d\s/–-]{2,9})", s):
        end = _fy_from_span(m[2])
        if end:
            return f"{m[1]}FY{end % 100:02d}"
    if m := re.search(r"\bFY\s*'?([\d\s/–-]{2,9})", s):
        end = _fy_from_span(m[1])
        if end:
            return f"FY{end % 100:02d}"
    if re.search(r"QUARTER|THREE MONTHS|QTR", s):
        d = explicit_date(s)
        if d and d.month in _QUARTER_END:
            q = _QUARTER_END[d.month]
            return f"Q{q}FY{(d.year + (0 if q == 4 else 1)) % 100:02d}"
    if m := re.fullmatch(_MON + r"[\s,'-]*(\d{2}|20\d{2})", s):
        year = _fy_end_year(m[2])
        return f"{m[1]}-{year}"
    return compact


_STATEMENT_QUARTER = re.compile(r"(?:QUARTER|THREE\s+MONTHS)\s+(?:AND\s+[A-Z ]{3,30}?\s+)?ENDED\s+(?:ON\s+)?(.{6,28})", re.I)
_STATEMENT_YEAR = re.compile(r"(?:\bYEAR|TWELVE\s+MONTHS)\s+ENDED\s+(?:ON\s+)?(.{6,28})", re.I)


def statement_quarter(text: str | None) -> str | None:
    """The quarter a results statement covers, from the first "quarter (and year) ended <date>" in
    its opening pages: "for the quarter and year ended 31st March, 2025" -> "Q4FY25"."""
    for m in _STATEMENT_QUARTER.finditer((text or "")[:8000]):
        d = explicit_date(m.group(1))
        if d and d.month in _QUARTER_END:
            q = _QUARTER_END[d.month]
            return f"Q{q}FY{(d.year + (0 if q == 4 else 1)) % 100:02d}"
    return None


def statement_year(text: str | None) -> str | None:
    """The fiscal year a statement closes, when it says "year ended 31 March <yyyy>": "FY25"."""
    for m in _STATEMENT_YEAR.finditer((text or "")[:8000]):
        d = explicit_date(m.group(1))
        if d and d.month == 3:
            return f"FY{d.year % 100:02d}"
    return None


def quarter_index(period: str) -> int | None:
    """Q1FY26 -> 26 * 4 + 1, so quarters can be shifted by arithmetic."""
    m = re.fullmatch(r"Q([1-4])FY(\d{2})", period)
    return int(m[2]) * 4 + int(m[1]) if m else None


def quarter_from_index(index: int) -> str:
    year, q = divmod(index - 1, 4)
    return f"Q{q + 1}FY{year % 100:02d}"


def due_date(text: str | None) -> date | None:
    """Last day of the period a deadline or figure refers to, if parseable.

    "FY27" / "FY2026-27" -> 2027-03-31, "Q3FY27" / "Q3 FY 2026-27" -> 2026-12-31, "H1 FY27" ->
    2026-09-30, "Dec-2026" / "December 2026" -> 2026-12-31, "2026-11-15" / "15-11-2026" /
    "November 15, 2026" -> that day, "CY2026" / "2026" -> 2026-12-31.
    """
    if not text:
        return None
    exact = explicit_date(text)
    if exact:
        return exact
    s = canonical_period(text)
    if m := re.fullmatch(r"Q([1-4])FY(\d{2})", s):
        end_year = _fy_end_year(m[2])
        month, year = ((6, end_year - 1), (9, end_year - 1), (12, end_year - 1), (3, end_year))[int(m[1]) - 1]
        return date(year, month, calendar.monthrange(year, month)[1])
    if m := re.fullmatch(r"9MFY(\d{2})", s):
        return date(_fy_end_year(m[1]) - 1, 12, 31)
    if m := re.fullmatch(r"H([12])FY(\d{2})", s):
        end_year = _fy_end_year(m[2])
        return date(end_year - 1, 9, 30) if m[1] == "1" else date(end_year, 3, 31)
    if m := re.fullmatch(r"FY(\d{2})", s):
        return date(_fy_end_year(m[1]), 3, 31)
    if m := re.fullmatch(r"([A-Z]{3})-(20\d{2})", s):
        month = _MONTHS.get(m[1].lower())
        if month:
            year = int(m[2])
            return date(year, month, calendar.monthrange(year, month)[1])
    upper = text.upper()
    if m := re.search(r"\b" + _MON + r"[\s,'-]*(20\d{2})\b", upper):
        month, year = _MONTHS[m[1].lower()], int(m[2])
        return date(year, month, calendar.monthrange(year, month)[1])
    if m := re.search(r"\b(?:CY\s*)?(20\d{2})\b", upper):
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
