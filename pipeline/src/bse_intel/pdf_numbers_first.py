"""An experimental "numbers-first" reader of a results statement (28 Oct 2026). BENCH ONLY: it is not in the live path and has no
switch. It is a ``pdf_readers`` reader (name ``numfirst``, selected only by ``PDF_READERS=native,numfirst``), scored by the same
scorer as the native reader (``pdf_bench``).

Why. The native reader (``pdf_referee.parse_page``) works from lines of text and finds a row by its label. It almost never gives a
wrong answer but finds no row for most figures (normal-results key: 45 of 337 right, 292 no answer): labels wrap over two or three
lines with the numbers on one of them, a total is printed as just "Total" or "(I+II)", and a text layer stores labels and number
columns apart. This reader starts from the numbers instead.

1. Words with coordinates (PyMuPDF ``get_text("words")``; a page printed sideways is turned upright as ``extract.upright_text``
   does; a tilted page is straightened with ``ocr._skew``). A page with no text layer is read with the pipeline's own RapidOCR
   (``ocr``): its boxes become words (a box of several tokens is cut in proportion to its characters).
2. Numbers first. A number token is Indian or western grouping, brackets or a leading minus for a negative, a lone "-" / "–" / "Nil"
   for nil. Tokens that line up (right edge, centre or left edge) form columns; tokens at one height form rows; a numeric row has
   cells in at least two columns. Numbers do not wrap.
3. Label stitching. A row's label is every word left of the first column whose height lies after the previous numeric row and up
   to this row's own band (a wrapped label is joined again).
4. Columns by header date. The header words above a column (stacked "30 September" / "2026" lines joined) give its date; the
   group words ("Quarter ended", "Six months ended", "Year ended") give its kind by the nearest group word, or by the standard
   layout of Indian results (``pdf_referee._pattern_kinds``). A column is the period's when its date and kind are.
5. A vertical arithmetic solver names the rows, over all columns at once, and a row is named only when its identity holds in at
   least three columns (all of them when fewer are printed; one garbled column is tolerated) and in the period's own column:
   total income = the rows directly above it (revenue + other income); total expenses = a block of rows above it; profit before
   exceptional items and tax = total income - total expenses; profit before tax = that +/- exceptional items and share of
   associates (hops over the rows in between); tax = a row, or the sum of rows; profit after tax = profit before tax - tax.
   The stitched label is a second signal (Schedule III landmarks) and never alone for a total: where the label says another
   line than the arithmetic does, there is no answer. Where two readings of the table give two values, there is no answer.
6. Units come from the unit line above the table (``grounding.unit_before``), else the page's one unit; the basis from the title
   text above the table, as the native reader tells it (``pdf_referee._basis_above_boxed``).

Never a guess: no answer is better than a wrong one. Not done in this first version: EPS, banks whose layout is not Schedule III
(only what the chain finds), two bases side by side on one page (the columns repeat their dates, so no column is unique), a table
that runs over two pages, a scan that is also tilted by more than a few degrees, a scan turned sideways.
"""

from __future__ import annotations

import itertools
import logging
import re
import statistics
from dataclasses import dataclass, field
from datetime import date

log = logging.getLogger(__name__)

NAME = "numfirst"
MAX_STATEMENT_PAGES = 6
MAX_OCR_PAGES = 16            # scanned pages read with OCR in a PDF (ATGL Q2FY27: 13 scanned pages, standalone on p14)
MAX_FILL_OCR_PAGES = 4         # pages with a text layer OCR'd only for a missing unit or row labels (fill_from_ocr)
MAX_TEXT_PAGES = 60            # pages with a text layer read from their words
SCAN_PAGE_LIMIT = 30           # a scan with no text layer is searched in a PDF of up to this many pages
MIN_COLUMN_FIGURES = 3         # figures that line up to make a column
IDENT_MIN_COLUMNS = 3
LABEL_WORDS_LINES = 14         # text lines above a table searched for its title and header


# --- words ----------------------------------------------------------------------------------------------------------------

@dataclass
class Word:
    x0: float
    x1: float
    y: float            # centre height, straightened
    h: float
    text: str
    ocr: bool = False

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


def upright_words(page) -> list[tuple[float, float, float, float, str]]:
    """The page's words as (x0, y0, x1, y1, text) with the text running left to right: a page printed sideways is turned a
    quarter, as ``extract.upright_text`` turns it."""
    lines = [line for block in page.get_text("dict", flags=0)["blocks"] for line in block.get("lines", [])]
    vertical = [line for line in lines if abs(line["dir"][1]) > 0.9]
    sideways = bool(lines) and len(vertical) >= 0.6 * len(lines)
    up = sideways and sum(line["dir"][1] for line in vertical) < 0
    out = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        if not str(text).strip():
            continue
        if sideways:
            x0, x1, y0, y1 = (-y1, -y0, x0, x1) if up else (y0, y1, -x1, -x0)
        out.append((x0, y0, x1, y1, str(text)))
    return out


def straighten(raw: list[tuple[float, float, float, float, str]], ocr_source: bool = False) -> list[Word]:
    """Words with the page's tilt taken out of their heights (``ocr._skew``: the angle whose row histogram is sharpest)."""
    from . import ocr
    items = [((y0 + y1) / 2, max(y1 - y0, 1.0), x0, text, x1) for x0, y0, x1, y1, text in raw]
    theta = ocr._skew(items) if len(items) >= 30 else 0.0
    import math
    t = math.tan(theta)
    return [Word(x0, x1, ((y0 + y1) / 2) - (x0 + x1) / 2 * t, max(y1 - y0, 1.0), text, ocr_source) for x0, y0, x1, y1, text in raw]


_BRACKET_OPEN = "([{"
_BRACKET_CLOSE = ")]}"


def merge_brackets(words: list[Word], height: float) -> list[Word]:
    """A bracket printed apart from its figure ("(" "12.5" ")") is joined to it, when it touches it."""
    out: list[Word] = []
    ordered = sorted(words, key=lambda w: (round(w.y / max(height, 1.0)), w.x0))
    for w in ordered:
        prev = out[-1] if out else None
        same_line = prev is not None and abs(prev.y - w.y) <= 0.5 * height
        if same_line and w.text in _BRACKET_CLOSE and w.x0 - prev.x1 <= 0.9 * height and prev.text[:1] in _BRACKET_OPEN \
                and prev.text[-1:] not in _BRACKET_CLOSE and re.search(r"\d", prev.text):
            out[-1] = Word(prev.x0, w.x1, prev.y, prev.h, prev.text + w.text, prev.ocr)
            continue
        if same_line and prev.text in _BRACKET_OPEN and w.x0 - prev.x1 <= 0.9 * height and re.match(r"-?\d", w.text):
            out[-1] = Word(prev.x0, w.x1, w.y, w.h, prev.text + w.text, w.ocr)
            continue
        out.append(w)
    return out



SPACE_GROUP_GAP = 1 / 3       # of the text height: TATAELXSI's split figures are 1-2 pt apart at 7.9 pt (at most 0.25)
_GROUP_HEAD = re.compile(r"^[(\[]?\d{1,3}$")
_GROUP_MID = re.compile(r"^\d{2,3}$")
_GROUP_TAIL = re.compile(r"^\d{3}(?:\.\d+)?[)\]]?$")


def merge_space_groups(words: list[Word], height: float) -> list[Word]:
    """A figure whose thousands are set apart by a space instead of a comma, as a scanner's text layer often writes them:
    "23 909.66" for 23,909.66, "3 02 060.27" for 3,02,060.27 (TATAELXSI Q2FY27). A run of pieces that touch (a gap under half
    a third of the text height; columns stand ten times further apart) is joined only as a whole and only when the whole run is one
    figure: the first piece has one to three digits, the middle pieces are all of two digits (Indian) or all of three
    (western), and the last has exactly three digits before its decimals. Any other run is left as it is, every piece. A
    piece with a comma is never joined: "24 1,245.60" stays a note number and a figure."""
    out: list[Word] = []
    ordered = sorted(words, key=lambda w: (round(w.y / max(height, 1.0)), w.x0))

    def touches(a: Word, b: Word) -> bool:
        return abs(b.y - a.y) <= 0.5 * height and 0 <= b.x0 - a.x1 <= SPACE_GROUP_GAP * height

    i = 0
    while i < len(ordered):
        run = [ordered[i]]
        while i + len(run) < len(ordered) and re.match(r"[(\[]?\d", run[-1].text) \
                and re.match(r"\d", ordered[i + len(run)].text) and touches(run[-1], ordered[i + len(run)]):
            run.append(ordered[i + len(run)])
        mids = {len(c.text) for c in run[1:-1]}
        if len(run) >= 2 and _GROUP_HEAD.match(run[0].text) and all(_GROUP_MID.match(c.text) for c in run[1:-1]) \
                and len(mids) <= 1 and _GROUP_TAIL.match(run[-1].text):
            out.append(Word(run[0].x0, run[-1].x1, run[0].y, run[0].h, "".join(c.text for c in run), run[0].ocr))
        else:
            out.extend(run)
        i += len(run)
    return out


def ocr_page_boxes(png: bytes):
    """RapidOCR's boxes of a page image (``ocr._boxes`` form), with the sideways turn ``ocr.recognise`` makes; [] when OCR is not
    installed. Kept apart so the bench can cache it."""
    from . import ocr
    if not ocr.available():
        return []
    import cv2
    import numpy as np
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    with ocr._lock:
        if ocr._engine is None:
            ocr._engine = ocr._new_engine()
        result = ocr._boxes(ocr._engine(image if image is not None else png))
        if len(result) >= 8 and ocr.lying_flat(result) < 0.5 and image is not None:
            best = None
            for turn in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
                turned = ocr._boxes(ocr._engine(cv2.rotate(image, turn)))
                if turned and ocr.lying_flat(turned) >= 0.5 and (best is None or ocr._mean_score(turned) > ocr._mean_score(best)):
                    best = turned
            if best is not None:
                result = best
    return [([[float(p[0]), float(p[1])] for p in box], str(text), float(score)) for box, text, score in result]



OCR_ALIGN_SHARE = 0.9        # of a table's figures that OCR must read at the layer's own place before its text is used
OCR_LABELS_SHARE = 0.9       # of a table's rows that must have a label once OCR's are added, or none are added


def ocr_aligned(table: "Table", words: list["Word"], height: float) -> bool:
    """OCR sees the page the layer describes: at least ``OCR_ALIGN_SHARE`` of the table's figures are read by OCR as the same
    value within half the figure's last printed digit, its centre within half a text height of the row and within the
    column. A rotated page, a shifted render or a different page frame fails this, and then no OCR text is used."""
    figs = [(w, c) for w in words if (c := parse_figure(w.text)) is not None and not c.nil]
    total = hits = 0
    for r in table.rows:
        for col, cell in zip(table.columns, r.cells):
            if cell is None or cell.nil:
                continue
            total += 1
            hits += any(abs(w.y - r.y) <= 0.5 * height and col.x0 - height <= w.xc <= col.x1 + height
                        and abs(c.value - cell.value) <= cell.tol + 1e-9 for w, c in figs)
    return total > 0 and hits >= OCR_ALIGN_SHARE * total

def words_from_boxes(boxes) -> list[tuple[float, float, float, float, str]]:
    """OCR boxes as words: a box of several tokens is cut in proportion to its characters."""
    from . import ocr
    out = []
    for box, text, _score in ocr._boxes(boxes):
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        text = str(text).strip()
        if not text:
            continue
        tokens = [m for m in re.finditer(r"\S+", text)]
        width = (x1 - x0) / max(len(text), 1)
        for m in tokens:
            tok = ocr._repair(m.group())
            out.append((x0 + m.start() * width, y0, x0 + m.end() * width, y1, tok))
    return out


# --- numbers --------------------------------------------------------------------------------------------------------------

_NUM = r"(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?"
_FIG = re.compile(rf"^(?P<open>[\(\[\{{])?(?P<minus>[-−–])?(?P<num>{_NUM})(?P<close>[\)\]\}}])?$")
_NIL = re.compile(r"^[-–—−]$|^nil$", re.I)
_YEAR_ONLY = re.compile(r"^(?:19|20)\d\d$")


@dataclass
class Cell:
    value: float
    decimals: int
    nil: bool
    strict: bool
    word: Word
    text: str = ""

    @property
    def tol(self) -> float:
        return 0.0 if self.nil else 0.5 * 10 ** -self.decimals


def parse_figure(text: str) -> Cell | None:
    """A number token as a ``Cell`` (value, printed decimals), or None. ``strict``: it has a decimal point, a comma group or at
    least four digits (a note number, a serial number or a year does not); a nil dash is a cell of value 0."""
    t = text.strip().strip("*")
    if _NIL.match(t):
        return Cell(0.0, 0, True, False, None, t)       # type: ignore[arg-type]
    m = _FIG.match(t)
    if not m:
        return None
    num = m["num"]
    digits = num.replace(",", "")
    if _YEAR_ONLY.match(digits) and "," not in num and "." not in num:
        return None
    decimals = len(num.split(".")[1]) if "." in num else 0
    value = float(digits)
    negative = bool(m["open"] or m["close"] or m["minus"])
    if m["open"] and m["close"] is None and not m["minus"]:
        negative = True            # a half-lost bracket: still a negative (ocr._repair does the same)
    strict = "." in num or "," in num or len(digits) >= 4
    return Cell(-value if negative else value, decimals, False, strict, None, t)    # type: ignore[arg-type]


# --- a page into rows and columns -----------------------------------------------------------------------------------------

@dataclass
class NRow:
    y: float
    top: float
    bottom: float
    label: str
    cells: list[Cell | None]
    words_left: list[Word] = field(default_factory=list)


@dataclass
class Column:
    x0: float
    x1: float
    xc: float
    index: int = 0
    date: date | None = None
    kind: str | None = None        # quarter, half, nine, year (None: not told)
    kind_confident: bool = False
    whole: bool = False            # a column of small whole figures found by ``whole_number_columns``
    inferred: bool = False         # its date was not read but given by the layout (``fill_corresponding_quarter``)
    read_date: date | None = None  # the header's date as read, kept when the kinds disagree (only the half-year sum uses it)


@dataclass
class Table:
    page: int
    basis: str | None
    unit: float | None             # figures per crore
    columns: list[Column]
    rows: list[NRow]
    source: str = "textlayer"
    note: str = ""
    named: dict = field(default_factory=dict)   # metric -> list of (rows, proofs)
    header_lines: list = field(default_factory=list)   # the text lines above the table (title, unit, header), for diagnosis
    contested: bool = False        # the lines above the table name both bases: its basis is never guessed


def _cluster(values: list[float], tol: float) -> list[list[int]]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    groups: list[list[int]] = []
    for i in order:
        if groups and values[i] - values[groups[-1][-1]] <= tol:
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


def text_height(words: list[Word]) -> float:
    hs = [w.h for w in words if re.search(r"[A-Za-z0-9]", w.text)]
    return statistics.median(hs) if hs else 8.0


def find_columns(cells: list[tuple[Word, Cell]], height: float) -> tuple[list[Column], str]:
    """Columns of the page: the figures (strict ones) that line up by right edge, centre or left edge, whichever lines up best."""
    strict = [(w, c) for w, c in cells if c.strict]
    if len(strict) < MIN_COLUMN_FIGURES:
        return [], ""
    tol = 0.8 * height
    best: tuple[float, str, list[list[int]]] | None = None
    for name, key in (("right", lambda w: w.x1), ("centre", lambda w: w.xc), ("left", lambda w: w.x0)):
        groups = _cluster([key(w) for w, _ in strict], tol)
        groups = [g for g in groups if len(g) >= MIN_COLUMN_FIGURES]
        score = sum(len(g) ** 2 for g in groups)
        if best is None or score > best[0]:
            best = (score, name, groups)
    if not best or not best[2]:
        return [], ""
    columns = []
    for g in best[2]:
        ws = [strict[i][0] for i in g]
        x0, x1 = min(w.x0 for w in ws), max(w.x1 for w in ws)
        # the aligned edge is the group's median, not its extreme: one garbled wider figure ("1,958.111" in ATUL's half-year
        # column) would move the edge off the other figures, and they would not be assigned to the column
        if best[1] == "right":
            x1 = statistics.median(w.x1 for w in ws)
        elif best[1] == "left":
            x0 = statistics.median(w.x0 for w in ws)
        columns.append(Column(x0, x1, (x0 + x1) / 2))
    columns.sort(key=lambda c: c.xc)
    for i, c in enumerate(columns):
        c.index = i
    return columns, best[1]


def whole_number_columns(cells: list[tuple[Word, Cell]], columns: list[Column], align: str, words: list[Word],
                         height: float) -> list[Column]:
    """Columns of small whole figures with no comma or decimals ("565 604 643" in crore, ORIENTCEM Q2FY27), which the strict
    figures alone do not make: a group of such figures that lines up as a column does, is about as long as the strict
    columns (six in ten of their median length) and stands on their grid (the strict columns' spacing, within a quarter of
    it). It needs two strict columns to set the grid, and most of its figures must have a word of letters to their left on
    their line (the row's label): a serial-number column ("1", "2", ... left of the labels) stands on the grid too but has
    nothing to its left. A note column stands off the grid as a rule, and a column with no date or whose arithmetic fails
    gives no answer anyway."""
    if len(columns) < 2:
        return []
    tol = 0.8 * height
    strict_sizes = [sum(1 for w, c in cells if c.strict and col.x0 - tol <= w.xc <= col.x1 + tol) for col in columns]
    key = {"right": lambda w: w.x1, "centre": lambda w: w.xc, "left": lambda w: w.x0}[align]
    ref = {"right": lambda c: c.x1, "centre": lambda c: c.xc, "left": lambda c: c.x0}[align]
    edges = sorted(ref(c) for c in columns)
    step = statistics.median([b - a for a, b in zip(edges, edges[1:])])
    loose = [w for w, c in cells if not c.strict and not c.nil and re.fullmatch(r"\(?-?\d{1,3}\)?", w.text.strip())
             and all(abs(key(w) - e) > tol for e in edges)]
    groups = [g for g in _cluster([key(w) for w in loose], tol)
              if len(g) >= max(MIN_COLUMN_FIGURES, 0.6 * statistics.median(strict_sizes))]
    out = []
    for g in groups:
        ws = [loose[i] for i in g]
        edge = statistics.median(key(w) for w in ws)
        k = round((edge - edges[0]) / step)
        if abs(edge - (edges[0] + k * step)) > 0.25 * step or any(abs(edge - e) < 0.5 * step for e in edges):
            continue
        labelled = sum(any(abs(v.y - w.y) <= 0.5 * height and v.x1 < w.x0 and re.search(r"[A-Za-z]{3}", v.text) for v in words)
                       for w in ws)
        if labelled < 0.6 * len(ws):
            continue
        x0, x1 = min(w.x0 for w in ws), max(w.x1 for w in ws)
        if align == "right":
            x1 = edge
        elif align == "left":
            x0 = edge
        out.append(Column(x0, x1, (x0 + x1) / 2, whole=True))
    return out


def assign_cells(words: list[Word], columns: list[Column], align: str, height: float) -> list[tuple[int, Word, Cell]]:
    """Every number-like word that sits in a column: (column, word, cell). Nil dashes by centre inside the column's extent, loose
    integers by the column's alignment, strict figures by alignment too."""
    if not columns:
        return []
    key = {"right": lambda w: w.x1, "centre": lambda w: w.xc, "left": lambda w: w.x0}[align]
    ref = {"right": lambda c: c.x1, "centre": lambda c: c.xc, "left": lambda c: c.x0}[align]
    gaps = [b.xc - a.xc for a, b in zip(columns, columns[1:])]
    spacing = min(gaps) if gaps else 8 * height
    # a column that prints decimals ("1,245.60") has no small whole number in it: a "24" that lines up with it is a note number or
    # a serial number, label text, never a figure (a "Note" column of annual reports sits left of the periods, 1 to 60)
    decimal_column = [False] * len(columns)
    for j in range(len(columns)):
        strict = [c for w in words if (c := parse_figure(w.text)) is not None and c.strict
                  and abs(ref(columns[j]) - key(w)) <= 0.8 * height]
        decimal_column[j] = sum(c.decimals >= 1 for c in strict) >= 0.75 * max(len(strict), 1)
        if columns[j].whole and len(strict) < MIN_COLUMN_FIGURES:
            decimal_column[j] = False    # a whole-figure column holds an EPS with decimals or two ("1.56", ORIENTCEM Q2FY27)
    out = []
    for w in words:
        cell = parse_figure(w.text)
        if cell is None:
            continue
        if cell.nil:
            j = min(range(len(columns)), key=lambda k: abs(columns[k].xc - w.xc))
            c = columns[j]
            if c.x0 - 0.3 * height <= w.xc <= c.x1 + 0.3 * height:
                cell.word = w
                out.append((j, w, cell))
            continue
        j = min(range(len(columns)), key=lambda k: abs(ref(columns[k]) - key(w)))
        if not cell.strict and decimal_column[j] and cell.value != 0:       # a bare 0 is a zero, never a note number
            continue
        if abs(ref(columns[j]) - key(w)) <= (0.8 if cell.strict else 0.8) * height and abs(w.xc - columns[j].xc) <= 0.5 * spacing:
            cell.word = w
            out.append((j, w, cell))
    return out


def decimals_filter(assigned: list[tuple[int, Word, Cell]], count: int) -> list[tuple[int, Word, Cell]]:
    """A column's figures print one number of decimals; a figure with another is a garbled one (a lost point or comma, "1,958.111",
    "558776" in a column of "5,58,271.23") and is not a cell. A nil dash is always one."""
    out = list(assigned)
    page = [c.decimals for _, _, c in assigned if not c.nil]
    if len(page) >= 12:
        mode = max(set(page), key=page.count)
        if mode >= 1 and page.count(mode) >= 0.7 * len(page):
            out = [t for t in out if t[2].nil or t[2].decimals == mode]
            assigned = out
    for j in range(count):
        mine = [c for jj, _, c in assigned if jj == j and not c.nil]
        if len(mine) < 4:
            continue
        counts: dict[int, int] = {}
        for c in mine:
            counts[c.decimals] = counts.get(c.decimals, 0) + 1
        mode, n = max(counts.items(), key=lambda kv: kv[1])
        if mode >= 1 and n >= 0.6 * len(mine):
            out = [t for t in out if t[0] != j or t[2].nil or t[2].decimals == mode]
    return out


def build_rows(assigned: list[tuple[int, Word, Cell]], words: list[Word], columns: list[Column], height: float) -> list[NRow]:
    """Numeric rows: cells at one height in at least two columns, each with its stitched label."""
    if not assigned:
        return []
    order = sorted(assigned, key=lambda t: (t[1].y, t[1].x0))
    groups: list[list[tuple[int, Word, Cell]]] = []
    ys: list[float] = []
    for item in order:
        y = item[1].y
        if groups and abs(y - ys[-1]) <= 0.5 * height:
            groups[-1].append(item)
            ys[-1] = sum(i[1].y for i in groups[-1]) / len(groups[-1])
        else:
            groups.append([item])
            ys.append(y)
    rows: list[NRow] = []
    for g, y in zip(groups, ys):
        if len({j for j, _, _ in g}) < 2:
            continue
        cells: list[Cell | None] = [None] * len(columns)
        for j, _, cell in g:
            cells[j] = cell if cells[j] is None else _CONFLICT
        cells = [None if c is _CONFLICT else c for c in cells]
        decs = [c.decimals for c in cells if c is not None and not c.nil]
        if len(decs) >= 4:
            mode = max(set(decs), key=decs.count)
            if mode >= 1 and decs.count(mode) >= 3 and decs.count(mode) >= 0.5 * len(decs):
                # a row prints one number of decimals: a figure with fewer or more has lost or gained a digit (the point of
                # "1,505.28" lost reads 150528, and every sum over such a column still adds up)
                cells = [c if c is None or c.nil or c.decimals == mode else None for c in cells]
        rows.append(NRow(y, min(w.y - w.h / 2 for _, w, _ in g), max(w.y + w.h / 2 for _, w, _ in g), "", cells))
    return rows


_CONFLICT = Cell(0.0, 0, False, False, None, "conflict")        # type: ignore[arg-type]


def stitch_labels(rows: list[NRow], words: list[Word], columns: list[Column], used: set[int], height: float,
                  header_bottom: float | None) -> None:
    """Each row's label: the words left of the first column whose height is after the previous numeric row and up to this row's
    own band, in reading order."""
    left = min(c.x0 for c in columns)
    label_words = [w for w in words if id(w) not in used and w.x1 <= left + 0.5 * height]
    for i, r in enumerate(rows):
        lower = rows[i - 1].bottom if i else (header_bottom if header_bottom is not None else r.top - 3 * height)
        picked = [w for w in label_words if lower < w.y <= r.bottom + 0.0]
        picked.sort(key=lambda w: (round(w.y / (0.6 * height)), w.x0))
        r.words_left = picked
        r.label = " ".join(w.text for w in picked).strip()


# --- header: dates, kinds, title, unit ------------------------------------------------------------------------------------

_MONTH_WORD = re.compile(r"^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?$", re.I)


def lines_of(words: list[Word], height: float) -> list[list[Word]]:
    """Words in lines (by height, on a running centre), each line left to right."""
    out: list[list[Word]] = []
    ys: list[float] = []
    for w in sorted(words, key=lambda w: (w.y, w.x0)):
        if out and abs(w.y - ys[-1]) <= 0.55 * height:
            out[-1].append(w)
            ys[-1] = sum(x.y for x in out[-1]) / len(out[-1])
        else:
            out.append([w])
            ys.append(w.y)
    return [sorted(line, key=lambda w: w.x0) for line in out]


def line_text(line: list[Word]) -> str:
    return " ".join(w.text for w in line)


def _dates_in_text(text: str) -> list[date]:
    from .pdf_referee import _dates_in
    # a comma glued to the year, "Sep 30,2026" (LOTUSDEV Q2FY27, OCR and layer alike): the year is read as after a spaced comma
    return _dates_in(re.sub(r"(?<=\d),(?=\d{4}\b(?!,\d))", ", ", text))   # not "30,2025,2026": two dates run together



_MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
                "december"]


def mend_months(text: str) -> str:
    """OCR's spelling of month names in a header ("Septemher", "Seplember", "Septfmher", NEWGEN Q2FY27): a word of five
    letters or more that is close to one month's full name only (difflib ratio 0.8 or more, and nearer to it than to any
    other month) is that month; a day glued to a month ("30June") is set apart."""
    import difflib
    text = re.sub(r"\b(\d{1,2})([A-Za-z]{3,9})\b", r"\1 \2", text)

    def one(m: re.Match) -> str:
        word = m.group(0)
        scores = sorted(((difflib.SequenceMatcher(None, word.lower(), name).ratio(), name) for name in _MONTH_NAMES),
                        reverse=True)
        best, second = scores[0], scores[1]
        if best[0] >= 0.8 and best[0] - second[0] >= 0.15:
            return best[1].capitalize()
        return word
    return re.sub(r"\b[A-Za-z]{5,10}\b", one, text)


def header_dates(text: str) -> list[date]:
    """The dates of a column's header text; when none parses, a year read a touch above its day ("September 2026 30," in
    PNGSREVA Q2FY27's OCR) is put after it, for a day that ends a period only and never "12 months" (fifteenth review:
    "March 2026 12 months" is not 12 March)."""
    found = _dates_in_text(text) or _dates_in_text(
        re.sub(r"\b([A-Za-z]{3,9}\.?)\s+(20\d\d)\s+(2[89]|3[01])\b(?!\s*months?),?", r"\1 \3, \2", text, flags=re.I))
    if found:
        return found
    mended = mend_months(text)
    return _dates_in_text(mended) if mended != text else []

def typical_gap(words: list[Word], height: float) -> float:
    """The usual space between two words of a line on this page."""
    gaps = []
    for line in lines_of(words, height):
        gaps += [b.x0 - a.x1 for a, b in zip(line, line[1:]) if 0 < b.x0 - a.x1 < 3 * height]
    return statistics.median(gaps) if gaps else 0.5 * height


def phrases_of(line: list[Word], gap: float) -> list[list[Word]]:
    """A line cut into phrases where the space between two words is more than twice the page's usual one; a phrase that holds
    two dates ("Sep 30, 2026 Jun 30, 2026" with no wider space between) is cut between them."""
    out: list[list[Word]] = []
    for w in line:
        if out and w.x0 - out[-1][-1].x1 <= 2.0 * gap + 0.5:
            out[-1].append(w)
        else:
            out.append([w])
    split: list[list[Word]] = []
    for ph in out:
        text, spans = "", []
        for w in ph:
            spans.append((len(text), len(text) + len(w.text), w))
            text += w.text + " "
        from .pdf_referee import _DATE_LOOSE_2, _DATE_LOOSE, _two_digit
        found = list((_DATE_LOOSE_2 if _two_digit() else _DATE_LOOSE).finditer(text))
        if len(found) >= 2:
            cut, start = [], 0
            for m in found:
                hit = [w for a, b, w in spans if a < m.end() and b > m.start()]
                cut.append(hit)
            split += cut
        else:
            split.append(ph)
    return split


_BORDER_MARKS = {"I", "l", "|", "!", "¦"}

def column_dates(gap_words: list[Word], columns: list[Column], height: float, sep: float) -> list[date | None]:
    """The date above each column. The header's phrases are given to the column nearest their centre (a phrase wider than a
    column is a title, not a date); the phrases over a column are read top to bottom, so a date broken over two lines is
    joined, and the last date found is the one nearest the table."""
    if not columns:
        return []
    xs = [c.xc for c in columns]
    spacing = min((b - a for a, b in zip(xs, xs[1:])), default=8 * height)
    mine: list[list[tuple[float, float, str]]] = [[] for _ in columns]
    # a table's border drawn as a letter ("I" between "September 30," and "2026" in ATUL Q2FY27) is never part of a date
    gap_words = [w for w in gap_words if w.text.strip() not in _BORDER_MARKS]
    for line in lines_of(gap_words, height):
        for ph in phrases_of(line, sep):
            width = ph[-1].x1 - ph[0].x0
            centre = (ph[0].x0 + ph[-1].x1) / 2
            j = min(range(len(columns)), key=lambda k: abs(xs[k] - centre))
            if width <= 1.3 * spacing and abs(xs[j] - centre) <= 0.75 * spacing:
                mine[j].append((sum(w.y for w in ph) / len(ph), ph[0].x0, " ".join(w.text for w in ph)))
    out: list[date | None] = []
    for items in mine:
        text = " ".join(t for _, _, t in sorted(items)).replace("_", " ").replace("|", " ")
        found = header_dates(text)
        out.append(found[-1] if found else None)
    return out


def group_phrases(gap: list[Word], columns: list[Column], height: float) -> list[tuple[float, str]]:
    """(centre, kind) of each "Quarter ended" / "Six months ended" / "Year ended" phrase of the header, as the native reader's
    group words read them (``pdf_referee._GROUP``), kept to the lines near the header's dates."""
    from .pdf_referee import _GROUP
    lines = lines_of(gap, height)
    in_bands = [w for w in gap if _MONTH_WORD.match(w.text) or _dates_in_text(w.text)]
    top = min((w.y for w in in_bands), default=None)
    found: list[tuple[float, str]] = []
    for line in lines:
        if top is not None and line[0].y < top - 3.4 * height * 1.6:
            continue
        text, spans = "", []
        for w in line:
            spans.append((len(text), len(text) + len(w.text), w))
            text += w.text + " "
        for m in _GROUP.finditer(text):
            hit = [w for a, b, w in spans if a < m.end() and b > m.start()]
            if hit:
                found.append((sum(w.xc for w in hit) / len(hit), m.lastgroup))
    return found


def column_kinds(columns: list[Column], dates: list[date | None], phrases: list[tuple[float, str]], march: bool) -> None:
    """Set each column's date and kind. A kind comes from the nearest group phrase when it is clearly nearest, else from the
    standard layout of the page's dates; a column whose two sources disagree has no kind."""
    from .pdf_referee import _pattern_kinds
    kinds_seen = {k for _, k in phrases}
    pattern = None
    if dates and all(d is not None for d in dates):
        pattern = _pattern_kinds(list(dates), march)
    for j, c in enumerate(columns):
        c.date = dates[j] if j < len(dates) else None
        c.read_date = c.date
        near: str | None = None
        confident = False
        if phrases:
            ranked = sorted(phrases, key=lambda p: abs(p[0] - c.xc))
            best = ranked[0]
            others = [p for p in ranked[1:] if p[1] != best[1]]
            if len(kinds_seen) == 1:
                near, confident = best[1], True
            elif not others or abs(best[0] - c.xc) <= 0.6 * abs(others[0][0] - c.xc):
                near, confident = best[1], True
        patt = pattern[j] if pattern else None
        if near and patt and near != patt:
            c.kind, c.kind_confident = None, False
            c.date = None          # the sources disagree about this column: it is not used
        elif near:
            c.kind, c.kind_confident = near, True
        elif patt:
            c.kind, c.kind_confident = patt, True
        else:
            c.kind, c.kind_confident = None, False


# A unit line that is only the unit word with the rupee sign glued to it, often garbled by the scanner's text layer: "tlakhs" for
# "₹ lakhs" (TATAELXSI Q2FY27), "(₹crore)", "Rs.lakhs". The whole short line, nothing else.
_GLUED_UNIT = re.compile(r"^[(\[{]?\s*(?:[t₹{~`]|rs\.?|inr)\s*(crores?|lakhs?|lacs?|millions?)\s*[)\]}]?$", re.I)

# A unit line that names no currency, or names it after the unit: "(Figures in Million , except per share data, unless stated
# otherwise)", "(Figures in Million ₹, except ...)" (SONACOMS Q2FY27, standalone and consolidated).
# The unit word may be followed only by a comma, a bracket, "except" or "unless", so "figures in million tonnes" is not money.
_FIGURES_IN_UNIT = re.compile(r"^[(\[]?\s*(?:all\s+)?(?:figures|amounts?)\s+(?:are\s+)?in\s+(crores?|lakhs?|lacs?|millions?|mn|thousands?)"
                              r"(?:\s*(?:₹|rs\.?|inr))?\s*(?:$|[,)\]]|except\b|unless\b)", re.I)

# "(Amount in Rupees lakhs)" with OCR's spellings of the words around the unit ("Amunt in Rupees lakhs", "Amount in Rupces
# lakhs", NEWGEN Q2FY27): the whole short line; the unit word itself must be clear
_AMOUNT_IN_RUPEES = re.compile(r"^[(\[{]?\s*am[a-z]{1,5}\s+in\s+r[a-z]{3,6}\s+(crores?|lakhs?|lacs?|millions?)\s*[)\]}]?$", re.I)


def scan_units(lines: list[str]) -> set:
    """The units named by short unit lines (a lost rupee sign, a garbled word: "t in crore", "({ in Lakh except per Share
    data)"), as ``pdf_referee`` reads them; a unit it does not know is None."""
    from .pdf_referee import _BARE_UNIT, _GARBLED_UNIT
    from .grounding import _PER_CRORE
    found = set()
    for line in lines:
        probe = line.strip()
        if len(probe) <= 70 and (m := _GARBLED_UNIT.match(probe)):
            found.add(_PER_CRORE.get(m[1].lower().rstrip("s")))
        clean = re.sub(r"^[^\w]+|[^\w.)]+$", "", probe)
        if len(clean) <= 40 and (m := _BARE_UNIT.match(clean)):
            found.add(_PER_CRORE.get(m[1].lower().rstrip("s.").rstrip("s")))
        elif len(probe) <= 16 and (m := _GLUED_UNIT.match(probe)):
            found.add(_PER_CRORE.get(m[1].lower().rstrip("s")))
        elif len(probe) <= 100 and (m := _FIGURES_IN_UNIT.match(probe)):
            found.add(_PER_CRORE.get(m[1].lower().rstrip("s")))
        elif len(probe) <= 40 and (m := _AMOUNT_IN_RUPEES.match(probe)):
            found.add(_PER_CRORE.get(m[1].lower().rstrip("s")))
    return found


def unit_of(lines: list[str], page_lines: list[str]) -> float | None:
    """Figures per crore: the unit declared above the table (``grounding.unit_before``, then the short unit lines a lost rupee
    sign or a garbled word leave), else the one unit the page names anywhere; None when none, or two."""
    from .grounding import _DECLARED_UNIT, _PER_CRORE, unit_before
    text = "\n".join(lines)
    u = unit_before(text, len(text))
    if u is not None:
        return u
    units = scan_units(lines)
    if len(units) == 1 and None not in units:
        return units.pop()
    page_text = "\n".join(page_lines)
    found = {_PER_CRORE.get(next(g for g in m.groups() if g).lower().rstrip("s")) for m in _DECLARED_UNIT.finditer(page_text)}
    found |= scan_units(page_lines)
    return found.pop() if len(found) == 1 and None not in found else None


# --- a page into tables ---------------------------------------------------------------------------------------------------


def date_parts(words: list[Word], height: float) -> set[int]:
    """The ids of day numbers that are part of a header date, never figures: a whole number of one or two digits right after
    a month word on its line ("Sept 30" over "2026" in KIRLPNU Q2FY27, whose days made a row of 30s that cut the header
    off the table)."""
    out: set[int] = set()
    ordered = sorted(words, key=lambda w: (round(w.y / max(height, 1.0)), w.x0))
    for prev, w in zip(ordered, ordered[1:]):
        if re.fullmatch(r"\d{1,2},?", w.text) and _MONTH_WORD.match(prev.text) and abs(prev.y - w.y) <= 0.5 * height \
                and 0 <= w.x0 - prev.x1 <= height:
            out.add(id(w))
    return out

def tables_of_page(page_no: int, words: list[Word], anywhere: bool, source: str = "textlayer") -> list[Table]:
    """The tables of one page: numeric rows, split where a header with dates stands between two rows, each with its columns'
    dates and kinds, its basis, its unit and its stitched labels."""
    from .pdf_referee import _MARCH_YEAR, _basis_above_boxed
    from .metrics import STANDALONE
    if len(words) < 12:
        return []
    height = text_height(words)
    words = merge_space_groups(merge_brackets(words, height), height)
    dated = date_parts(words, height)
    cellable = [w for w in words if id(w) not in dated]
    figs = [(w, c) for w in cellable if (c := parse_figure(w.text)) is not None and not c.nil]
    columns, align = find_columns(figs, height)
    if len(columns) < 2:
        return []
    extra = whole_number_columns(figs, columns, align, cellable, height)
    if extra:
        columns = sorted(columns + extra, key=lambda c: c.xc)
        for i, c in enumerate(columns):
            c.index = i
    assigned = decimals_filter(assign_cells(cellable, columns, align, height), len(columns))
    rows = build_rows(assigned, words, columns, height)
    if len(rows) < 3:
        return []
    used = {id(w) for _, w, _ in assigned}
    free = [w for w in words if id(w) not in used]
    page_texts = [line_text(line) for line in lines_of(words, height)]
    pitch = statistics.median([b.y - a.y for a, b in zip(rows, rows[1:]) if b.y > a.y] or [2 * height])
    sep = typical_gap(words, height)
    # where a header stands: a gap between two numeric rows with dates over at least two columns
    starts = [0]
    gaps: dict[int, list[Word]] = {}
    wide: dict[int, list[Word]] = {}
    for i, r in enumerate(rows):
        lower = rows[i - 1].bottom if i else r.top - LABEL_WORDS_LINES * pitch
        gap = [w for w in free if lower < w.y < r.top]
        gaps[i] = gap
        wide[i] = [w for w in free if (rows[i - 1].bottom if i else -1e9) < w.y < r.top]
        if i:
            dated = sum(d is not None for d in column_dates(gap, columns, height, sep))
            if dated >= 2:
                starts.append(i)
    tables: list[Table] = []
    for n, a in enumerate(starts):
        b = starts[n + 1] if n + 1 < len(starts) else len(rows)
        gap = gaps[a]
        dates = column_dates(gap, columns, height, sep)
        texts = [line_text(line) for line in lines_of(wide[a], height)]
        march = bool(_MARCH_YEAR.search("\n".join(texts[-14:])))
        if sum(d is not None for d in dates) < 2:
            continue
        gap_lines = lines_of(gap, height)
        cols = [Column(c.x0, c.x1, c.xc, c.index, whole=c.whole) for c in columns]
        column_kinds(cols, dates, group_phrases(gap, cols, height), march)
        fill_corresponding_quarter(cols)
        basis, contested = _basis_above_boxed(texts, len(texts))
        if basis and any(_NON_CONSOLIDATED.search(x) for x in [" ".join(texts)] + texts):
            basis, contested = None, True     # "Non-Consolidated Financial Results" names neither as a word (22nd review)
        if basis is None and not anywhere and not contested:
            basis = STANDALONE
        rows_t = [NRow(r.y, r.top, r.bottom, "", list(r.cells)) for r in rows[a:b]]
        header_bottom = max((w.y for w in gap if any(abs(w.xc - c.xc) < 0.5 * (c.x1 - c.x0 + 4 * height) for c in cols)), default=None)
        stitch_labels(rows_t, free, cols, set(), height, header_bottom)
        unit = unit_of(texts, page_texts)
        tables.append(Table(page_no, basis, unit, cols, rows_t, source, header_lines=texts, contested=contested))
    return tables


# --- the stitched label's landmark (the second signal) --------------------------------------------------------------------

_CLASS_RULES: list[tuple[str, re.Pattern]] = [
    # before the PAT rule: "Share of profit of associates after tax" is an associate's share, not a profit (ninth review);
    # a row number may lead it ("04. Share of net profit of associates", ATUL Q2FY27)
    ("ASSOC", re.compile(r"^\W*(?:[a-z\d]{1,4}\W+)?(?:add:?\s*|less:?\s*)?share\s+(?:of|in)\b.*\b(?:associates?|joint\s+ventures?)", re.I)),
    ("EPS", re.compile(r"earnings?\s+per|\beps\b|per\s+(?:equity\s+)?share", re.I)),
    ("TCI", re.compile(r"comprehensive|\boci\b", re.I)),          # "Profit after tax and OCI" is a total comprehensive income
    ("PAT", re.compile(r"(?:profit|loss)\b.*\bfor\s+the\s+(?:period|year|quarter)\b.*continuing\s+and\s+discontinu", re.I)),
    ("ATTR", re.compile(r"attributable|owners\s+of|non[- ]?controlling|minority|equity\s+holders", re.I)),
    ("DISC", re.compile(r"discontinu", re.I)),
    ("PBEI", re.compile(r"before\b.*\b(?:exceptional|extraordinary|share\s+of|associates?|joint\s+ventures?)", re.I)),
    ("PBT", re.compile(r"before\s+(?:\w+\s+){0,3}tax|\bpbt\b", re.I)),
    ("TAX", re.compile(r"^(?!.*\b(?:profit|loss|surplus)\b).*\btax", re.I)),      # a tax line: no profit or loss in its words
    ("CONT", re.compile(r"continuing", re.I)),
    ("PAT", re.compile(r"(?:profit|loss|surplus)\b.*\b(?:for\s+the\s+(?:period|year|quarter)|after\s+tax)|\bpat\b|net\s+profit", re.I)),
    ("TE", re.compile(r"total\s+(?:expenses|expenditure)", re.I)),
    ("TI", re.compile(r"total\s+income|total\s+revenue\b(?!\s+from\s+operations)", re.I)),
    ("OI", re.compile(r"other\s+income", re.I)),
    ("EXC", re.compile(r"exceptional|extraordinary", re.I)),
    ("ASSOC", re.compile(r"associate|joint\s+venture", re.I)),
    ("TAX", re.compile(r"\btax\b|taxation", re.I)),
    ("REV", re.compile(r"revenue|net\s+sales|\bsales\b|turnover|interest\s+earned|income\s+from\s+operations", re.I)),
]


def label_class(label: str) -> str | None:
    """The landmark a stitched label names: TI total income, TE total expenses, REV revenue, OI other income, PBEI profit before
    exceptional items (or associates) and tax, PBT profit before tax, EXC exceptional items, ASSOC share of associates, TAX a tax
    line, PAT profit for the period, TCI comprehensive income, ATTR a split between owners and minority, DISC / CONT
    discontinued / continuing operations, EPS; None when the label names none (a bare "Total", "(I+II)", a garbled word)."""
    text = re.sub(r"\s+", " ", label or "").strip()
    if not re.search(r"[A-Za-z]{3,}", text):
        return None
    for name, rule in _CLASS_RULES:
        if rule.search(text):
            return name
    return None


# --- the vertical arithmetic solver -----------------------------------------------------------------------------------------

Proof = tuple[int, tuple[tuple[int, int], ...]]        # (row that equals, ((row, sign), ...) its parts)


# a revenue row that opens a list of its parts: "1 Revenue from operations (a) Interest income", "Revenue from Operations
# (i) Interest Income", "Revenue from operations: a) Sales"
# (a list's first marker: "(a)", "a)", "[a]", "a.", "(i)", "i.", "(1)" - a numbered one is a note reference when "refer" or
# "note" follows it; a lettered or roman one never is, whatever word follows: "(a) Note income" is a part, nineteenth review)
_ITEM_MARK = r"(?:\(?[a-z]\)|\[[a-z]\]|[a-z]\.|\(?[ivx]{1,5}\)|[ivx]{1,5}\.|\(?\d{1,2}\)(?!\s*(?:refer|notes?|see)\b))"
# the marker is followed by the first part's name; a total is never a list ("Total Revenue from Operations (1)", EMKAY Q2FY25)
_REVENUE_LIST = re.compile(r"(?<!total\s)revenue\s+from\s+operations?(?:\s*\((?:refer\s+)?notes?\s*\d+\))?\W{0,3}" + _ITEM_MARK
                           + r"\s*[a-z]", re.I)
# a row that is an item of a list ("(c) Other income", "iv) Others", "B. Other income"): after a revenue list it may be one of
# its parts; a capital roman numeral with a dot ("II. Other income") numbers the statement's own lines and is not one
_LIST_ITEM = re.compile(r"^\W*" + _ITEM_MARK, re.I)
_TOTAL_REVENUE = re.compile(r"^\W*(?:[\divx]+\W+)?total\s+revenue\s+from\s+operations?\W*(?:\(\w{1,4}\))?\W*$", re.I)
def not_revenue_line(label: str) -> bool:
    """A line that cannot be a part of revenue, by an allow-list (25th review: a gain on fair value changes or on
    derecognition is a revenue part in an NBFC's statement): a foreign-exchange gain or loss ("Foreign exchange gain (net)",
    SONACOMS Q2FY27), or "Other" and OCR's spelling of "income", one letter off ("Other incume", NEWGEN Q2FY27)."""
    if re.search(r"\b(?:gains?|loss(?:es)?)\b", label, re.I) and re.search(r"\b(?:foreign\s+exchange|exchange|forex|currency)\b", label, re.I) \
            and not re.search(r"\b(?:fair\s+value|derecogni|investments?|securities|sales?|services?|fees?|interest|dividend)", label, re.I):
        return True
    m = re.match(r"^\W*other\s+([a-z]{6})\W*$", label, re.I)
    return bool(m) and sum(x != y for x, y in zip(m[1].lower(), "income")) == 1


# a whole revenue line: the label ends with the revenue's own name (a note or "(net)" in brackets may follow)
_WHOLE_REVENUE = re.compile(r"(?:revenue|income|sales)\s+from\s+operations?\W*(?:\((?:net|gross|refer[^)]*|notes?[^)]*)\)\W*)?$", re.I)


def list_item(label: str) -> bool:
    return bool(_LIST_ITEM.match(label)) and not re.match(r"^\W*[IVX]{1,4}\.\s", label)


class Solver:
    """Names the rows of one table by the identities that hold down its columns. ``explanations`` maps a metric to its readings
    of the table: a list of (rows, proofs); a proof is an identity checked again in the period's own column when a figure is
    asked, so a row is never named on other columns' proof alone."""

    def __init__(self, table: Table):
        self.t = table
        self.n = len(table.rows)
        self.m = len(table.columns)
        self.cls = [label_class(r.label) for r in table.rows]
        self.explanations: dict[str, list[tuple[tuple[int, ...], list[Proof]]]] = {}
        self.pat_unsure = False          # a profit carried on by arithmetic alone (``carried_on``): no profit from the table
        self.chains = 0

    # --- identities
    def cell(self, i: int, j: int) -> Cell | None:
        return self.t.rows[i].cells[j]

    def mask(self, proof: Proof) -> list[bool | None]:
        target, parts = proof
        out: list[bool | None] = []
        for j in range(self.m):
            a = self.cell(target, j)
            cs = [(self.cell(r, j), s) for r, s in parts]
            if a is None or any(c is None for c, _ in cs):
                out.append(None)
                continue
            total = sum(s * c.value for c, s in cs)
            tol = a.tol + sum(c.tol for c, _ in cs) + 1e-9
            out.append(abs(a.value - total) <= tol)
        return out

    def valid(self, proof: Proof) -> bool:
        """The identity holds in at least three columns (all of them when fewer can be checked), is broken in at most one, and is
        not made of zeros."""
        mask = self.mask(proof)
        checked = sum(v is not None for v in mask)
        holds = sum(v is True for v in mask)
        fails = sum(v is False for v in mask)
        if checked < 2 or holds < min(IDENT_MIN_COLUMNS, checked) or fails > (1 if holds >= 3 else 0):
            return False
        target, _ = proof
        return sum(1 for j, v in enumerate(mask) if v is True and (c := self.cell(target, j)) is not None and abs(c.value) > 1e-9) >= 2

    def label_ok(self, i: int, allowed: set) -> bool:
        """The label does not name another landmark than the arithmetic does (a label naming none is no objection)."""
        return self.cls[i] in allowed or self.cls[i] is None

    # --- the chain
    def add(self, metric: str, rows: tuple[int, ...], proofs: list[Proof]) -> None:
        entry = (rows, proofs)
        if entry not in self.explanations.setdefault(metric, []):
            self.explanations[metric].append(entry)

    HOP_OK = {None, "EXC", "ASSOC", "TAX"}

    def hops(self, start: int, depth: int = 3) -> list[tuple[int, list[Proof]]]:
        """Rows reached from ``start`` by hops over one to three rows between (each counted + or -): the row equals the row
        before it plus or minus the rows in between. ``start`` itself is reached with no hop."""
        found: list[tuple[int, list[Proof]]] = [(start, [])]
        frontier = [(start, [])]
        for _ in range(depth):
            nxt = []
            for pos, proofs in frontier:
                # a profit before tax printed as the same figure as the line above it: an exceptional item or an associate's
                # share that is nil in most columns is a row of one cell, which is not a numeric row; the label must say so
                x = pos + 1
                if x < self.n and self.cls[x] == "PBT" and all(x != f[0] for f in found):
                    proof: Proof = (x, ((pos, 1),))
                    if self.valid(proof):
                        item = (x, proofs + [proof])
                        found.append(item)
                        nxt.append(item)
                for x in range(pos + 2, min(self.n, pos + 5)):
                    between = list(range(pos + 1, x))
                    if any(self.cls[r] not in self.HOP_OK for r in between):
                        continue
                    for signs in itertools.product((1, -1), repeat=len(between)):
                        proof: Proof = (x, ((pos, 1),) + tuple(zip(between, signs)))
                        if self.valid(proof):
                            if all(x != f[0] for f in found):
                                item = (x, proofs + [proof])
                                found.append(item)
                                nxt.append(item)
                            break
            frontier = nxt
        return found

    def tax_and_pat(self, b: int) -> list[tuple[int, tuple[int, ...], Proof]]:
        """(PAT row, tax rows, proof) after the profit before tax row ``b``: PAT = PBT - the sum of a block of the rows between."""
        out = []
        a = b + 1
        if a < self.n and self.cls[a] in ("PAT", "CONT"):
            equal: Proof = (a, ((b, 1),))
            if self.valid(equal):         # no tax at all (its rows are nil in all but one column): the profit after tax is the same figure
                out.append((a, (), equal))
        for a in range(b + 1, min(self.n, b + 8)):
            between = list(range(b + 1, a))
            if not between or any(self.cls[r] not in {None, "TAX"} for r in between) or not self.label_ok(a, {"PAT", "CONT"}):
                continue
            best = None
            for size in range(1, len(between) + 1):
                for s in range(0, len(between) - size + 1):
                    block = tuple(between[s:s + size])
                    proof: Proof = (a, ((b, 1),) + tuple((r, -1) for r in block))
                    if best is None and self.valid(proof):
                        best = (block, proof)
                if best:
                    break
            if best is None:
                continue
            block, proof = best
            moved = any(self.cell(r, j) is not None and abs(self.cell(r, j).value) > 1e-9 for r in block for j in range(self.m))
            if not moved and not any(self.cls[r] == "TAX" for r in block):
                continue            # no tax and no row that says tax: this "profit after tax" would be a repeat of the profit before
            out.append((a, block, proof))
        return out

    def carried_on(self, a: int):
        """Whether the profit after tax ``a`` is carried on further down: "label" when the row after it is an associate's share
        or discontinued operations that is not nil (EMKAY Q2FY25: "IX Profit after tax" 2,581.77, "X Share of Profit of
        Associates" 9.39, the profit for the period 2,591.16), then only an extension that reaches the bottom line may be the
        profit; or ``(x, proof)`` when only the arithmetic says so: a later row ``x`` equals the profit plus or minus one or two
        non-nil rows between, whatever their labels (ninth review: a garbled share label, a nil row between, an exceptional
        item after tax). The arithmetic cannot tell that from a total comprehensive income with a garbled label (= profit +
        other comprehensive income, tenth review), so then ``a`` and ``x`` are both offered and the reading is a conflict:
        no answer either way. None when neither."""
        def nonzero(r: int) -> bool:
            return any(c is not None and abs(c.value) > 1e-9 for c in self.t.rows[r].cells)

        nxt = a + 1
        if nxt < self.n and self.cls[nxt] in ("ASSOC", "DISC") and nonzero(nxt):
            return "label"
        for x in range(a + 2, min(self.n, a + 13)):
            between = list(range(a + 1, x))
            if any(self.cls[r] in ("TCI", "ATTR", "EPS") for r in between):
                break
            if self.cls[x] in ("TCI", "ATTR", "EPS", "TE", "TI"):
                continue
            live = [r for r in between if nonzero(r)]
            for size in (1, 2, 3):
                for subset in itertools.combinations(live, size):
                    for signs in itertools.product((1, -1), repeat=size):
                        proof: Proof = (x, ((a, 1),) + tuple(zip(subset, signs)))
                        if self.valid(proof):
                            return (x, proof)
        return None

    def covered(self, skipped: list[int], subset: tuple[int, ...]) -> bool:
        """Every non-nil row the sum leaves out is a part of a subtotal it takes in: some row of ``subset`` equals the left-out
        rows plus or minus each other (ABREL: 14 = 11 + 13, so 15 = 9 + 14 may leave 11 and 13 out). A left-out row no subtotal
        accounts for is a profit or a tax the sum skipped (fourteenth review), and the row is not the profit for the period."""
        if not skipped:
            return True
        if len(skipped) > 3:
            return False
        for s_row in subset:
            if s_row < max(skipped):     # a subtotal stands below its parts (fifteenth review: a gross row is not one)
                continue
            for signs in itertools.product((1, -1), repeat=len(skipped)):
                if self.valid((s_row, tuple(zip(skipped, signs)))):
                    return True
        return False

    def pat_extensions(self, a: int) -> list[tuple[int, list[Proof]]]:
        """Rows after the profit after tax ``a`` that equal it plus or minus the rows between (discontinued operations, an
        associate's share): the row's label names the profit (not merely does not object), every row between is an associate's
        share, discontinued operations, an exceptional item or a tax line, or nil, and the sum takes in every non-nil
        associate's share between (eleventh review: a garbled total comprehensive income or an identity
        that skips the share is not the profit)."""
        out = []
        for x in range(a + 2, min(self.n, a + 9)):
            between = list(range(a + 1, x))
            live = [r for r in between if any(c is not None and abs(c.value) > 1e-9 for c in self.t.rows[r].cells)]
            if self.cls[x] != "PAT" or any(self.cls[r] not in {"DISC", "ASSOC", "EXC", "TAX"} for r in live):
                continue
            # every associate's share between must be in the sum; a discontinued block has its parts and their subtotal
            # (ABREL Q2FY27: 15 = 9 + 14, where 14 is the net of 11 and 13), so it is not asked for row by row
            needed = {r for r in live if self.cls[r] == "ASSOC"}
            for size in (1, 2):
                hit = None
                for subset in itertools.combinations(live, size):
                    if not needed <= set(subset) or not self.covered([r for r in live if r not in subset], subset):
                        continue
                    for signs in itertools.product((1, -1), repeat=size):
                        proof: Proof = (x, ((a, 1),) + tuple(zip(subset, signs)))
                        if hit is None and self.valid(proof):
                            hit = proof
                if hit:
                    out.append((x, [hit]))
                    break
        return out

    def solve(self) -> "Solver":
        for t in range(1, self.n):
            for k in (2, 3):
                if t - k < 0:
                    continue
                parts = tuple((r, 1) for r in range(t - k, t))
                ti_proof: Proof = (t, parts)
                if not self.label_ok(t, {"TI"}) or not self.valid(ti_proof):
                    continue
                if k == 3 and self.valid((t, parts[1:])):
                    continue
                self.chain_from(t, k, ti_proof)
            self.nested_income(t)
            self.parts_income(t)
            self.bank_income(t)
        if "total_income" not in self.explanations:
            # no chain below it: a total income by its label AND the arithmetic (never the label alone)
            for t in range(1, self.n):
                if self.cls[t] != "TI":
                    continue
                for k in (2, 3):
                    if t - k >= 0:
                        proof: Proof = (t, tuple((r, 1) for r in range(t - k, t)))
                        if self.valid(proof):
                            self.name_income(t, k, proof)
                            break
        return self

    def nested_income(self, t: int) -> None:
        """Total income = revenue + an other-income subtotal printed with its parts between them (PRIMESECU Q4FY24: "I Revenue
        from Operations" 1,136, "II Other Income" i) to iv), "Total Other Income" 146, "III Total income (I+II)" 1,282): the
        row above the total says other income and is the sum of the two to eight rows between (its own identity), and the row
        before those does not say anything but revenue."""
        if t < 1 or self.cls[t - 1] != "OI" or not self.label_ok(t, {"TI"}):
            return
        for size in range(2, 9):
            r = t - 2 - size
            if r < 0:
                return
            sub: Proof = (t - 1, tuple((x, 1) for x in range(r + 1, t - 1)))
            proof: Proof = (t, ((r, 1), (t - 1, 1)))
            if self.label_ok(r, {"REV"}) and self.valid(sub) and self.valid(proof):
                self.chain_from(t, (r, t - 1), proof)
                return

    def parts_income(self, t: int) -> None:
        """Total income = revenue printed only as its parts + other income, with no line for the revenue itself (BFINVEST
        Q2FY25: "1 Revenue from operations (a) Interest income" 57.46, "(b) Dividend income" 655.73, "(c) Net gain on fair
        value changes" 24.86, "2 Other income" 7.02, "3 Total income (1+2)" 745.07): the first row says revenue from
        operations and opens a list ("(a)", "(i)", "a)"), the rows after it say nothing (no landmark), the row above the total
        says other income, and all of them add up to the total. The revenue is the sum of the parts."""
        if not self.label_ok(t, {"TI"}) or t < 1 or self.cls[t - 1] != "OI":
            return
        for k in range(3, 9):
            first = t - k
            if first < 0:
                return
            parts = tuple(range(first, t - 1))
            if self.cls[first] != "REV" or not _REVENUE_LIST.search(self.t.rows[first].label):
                continue
            if list_item(self.t.rows[t - 1].label):
                return          # "(d) Other income": a part of the revenue list or not, the labels cannot tell
            if any(self.cls[r] is not None for r in parts[1:]):
                return
            proof: Proof = (t, tuple((r, 1) for r in range(first, t)))
            if self.valid(proof):
                self.chain_from(t, (parts, t - 1), proof)
            return

    _OF_WHICH = re.compile(r"^\W*(?:\w{1,2}\W+)?of\s+which\b", re.I)

    def bank_hops(self, start: int) -> list[tuple[int, list[Proof]]]:
        """Rows reached from ``start`` over the rows between that are not "Of which ..." lines: a bank's provisions are followed by
        "Of which provisions for non-performing assets", a part of the provisions that is not taken off again (UNIONBANK).
        Only the rows between that do not say "of which" are in the sum; the identity is the table's own."""
        found: list[tuple[int, list[Proof]]] = []
        for x in range(start + 2, min(self.n, start + 6)):
            between = list(range(start + 1, x))
            used = [r for r in between if not self._OF_WHICH.match(self.t.rows[r].label)]
            if len(used) == len(between) or not 1 <= len(used) <= 3 or any(self.cls[r] not in self.HOP_OK for r in used):
                continue
            for signs in itertools.product((1, -1), repeat=len(used)):
                proof: Proof = (x, ((start, 1),) + tuple(zip(used, signs)))
                if self.valid(proof):
                    found.append((x, [proof]))
                    break
        return found

    BANK_LEVEL = re.compile(r"operating\s+profit|profit\s+before\s+provision", re.I)
    BANK_SEGMENT = re.compile(r"segment|treasury|retail\s+banking|wholesale|corporate\s*/?\s*(?:wholesale\s+)?banking", re.I)

    BANK_CARRIED = re.compile(r"associate|minorit|share\s+(?:of|in)\b|discontinu", re.I)

    def bank_carried_on(self, a: int) -> bool:
        """A row after a bank's profit after tax ``a`` that is an associate's share, a minority's share or discontinued
        operations and is not nil (or is unreadable): the bottom line is further down, so ``a`` is not the profit."""
        for r in range(a + 1, min(self.n, a + 9)):
            label = re.sub(r"before\s+minorit\w*", "", self.t.rows[r].label, flags=re.I)   # "profit for the period before minority interest"
            if self.cls[r] in ("ASSOC", "DISC") or self.BANK_CARRIED.search(label):
                if any(c is None or abs(c.value) > 1e-9 for c in self.t.rows[r].cells):
                    return True
        return False

    def parts_sum(self, head: int, first: int, last: int) -> bool:
        """The rows ``first``..``last`` (the printed parts of the row ``head``) add up to it; no parts is also fine."""
        return first > last or self.valid((head, tuple((r, 1) for r in range(first, last + 1))))

    def bank_income(self, t: int) -> None:
        """A bank's statement (RBI format): "1 Interest earned (a)+(b)+(c)+(d)" printed over its parts, "2 Other income" (also over
        its parts, ICICI's group), "3 Total income (1+2)" = the two; "4 Interest expended", "5 Operating expenses" (over its
        parts), "6 Total expenditure (4+5)"; "7 Operating profit (3-6)", then provisions and the exceptional items down to the
        profit before tax, the tax and the profit after tax. Every identity is the table's own (the parts of each line
        add up to it, the totals are sums of the two lines), so the chain runs through eight or more of them. The two-row
        sums of a corporate chain cannot see it: the parts stand between the lines. Revenue is the interest earned (the
        bench key's revenue for a bank), other income the second line."""
        if not self.label_ok(t, {"TI"}):
            return
        for b in range(t - 1, max(t - 5, 0), -1):
            if not self.label_ok(b, {"OI"}) or not self.parts_sum(b, b + 1, t - 1):
                continue
            for a in range(b - 1, max(b - 9, -1), -1):
                if not self.label_ok(a, {"REV"}) or not self.parts_sum(a, a + 1, b - 1):
                    continue
                ti_proof: Proof = (t, ((a, 1), (b, 1)))
                if b - a < 2 or not self.valid(ti_proof):
                    continue            # the parts stand between them: adjacent rows are the corporate chain's
                self.bank_chain_from(t, a, b, ti_proof)

    def bank_chain_from(self, t: int, a: int, b: int, ti_proof: Proof) -> None:
        for c in (t + 1, t + 2):                      # interest expended
            for e in range(c + 2, min(self.n, c + 12)):    # total expenditure = interest expended + operating expenses
                if not self.label_ok(e, {"TE"}):
                    continue
                for d in range(c + 1, e):
                    te_proof: Proof = (e, ((c, 1), (d, 1)))
                    if not self.parts_sum(d, d + 1, e - 1) or not self.valid(te_proof):
                        continue
                    if any(self.BANK_SEGMENT.search(self.t.rows[r].label) for r in range(a, e + 1)):
                        continue            # a segment table has its own chain: never a bank's statement of results
                    for p in range(e + 1, min(self.n, e + 4)):      # operating profit
                        p_proof: Proof = (p, ((t, 1), (e, -1)))
                        if not self.label_ok(p, {"PBEI", "PBT", "TAX", "EXC"}) or not self.valid(p_proof):
                            continue
                        self.chains += 1
                        pending: list = [("expenses", (e,), [te_proof]), ("total_income", (t,), [p_proof]),
                                         ("total_income", (t,), [ti_proof]), ("revenue", (a,), [ti_proof]),
                                         ("other_income", (b,), [ti_proof])]
                        completed = self.profit_tail(p, p_proof, pending, bank=True)
                        said = self.cls[t] == "TI" or self.cls[e] == "TE" or any(
                            self.cls[x] == "PBT" for x, _ in self.hops(p))
                        if not (said or completed):
                            continue
                        for metric, rows, proofs in pending:
                            self.add(metric, rows, proofs)

    def name_income(self, t: int, k, proof: Proof) -> None:
        """``k``: the number of rows right above the total that add up to it, or the (revenue, other income) rows of a nested
        total (``nested_income``: one revenue row) or of revenue printed as its parts (``parts_income``: a tuple of rows)."""
        self.add("total_income", (t,), [proof])
        if isinstance(k, tuple) and isinstance(k[0], tuple):
            self.add("revenue", k[0], [proof])
            self.add("other_income", (k[1],), [proof])
            return
        rows = list(k) if isinstance(k, tuple) else list(range(t - k, t))
        # a revenue row that opens a list of its parts is only the first part: never the revenue (BFINVEST Q2FY25)
        rows_rev_ok = not any(self.cls[r] == "REV" and _REVENUE_LIST.search(self.t.rows[r].label) for r in rows)
        # nor is one followed by a row that is an item of a list ("I. Interest income", "[a] Sales" after "Revenue from
        # operations"): the revenue row may be a heading over its parts (nineteenth review)
        # nor is one followed by a row that says nothing (no landmark): "Revenue from operations" over "(a) Sales" and
        # "Dividend income" or "- Fees" may be a heading over its parts, whatever marks them or none (twentieth review)
        # nor one with a row that says nothing above it ("Interest income" over "Net sales": the revenue is both, twenty-first)
        # A row that says nothing BELOW a whole revenue line ("Revenue from operations" and nothing after it: a line with its own
        # figures) is another line of income, not a part (SONACOMS Q2FY27: "Foreign exchange gain (net)"; NEWGEN: OCR's
        # "Other incume"); below a heading joined to its first part ("Revenue from operations Sale of products") it may be one
        rev_at = [i for i, r in enumerate(rows) if self.cls[r] == "REV"]
        if rev_at:
            first = rev_at[0]
            if any(self.cls[r] is None for r in rows[:first]):
                rows_rev_ok = False
            elif any(self.cls[r] is None and not not_revenue_line(self.t.rows[r].label) for r in rows[first + 1:]) \
                    or not _WHOLE_REVENUE.search(self.t.rows[rows[first]].label) and any(self.cls[r] is None for r in rows[first + 1:]):
                rows_rev_ok = False
        if len(rows) == 2:
            # a revenue row right above the sum and outside it: the first row is not the revenue (22nd review: "Revenue from
            # operations" over "Interest income" + "Other income" = a total that leaves the revenue out)
            above = min(rows) - 1
            # unless the first row is the subtotal of the rows right above it ("a. Sale of products", "b. Other operating
            # revenues", "Total Revenue from operations", SRF Q2FY27): then the revenue row above is one of its parts
            # (the subtotal says revenue itself and holds in every column it can be checked in: no broken column is
            # tolerated here, 27th review)
            def strict(proof: Proof) -> bool:
                return self.valid(proof) and False not in self.mask(proof)
            subtotal = self.cls[rows[0]] == "REV" and any(
                strict((rows[0], tuple((r, 1) for r in range(above - size + 1, above + 1)))) for size in range(1, 7)
                if above - size + 1 >= 0 and all(self.cls[r] != "OI" for r in range(above - size + 1, above + 1)))
            # (an other-income row right above is the same doubt: "Total revenues" may take it in, 28th review)
            # or the first row says it is the total of revenue from operations and the row above is a part of revenue, not other
            # income (BAJAJHLDNG Q4FY24: OCR lost one part, so the sum cannot be checked)
            said_total = self.cls[above] == "REV" and bool(_TOTAL_REVENUE.match(self.t.rows[rows[0]].label)) if above >= 0 else False
            if above >= 0 and self.cls[above] in ("REV", "OI") and not subtotal and not said_total:
                rows_rev_ok = False
            rev_named = self.label_ok(rows[0], {"REV"}) and rows_rev_ok
            if rev_named:
                self.add("revenue", (rows[0],), [proof])
            # a row that says nothing is the other income only beside a named revenue (22nd review)
            oi_ok = self.cls[rows[1]] == "OI" or (self.cls[rows[1]] is None and rev_named and self.cls[rows[0]] == "REV")
            # another other-income row right above: which of the two is the company's other income is not told (29th review)
            if above >= 0 and self.cls[above] == "OI":
                oi_ok = False
            if oi_ok and (rows_rev_ok or not list_item(self.t.rows[rows[1]].label)):
                self.add("other_income", (rows[1],), [proof])
        else:
            rev = [r for r in rows if self.cls[r] == "REV"]
            oi = [r for r in rows if self.cls[r] == "OI"]
            if len(rev) == 1 and rows_rev_ok:
                self.add("revenue", (rev[0],), [proof])
            # after a revenue list, "(c) Other income" may be one of its parts (eighteenth review)
            if len(oi) == 1 and (rows_rev_ok or not list_item(self.t.rows[oi[0]].label)):
                self.add("other_income", (oi[0],), [proof])

    def profit_tail(self, p: int, p_proof: Proof, pending: list, bank: bool = False) -> bool:
        """From the row ``p`` (profit before exceptional items, or a bank's operating profit): the hops to the profit before tax,
        the tax and the profit after tax are added to ``pending``. True when a profit after tax was reached. ``bank``: a profit
        carried on by a later associate's share, a minority or a discontinued block is never the bottom line (the chain's own
        arithmetic cannot name it)."""
        completed = False
        for b, hop_proofs in self.hops(p) + (self.bank_hops(p) if bank else []):
            # a bank's profit before tax shares its row with the exceptional items' line, whose label then leads the stitched
            # label (UNIONBANK: "E. Exceptional Items Profit/(Loss) from Oridnary Activi..."); the arithmetic (provisions,
            # exceptional items nil, then a tax that leads to a profit after tax) is what names it
            if not self.label_ok(b, {"PBT", "EXC"} if bank else {"PBT"}):
                continue
            # the three profit levels stay apart: the operating profit (the row ``p`` itself, or a label saying "operating") is
            # never the profit before tax
            if bank and (b == p or self.BANK_LEVEL.search(self.t.rows[b].label)):
                continue
            if self.cls[b] == "PBT":          # the label says profit before tax and the arithmetic reaches it
                pending.append(("pbt", (b,), [p_proof] + hop_proofs))
            for a, block, pat_proof in self.tax_and_pat(b):
                completed = True
                pending.append(("pbt", (b,), [p_proof] + hop_proofs))
                pending.append(("pbt", (b,), [pat_proof]))     # or: the tax identity proves it where a hop is not legible
                if block:
                    pending.append(("tax", block, [pat_proof]))
                carried = self.carried_on(a)
                if bank and not isinstance(carried, tuple) and self.bank_carried_on(a):
                    carried = (a, None)
                if isinstance(carried, tuple):
                    # the arithmetic alone says the profit is carried on, and the labels cannot tell an associate's
                    # share from a total comprehensive income (eleventh review): no profit from this table at all
                    self.pat_unsure = True
                elif self.label_ok(a, {"PAT"}) and carried != "label" \
                        and not (bank and re.search(r"operating|before", self.t.rows[a].label, re.I)):
                    pending.append(("pat", (a,), [pat_proof]))
                # a profit after tax followed by discontinued operations or associates: the bottom line is the sum
                for x, ext in self.pat_extensions(a):
                    pending.append(("pat", (x,), [pat_proof] + ext))
        return completed

    def chain_from(self, t: int, k, ti_proof: Proof) -> None:
        """Total income at row ``t`` (its identity holds): look below it for total expenses, the profit identity, the hops to
        the profit before tax, the tax and the profit after tax. The names are kept only when a label of the chain says what
        the arithmetic says (a total income, total expenses, a profit before tax) or the chain runs through to a profit after
        tax: a table of segment assets and liabilities adds up the same way (assets - liabilities = capital employed) and has
        neither."""
        for s in (t + 1, t + 2):
            for e in range(s + 2, min(self.n, s + 40)):
                te_proof: Proof = (e, tuple((r, 1) for r in range(s, e)))
                if not self.label_ok(e, {"TE"}) or not self.valid(te_proof):
                    continue
                for p in range(e + 1, min(self.n, e + 4)):
                    p_proof: Proof = (p, ((t, 1), (e, -1)))
                    if not self.label_ok(p, {"PBEI", "PBT"}) or not self.valid(p_proof):
                        continue
                    self.chains += 1
                    pending: list[tuple[str, tuple[int, ...], list[Proof]]] = [
                        ("expenses", (e,), [te_proof]), ("pbt_pre", (p,), [p_proof]),
                        # the profit identity ties total income, total expenses and the profit before exceptional items together
                        # in the period's column: where a part of a sum is not legible there, it proves each of the three alone
                        ("total_income", (t,), [p_proof]), ("expenses", (e,), [p_proof])]
                    completed = self.profit_tail(p, p_proof, pending)
                    said = self.cls[t] == "TI" or self.cls[e] == "TE" or self.cls[p] in ("PBEI", "PBT")
                    if not (said or completed):
                        continue
                    self.name_income(t, k, ti_proof)
                    for metric, rows, proofs in pending:
                        self.add(metric, rows, proofs)


# --- a PDF into tables ----------------------------------------------------------------------------------------------------

# OCR's spelling of "consolidated" as the negative check above reads it: anything like "consol" ("C0NSOLIDATED", "Consolldated",
# "Consoli-" broken over a line) counts, so a garbled title can never be taken for no consolidated statement; a false alarm
# ("console", "consolation") only costs an answer
_LOOSE_CONSOLIDATED = re.compile(r"c\W{0,2}[o0]\W{0,2}n\W{0,2}[s5]\W{0,2}[o0]\W{0,2}[l1i|!]"
                                 r"|[s5]\W{0,2}[o0]\W{0,2}[l1i|]\W{0,2}[i1l|]\W{0,2}d\W{0,2}a\W{0,2}t|group\s+financial", re.I)


def usable_dates(tables: list[Table]) -> int:
    """The most usable column dates any named table of a page has (-1 when none is named): a date the header's words dispute
    does not count (RADICO Q2FY27: its half-year columns' dates were read and disputed, so the page looked dated and its
    garbled layer was never read with OCR)."""
    # a date the layout gave, not read, does not count either (CENTRUM Q4FY24: the page then looked dated and its OCR pass,
    # which answers the year, was skipped)
    return max((sum(c.date is not None and not c.inferred for c in t.columns) for t in tables if t.named), default=-1)

def analyse(pdf_bytes: bytes, ocr_boxes=None, ocr_garbled: bool = False, max_pages: int = MAX_TEXT_PAGES,
            keep_unnamed: bool = False) -> list[Table]:
    """The solved tables of a results PDF. Every page with a text layer (the first ``max_pages``) is read from its words. A page
    with no text layer is read with OCR (``ocr_boxes(png)`` returns RapidOCR's boxes; default ``ocr_page_boxes``), in a PDF of up
    to ``SCAN_PAGE_LIMIT`` pages, at most ``MAX_OCR_PAGES`` pages in all. With ``ocr_garbled``, the scanned pages whose own text
    layer gave no named row (the layer of a scan is OCR output and often garbled) are read with OCR as well, the pages that
    ``statement_pages`` ranks first, then those with most figures, while the page budget lasts. Only tables with a named row
    are kept (``keep_unnamed`` keeps all, for diagnosis)."""
    from . import ocr
    from .pdf_readers import _pymupdf, consolidated_anywhere, names_consolidated, page_layers, statement_pages
    ocr_boxes = ocr_boxes or ocr_page_boxes
    layers = page_layers(pdf_bytes, max_pages)
    anywhere = consolidated_anywhere(layers)
    ranked = statement_pages(layers, MAX_STATEMENT_PAGES)
    scans = [p for p, layer in layers.items() if not layer.has_layer] if len(layers) <= SCAN_PAGE_LIMIT else []
    by_page: dict[int, list[Table]] = {}
    unnamed: list[int] = []
    ocr_used = 0
    fill_used = 0
    ocr_texts: dict[int, str] = {}     # the OCR text of the pages with no text layer

    def read_ocr(page, p: int) -> list[Table]:
        png = page.get_pixmap(dpi=ocr.DPI).tobytes("png")
        raw = words_from_boxes(ocr_boxes(png))
        if not layers[p].has_layer:
            ocr_texts[p] = " ".join(w[4] for w in raw)
        found = [Table_solved(t) for t in tables_of_page(p, straighten(raw, True), anywhere, "ocr")]
        if layers[p].has_layer:
            title = layer_basis(layers[p].text)
            for t in found:
                if not t.contested:            # a basis left disputed above the table stays so (22nd review)
                    t.basis = t.basis or title  # a title OCR cannot read (big type) is still in the garbled text layer
        return found

    dated = usable_dates

    def fill_from_ocr(page, tables: list[Table], layer_text: str) -> None:
        """What a page's text layer leaves out, from OCR, for its named tables (NESTLEIND Q2FY27: the title, "(₹ in million)"
        and every row label are drawn without text). Nothing is taken unless OCR is proved to see the same page as the layer:
        the page is not rotated, and OCR reads nearly every figure of the table at the layer's own place (``ocr_aligned``).
        A table with no unit, on a page whose layer names no unit at all, gets the unit of the OCR lines between the table
        above it (or the page top) and its first row, with no page-wide guess. A table whose rows mostly have no label gets,
        for each row without one, the OCR words from below the row before down to the row's own line that are not figures and
        stand outside the number columns (NESTLEIND prints its labels between the quarter and the half-year columns), and only
        when nearly every row then has a label (a partly labelled table is where a misplaced label could name a wrong row);
        the table is solved again. A unit or label the layer gives is never changed."""
        if page.rotation:
            return
        png = page.get_pixmap(dpi=ocr.DPI).tobytes("png")
        k = 72.0 / ocr.DPI
        words = straighten([(x0 * k, y0 * k, x1 * k, y1 * k, t) for x0, y0, x1, y1, t in words_from_boxes(ocr_boxes(png))], True)
        if not words:
            return
        height = text_height(words)
        lines = [(line[0].y, line_text(line)) for line in lines_of(words, height)]
        layer_names_a_unit = bool(scan_units(layer_text.splitlines())) or unit_of(layer_text.splitlines(), []) is not None
        above = 0.0
        for n, t in sorted(enumerate(tables), key=lambda e: e[1].rows[0].top):
            top_of_table, floor = t.rows[0].top, above
            above = max(above, t.rows[-1].bottom)
            if not t.named or not ocr_aligned(t, words, height):
                continue
            if t.unit is None and not layer_names_a_unit:
                t.unit = unit_of([text for y, text in lines if floor < y < top_of_table], [])
            if sum(not r.label.strip() for r in t.rows) * 2 > len(t.rows):
                def in_column(w: Word) -> bool:
                    return any(w.x1 > c.x0 - 0.5 * height and w.x0 < c.x1 + 0.5 * height for c in t.columns)
                labels = []
                for i, r in enumerate(t.rows):
                    if r.label.strip():
                        labels.append(r.label)
                        continue
                    # the row's own line and, for a wrapped label, the lines above it down from the row before
                    top = t.rows[i - 1].y + 0.5 * height if i else r.y - 0.5 * height
                    own = sorted((w for w in words if top < w.y <= r.y + 0.5 * height and not in_column(w)
                                  and parse_figure(w.text) is None), key=lambda w: (round(w.y / height), w.x0))
                    labels.append(" ".join(w.text for w in own))
                if sum(bool(lb.strip()) for lb in labels) >= OCR_LABELS_SHARE * len(t.rows):
                    for r, lb in zip(t.rows, labels):
                        r.label = lb
                    tables[n] = Table_solved(t)

    with _pymupdf().open(stream=pdf_bytes, filetype="pdf") as doc:
        for p in layers:
            page = doc[p - 1]
            if layers[p].has_layer:
                by_page[p] = [Table_solved(t) for t in tables_of_page(p, straighten(upright_words(page)), anywhere)]
                wanting = [t for t in by_page[p] if t.named and (t.unit is None or sum(not r.label.strip() for r in t.rows) * 2 > len(t.rows))]
                if wanting and fill_used < MAX_FILL_OCR_PAGES and ocr.available():
                    fill_used += 1          # its own budget: the scanned statement pages keep all of MAX_OCR_PAGES (TBZ)
                    try:
                        fill_from_ocr(page, by_page[p], layers[p].text)
                    except Exception as exc:    # noqa: BLE001 - the table keeps what its layer gave (no unit: no answer)
                        log.warning("numbers-first: OCR of a page's unit or labels failed on page %d (%s)", p, type(exc).__name__)
                if page.get_images(full=False) and (not any(t.named for t in by_page[p])
                                                     or dated(by_page[p]) < max(len(t.columns) for t in by_page[p] if t.named)):
                    # a scan's layer gave no named table, or named tables whose column dates it garbled ("30-Seo-26", TBZ
                    # Q2FY27): the page is read with OCR as well
                    unnamed.append(p)
            elif p in scans and ocr_used < MAX_OCR_PAGES:
                ocr_used += 1
                try:
                    by_page[p] = read_ocr(page, p)
                except Exception as exc:    # noqa: BLE001 - one page failing leaves the rest
                    log.warning("numbers-first: OCR failed on page %d (%s)", p, type(exc).__name__)
        if ocr_garbled:
            def figures(p: int) -> int:
                return sum(bool(re.search(r"\d", w[4])) for w in layers[p].words)
            order = sorted(unnamed, key=lambda p: (p not in ranked, -figures(p)))
            for p in order:
                if ocr_used >= MAX_OCR_PAGES:
                    break
                ocr_used += 1
                try:
                    found = read_ocr(doc[p - 1], p)
                except Exception as exc:    # noqa: BLE001
                    log.warning("numbers-first: OCR failed on page %d (%s)", p, type(exc).__name__)
                    continue
                if any(t.named for t in found):
                    # OCR's tables beside the layer's, never instead of them (third review): where both answer they must
                    # agree or the reading is a conflict, so OCR only adds an answer the layer could not give
                    by_page[p] = by_page.get(p, []) + found
    # a filing where only pages with no text layer left the basis of untitled tables unproven: once OCR has read every one of
    # them and none, like no layer, names a consolidated statement, such a table is standalone (CMPDI and RIR Q2FY27, whose
    # statements are scans and whose covering letters say "Standalone")
    # (seventh review) only with positive evidence, the word standalone somewhere in the filing, and only for the tables OCR
    # read from those pages themselves: a blank page cannot switch it on for the typed pages
    no_layer = [p for p, layer in layers.items() if not layer.has_layer]
    if anywhere and no_layer and all(p in ocr_texts for p in no_layer) \
            and not any(names_consolidated(layer.text, not_required=True) for layer in layers.values()) \
            and not any(_LOOSE_CONSOLIDATED.search(ocr_texts[p]) for p in no_layer):
        from .metrics import STANDALONE
        alone = re.compile(r"stand[- ]?alone", re.I)
        typed = any(alone.search(layer.text) for layer in layers.values() if layer.has_layer)
        for p in no_layer:
            # the word standalone from a typed page (a covering letter) or from OCR of the table's own page, not any scan
            if not (typed or alone.search(ocr_texts.get(p, ""))):
                continue
            for t in by_page.get(p, []):
                if t.basis is None and not t.contested and t.source == "ocr":
                    t.basis = STANDALONE
    return [t for p in sorted(by_page) for t in by_page[p] if t.named or keep_unnamed]


def layer_basis(text: str) -> str | None:
    """The one basis the page's title lines name (``pdf_referee._words_basis``), None when none or two."""
    from .metrics import CONSOLIDATED, STANDALONE
    from .pdf_referee import _TITLE, _words_basis
    lines = text.splitlines()
    if _NON_CONSOLIDATED.search(text):          # also over a line break ("Non-\nConsolidated")
        return None             # "Statement of Non Consolidated Financial Results": the words say both (twenty-first review)
    found = {b for line in lines if _TITLE.search(line) and (b := _words_basis(line))}
    # a title printed as one glued word, its letters garbled (SUNDARMFIN Q4FY24's garbled layer:
    # "STATEMENTOFAUDITEDCONSOLIl)ATEDFINANCIALRESULTSFORTHEQUARTER..."): the whole "statement of ... financial results"
    # only on a line that names neither basis as a word: a spaced line naming both ("... read with the Statement of
    # Consolidated Financial Results") is ambiguous, not glued (twentieth review)
    # taken with the spaced lines' bases, so a glued title and a note naming the other basis are two: none (twenty-first)
    found |= {CONSOLIDATED if m[1].lower().startswith("consol") else STANDALONE
             for line in lines if not _BASIS_WORD.search(line)
             for m in _GLUED_TITLE.finditer(re.sub(r"\s+", "", line))}
    return found.pop() if len(found) == 1 else None


# "STATEMENTOFUNCONSOLIDATED..." is not a consolidated title: "un" only as part of "unaudited" (twentieth review)
_GLUED_TITLE = re.compile(r"statementof(?:unaudited|audited|reviewed)?(consol\S{1,4}?ated|standalone)financialresults", re.I)
_BASIS_WORD = re.compile(r"\b(?:consolidated|standalone)\b", re.I)
_NON_CONSOLIDATED = re.compile(r"\b(?:non|not|un)[\W_]+consolidated|\bnonconsolidated", re.I)


def Table_solved(table: Table) -> Table:
    """The table with its rows named by the solver (``named``: metric -> explanations)."""
    solver = Solver(table).solve()
    table.named = solver.explanations
    table.solver = solver          # type: ignore[attr-defined]
    return table


# --- one figure ----------------------------------------------------------------------------------------------------------

def layout_ok(columns: list[Column]) -> bool:
    """The kinds told fit a layout Indian results print: at most three quarter columns, two half-year (or nine-month) columns and
    two year columns. A header whose group words were given to the wrong columns (a third "year" column in a March table, where
    the prior-year quarter sits) does not."""
    kinds = [c.kind for c in columns]
    return kinds.count("quarter") <= 3 and kinds.count("year") <= 2 and (kinds.count("half") + kinds.count("nine")) <= 2


def target_columns(table: Table, kind: str, when: date) -> list[Column]:
    """The columns of the table that are the period's: its date and its kind. A table whose kinds do not fit a standard layout
    gives none. A column whose kind the header does not tell counts only when every column's date was read and it is the one
    column of its date (a quarter and a year of one date sit side by side in a March table)."""
    if not layout_ok(table.columns):
        return []
    same = [c for c in table.columns if c.date == when]
    told = [c for c in same if c.kind == kind]
    if told:
        return told
    if all(c.date is not None for c in table.columns) and len(same) == 1 and same[0].kind is None:
        return same
    return []



HALF_SUM_METRICS = ("revenue", "other_income", "total_income", "expenses", "pbt_pre", "pbt", "tax", "pat")
HALF_SUM_MIN_ROWS = 4


def fill_corresponding_quarter(columns: list[Column]) -> None:
    """The one date a SEBI results layout allows in an undated third column (A5, date-candidate matching; ABCAPITAL Q4FY24:
    "31.03.2024" quarter, "31.12.2023" quarter, an unreadable date, "31.03.2024" year, "31.03.2023" year): when the first two
    columns are quarters dated the current quarter and the one before it, the third has no date and no kind, every column after
    it is dated and is a half year, nine months or year, and one of those is dated a year before the current quarter, the third
    is the same quarter a year before. Nothing else is filled."""
    if len(columns) < 4:
        return
    a, b, c, rest = columns[0], columns[1], columns[2], columns[3:]
    if not (a.kind == b.kind == "quarter" and a.date and b.date and c.date is None and c.kind is None):
        return
    if b.date != previous_quarter_end(a.date):
        return
    if not all(x.date and x.kind in ("half", "nine", "year") for x in rest):
        return
    try:
        year_before = a.date.replace(year=a.date.year - 1)
    except ValueError:          # 29 February
        return
    if not any(x.date == year_before for x in rest):
        return
    # and the current year to date is printed and dated after it: otherwise the undated third column may itself be the
    # current half year, nine months or year of a layout that leaves the same quarter last year out (31st review)
    if not any(x.date == a.date and x.kind in ("half", "nine", "year") for x in rest):
        return
    c.date, c.kind, c.inferred = year_before, "quarter", True


def previous_quarter_end(d: date) -> date:
    import calendar
    y, m = (d.year, d.month - 3) if d.month > 3 else (d.year - 1, d.month + 9)
    return date(y, m, calendar.monthrange(y, m)[1])


def quarter_by_half_sum(table: Table, solver: "Solver", when: date) -> list[Column]:
    """The September quarter's column when the header's kinds do not fit (a garbled "Year to date for the period from April 01,
    2026 to ..." read as a year): the column dated ``when`` and the one dated the quarter before are two quarters when a third
    column is their sum, the half year, on every line the arithmetic named (revenue, other income, total income, expenses,
    profit before tax, tax, profit), at least four lines and none against (TATAELXSI Q2FY27: 105,565.73 + 102,110.75 =
    2,07,676.48 and so on down the table). Both dates must be read; the half year's need not, but if read it is ``when`` or the
    first of April it runs from. The
    sum cannot tell the two quarters apart, so the September column must stand left of the June one. Empty otherwise."""
    if when.month != 9:
        return []
    prev = previous_quarter_end(when)
    # the dates as the header prints them, also where the header's group words disagree with them (BRIGHOTEL Q2FY27: the title's
    # "six months" and a "Year to date" read as a year): the sum, not the words, tells the quarters here
    cur = [c for c in table.columns if (c.date or c.read_date) == when]
    prv = [c for c in table.columns if (c.date or c.read_date) == prev]
    if not cur or len(prv) != 1:
        return []
    lines = list(dict.fromkeys(rows for metric in HALF_SUM_METRICS for rows, _ in solver.explanations.get(metric, [])))

    def total(rows: tuple[int, ...], j: int):
        cells = [solver.cell(r, j) for r in rows]
        return None if any(c is None for c in cells) else (sum(c.value for c in cells), sum(c.tol for c in cells))

    found = []
    for i in cur:
        k = prv[0]
        if i.xc >= k.xc:            # results print the newest quarter first: a September column right of June is not trusted
            continue
        for h in table.columns:
            if h.index in (i.index, k.index) or (h.date or h.read_date) not in (None, when, date(when.year, 4, 1)):
                continue            # the half year is dated its end, or its start ("from April 01"), or was not read
            holds = fails = 0
            for rows in lines:
                a, b, c = total(rows, i.index), total(rows, k.index), total(rows, h.index)
                if a is None or b is None or c is None or (a[0] == 0 and b[0] == 0 and c[0] == 0):
                    continue
                if abs(c[0] - (a[0] + b[0])) <= a[1] + b[1] + c[1] + 1e-9:
                    holds += 1
                else:
                    fails += 1
            if holds >= HALF_SUM_MIN_ROWS and fails == 0:
                found.append((i, h))
    return [found[0][0]] if len(found) == 1 else []

def table_figure(table: Table, metric: str, kind: str, when: date):
    """(value in crore, tolerance in crore, label, why) of ``metric`` in the period's column of one table. ``value`` is None with
    the reason in ``why`` when the table gives no answer."""
    solver: Solver = getattr(table, "solver", None) or Solver(table).solve()
    if metric == "pat" and solver.pat_unsure:
        return None, 0.0, "", "the profit after tax is carried on further down and the labels do not tell by what"
    if table.unit is None:
        return None, 0.0, "", "no unit declared above the table"
    cols = target_columns(table, kind, when)
    if not cols and kind == "quarter":
        cols = quarter_by_half_sum(table, solver, when)
    if len(cols) != 1:
        return None, 0.0, "", f"{len(cols)} columns for {kind} ended {when}"
    j = cols[0].index
    found: list[tuple[float, float, str]] = []
    for rows, proofs in solver.explanations.get(metric, []):
        cells = [solver.cell(r, j) for r in rows]
        if any(c is None for c in cells):
            continue
        if not all(solver.mask(pf)[j] is True for pf in proofs):
            continue
        value = sum(c.value for c in cells)
        tol = sum(c.tol for c in cells)
        found.append((value, tol, table.rows[rows[0]].label))
    if not found:
        return None, 0.0, "", "no row of the table is named by arithmetic for this metric in the period's column"
    first = found[0]
    if any(abs(v - first[0]) > max(tol, first[1]) + 1e-9 for v, tol, _ in found[1:]):
        return None, 0.0, "", "the table's arithmetic names two different rows (" + ", ".join(f"{v:g}" for v, _, _ in found[:4]) + ")"
    return first[0] / table.unit, first[1] / table.unit, first[2], ""


def reading_from_tables(tables: list[Table], period: str, metric: str, basis: str | None, reader: str = NAME):
    """A ``pdf_readers.Reading`` from the solved tables: the figure when every table of the basis that names it agrees."""
    from .metrics import CONSOLIDATED, STANDALONE
    from .pdf_readers import Reading, same_value
    from .pdf_referee import target_column
    family = "numbers-first"
    target = target_column(period)
    if target is None or metric not in ("revenue", "other_income", "total_income", "expenses", "pbt", "tax", "pat"):
        return Reading(reader, family, "none", note=f"no {metric} for {period}")
    kind, when = target
    other = {CONSOLIDATED: STANDALONE, STANDALONE: CONSOLIDATED}.get(basis or "")
    mine: list[tuple[float, float, str, int, str]] = []
    theirs = False
    notes: list[str] = []
    for t in tables:
        if t.basis is None:
            notes.append(f"p{t.page}: the table's basis is not told")
            continue
        value, tol, label, why = table_figure(t, metric, kind, when)
        if metric == "pat" and (t.basis == basis or not basis) and getattr(getattr(t, "solver", None), "pat_unsure", False):
            # one table of the basis whose profit is carried on by arithmetic alone vetoes the others (twelfth review: a
            # second table of the basis that stops at the profit after tax would give the profit before the share)
            return Reading(reader, family, "none", note=f"p{t.page}: {why}"[:300])
        if value is None:
            if t.basis == basis or not basis:
                notes.append(f"p{t.page}: {why}")
            continue
        if t.basis == basis or not basis:
            mine.append((value, tol, label, t.page, t.source))
        elif t.basis == other:
            theirs = True
    if not mine:
        if theirs:
            return Reading(reader, family, "otherbasis", note=f"the figure is printed on the {other} basis only")
        return Reading(reader, family, "none", note="; ".join(dict.fromkeys(notes))[:300] or "no table")
    first = mine[0]
    if any(not same_value(first[0], v, max(first[1], tol)) for v, tol, *_ in mine[1:]):
        return Reading(reader, family, "conflict", note="tables differ: " + ", ".join(f"{v:g}" for v, *_ in mine[:4]))
    value, tol, label, page, source = first
    return Reading(reader, family, "ok", value, source == "textlayer", source == "textlayer", source, label, page,
                   tol=tol)


def combine_readings(first, second):
    """The native reader first, the numbers-first reader only where the native one gives no answer."""
    return first if first.status == "ok" and first.value is not None else second
