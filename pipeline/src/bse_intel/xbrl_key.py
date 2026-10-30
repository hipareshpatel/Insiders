"""The exchange's XBRL figures as a free answer key for the PDF reader (owner, 28 Oct 2026). Read only: no memory write, no card
change, no AI. It reads NSE (announcement lists and the results PDFs, through the PDF referee's own ``Sources``).

Why. Memory holds the exchange's XBRL figures for thousands of filings and they are right about 99% of the time. For each such
figure this module finds where it is printed on the filing's PDF page. That gives (a) a large labelled test set for every reader
(the row label, the column and the position of each figure) and (b) a list of filings where the XBRL figure is not on the page
though its row is: the cases where the file and the printed page really differ.

The locating core is a pure function: ``locate(pdf, expected)`` takes a PDF (path or bytes) and a list of ``Expected`` figures
(filing id, symbol, basis, period, metric, value) and returns one ``Result`` each. It knows nothing of NSE or memory, so it is
tested on made-up PDFs and on the hand answer keys (``docs/bench/hardpdf``, ``docs/bench/normalpdf``; the measured accuracy is in
``docs/bench/xbrlkey``).

How a figure is found (word positions, not text lines):

- every word of a page comes from PyMuPDF ``get_text("words")`` with its box; a page whose text runs up, down or upside down (a
  landscape table on a portrait page, a rotated scan) is turned so the text reads left to right (``upright_words``); the box of a
  result is the one the page gave, in the page's own coordinates;
- the words are put into rows by their vertical centre (the OCR line builder's rule); a row of figures with no label of its own
  (a label printed a few points off its figures) takes the nearest label-only row;
- a header is a row (or two rows next to each other) that is mostly dates, read with the pipeline's own date reader (``pdf_referee``
  date patterns, ``periods.explicit_date``; a date wrapped over two lines or split in two words is put back). Each date is a column
  and its header path is ``[basis >] parent heading > date``: the parent heading ("Quarter ended", "Half year ended", "Year
  ended") is read from the words above the dates, one a column or one over its run of columns (the cut that puts each heading over
  the middle of its own run; where the geometry cannot choose, the standard Indian layout, ``pdf_referee._pattern_kinds``, may,
  but only when the headings read agree with its runs). A heading that is missing, or that only the layout rule supplied, leaves the
  column *not proven*: the same date can head a quarter and a year, so such a column never gives ``found_unique``;
- every number token under a column is a cell: brackets for a negative, a minus sign that is its own token and a bracket that is
  its own token are joined; a figure a text layer cut in two words next to each other is put back ("12,31" "4.66" is 12,314.66,
  "7" "864.39" is 7,864.39, "10" "246" is 10,246, "(1" ".73)" is (1.73); ``_mend_numbers``); a figure with a stray dot or comma
  for its separator (an OCR layer: "5.58.271.46") is read once more with the separators repaired and marked ``repaired``;
- the unit is the last declaration above the row ("(Rs. in lakhs)", ``grounding._DECLARED_UNIT``); a figure is compared in that
  unit, within the larger of half a unit of its last printed digit and ₹0.006 Cr (memory keeps crore to two decimals); with no unit
  declared every unit is tried and the printed unit is marked ``?``;
- the basis (standalone or consolidated) is the nearest title above the table, or the words above the columns when the two
  sit side by side; a page with no title takes the previous page's, and a document that never says "consolidated" is
  standalone (``pdf_referee``'s rule).

A figure is a *placement* when its value matches a cell. It is *strong* when the cell's column is the period's column (the date and
the parent heading, read from the page) and its row label names the metric and its basis is the figure's basis. ``found_unique``
needs exactly one strong placement, where a row that repeats on another page with the same label and figures counts once, the same
row printed in a results statement and in a segment table is the statement's (the table that names three or more metrics), and
two lines of one table that print the same figure in the period's column are one figure (the lower line). Status:

- ``found_unique``: one strong placement;
- ``found_ambiguous``: two or more strong placements, or only placements that are not provably the right row, column heading or
  basis (``placements`` lists them with what failed); never a guess;
- ``row_found_other_value``: no cell holds the value, but the metric's row has a figure in the period's proven column (the basis
  proven): the printed number is ``other_value`` (a note when it equals the value in another unit);
- ``not_found``: no such cell and no such row in the period's column;
- ``no_text``: the document has no usable text layer (a scan), or its pages show no table of dates at all.

``failure_stage`` names, for every figure ``not_found`` (and an ambiguous one with no strong placement), the stage that lost it:
``not_in_text_layer`` (the number, in any printed unit, is nowhere in the document's words: the text layer or OCR is the problem),
``no_statement_page`` (it is in the words, but no table of dates was tied to the basis), ``unit_unknown`` (a table on the basis was
found, no unit line was read), ``in_text_wrong_place`` (it is in the words and a table exists, but not at a plausible row and
column).

No OCR in this version: a scanned page is ``no_text``. The words are plain boxes (left, top, right, bottom, text), so a later
version can feed the OCR engine's boxes through the same code (``Word``).

Arithmetic, as columns of the CSV and never a reason to change a value: where revenue, other income and total income are placed
in one column, revenue + other income should equal total income (``arith_income``); where total income, total expenses and PBT
are, total income - expenses should equal PBT, with exceptional items allowed for (``arith_pbt``). pass, fail or na.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from .grounding import _DECLARED_UNIT, _PER_CRORE
from .pdf_referee import (_BARE_UNIT, names_other_currency, _DATE_LOOSE_2, _GARBLED_UNIT, _MARCH_YEAR, _PAT_NAME_LETTERED,
                          _PAT_NOT, _TOTAL_INCOME, MAX_CANDIDATES, _basis_above_boxed, _date_of, _names, _pattern_kinds,
                          _revenue_rank, target_column)
from .metrics import CONSOLIDATED, STANDALONE

log = logging.getLogger(__name__)

# fetch_failed: a list or a download failed on the way (transport; read again next run); locate_error: the locator itself raised on a
# PDF it had (a bug or a damaged file: settled, so not downloaded again every dispatch; the exception class is in the note)
STATUSES = ("found_unique", "found_ambiguous", "row_found_other_value", "not_found", "no_text", "fetch_failed", "locate_error")
# Bump whenever placement logic changes (what counts as a column, a row, a basis, a unit, a statement table, a status): saved rows
# of another version are dropped on resume and their filings are read again.
LOCATOR_VERSION = "2026-10-30.1"
METRICS = ("revenue", "other_income", "total_income", "total_expenses", "exceptional_items", "pbt", "tax_expense", "pat", "eps",
           "interest_earned")
TOL_CR = 0.006              # memory keeps crore to two decimals: half a hundredth, with a little to spare
MAX_PAGES = 80
STATEMENT_METRICS = 3       # a table whose rows name this many different metrics is a results statement
MIN_NUMERIC_WORDS = 8       # fewer number words in the whole document: no text layer worth reading
ROW_TOLERANCE = 0.5         # a word joins a row whose centre is within this share of the smaller word's height (ocr.positioned_lines)
UNITS = {"crore": 1.0, "lakh": 100.0, "million": 10.0, "thousand": 10_000.0, "billion": 0.01}   # figures per ₹ crore
_UNIT_NAME = {v: k for k, v in UNITS.items()}
_ALL_UNITS = (1.0, 100.0, 10.0, 10_000.0)


# --- words, turned upright ----------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Word:
    """One word of a page in the upright frame (text reads left to right): its box and text, and the box as the page gave it."""
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    box: tuple = ()

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return max(self.y1 - self.y0, 1.0)


def quarter_turn(page) -> int:
    """How the page's text runs: 0 left to right, 1 up, 2 upside down, 3 down (PyMuPDF line directions, weighted by characters)."""
    weight = [0, 0, 0, 0]
    try:
        for block in page.get_text("dict", flags=0)["blocks"]:
            for line in block.get("lines", []):
                dx, dy = line["dir"]
                n = sum(len(s.get("text", "")) for s in line.get("spans", [])) or 1
                if abs(dx) >= abs(dy):
                    weight[0 if dx >= 0 else 2] += n
                else:
                    weight[1 if dy < 0 else 3] += n
    except Exception:   # noqa: BLE001 - no direction: upright
        return 0
    return max(range(4), key=lambda k: weight[k]) if sum(weight) else 0


def _turn_point(x: float, y: float, turn: int) -> tuple[float, float]:
    return ((x, y), (-y, x), (-x, -y), (y, -x))[turn]


def upright_words(page) -> tuple[list[Word], int]:
    """(the page's words with the text turned left to right, the turn). The turn is by the text's own direction, so a page that
    is rotated by its /Rotate flag and a page with text set sideways in its content come out the same."""
    turn = quarter_turn(page)
    words = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        if not str(text).strip():
            continue
        (ax, ay), (bx, by) = _turn_point(x0, y0, turn), _turn_point(x1, y1, turn)
        words.append(Word(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by), str(text), (x0, y0, x1, y1)))
    return words, turn


# --- numbers ------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Num:
    value: float
    decimals: int
    repaired: bool = False


_MINUS = "-−–—"
_OPEN = ("(", "(-", "(−", "(–", "-", "−", "–", "—", "[")
_CLOSE = (")", ")-", "]", ")*")


def _grouped(integer: str) -> bool:
    """Digits grouped by thousands (1,234,567) or the Indian way (12,34,567), or not grouped at all."""
    parts = integer.split(",")
    if len(parts) == 1:
        return parts[0].isdigit()
    if not (1 <= len(parts[0]) <= 3 and parts[0].isdigit()) or not all(p.isdigit() for p in parts[1:]):
        return False
    return all(len(p) == 3 for p in parts[1:]) or (len(parts[-1]) == 3 and all(len(p) == 2 for p in parts[1:-1]))


def parse_number(text: str) -> Num | None:
    """The number a token prints, or None. Brackets or a minus (before or after) make it negative; a separator an OCR layer got
    wrong ("5.58.271.46", "11,45,137,09") is read again with the separators repaired and marked."""
    t = text.strip().rstrip("*#^@†")
    if not t or t.endswith("%"):
        return None
    negative = False
    if t.startswith("(") :
        negative, t = True, t[1:]
        t = t[:-1] if t.endswith(")") else t
    elif t.endswith(")") and "(" not in t:
        negative, t = True, t[:-1]
    t = t.strip().strip("[]").strip()
    if t and t[0] in _MINUS:
        negative, t = True, t[1:].strip()
    if t.endswith("-") and len(t) > 1:
        negative, t = True, t[:-1]
    if not t or not t[0].isdigit() and not (t[0] == "." and len(t) > 1 and t[1].isdigit()):
        return None
    if not re.fullmatch(r"[\d,.]+", t):
        return None
    repaired = False
    if t.count(".") >= 2:                                  # dots for thousands: "5.58.271.46"
        head, _, tail = t.rpartition(".")
        t, repaired = head.replace(".", ",") + "." + tail, True
    if "." in t:
        integer, _, frac = t.partition(".")
        if not frac.isdigit() or not (_grouped(integer) or integer == ""):
            return None
    else:
        integer, frac = t, ""
        if "," in t and not _grouped(t):
            head, _, tail = t.rpartition(",")             # a comma for the decimal point: "11,45,137,09"
            if len(tail) == 2 and _grouped(head):
                integer, frac, repaired = head, tail, True
            else:
                return None
    digits = integer.replace(",", "") or "0"
    if not digits.isdigit():
        return None
    value = float(f"{digits}.{frac or '0'}")
    return Num(-value if negative else value, len(frac), repaired)


@dataclass
class Fig:
    """A number token (joined from its pieces) with its box in the upright frame and as the page gave it."""
    text: str
    num: Num
    x0: float
    y0: float
    x1: float
    y1: float
    box: tuple

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


def _union(words: list[Word]) -> tuple[float, float, float, float, tuple]:
    boxes = [w.box for w in words if w.box]
    box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)) if boxes else ()
    return (min(w.x0 for w in words), min(w.y0 for w in words), max(w.x1 for w in words), max(w.y1 for w in words), box)


_NEG = "(\\-\u2212\u2013"
_HEAD_DIGITS = re.compile(rf"^[{_NEG}]?\d{{1,3}}$")                              # "7", "10", "(2": the front of a grouped number
_GROUP_TAIL = re.compile(r"^,?\d{3}(?:\.\d+)?\)?$")                             # "246", ",459.29", "864.39": its last group
_CUT_GROUP = re.compile(rf"^[{_NEG}]?\d{{1,3}}(?:,\d{{2,3}})*,\d{{1,2}}$")        # "12,31": cut inside its last group
_CUT_TAIL = re.compile(r"^\d{1,2}(?:\.\d+)?\)?$")                                # "4.66": the rest of that group, then the decimals
_HEAD_DOT = re.compile(rf"^[{_NEG}]?[\d,]*\d\.?$")                               # "(1", "41", "(0.": a number ending where the point is
_TAIL_DOT = re.compile(r"^\.?\d+\)?$")                                         # ".73)", "12", "13)": the decimals
_NUMBERING = re.compile(r"^\(?(?:\d{1,2}\.|[A-Za-z]|[ivxIVX]{1,4})\)?\.?$|^\(\d{1,2}\)$")   # "2.", "(a)", "iv", "(2)": a line number
_MEND_GAP = 0.5      # the words' gap, in their heights: a space is 0.3, a figure's neighbour column is far more


def _mend_numbers(ordered: list[Word]) -> list[Word]:
    """A figure a text layer cut into two words put back in one, only when the two pieces sit a space apart and nothing else would
    make a number of them: the thousands separator lost between a head of one to three digits and a last group of three
    (Kirloskar "10" "246", WeWork "7" "864.39", Ashok Leyland ",459.29" after "51"), a group cut in its middle ("12,31" "4.66"
    printed 12,314.66, which read alone is 12.31), a decimal point split off ("(1" ".73)", "41" ".12", "(0." "13)"). The joined text
    must be a number as printed, not one an OCR separator repair makes; the words' boxes are joined."""
    out: list[Word] = []
    i = 0
    while i < len(ordered):
        a = ordered[i]
        b = ordered[i + 1] if i + 1 < len(ordered) else None
        joined = None
        # a lone line number ("2." "(a)" "iv") with no label word before it, then a figure: "2." "123" is a line number and a
        # figure, not 2.123
        numbering = bool(_NUMBERING.match(a.text)) and not any(re.search(r"[A-Za-z]{3}", w.text) for w in ordered[:i])
        if b is not None and not numbering and 0 <= b.x0 - a.x1 <= _MEND_GAP * max(a.h, b.h) \
                and abs(a.yc - b.yc) <= 0.5 * max(a.h, b.h):
            if _HEAD_DIGITS.match(a.text) and _GROUP_TAIL.match(b.text):
                joined = a.text + ("" if b.text.startswith(",") else ",") + b.text
            elif _CUT_GROUP.match(a.text) and _CUT_TAIL.match(b.text):
                joined = a.text + b.text
            elif (a.text.endswith(".") and _HEAD_DOT.match(a.text) and _TAIL_DOT.match(b.text)) or \
                    (b.text.startswith(".") and _HEAD_DOT.match(a.text) and _TAIL_DOT.match(b.text)):
                joined = a.text + b.text
        num = parse_number(joined) if joined else None
        if num is not None and not num.repaired:
            x0, y0, x1, y1, box = _union([a, b])
            out.append(Word(x0, y0, x1, y1, joined, box))
            i += 2
        else:
            out.append(a)
            i += 1
    return out


def figures_in(words: list[Word]) -> tuple[list[Fig], list[Word]]:
    """(the number tokens of a row, the words that are not part of one). A bracket or a minus that is its own word is joined to
    the number next to it, a closing bracket too; a figure the text layer cut in two is put back (``_mend_numbers``)."""
    ordered = _mend_numbers(sorted(words, key=lambda w: w.x0))
    figs: list[Fig] = []
    rest: list[Word] = []
    i = 0
    while i < len(ordered):
        w = ordered[i]
        group = [w]
        nxt = ordered[i + 1] if i + 1 < len(ordered) else None
        if w.text in _OPEN and nxt is not None and nxt.x0 - w.x1 < 1.2 * w.h and parse_number(nxt.text) is not None:
            group.append(nxt)
        elif parse_number(w.text) is not None and nxt is not None and nxt.text in _CLOSE and nxt.x0 - w.x1 < 1.2 * w.h:
            group.append(nxt)
        text = "".join(g.text for g in group)
        num = parse_number(text)
        if num is not None and (len(group) == 1 or parse_number(group[-1].text) is not None or group[-1].text in _CLOSE):
            x0, y0, x1, y1, box = _union(group)
            figs.append(Fig(text, num, x0, y0, x1, y1, box))
            i += len(group)
        else:
            rest.append(w)
            i += 1
    return figs, rest


# --- rows ---------------------------------------------------------------------------------------------------------

@dataclass
class Row:
    idx: int
    yc: float
    h: float
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in sorted(self.words, key=lambda w: w.x0))


def build_rows(words: list[Word]) -> list[Row]:
    """The words in rows, top to bottom, by the vertical centre (ocr.positioned_lines' rule: a word joins a row whose running
    centre is within half the smaller height of its own, looking at the last few rows)."""
    rows: list[dict] = []
    for w in sorted(words, key=lambda w: (w.yc, w.x0)):
        home = None
        for r in rows[-3:]:
            if abs(w.yc - r["yc"]) <= ROW_TOLERANCE * min(w.h, r["h"]):
                home = r
        if home is None:
            rows.append({"yc": w.yc, "h": w.h, "words": [w]})
        else:
            home["words"].append(w)
            n = len(home["words"])
            home["yc"] += (w.yc - home["yc"]) / n
            home["h"] += (w.h - home["h"]) / n
    return [Row(i, r["yc"], r["h"], sorted(r["words"], key=lambda w: w.x0)) for i, r in enumerate(rows)]


# --- headers: dates, kinds, bases --------------------------------------------------------------------------------

@dataclass
class DateTok:
    day: date
    x0: float
    x1: float
    text: str

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


def _spans(words: list[Word]) -> tuple[str, list[tuple[int, int, Word]]]:
    text, spans = "", []
    for w in words:
        start = len(text) + (1 if text else 0)
        text += (" " if text else "") + w.text
        spans.append((start, len(text), w))
    return text, spans


def _box_of(spans, a: int, b: int) -> tuple[float, float]:
    hit = [w for s, e, w in spans if s < b and e > a]
    return min(w.x0 for w in hit), max(w.x1 for w in hit)


def _mend_dates(words: list[Word]) -> list[Word]:
    """A date a text layer split in two or three words ("31" ".03.2026", "30." "09" ".2026") put back in one."""
    out: list[Word] = []
    i = 0
    while i < len(words):
        for n in (3, 2):
            group = words[i:i + n]
            if len(group) == n and all(b.x0 - a.x1 < 1.2 * a.h for a, b in zip(group, group[1:])):
                joined = "".join(w.text for w in group)
                if _DATE_LOOSE_2.fullmatch(joined) and not any(_DATE_LOOSE_2.fullmatch(w.text) for w in group):
                    out.append(Word(min(w.x0 for w in group), min(w.y0 for w in group), max(w.x1 for w in group),
                                    max(w.y1 for w in group), joined))
                    i += n
                    break
        else:
            out.append(words[i])
            i += 1
    return out


_MONTH_COMMA = re.compile(r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,$", re.I)


def _month_commas(words: list[Word]) -> list[Word]:
    """"Jun," "30" "2026": the comma a header prints after the month (Styrenix's "Jun, 30 2026") taken off, so the date reader, which
    knows "Jun 30, 2026", reads the column. Boxes stay as they are."""
    return [replace(w, text=w.text[:-1]) if _MONTH_COMMA.match(w.text) else w for w in words]


def row_dates(row: Row) -> list[DateTok]:
    text, spans = _spans(_mend_dates(_month_commas(row.words)))
    out = []
    for m in _DATE_LOOSE_2.finditer(text):
        # "30 September 30 June": the 30 after the month is the next date's day, not a two-digit year
        if re.match(r"\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", text[m.end():], re.I) and re.search(r"[ -]\d{2}$", m[0]):
            continue
        day = _date_of(m[0], True)
        if day:
            x0, x1 = _box_of(spans, m.start(), m.end())
            out.append(DateTok(day, x0, x1, m[0]))
    return out


_DAY_MONTH = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?[ -]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?(?![ ,-]*\d)", re.I)
_YEAR_WORD = re.compile(r"^20\d{2}$")


def stacked_dates(row: Row, below: Row | None) -> list[DateTok]:
    """Dates printed over two lines: "30 September" on the row, "2026" under it (a cell that wrapped). Each day and month is paired
    with the year word nearest its centre on the next row, only when the row has as many year words as day-months, one each."""
    if below is None:
        return []
    text, spans = _spans(_mend_dates(_month_commas(row.words)))
    found = [(m, _box_of(spans, m.start(), m.end())) for m in _DAY_MONTH.finditer(text)]
    years = [w for w in below.words if _YEAR_WORD.match(w.text)]
    if not found or len(years) != len(found):
        return []
    out = []
    for (m, (x0, x1)), w in zip(found, sorted(years, key=lambda w: w.xc)):
        if abs(w.xc - (x0 + x1) / 2) > 3 * max(row.h, 8) * 3:
            return []
        day = _date_of(f"{m[0]} {w.text}", True)
        if day is None:
            return []
        out.append(DateTok(day, min(x0, w.x0), max(x1, w.x1), f"{m[0]} {w.text}"))
    return out


_KIND = re.compile(r"(?P<half>half[\s-]*year(?:ly)?|six\s+months?|6\s+months?)|(?P<nine>nine\s+months?|9\s+months?)"
                   r"|(?P<year>year\s+ended|year\s+to\s+date|twelve\s+months?|12\s+months?|\byear\b|\bannual\b)"
                   r"|(?P<quarter>quarter|three\s+months?|3\s+months?)", re.I)
_BASIS_WORD = re.compile(r"\b(?P<cons>consolidated)\b|\b(?P<alone>stand[- ]?alone)\b", re.I)
_TITLE_ROW = re.compile(r"statement\s+of|results\s+for|financial\s+results", re.I)


@dataclass
class Column:
    day: date
    kind: str | None
    kind_how: str
    x0: float
    x1: float
    text: str
    basis: str | None = None      # only when the two bases sit side by side in the header

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def proven(self) -> bool:
        """The parent heading was read from the page's words (one per column, or one over its run of columns)."""
        return self.kind is not None and self.kind_how in ("words", "span", "words+layout")

    def title(self) -> str:
        """The full header path: [basis >] parent heading > date. A heading the layout rule supplied is marked, a missing one too."""
        heading = {"quarter": "Quarter ended", "half": "Half year ended", "nine": "Nine months ended", "year": "Year ended"}.get(self.kind or "")
        if heading is None:
            heading = "[no heading]"
        elif self.kind_how == "duplicate":
            heading += " [date repeated in the table]"
        elif not self.proven:
            heading += " [layout]"
        path = [heading, f"{self.day:%d.%m.%Y}"]
        if self.basis:
            path.insert(0, self.basis.capitalize())
        return " > ".join(path)


@dataclass
class Table:
    first: int                    # first header row
    last: int                     # last header row
    end: int                      # last row of the table (the row before the next header, or the page's last)
    columns: list[Column]
    basis: str | None = None
    basis_how: str = ""
    number: int = 0
    n_metrics: int = 0            # distinct metrics named by the table's rows: a results statement has several, a segment table one
    segment: bool = False         # a heading just above the table names segments
    discontinued: bool = False    # a line just above the table says it is about a discontinued operation


def _date_row(row: Row, below: Row | None = None) -> tuple[list[DateTok], bool]:
    """(the dates of a row that is mostly dates (a header cell row), whether the next row's years were used); a title or a
    paragraph that names a date has words besides."""
    dates, used = row_dates(row), False
    if not dates and (dates := stacked_dates(row, below)):
        used = True
    letters = sum(1 for w in row.words if re.search(r"[A-Za-z]{2}", w.text) and not _DATE_LOOSE_2.fullmatch(w.text)
                  and not _DAY_MONTH.fullmatch(w.text))
    letters -= sum(len(_DAY_MONTH.findall(row.text)) * 2 for _ in [0]) if used else 0
    return (dates if 3 * len(dates) >= max(letters, 0) else []), used


def _headers(rows: list[Row]) -> list[tuple[int, int, list[DateTok]]]:
    """Header row runs: a row that is mostly dates, joined to another such row within three rows of it with no figures between;
    a run needs two or more dates in different places."""
    out: list[tuple[int, int, list[DateTok]]] = []
    for r in rows:
        dates, used = _date_row(r, rows[r.idx + 1] if r.idx + 1 < len(rows) else None)
        if not dates:
            continue
        last = r.idx + 1 if used else r.idx          # the year row under a wrapped date is part of the header
        if out and r.idx - out[-1][1] <= 3 and all(not figures_in(rows[k].words)[0] for k in range(out[-1][1] + 1, r.idx)):
            out[-1] = (out[-1][0], last, out[-1][2] + dates)
        else:
            out.append((r.idx, last, list(dates)))
    return [h for h in out if len({(d.day, round(d.xc)) for d in h[2]}) >= 2]


def _kinds(region: list[Row], dates: list[DateTok], march_year_end: bool) -> tuple[list[str | None], str]:
    """(the kind of each date, how it was told): one group word a column in order, the standard layout when the dates fit it
    exactly, else the nearest group word's span; None where nothing says."""
    groups = []
    for r in region:
        text, spans = _spans(r.words)
        for m in _KIND.finditer(text):
            x0, x1 = _box_of(spans, m.start(), m.end())
            groups.append((m.lastgroup, (x0 + x1) / 2, r.idx))
    groups.sort(key=lambda g: g[1])
    ordered = sorted(range(len(dates)), key=lambda k: dates[k].xc)
    n = len(dates)
    kinds: list[str | None] = [None] * n
    if groups and len(groups) == n:
        for k, g in zip(ordered, groups):
            kinds[k] = g[0]
        return kinds, "words"
    if groups and 1 < len(groups) < n <= 12:
        # fewer headings than dates: the dates in x order are cut into one run a heading, in order; the cut that puts each
        # heading nearest the middle of its own run wins, and only when it clearly beats the next best (a heading is printed
        # over its run, and a run is as many columns as the page gave it)
        from itertools import combinations

        gap = min((dates[b].xc - dates[a].xc for a, b in zip(ordered, ordered[1:]) if dates[b].xc - dates[a].xc > 1), default=60.0)
        scored = []
        for cuts in combinations(range(1, n), len(groups) - 1):
            bounds = (0, *cuts, n)
            runs = [ordered[i:j] for i, j in zip(bounds, bounds[1:])]
            cost = 0.0
            for g, run in zip(groups, runs):
                lo, hi = min(dates[k].x0 for k in run), max(dates[k].x1 for k in run)
                if not lo - 0.5 * gap <= g[1] <= hi + 0.5 * gap:
                    cost = None
                    break
                cost += abs(g[1] - sum(dates[k].xc for k in run) / len(run))
            if cost is not None:
                scored.append((cost, runs))
        scored.sort(key=lambda c: c[0])
        if scored and (len(scored) == 1 or scored[1][0] >= 2 * scored[0][0] + 0.2 * gap):
            for g, run in zip(groups, scored[0][1]):
                for k in run:
                    kinds[k] = g[0]
            return kinds, "span"
    elif groups and len(groups) == 1:
        lo, hi = min(d.x0 for d in dates), max(d.x1 for d in dates)
        if lo <= groups[0][1] <= hi:
            return [groups[0][0]] * n, "span"
    pattern = _pattern_kinds([dates[k].day for k in ordered], march_year_end)
    if pattern:
        for k, p in zip(ordered, pattern):
            kinds[k] = p
        # the headings the page prints, in order, are the standard layout's runs in the same order: the words and the dates
        # agree on where each heading's columns are (the geometry alone cannot cut "3 + 2 + 1" from "2 + 3 + 1")
        runs = [p for i, p in enumerate(pattern) if i == 0 or p != pattern[i - 1]]
        if groups and [g[0] for g in groups] == runs:
            return kinds, "words+layout"
        return kinds, "layout"
    return kinds, "unknown"


def _table_columns(rows: list[Row], first: int, last: int, dates: list[DateTok], page_text: str, floor: int) -> list[Column]:
    region = [r for r in rows[max(floor, first - 4): last + 2]
              if not _TITLE_ROW.search(r.text) and (r.idx >= first or not _has_figures(r))]
    kinds, how = _kinds(region, dates, bool(_MARCH_YEAR.search(page_text)))
    bases = []
    for r in region:
        text, spans = _spans(r.words)
        for m in _BASIS_WORD.finditer(text):
            x0, x1 = _box_of(spans, m.start(), m.end())
            bases.append((CONSOLIDATED if m.lastgroup == "cons" else STANDALONE, (x0 + x1) / 2))
    side = len({b for b, _ in bases}) == 2
    cols = []
    for tok, kind in sorted(zip(dates, kinds), key=lambda p: p[0].xc):
        col = Column(tok.day, kind, how if kind else "unknown", tok.x0, tok.x1, tok.text)
        if side:
            col.basis = min(bases, key=lambda b: abs(b[1] - tok.xc))[0]
        cols.append(col)
    return cols


def _has_figures(row: Row) -> bool:
    figs, _ = figures_in(row.words)
    return sum(1 for f in figs if "." in f.text or len(re.sub(r"\D", "", f.text)) >= 4) >= 2


# --- metric rows --------------------------------------------------------------------------------------------------

_NUMBERING = re.compile(r"^[\W_]*(?:\(?(?:[ivx]{1,4}|[a-z]|\d{1,2})[.)]\s*|\b(?:[ivx]{1,4}|\d{1,2})\s+)", re.I)
_OTHER_INCOME = re.compile(r"^other\s+income\b(?!.*comprehensive)", re.I)
_TOTAL_REVENUE = re.compile(r"^total\s+revenue\b(?!\s+from\s+operations)", re.I)
_TOTAL_EXPENSES = re.compile(r"^total\s+expen(?:ses|diture)\b", re.I)
_EXCEPTIONAL = re.compile(r"^(?:add\W*|less\W*|\(?add\)?\W*)?exceptional\s+items?\b", re.I)
_PBT = re.compile(r"(?:profit|loss|income)\b[^\d]{0,40}?\bbefore\s+(?:income\s+)?tax(?:es)?\b", re.I)
_PBT_NOT = re.compile(r"before\s+(?:exceptional|extraordinary|share\s+of|non[- ]?controlling|minority|associate)|discontinued|"
                      r"per\s+share|margin|%|segment", re.I)
_TAX = re.compile(r"^(?:total\s+)?(?:income\s+)?tax\s+expenses?\b(?!.*(?:relating|reclass))|^provision\s+for\s+(?:income\s+)?tax(?:ation)?\b|"
                  r"^total\s+tax\b|^tax\s*\(?(?:net|credit|expenses?)?\)?\s*$", re.I)
_EPS_LABEL = re.compile(r"\bbasic\b|^(?:earnings?\s+per\s+(?:equity\s+)?share|eps)\b", re.I)


def _stripped(label: str) -> str:
    out = re.sub(r"^[^A-Za-z0-9]*[A-H]\s+(?=[A-Z][a-z])", "", label.strip())      # "G Profit for the Period (E-F)"
    for _ in range(2):
        out = _NUMBERING.sub("", out, count=1).strip()
    return out


DISCONTINUED_SEPARATE = {"exceptional_items", "tax_expense"}   # printed again for the discontinued business, under its own heading
_DISCONTINUED = re.compile(r"discontinu", re.I)
_CONTINUING = re.compile(r"\bcontinu(?:ing|ed)\b", re.I)


def _in_discontinued(label: str, inside: bool) -> bool:
    """Whether the lines from this one are the discontinued business's: a line that names discontinued operations opens that part
    of a results statement (Aditya Birla Real Estate's "DISCONTINUED OPERATIONS" heading, or its line 12 "Profit before tax from
    discontinued operations"), a line that names continuing operations (and not discontinued, nor both) closes it. Its exceptional
    item (the ₹868.12 Cr gain on the pulp and paper sale) and its tax (₹(73.38) Cr) are not the company's continuing ones."""
    if _DISCONTINUED.search(label):
        return not re.search(r"continuing\s*(?:and|&|\+)|(?:and|&|\+)\s*discontinu", label, re.I)
    if _CONTINUING.search(label):
        return False
    return inside


def classify(label: str) -> set[str]:
    """The metrics a row label names (usually one): the PDF referee's own label patterns where it has them."""
    core = _stripped(label)
    out: set[str] = set()
    rank = _revenue_rank(core)
    if rank == 0 or (rank is None and core and re.match(r"^(?:total\s+)?revenue\s+from\s+operations", core, re.I)):
        out.add("revenue")
    elif rank == 1:
        out.add("interest_earned")
    elif rank == 2 or _TOTAL_REVENUE.search(core):
        out.add("total_income")
    if _OTHER_INCOME.search(core):
        out.add("other_income")
    if _TOTAL_EXPENSES.search(core):
        out.add("total_expenses")
    if _EXCEPTIONAL.search(core):
        out.add("exceptional_items")
    if _PBT.search(core) and not _PBT_NOT.search(core):
        out.add("pbt")
    if _TAX.search(core):
        out.add("tax_expense")
    if _PAT_NAME_LETTERED.search(core) and not _PAT_NOT.search(core) and "pbt" not in out:
        out.add("pat")
    if _EPS_LABEL.search(core) and not re.match(r"^diluted\b", core, re.I):
        out.add("eps")
    if "total_income" in out and not _TOTAL_INCOME.search(core) and not _TOTAL_REVENUE.search(core):
        out.discard("total_income")
    return out


# --- a page, as a model of tables and cells ----------------------------------------------------------------------

@dataclass
class Cell:
    page: int
    table: Table
    col: Column
    col_index: int
    row: Row
    fig: Fig
    label: str
    metrics: set
    unit: float | None             # figures per crore, None when no unit is declared above
    unit_how: str                  # page, previous page, document, none
    basis: str | None
    basis_how: str
    turn: int

    def key(self) -> tuple:
        return (self.page, self.table.number, self.col_index)


@dataclass
class DocModel:
    pages: int = 0
    numeric_words: int = 0
    scanned_pages: int = 0
    tables: int = 0
    cells: list[Cell] = field(default_factory=list)
    unit_declared: bool = False
    numbers: list = field(default_factory=list)       # (page, Num) of every number token of the text layer, in a table or not
    table_list: list = field(default_factory=list)


def _declared_unit(text: str) -> float | None:
    m = _DECLARED_UNIT.search(text)
    if m:
        word = next((g for g in m.groups() if g), None)
        if word:
            return _PER_CRORE.get(word.lower().rstrip("s"))
    if names_other_currency(text):
        return None
    probe = re.sub(r"^[^\w]+|[^\w.)]+$", "", text.strip())
    if len(probe) <= 40 and (m := _BARE_UNIT.match(probe)):
        return _PER_CRORE.get(m[1].lower().rstrip("s.").rstrip("s"))
    if len(text.strip()) <= 70 and (m := _GARBLED_UNIT.match(text.strip())):
        return _PER_CRORE.get(m[1].lower().rstrip("s"))
    return None


def _columns_for(table: Table, fig: Fig) -> int | None:
    """The column a figure sits under: the most overlap with a header date's span, else the nearest centre within half a column
    gap; None when it is between two (not trusted) or outside the table."""
    cols = table.columns
    gaps = [b.xc - a.xc for a, b in zip(cols, cols[1:]) if b.xc - a.xc > 1]
    gap = min(gaps) if gaps else 60.0
    scored = []
    for k, c in enumerate(cols):
        overlap = min(fig.x1, c.x1) - max(fig.x0, c.x0)
        scored.append((overlap, -abs(fig.xc - c.xc), k))
    scored.sort(reverse=True)
    best = scored[0]
    if best[0] > 0:
        if len(scored) > 1 and scored[1][0] > 0 and scored[1][0] >= 0.8 * best[0]:
            return None
        return best[2]
    near = sorted(range(len(cols)), key=lambda k: abs(fig.xc - cols[k].xc))
    d0 = abs(fig.xc - cols[near[0]].xc)
    if d0 > 0.55 * gap:
        return None
    if len(near) > 1 and abs(fig.xc - cols[near[1]].xc) - d0 < 0.25 * gap:
        return None
    return near[0]


def _label_of(words: list[Word]) -> str:
    return " ".join(w.text for w in sorted(words, key=lambda w: w.x0)).strip()


def analyse_page(words: list[Word], turn: int, page_no: int, carried: dict, doc_consolidated: bool,
                 table_count: int) -> tuple[list[Cell], dict, list[Table]]:
    """The cells of one page. ``carried`` holds what the previous page left (its last basis and unit); every number token of the
    page goes to ``carried["numbers"]`` (the text layer's own numbers, for the failure stage of a figure not found)."""
    rows = build_rows(words)
    carried.setdefault("numbers", []).extend((page_no, f.num) for r in rows for f in figures_in(r.words)[0])
    page_text = "\n".join(r.text for r in rows)
    headers = _headers(rows)
    tables: list[Table] = []
    for n, (first, last, dates) in enumerate(headers):
        end = (headers[n + 1][0] - 1) if n + 1 < len(headers) else len(rows) - 1
        floor = headers[n - 1][1] + 1 if n else 0
        t = Table(first, last, end, _table_columns(rows, first, last, dates, page_text, floor), number=table_count + n)
        repeated = Counter((c.day, c.kind) for c in t.columns if c.proven and c.basis is None)
        for c in t.columns:
            if c.proven and c.basis is None and repeated[(c.day, c.kind)] > 1:
                # two columns of one table with the same date and heading, no basis between them: the page (or its text layer)
                # misprints one (Styrenix's third column reads "Jun 30, 2026" in the text layer, "2025" on the page), so neither
                # column can prove a figure
                c.kind_how = "duplicate"
        t.segment = any(re.search(r"\bsegment", rows[k].text, re.I) for k in range(max(floor, first - 6), first))
        t.discontinued = any(_in_discontinued(rows[k].text, False) for k in range(max(floor, first - 4), first))
        lines = [r.text for r in rows]
        basis, contested = _basis_above_boxed(lines, first)
        if basis:
            t.basis, t.basis_how = basis, "title"
        elif not contested and carried.get("basis"):
            t.basis, t.basis_how = carried["basis"], "previous page"
        elif not contested and not doc_consolidated:
            t.basis, t.basis_how = STANDALONE, "no consolidated anywhere"
        tables.append(t)
        carried["basis"] = t.basis or carried.get("basis")
    declared = [(r.idx, u) for r in rows if (u := _declared_unit(r.text)) is not None]
    cells: list[Cell] = []
    for t in tables:
        body = rows[t.last + 1: t.end + 1]
        info = []
        for r in body:
            figs, rest = figures_in(r.words)
            placed = [(f, k) for f in figs if (k := _columns_for(t, f)) is not None]
            info.append((r, placed, _label_of(rest)))
        reach = 1.8 * max(r.h for r, _, _ in info) if info else 0
        label_only = [(r, label) for r, placed, label in info if not placed and re.search(r"[A-Za-z]{3}", label)]
        attached: dict[int, list[tuple[Row, str]]] = {}
        for r, label in label_only:
            options = [(abs(r2.yc - r.yc), r2.idx) for r2, placed2, label2 in info
                       if placed2 and not re.search(r"[A-Za-z]{3}", label2) and abs(r2.yc - r.yc) <= reach]
            if options:
                attached.setdefault(min(options)[1], []).append((r, label))
        discontinued = t.discontinued
        for r, placed, label in info:
            discontinued = _in_discontinued(label, discontinued)
            if not placed:
                continue
            if re.search(r"[A-Za-z]{3}", label):
                candidates = [label]
            else:
                # a row of figures with no label of its own takes the nearest label-only row; the label-only rows together are
                # its label when that one names no metric (a label wrapped over two lines). Never the union of them: "Other
                # income" next to "Total income" must not make the row both.
                near = sorted(attached.get(r.idx, []), key=lambda p: abs(p[0].yc - r.yc))
                candidates = [near[0][1]] if near else []
                if len(near) > 1:
                    candidates.append(" ".join(l2 for _, l2 in sorted(near, key=lambda p: p[0].yc)))
            shown = next((c for c in candidates if classify(c)), candidates[0] if candidates else "")
            metrics = classify(shown) if candidates else set()
            if discontinued:
                metrics = metrics - DISCONTINUED_SEPARATE   # the discontinued business's own exceptional item and tax
            above = [u for i, u in declared if i <= r.idx]
            unit, how = (above[-1], "page") if above else (carried.get("unit"), "previous page" if carried.get("unit") else "none")
            for f, k in placed:
                col = t.columns[k]
                basis = col.basis or t.basis
                cells.append(Cell(page_no, t, col, k, r, f, shown, metrics, unit, how, basis,
                                  "columns" if col.basis else t.basis_how, turn))
    if declared:
        carried["unit"] = declared[-1][1]
    return cells, carried, tables


def read_pdf(source, max_pages: int = MAX_PAGES) -> DocModel:
    """The model of a PDF (path or bytes): every page's tables and cells. Never raises on a damaged file: an empty model."""
    import pymupdf

    model = DocModel()
    try:
        doc = pymupdf.open(stream=source, filetype="pdf") if isinstance(source, (bytes, bytearray)) else pymupdf.open(str(source))
    except Exception:   # noqa: BLE001
        return model
    try:
        model.pages = doc.page_count
        pages = []
        for i in range(min(doc.page_count, max_pages)):
            page = doc[i]
            words, turn = upright_words(page)
            numeric = sum(1 for w in words if re.search(r"\d", w.text))
            model.numeric_words += numeric
            if len(words) < 30 and page.get_images():
                model.scanned_pages += 1
            pages.append((i + 1, words, turn))
    finally:
        doc.close()
    doc_consolidated = any(_names(" ".join(w.text for w in words), "consolidated") for _, words, _ in pages)
    carried: dict = {}
    for page_no, words, turn in pages:
        if not words:
            continue
        cells, carried, tables = analyse_page(words, turn, page_no, carried, doc_consolidated, model.tables)
        model.tables += len(tables)
        model.table_list += tables
        model.cells += cells
    model.numbers = carried.get("numbers", [])
    for t in model.table_list:
        t.n_metrics = len({m for c in model.cells if c.table is t for m in c.metrics})
    first_unit = next((c.unit for c in model.cells if c.unit_how == "page"), None)
    model.unit_declared = first_unit is not None
    if first_unit is not None:
        for c in model.cells:
            if c.unit is None:
                c.unit, c.unit_how = first_unit, "document"
    return model


# --- matching ------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Expected:
    """One figure to find: the filing it belongs to (its XBRL source id), the company, the basis, the period (Q2FY27, FY26),
    the metric and its value (₹ crore, or ₹ for EPS)."""
    news_id: str
    symbol: str
    basis: str
    period: str
    metric: str
    value: float
    tol_cr: float = TOL_CR


@dataclass
class Placement:
    page: int
    value: float                   # the printed value in its printed unit
    text: str
    unit: str
    row_label: str
    column: str
    bbox: tuple
    fit: str                       # strong, or what failed: row, column, basis
    repaired: bool = False
    turn: int = 0
    key: tuple = ()
    per_crore: float = 1.0

    def as_dict(self) -> dict:
        return {"page": self.page, "text": self.text, "unit": self.unit, "label": self.row_label[:80], "column": self.column,
                "fit": self.fit, **({"repaired": True} if self.repaired else {})}


@dataclass
class Result:
    expected: Expected
    status: str
    page: int | None = None
    printed_value: float | None = None
    printed_text: str = ""
    printed_unit: str = ""
    row_label: str = ""
    column_header: str = ""
    bbox: tuple = ()
    other_value: str = ""
    placements: list = field(default_factory=list)
    n_strong: int = 0
    note: str = ""
    arith_income: str = "na"
    arith_pbt: str = "na"
    arith_note: str = ""
    reading: str = ""
    failure_stage: str = ""
    reason: str = ""               # found_ambiguous only: segment_only, unit_not_declared, multiple_strong, or what failed (not_row ...)
    cell_key: tuple = ()
    printed_cr: float | None = None
    half_unit_cr: float = 0.0


def _target(period: str) -> tuple[str, date] | None:
    if m := re.fullmatch(r"(H1|9M)FY(\d{2})", period):
        year = 2000 + int(m[2])
        return ("half", date(year - 1, 9, 30)) if m[1] == "H1" else ("nine", date(year - 1, 12, 31))
    return target_column(period)


def _column_state(col: Column, target: tuple[str, date] | None) -> str:
    """``ok``: the date and the parent heading (read from the page's words) are the period's; ``heading``: the date is, the
    heading is missing, inferred from the standard layout or the same only by layout (the column is not proven: the same date can
    head a quarter and a year); ``wrong``: another date or another heading."""
    if target is None or col.day != target[1]:
        return "wrong"
    if col.kind is not None and col.kind != target[0]:
        return "wrong"
    return "ok" if col.proven else "heading"


def _matches(expected: Expected, fig: Fig, per_crore: float) -> bool:
    if expected.metric == "eps":
        return abs(fig.num.value - expected.value) <= max(0.011, 0.5 * 10 ** -fig.num.decimals + 1e-9)
    half = 0.5 * 10 ** -fig.num.decimals / per_crore
    return abs(fig.num.value / per_crore - expected.value) <= max(expected.tol_cr, half) + 1e-9


def _unit_label(per_crore: float | None, assumed: bool) -> str:
    return ("?" if assumed else "") + (_UNIT_NAME.get(per_crore, "") if per_crore else "")


def _basis_fit(cell: Cell, expected: Expected) -> str:
    if cell.basis is None:
        return "unknown"
    return "same" if cell.basis == expected.basis else "other"


def _dedupe(placements: list[tuple[Placement, Cell, tuple]]) -> list[tuple[Placement, Cell, tuple]]:
    """A row that repeats on another page with the same label, column and figures (the statement printed twice in a filing) is one
    placement: the first."""
    seen, out = set(), []
    for p, cell, signature in placements:
        if signature in seen:
            continue
        seen.add(signature)
        out.append((p, cell, signature))
    return out


def _row_signature(cells: list[Cell], cell: Cell) -> tuple:
    same_row = [c for c in cells if c.row is cell.row and c.table is cell.table]
    figs = tuple(sorted((c.col_index, c.fig.text) for c in same_row))
    return (_stripped(cell.label).lower()[:60], cell.basis, cell.col.day, cell.col.kind, cell.col_index, figs)


def locate_in(model: DocModel, expected: list[Expected]) -> list[Result]:
    """The result for each expected figure against a read PDF (``read_pdf``)."""
    by_row: dict[int, list[Cell]] = {}
    for c in model.cells:
        by_row.setdefault(id(c.row), []).append(c)
    results = []
    for e in expected:
        target = _target(e.period)
        res = Result(e, "not_found")
        results.append(res)
        if model.numeric_words < MIN_NUMERIC_WORDS:
            res.status, res.note = "no_text", "no usable text layer"
            continue
        found: list[tuple[Placement, Cell, tuple]] = []
        rows_seen: list[tuple[Cell, Fig]] = []
        for c in model.cells:
            basis = _basis_fit(c, e)
            if basis == "other":
                continue
            row_ok = e.metric in c.metrics
            col_state = _column_state(c.col, target)
            col_ok = col_state == "ok"
            if row_ok and col_ok and basis == "same":
                rows_seen.append((c, c.fig))
            units = (c.unit,) if c.unit else _ALL_UNITS
            if e.metric == "eps":
                units = (1.0,)
            for per_crore in units:
                if not _matches(e, c.fig, per_crore):
                    continue
                fit = "strong" if row_ok and col_ok and basis == "same" else "+".join(
                    n for n, ok in (("row", row_ok), ("heading" if col_state == "heading" else "column", col_ok),
                                    ("basis", basis == "same")) if not ok)
                fit = fit if fit == "strong" else "not " + fit
                unit = _unit_label(None if e.metric == "eps" else per_crore, c.unit is None and e.metric != "eps")
                p = Placement(c.page, c.fig.num.value, c.fig.text, unit, c.label, c.col.title(), c.fig.box, fit,
                              c.fig.num.repaired, c.turn, c.key(), per_crore)
                found.append((p, c, _row_signature(by_row.get(id(c.row), [c]), c)))
                break
        found = _dedupe(found)
        strong = [x for x in found if x[0].fit == "strong"]
        res.n_strong = len(strong)
        res.placements = [x[0].as_dict() for x in found][:12]
        # the same row in a results statement and in a segment table (or a summary) is one figure printed twice: the placement in
        # the table that names several metrics is the statement's, when it is the only such
        statement = [x for x in strong if x[1].table.n_metrics >= STATEMENT_METRICS and not x[1].table.segment]
        chosen, how = None, ""
        if len(strong) > 1 and len(statement) == 1:
            chosen = statement[0]
            how = f"also printed in another table on page {', '.join(str(g) for g in sorted({x[0].page for x in strong if x is not chosen}))}"
        elif len(strong) == 1:
            chosen = strong[0]
        elif len(strong) > 1 and len({x[1].table.number for x in strong}) == 1 and len({x[1].col_index for x in strong}) == 1 \
                and len({x[0].per_crore for x in strong}) == 1 and len({x[0].value for x in strong}) == 1:
            # two lines of one table name the metric ("Profit after tax", "Profit for the period") and print the same figure in
            # the period's column: one figure, listed twice; the lower line (the bottom line) is the placement
            chosen = max(strong, key=lambda x: x[1].row.yc)
            how = "also on the line " + " / ".join(f"'{x[1].label[:40]}'" for x in strong if x is not chosen) + " of the same table"
        if chosen is not None:
            p, cell, _ = chosen
            if cell.table.n_metrics < STATEMENT_METRICS or cell.table.segment:
                # the only proven placement is in a segment or summary table, not the results statement
                fill(res, p, cell, "found_ambiguous")
                res.reason = "segment_only"
                res.note = (f"segment_only: the table {'has a segment heading' if cell.table.segment else ''}"
                            f"{' and ' if cell.table.segment and cell.table.n_metrics < STATEMENT_METRICS else ''}"
                            f"{f'names only {cell.table.n_metrics} metric(s)' if cell.table.n_metrics < STATEMENT_METRICS else ''}")
            elif p.unit.startswith("?") and e.metric != "eps":
                fill(res, p, cell, "found_ambiguous")
                res.reason = "unit_not_declared"
                res.note = "unit_not_declared: no unit line was read, every unit was tried"
            else:
                fill(res, p, cell, "found_unique")
                res.note = "; ".join(x for x in (res.note, how) if x)
        elif found:
            best = strong[0] if strong else found[0]
            fill(res, best[0], best[1], "found_ambiguous")
            res.reason = "multiple_strong" if strong else found[0][0].fit.replace(" ", "_")
            res.note = (f"{len(strong)} strong placements" if strong else
                        f"value printed, but {found[0][0].fit}" + (f" ({len(found)} places)" if len(found) > 1 else ""))
        elif rows_seen:
            cell, fig = rows_seen[0]
            res.status = "row_found_other_value"
            res.other_value = fig.text
            res.page, res.printed_value, res.printed_text = cell.page, fig.num.value, fig.text
            res.printed_unit = _unit_label(None if e.metric == "eps" else cell.unit, cell.unit is None)
            res.row_label, res.column_header, res.bbox = cell.label, cell.col.title(), _bbox(fig, cell.turn)
            res.note = _other_unit_note(e, cell, fig)
            if len({(c.page, c.fig.text) for c, _ in rows_seen}) > 1:
                res.note = (res.note + "; " if res.note else "") + f"{len(rows_seen)} cells in the row and column"
        elif model.tables == 0:
            res.note = "no table of dates in the text layer"
            if model.scanned_pages:
                res.status, res.note = "no_text", f"{model.scanned_pages} scanned page(s), no table of dates in the text layer"
        elif not any(e.metric in c.metrics for c in model.cells):
            res.note = "no row for the metric"
            if model.scanned_pages:
                res.status, res.note = "no_text", f"{model.scanned_pages} scanned page(s) and no row for the metric"
        else:
            res.note = "a row for the metric, none under the period's column on the basis"
        if res.status in ("not_found", "no_text"):
            res.failure_stage = failure_stage(model, e)
        elif res.status == "found_ambiguous" and not strong:
            res.failure_stage = "in_text_wrong_place"
    check_arithmetic(results, model)
    return results


FAILURE_STAGES = ("not_in_text_layer", "no_statement_page", "unit_unknown", "in_text_wrong_place")


def in_text_layer(model: DocModel, e: Expected) -> bool:
    """The value, in any printed unit (crore, lakh, million, thousand; EPS as it is), is one of the text layer's number tokens."""
    for _, num in model.numbers:
        fig = Fig("", num, 0, 0, 0, 0, ())
        if any(_matches(e, fig, per) for per in ((1.0,) if e.metric == "eps" else _ALL_UNITS)):
            return True
    return False


def failure_stage(model: DocModel, e: Expected) -> str:
    """Why a figure was not found, the stage that lost it, in this order:

    - ``not_in_text_layer``: the number appears nowhere in the document's words in any printed unit, so the text layer (or the
      OCR a later version adds) is the problem;
    - ``no_statement_page``: it is in the words, but no table of dates was tied to the figure's basis, so its page was not found;
    - ``unit_unknown``: a table on the basis was found but no unit line could be read for it;
    - ``in_text_wrong_place``: it is in the words and a table on the basis exists with its unit, but the number is not at a
      plausible row and column."""
    if not in_text_layer(model, e):
        return "not_in_text_layer"
    cells = [c for c in model.cells if c.basis in (e.basis, None)]
    if not cells:
        return "no_statement_page"
    if e.metric != "eps" and not any(c.unit_how == "page" or c.unit_how == "previous page" for c in cells):
        return "unit_unknown"
    return "in_text_wrong_place"


def _point_lost(e: Expected, cell: Cell, fig: Fig) -> bool:
    """The printed token is the figure with its decimal point lost ("827" for 8.27: Techno Electric's scanned page, whose text layer
    dropped the dot of every EPS)."""
    if fig.num.decimals or not e.value:
        return False
    per = 1.0 if e.metric == "eps" else (cell.unit or 1.0)
    return abs(abs(fig.num.value) / per - abs(e.value) * 100) <= 0.5 / per + 1e-9 and abs(e.value) * 100 >= 10


def _other_unit_note(e: Expected, cell: Cell, fig: Fig) -> str:
    if _point_lost(e, cell, fig):
        return f"equals the value with its decimal point lost (the text layer prints '{fig.text}')"
    if e.metric == "eps":
        return ""
    for per_crore in _ALL_UNITS:
        if per_crore != cell.unit and _matches(e, fig, per_crore):
            return f"equals the value if printed in {_UNIT_NAME[per_crore]} (page declares {_UNIT_NAME.get(cell.unit, 'no unit')})"
    return ""


def _bbox(fig: Fig, turn: int) -> tuple:
    return tuple(round(v, 1) for v in fig.box) if fig.box else ()


def fill(res: Result, p: Placement, cell: Cell, status: str) -> None:
    res.status = status
    res.page, res.printed_value, res.printed_text, res.printed_unit = p.page, p.value, p.text, p.unit
    res.row_label, res.column_header, res.bbox = p.row_label, p.column, tuple(round(v, 1) for v in p.bbox)
    res.cell_key = p.key
    if res.expected.metric != "eps":
        res.printed_cr = p.value / p.per_crore
        res.half_unit_cr = 0.5 * 10 ** -cell.fig.num.decimals / p.per_crore
    res.reading = "repaired" if p.repaired else ""
    if cell.basis_how and cell.basis_how not in ("title", "columns"):
        res.note = (res.note + "; " if res.note else "") + f"basis from {cell.basis_how}"
    if cell.unit_how != "page" and res.expected.metric != "eps":
        res.note = (res.note + "; " if res.note else "") + f"unit from {cell.unit_how}"


def check_arithmetic(results: list[Result], model: DocModel | None = None) -> None:
    """Revenue + other income = total income, and total income - expenses = PBT (exceptional items allowed for), among the
    figures placed uniquely in one column of one table. A check on the locating, never a reason to change a value."""
    groups: dict[tuple, dict[str, Result]] = {}
    for r in results:
        if r.status == "found_unique" and r.printed_cr is not None and r.cell_key:
            groups.setdefault((r.expected.news_id, r.expected.basis, r.expected.period, r.cell_key), {})[r.expected.metric] = r
    for g in groups.values():
        def tol(*rs: Result) -> float:
            return TOL_CR + sum(r.half_unit_cr for r in rs)

        if all(k in g for k in ("revenue", "other_income", "total_income")):
            rev, oi, ti = g["revenue"], g["other_income"], g["total_income"]
            ok = abs(rev.printed_cr + oi.printed_cr - ti.printed_cr) <= tol(rev, oi, ti)
            for r in (rev, oi, ti):
                r.arith_income = "pass" if ok else "fail"
                if not ok:
                    r.arith_note = (r.arith_note + "; " if r.arith_note else "") + \
                        f"revenue {rev.printed_cr:g} + other income {oi.printed_cr:g} != total income {ti.printed_cr:g}"
        if all(k in g for k in ("total_income", "total_expenses", "pbt")):
            ti, te, pbt = g["total_income"], g["total_expenses"], g["pbt"]
            gap = ti.printed_cr - te.printed_cr - pbt.printed_cr
            allowed = [0.0]
            if "exceptional_items" in g:
                ex = g["exceptional_items"].printed_cr
                allowed += [ex, -ex]
            parts = (ti, te, pbt) + ((g["exceptional_items"],) if "exceptional_items" in g else ())
            ok = any(abs(gap - a) <= tol(*parts) for a in allowed)
            for r in (ti, te, pbt, *([g["exceptional_items"]] if "exceptional_items" in g else [])):
                r.arith_pbt = "pass" if ok else "fail"
                if not ok:
                    r.arith_note = (r.arith_note + "; " if r.arith_note else "") + \
                        f"total income {ti.printed_cr:g} - expenses {te.printed_cr:g} != PBT {pbt.printed_cr:g}"


def locate(source, expected: list[Expected], max_pages: int = MAX_PAGES) -> list[Result]:
    """The pure core: where each expected figure is printed in the PDF (path or bytes)."""
    return locate_in(read_pdf(source, max_pages), expected)


# --- from memory ---------------------------------------------------------------------------------------------------

def expected_from_dossier(dossier: dict | None, symbol: str = "") -> dict[str, list[Expected]]:
    """The XBRL figures of memory by filing period (``Q2FY27``): for each basis, the machine-tagged figures of ``METRICS``
    (``metrics._figures``: the ``xbrl:`` sources), each tied to the id of the file that stated it. Only crore money lines and EPS
    in rupees; any other unit is left out, never rescaled."""
    from .metrics import _figures, _value_source

    out: dict[str, list[Expected]] = {}
    for basis in (CONSOLIDATED, STANDALONE):
        figures, _ = _figures(dossier or {}, basis)
        for (metric, period), entry in figures.items():
            if metric not in METRICS or entry.get("value") is None:
                continue
            unit = str(entry.get("unit") or "")
            if (metric == "eps") != (unit == "INR") or (metric != "eps" and unit != "INR_CR"):
                continue
            sid = _value_source(entry)
            m = re.fullmatch(r"xbrl:res(?:-sa)?:[^:]*:(Q[1-4]FY\d{2})", sid)
            if not m:
                continue
            out.setdefault(m[1], []).append(Expected(sid, symbol, basis, period, metric, float(entry["value"])))
    return out


# --- the run ---------------------------------------------------------------------------------------------------------

CSV_HEADER = ("news_id,symbol,basis,period,metric,xbrl_value,status,reason,page,printed_value,printed_text,printed_unit,row_label,"
              "column_header,bbox,other_value,n_strong,placements,arith_income,arith_pbt,arith_note,reading,failure_stage,note,locator_version,pdf_url,"
              "pdf_news_id,filing_period").split(",")


def _cell(v) -> str:
    """A CSV cell; a float keeps every digit (``{:g}`` kept six: 58187.57 crore was written 58187.6, so a key built from the CSV
    scored a right reading wrong)."""
    return "" if v is None else repr(v) if isinstance(v, float) else str(v)


def result_row(r: Result, extra: dict | None = None) -> dict:
    e = r.expected
    row = {"news_id": e.news_id, "symbol": e.symbol, "basis": e.basis, "period": e.period, "metric": e.metric,
           "xbrl_value": e.value, "status": r.status, "reason": r.reason, "page": r.page, "printed_value": r.printed_value,
           "printed_text": r.printed_text, "printed_unit": r.printed_unit, "row_label": r.row_label[:120],
           "column_header": r.column_header, "bbox": " ".join(f"{v:g}" for v in r.bbox), "other_value": r.other_value,
           "n_strong": r.n_strong, "placements": json.dumps(r.placements, ensure_ascii=False) if r.placements else "",
           "arith_income": r.arith_income, "arith_pbt": r.arith_pbt, "arith_note": r.arith_note, "reading": r.reading,
           "failure_stage": r.failure_stage, "note": r.note, "locator_version": LOCATOR_VERSION}
    row.update(extra or {})
    return row


def to_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for r in rows:
        writer.writerow([_cell(r.get(k)) for k in CSV_HEADER])
    return buffer.getvalue()


_NUMERIC = {"xbrl_value": float, "printed_value": float, "page": int, "n_strong": int}


def load_csv(text: str) -> list[dict]:
    """The rows of a CSV this module wrote, the numeric fields as numbers again (a row read back is formatted and counted like a
    fresh one; an empty or unreadable cell is None)."""
    rows = list(csv.DictReader(io.StringIO(text)))
    for r in rows:
        for key, kind in _NUMERIC.items():
            try:
                r[key] = kind(float(r[key])) if r.get(key) not in (None, "") else None
            except (TypeError, ValueError):
                r[key] = None
    return rows


def _g(v) -> str:
    """A number for the report whatever it came as (a float, a string read from a CSV, nothing)."""
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return "" if v is None else str(v)


def summarise(rows: list[dict], calls: dict, filings: int, blocked: bool = False, out_of_time: bool = False,
              capped: bool = False) -> dict:
    by_status = Counter(r["status"] for r in rows)
    by_metric: dict[str, Counter] = {}
    by_basis: dict[str, Counter] = {}
    for r in rows:
        by_metric.setdefault(r["metric"], Counter())[r["status"]] += 1
        by_basis.setdefault(r["basis"], Counter())[r["status"]] += 1
    arith = Counter()
    for r in rows:
        for k in ("arith_income", "arith_pbt"):
            if r.get(k) in ("pass", "fail"):
                arith[f"{k}_{r[k]}"] += 1
    stages = Counter(r["failure_stage"] for r in rows if r.get("failure_stage"))
    stages_by_metric: dict[str, Counter] = {}
    for r in rows:
        if r.get("failure_stage"):
            stages_by_metric.setdefault(r["metric"], Counter())[r["failure_stage"]] += 1
    reasons = Counter(r["reason"] for r in rows if r.get("reason"))
    failed = {(r["symbol"], r.get("filing_period", "")) for r in rows if r["status"] == "fetch_failed"}
    others = [r for r in rows if r["status"] == "row_found_other_value"]
    notes = Counter(re.sub(r"[\d.,]+", "<n>", r.get("note") or "") for r in rows if r["status"] in ("not_found", "no_text", "found_ambiguous"))
    return {"figures": len(rows), "filings": filings, "calls": calls, "blocked": blocked, "out_of_time": out_of_time,
            "file_cap_reached": capped, "fetch_failed_filings": len(failed),
            "statuses": {s: by_status.get(s, 0) for s in STATUSES}, "ambiguous_reasons": dict(reasons.most_common()),
            "failure_stages": {k: stages.get(k, 0) for k in FAILURE_STAGES},
            "failure_stages_by_metric": {k: dict(v) for k, v in sorted(stages_by_metric.items())},
            "by_metric": {k: dict(v) for k, v in sorted(by_metric.items())},
            "by_basis": {k: dict(v) for k, v in sorted(by_basis.items())}, "arithmetic": dict(arith),
            "other_value_examples": [{k: r.get(k) for k in ("news_id", "symbol", "basis", "period", "metric", "xbrl_value",
                                                            "other_value", "row_label", "column_header", "page", "note")}
                                     for r in others[:25]],
            "why_not_unique": dict(notes.most_common(12))}


def to_json(summary: dict) -> str:
    return json.dumps(summary, ensure_ascii=False, indent=1) + "\n"


def to_markdown(summary: dict, date_text: str) -> str:
    s = summary["statuses"]
    total = max(1, summary["figures"])
    out = [f"# XBRL key, {date_text}", "",
           "Read only: the exchange's XBRL figures held in memory, each looked for on its filing's PDF page by word position "
           "(`xbrl_key.py`). No OCR: a scanned page is `no_text`. A figure is `found_unique` only when exactly one cell fits "
           "the period's column, a row label naming the metric and the basis; `found_ambiguous` lists the placements; "
           "`row_found_other_value` is a row with a different figure in the period's column (the cases where file and page may "
           "really differ). Memory is not written and no card changes.", "",
           f"{summary['figures']} figures of {summary['filings']} filings; {summary['calls']['lists']} announcement lists and "
           f"{summary['calls']['pdfs']} PDFs fetched.", ""]
    if summary["blocked"] or summary["out_of_time"] or summary["file_cap_reached"]:
        why = "NSE refused the session" if summary["blocked"] else "time budget" if summary["out_of_time"] else "file cap reached"
        out += [f"The run stopped early ({why}); what it read is here and the rest waits for the next run.", ""]
    if summary.get("fetch_failed_filings"):
        out += [f"{summary['fetch_failed_filings']} filings could not be fetched (an announcement list or a download failed): their "
                "rows are `fetch_failed`, not `not_found`, and a rerun with the same progress name reads them again.", ""]
    if summary["statuses"].get("locate_error"):
        out += [f"{summary['statuses']['locate_error']} figures hit an error inside the locator (`locate_error`, the exception class "
                "is in the note): settled, not downloaded again until the locator changes.", ""]
    out += ["## Status", "", "| status | figures | share |", "|---|---|---|"]
    out += [f"| {k} | {v} | {v / total:.1%} |" for k, v in s.items()]
    out += ["", "## Status per metric", "", "| metric | " + " | ".join(STATUSES) + " |", "|---|" + "---|" * len(STATUSES)]
    out += [f"| {k} | " + " | ".join(str(v.get(x, 0)) for x in STATUSES) + " |" for k, v in summary["by_metric"].items()]
    if summary.get("ambiguous_reasons"):
        out += ["", "## Why found_ambiguous", ""] + [f"- {k}: {n}" for k, n in summary["ambiguous_reasons"].items()]
    if any(summary["failure_stages"].values()):
        out += ["", "## Which stage lost the figures not found", "",
                "`not_in_text_layer`: the number is nowhere in the page words (text layer or OCR); `no_statement_page`: no table "
                "was tied to the basis; `unit_unknown`: no unit line read; `in_text_wrong_place`: in the words, not at a plausible "
                "row and column.", ""]
        out += [f"- {k}: {n}" for k, n in summary["failure_stages"].items()]
    if summary["arithmetic"]:
        out += ["", "## Arithmetic check of the locating", ""] + [f"- {k}: {n}" for k, n in sorted(summary["arithmetic"].items())]
    if summary["other_value_examples"]:
        out += ["", "## Row found, another value printed (first 25)", "",
                "| symbol | basis | period | metric | XBRL | printed | row | column |", "|---|---|---|---|---|---|---|---|"]
        out += [f"| {x['symbol']} | {x['basis']} | {x['period']} | {x['metric']} | {_g(x['xbrl_value'])} | {x['other_value']} | "
                f"{(x['row_label'] or '')[:40]} | {x['column_header']} |" for x in summary["other_value_examples"]]
    if summary["why_not_unique"]:
        out += ["", "## Why not found, ambiguous or no text", ""] + [f"- {k or 'unspecified'}: {n}" for k, n in summary["why_not_unique"].items()]
    out += ["", "Every figure, with its page, row label, column header and box, is in the CSV artifact.", ""]
    return "\n".join(out)


BEST = {s: i for i, s in enumerate(STATUSES)}   # a lower index is a better answer


def drop_stale(saved: list[dict]) -> tuple[list[dict], int]:
    """(the saved rows of filings all read by this locator version, how many rows were dropped). A filing with any row of another
    version (or none: a file written before the stamp) is dropped whole, so it is read again with today's placement logic."""
    old = {(r.get("symbol"), r.get("filing_period", "")) for r in saved if r.get("locator_version") != LOCATOR_VERSION}
    kept = [r for r in saved if (r.get("symbol"), r.get("filing_period", "")) not in old]
    return kept, len(saved) - len(kept)


def is_transport_error(exc: BaseException) -> bool:
    """A network or HTTP error or a timeout (OSError covers timeouts and connection errors; httpx's own errors): the kind a later
    run may get past. Anything else raised in our own code is a deterministic failure."""
    import httpx

    return isinstance(exc, (OSError, httpx.HTTPError))


_TRANSIENT = re.compile(r"^(?:announcement list unavailable|download failed)")


def keep_pdf(keep_dir: str, url: str, data: bytes) -> str:
    """Write a downloaded PDF into ``keep_dir`` under the name ``pdf_bench --collect`` gives it (``<pdf_key(url)>.pdf``), so that
    ``pdf_bench --run`` finds it by its url; at once, and whole or not at all (a run stopped on the way keeps what it got)."""
    from .pdf_readers import pdf_key

    os.makedirs(keep_dir, exist_ok=True)
    path = os.path.join(keep_dir, f"{pdf_key(url)}.pdf")
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
    return path


def bench_symbols(docs_dir: str | None = None) -> set[str]:
    """The symbols of the two hand answer keys (``docs/bench/normalpdf/key.csv``, ``docs/bench/hardpdf/key.csv``): the companies
    the readers were built and tuned on. A missing key file is an error, never an empty set (a test would then not be out of sample)."""
    base = Path(docs_dir) if docs_dir else Path(__file__).resolve().parents[3] / "docs"
    symbols: set[str] = set()
    for name in ("normalpdf", "hardpdf"):
        path = base / "bench" / name / "key.csv"
        if not path.is_file():
            raise FileNotFoundError(f"--exclude-bench: the answer key {path} is missing")
        with open(path, encoding="utf-8", newline="") as fh:
            symbols |= {r["symbol"].strip().upper() for r in csv.DictReader(fh) if r.get("symbol", "").strip()}
    if not symbols:
        raise ValueError("--exclude-bench: the answer keys name no company")
    return symbols


_STATEMENT_WORDS = re.compile(r"(?:revenue|income|sales)\s+from\s+operations|total\s+(?:income|revenue)|net\s+sales|gross\s+sales|"
                             r"interest\s+earned|profit\s*(?:/\s*\(?\s*loss\s*\)?\s*)?before\s+(?:exceptional\s+items\s+and\s+)?tax|"
                             r"premiums?\s+earned|net\s+premium", re.I)


def _scanned_or_drawn(page, text: str) -> bool:
    """A page only OCR can read: one image covers at least ``SCAN_IMAGE_SHARE`` of it (its text layer, if any, is the scanner's
    and may be garbled), or it has images or vector drawings and almost no words (a statement drawn as paths)."""
    from .pdf_numbers_first import SCAN_IMAGE_SHARE, largest_image_share

    try:
        if largest_image_share(page) >= SCAN_IMAGE_SHARE:
            return True
    except Exception:   # noqa: BLE001 - the images cannot be measured: keep the PDF
        return True
    return len(text.split()) < 30 and bool(page.get_images() or page.get_drawings())


def holds_results(source, max_pages: int = MAX_PAGES) -> bool:
    """Whether a PDF (bytes) may hold a results statement: a page of its text layer names a statement line (revenue from
    operations, total income, profit (loss) before tax, premiums earned...), or a page is a scan or a drawing that only OCR can
    read (``_scanned_or_drawn``). NSE's "results" announcements also carry AGM proceedings, postal ballot results, Reg 30
    letters and asset cover certificates (30 Oct 2026: 76 of 500 key figures paired with such a PDF, where a stray number could
    be "placed"); those have neither. Known and accepted: voting results or a scrutinizer's report with a scanned page still
    pass, as without OCR a scanned letter cannot be told from a scanned statement. A file pymupdf cannot open is left to the
    locator, as before."""
    import pymupdf

    try:
        doc = pymupdf.open(stream=source, filetype="pdf")
    except Exception:   # noqa: BLE001
        return True
    try:
        for i in range(min(doc.page_count, max_pages)):
            page = doc[i]
            text = page.get_text()
            if _STATEMENT_WORDS.search(text) or _scanned_or_drawn(page, text):
                return True
        return doc.page_count == 0
    finally:
        doc.close()


_PLACED = ("found_unique", "found_ambiguous", "row_found_other_value")

PDF_STORE = "raw/results-pdf/"     # every results PDF this module downloads, gzip, by ``pdf_key(url)``: read first, never fetched twice


def stored_payload(src, store, url: str) -> tuple[bytes | None, str]:
    """A candidate PDF read from our store first (``PDF_STORE``), downloaded only if we do not hold it, and every download kept
    there at once (owner, 29 Oct 2026: reuse test files, never download twice). ``store`` is the sink (``get_object`` /
    ``put_object``); None reads NSE as before. A store that fails to answer or to keep is logged and never stops the filing."""
    import gzip

    from .pdf_readers import pdf_key
    if store is None:
        return src.payload(url)
    key = f"{PDF_STORE}{pdf_key(url)}.pdf.gz"
    try:
        held = store.get_object(key)
    except Exception as exc:   # noqa: BLE001
        log.warning("xbrl-key: the PDF store did not answer for %s (%s); downloading", key, type(exc).__name__)
        held = None
    if held:
        try:
            data = gzip.decompress(held)
        except Exception:   # noqa: BLE001 - not gzip (OSError), cut short (EOFError) or damaged (zlib.error)
            log.warning("xbrl-key: %s in the store is not a whole gzip; downloading again", key)
            data = b""
        if data:
            return data, ""
    data, why = src.payload(url)
    if data:
        try:
            store.put_object(key, gzip.compress(data), "application/gzip")
        except Exception as exc:   # noqa: BLE001
            log.warning("xbrl-key: the PDF store did not keep %s (%s)", key, type(exc).__name__)
    return data, why


_KEPT_NAME = re.compile(r"^[0-9a-f]{16}\.pdf$")


def store_kept_pdfs(sink, folder: str) -> dict:
    """Put each PDF a run kept in ``folder`` (named ``pdf_key(url).pdf``, as ``--keep-pdfs`` and ``pdf_bench --collect`` name them)
    into the PDF store (``PDF_STORE``, gzip), skipping a key the store already holds; nothing is downloaded from NSE. Returns the
    counts: stored, already held, failed (a put that raised), skipped (a file not so named, or not a PDF). A failure is logged and
    the next file goes on."""
    import gzip

    counts = {"stored": 0, "already_held": 0, "failed": 0, "skipped": 0}
    try:
        held: set[str] | None = set(sink.list_objects(PDF_STORE))
    except Exception as exc:   # noqa: BLE001 - no listing: ask for each key instead
        log.warning("store-kept-pdfs: the store could not list %s (%s); asking for each key", PDF_STORE, type(exc).__name__)
        held = None
    for path in sorted(Path(folder).iterdir()) if Path(folder).is_dir() else []:
        if not path.is_file():
            continue
        data = path.read_bytes() if _KEPT_NAME.match(path.name) else b""
        if not data.startswith(b"%PDF"):
            counts["skipped"] += 1
            continue
        key = f"{PDF_STORE}{path.name}.gz"
        try:
            if (key in held) if held is not None else bool(sink.get_object(key)):
                counts["already_held"] += 1
                continue
            sink.put_object(key, gzip.compress(data), "application/gzip")
            counts["stored"] += 1
        except Exception as exc:   # noqa: BLE001
            log.warning("store-kept-pdfs: %s not stored (%s)", key, type(exc).__name__)
            counts["failed"] += 1
    return counts


def locate_filing(src, symbol: str, period: str, expected: list[Expected], keep_dir: str | None = None,
                  store=None) -> tuple[list[dict], str, bool]:
    """The rows for one filing (quarter): its results PDFs from NSE's announcements, tried in the PDF referee's order (at most
    ``MAX_CANDIDATES``), a PDF with no results statement in it (``holds_results``) skipped. Every candidate is read; the filing's
    rows are those of the ONE PDF with most ``found_unique`` figures (then most placements, then list order), the others' rows
    dropped, so a letter that passed the filter with a few stray numbers placed cannot stand in for the statement (30 Oct
    2026: the first PDF with any placement used to end the search before the results PDF was read). When no PDF has a
    ``found_unique``, the first PDF that places any figure is the filing's, the best answer of each figure across the PDFs up
    to it kept. Returns (rows, why none, transient): ``transient`` is true when nothing was read
    because a list or a download failed on the way (a timeout, a refused call), which a later run may get; a filing NSE has no
    results PDF for, or a PDF it serves empty or too large, is a settled answer, not a failure."""
    listed = src.filings(symbol, period)
    if isinstance(listed, str):
        return [], listed, bool(_TRANSIENT.match(listed))
    best: dict[int, tuple[Result, dict]] = {}
    read: list[tuple[list[Result], dict]] = []       # (results, row extras) of each PDF located, in list order
    reasons = []
    transient = False
    error = None
    for f in listed[:MAX_CANDIDATES]:
        data, why = stored_payload(src, store, f.pdf_url)
        if data is None:
            reasons.append(why)
            transient = transient or bool(_TRANSIENT.match(why))
            continue
        if keep_dir:
            keep_pdf(keep_dir, f.pdf_url, data)
        if not holds_results(data):
            reasons.append("not a results statement: " + f.pdf_url.rsplit("/", 1)[-1][:40])
            continue
        extra = {"pdf_url": f.pdf_url, "pdf_news_id": f.news_id, "filing_period": period}
        try:
            results = locate(data, expected)
        except Exception as exc:   # noqa: BLE001 - the locator raised on a PDF we have: a bug or a damaged file, not a transport error
            log.exception("xbrl-key: locating in %s failed", f.pdf_url)
            error = (exc, extra)
            reasons.append(f"{type(exc).__name__} while locating")
            continue
        read.append((results, extra))
        if not any(r.status in _PLACED for r in results):
            reasons.append("no figure placed in " + f.pdf_url.rsplit("/", 1)[-1][:40])

    def score(i: int) -> tuple[int, int, int]:
        results = read[i][0]
        return sum(r.status == "found_unique" for r in results), sum(r.status in _PLACED for r in results), -i

    winner = max(range(len(read)), key=score, default=None)
    if winner is not None and score(winner)[0]:
        results, extra = read[winner]
        best = {k: (r, extra) for k, r in enumerate(results)}
    else:
        for results, extra in read:
            for k, r in enumerate(results):
                if k not in best or BEST[r.status] < BEST[best[k][0].status]:
                    best[k] = (r, extra)
            if any(r.status in _PLACED for r in results):
                break
    used = any(r.status in _PLACED for r, _ in best.values())
    if transient and not used:
        return [], "; ".join(dict.fromkeys(reasons)), True      # a download failed and no other PDF gave a figure: not finished
    if not best and error is not None:
        exc, extra = error     # settled: the same PDF would raise again, so it is not read again until the locator changes
        return [result_row(Result(e, "locate_error", note=f"{type(exc).__name__}: {str(exc)[:100]}"), extra) for e in expected], "", False
    if not best:
        return [], "; ".join(dict.fromkeys(reasons)) or "no results PDF read", False
    return [result_row(r, extra) for r, extra in (best[k] for k in sorted(best))], "", False


PROGRESS_PREFIX = "meta/xbrl-key/"   # R2: outlives a lost runner, unlike the job's artifact (as pdf-referee's progress)
SAVE_EVERY_FILINGS = 10
SAVE_EVERY_SECONDS = 180.0


def progress_key(name: str) -> str:
    return f"{PROGRESS_PREFIX}{re.sub(r'[^A-Za-z0-9._-]', '_', name)[:100]}.csv"


def load_progress(sink, name: str) -> list[dict]:
    try:
        body = sink.get_object(progress_key(name))
    except Exception as exc:   # noqa: BLE001 - nothing saved is a fresh start, not a stop
        log.warning("xbrl-key: saved progress unreadable (%s: %s); starting fresh", type(exc).__name__, exc)
        return []
    return load_csv(body.decode("utf-8")) if body else []


def save_progress(sink, name: str, rows: list[dict]) -> bool:
    try:
        sink.put_object(progress_key(name), to_csv(rows).encode("utf-8"), "text/csv")
        return True
    except Exception as exc:   # noqa: BLE001
        log.warning("xbrl-key: progress not saved (%s: %s)", type(exc).__name__, exc)
        return False


def plan(sink, companies: list[tuple[str, str]], limit: int | None, per_company: int, seed: int, floor: int = 8,
         exclude: set[str] | None = None):
    """The filings to read, one at a time (a dossier is read when its turn comes, so the first filing is read at once): companies in
    a seeded shuffle (a spread over the universe), for each its newest ``per_company`` quarter filings that have at least ``floor``
    XBRL figures of the listed metrics; at most ``limit`` filings. A company whose symbol is in ``exclude`` is left out (the shuffle
    is made first, so the others keep their order). Yields (scrip, symbol, period, expected figures)."""
    import random

    from .memory_gaps import quarter_end

    order = sorted(companies)
    random.Random(seed).shuffle(order)
    given = 0
    skip = {x.upper() for x in exclude or ()}
    for scrip, symbol in order:
        if symbol.upper() in skip:
            continue
        try:
            dossier = sink.get_dossier(scrip)
        except Exception as exc:   # noqa: BLE001
            log.warning("xbrl-key: dossier of %s unreadable (%s)", scrip, type(exc).__name__)
            continue
        by_period = expected_from_dossier(dossier, symbol)
        periods = sorted((p for p, v in by_period.items() if len(v) >= floor and quarter_end(p)), key=quarter_end, reverse=True)
        for period in periods[:per_company]:
            if limit is not None and given >= limit:
                return
            given += 1
            yield scrip, symbol, period, by_period[period]


def run(nse, sink, companies: list[tuple[str, str]], limit: int | None = None, per_company: int = 1, seed: int = 28,
        time_budget: float | None = None, clock=time.monotonic, progress=None, saved: list[dict] | None = None,
        every: int = SAVE_EVERY_FILINGS, every_seconds: float = SAVE_EVERY_SECONDS, src=None,
        exclude: set[str] | None = None, keep_dir: str | None = None) -> dict:
    """Read the planned filings one after the other; ``progress(rows, summary)`` gets everything so far every ``every`` filings or
    ``every_seconds``, so a run stopped by its time budget, the file cap or a lost runner keeps what it did. ``saved`` are the
    rows of an earlier run of the same name: a filing already in them (its id and period) is kept and not read again."""
    from .nse import FileCapReached, SourceBlockedError
    from .pdf_referee import Sources

    src = src or Sources(nse, ocr=False)
    kept, stale = drop_stale(saved or [])
    if stale:
        log.warning("xbrl-key: %d saved rows of another locator version (not %s) dropped; their filings are read again",
                    stale, LOCATOR_VERSION)
    rows: list[dict] = [r for r in kept if r.get("status") != "fetch_failed"]
    done = {(r["symbol"], r.get("filing_period", "")) for r in rows}
    started, last_save, since = clock(), clock(), 0
    blocked = out_of_time = capped = False
    for scrip, symbol, period, expected in plan(sink, companies, limit, per_company, seed, exclude=exclude):
        if (symbol, period) in done:
            continue
        if time_budget is not None and clock() - started > time_budget:
            out_of_time = True
            break
        try:
            got, why, transient = locate_filing(src, symbol, period, expected, store=sink,
                                                **({"keep_dir": keep_dir} if keep_dir else {}))
        except FileCapReached as exc:
            capped = True
            log.warning("file cap reached (%s): stopping the XBRL key; the rest waits for the next run", exc)
            break
        except SourceBlockedError as exc:
            blocked = True
            log.warning("NSE refused (%s): stopping the XBRL key", exc)
            break
        except Exception as exc:   # noqa: BLE001 - one filing failing is a reason, not a stop
            if is_transport_error(exc):
                got, why, transient = [], f"{type(exc).__name__}: {str(exc)[:80]}", True      # read again next run
            else:   # a deterministic failure of ours: settled, with the class in the note, not downloaded again every dispatch
                log.exception("xbrl-key: %s %s failed", symbol, period)
                got = [result_row(Result(e, "locate_error", note=f"{type(exc).__name__}: {str(exc)[:100]}"), {"filing_period": period})
                       for e in expected]
                why, transient = "", False
        if not got:
            log.info("xbrl-key: %s %s: %s%s", symbol, period, why, " (fetch failed, not finished)" if transient else "")
            status = "fetch_failed" if transient else "not_found"
            got = [result_row(Result(e, status, note=f"no PDF read: {why}"), {"filing_period": period}) for e in expected]
        rows += got
        if not transient:
            done.add((symbol, period))        # a fetch failure is not a finished filing: a resume reads it again
        since += 1
        src.release()
        if progress and (since >= every or clock() - last_save >= every_seconds):
            try:
                progress(rows, summarise(rows, src.calls, len(done), blocked, out_of_time, capped))
            except Exception:   # noqa: BLE001 - a failed save is never a stop
                log.exception("xbrl-key: the progress callback failed")
            last_save, since = clock(), 0
    return {"rows": rows, "stale_rows_dropped": stale, **summarise(rows, src.calls, len(done), blocked, out_of_time, capped)}
