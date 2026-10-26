"""The referee of the screener cross-check: where memory and screener disagree, the official filing decides. No request.

Owner rule (26 Oct 2026): compare the official figure with both ours and screener's, to find who is wrong (us, screener,
or just a naming / line-definition difference). The official text is the results filing's text kept in R2 by the pipeline
(``text/<news_id>.json.gz``, ``pipeline.text_key``, kept 6 months); nothing is downloaded here, a quarter with no text is
listed (``no_official_text``) for a later step to fetch.

A pair's two values are searched in the text at each printed unit (crore, lakh, million; figures per crore 1, 100, 10).
Ours is stored from the exchange file, so it must agree to ₹0.006 Cr; screener rounds to whole crore, so its figure may
be ₹0.51 Cr off. For a quarter the figure must be the first figure on its line (the statements print the current quarter
first, the comparatives after it), so a prior column holding the same number is not taken for the current one. A pair
where ours equals screener's figure for another quarter (``wrong_quarter``) is settled by the column the value sits under:
the dates of the nearest header line above it, read with ``periods.explicit_date`` and ``canonical_period`` (the pipeline's
own "quarter ended <date>" rule), giving ``official_says_<period>``.

Verdicts: ``ours_matches_official``, ``screener_matches_official``, ``both_match`` (two different lines), ``neither``,
``no_official_text``, ``official_says_<period>``.
"""

from __future__ import annotations

import gzip
import json
import re

from .periods import canonical_period, explicit_date

UNITS = (("crore", 1.0), ("lakh", 100.0), ("million", 10.0))   # figures per ₹ crore
OURS_TOLERANCE_CR = 0.006
THEIRS_TOLERANCE_CR = 0.51
EPS_TOLERANCE = 0.011
HEADER_LOOKBACK = 40

_NUMBER = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?")
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
_DATE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]20\d{2}\b|\b\d{1,2}(?:st|nd|rd|th)?[ -]" + _MONTH + r",?[ -]20\d{2}\b|\b"
                   + _MONTH + r" \d{1,2},? 20\d{2}\b", re.I)


def numbers_on(line: str) -> list[tuple[float, bool]]:
    """(value, is_a_figure) for each number of a line; a figure has a decimal point or at least four digits, which a
    serial number or a note reference does not."""
    out = []
    for m in _NUMBER.finditer(line):
        raw = m[0]
        digits = re.sub(r"[^\d.]", "", raw)
        try:
            value = float(digits)
        except ValueError:
            continue
        if raw.startswith("(") and raw.endswith(")") or raw.startswith("-"):
            value = -value
        out.append((value, "." in digits or len(digits.replace(".", "")) >= 4))
    return out


def text_of(body: bytes) -> str:
    """The filing's text from a ``text/<news_id>.json.gz`` file, as the audits read it."""
    from .extract import Document
    return Document.from_cache(json.loads(gzip.decompress(body))).select_text(10_000_000, [])


def column_period(lines: list[str], line_no: int, column: int) -> str | None:
    """The period a column's header names: the dates of the nearest line above with two or more, the ``column``-th one."""
    for back in range(line_no - 1, max(-1, line_no - HEADER_LOOKBACK), -1):
        dates = [explicit_date(m[0]) for m in _DATE.finditer(lines[back])]
        dates = [d for d in dates if d]
        if len(dates) >= 2:
            if column < len(dates):
                return canonical_period(f"quarter ended {dates[column]:%d.%m.%Y}")
            return None
    return None


def hits(text: str, value: float, metric: str, ours_side: bool, first_only: bool) -> list[dict]:
    """Where ``value`` (₹ crore, or EPS in ₹) is printed in the text: line, column among the line's figures, the unit."""
    found = []
    lines = text.splitlines()
    for line_no, line in enumerate(lines):
        nums = numbers_on(line)
        figures = [i for i, (_, fig) in enumerate(nums) if fig]
        for i, (n, fig) in enumerate(nums):
            for unit, per_crore in (UNITS[:1] if metric == "eps" else UNITS):
                tolerance = EPS_TOLERANCE if metric == "eps" else (OURS_TOLERANCE_CR if ours_side else THEIRS_TOLERANCE_CR)
                if abs(n / per_crore - value) > tolerance + 1e-5 * abs(value):
                    continue
                column = figures.index(i) if i in figures else None
                if first_only and column != 0:
                    continue
                found.append({"line": line_no, "column": column, "unit": unit, "text": line.strip()[:140]})
    return found


def referee(pair: dict, texts: list[str]) -> dict:
    """The verdict for one pair against the quarter's official text(s): ``{"verdict", "ours_hits", "theirs_hits",
    "snippet"}``. ``pair`` has ``memory_value``, ``screener_value``, ``metric``, ``period`` and ``class``."""
    if not texts:
        return {"verdict": "no_official_text", "ours_hits": [], "theirs_hits": [], "snippet": ""}
    metric = pair["metric"]
    first_only = bool(re.fullmatch(r"Q[1-4]FY\d{2}", pair["period"])) and pair["class"] != "wrong_quarter"
    ours = [h for t in texts for h in hits(t, pair["memory_value"], metric, True, first_only)]
    theirs = [h for t in texts for h in hits(t, pair["screener_value"], metric, False, first_only)]
    verdict = ("both_match" if ours and theirs else "ours_matches_official" if ours
               else "screener_matches_official" if theirs else "neither")
    if pair["class"] == "wrong_quarter":
        for text in texts:
            lines = text.splitlines()
            for h in hits(text, pair["memory_value"], metric, True, False):
                if h["column"] is not None and (period := column_period(lines, h["line"], h["column"])):
                    ours = [h]
                    verdict = f"official_says_{period}"
                    break
            if verdict.startswith("official_says_"):
                break
    shown = [f"ours: {h['text']}" for h in ours[:2]] + [f"screener: {h['text']}" for h in theirs[:2]]
    return {"verdict": verdict, "ours_hits": ours, "theirs_hits": theirs, "snippet": " | ".join(shown)[:300]}
