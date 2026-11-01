"""CARD_YEAR_AGO_LABEL: a year-ago label in a card's words that is one year too old (settings.card_year_ago_label; off by
default, then nothing here runs). Blind audit 1 Nov 2026: GICRE (nse-106837460, an H1FY27 card) said "from ₹5,404.12 Cr in H1 FY25"
and HEGAM (nse-106837190, a Q2FY27 card) said "compared to ₹696.85 Cr in Q2FY25"; the year-ago of both is one year later.

The card's period is the results table's, else the first quarter, half, nine-month or full-year label of its headline. A label
that names exactly two years before it (the same quarter, half, nine months or year) is replaced by the right year-ago label
("Q2FY25" -> "Q2FY26"), but only in a clear comparison context: after vs / versus / against / compared with or to / from / over /
YoY, after a change word and "in", or beside "a year earlier". A label in a sentence about another year on purpose (since,
guidance, target, outlook, "by FY25") and any label outside such a context is left. Quotes are never touched. Every change is
returned as a note."""

from __future__ import annotations

import re

from .periods import prior_year_period
from .settings import card_year_ago_label

_LABEL = re.compile(r"\b((?:Q[1-4]|H[12]|9M)\s?)?FY\s?(\d{4}|\d{2})\b(?P<range>\s?[-–/]\s?\d{2,4}\b)?", re.I)
_FIGURE = re.compile(r"(?:₹|rs\.?\s?|inr\s?)?(-?\d[\d,]*(?:\.\d+)?)\s*(?:cr\b|crores?\b|%|x\b)?", re.I)
_CONTEXT = re.compile(r"\b(?:vs\.?|versus|against|compared\s+(?:with|to)|as\s+compared\s+(?:with|to)|from|over|yoy|year[- ]on[- ]year"
                      r"|(?:rose|rise|rising|fell|fall|falling|up|down|grew|growth|declined|decline|increased|increase|jumped|dropped"
                      r"|slipped|improved|widened|narrowed|higher|lower)\b[^.;]{0,50}\bin)\b", re.I)
_ON_PURPOSE = re.compile(r"\b(?:since|until|till|by|guidance|guided|target(?:s|ed)?|outlook|expects?|expected|forecast|estimate[sd]?"
                         r"|plans?|aims?)\b", re.I)
_AFTER_ON_PURPOSE = re.compile(r"\s*(?:guidance|target|outlook|estimate|forecast)", re.I)
_CLAUSE = re.compile(r"[.;]\s")
_LISTS = (("what_happened", ("text", "why", "change")), ("why_it_matters", ("text", "why", "change")),
          ("notable_changes", ("text", "why", "change")))


def _norm(label: str) -> str:
    return re.sub(r"\s", "", label).upper()


def card_period(card_json: dict) -> str | None:
    """The card's period: the results table's, else the first quarter, half or nine-month label of its headline or timeline entry
    (a bare year there is as often a year still running, "FY27 guidance", as the year reported: blind review of release check
    41318733817)."""
    period = (card_json.get("results") or {}).get("period") if isinstance(card_json.get("results"), dict) else None
    if isinstance(period, str) and prior_year_period(period):
        return _norm(period)
    for attr in ("headline", "timeline_entry"):
        text = card_json.get(attr)
        if isinstance(text, str) and (m := _LABEL.search(text)):
            return None if m.group("range") or not m.group(1) else _norm(m.group(0))
    return None


def _figure_before(text: str, start: int) -> float | None:
    """The last figure of the label's own clause before it ("from ₹5,404.12 Cr in H1 FY25": 5404.12)."""
    clause = _CLAUSE.split(text[:start])[-1]
    found = [m for m in _FIGURE.finditer(clause) if not _LABEL.search(clause[max(0, m.start() - 6):m.end()])]
    return abs(float(found[-1].group(1).replace(",", ""))) if found else None


def _memory_has(dossier: dict | None, period: str, figure: float | None) -> bool:
    """Whether memory holds ``figure`` (any metric, either basis, within 1%) for ``period``."""
    if figure is None or not dossier:
        return False
    return any(isinstance(m, dict) and m.get("period") == period and isinstance(m.get("value"), (int, float))
               and abs(abs(m["value"]) - figure) <= 0.01 * max(abs(m["value"]), 0.01)
               for m in dossier.get("financial_metrics") or [])


def _in_comparison(text: str, start: int, end: int) -> bool:
    """The label at text[start:end] stands in a comparison: a comparison word, no on-purpose word between it and the label (in
    its own sentence), or "a year earlier" beside it."""
    before = text[:start]
    cut = list(_CLAUSE.finditer(before))
    before = before[cut[-1].end():] if cut else before
    if _AFTER_ON_PURPOSE.match(text[end:]):
        return False
    after = text[end:end + 40]
    if re.match(r"\W{0,3}(?:a\s+)?year\s+(?:earlier|ago)", after, re.I) and not _ON_PURPOSE.search(before[-40:]):
        return True
    hits = list(_CONTEXT.finditer(before[-120:]))
    if not hits:
        return False
    between = before[-120:][hits[-1].start():]
    return not _ON_PURPOSE.search(between) and not _LABEL.search(between)


def fix_text(text: str, period: str, dossier: dict | None = None) -> tuple[str, list[str]]:
    """``text`` with a year-ago label two years back (in a comparison) put right, and what was changed. A label written with a year
    range ("Q2FY25-26", the year 2025-26) is never read as two years back; the figure beside the label must be memory's figure for
    the year-ago period and not for the period two years back (a figure that truly is two years back stays: blind review of release
    check 41318733817)."""
    year_ago = prior_year_period(period)
    two_back = prior_year_period(year_ago or "")
    if not year_ago or not two_back:
        return text, []
    changed: list[str] = []
    out, last = [], 0
    for m in _LABEL.finditer(text):
        if m.group("range") or _norm(m.group(0)) != two_back or not _in_comparison(text, m.start(), m.end()):
            continue
        figure = _figure_before(text, m.start())
        if not _memory_has(dossier, year_ago, figure) or _memory_has(dossier, two_back, figure):
            continue
        # the year digits only, so the label keeps its own spacing and year width ("H1 FY25" -> "H1 FY26")
        digits = m.group(2)
        new_year = year_ago[-len(digits):]
        out += [text[last:m.start(2)], new_year]
        last = m.end(2)
        changed.append(f"{m.group(0)} -> {m.group(0)[:-len(digits)]}{new_year}")
    out.append(text[last:])
    return "".join(out), changed


def apply_card_json(card_json: dict, dossier: dict | None = None) -> list[str]:
    """Put a year-ago label two years back right in a stored or new card (a dict); the notes of what was changed."""
    if not card_year_ago_label():
        return []
    period = card_period(card_json)
    if not period or not prior_year_period(period):
        return []
    notes: list[str] = []

    def fix(holder: dict, key: str, where: str) -> None:
        value = holder.get(key)
        if isinstance(value, str):
            new, changed = fix_text(value, period, dossier)
            if changed:
                holder[key] = new
                notes.append(f"{where}: year-ago label {', '.join(changed)} (the card is {period})")

    for attr in ("headline", "takeaway", "timeline_entry"):
        fix(card_json, attr, attr)
    for name, keys in _LISTS:
        for item in card_json.get(name) or []:
            if isinstance(item, dict):
                for key in keys:
                    fix(item, key, name)
    for item in card_json.get("key_numbers") or []:
        if isinstance(item, dict):
            for key in ("label", "change"):
                fix(item, key, "key_numbers")
    return notes
