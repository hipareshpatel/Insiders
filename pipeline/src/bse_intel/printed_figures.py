"""What the company itself prints in its results filing or press release: its own EBITDA and the profit line it
headlines (owner, 25 Oct 2026, TODO 11, 14, 15; F151).

Nothing here is read by a model. Each figure is found in the filing's text by a fixed pattern, comes with the line it
was found on (a quote that is in the text word for word), and is dropped when it cannot be read with certainty: the unit
unclear, the column not the quarter, a figure far from the one the exchange file gives. A printed figure that is
dropped means the card shows ours alone, never a guess.

Everything is behind `CARD_EBITDA_PROFIT_V2` (settings.card_ebitda_profit_v2); with it off, no caller reads this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import gate
from .grounding import unit_before

# the filing's EBITDA may be this far from ours (printed / ours) before it is taken for a unit slip or another
# measure altogether: a company's own EBITDA with other income in it is within a few per cent of ours, and a "Adjusted
# EBITDA" within a third; 10x and 100x slips and a segment's figure are far outside
BAND = (0.4, 2.5)

_AMOUNT = r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(crores?|crs?|million|mn|lakhs?|lacs?)(?![a-z])"
_NAME = (r"((?:adjusted\s+|operating\s+|consolidated\s+|reported\s+|underlying\s+|normali[sz]ed\s+|core\s+)*"
         r"ebitda(?!\s*(?:margin|%|/|per\b|\(%\)))(?:\s*\((?:[^)\d%]{0,30})\))?)")
_NUM = r"\(?-?[\d,]+(?:\.\d+)?\)?"
_ROW = re.compile(rf"^\s*(?:[-•*▪]\s*)?{_NAME}\s*[:|]?\s*((?:{_NUM}%?\s*[|,]?\s*){{1,9}})\s*$", re.I)
_PROSE = re.compile(rf"{_NAME}\s*(?:of|at|was|stood\s+at|came\s+in\s+at|grew\s+to|rose\s+to|increased\s+to|up\s+at|is|:)?\s*{_AMOUNT}", re.I)
_PRIOR = re.compile(rf"(?:from|against|compared\s+(?:to|with)|vs\.?|versus|as\s+against)\s+{_AMOUNT}", re.I)
_QUARTER = re.compile(r"\bQ([1-4])\s*[-']?\s*(?:FY)?\s*'?(\d{2,4})\b", re.I)
_PER_CRORE = {"crore": 1.0, "cr": 1.0, "million": 10.0, "mn": 10.0, "lakh": 100.0, "lac": 100.0}
_LINE_UNIT = re.compile(r"\b(?:in\s*)?(?:₹|rs\.?|inr)\s*(?:in\s*)?(crores?|crs?|million|mn|lakhs?|lacs?)\b", re.I)
_XBRL_LINE = re.compile(r"^\s*-\s*ebitda\b", re.I)


# --- the basis a printed figure is on (F154) -----------------------------------------------------------------
# A release that prints the group's and the company's own figures side by side must not have its "first sensible
# row" taken for the card's basis. Basis comes from the row's or sentence's own words, else from the nearest
# heading above it; none when neither says.

_CONS = re.compile(r"\bconsolidated\b|\bgroup\b|\bconsol\.?(?=\s|\b)", re.I)
_ALONE = re.compile(r"\bstand[- ]?alone\b|\bcompany[- ]alone\b|\bcompany'?s?\s+(?:own|alone)\b|\bon\s+a\s+(?:stand[- ]?alone)\b", re.I)
HEADING_LOOKBACK = 3000   # characters above a figure in which a heading may name its basis
_HEADING_MAX = 110        # a heading is a short line


def _words_basis(words: str) -> str | None:
    """CONSOLIDATED / STANDALONE when `words` name exactly one basis; None when none or both."""
    cons, alone = bool(_CONS.search(words)), bool(_ALONE.search(words))
    return "CONSOLIDATED" if cons and not alone else "STANDALONE" if alone and not cons else None


def basis_at(text: str, start: int, end: int) -> str | None:
    """The basis of the figure at text[start:end]: the words of its own line or sentence, else the nearest heading
    above it (a short line with no amount that names a basis; a table title)."""
    own_start = text.rfind("\n", 0, start) + 1
    own_end = text.find("\n", end)
    own_end = own_end if own_end >= 0 else len(text)
    # the sentence the figure is in, inside its line: a table row is its whole line
    bounds = [m.end() for m in re.finditer(r"[.;!?]\s+", text[own_start:start])]
    sentence_start = own_start + (bounds[-1] if bounds else 0)
    after = re.search(r"[.;!?]\s+(?=[A-Z])", text[end:own_end])
    sentence = text[sentence_start: end + after.start() if after else own_end]
    found = _words_basis(sentence)
    if found:
        return found
    if _CONS.search(sentence) and _ALONE.search(sentence):
        return None   # one sentence naming both: which one the figure is on is not told
    head = text[max(0, own_start - HEADING_LOOKBACK): own_start].splitlines()
    for line in reversed(head):
        line = line.strip()
        if not line or len(line) > _HEADING_MAX or re.search(r"(?:₹|rs\.?|inr)\s*[\d,]+", line, re.I):
            continue
        found = _words_basis(line)
        if found:
            return found
    return None


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= 0.005 * max(abs(a), abs(b)) + 0.011


def _one_value(values: list[float]) -> bool:
    """Whether every figure is the same value (to rounding): a release that prints one EBITDA twice has one."""
    return all(_same(v, values[0]) for v in values)


@dataclass
class PrintedEbitda:
    name: str                    # the company's own words: "EBITDA", "Adjusted EBITDA", "Operating EBITDA"
    value_cr: float
    prev_year_cr: float | None   # only when the filing prints it, by its own arithmetic (below)
    quote: str                   # the line or sentence it was found in, as printed
    yoy_printed: float | None = None   # the change the filing prints beside it, when it agrees with the two figures
    basis: str | None = None           # CONSOLIDATED / STANDALONE as the release's own words or heading say; None: not told

    def yoy_pct(self) -> float | None:
        return self.yoy_printed if self.prev_year_cr is not None else None


def _cr(number: str, unit: str) -> float:
    return float(number.replace(",", "")) / _PER_CRORE[unit.lower().rstrip("s")]


def _num(token: str) -> float:
    t = token.strip().rstrip("%")
    negative = t.startswith("(") or t.startswith("-")
    value = float(t.strip("()-").replace(",", ""))
    return -value if negative else value


def _name(raw: str) -> str:
    return " ".join(raw.split()).strip()


def _quarter_key(label: str) -> tuple[str, str] | None:
    m = _QUARTER.search(label or "")
    if not m:
        return None
    year = m.group(2)[-2:]
    return f"Q{m.group(1)}", year


def _header_ok(lines: list[str], at: int, period: str | None) -> bool:
    """When quarter labels head the table above this row, the first must be the card's quarter."""
    if not period:
        return True
    want = _quarter_key(period)
    for back in range(1, 9):
        if at - back < 0:
            break
        found = _QUARTER.findall(lines[at - back])
        if len(found) >= 2:
            first = _QUARTER.search(lines[at - back])
            return _quarter_key(first.group(0)) == want if want else True
    return True


def _row_unit(lines: list[str], at: int, text: str, offset: int) -> float | None:
    """Figures per crore for a table row: the row's own bracket, else the unit the page declared above it."""
    m = _LINE_UNIT.search(lines[at])
    if m:
        return _PER_CRORE[m.group(1).lower().rstrip("s")]
    return unit_before(text, offset)


def _prior_from_row(cells: list[str], current: float) -> tuple[float, float] | None:
    """The year-ago figure of a row: the cell whose change to this quarter's figure is the row's own printed YoY, to
    its rounding. A cell with no percentage that proves it is not taken (a row's other cells are the previous quarter,
    the half year, the full year)."""
    pcts = [_num(c) for c in cells if c.strip().endswith("%")]
    figures = [_num(c) for c in cells if not c.strip().endswith("%")][1:]
    for pct in pcts:
        for n in figures:
            if n > 0 and abs((current / n - 1) * 100 - pct) <= 0.15:
                return n, pct
    return None


_YEAR_WORDS = re.compile(r"year[- ]ago|\byoy\b|y-o-y|y/y|corresponding|(?:previous|last|prior)\s+(?:financial\s+)?year|\bQ[1-4]\s*FY\s*'?\d{2}\b|\bFY\s*'?\d{2}\b", re.I)
_SEQUENTIAL = re.compile(r"previous\s+quarter|preceding\s+quarter|sequential|\bqoq\b|q-o-q|last\s+quarter", re.I)


def _year_ago(words: str) -> bool:
    return bool(_YEAR_WORDS.search(words)) and not _SEQUENTIAL.search(words)


def printed_ebitda(text: str | None, period: str | None = None, ours: float | None = None,
                   basis: str | None = None) -> PrintedEbitda | None:
    """The company's own EBITDA for the quarter, from its filing's text; None when the text prints none or the one it
    prints cannot be read with certainty. `ours` (crore) is the figure the exchange file gives: a printed figure outside
    BAND of it is a unit slip or another measure, and is not shown. `basis` is the card's (CONSOLIDATED / STANDALONE): a
    printed figure on the other basis is never taken, one with no basis told is taken only when every EBITDA the release
    prints has the same value (F154); with no `basis` the first sensible figure is taken, as before."""
    if not text:
        return None
    lines = text.splitlines()
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    candidates: list[PrintedEbitda] = []

    for i, line in enumerate(lines):
        if _XBRL_LINE.match(line):
            continue
        m = _ROW.match(line)
        if not m:
            continue
        unit = _row_unit(lines, i, text, offsets[i])
        if unit != 1.0 or not _header_ok(lines, i, period):   # crore only: a converted figure is not on the page
            continue
        cells = re.findall(rf"{_NUM}%?", m.group(2))
        figures = [c for c in cells if not c.endswith("%")]
        if not figures:
            continue
        current = _num(figures[0])
        # the first cell is the quarter only when the row is a plain list of figures; a bare "EBITDA 12" is no row
        if len(figures) < 2 and not any(c.endswith("%") for c in cells):
            continue
        prev = _prior_from_row(cells, current)
        candidates.append(PrintedEbitda(_name(m.group(1)), round(current, 2), prev[0] if prev else None, line.strip(),
                                        prev[1] if prev else None, basis_at(text, offsets[i], offsets[i] + len(line))))

    for m in _PROSE.finditer(text):
        sentence_end = re.search(r"\.\s+[A-Z]|\n", text[m.end():m.end() + 200])
        tail = text[m.end(): m.end() + (sentence_end.start() if sentence_end else 200)]
        prior = _PRIOR.search(tail)
        if prior and not _year_ago(tail[:prior.end()] + " " + tail[prior.end(): prior.end() + 40]):
            prior = None   # "from ₹X in the previous quarter" is no year-ago figure
        start = max(text.rfind("\n", 0, m.start()) + 1, m.start() - 80)
        quote = " ".join(text[start: m.end() + (prior.end() if prior else 0)].split())
        if _PER_CRORE[m.group(3).lower().rstrip("s")] != 1.0 or (prior and _PER_CRORE[prior.group(2).lower().rstrip("s")] != 1.0):
            continue   # crore only: a figure converted from million or lakh is not the figure on the page
        value = _cr(m.group(2), m.group(3))
        before = _cr(prior.group(1), prior.group(2)) if prior else None
        printed_change = None
        if before and before > 0:
            gap = (value / before - 1) * 100
            shown = next((float(x) for _, x in re.findall(r"([+\-−]?)\s*(\d+(?:\.\d+)?)\s*%", quote)
                          if abs(float(x) - abs(gap)) <= 0.15), None)
            printed_change = None if shown is None else (shown if gap >= 0 else -shown)
        candidates.append(PrintedEbitda(_name(m.group(1)), round(value, 2), round(before, 2) if before else None, quote,
                                        printed_change, basis_at(text, m.start(), m.end() + (prior.end() if prior else 0))))

    usable = [c for c in candidates
              if not (ours is not None and ours > 0 and not BAND[0] <= c.value_cr / ours <= BAND[1])
              and c.value_cr != 0 and gate.quote_found(c.quote, text)]
    if basis:
        # the card's basis: a figure on it first; a figure with no basis told only when the release prints one value
        # (the group's and the company's own EBITDA differ, so two values with no label say nothing); never the other basis
        told = [c for c in usable if c.basis == basis]
        untold = [c for c in usable if c.basis is None]
        alone = _one_value([c.value_cr for c in usable])
        usable = told or (untold if alone else [])
    for c in usable:
        if c.prev_year_cr is not None and (c.prev_year_cr <= 0 or not 0.2 <= c.prev_year_cr / c.value_cr <= 5):
            c.prev_year_cr = None   # a year-ago figure far from this quarter's is not trusted as the same measure
        return c
    return None


# --- the profit line the company headlines -------------------------------------------------------------------

_PROFIT_NAME = (r"((?:adjusted\s+|consolidated\s+)?"
                r"(?:PAT|profit\s+after\s+tax|net\s+profit|profit\s+for\s+the\s+(?:period|quarter|year)|"
                r"(?:net\s+)?profit\s+attributable\s+to\s+(?:the\s+)?(?:owners|shareholders|equity\s+holders)[^,.;:\d₹]{0,30}|"
                r"PAT\s+attributable[^,.;:\d₹]{0,30}))")
_PROFIT = re.compile(rf"{_PROFIT_NAME}\s*(?:of|at|was|stood\s+at|came\s+in\s+at|grew\s+to|rose\s+to|jumped\s+to|increased\s+to|"
                     rf"declined\s+to|fell\s+to|is|:)?\s*{_AMOUNT}", re.I)
HEADLINE_WINDOW = 6000   # the headline is in the release's opening, not in its notes


@dataclass
class HeadlineProfit:
    label: str        # the company's words ("PAT", "Profit After Tax")
    value_cr: float
    metric: str | None   # "pat" / "pat_owners" when the amount is that exchange-file line; None when it is neither
    quote: str
    basis: str | None = None


def headline_profit(text: str | None, candidates: dict[str, float], basis: str | None = None) -> HeadlineProfit | None:
    """The profit line the filing's opening headlines, the first one it names with an amount. `candidates` are the
    exchange file's lines of this quarter (pat, pat_owners), crore. `metric` says which of them the amount is; an amount
    that is neither (an adjusted profit) comes back with metric None, so the caller knows the company headlines
    something the file does not give and falls back to the shareholders' profit. With the card's `basis` (F154) a profit
    on the other basis is skipped, and one with no basis told is taken only when every profit the opening names has the
    same value."""
    if not text:
        return None
    matches = [(m, basis_at(text, m.start(), m.end())) for m in _PROFIT.finditer(text[:HEADLINE_WINDOW])]
    if basis:
        own = [x for x in matches if x[1] == basis]
        untold = [x for x in matches if x[1] is None]
        matches = own or (untold if _one_value([_cr(x[0].group(2), x[0].group(3)) for x in matches]) else [])
    for m, found_basis in matches:
        value = _cr(m.group(2), m.group(3))
        metric = next((k for k, v in candidates.items() if v is not None
                       and abs(abs(v) - value) <= 0.005 * abs(value) + 0.011), None)
        start = max(text.rfind("\n", 0, m.start()) + 1, m.start() - 60)
        quote = " ".join(text[start: m.end()].split())
        if not gate.quote_found(quote, text):
            continue
        return HeadlineProfit(" ".join(m.group(1).split()), round(value, 2), metric, quote, found_basis)
    return None


def choose_profit(candidates: dict[str, float], text: str | None, basis: str | None = None) -> tuple[str | None, str | None]:
    """(metric, the company's label or None): the headline's line when the filing headlines one of the file's lines,
    else the profit attributable to shareholders (the line EPS is on), else profit for the period."""
    head = headline_profit(text, candidates, basis)
    if head is not None and head.metric is not None:
        return head.metric, head.label
    if candidates.get("pat_owners") is not None:
        return "pat_owners", None
    if candidates.get("pat") is not None:
        return "pat", None
    return None, None


_EBITDA_PROSE = re.compile(
    r"\bEBITDA\b[^.%\n]{0,40}?\b(increased|grew|rose|up|improved|declined|decreased|fell|down|dropped)\b[^.%\n]{0,25}?"
    r"(\d+(?:\.\d+)?)\s*%\s*(?:YoY|Y-o-Y|year[- ]on[- ]year|over the corresponding)", re.I)


def printed_ebitda_yoy(text: str | None) -> float | None:
    """The year-on-year change a release states for its EBITDA in words ("EBITDA increased 24.1% YoY to Rs. 205 Cr"), as a
    signed percentage; None when it states none or states two that differ (F155)."""
    found = {(-1 if m.group(1).lower() in ("declined", "decreased", "fell", "down", "dropped") else 1) * float(m.group(2))
             for m in _EBITDA_PROSE.finditer(text or "")}
    return found.pop() if len(found) == 1 else None
