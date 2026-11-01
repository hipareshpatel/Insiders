"""CARD_WORDS_MATCH_FIGURES: a card's comparison words checked against its own figures (settings.card_words_match_figures; off
by default, then nothing here runs). Blind audit 1 Nov 2026, "arithmetic in words": a card said revenue growth "accelerated"
when this quarter's YoY was below last quarter's, and "far outpaced" between two figures the wrong way round.

Three checks, each acting only when the card's own figures contradict the word (no figure, no judgement):

1. **doubled / tripled / halved** after a metric the results table holds: the table's YoY or QoQ change for that metric (the
   one the words name, else either) must agree (doubled +90% or more, tripled +190%, halved -45% or less).
2. **accelerated / slowed / decelerated** after a metric's growth: this quarter's YoY in the table against the previous
   quarter's YoY worked out from memory (the previous quarter and the quarter a year before it).
3. **outpaced / outperformed / outgrew**, between two percentages of one sentence: the first must be above the second.

A contradicted item of a list (what happened, why it matters, notable changes) is dropped; in the headline or takeaway the word
is softened ("doubled" -> "rose", "halved" -> "fell", "accelerated" -> "rose", "slowed" -> "fell") or, for an outpacing,
left and noted. Every change is returned as a note."""

from __future__ import annotations

import re

from .grounding import _tokens
from .periods import prior_quarter_period, prior_year_period
from .settings import card_words_match_figures

_METRICS = (("revenue", r"revenue|sales|top[- ]?line|total income"), ("ebitda", r"EBITDA|operating profit"),
            ("pat", r"PAT|net profit|profit after tax|bottom[- ]?line|(?<!operating )(?<!gross )profit(?!\s+before)"),
            ("pbt", r"PBT|profit before tax"))
_MULTIPLE = re.compile(r"\b(doubl(?:ed|es|ing)|tripl(?:ed|es|ing)|halv(?:ed|es|ing)|more than doubled)\b", re.I)
_PACE = re.compile(r"\b(accelerat(?:ed|es|ing)|slow(?:ed|s|ing)|decelerat(?:ed|es|ing))\b", re.I)
_OUTPACE = re.compile(r"\b((?:far\s+)?out(?:pac|perform|grow|grew|strip)\w*)\b", re.I)
_SENTENCE = re.compile(r"(?<=[.;])\s+")
_SOFT = {"doubled": "rose", "doubles": "rises", "doubling": "rising", "tripled": "rose", "triples": "rises", "tripling": "rising",
         "halved": "fell", "halves": "falls", "halving": "falling", "more than doubled": "rose",
         "accelerated": "rose", "accelerates": "rises", "accelerating": "rising",
         "slowed": "fell", "slows": "falls", "slowing": "falling", "decelerated": "fell", "decelerates": "falls", "decelerating": "falling"}
_LISTS = ("what_happened", "why_it_matters", "notable_changes")


def _metric_before(text: str, at: int) -> str | None:
    """The table metric the words name last before position ``at``, in the same clause."""
    clause = re.split(r"[;,]|\b(?:while|but|whereas|and)\b", text[:at])[-1]
    best = None
    for key, pattern in _METRICS:
        for m in re.finditer(rf"\b(?:{pattern})\b", clause, re.I):
            if best is None or m.start() > best[1]:
                best = (key, m.start())
    return best[0] if best else None


def _row(results: dict, key: str) -> dict | None:
    row = results.get(key) or (results.get("pat_owners") if key == "pat" else None)
    return row if isinstance(row, dict) else None


def _multiple_wrong(word: str, text: str, row: dict) -> bool:
    w = word.lower()
    floor = 190.0 if w.startswith("tripl") else 90.0
    want = (lambda c: c <= -45.0) if w.startswith("halv") else (lambda c: c >= floor)
    named = "qoq" if re.search(r"\bQoQ\b|sequential|quarter[- ]on[- ]quarter", text, re.I) else \
        "yoy" if re.search(r"\bYoY\b|year[- ]on[- ]year|year[- ]ago", text, re.I) else None
    changes = [row.get(f"{k}_pct") for k in ((named,) if named else ("yoy", "qoq"))]
    changes = [c for c in changes if isinstance(c, (int, float))]
    return bool(changes) and not any(want(c) for c in changes)


def _previous_yoy(found: dict[tuple[str, str], float], key: str, period: str | None) -> float | None:
    prev = prior_quarter_period(period or "")
    base = prior_year_period(prev) if prev else None
    now, then = found.get((key, prev or "")), found.get((key, base or ""))
    if now is None or not then or then <= 0:
        return None
    return (now / then - 1) * 100


def _pace_wrong(word: str, row: dict, previous: float | None) -> bool:
    yoy = row.get("yoy_pct")
    if not isinstance(yoy, (int, float)) or previous is None:
        return False
    return yoy <= previous if word.lower().startswith("accelerat") else yoy >= previous


def _outpace_wrong(sentence: str, at: int) -> bool:
    pcts = [(pos, value) for value, _d, pos, kind, _r in _tokens(sentence) if kind == "pct"]
    before = [v for pos, v in pcts if pos < at]
    after = [v for pos, v in pcts if pos > at]
    if not before or not after:
        return False
    return before[-1] <= after[0]


def _judge(text: str, results: dict, found: dict[tuple[str, str], float]) -> list[tuple[str, str]]:
    """(word, why) for each comparison word of ``text`` its figures contradict."""
    wrong = []
    for sentence in _SENTENCE.split(text.replace("**", "")):
        for m in _MULTIPLE.finditer(sentence):
            key = _metric_before(sentence, m.start())
            row = _row(results, key) if key else None
            if row and _multiple_wrong(m.group(1), sentence, row):
                wrong.append((m.group(1), f"{key} change YoY {row.get('yoy_pct')}%, QoQ {row.get('qoq_pct')}%"))
        for m in _PACE.finditer(sentence):
            key = _metric_before(sentence, m.start())
            row = _row(results, key) if key else None
            if row and re.search(r"growth|grow|rise|increase|expan", sentence[:m.start()], re.I):
                previous = _previous_yoy(found, key, results.get("period"))
                if _pace_wrong(m.group(1), row, previous):
                    wrong.append((m.group(1), f"{key} YoY {row.get('yoy_pct')}% against the previous quarter's {previous:.1f}%"))
        for m in _OUTPACE.finditer(sentence):
            if _outpace_wrong(sentence, m.start()):
                wrong.append((m.group(1), "the first growth figure is not above the second"))
    return wrong


def _soften(text: str, word: str) -> str | None:
    soft = _SOFT.get(word.lower())
    if soft is None:
        return None
    return re.sub(rf"\b{re.escape(word)}\b", lambda m: soft.capitalize() if m.group(0)[0].isupper() else soft, text, count=1)


def apply_card_json(card_json: dict, dossier: dict | None = None) -> list[str]:
    """The checks on a stored or new card (a dict) with a results table; memory gives the previous quarter's YoY."""
    results = card_json.get("results")
    if not card_words_match_figures() or not isinstance(results, dict):
        return []
    found = {(m["metric"], m["period"]): m["value"] for m in (dossier or {}).get("financial_metrics") or []
             if isinstance(m, dict) and m.get("period") and isinstance(m.get("value"), (int, float))}
    for key in ("revenue", "ebitda", "pat", "pbt"):   # the table's own figures over memory's
        row = results.get(key)
        if isinstance(row, dict):
            for slot, p in (("value", results.get("period")), ("prev_quarter", prior_quarter_period(results.get("period") or ""))):
                if isinstance(row.get(slot), (int, float)) and p:
                    found[(key, p)] = row[slot]
    notes: list[str] = []
    for attr in ("headline", "takeaway"):
        text = card_json.get(attr)
        if not isinstance(text, str):
            continue
        for word, why in _judge(text, results, found):
            softer = _soften(card_json[attr], word)
            if softer:
                card_json[attr] = softer
                notes.append(f"{attr}: '{word}' softened, the figures do not show it ({why})")
            else:
                notes.append(f"{attr}: '{word}' is not what the figures show ({why}); left for review")
    for name in _LISTS:
        items = card_json.get(name)
        if not isinstance(items, list):
            continue
        kept = []
        for item in items:
            text = item.get("text") if isinstance(item, dict) else item if isinstance(item, str) else None
            wrong = _judge(text, results, found) if isinstance(text, str) else []
            if wrong:
                notes.append(f"{name}: dropped '{text[:80]}', '{wrong[0][0]}' is not what the figures show ({wrong[0][1]})")
                continue
            kept.append(item)
        card_json[name] = kept
    return notes
