"""CARD_VERDICT_NEEDS_FIGURE: a model's met / missed / delivered verdict on a target needs a figure in the target's unit in its
own words (settings.card_verdict_needs_figure; off by default, then nothing here runs). Blind audit 1 Nov 2026
(docs/audit/live/release-2026-11-01, deck_period_unreplayable): 9 of 23 stored guidance and watch verdicts were wrong.

* No figure for the target: HERITGFOOD "Add 5,000 farmers in Q2FY27" DELIVERED on "procurement volumes increased 7% YoY to
  1.73 MLPD" (no farmer count); EMUDHRA "International revenue growth" MET on "international business now contributes 62% of
  total revenue" (a share, not growth).
* Only the target's own figure: CLEANMAX "Commissioning of 51 MWp" MISSED on "1.4 GW commissioned in FY26, including 51 MWp";
  OLAELEC's 45,000-unit order guidance DELIVERED on "Q1 FY27 orders expected at 40,000 to 45,000 units" (an expectation).
* A miss the words contradict: SURYODAY "KPI check missed" on "NNPA ratio 4.2% at Mar-26, within the <=4.21 target"; CANBK
  "GNPA trending to FY27 guidance" missed on "GNPA reached 1.33%" against 1.50% (a lower-is-better ratio under its ceiling).

Only verdicts code did not decide reach here (watch_code's memory verdict and the relative-guidance verdict stand). Each failing
verdict becomes the dated "management said X" line with the reason; the verdict is never turned into its opposite."""

from __future__ import annotations

import re

from .guidance_dated import _LOWER_BETTER, _SAVING, _CORRIDOR, _bound, _figs, _num, _PERIODS
from .settings import card_verdict_needs_figure

GOOD, BAD = ("MET", "DELIVERED"), ("MISSED",)
_COUNT = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*([A-Za-z]{2,})")
_NOT_NOUN = {"cr", "crore", "crores", "lakh", "mn", "bn", "million", "billion", "bps", "percent", "x", "per", "and", "or", "to",
             "the", "in", "of", "by", "for", "at", "on", "from", "with", "vs", "day", "days", "year", "years", "month", "months",
             "quarter", "quarters", "times", "basis", "new", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
             "nov", "dec", "st", "nd", "rd", "th"}
_GROWTH = re.compile(r"\bgrow(?:th|s|ing)?\b", re.I)
_SHARE = re.compile(r"\bcontribut\w*|\bshare\b|%\s*of\s+(?:the\s+)?(?:total|overall|group|consolidated|company)", re.I)
_CHANGE = re.compile(r"\b(?:grew|grow\w*|rose|rise|up|increase\w*|declin\w*|fell|down|yoy|y-o-y|qoq|q-o-q)\b", re.I)
_FORWARD = re.compile(r"\b(?:expects?|expected|expecting|will|would|aims?|plans?|targets?|targeting|guid\w*|outlook|likely|"
                      r"to\s+reach|going\s+forward)\b", re.I)
_SAYS_MET = re.compile(r"\b(?:within|met|meets|meeting|achieved|beat|beats|beating|ahead\s+of|outperform\w*|better\s+than)\s+"
                       r"(?:the\s+|its\s+|our\s+)?(?:(?:[^.;,]|(?<=\d)[.,](?=\d)){0,30}?\s)?(?:target|guidance|range|goal)\b", re.I)
_SAYS_MISSED = re.compile(r"\b(?:missed|misses|short\s+of|fell\s+short|behind)\s+(?:the\s+|its\s+|our\s+)?(?:(?:[^.;,]|(?<=\d)[.,](?=\d)){0,30}?\s)?"
                          r"(?:target|guidance|range|goal)\b", re.I)


def _noun(word: str) -> str:
    return word.lower().rstrip("s") or word.lower()


def _units(text: str) -> set[str]:
    """The units of the figures in a target: %, bps, x, cr, lakh, mn, bn, a currency, or the word a count is of ("5,000 farmers",
    "51 MWp")."""
    out = {f[2] or f[1] for f in _figs(text) if f[2] or f[1]}
    for m in _COUNT.finditer(_PERIODS.sub(" ", text or "")):
        if m.group(2).lower() not in _NOT_NOUN:
            out.add(_noun(m.group(2)))
    return out


def _figures(text: str, units: set[str], growth: bool) -> list[float]:
    """The figures in ``text`` in one of ``units``; for a growth target, not a share ("contributes 62% of total revenue")."""
    found: list[float] = []
    for sentence in re.split(r"(?<=[.;])\s+", text or ""):
        shares = growth and bool(_SHARE.search(sentence)) and not _CHANGE.search(sentence)
        for value, cur, unit in _figs(sentence):
            if (unit or cur) in units and not (shares and unit == "%"):
                found.append(value)
        for m in _COUNT.finditer(_PERIODS.sub(" ", sentence)):
            if _noun(m.group(2)) in units and m.group(2).lower() not in _NOT_NOUN:
                found.append(_num(m.group(1)))
    return found


def _good(value: float, target: str, topic: str) -> bool | None:
    """Whether ``value`` meets or beats the target's bound: a range, one direction word, or a bare figure of a lower-is-better
    ratio (GNPA, costs) read as a ceiling; None when the target gives no bound."""
    words = f"{topic} {target}"
    lower_better = bool(_LOWER_BETTER.search(words)) and not _SAVING.search(words)
    b = _bound(target)
    if b is None:
        figs = [f for f in _figs(target) if f[1] or f[2]]
        if len(figs) != 1 or not lower_better:
            return None
        return value <= figs[0][0]
    lo, hi, slo, shi, _cur, _unit = b
    inside = (lo is None or (value > lo if slo else value >= lo)) and (hi is None or (value < hi if shi else value <= hi))
    if inside or lo is None or hi is None or _CORRIDOR.search(words):
        return inside
    return value < lo if lower_better else value > hi   # beyond a range on its good side (SKYGOLD) is no miss


def why_unjudged(status: str, target: str | None, evidence: str | None, topic: str | None = None) -> str | None:
    """Why a model's ``status`` on a target cannot stand on ``evidence``, in plain words; None when it can, when the target has
    no figure (an event: the rule does not apply), or when the switch is off."""
    if not card_verdict_needs_figure() or status not in GOOD + BAD:
        return None
    target, evidence, topic = str(target or ""), str(evidence or ""), str(topic or "")
    units = _units(target)
    if not units:
        return None
    growth = bool(_GROWTH.search(f"{topic} {target}"))
    figures = _figures(evidence, units, growth)
    if not figures:
        return f"the filing's words give no figure in the target's unit ({', '.join(sorted(units))})"
    if status in BAD and _SAYS_MET.search(evidence):
        return "the verdict says missed, but its own words say the target was met"
    if status in GOOD and _SAYS_MISSED.search(evidence):
        return "the verdict says met, but its own words say the target was missed"
    own = {f[0] for f in _figs(target)} | {_num(m.group(1)) for m in _COUNT.finditer(_PERIODS.sub(" ", target))}
    actual = sorted({v for v in figures if v not in own})
    if not actual:
        if status in BAD:
            return "the filing's words state only the target's own figure, not a result short of it"
        if _FORWARD.search(evidence):
            return "the filing's words restate the target as an expectation, not a result"
        return None
    if status in BAD and len(actual) == 1 and _good(actual[0], target, topic):
        return f"the filing's figure {actual[0]:g} meets the target ({target}), so missed cannot stand"
    return None


def judge_item(status: str, item: dict, evidence: str | None) -> str | None:
    """``why_unjudged`` for a memory guidance item or watch: its target when that has a figure, else its own words (statement or
    text, "Commissioning of 51 MWp solar capacity"); the topic is its words and metric."""
    target = str(item.get("target") or "")
    words = str(item.get("statement") or item.get("text") or "")
    return why_unjudged(status, target if _units(target) else words, evidence, f"{words} {item.get('metric') or ''}")
