"""Checks a card's words against its own code-built figures (wrong-card trace, 25 Oct 2026).

Of the 96 wrong points in the 48 WRONG cards of the 21-24 Oct daily audits, 36 were the writer's: the figure was in the
filing and in the card's own results table, and the words said the opposite. Sapphire Foods' headline "PAT turns
positive" over a table whose PAT row says the loss narrowed; CRISIL's growth "accelerated" from 25.7% to 20.2%. A second
reading of the filing would agree with both figures; what catches them is the card checked against itself.

Each check returns the sentences it faults with the reason; the pipeline drops a faulted point and sends a card whose
headline is faulted to review (as results_card.call_figure_conflicts)."""

from __future__ import annotations

import re

# a turn the words claim, and the results-table turns that bear it out
_TO_PROFIT = re.compile(r"\b(turns?|turned|swings?|swung|returns?|returned|back)\s+(to\s+)?(positive|profit|profitab\w*|"
                        r"black)\b|\bturn-?around\b|\bin\s+the\s+black\b", re.I)
_TO_LOSS = re.compile(r"\b(turns?|turned|swings?|swung|slips?|slipped|falls?|fell|plunges?|plunged)\s+(in)?to\s+(a\s+)?"
                      r"(net\s+)?loss\b|\bin\s+the\s+red\b", re.I)

# a line's direction in a short phrase: "PAT rises 12%", "revenue fell", "EBITDA down 8%"
_LINES = {"pat": r"(net\s+)?profit|pat|earnings", "revenue": r"revenue|sales|top[\s-]?line|income\s+from\s+operations",
          "ebitda": r"ebitda|operating\s+profit"}
_UP = r"ris\w*|rose|jump\w*|surg\w*|soar\w*|climb\w*|grow\w*|grew|up|higher|increas\w*|gain\w*|beat\w*"
_DOWN = r"fall\w*|fell|drop\w*|declin\w*|slump\w*|slid\w*|slip\w*|dip\w*|down|lower|decreas\w*|plung\w*|tumbl\w*|shrink\w*|shrank"
_SEQUENTIAL = re.compile(r"\b(qoq|q-o-q|sequential\w*|quarter[\s-]on[\s-]quarter|from\s+q[1-4])\b", re.I)
_YEARLY = re.compile(r"\b(yoy|y-o-y|year[\s-]on[\s-]year|a\s+year\s+(ago|earlier)|from\s+last\s+year)\b", re.I)
SMALL_MOVE = 2.0   # a change under this many per cent is "flat": no direction word is faulted against it

# "accelerated to 20.2% from 25.7%", "grew 20.2% against 25.7%": a direction between two figures the sentence states
_RISE_WORDS = r"accelerat\w*|quicken\w*|faster|ris\w*|rose|increas\w*|grew|higher|up|climb\w*|jump\w*"
_FALL_WORDS = r"decelerat\w*|slow\w*|moderat\w*|declin\w*|fell|fall\w*|lower|down|eas\w*|dropp?\w*|dipp?\w*"
_NUM = r"(-?\d[\d,]*(?:\.\d+)?)\s*(%|bps|x)?"
_FROM_TO = re.compile(rf"\b(?P<word>{_RISE_WORDS}|{_FALL_WORDS})\b[^.;:]{{0,40}}?\bto\s+(?:₹\s*)?{_NUM}[^.;:]{{0,30}}?"
                      rf"\bfrom\s+(?:₹\s*)?{_NUM}", re.I)
_TO_FROM = re.compile(rf"\b(?P<word>{_RISE_WORDS}|{_FALL_WORDS})\b[^.;:]{{0,40}}?\bfrom\s+(?:₹\s*)?{_NUM}[^.;:]{{0,30}}?"
                      rf"\bto\s+(?:₹\s*)?{_NUM}", re.I)
_VERSUS = re.compile(rf"\b(?P<word>{_RISE_WORDS}|{_FALL_WORDS})\b[^.;:]{{0,30}}?(?:₹\s*)?{_NUM}[^.;:]{{0,25}}?"
                     rf"\b(?:vs\.?|versus|against|compared\s+(?:with|to))\s+(?:₹\s*)?{_NUM}", re.I)


def _num(raw: str) -> float:
    return float(raw.replace(",", ""))


def turn_conflict(text: str, results: dict | None) -> str | None:
    """A turn to profit or to loss the words claim that the results table's PAT row does not show."""
    pat = (results or {}).get("pat") or {}
    now = pat.get("value")
    if not isinstance(now, (int, float)) or not text:
        return None
    turns = {pat.get("yoy_turn"), pat.get("qoq_turn")} - {None}
    if _TO_PROFIT.search(text) and now < 0:
        return f"says profit turned positive; the results table's PAT is a loss of ₹{abs(now):,.2f} Cr"
    if _TO_PROFIT.search(text) and turns and "LOSS_TO_PROFIT" not in turns:
        return "says profit turned positive; the results table shows no turn from a loss"
    if _TO_LOSS.search(text) and now >= 0:
        return f"says it turned to a loss; the results table's PAT is a profit of ₹{now:,.2f} Cr"
    return None


def direction_conflict(text: str, results: dict | None) -> str | None:
    """A line said to rise (or fall) whose results-table change goes the other way, by more than SMALL_MOVE, against
    every comparison the words could mean: the year-ago, and the previous quarter unless the words name the year."""
    if not results or not text:
        return None
    for key, names in _LINES.items():
        row = results.get(key)
        if not isinstance(row, dict):
            continue
        for word, sign in ((_UP, 1), (_DOWN, -1)):
            m = re.search(rf"\b({names})\b\W+(?:\w+\W+){{0,2}}?({word})\b", text, re.I)
            if not m:
                continue
            clause = text[m.start():m.end() + 40]
            slots = ("qoq_pct",) if _SEQUENTIAL.search(clause) else ("yoy_pct",) if _YEARLY.search(clause) \
                else ("yoy_pct", "qoq_pct")
            changes = [row.get(s) for s in slots if isinstance(row.get(s), (int, float))]
            if changes and all(c * sign < -SMALL_MOVE for c in changes):
                shown = ", ".join(f"{c:+.1f}%" for c in changes)
                return f"says {key} {'rose' if sign > 0 else 'fell'}; the results table has {shown}"
    return None


def comparison_conflict(text: str) -> str | None:
    """A direction word between two figures the sentence itself states that the figures contradict: "accelerated to
    20.2% from 25.7%", "growth slowed to 30% against 25%"."""
    for rx, current_first in ((_FROM_TO, True), (_VERSUS, True), (_TO_FROM, False)):
        for m in rx.finditer(text or ""):
            a, a_unit, b, b_unit = m.group(2), m.group(3), m.group(4), m.group(5)
            if (a_unit or "") != (b_unit or ""):
                continue   # 20% against ₹25 Cr: not one measure
            now, then = (_num(a), _num(b)) if current_first else (_num(b), _num(a))
            if now == then:
                continue
            rising = re.fullmatch(_RISE_WORDS, m.group("word"), re.I) is not None
            if rising != (now > then):
                return f"'{m.group('word')}' but {now:g} against {then:g}"
    return None


# "PAT more than doubled", "revenue tripled", "profit halved": a multiple the results-table change must bear out
_MULTIPLE = {r"more\s+than\s+doubl\w*|over\s+doubl\w*": (2.0, None), r"(?<!more than )doubl\w*": (1.85, 2.2),
             r"(more\s+than\s+)?tripl\w*": (2.75, None), r"halv\w*": (0.45, 0.55)}


def multiple_conflict(text: str, results: dict | None) -> str | None:
    """A line said to have doubled, tripled or halved whose results-table year-ago change is not that multiple (LMW's
    PAT "more than double" at +74%)."""
    if not results or not text:
        return None
    for key, names in _LINES.items():
        row = results.get(key)
        if not isinstance(row, dict) or not isinstance(row.get("yoy_pct"), (int, float)):
            continue
        ratio = 1 + row["yoy_pct"] / 100
        for words, (low, high) in _MULTIPLE.items():
            if re.search(rf"\b({names})\b\W+(?:\w+\W+){{0,3}}?({words})", text, re.I) \
                    and (ratio < low or (high is not None and ratio > high)):
                return f"says {key} {re.search(words, text, re.I).group(0)}; the results table has {row['yoy_pct']:+.1f}% YoY"
    return None


def conflicts(card: dict) -> dict:
    """{"headline": reason or None, "points": [(index, reason)]} for a card_json: the headline and each what_happened
    point checked against the card's results table and against the figures each sentence states."""
    results = card.get("results")

    def judge(text: str) -> str | None:
        return (turn_conflict(text, results) or direction_conflict(text, results) or multiple_conflict(text, results)
                or comparison_conflict(text))

    points = [(i, why) for i, p in enumerate(card.get("what_happened") or [])
              if isinstance(p, dict) and (why := judge(p.get("text") or ""))]
    return {"headline": judge(card.get("headline") or ""), "points": points}
