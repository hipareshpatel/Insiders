"""A year's figure against its quarters, and the owners' / minorities' swap (MEMORY_YEAR_CHECK, F177; TODO 64-65). A pure read:
nothing stored is changed; a figure that fails is *held*, with a reason, and the readers leave it out.

The shared helpers of the NSE self-check live here (``close``, ``SUM_METRICS``): ``nse_selfcheck`` reads them from this module,
so the report and the hold judge a year by one rule.

(A) A flow line's year-to-date figure (H1, 9M, FY) whose own quarters are all in memory, on one basis, and do not add up to it
within rounding (0.5% or 1 crore) is held. A year with a missing quarter, or quarters on two bases, cannot be checked and is
not held. Glenmark FY26, The Leela FY26 (owners 33 Cr against profit 403 Cr), BLAL FY26 (a tax sign): each file adds up by
itself, the year does not match its four quarters.

(B) A period's ``pat_owners`` under 5% of its ``pat`` while the same period a year before had ``pat_owners`` at 80% or more of
``pat`` is held, and so is that period's ``pat_minority``: the labels are swapped (Glenmark FY26: owners 0.10 Cr, minorities
1,361.85 Cr; FY25 1,047 Cr owners, 0.45 Cr minorities; Nitco FY25 the same)."""
from __future__ import annotations

import re

from .dossier import FLOW_METRICS, _entry_basis
from .periods import prior_year_period

ROUND_PCT = 0.5     # within 0.5% ...
ROUND_CR = 1.0      # ... or 1 crore
SUM_METRICS = FLOW_METRICS - {"operating_cash_flow"}   # a cash flow is not stated quarter by quarter, so the sum check skips it
SWAP_NOW = 0.05     # owners under this share of the profit ...
SWAP_BEFORE = 0.80  # ... where a year before they held at least this share
OWNERS_METRICS = ("pat_owners", "pat_minority")
# the quarters each year-to-date label adds up from
_PARTS = {"H1": (1, 2), "9M": (1, 2, 3), "FY": (1, 2, 3, 4)}
_YTD = re.compile(r"(H1|9M)?(FY\d{2})")


def close(a: float, b: float, unit: str | None = "INR_CR") -> bool:
    """Equal within rounding: 0.5% of the larger figure, or 1 crore when the figures are in crore."""
    tol = max(abs(a), abs(b)) * ROUND_PCT / 100
    if (unit or "INR_CR") == "INR_CR":
        tol = max(tol, ROUND_CR)
    return abs(a - b) <= max(tol, 1e-9)


def _num(entry: dict | None) -> float | None:
    v = (entry or {}).get("value")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _crore(entry: dict | None) -> bool:
    return _num(entry) is not None and ((entry or {}).get("unit") or "INR_CR") == "INR_CR"


def held_figures(entries: list[dict]) -> dict[tuple[str, str], str]:
    """{(metric, period): reason} for every figure of ``entries`` (financial_metrics rows) that fails (A) or (B)."""
    by = {(e.get("metric"), e.get("period")): e for e in entries if isinstance(e, dict) and e.get("metric") and e.get("period")}
    held: dict[tuple[str, str], str] = {}
    for (metric, period), whole in by.items():
        m = _YTD.fullmatch(str(period))
        if metric not in SUM_METRICS or not m or not _crore(whole):
            continue
        kind, fy = m.group(1) or "FY", m.group(2)
        parts = [by.get((metric, f"Q{i}{fy}")) for i in _PARTS[kind]]
        if any(not _crore(p) for p in parts):
            continue   # a missing quarter: it cannot be checked
        bases = {_entry_basis(x) for x in [whole, *parts]} - {None}
        if len(bases) > 1:
            continue   # a year on one basis against quarters on another is no sum
        total, year = sum(_num(p) for p in parts), _num(whole)
        if not close(total, year):
            span = f"Q1-Q{_PARTS[kind][-1]}"
            label = {"H1": "half year", "9M": "nine months", "FY": "year"}[kind]
            held[(metric, period)] = f"{label} does not match its quarters ({span} sum {total:,.2f}, {kind} {year:,.2f})"
    for (metric, period), owners in by.items():
        if metric != "pat_owners":
            continue
        before = prior_year_period(str(period))
        pat, old_pat, old_owners = by.get(("pat", period)), by.get(("pat", before)), by.get(("pat_owners", before))
        if not (_crore(owners) and _crore(pat) and _crore(old_pat) and _crore(old_owners)):
            continue
        bases = {_entry_basis(x) for x in (owners, pat)} - {None}
        old_bases = {_entry_basis(x) for x in (old_owners, old_pat)} - {None}
        if len(bases) > 1 or len(old_bases) > 1 or (bases and old_bases and bases != old_bases):
            continue
        now_p, now_o, was_p, was_o = _num(pat), _num(owners), _num(old_pat), _num(old_owners)
        if now_p and was_p and abs(now_o) < SWAP_NOW * abs(now_p) and was_o * was_p > 0 and abs(was_o) >= SWAP_BEFORE * abs(was_p):
            reason = (f"owners' / minorities' share looks swapped against {before} (owners {now_o:,.2f} of profit {now_p:,.2f}; "
                      f"{before} owners {was_o:,.2f} of profit {was_p:,.2f})")
            for name in OWNERS_METRICS:
                if (name, period) in by:
                    held[(name, period)] = reason
    return held
