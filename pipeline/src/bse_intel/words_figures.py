"""CARD_WORDS_MATCH_FIGURES: a card's comparison words checked against its own figures (settings.card_words_match_figures; off
by default, then nothing here runs). Blind audit 1 Nov 2026, "arithmetic in words": a card said revenue growth "accelerated"
when this quarter's YoY was below last quarter's, and "far outpaced" between two figures the wrong way round.

Three checks, each acting only when the card's own figures contradict the word (no figure, no judgement):

1. **doubled / tripled / halved** after a metric the results table holds: the table's YoY or QoQ change for that metric (the
   one the words name, else either) must agree (doubled +90% or more, tripled +190%, halved -45% or less).
2. **accelerated / slowed / decelerated** after a metric's growth: this quarter's YoY in the table against the previous
   quarter's YoY worked out from memory (the previous quarter and the quarter a year before it).
3. **outpaced / outperformed / outgrew**, between two percentages of one sentence: the first must be above the second.

A contradicted word is softened ("doubled" -> "rose", "halved" -> "fell", "accelerated" -> "rose", "slowed" -> "fell"), in a
list item (what happened, why it matters, notable changes) as in the headline or takeaway; an outpacing has no softer word, so
its list item is dropped and a headline or takeaway one is noted. Memory is read on the card's own basis only. Every change is returned as a note."""

from __future__ import annotations

import re

from .grounding import _tokens
from .results_one_line import _differs_from, _periods
from .periods import prior_quarter_period, prior_year_period
from .settings import card_words_match_figures

_METRICS = (("revenue", r"revenue|sales|top[- ]?line|total income"), ("ebitda", r"EBITDA|operating profit"),
            ("pat", r"PAT|net profit|profit after tax|bottom[- ]?line|(?<!operating )(?<!gross )profit(?!\s+before)"),
            ("pbt", r"PBT|profit before tax"))
_MULTIPLE = re.compile(r"\b((?:(?:nearly|almost|more than|over)\s+)?(?:doubl|tripl)(?:ed|es|ing)|halv(?:ed|es|ing))\b", re.I)
_PACE = re.compile(r"\b(accelerat(?:ed|es|ing)|slow(?:ed|s|ing)|decelerat(?:ed|es|ing))\b", re.I)
_OUTPACE = re.compile(r"\b((?:far\s+)?out(?:pac|perform|grow|grew|strip)\w*)\b", re.I)
_SENTENCE = re.compile(r"(?<=[.;])\s+")
_SOFT = {"doubled": "rose", "doubles": "rises", "doubling": "rising", "tripled": "rose", "triples": "rises", "tripling": "rising",
         "halved": "fell", "halves": "falls", "halving": "falling",
         **{f"{m} {w}": "rose" for m in ("nearly", "almost", "more than", "over") for w in ("doubled", "tripled")},
         "accelerated": "rose", "accelerates": "rises", "accelerating": "rising",
         "slowed": "fell", "slows": "falls", "slowing": "falling", "decelerated": "fell", "decelerates": "falls", "decelerating": "falling"}
_LISTS = ("what_happened", "why_it_matters", "notable_changes")


_CLAUSE_BREAK = re.compile(r"[;,]|\b(?:while|but|whereas|and)\b")
_NOT_METRIC = re.compile(r"\b(?:provisions?|investments?|costs?|expenses?|orders?|volumes?|customers?|margins?)\b", re.I)


def _clause_at(text: str, at: int) -> tuple[str, int]:
    """The clause of ``text`` holding position ``at``, and where that clause starts."""
    start = 0
    for m in _CLAUSE_BREAK.finditer(text):
        if m.end() <= at:
            start = m.end()
        elif m.start() >= at:
            return text[start:m.start()], start
    return text[start:], start


def _metric_before(text: str, at: int) -> str | None:
    """The table metric directly before position ``at``: named within the 4 words before it, in the same clause, with no other
    noun (provisions, investment, costs, orders, volume, customers) between the metric and the word."""
    clause = _CLAUSE_BREAK.split(text[:at])[-1]
    words = list(re.finditer(r"\S+", clause))[-4:]
    window = clause[words[0].start():] if words else ""
    best = None
    for key, pattern in _METRICS:
        for m in re.finditer(rf"\b(?:{pattern})\b", window, re.I):
            if best is None or m.start() > best[1]:
                best = (key, m.start(), m.end())
    if best is None or _NOT_METRIC.search(window[best[2]:]):
        return None
    return best[0]


def _other_period_named(sentence: str, period: str | None) -> bool:
    """The sentence names a period other than the table's quarter and its comparison quarters (FY, 9M, H1, a year, another
    quarter): not judged against its row. "Revenue doubled YoY to ₹200 Cr in Q2FY27 from ₹100 Cr in Q2FY26" names the year-ago
    quarter, which is the table's own comparison, so it is judged (lead's review of #337)."""
    allowed = [p for q in (period, prior_year_period(period or ""), prior_quarter_period(period or "")) if q
               for p in _periods(q)[:1]]
    if not allowed:
        allowed = [None]
    return any(all(_differs_from(p, a) for a in allowed) for p in _periods(sentence))


_COLUMNS = re.compile(r"\b(?P<yoy>YoY|year[- ]on[- ]year|year[- ]ago)\b|\b(?P<qoq>QoQ|sequential(?:ly)?|quarter[- ]on[- ]quarter)\b", re.I)


def _row(results: dict, key: str) -> dict | None:
    row = results.get(key) or (results.get("pat_owners") if key == "pat" else None)
    return row if isinstance(row, dict) else None


def _multiple_wrong(word: str, sentence: str, at: int, row: dict) -> bool:
    w = " ".join(word.lower().split())
    loose = w.startswith(("nearly", "almost"))   # "nearly doubled" is true a little under +100%
    floor = (150.0 if loose else 190.0) if "tripl" in w else (75.0 if loose else 90.0)
    want = (lambda c: c <= -45.0) if w.startswith("halv") else (lambda c: c >= floor)
    clause, start = _clause_at(sentence, at)
    named = [(abs(m.start() - (at - start)), "yoy" if m.group("yoy") else "qoq") for m in _COLUMNS.finditer(clause)]
    column = min(named)[1] if named else "yoy"   # the column the text names nearest the word, else YoY alone
    change = row.get(f"{column}_pct")
    return isinstance(change, (int, float)) and not want(change)


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


def _bound_to_growth(sentence: str, m: re.Match) -> bool:
    """The pace word is about growth: "growth slowed", "growth of revenue accelerated to", "slowing growth", within a few words
    (lead's review of #326: "revenue grew 12% despite slowing demand" is about demand, not revenue's growth)."""
    before, after = sentence[:m.start()], sentence[m.end():]
    return bool(re.search(r"\bgrowth\b(?:\s+\S+){0,3}\s*$", before, re.I) or re.match(r"\s+(?:\S+\s+){0,1}growth\b", after, re.I))


_FALL = re.compile(r"\b(?:fell|fall(?:s|ing)?|declin\w*|drop\w*|down|lower|contract\w*|shr[ai]nk\w*|slump\w*)\b[^%]{0,15}$", re.I)
_FALL_AFTER = re.compile(r"\s*(?:decline|drop|fall|lower|contraction)\b", re.I)


def _outpace_wrong(sentence: str, at: int) -> bool:
    """The first growth figure is not above the second. The tokens carry no sign, so a fall on either side ("fell 5%,
    outperforming the industry's 10% decline") is not judged (lead's review of #326)."""
    pcts = [(pos, value, raw) for value, _d, pos, kind, raw in _tokens(sentence) if kind == "pct"]
    before = [(pos, v, raw) for pos, v, raw in pcts if pos < at]
    after = [(pos, v, raw) for pos, v, raw in pcts if pos > at]
    if not before or not after:
        return False

    def falls(pos: int, raw: str) -> bool:
        near = sentence[max(0, pos - 25):pos]
        rest = sentence[pos:pos + 25].split("%", 1)[-1]
        return raw.startswith("-") or bool(_FALL.search(near)) or bool(_FALL_AFTER.match(rest))

    (p1, v1, r1), (p2, v2, r2) = before[-1], after[0]
    if falls(p1, r1) or falls(p2, r2):
        return False
    return v1 <= v2


def _judge(text: str, results: dict, found: dict[tuple[str, str], float]) -> list[tuple[str, str]]:
    """(word, why) for each comparison word of ``text`` its figures contradict."""
    wrong = []
    for sentence in _SENTENCE.split(text.replace("**", "")):
        other_period = _other_period_named(sentence, results.get("period"))
        for m in ([] if other_period else _MULTIPLE.finditer(sentence)):
            key = _metric_before(sentence, m.start())
            row = _row(results, key) if key else None
            if row and _multiple_wrong(m.group(1), sentence, m.start(), row):
                wrong.append((m.group(1), f"{key} change YoY {row.get('yoy_pct')}%, QoQ {row.get('qoq_pct')}%"))
        for m in ([] if other_period else _PACE.finditer(sentence)):
            key = _metric_before(sentence, m.start())
            row = _row(results, key) if key else None
            if row and _bound_to_growth(sentence, m):
                previous = _previous_yoy(found, key, results.get("period"))
                if _pace_wrong(m.group(1), row, previous):
                    wrong.append((m.group(1), f"{key} YoY {row.get('yoy_pct')}% against the previous quarter's {previous:.1f}%"))
        for m in _OUTPACE.finditer(sentence):
            if _outpace_wrong(sentence, m.start()):
                wrong.append((m.group(1), "the first growth figure is not above the second"))
    return wrong


def _soften(text: str, word: str) -> str | None:
    soft = _SOFT.get(" ".join(word.lower().split()))   # "nearly  doubled" across two spaces or a line break
    if soft is None:
        return None
    return re.sub(rf"\b{re.escape(word)}\b", lambda m: soft.capitalize() if m.group(0)[0].isupper() else soft, text, count=1)


def apply_card_json(card_json: dict, dossier: dict | None = None) -> list[str]:
    """The checks on a stored or new card (a dict) with a results table; memory gives the previous quarter's YoY."""
    results = card_json.get("results")
    if not card_words_match_figures() or not isinstance(results, dict):
        return []
    from .dossier import _entry_basis

    # memory on the card's own basis only; a card with no basis takes nothing from memory, so its pace words are not judged
    # (lead's review of #326: a standalone previous quarter judged a consolidated card's "accelerated")
    basis = card_json.get("basis") or results.get("basis")
    found = {(m["metric"], m["period"]): m["value"] for m in (dossier or {}).get("financial_metrics") or []
             if basis and isinstance(m, dict) and m.get("period") and isinstance(m.get("value"), (int, float))
             and _entry_basis(m) == basis}
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
            softer = text
            for word, why in wrong:
                softer = _soften(softer, word) if softer is not None else None
                if softer is None:
                    break
            if wrong and softer is not None:   # the item keeps its other facts with the word softened (lead's review of #326)
                notes.append(f"{name}: '{wrong[0][0]}' softened in '{text[:80]}', the figures do not show it ({wrong[0][1]})")
                item = {**item, "text": softer} if isinstance(item, dict) else softer
            elif wrong:
                notes.append(f"{name}: dropped '{text[:80]}', '{wrong[0][0]}' is not what the figures show ({wrong[0][1]})")
                continue
            kept.append(item)
        card_json[name] = kept
    return notes
