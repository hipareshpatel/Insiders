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


def _own_periods(metrics: list[dict], news_id: str, discussed: str | None = None) -> dict[str, set[str]]:
    """The periods this filing printed figures for, each with the metric names it printed for that period. A call or
    investor deck states no table of its own: the quarter it discusses (``discussed``, the period its card shows from the
    results filing that reported it) counts as its period, with memory's figures for it (KRN Heat Exchanger's Q2FY27 deck,
    live audit 1 Nov 2026: a missed EBITDA-margin target was hidden as "not due for the period this filing reports")."""
    from .dossier import reported_by

    out: dict[str, set[str]] = {}
    for m in metrics:
        if m.get("value") is None or not m.get("period"):
            continue
        period = canonical_period(m["period"])
        if reported_by(m, news_id) or (discussed and period == canonical_period(discussed)):
            out.setdefault(period, set()).add(_name(m.get("metric")))
    return out


def discussed_period(event_type: str | None, metrics: list[dict], filed_at: str) -> str | None:
    """The quarter a call or investor deck filed on ``filed_at`` discusses (the card's own rule, dossier._discussed), else None."""
    if event_type != "CONCALL_PRESENTATION":
        return None
    from .dossier import _discussed, _latest_reported

    try:
        filed = date.fromisoformat((filed_at or "")[:10])
    except ValueError:
        return None
    latest = _latest_reported({"financial_metrics": metrics}, filed)
    return canonical_period(latest[1]) if latest and _discussed(latest[0], filed) else None


def _same_period(due: str | None, due_iso: str | None, period: str) -> bool:
    label = canonical_period(due or "")
    if _PERIOD.fullmatch(label):
        return label == period          # FY27 is not Q2FY27, though a year's end and its last quarter's end are one day
    end = date.fromisoformat(due_iso) if due_iso else None
    return end is not None and end == due_date(period) and bool(re.fullmatch(r"Q[1-4]FY\d{2}", period))


def why_no_verdict(g: dict, metrics: list[dict], news_id: str, discussed: str | None = None) -> str | None:
    """None when memory target ``g`` may be judged by filing ``news_id``; else why not, in plain words."""
    if not g.get("due_date"):
        return "the target has no date"
    if g["due_date"] < (g.get("given_on") or "")[:10]:
        return "the target's date is before the day it was said"
    own = _own_periods(metrics, news_id, discussed)
    periods = [p for p in own if _same_period(g.get("due"), g.get("due_date"), p)]
    if not periods:
        return "the target is not due for the period this filing reports"
    if not any(_name(g.get("metric")) and _name(g.get("metric")) in own[p] for p in periods):
        return "this filing prints no figure for the target's metric"
    return None


def why_no_watch_verdict(w: dict, metrics: list[dict], news_id: str, discussed: str | None = None) -> str | None:
    """The same rule for a KPI watch item: its own check date, its quarter among the filing's periods, and a target that
    is a plain figure to compare with (not "progress toward 6,000 Cr", a cumulative build-up that a quarter's P&L line
    cannot settle)."""
    if w.get("kind") != "KPI":
        return None
    if not w.get("check_by") or w["check_by"] < (w.get("created_on") or "")[:10]:
        return "the check has no date, or one before it was set"
    own = _own_periods(metrics, news_id, discussed)
    if canonical_period(w.get("check_in") or "") not in own:
        return "the check is not due for the period this filing reports"
    target = str(w.get("target") or "")
    if not discussed and not _KPI_TARGET.fullmatch(target):
        return "the target is not a plain figure"   # as before; the honest reason below rides DECK_DISCUSSED_PERIOD (review)
    if not re.search(r"\d", target):
        return "the target is not a plain figure"
    if not _KPI_TARGET.fullmatch(target):
        # a number with words around it ("at or below Rs 1.95", "16% or above"): the target is a figure, so the honest
        # reason is that no figure of that metric was found, not that the target is not a figure (blind grade 1 Nov 2026)
        return "this filing prints no figure for the target's metric"
    return None


def said_on(item: dict, why: str) -> str:
    """The dated statement that replaces a verdict."""
    text = item.get("statement") or item.get("text") or ""
    target = item.get("target")
    when = (item.get("given_on") or item.get("created_on") or "")[:10]
    due = item.get("due") or item.get("check_in")
    parts = ([f"target {target}"] if target else []) + [f"due {due}" if due else "no date given"]
    return f"Management said on {when}: \"{text}\" ({'; '.join(parts)}). Not judged against this filing: {why}."


# ---- DECK_DISCUSSED_PERIOD: a code check of a "met / delivered" verdict against the target's own numbers
_CUR = {"₹": "inr", "rs": "inr", "rs.": "inr", "inr": "inr", "$": "usd", "usd": "usd"}
_UNIT = {"%": "%", "percent": "%", "bps": "bps", "x": "x", "cr": "cr", "crore": "cr", "crores": "cr", "lakh": "lakh",
         "mn": "mn", "million": "mn", "bn": "bn", "billion": "bn"}
_PERIODS = re.compile(r"\b(?:Q[1-4]|H[12]|9M)?\s?FY\s?'?\d{2,4}\b|\b(?:19|20)\d{2}\b", re.I)
_FIG = re.compile(r"(?P<cur>₹|rs\.?|inr|\$|usd)?\s*(?P<n>\d[\d,]*\.?\d*)(?:\s*(?P<u>%|percent\b|bps\b|crores?\b|cr\b|lakh\b|mn\b|million\b|bn\b|billion\b|x\b))?", re.I)
_UP = re.compile(r"\b(above|over|more than|at least|min(?:imum)?|or (?:above|higher|more)|greater than)\b|>=|≥|>", re.I)
_DOWN = re.compile(r"\b(below|under|less than|at most|max(?:imum)?|or (?:below|lower|less)|at or below)\b|<=|≤|<", re.I)
_STRICT = re.compile(r"\b(above|over|more than|below|under|less than|greater than)\b|(?<![<>=≤≥])[<>](?!=)", re.I)


_NEGATIVE = re.compile(r"(?<![\w.])[-−(]\s*(?:₹|rs\.?|\$)?\s*\d")


def _num(x: str) -> float:
    return float(x.replace(",", "").rstrip("."))


def _figs(text: str) -> list[tuple[float, str | None, str | None]]:
    text = _PERIODS.sub(" ", text or "")
    return [(_num(m["n"]), _CUR.get((m["cur"] or "").lower()), _UNIT.get((m["u"] or "").lower()))
            for m in _FIG.finditer(text) if m["n"] and re.search(r"\d", m["n"])]


def _bound(target: str):
    """(low, high, strict_low, strict_high, cur, unit) for a numeric target with one range or one direction word, else None."""
    figs = _figs(target)
    if not figs or len(figs) > 2:
        return None
    cur = next((f[1] for f in figs if f[1]), None)
    unit = next((f[2] for f in figs if f[2]), None)
    if not cur and not unit:
        return None
    t = _PERIODS.sub(" ", target)
    if len(figs) == 2:
        if _UP.search(t) or _DOWN.search(t) or not re.search(
                r"\d\s*(?:%|bps|cr|crores?|mn|bn|million|billion|x)?\s*(?:-|–|to)\s*(?:₹|rs\.?|\$)?\s*\d", t, re.I):
            return None
        lo, hi = sorted((figs[0][0], figs[1][0]))
        return lo, hi, False, False, cur, unit
    v, strict = figs[0][0], bool(_STRICT.search(t))
    up, down = bool(_UP.search(t)), bool(_DOWN.search(t))
    if up == down:
        return None
    return (v, None, strict, False, cur, unit) if up else (None, v, False, strict, cur, unit)


def numeric_contradiction(target: str | None, evidence: str | None) -> str | None:
    """A sentence naming the contradiction when the one figure in ``evidence`` that is in the target's unit lies outside the
    target's range or on the wrong side of its bound ("36 bps" against "33-35 bps"); else None. Figures equal to a bound are the
    target quoted back and skipped; two different candidate figures give None (not certain)."""
    if _NEGATIVE.search(str(target or "")) or _NEGATIVE.search(str(evidence or "")):
        return None   # a sign the figure reader drops ("-5%" read as 5) could flip a right verdict (review)
    b = _bound(str(target or ""))
    if not b:
        return None
    lo, hi, slo, shi, cur, unit = b
    bounds = {x for x in (lo, hi) if x is not None}
    figs = [f[0] for f in _figs(evidence or "") if f[2] == unit and (not cur or f[1] == cur)]
    if any(f in bounds for f in figs):
        return None   # the evidence quotes the target back: which other figure is the result is not certain (review)
    got = set(figs)
    if len(got) != 1:
        return None
    v = got.pop()
    ok = (lo is None or (v > lo if slo else v >= lo)) and (hi is None or (v < hi if shi else v <= hi))
    return None if ok else f"the filing's figure {v:g} is outside the target ({target})"


def smaller_count(target: str | None, evidence: str | None) -> str | None:
    """For an event target with a count ("award of 26,000-site add-on order") that ``evidence`` meets with a smaller count of the
    same thing (18,685 add-on sites): the sentence saying so, else None."""
    m = re.search(r"(\d[\d,]*)\s*-?\s*([A-Za-z]{3,})", _PERIODS.sub(" ", str(target or "")))
    if not m or _num(m[1]) < 100:
        return None
    want, noun = _num(m[1]), m[2].lower().rstrip("s")
    if noun in _UNIT or noun in ("crore", "lakh", "per", "and", "the", "day", "basi", "year", "month", "new"):
        return None
    if _DOWN.search(_PERIODS.sub(" ", str(target or ""))) or re.search(r"\b(?:reduce|cut|limit|lower)\b", str(target or ""), re.I):
        return None   # a lower-is-better target: a smaller count is the target met, not missed (review)
    ev = _PERIODS.sub(" ", evidence or "")
    seen = [_num(e["n"]) for e in _FIG.finditer(ev) if re.search(rf"\b{re.escape(noun)}s?\b", ev[e.end():e.end() + 45].lower())]
    if seen and all(x < want for x in seen):
        return f"the filing states {max(seen):,.0f} {noun}s against a target of {want:,.0f}, a smaller count is not delivery"
    return None
