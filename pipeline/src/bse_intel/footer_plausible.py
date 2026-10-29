"""CARD_FOOTER_PLAUSIBLE (settings.card_footer_plausible; F182, TODO 77): a footer KPI that cannot be right is not shown.

The case: GIC Housing Finance (nse-106827848, 26 Oct 2026 audit) showed a net interest margin of 19.63% against its FY26
3.41%, a figure an AI read off the card's document and stored under a label nobody checked. Two tests, each a reason to hide
the figure from the footer strip and the results table's sector rows (nothing stored is changed; the figure stays in memory):

1. **Against the company itself.** More than 3x the highest of the company's own last four periods of the same metric and
   kind (a quarter against quarters, a year against years: a quarter's flow is a quarter of the year; a rate, such as a NIM,
   may be judged against years when there are fewer than two quarters; at least two, all above zero). It is deliberately the wide test: a
   real order book can double, a margin does not triple. There is no low side: a margin or volume that collapses is often
   the news of the filing (independent review, 26 Oct 2026).
2. **Against what its type of company can earn.** A home-loan (housing finance) NIM 1-15% (small-ticket lenders run past
   10%), a bank's 1-8.5% (Bandhan has reported above 7%). Other lenders (microfinance NIMs run 10% and more) and every other
   metric have no range, only test 1: an EBITDA margin above 60% is real for power transmission, exchanges and ports.

The type is read from the company's industry the way sectors.toml reads it: the most specific level first.
A hidden figure comes back with its reason so the card can store it (``grounding.footer_hidden``, shown on the owner's Issues
page); the live footer simply does not carry it."""
from __future__ import annotations

import re

from .periods import due_date

RATIO = 3.0          # more than 3x the highest of the last periods
LOOK_BACK = 4        # the company's own last four periods
MIN_PRIORS = 2       # fewer than this and the company has no history to judge by
_PCT_UNITS = ("PCT", "%", "PERCENT", "")

# (type, metric) -> (low, high) in percent
RANGES = {("hfc", "nim"): (1.0, 15.0), ("bank", "nim"): (1.0, 8.5)}

_HFC = re.compile(r"housing\s+finance", re.I)
_BANK = re.compile(r"\bbanks?\b|\bbanking\b", re.I)
_NON_BANK = re.compile(r"non[- ]?banking", re.I)
_LENDER = re.compile(r"\bnbfc\b|finance|financial\s+services|microfinance|asset\s+management|broking|insurance", re.I)


def company_type(industry: str | None) -> str:
    """hfc | bank | lender | other, from the industry path's most specific level up."""
    for level in reversed([p.strip() for p in (industry or "").split(">") if p.strip()]):
        if _HFC.search(level):
            return "hfc"
        if _NON_BANK.search(level) or _LENDER.search(level):
            return "lender"
        if _BANK.search(level):
            return "bank"
    return "other"


def _num(entry: dict | None) -> float | None:
    v = (entry or {}).get("value")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _priors(metrics: list[dict], names: tuple[str, ...], entry: dict, rate: bool = False) -> list[float]:
    """The values of the company's own last four earlier periods of this metric and of the entry's kind (quarters for a
    quarter, years for a year: a quarter's flow is a quarter of the year), newest first, one a period."""
    end = due_date(entry.get("period"))
    if end is None:
        return []
    latest: dict[str, dict] = {}
    for m in metrics:
        p = m.get("period")
        if m.get("metric") not in names or _num(m) is None or not p or p == entry.get("period"):
            continue
        if (m.get("unit") or "") != (entry.get("unit") or "") or not re.fullmatch(r"(Q[1-4])?FY\d{2}", str(p)):
            continue
        d = due_date(p)
        if d is None or d >= end:
            continue
        if p not in latest or str(m.get("as_of") or "") >= str(latest[p].get("as_of") or ""):
            latest[p] = m
    quarter = str(entry.get("period")).startswith("Q")
    pool = sorted((p for p in latest if p.startswith("Q") == quarter), key=due_date, reverse=True)[:LOOK_BACK]
    if rate and len(pool) < MIN_PRIORS:   # a rate has no quarter-to-year scale (GIC's NIM: FY26 3.41%): its years
        pool = sorted(latest, key=due_date, reverse=True)[:LOOK_BACK]
    return [_num(latest[p]) for p in pool]


def hide_reason(metrics: list[dict], names: tuple[str, ...], entry: dict | None, fmt: str, industry: str | None) -> str | None:
    """Why this footer figure must not be shown, or None. ``metrics`` is the company's financial_metrics, ``names`` the
    footer spec's metric and aliases, ``entry`` the figure the footer would show."""
    value = _num(entry)
    if entry is None or value is None:
        return None
    kind = company_type(industry)
    if fmt == "pct" and (entry.get("unit") or "").upper().replace(" ", "") in _PCT_UNITS:
        if names[0] == "nim" and (kind, "nim") in RANGES:
            low, high = RANGES[(kind, "nim")]
            if not low <= value <= high:
                label = "home-loan lender" if kind == "hfc" else "bank"
                return f"{value:g}% is outside the {low:g}-{high:g}% a {label}'s NIM can be"
    priors = _priors(metrics, names, entry, rate=fmt == "pct")
    if len(priors) >= MIN_PRIORS and value > 0 and all(p > 0 for p in priors):
        if value > RATIO * max(priors):
            return f"{value:g} is more than {RATIO:g}x the company's own last {len(priors)} periods (highest {max(priors):g})"
    return None


SLIP_BAND = 1.25     # within 25% of 10x, 100x or 1,000x


def scale_slip(now: dict | None, base: dict | None) -> str | None:
    """Why a footer figure's comparative is a scale slip of it, or None: the two in one unit and one about 10, 100 or 1,000
    times the other. Shree Cement's Q2FY27 card (nse-106826079, 29 Oct 2026 audit) showed volumes of 10.52 MT against a
    previous quarter of 114.5 (an AI reading of 11.45), so "-90.8% QoQ". A sector volume, order book or ARPU does not move
    tenfold in a quarter or a year; a rate is left alone (a margin from 2% to 20% is a change, not a unit)."""
    a, b = _num(now), _num(base)
    if a is None or b is None or a <= 0 or b <= 0 or (now.get("unit") or "") != (base.get("unit") or ""):
        return None
    if str(now.get("unit") or "").upper().replace(" ", "") in _PCT_UNITS:
        return None
    ratio = max(a, b) / min(a, b)
    for power in (10.0, 100.0, 1000.0):
        if power / SLIP_BAND <= ratio <= power * SLIP_BAND:
            return f"{b:g} ({base.get('period')}) is about {power:g}x off {a:g}: a unit slip, not a change"
    return None


def note(label: str, entry: dict, reason: str) -> dict:
    """The record a hidden figure leaves on the block it was left off (read by ``card_notes``)."""
    return {"label": label, "period": entry.get("period"), "value": entry.get("value"), "reason": reason}


def card_notes(card_json: dict) -> list[str]:
    """One line a hidden footer figure, from the blocks of a card (fundamentals, results), for ``grounding.footer_hidden``."""
    seen, lines = set(), []
    for block in ("fundamentals", "results"):
        for h in (card_json.get(block) or {}).get("footer_hidden") or []:
            line = f"{h['label']} {h.get('value'):g} ({h.get('period')}) not shown: {h['reason']}" if isinstance(h.get("value"), (int, float)) \
                else f"{h['label']} ({h.get('period')}) not shown: {h['reason']}"
            if line not in seen:
                seen.add(line)
                lines.append(line)
    return lines
