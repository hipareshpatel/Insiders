"""F172 (CARD_GUIDANCE_DATED): a guidance verdict only from a target that can be judged by this filing.

A card said management "missed" a target in three live cases (26 Oct 2026 audit): Castrol India's 21-24% EBITDA margin
was "medium term" (no date) and, said again in August 2026, was stored as due FY26 (a year that ended before it was
said); Union Bank's FCNR target (due Sep-2026) was "missed" by a filing that never mentions FCNR. The rule, set by the
owner: a verdict (delivered / on track / delayed / missed) comes only from a memory target that

1. has its own date, and the date is not before the day it was said;
2. is due for the same period this filing reports; and
3. is for a metric this filing prints a figure for (the same metric name; the memory figure carries the basis).

Anything else gets no verdict. The target is still shown, as "management said X on <date>" (``said_on``).
"""

from __future__ import annotations

import re
from datetime import date

from .periods import canonical_period, due_date

_PERIOD = re.compile(r"(?:Q[1-4]|H[12]|9M)?FY\d{2}")
_KPI_TARGET = re.compile(
    r"\s*(?:(?:above|below|over|under|at least|at most|more than|less than|min(?:imum)?|max(?:imum)?|>=|<=|≥|≤|>|<|=)\s*)?"
    r"(?:₹|rs\.?|inr|usd|\$)?\s*-?\d[\d,]*\.?\d*(?:\s*(?:-|to|–)\s*-?\d[\d,]*\.?\d*)?\s*"
    r"(?:%|bps|x|cr|crore|crores|lakh|mn|bn|million|billion)?\s*", re.I)


def _name(metric: str | None) -> str:
    """A metric's comparable name: lower case, letters and digits only, a trailing "growth" dropped (a growth target is
    judged on the figure's own change)."""
    s = re.sub(r"[^a-z0-9]+", "_", (metric or "").lower()).strip("_")
    return re.sub(r"_?growth$", "", s).replace("_", "")


def _own_periods(metrics: list[dict], news_id: str) -> dict[str, set[str]]:
    """The periods this filing printed figures for, each with the metric names it printed for that period."""
    from .dossier import reported_by

    out: dict[str, set[str]] = {}
    for m in metrics:
        if m.get("value") is not None and m.get("period") and reported_by(m, news_id):
            out.setdefault(canonical_period(m["period"]), set()).add(_name(m.get("metric")))
    return out


def _same_period(due: str | None, due_iso: str | None, period: str) -> bool:
    label = canonical_period(due or "")
    if _PERIOD.fullmatch(label):
        return label == period          # FY27 is not Q2FY27, though a year's end and its last quarter's end are one day
    end = date.fromisoformat(due_iso) if due_iso else None
    return end is not None and end == due_date(period) and bool(re.fullmatch(r"Q[1-4]FY\d{2}", period))


def why_no_verdict(g: dict, metrics: list[dict], news_id: str) -> str | None:
    """None when memory target ``g`` may be judged by filing ``news_id``; else why not, in plain words."""
    if not g.get("due_date"):
        return "the target has no date"
    if g["due_date"] < (g.get("given_on") or "")[:10]:
        return "the target's date is before the day it was said"
    own = _own_periods(metrics, news_id)
    periods = [p for p in own if _same_period(g.get("due"), g.get("due_date"), p)]
    if not periods:
        return "the target is not due for the period this filing reports"
    if not any(_name(g.get("metric")) and _name(g.get("metric")) in own[p] for p in periods):
        return "this filing prints no figure for the target's metric"
    return None


def why_no_watch_verdict(w: dict, metrics: list[dict], news_id: str) -> str | None:
    """The same rule for a KPI watch item: its own check date, its quarter among the filing's periods, and a target that
    is a plain figure to compare with (not "progress toward 6,000 Cr", a cumulative build-up that a quarter's P&L line
    cannot settle)."""
    if w.get("kind") != "KPI":
        return None
    if not w.get("check_by") or w["check_by"] < (w.get("created_on") or "")[:10]:
        return "the check has no date, or one before it was set"
    own = _own_periods(metrics, news_id)
    if canonical_period(w.get("check_in") or "") not in own:
        return "the check is not due for the period this filing reports"
    if not _KPI_TARGET.fullmatch(str(w.get("target") or "")):
        return "the target is not a plain figure"
    return None


def said_on(item: dict, why: str) -> str:
    """The dated statement that replaces a verdict."""
    text = item.get("statement") or item.get("text") or ""
    target = item.get("target")
    when = (item.get("given_on") or item.get("created_on") or "")[:10]
    due = item.get("due") or item.get("check_in")
    parts = ([f"target {target}"] if target else []) + [f"due {due}" if due else "no date given"]
    return f"Management said on {when}: \"{text}\" ({'; '.join(parts)}). Not judged against this filing: {why}."
