"""Several free, local document readers for the PDF referee (owner, 26 Oct 2026; TRACKER F177). Read only, no AI service.

``pdf_referee`` reads a results PDF with the pipeline's own reader (text layer, RapidOCR on scanned pages). This module adds
other readers, each at its most accurate setting, and one rule that settles a figure only when independent readers agree.

The interface. A reader's ``read_tables(pdf_bytes, pages)`` returns ``Table`` objects (a grid of cell texts, the page, the
reader's name). Only the statement pages are passed (``statement_pages``: at most ``MAX_PAGES``), as a small sub-PDF, so a slow
reader (MinerU, about a minute a page) stays bounded. A table's rows are turned into the referee's own ``Row`` objects by
the referee's own ``parse_page`` (the table is written out as lines of text, with the page's title and unit lines above it), so
the column proof, the basis and the unit are decided by the same code for every reader.

Readers (all optional, imported lazily; a missing package makes the reader ``unavailable`` and the rest carry on):

====== ================= ==========================================================================================
name   structure family  how
====== ================= ==========================================================================================
native textlayer-native  the pipeline's ``Document`` as ``pdf_referee.read_document`` uses it (wrapped, not changed)
camelot camelot           lattice first, stream on a page where lattice finds no table
pdfplumber pdfplumber     lines strategy, then the text strategy with explicit verticals from the header's dates
tabula tabula             lattice, then stream (needs Java)
docling docling           TableFormer ACCURATE, cell matching on, OCR on
mineru mineru             the ``mineru`` command, pipeline backend, mode auto, table on, formula off
paddle paddle             PP-StructureV3 (layout on, table recognition on; its default table models)
marker surya              Marker 2 ``TableConverter``, html output, no LLM, OCR only where no text layer
surya  surya              Surya layout then Surya table recognition (full HTML path), no LLM service
rapidtable paddle         rapid-table (SLANet-plus ONNX); cell text from the text layer's words, else RapidOCR
tatr   tatr               Table Transformer detection + structure v1.1, cell text from the text layer, else Tesseract
numfirst numbers-first     EXPERIMENT, bench only (pdf_numbers_first): numeric rows and columns first, rows named by vertical arithmetic
====== ================= ==========================================================================================

The settlement rule (``settle``) is the owner's: a PDF figure counts only from the text layer. A figure is *settled* when
(a) its digits appear verbatim in the page's text layer, (b) at least two readers of two different families place the same
value in the same row, period column and basis (families: textlayer-native, camelot, pdfplumber, tabula, docling, mineru, paddle = PP-StructureV3 and
rapid-table, surya = Marker and Surya, tatr), and (c) no reader of any family places a different value there (then ``pdf_disagree``).
On a page with no text layer the OCR readers cannot settle: two OCR engines of different families agreeing give
``pdf_scanned_lead`` (a lead for the owner, not a verdict). For that case a reader's family is its OCR engine's: RapidOCR
(the native reader on scanned pages, and Docling's default) runs PaddleOCR's models, so it counts as ``paddle``; Marker and
Surya read with Surya; Table Transformer reads with Tesseract.

Heavy readers can conflict in their dependencies (measured 26 Oct 2026 with ``pip install --dry-run``: marker-pdf 2.0.0 and
mineru 4.0.12 cannot resolve together) and must not share a process, so each is run in a process of its own, one after another:
set ``PDF_READER_PYTHON_<NAME>`` (e.g. ``PDF_READER_PYTHON_DOCLING``) to the python of that reader's own environment, else the
current python is used; the reader runs there as a worker (``python -m bse_intel.pdf_readers --worker``); ``PDF_MINERU_BIN`` is the ``mineru`` command.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from html.parser import HTMLParser

log = logging.getLogger(__name__)

MAX_PAGES = 4               # statement pages passed to the readers (MinerU takes about a minute a page)
SCAN_PAGE_LIMIT = 12        # scanned pages are searched only in short PDFs
SCAN_PAGE_LIMIT_RANKED = 30  # with PDF_PAGE_RANK: the 25-26 page scans are searched too; at most MAX_PAGES pages are read either way
DPI = 200
WORKER_TIMEOUT = 900        # seconds for one reader on one PDF
LAYER_MIN_CHARS = 40        # fewer characters on a page: no text layer
HEADER_LINES = 25           # lines at the top of a page kept as the table's title and unit context

_UNIT_WORD = re.compile(r"\b(crores?|lakhs?|lacs?|millions?|thousands?|mn|cr)\b", re.I)
_TWO_POINTS = re.compile(r"^\(?-?[\d,]*\d(?:\.\d+){2,}\)?$")   # "18.370.88": a figure with two or more decimal points (nemotron_grids)
_DATE_POINTS = re.compile(r"^(0?[1-9]|[12]\d|3[01])\.(0?[1-9]|1[0-2])\.(\d{2}|\d{4})$")   # 30.06.2023: a date (18.37.88 is not)
_CELL_MARKS = re.compile(r"[*†‡#%\s]|\(\d\)$|\[\d\]$")             # footnote marks and the like around a figure


def garbled_figure(cell: str) -> bool:
    """A figure with two or more decimal points (\"18.370.88\" for 18,370.88), marks around it ignored; a date is not one."""
    text = _CELL_MARKS.sub("", (cell or "").replace("\u2212", "-"))
    return bool(_TWO_POINTS.match(text)) and not _DATE_POINTS.match(text)
_CONS_WORD = re.compile(r"\bconsolidated\b", re.I)
_ALONE_WORD = re.compile(r"\bstand[- ]?alone\b", re.I)
# "consolidated" as a verb in prose ("the Government has consolidated 29 labour laws into 4 Labour Codes", TATAELXSI Q2FY27): not a
# sign of a consolidated statement, unless a group word stands near it ("the subsidiaries have been consolidated")
_CONS_VERB = re.compile(r"\b(?:has|have|had|been|being|is|are|was|were|be|will|shall)\s+consolidated\b", re.I)
_GROUP_WORDS = re.compile(r"subsidiar|\bgroup\b|results|financial|statements?\b|accounts|entit|joint\s+ventures?|associates?\b"
                          r"|\bbasis\b|holding\s+company", re.I)


_NO_SUBSIDIARY = re.compile(r"(?:does\s+not\s+have|has\s+no|have\s+no|not\s+having)\s+(?:any\s+)?subsidiar", re.I)
# said of the consolidated results themselves: "consolidated financial results is not applicable" (at most three words between)
_NOT_APPLICABLE = re.compile(r"[ \t]+(?:[\w-]+[ \t]+){0,3}?(?:is|are)[ \t]+not[ \t]+applicable", re.I)
# "the Company is not required to prepare consolidated financial results" (SBICARD Q2FY27), only where the page also says the
# company has no subsidiary, associate or joint venture (one sentence naming all three: a company with associates alone may still
# publish consolidated results)
_NOT_REQUIRED_BEFORE = re.compile(r"(?:is|are)\s+not\s+required\s+to\s+(?:prepare|present|publish|submit|draw\s+up)\s+(?:the\s+)?$", re.I)
_NO_SUB_ASSOC_JV = re.compile(r"(?:does\s*not\s+have|has\s+no|have\s+no)\s+(?:any\s+)?subsidiar\w*\s*[/,]?\s*(?:or\s+)?associate\w*"
                              r"\s*[/,]?\s*(?:or\s+)?joint\s+venture", re.I)
# "... or joint venture except XYZ Ltd": the company has one after all
_EXCEPT = re.compile(r"\b(?:except|other\s+than|save|barring|apart\s+from|excluding|but)\b", re.I)


def _none_of_three(text: str) -> bool:
    """The page says the company has no subsidiary, associate or joint venture, with no exception in the rest of that sentence."""
    return any(not _EXCEPT.search(re.split(r"[.\n]", text[m.end():], maxsplit=1)[0]) for m in _NO_SUB_ASSOC_JV.finditer(text))


def names_consolidated(text: str, not_required: bool = False) -> bool:
    """Whether ``text`` says "consolidated" of the accounts: every use counts but a verb in prose with no group word within about
    eight words either side, and, on a page that says the company has no subsidiary, a use that the same sentence calls not
    applicable ("...does not have any subsidiary ... Accordingly, preparation of consolidated financial results is not
    applicable", ORIENTCEM Q2FY27). ``not_required`` (numbers-first only): also a use the same sentence says the company is not
    required to prepare, on a page that says it has no subsidiary, associate or joint venture (SBICARD Q2FY27)."""
    no_subsidiary = bool(_NO_SUBSIDIARY.search(text))
    none_of_three = not_required and _none_of_three(text)
    for m in _CONS_WORD.finditer(text):
        if no_subsidiary and _NOT_APPLICABLE.match(text, m.end()):
            continue
        if none_of_three and _NOT_REQUIRED_BEFORE.search(text[max(0, m.start() - 60):m.start()]):
            continue
        verb = _CONS_VERB.search(text, max(0, m.start() - 12), m.end())
        if not verb or verb.end() != m.end():
            return True
        before = " ".join(text[:m.start()].split()[-8:])
        after = " ".join(text[m.end():].split()[:8])
        if _GROUP_WORDS.search(before) or _GROUP_WORDS.search(after):
            return True
    return False
_RESULTS_HEAD = re.compile(r"statement\s+of\s+(?:\w+\s+){0,6}results|financial\s+results", re.I)
_PERIOD_WORDS = re.compile(r"months?\s+ended|quarter|year\s+ended", re.I)
_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")


# --- data ------------------------------------------------------------------------------------------------------------

@dataclass
class Table:
    reader: str
    page: int                       # 1-based page of the original PDF
    cells: list[list[str]]          # the grid, one list of cell texts a row
    source: str = ""                # "textlayer" or "ocr": set from the page, not by the reader
    ocr_engine: str = ""            # the OCR engine that read the cells, when ``source`` is "ocr"

    def as_json(self) -> dict:
        return {"reader": self.reader, "page": self.page, "cells": self.cells, "ocr_engine": self.ocr_engine}


@dataclass
class PageLayer:
    text: str
    has_layer: bool
    numbers: set[float]
    context: str                    # title and unit lines to put above a table of this page
    unit_context: str = ""          # the unit lines alone (a page with two tables gives a table without its own title no basis)
    words: list = field(default_factory=list)      # (x0, y0, x1, y1, text) of the page's words, when read from the PDF
    _bands: list | None = None

    def header_block(self) -> str:
        """The page's column header as printed (the group words above the dates, the dates, the line below), for a table whose
        reader left the header out: only when every row of dates on the page is the same dates, else empty (two headers would be a
        guess)."""
        from .pdf_referee import _dates_in
        lines = [" ".join([b.label] + b.nums) for b in self.bands()]
        dated = [i for i, line in enumerate(lines) if len(_dates_in(line)) >= 2]
        if not dated or len({tuple(_dates_in(lines[i])) for i in dated}) != 1:
            return ""
        first = dated[0]
        end = first + 1
        if end < len(lines) and not re.search(r"\d[\d,]*\.\d", lines[end]):
            end += 1          # the line under the dates ("Unaudited", "Audited"), never a row of figures
        from .pdf_referee import _words_basis
        # never a line that names a basis: a title carried into the table would set its basis from the page's other table
        return "\n".join(line for line in lines[max(0, first - 4): end] if not _words_basis(line))

    def bands(self) -> list["Band"]:
        """The page's rows as printed (label, trailing figures, the basis of the nearest title above), read once."""
        if self._bands is None:
            self._bands = make_bands(self.words, self.text)
        return self._bands


@dataclass
class Band:
    label: str
    nums: list[str]                 # the figures after the label, as printed
    basis: str | None               # the basis named by the nearest title above (None: none named yet)


_NUMTOK = re.compile(r"^\(?-?\d[\d,]*(?:\.\d+)?\)?$")
_YEAR = re.compile(r"(?:19|20)\d\d[,.]?")
# a title's own date: "... results for the quarter ended September" (then "30, 2025"); a data row never reads so
_DATED = re.compile(r"\b(?:results|statement)\b.*\b(?:ended|ending|as at|as on)\s+(?:the\s+)?(?:\d{1,2}(?:st|nd|rd|th)?\s+)?"
                    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[.,]?$", re.I)


def _alpha(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def make_bands(words: list, text: str) -> list[Band]:
    """Rows of the text layer: words on one baseline band (3.5 pt) when the words are known, else the text's lines. A row's
    figures are the numeric tokens after its last non-numeric token (a serial number before the label is not one)."""
    from .pdf_referee import _words_basis
    groups: list[list[str]] = []
    if words:
        ordered = sorted(words, key=lambda w: (w[1] + w[3]) / 2)
        current: list = []
        last = None
        for w in ordered:
            centre = (w[1] + w[3]) / 2
            if last is not None and centre - last > 3.5:
                groups.append([x[4] for x in sorted(current, key=lambda x: x[0])])
                current = []
            current.append(w)
            last = centre
        if current:
            groups.append([x[4] for x in sorted(current, key=lambda x: x[0])])
    else:
        groups = [line.split() for line in text.splitlines() if line.strip()]
    bands: list[Band] = []
    basis: str | None = None
    for tokens in groups:
        stop = max((i for i, t in enumerate(tokens) if not _NUMTOK.match(t)), default=-1)
        label, nums = " ".join(tokens[: stop + 1]), tokens[stop + 1:]
        # a title names one basis and ends at most in its date ("... quarter ended September 30, 2025")
        if (not nums or (_DATED.search(label) and len(nums) <= 2 and any(_YEAR.fullmatch(n) for n in nums))) \
                and (named := _words_basis(label)):
            basis = named
        bands.append(Band(label, nums, basis))
    return bands


def cell_in_layer(layer: "PageLayer", label: str, basis: str | None, printed: float, index: int, count: int,
                  anywhere: bool) -> str:
    """The printed token of the cell when the text layer has the figure on the row of ``label`` under the same basis and at
    column ``index`` of ``count`` figures (the row must show exactly that many), else an empty string."""
    from .pdf_referee import STANDALONE
    key = _alpha(label)
    if len(key) < 6 or not layer.has_layer:
        return ""
    for band in layer.bands():
        bk = _alpha(band.label)
        if len(bk) < 6 or not (key in bk or bk in key) or len(band.nums) != count:
            continue
        band_basis = band.basis if band.basis is not None else (None if anywhere else STANDALONE)
        if basis and band_basis != basis:
            continue
        token = band.nums[index]
        try:
            figure = float(token.strip("()").replace(",", ""))
        except ValueError:
            continue
        if abs(abs(figure) - abs(printed)) <= 1e-6 * max(1.0, abs(printed)):
            return token
    return ""


@dataclass
class Reading:
    """One reader's figure for one pair (row, period column, basis)."""
    reader: str
    family: str = ""                # the family it counts in (structure family on a text layer, OCR engine's on a scan)
    status: str = "ok"              # ok | none | conflict | otherbasis | unavailable | error
    value: float | None = None      # crore (EPS as printed), after unit conversion
    verbatim: bool = False          # the printed digits are in the page's text layer
    layer: bool = True              # the page has a text layer
    source: str = "textlayer"       # textlayer or ocr: where the figure came from
    label: str = ""
    page: int = 0
    note: str = ""
    tol: float = 0.005              # half a unit of the last printed decimal, in the same unit as ``value``


@dataclass
class Verdict:
    status: str                     # settled | disagree | scanned_lead | unsure | none
    value: float | None = None
    agreed: list[str] = field(default_factory=list)
    disagreed: list[str] = field(default_factory=list)
    abstained: list[str] = field(default_factory=list)
    families: list[str] = field(default_factory=list)
    reason: str = ""
    label: str = ""
    page: int = 0

    def readers_text(self) -> str:
        parts = [f"agreed={'+'.join(self.agreed)}", f"disagreed={'+'.join(self.disagreed)}"]
        if self.abstained:
            parts.append(f"abstained={'+'.join(self.abstained)}")
        return ";".join(parts)


# --- the settlement rule -------------------------------------------------------------------------------------------

def same_value(a: float, b: float, tol: float = 0.005) -> bool:
    """Two readings of one figure are the same when they differ by no more than half a unit of the last printed decimal after
    unit conversion (0.005 crore for two decimals): exact at the printed precision, never a percentage."""
    return abs(a - b) <= tol + 1e-9


def _agree(a: Reading, b: Reading) -> bool:
    return same_value(a.value, b.value, max(a.tol, b.tol))


def settle(readings: list[Reading]) -> Verdict:
    """The two-families-agree-and-none-disagrees rule over the readers' figures for one pair.

    A reader that finds the row only on the other basis vetoes (``disagree``); a reader whose own rows differ vetoes
    (``unsure``, as the native path does); a reader with no proven column or basis abstains. The agreeing values form a
    cluster only when every member is within tolerance of every other; the settled value is a text-layer reader's."""
    ok = [r for r in readings if r.status == "ok" and r.value is not None]
    abstained = [f"{r.reader}({r.status})" for r in readings if r.status not in ("ok", "otherbasis", "conflict")]
    other = [r.reader for r in readings if r.status == "otherbasis"]
    conflict = [r for r in readings if r.status == "conflict"]
    if not ok:
        out = Verdict("none", abstained=abstained, reason="no reader gave a figure")
        if other:
            out.status, out.disagreed, out.reason = "disagree", other, "a reader finds the figure only on the other basis"
        elif conflict:
            out.status, out.reason = "unsure", f"{conflict[0].reader}'s own rows differ ({conflict[0].note})"
        return out
    clusters: list[list[Reading]] = []
    for r in ok:
        for c in clusters:
            if all(_agree(m, r) for m in c):
                c.append(r)
                break
        else:
            clusters.append([r])
    clusters.sort(key=lambda c: (-len({m.family for m in c}), -len(c)))
    best = clusters[0]
    verbatim = [m for m in best if m.verbatim]
    first = verbatim[0] if verbatim else best[0]
    out = Verdict("unsure", value=first.value, agreed=[m.reader for m in best], abstained=abstained, label=first.label,
                  page=first.page)
    if len(clusters) > 1 or other:
        out.status = "disagree"
        out.disagreed = [m.reader for c in clusters[1:] for m in c] + other
        shown = ", ".join(f"{c[0].value:g} ({'+'.join(m.reader for m in c)})" for c in clusters[:4])
        out.reason = "readers disagree: " + (shown if len(clusters) > 1 else "one finds the figure only on the other basis")
        return out
    if conflict:
        out.reason = f"{conflict[0].reader}'s own rows differ ({conflict[0].note}): no verdict"
        return out
    out.families = sorted({m.family for m in verbatim})
    if len(out.families) >= 2:
        out.status = "settled"
        out.agreed = [m.reader for m in verbatim]
        return out
    if all(not m.layer for m in best):
        families = sorted({m.family for m in best})
        out.families = families
        if len(families) >= 2:
            out.status = "scanned_lead"
            out.reason = "no text layer on the page: OCR readers of different families agree"
        else:
            out.reason = "no text layer on the page and one OCR family only"
        return out
    if verbatim:
        out.reason = f"only one family ({verbatim[0].family}) read the figure from the text layer"
    else:
        out.reason = "the figure's digits are not in the page's text layer on that row and column"
    return out


def family_of(reader: "Reader", source: str, verbatim: bool = True) -> str:
    """The family a reading counts in: the structure family when the digits come from the text layer, else the OCR engine's."""
    if source == "textlayer" and verbatim:
        return reader.family
    return reader.ocr_family or reader.family


# --- tables to the referee's rows ---------------------------------------------------------------------------------

def clean_cell(text) -> str:
    """One cell's text: runs of spaces become one space; a line break stays as one ``\\n`` (a reader that joins several printed
    lines into one cell, as Camelot and Tabula do for a merged cell, keeps them apart for ``table_text``)."""
    raw = str(text if text is not None else "").replace("\r", "\n")
    return "\n".join(p for p in (re.sub(r"[^\S\n]+", " ", ln).strip() for ln in raw.split("\n")) if p)


_LONE_BASIS = re.compile(r"^\W*(?:un-?)?(standalone|stand[- ]alone|consolidated)\W*$", re.I)


def _explode_merged(row: list[str]) -> list[list[str]]:
    """A merged cell row (several printed rows in one: ``label1\\nlabel2`` beside ``1.0\\n2.0``) back into its rows, when the
    label cell and every figure cell have the same number of lines; any other multi-line row is joined into one line."""
    cells = [clean_cell(c) for c in row]
    parts = [c.split("\n") for c in cells]
    counts = {len(p) for p in parts if p != [""]}
    if counts <= {1}:
        return [cells]
    figure_counts = {len(p) for c, p in zip(cells, parts) if p != [""] and re.search(r"\d", c) and not re.search(r"[A-Za-z]{3}", c)}
    label_counts = {len(p) for c, p in zip(cells, parts) if re.search(r"[A-Za-z]", c)}
    n = max(figure_counts, default=1)
    if n > 1 and {c for c in figure_counts if c > 1} == {n} and label_counts <= {n, 1}:      # a serial number has one line
        return [[(p[i] if len(p) == n else (p[0] if i == 0 else "")) for p in parts] for i in range(n)]
    return [[c.replace("\n", " ") for c in cells]]


def table_text(cells: list[list[str]]) -> str:
    """A grid written as lines: the non-empty cells of a row joined by two spaces (what the text layer would give). A line
    that is only the basis word (a ``STANDALONE`` cell above the columns) becomes ``STANDALONE financial results``, the form
    of a title the referee's own parsing reads."""
    lines = []
    for row in cells:
        for sub in _explode_merged(row):
            parts = [clean_cell(c) for c in sub]
            line = "  ".join(p for p in parts if p)
            if line:
                lines.append(line)
    for i, line in enumerate(lines[:4]):
        if _LONE_BASIS.match(line):
            lines[i] = f"{line} financial results"
    return "\n".join(lines)


def page_layer(text: str) -> PageLayer:
    has = len(text.strip()) >= LAYER_MIN_CHARS
    numbers = {round(float(m.replace(",", "")), 4) for m in _TOKEN.findall(text) if _safe_float(m)}
    lines = [ln for ln in text.splitlines() if ln.strip()]
    top = lines[:HEADER_LINES]
    bases = {b for b in (("c" if _CONS_WORD.search(text) else ""), ("s" if _ALONE_WORD.search(text) else "")) if b}
    units = [ln for ln in lines if _UNIT_WORD.search(ln)]
    kinds = {m.group(1).lower().rstrip("s") for ln in units for m in _UNIT_WORD.finditer(ln)}
    context: list[str] = []
    unit_lines: list[str] = []
    if len(bases) == 1:                       # one basis on the page: its title can stand above any table of it
        context += [ln for ln in top if _CONS_WORD.search(ln) or _ALONE_WORD.search(ln)]
    elif len(bases) == 2:
        # both words appear (a note naming the other basis, a footer): the page's titles still tell the basis when every title line
        # of the page, anywhere on it, names the same one; two statements on a page (two titles) give nothing
        from .pdf_referee import _TITLE, _words_basis
        titles = [ln for ln in lines if _TITLE.search(ln) and _words_basis(ln)]
        if titles and len({_words_basis(t) for t in titles}) == 1:
            context += titles[:2]
    if len(kinds) == 1:                       # one unit on the page; two units would be a guess, so none is given
        context += units[:2]
        unit_lines = units[:2]
    return PageLayer(text, has, numbers, "\n".join(dict.fromkeys(context)), "\n".join(dict.fromkeys(unit_lines)))


def _safe_float(token: str) -> bool:
    try:
        float(token.replace(",", ""))
        return True
    except ValueError:
        return False


def consolidated_anywhere(layers: dict[int, PageLayer], tables: list[Table] | None = None, not_required: bool = False,
                          numbers_first: bool = False) -> bool:
    """Shared by every reader of a PDF: a table with no title of its own is read as standalone only when every page's text
    layer is there to say "consolidated" and does not. A page with no layer, or a layer that names consolidated anywhere,
    leaves such a table's basis unproven. ``numbers_first``: the word is read by ``names_consolidated`` (with ``not_required``);
    every other reader keeps the plain word search it has always had (the lead's review: the old reader unchanged)."""
    if any(not layer.has_layer for layer in layers.values()) or not layers:
        return True
    names = (lambda text: names_consolidated(text, not_required)) if numbers_first else (lambda text: bool(_CONS_WORD.search(text)))
    if any(names(layer.text) for layer in layers.values()):
        return True
    return any(names(table_text(t.cells)) for t in tables or [])


def _cons_or_alone(text: str) -> bool:
    return bool(_CONS_WORD.search(text) or _ALONE_WORD.search(text))


def tables_to_rows(tables: list[Table], layers: dict[int, PageLayer], anywhere: bool | None = None) -> list:
    """The referee's ``Row`` objects of every table, each parsed with ``pdf_referee.parse_page`` under its page's title and unit."""
    from .pdf_referee import parse_page
    from .pdf_referee import _dates_in
    texts = []
    per_page: dict[int, int] = {}
    for t in tables:
        per_page[t.page] = per_page.get(t.page, 0) + 1
    for t in tables:
        layer = layers.get(t.page)
        body = table_text(t.cells)
        if body:
            if layer and layer.has_layer and not any(len(_dates_in(ln)) >= 2 for ln in body.splitlines()):
                # the reader's table starts below the header (or lost it): the page's own header stands above the figures
                header = layer.header_block()
                if header:
                    body = header + "\n" + body
            context = layer.context if layer else ""
            if layer and per_page[t.page] > 1 and not (_cons_or_alone(body)):
                # two tables of this reader on the page and this one names no basis: the page's title may belong to the other
                # (a results table under the title of an assets and liabilities table: measured on EMKAY, 26 Oct 2026), so
                # only the unit stands above it
                context = layer.unit_context
            texts.append((t.page, (context + "\n" if context else "") + body))
    if anywhere is None:
        anywhere = consolidated_anywhere(layers, tables)
    rows = []
    for page, text in texts:
        rows += parse_page(text, page, anywhere or bool(_CONS_WORD.search(text)))
    return rows


def _period_index(row, period: str) -> int | None:
    """The column of the period in a row, found as ``pdf_referee.figure_for`` finds it."""
    from .pdf_referee import target_column
    target = target_column(period)
    if target is None:
        return None
    if row.columns is not None:
        matching = [k for k, c in enumerate(row.columns) if c == target]
        return matching[0] if len(matching) == 1 else None
    return row.dates.index(target[1]) if target[1] in row.dates else None


def _row_fixes() -> bool:
    from .settings import pdf_option
    return pdf_option("pdf_row_fixes")


def _other(basis: str | None) -> str | None:
    from .pdf_referee import CONSOLIDATED, STANDALONE
    return {CONSOLIDATED: STANDALONE, STANDALONE: CONSOLIDATED}.get(basis or "")


def reading_of(reader: "Reader", rows: list, layers: dict[int, PageLayer], period: str, metric: str, basis: str | None,
               anywhere: bool = True) -> Reading:
    """One reader's figure for the pair, with the proof the rule needs: the basis proven from a title (rows with no proven
    basis are never taken), the printed cell found in the text layer on its row and column, the source and the printed precision."""
    from .pdf_referee import _TOTAL_INCOME, figure_for
    got = figure_for(rows, period, metric, basis)
    values = got["values"]
    if not values:
        theirs = _other(basis)
        if theirs and figure_for(rows, period, metric, theirs)["values"]:
            return Reading(reader.name, reader.family, "otherbasis", note=f"the figure is printed on the {theirs} basis only")
        return Reading(reader.name, reader.family, "none", note=got.get("unsure", "") or "no row")
    distinct: list[float] = []
    for v, _, _ in values:
        if not any(same_value(d, v) for d in distinct):
            distinct.append(v)
    if len(distinct) > 1:
        return Reading(reader.name, reader.family, "conflict", note="rows differ: " + ", ".join(f"{d:g}" for d in distinct[:4]))
    value, label, page = values[0]
    if metric == "revenue" and _row_fixes() and all(_TOTAL_INCOME.search(lab) for _, lab, _ in values):
        # memory's revenue is revenue from operations: "Total income" includes other income, so a table that prints no such row
        # has no figure for the pair (the key tags it revenue_total_not_printed); F215, PDF_ROW_FIXES
        return Reading(reader.name, reader.family, "none", note=f"only 'Total income' printed ({value:g}), which includes other income")
    layer = layers.get(page)
    has_layer = bool(layer and layer.has_layer)
    token = ""
    unit = 1.0
    for r in rows:
        if r.metric != metric or r.page != page or r.label[:60] != label or (basis and r.basis != basis):
            continue
        if metric != "eps" and not r.unit:
            continue
        unit = 1.0 if metric == "eps" else r.unit
        printed = value * unit
        seq = r.aligned if r.aligned is not None else r.figures
        k = _period_index(r, period)
        if k is not None and k < len(seq) and seq[k] is not None and layer is not None \
                and abs(seq[k] - printed) <= 1e-9 * max(1.0, abs(printed)):
            token = cell_in_layer(layer, r.label, r.basis, printed, k, len(seq), anywhere)
        if token:
            break
    verbatim = bool(token)
    source = "textlayer" if verbatim else "ocr"
    decimals = len(token.split(".")[1].strip(")")) if "." in token else 0
    tol = 0.5 * 10 ** -(decimals if verbatim else 2) / unit
    return Reading(reader.name, family_of(reader, source, verbatim), "ok", value, verbatim, has_layer, source, label, page,
                   tol=tol)


# --- the page sub-PDF and the pages of a statement ---------------------------------------------------------------

def _pymupdf():
    import pymupdf
    return pymupdf


def page_layers(pdf_bytes: bytes, limit: int = 80) -> dict[int, PageLayer]:
    pymupdf = _pymupdf()
    layers: dict[int, PageLayer] = {}
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i in range(min(doc.page_count, limit)):
            layer = page_layer(doc[i].get_text())
            layer.words = [(w[0], w[1], w[2], w[3], w[4]) for w in doc[i].get_text("words")]
            layers[i + 1] = layer
    return layers


def _metric_kinds(layer: PageLayer) -> int:
    """How many of the three metrics (revenue, profit, EPS) have a labelled row with figures on the page, read from the page's
    rows as printed (words on one baseline), so a table whose cells sit on separate lines of the raw text still counts."""
    from .pdf_referee import _EPS, _PAT_NAME, _PAT_NOT, _revenue_rank
    found = set()
    for band in layer.bands():
        if not band.nums:
            continue
        label = band.label.strip()
        if _revenue_rank(label) is not None:
            found.add("revenue")
        elif _PAT_NAME.search(label) and not _PAT_NOT.search(label):
            found.add("pat")
        elif _EPS.search(label):
            found.add("eps")
    return len(found)


def _has_date_header(layer: PageLayer) -> bool:
    """A header row with two dates or more: in the raw text's lines, or in the rows read from the words (a page whose raw text
    puts each cell on a line of its own has its dates on separate lines, so the lines alone never show two)."""
    from .pdf_referee import _dates_in
    if any(len(_dates_in(line)) >= 2 for line in layer.text.splitlines()):
        return True
    if any(len(_dates_in(" ".join([b.label] + b.nums))) >= 2 for b in layer.bands()):
        return True
    from .settings import pdf_option
    if pdf_option("pdf_page_rank"):     # F215: each date of the header on a line of its own ("-31Mar-23" / "31-Dec-22" / ...)
        lines = layer.text.splitlines()
        counts = [len(_dates_in(line)) if len(line.strip()) <= 16 else 0 for line in lines]     # a line of its own, not prose
        return any(sum(counts[i:i + 8]) >= 3 for i in range(len(lines)))
    return False


_SPLIT_DATE = re.compile(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}\s*,?\s+20\d{2}\b", re.I)
_SEGMENT_HEAD = re.compile(r"\bsegment", re.I)


def _split_date_header(layer: PageLayer) -> bool:
    """A header whose dates the text layer breaks over lines ("September 30," then "2024" on a line of its own): two or more
    dates once the whitespace between day and year is one space (F215, PDF_PAGE_RANK). A cover letter says "September 30, 2024"
    twice too, so the caller also asks for labelled rows."""
    return len(_SPLIT_DATE.findall(layer.text)) >= 2


def _segment_page(layer: PageLayer) -> bool:
    """A segment-wise page: "segment" in its first lines, where a results page has its title (F215, PDF_PAGE_RANK)."""
    return bool(_SEGMENT_HEAD.search("\n".join(layer.text.splitlines()[:HEADER_LINES // 2])))


def statement_pages(layers: dict[int, PageLayer], max_pages: int = MAX_PAGES) -> list[int]:
    """Pages that hold a results table: a "Statement of ... Results" heading or a header with two dates and the period
    words (a page of the text layer), best first; a page that also has labelled revenue, profit and EPS rows ranks above one that
    only repeats the heading (a segment or notes page); pages with no text layer fill what is left in a short PDF.

    With PDF_PAGE_RANK (F215): a page whose date header is split over lines, or one with three metric kinds under a results
    heading, passes the date gate too; a segment page ranks below a page of the statement itself before the top ``max_pages``
    are taken; scanned pages are searched in PDFs of up to ``SCAN_PAGE_LIMIT_RANKED`` pages."""
    from .settings import pdf_option
    ranked = pdf_option("pdf_page_rank")
    scored: list[tuple[int, int]] = []
    for page, layer in layers.items():
        if not layer.has_layer:
            continue
        kinds = None
        if not _has_date_header(layer):
            if not ranked:
                continue
            kinds = _metric_kinds(layer)
            if not ((kinds >= 2 and _split_date_header(layer)) or (kinds >= 3 and _RESULTS_HEAD.search(layer.text))):
                continue
        score = (2 if _RESULTS_HEAD.search(layer.text) else 0) + (1 if _PERIOD_WORDS.search(layer.text) else 0)
        if score:
            if kinds is None:
                kinds = _metric_kinds(layer)
            rank = score + 2 * kinds
            if ranked and kinds < 3 and _segment_page(layer):
                rank -= 3
            scored.append((-rank, page))
    pages = [p for _, p in sorted(scored)][:max_pages]
    if len(pages) < max_pages and len(layers) <= (SCAN_PAGE_LIMIT_RANKED if ranked else SCAN_PAGE_LIMIT):
        pages += [p for p, layer in layers.items() if not layer.has_layer][: max_pages - len(pages)]
    return sorted(pages)


def subset_pdf(pdf_bytes: bytes, pages: list[int]) -> bytes:
    """A PDF of only ``pages`` (1-based, in the order given)."""
    pymupdf = _pymupdf()
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as src, pymupdf.open() as out:
        for p in pages:
            out.insert_pdf(src, from_page=p - 1, to_page=p - 1)
        return out.tobytes()


def render_pages(pdf_bytes: bytes, dpi: int = DPI) -> list:
    """PIL images of each page of a (sub-)PDF."""
    from PIL import Image
    pymupdf = _pymupdf()
    images = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            images.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    return images


# --- HTML tables (MinerU, PP-StructureV3, Marker, Surya) ----------------------------------------------------------

def is_group_header(text: str) -> bool:
    """A header cell that names the kind of period ("Quarter ended", "Year ended", "Nine months ended") and holds no figure: a
    cell like it that spans several columns names each of them, so its text is repeated over the span (the dates below it then
    each have their kind). A spanned cell of figures or labels is never repeated."""
    from .pdf_referee import _GROUP
    return bool(text) and not re.search(r"\d{2}", text) and bool(_GROUP.search(text)) and len(text) <= 60


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._depth = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._span = 1
        self._rowspan = 1
        self._pending: dict[int, int] = {}       # column -> rows still covered by a rowspan

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self.tables.append([])
                self._pending = {}
        elif tag == "tr" and self._depth == 1:
            self._row = []
        elif tag in ("td", "th") and self._depth == 1 and self._row is not None:
            self._cell = []
            self._span = max(1, int(a.get("colspan", 1) or 1)) if str(a.get("colspan", "1")).isdigit() else 1
            self._rowspan = max(1, int(a.get("rowspan", 1))) if str(a.get("rowspan", "1")).isdigit() else 1
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def _fill_pending(self):
        while self._row is not None and self._pending.get(len(self._row), 0) > 0:
            self._pending[len(self._row)] -= 1
            self._row.append("")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._fill_pending()
            col = len(self._row)
            text = clean_cell("".join(self._cell))
            self._row.append(text)
            for k in range(1, self._span):
                self._row.append(text if is_group_header(text) else "")
            if self._rowspan > 1:
                for k in range(self._span):
                    self._pending[col + k] = self._rowspan - 1
            self._cell = None
        elif tag == "tr" and self._depth == 1 and self._row is not None:
            self._fill_pending()
            self.tables[-1].append(self._row)
            self._row = None
        elif tag == "table":
            self._depth = max(0, self._depth - 1)


def html_tables(html: str) -> list[list[list[str]]]:
    """The grids of the (outermost) tables of an HTML string; a spanned cell's text sits in its first cell, the rest are empty."""
    parser = _TableParser()
    parser.feed(html or "")
    return [t for t in parser.tables if t]


# --- readers -------------------------------------------------------------------------------------------------------

def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


class Reader:
    name = ""
    family = ""
    ocr_family = ""         # the OCR engine's family, used where the page has no text layer
    ocr_engine = ""
    modules: tuple[str, ...] = ()
    worker = True           # runs in its own environment when PDF_READER_PYTHON_<NAME> is set
    direct = False          # True: gives a Reading from the PDF itself (``direct_reading``), not tables for ``parse_page``

    def available(self) -> bool:
        if self.worker and os.environ.get(f"PDF_READER_PYTHON_{self.name.upper()}"):
            return True          # its own environment: the package is not imported here
        return all(_has(m) for m in self.modules)

    def extract(self, sub_pdf: bytes) -> list[tuple[int, list[list[str]]]]:
        """(1-based page of ``sub_pdf``, grid) per table. Heavy imports happen here, not at module import."""
        raise NotImplementedError

    def read_tables(self, pdf_bytes: bytes, pages: list[int]) -> list[Table]:
        sub = subset_pdf(pdf_bytes, pages)
        # a heavy reader never loads in the referee's process: a worker process of its own, one after another (owner, 26 Oct 2026)
        python = (os.environ.get(f"PDF_READER_PYTHON_{self.name.upper()}") or sys.executable) if self.worker else None
        found = _run_worker(python, self.name, sub) if python else self.extract(sub)
        tables = []
        for index, grid in found:
            if 1 <= index <= len(pages):
                tables.append(Table(self.name, pages[index - 1], [[clean_cell(c) for c in row] for row in grid],
                                    ocr_engine=self.ocr_engine))
        return tables


class NativeReader(Reader):
    """The pipeline's own reader, wrapped: ``pdf_referee.read_document`` (text layer; RapidOCR on scanned pages)."""
    name, family, ocr_family, ocr_engine = "native", "textlayer-native", "paddle", "rapidocr"
    worker = False

    def available(self) -> bool:
        return True

    def read_rows(self, payload: bytes, ocr: bool = True):
        from .pdf_referee import read_document
        return read_document(payload, ocr=ocr)

    def read_tables(self, pdf_bytes: bytes, pages: list[int]) -> list[Table]:
        """The interface's tables: each page's text as one-cell rows (the referee's own parsing reads lines of text)."""
        tables = []
        with _pymupdf().open(stream=pdf_bytes, filetype="pdf") as doc:
            for p in pages:
                lines = [ln for ln in doc[p - 1].get_text().splitlines() if ln.strip()]
                tables.append(Table(self.name, p, [[ln] for ln in lines]))
        return tables


class NumbersFirstReader(Reader):
    """The experimental numbers-first reader (``pdf_numbers_first``, 28 Oct 2026): bench only, chosen by ``PDF_READERS`` and by
    nothing else. It names rows by the arithmetic of the numeric columns and gives its Reading directly."""
    name, family, ocr_family, ocr_engine = "numfirst", "numbers-first", "paddle", "rapidocr"
    worker = False
    direct = True

    def __init__(self):
        self._cache: dict[str, list] = {}
        self.ocr_garbled = True          # a scan's garbled text layer is read with OCR too (the scored setting)
        self.ocr_boxes = None            # a cache of RapidOCR's boxes for the bench, else ``pdf_numbers_first.ocr_page_boxes``

    def available(self) -> bool:
        return True

    def tables(self, payload: bytes) -> list:
        import hashlib

        from . import pdf_numbers_first as nf
        key = hashlib.sha1(payload).hexdigest()
        if key not in self._cache:
            self._cache[key] = nf.analyse(payload, self.ocr_boxes, ocr_garbled=self.ocr_garbled)
            while len(self._cache) > 3:
                self._cache.pop(next(iter(self._cache)))
        return self._cache[key]

    def direct_reading(self, payload: bytes, period: str, metric: str, basis: str | None) -> "Reading":
        from . import pdf_numbers_first as nf
        return nf.reading_from_tables(self.tables(payload), period, metric, basis, self.name)


def _write_temp(data: bytes, suffix: str = ".pdf") -> str:
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    handle.write(data)
    handle.close()
    return handle.name


class CamelotReader(Reader):
    """Lattice first (ruled tables), stream on a page where lattice finds no table. Tuned for results statements: a line
    scale of 40 keeps thin rules, a row tolerance of 6 joins the two lines of a wrapped label (``row_tol``), the column
    tolerance of 2 and an edge tolerance of 100 keep a long label column from being cut as a table edge."""
    name = family = "camelot"
    modules = ("camelot",)

    def extract(self, sub_pdf):
        import camelot
        path = _write_temp(sub_pdf)
        out: list[tuple[int, list[list[str]]]] = []
        try:
            with _pymupdf().open(path) as doc:
                count = doc.page_count
            for page in range(1, count + 1):
                tables = camelot.read_pdf(path, pages=str(page), flavor="lattice", line_scale=40)
                good = [t for t in tables if t.df.shape[1] >= 3]
                if not good:
                    tables = camelot.read_pdf(path, pages=str(page), flavor="stream", row_tol=6, column_tol=2, edge_tol=100)
                    good = [t for t in tables if t.df.shape[1] >= 3]
                out += [(page, t.df.values.tolist()) for t in good]
        finally:
            os.unlink(path)
        return out


_DATE_WORD = re.compile(r"^\(?\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\)?$|^\d{1,2}(?:st|nd|rd|th)?$|^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?$", re.I)


class PdfplumberReader(Reader):
    """The lines strategy first; when it finds no table of three columns, the text strategy with explicit vertical lines placed
    from the x positions of the header's dates (the label column ends before the first date), snap and join tolerance 3."""
    name = family = "pdfplumber"
    modules = ("pdfplumber",)

    def extract(self, sub_pdf):
        import io
        import pdfplumber
        out: list[tuple[int, list[list[str]]]] = []
        lines_settings = {"vertical_strategy": "lines", "horizontal_strategy": "lines", "snap_tolerance": 3,
                          "join_tolerance": 3, "intersection_tolerance": 5}
        with pdfplumber.open(io.BytesIO(sub_pdf)) as pdf:
            for number, page in enumerate(pdf.pages, 1):
                found = [t for t in page.extract_tables(lines_settings) if t and max(len(r) for r in t) >= 3]
                if not found:
                    verticals = self.verticals(page)
                    if verticals:
                        text_settings = {"vertical_strategy": "explicit", "explicit_vertical_lines": verticals,
                                         "horizontal_strategy": "text", "snap_tolerance": 3, "join_tolerance": 3,
                                         "text_x_tolerance": 2, "text_y_tolerance": 3}
                        found = [t for t in page.extract_tables(text_settings) if t and max(len(r) for r in t) >= 3]
                out += [(number, t) for t in found]
        return out

    @staticmethod
    def verticals(page) -> list[float]:
        """Column boundaries from the line with the most date-like words: label | date | date ... | page edge."""
        words = page.extract_words(x_tolerance=2, y_tolerance=3)
        by_line: dict[int, list[dict]] = {}
        for w in words:
            if _DATE_WORD.match(w["text"]):
                by_line.setdefault(round(w["top"] / 12), []).append(w)
        if not by_line:
            return []
        best = max(by_line.values(), key=len)
        if len(best) < 2:
            return []
        centres = sorted((w["x0"] + w["x1"]) / 2 for w in best)
        first = min(w["x0"] for w in best)
        marks = [page.bbox[0], first - 2]
        marks += [(a + b) / 2 for a, b in zip(centres, centres[1:])]
        marks.append(page.bbox[2])
        return marks


class TabulaReader(Reader):
    """Lattice, then stream (needs Java on the PATH)."""
    name = family = "tabula"
    modules = ("tabula",)

    def available(self) -> bool:
        return super().available() and (shutil.which("java") is not None or bool(os.environ.get("PDF_READER_PYTHON_TABULA")))

    def extract(self, sub_pdf):
        import tabula
        path = _write_temp(sub_pdf)
        out: list[tuple[int, list[list[str]]]] = []
        try:
            with _pymupdf().open(path) as doc:
                count = doc.page_count
            for page in range(1, count + 1):
                opts = {"pages": page, "multiple_tables": True, "pandas_options": {"header": None, "dtype": str}, "silent": True}
                frames = tabula.read_pdf(path, lattice=True, **opts) or []
                frames = [f for f in frames if f.shape[1] >= 3]
                if not frames:
                    frames = [f for f in (tabula.read_pdf(path, stream=True, guess=True, **opts) or []) if f.shape[1] >= 3]
                out += [(page, f.fillna("").values.tolist()) for f in frames]
        finally:
            os.unlink(path)
        return out


class DoclingReader(Reader):
    """TableFormer in ACCURATE mode with cell matching, OCR on (RapidOCR by default, the paddle family)."""
    name = family = "docling"
    ocr_family, ocr_engine = "paddle", "rapidocr"
    modules = ("docling",)

    def extract(self, sub_pdf):
        import io
        from docling.datamodel.base_models import DocumentStream, InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
        from docling.document_converter import DocumentConverter, PdfFormatOption
        options = PdfPipelineOptions()
        options.do_ocr = True
        options.do_table_structure = True
        options.table_structure_options.mode = TableFormerMode.ACCURATE
        options.table_structure_options.do_cell_matching = True
        converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
        result = converter.convert(DocumentStream(name="statement.pdf", stream=io.BytesIO(sub_pdf)))
        out = []
        for table in result.document.tables:
            page = table.prov[0].page_no if table.prov else 1
            grid = []
            for r, row in enumerate(table.data.grid):
                cells = []
                for c, cell in enumerate(row):
                    start = (getattr(cell, "start_row_offset_idx", r), getattr(cell, "start_col_offset_idx", c))
                    # a spanned cell's text once, at its origin; a period-kind header ("Quarter ended") over several columns in each
                    cells.append(cell.text if start == (r, c) or is_group_header(clean_cell(cell.text)) else "")
                grid.append(cells)
            out.append((page, grid))
        return out


class MineruReader(Reader):
    """The ``mineru`` command, pipeline backend at full accuracy: layout model and table recognition on, formula off, OCR
    auto (text layer where there is one). Never the fast/basic mode (measured 26 Oct 2026: basic 69%, standard ~100% on 7
    filings, docs/bench/). Output ``*_content_list.json``: items of type "table" with an HTML ``table_body`` and a ``page_idx``."""
    name = family = "mineru"
    ocr_family, ocr_engine = "paddle", "paddleocr (mineru)"
    worker = False

    @staticmethod
    def binary() -> str | None:
        return shutil.which(os.environ.get("PDF_MINERU_BIN", "mineru"))

    def available(self) -> bool:
        return self.binary() is not None

    def extract(self, sub_pdf):
        import glob
        binary = self.binary()
        work = tempfile.mkdtemp(prefix="mineru-")
        path = os.path.join(work, "statement.pdf")
        with open(path, "wb") as fh:
            fh.write(sub_pdf)
        env = {**os.environ, "MINERU_TABLE_ENABLE": "true", "MINERU_FORMULA_ENABLE": "false"}
        env.setdefault("MINERU_MODEL_SOURCE", "huggingface")
        cmd = [binary, "-p", path, "-o", os.path.join(work, "out"), "-b", "pipeline", "-m", "auto", "-l", "en",
               "-f", "false", "-t", "true"]
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=WORKER_TIMEOUT, env=env)
            if done.returncode:
                raise RuntimeError(f"mineru exit {done.returncode}: {done.stderr[-200:]}")
            found = glob.glob(os.path.join(work, "out", "**", "*_content_list.json"), recursive=True)
            if not found:
                raise RuntimeError("mineru wrote no content list")
            with open(found[0], encoding="utf-8") as fh:
                items = json.load(fh)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        out = []
        for item in items:
            if item.get("type") == "table" and item.get("table_body"):
                for grid in html_tables(item["table_body"]):
                    out.append((int(item.get("page_idx", 0)) + 1, grid))
        return out


class PaddleReader(Reader):
    """PP-StructureV3 (PaddleOCR 3.x): layout detection on, table recognition on with the pipeline's own best table models
    (it classifies each table as wired or wireless and uses SLANeXt for the structure); formula, chart, seal, orientation and
    unwarping off. OCR reads every cell (the text layer is not used), so its figures are checked against the layer by the rule."""
    name = family = "paddle"
    ocr_family, ocr_engine = "paddle", "paddleocr"
    modules = ("paddleocr", "paddle")

    def extract(self, sub_pdf):
        from paddleocr import PPStructureV3
        # enable_mkldnn False: with oneDNN on (the default) the layout detector of paddlepaddle 3.3.1 stops every page with
        # "NotImplementedError: (Unimplemented) ConvertPirAttribute2RuntimeAttribute not support
        # [pir::ArrayAttribute<pir::DoubleAttribute>]" (run 40388046768, 29 of 29 PDFs; reproduced and mended with this flag)
        pipeline = PPStructureV3(use_table_recognition=True, use_formula_recognition=False, use_chart_recognition=False,
                                 use_seal_recognition=False, use_doc_orientation_classify=False, use_doc_unwarping=False,
                                 enable_mkldnn=False)
        path = _write_temp(sub_pdf)
        out = []
        try:
            for index, result in enumerate(pipeline.predict(input=path), 1):
                data = result.json
                data = data.get("res", data) if isinstance(data, dict) else {}
                for table in data.get("table_res_list", []) or []:
                    for grid in html_tables(table.get("pred_html", "")):
                        out.append((index, grid))
        finally:
            os.unlink(path)
        return out


class MarkerReader(Reader):
    """Marker 2 (Datalab; Surya inside), plain: the ``TableConverter``, html output, ``use_llm`` off, ``force_ocr`` off (OCR
    only where a page has no text layer). One page at a time, so each table keeps its page."""
    name, family = "marker", "surya"
    ocr_family, ocr_engine = "surya", "surya"
    modules = ("marker",)

    def extract(self, sub_pdf):
        from marker.config.parser import ConfigParser
        from marker.converters.table import TableConverter
        from marker.models import create_model_dict
        models = create_model_dict()
        out = []
        with _pymupdf().open(stream=sub_pdf, filetype="pdf") as doc:
            count = doc.page_count
        for page in range(1, count + 1):
            parser = ConfigParser({"output_format": "html", "use_llm": False, "force_ocr": False, "page_range": "0"})
            converter = TableConverter(artifact_dict=models, config=parser.generate_config_dict(),
                                       processor_list=parser.get_processors(), renderer=parser.get_renderer(), llm_service=None)
            path = _write_temp(subset_pdf(sub_pdf, [page]))
            try:
                rendered = converter(path)
            finally:
                os.unlink(path)
            for grid in html_tables(getattr(rendered, "html", "") or ""):
                out.append((page, grid))
        return out


class SuryaReader(Reader):
    """Surya used directly: layout (tables found on a 200 dpi render), then table recognition on each crop by the full path
    (HTML with spans). CPU. No LLM service."""
    name = family = "surya"
    ocr_family, ocr_engine = "surya", "surya"
    modules = ("surya",)

    def extract(self, sub_pdf):
        from surya.layout import LayoutPredictor
        from surya.table_rec import TableRecPredictor
        layout, tables = LayoutPredictor(), TableRecPredictor()
        out = []
        for page, image in enumerate(render_pages(sub_pdf), 1):
            boxes = [b for b in layout([image])[0].bboxes if str(b.label).lower() in ("table", "tableofcontents", "form")]
            crops = []
            for b in boxes:
                x0, y0, x1, y1 = (int(v) for v in b.bbox)
                crops.append(image.crop((max(0, x0 - 8), max(0, y0 - 8), x1 + 8, y1 + 8)))
            for result in (tables.predict_full(crops) if crops else []):
                for grid in html_tables(result.html or ""):
                    out.append((page, grid))
        return out


def table_region(words: list) -> tuple[float, float, float, float] | None:
    """(x0, y0, x1, y1) in points of a results table on a text-layer page: from three rows above the first row of dates (the group
    words, "Particulars") to the last row of figures before a gap of six rows with none (the notes). None when no row has two
    dates. SLANet reads one table at a time (PP-StructureV3 gives it layout crops); a whole page of title, table and notes made
    its rows run into each other (rapid-table on 0f9e366d page 7: "Revenue from operations" empty, its figures a row lower)."""
    from .pdf_referee import _dates_in
    rows: list[list[tuple]] = []
    for w in sorted(words, key=lambda w: (w[1] + w[3]) / 2):
        if rows and (w[1] + w[3]) / 2 - sum((x[1] + x[3]) / 2 for x in rows[-1]) / len(rows[-1]) <= 3.5:
            rows[-1].append(w)
        else:
            rows.append([w])
    texts = [" ".join(x[4] for x in sorted(r, key=lambda x: x[0])) for r in rows]
    dated = next((i for i, t in enumerate(texts) if len(_dates_in(t)) >= 2), None)
    if dated is None:
        return None
    first, last, gap = max(0, dated - 3), dated, 0
    for i in range(dated + 1, len(rows)):
        figures = sum(1 for x in rows[i] if _NUMTOK.match(x[4]))
        if figures >= 2:
            last, gap = i, 0
        else:
            gap += 1
            if gap >= 6:
                break
    chosen = [w for r in rows[first: last + 1] for w in r]
    return (min(w[0] for w in chosen), min(w[1] for w in chosen), max(w[2] for w in chosen), max(w[3] for w in chosen))


class RapidTableReader(Reader):
    """rapid-table (SLANet-plus, ONNX), the PP-StructureV3 table models without the Paddle framework. The page is rendered at
    200 dpi; the cell text comes from the page's text-layer words (boxes scaled to the image) when it has a layer, else from
    RapidOCR. There is no layout model: a text-layer page is cropped to its results table (``table_region``), a scan is passed whole."""
    name, family = "rapidtable", "paddle"   # the PP-StructureV3 table models: one family with PaddleReader
    ocr_family, ocr_engine = "paddle", "rapidocr"
    modules = ("rapid_table", "rapidocr")

    def extract(self, sub_pdf):
        import numpy as np
        from rapid_table import ModelType, RapidTable, RapidTableInput
        engine = RapidTable(RapidTableInput(model_type=ModelType.SLANETPLUS))
        ocr = None
        out = []
        scale = DPI / 72
        with _pymupdf().open(stream=sub_pdf, filetype="pdf") as doc:
            for index, page in enumerate(doc, 1):
                image = render_pages_one(page, DPI)
                words = page.get_text("words")
                if sum(len(w[4]) for w in words) >= LAYER_MIN_CHARS:
                    region = table_region(words)
                    if region:      # the table alone, with a margin; the words inside it, in the crop's own coordinates
                        pad = 6.0
                        x0, y0, x1, y1 = (max(0.0, region[0] - pad), max(0.0, region[1] - pad), region[2] + pad, region[3] + pad)
                        image = image.crop((int(x0 * scale), int(y0 * scale), min(image.width, int(x1 * scale) + 1),
                                            min(image.height, int(y1 * scale) + 1)))
                        words = [(w[0] - x0, w[1] - y0, w[2] - x0, w[3] - y0, w[4]) for w in words
                                 if w[0] >= x0 - 1 and w[2] <= x1 + 1 and w[1] >= y0 - 1 and w[3] <= y1 + 1]
                    boxes = [[[w[0] * scale, w[1] * scale], [w[2] * scale, w[1] * scale], [w[2] * scale, w[3] * scale],
                              [w[0] * scale, w[3] * scale]] for w in words]
                    found = (np.array(boxes, dtype="float32"), [w[4] for w in words], [1.0] * len(words))
                else:
                    if ocr is None:
                        from rapidocr import RapidOCR
                        ocr = RapidOCR()
                    result = ocr(np.array(image))
                    found = (result.boxes, result.txts, result.scores)
                if found[1] is None or not len(found[1]):
                    continue
                result = engine(np.array(image), ocr_results=[found])
                for html in getattr(result, "pred_htmls", None) or []:
                    for grid in html_tables(html):
                        out.append((index, grid))
        return out


# Table Transformer ------------------------------------------------------------------------------------------------

def cells_from_structure(rows: list[tuple], cols: list[tuple], text_of) -> list[list[str]]:
    """The grid of row x column intersections; ``text_of((x0, y0, x1, y1))`` gives a cell's text."""
    rows = sorted(rows, key=lambda b: b[1])
    cols = sorted(cols, key=lambda b: b[0])
    return [[text_of((c[0], r[1], c[2], r[3]), ci) for ci, c in enumerate(cols)] for r in rows]


def words_in(words: list[tuple], box: tuple) -> str:
    """The words (x0, y0, x1, y1, text) whose centre lies inside ``box``, in reading order."""
    inside = [w for w in words if box[0] <= (w[0] + w[2]) / 2 <= box[2] and box[1] <= (w[1] + w[3]) / 2 <= box[3]]
    inside.sort(key=lambda w: (round(w[1] / 4), w[0]))
    return " ".join(w[4] for w in inside)


_NUMERICISH = re.compile(r"[\d.,()\-\s]")


class MistralOcrReader(Reader):
    """Mistral's Document OCR API (``POST /v1/ocr``, model ``MISTRAL_OCR_MODEL``, default ``mistral-ocr-latest``), bench only (lead,
    30 Oct 2026): never in a live path. The statement pages go as a base64 data URL, one page a request by default; tables come back as HTML
    (``table_format``) in the page's ``tables`` or inline in its markdown. ``MISTRAL_OCR_PAGE_CAP`` (default 300) pages a process,
    then no answer: at up to $10 per 1,000 pages that stays inside the lead's $3. ``MISTRAL_OCR_RAW_DIR`` keeps each answer."""
    name, family = "mistral", "mistral"
    ocr_family, ocr_engine = "mistral", "mistral-ocr"
    modules = ("httpx",)
    worker = False
    pages_used = 0          # pages the API reported processed in this process (``usage_info.pages_processed``)

    def available(self) -> bool:
        return bool(os.environ.get("MISTRAL_API_KEY")) and super().available()

    last_call = 0.0         # time.monotonic() of the last request, for MISTRAL_OCR_SPACING_S

    def extract(self, sub_pdf):
        """One request a page by default (``MISTRAL_OCR_PER_PAGE``, default on; off sends the PDF in one request), spaced
        ``MISTRAL_OCR_SPACING_S`` (default 3 s) apart: the Free plan allows OCR (owner, 1 Nov 2026) and every request of runs
        41072420377, 41076952339 and 41267832784 got 429 "Rate limit exceeded" (code 1300), so it is a real rate limit."""
        with _pymupdf().open(stream=sub_pdf, filetype="pdf") as doc:
            count = doc.page_count
        if os.environ.get("MISTRAL_OCR_PER_PAGE", "1") == "0" or count <= 1:
            return self._ocr(sub_pdf, count)
        out = []
        for page in range(1, count + 1):
            try:
                out.extend((page, grid) for _, grid in self._ocr(subset_pdf(sub_pdf, [page]), 1))
            except RuntimeError:
                if not out:
                    raise         # nothing read: the refusal (or the cap) is the answer
                break             # pages already read and paid for are kept (review of d0a3c41)
        return out

    def _ocr(self, pdf: bytes, count: int):
        import base64
        import hashlib
        import time

        import httpx
        cap = int(os.environ.get("MISTRAL_OCR_PAGE_CAP", "300"))
        if MistralOcrReader.pages_used + count > cap:
            raise RuntimeError(f"page cap {cap} reached ({MistralOcrReader.pages_used} used)")
        body = {"model": os.environ.get("MISTRAL_OCR_MODEL", "mistral-ocr-latest"), "table_format": "html", "include_blocks": True,
                "document": {"type": "document_url", "document_url": "data:application/pdf;base64," + base64.b64encode(pdf).decode()}}
        spacing = float(os.environ.get("MISTRAL_OCR_SPACING_S", "3"))
        t0 = time.perf_counter()
        for wait in (5, 20, 60, None):   # a 429 waits (its Retry-After when it gives one) and tries again
            gap = spacing - (time.monotonic() - MistralOcrReader.last_call)
            if gap > 0:
                time.sleep(gap)
            MistralOcrReader.last_call = time.monotonic()
            reply = httpx.post("https://api.mistral.ai/v1/ocr", json=body, timeout=180,
                               headers={"Authorization": f"Bearer {os.environ['MISTRAL_API_KEY'].strip()}"})
            if reply.status_code != 429 or wait is None:
                break
            try:
                wait = max(0.0, min(120.0, float(reply.headers.get("retry-after") or wait)))
            except ValueError:
                pass
            time.sleep(wait)
        raw_dir = os.environ.get("MISTRAL_OCR_RAW_DIR")
        if reply.status_code >= 400:
            _keep_refusal(raw_dir, reply)
            raise RuntimeError(f"mistral ocr HTTP {reply.status_code}: {reply.text[:200]}")
        answer = reply.json()
        answer["_seconds"] = round(time.perf_counter() - t0, 2)
        MistralOcrReader.pages_used += int((answer.get("usage_info") or {}).get("pages_processed") or count)
        if raw_dir:
            os.makedirs(raw_dir, exist_ok=True)
            with open(os.path.join(raw_dir, hashlib.sha256(pdf).hexdigest()[:16] + ".json"), "w", encoding="utf-8") as fh:
                json.dump(answer, fh)
        return mistral_grids(answer)


class NemotronParseReader(Reader):
    """NVIDIA's nemotron-parse on build.nvidia.com (``NEMOTRON_PARSE_MODEL``, default ``nvidia/nemotron-parse``), bench only (lead,
    30 Oct 2026): never in a live path. Each statement page goes as one PNG (fitted inside the model's 1648 x 2048) to the
    OpenAI-style chat endpoint with the ``markdown_bbox`` tool; the answer is a list of elements (normalised bbox, text, type),
    and a table element's text is turned into a grid (LaTeX tabular, HTML or pipe table). ``NEMOTRON_PARSE_PAGE_CAP`` (default
    300) pages a process; ``NEMOTRON_PARSE_RAW_DIR`` keeps each answer; ``seconds`` sums the calls. ``env`` names the switches,
    so a second model (``NemotronParse2Reader``) keeps its own cap, folder and count."""
    name, family = "nemotron", "nemotron"
    env, model = "NEMOTRON_PARSE", "nvidia/nemotron-parse"
    named_tool = False      # True: the tool named in tool_choice (an endpoint without "auto" tool choice answers 400 otherwise)
    ocr_family, ocr_engine = "nemotron", "nemotron-parse"
    modules = ("httpx",)
    worker = False
    pages_used = 0
    seconds = 0.0

    def available(self) -> bool:
        return bool(os.environ.get("NVIDIA_API_KEY")) and super().available()

    def extract(self, sub_pdf):
        import base64
        import hashlib
        import time

        import httpx
        cap = int(os.environ.get(f"{self.env}_PAGE_CAP", "300"))
        raw_dir = os.environ.get(f"{self.env}_RAW_DIR")
        out = []
        with _pymupdf().open(stream=sub_pdf, filetype="pdf") as doc:
            for number, page in enumerate(doc, start=1):
                if type(self).pages_used >= cap:
                    raise RuntimeError(f"page cap {cap} reached")
                zoom = min(1648 / page.rect.width, 2048 / page.rect.height)
                png = page.get_pixmap(matrix=_pymupdf().Matrix(zoom, zoom)).tobytes("png")
                body = {"model": os.environ.get(f"{self.env}_MODEL", self.model), "temperature": 0,
                        "tools": [{"type": "function", "function": {"name": "markdown_bbox"}}],
                        **({"tool_choice": {"type": "function", "function": {"name": "markdown_bbox"}}} if self.named_tool else {}),
                        "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {
                            "url": "data:image/png;base64," + base64.b64encode(png).decode()}}]}]}
                t0 = time.perf_counter()
                reply = httpx.post("https://integrate.api.nvidia.com/v1/chat/completions", json=body, timeout=180,
                                   headers={"Authorization": f"Bearer {os.environ['NVIDIA_API_KEY'].strip()}",
                                            "Accept": "application/json"})
                type(self).seconds += time.perf_counter() - t0
                type(self).pages_used += 1
                if reply.status_code >= 400:
                    _keep_refusal(raw_dir, reply)
                    raise RuntimeError(f"{self.model} HTTP {reply.status_code}: {reply.text[:200]}")
                answer = reply.json()
                answer["_seconds"] = round(time.perf_counter() - t0, 2)
                if raw_dir:
                    os.makedirs(raw_dir, exist_ok=True)
                    name = hashlib.sha256(png).hexdigest()[:16] + ".json"
                    with open(os.path.join(raw_dir, name), "w", encoding="utf-8") as fh:
                        json.dump(answer, fh)
                out.extend((number, g) for g in nemotron_grids(answer))
        return out


class NemotronParse2Reader(NemotronParseReader):
    """nemotron-parse 2.0 (``NEMOTRON_PARSE2_MODEL``, default ``nvidia/nemotron-parse-2.0``), the same call and answer as
    ``NemotronParseReader`` (lead, 30 Oct 2026: listed on our free NVIDIA key, providers-check run 41059917128); bench only."""
    name, ocr_engine = "nemotron2", "nemotron-parse-2.0"
    env, model = "NEMOTRON_PARSE2", "nvidia/nemotron-parse-2.0"
    named_tool = True       # probe run 41072420377: 400 '"auto" tool choice requires --enable-auto-tool-choice'

    pages_used = 0
    seconds = 0.0


class NemotronParse35Reader(NemotronParseReader):
    """nemotron-3.5-parse (``NEMOTRON_PARSE35_MODEL``, default ``nvidia/nemotron-3.5-parse``), the same call and answer as
    ``NemotronParseReader`` (lead, 30 Oct 2026: a free endpoint on the owner's NVIDIA catalogue; nemotron-parse-2.0 is
    downloadable only); bench only, probed on one page first."""
    name, ocr_engine = "nemotron35", "nemotron-3.5-parse"
    env, model = "NEMOTRON_PARSE35", "nvidia/nemotron-3.5-parse"
    pages_used = 0
    seconds = 0.0


def _keep_refusal(raw_dir: str | None, reply) -> None:
    """An API reader's refusal kept beside its answers (``refused-<n>.json``: status and body), so a run's artifact says why;
    the scorer keeps only the error's type."""
    if not raw_dir:
        return
    os.makedirs(raw_dir, exist_ok=True)
    n = len([f for f in os.listdir(raw_dir) if f.startswith("refused-")])
    with open(os.path.join(raw_dir, f"refused-{n}.json"), "w", encoding="utf-8") as fh:
        limits = {k: v for k, v in reply.headers.items() if "ratelimit" in k.lower() or k.lower() == "retry-after"}
        json.dump({"status": reply.status_code, "body": reply.text[:2000], "headers": limits}, fh)


def nemotron_grids(answer: dict) -> list[list[list[str]]]:
    """The grids of the table elements of a nemotron-parse answer (the ``markdown_bbox`` tool call's JSON list, sometimes
    nested one level). The answer gives a page's title and unit line as elements of their own, so the text elements above
    each table (since the one before it, in the answer's reading order: titles, page headers and short text lines, never
    notes, list items or captions) go in as its first rows (``NEMOTRON_HEADER``, default on): the basis and the unit are read from them. A cell holding a figure with two decimal points (FIVESTAR Q1FY24 "18.370.88" for 18,370.88, read
    as 18.37: run 41063175585) is emptied, so it gives no answer rather than a wrong one. ``NEMOTRON_NEED_UNIT`` (default off;
    measured 30 Oct: it dropped right tables and let another table on the page answer wrong) drops a table with no unit word
    in it or above it."""
    header_on = os.environ.get("NEMOTRON_HEADER", "1") != "0"
    need_unit = os.environ.get("NEMOTRON_NEED_UNIT", "0") == "1"
    # NEMOTRON_BASIS_GUARD (default off; lead, 1 Nov 2026): a table is read only when its own header rows (the lines above it
    # in this answer, or its first two rows) name exactly one basis, consolidated or standalone ("Notes to ..." headings never
    # count); the page's context never decides its basis.
    # Out of sample (run 41077643109) the one real basis wrong was a table whose basis came from elsewhere (SMARTWORKS)
    basis_guard = os.environ.get("NEMOTRON_BASIS_GUARD", "0") == "1"
    grids = []
    for choice in answer.get("choices") or []:
        for call in (choice.get("message") or {}).get("tool_calls") or []:
            try:
                items = json.loads((call.get("function") or {}).get("arguments") or "[]")
            except ValueError:
                continue
            while len(items) == 1 and isinstance(items[0], list):
                items = items[0]
            if items and isinstance(items[0], list):
                items = [e for group in items for e in group]
            above: list[str] = []
            after_table = False
            # the answer's own reading order: sorting by height mixed two blocks side by side (J&KBANK, 4 consolidated PATs
            # given another title: replay of run 41063175585, 30 Oct 2026)
            for element in (e for e in items if isinstance(e, dict)):
                kind = str(element.get("type", "")).lower()
                text = element.get("text") or ""
                if kind != "table":
                    # titles and short lines only (a unit or a basis line); notes, list items and captions never name a table.
                    # After a table a short line is its footnote until a new title starts the next block (blind review)
                    titled = kind in ("title", "section-header", "page-header")
                    after_table = after_table and not titled
                    if titled or (kind == "text" and len(text) <= 120 and not after_table):
                        above.append(re.sub(r"<br\s*/?>|\*\*|\\textbf\{|\}", " ", text).strip())
                    continue
                after_table = True
                found = [[["" if garbled_figure(c) else c for c in row] for row in grid]
                         for grid in (latex_tables(text) or html_tables(text) or markdown_tables(text))]
                head = [[line] for line in above[-6:] if line] if header_on else []
                above = []
                for grid in found:
                    if need_unit and not (_UNIT_WORD.search(text) or any(_UNIT_WORD.search(h[0]) for h in head)):
                        continue
                    if basis_guard:
                        # a "Notes to ..." heading names the statement the notes belong to, not the table under it
                        # (SMARTWORKS: standalone key figures under "NOTES TO ... CONSOLIDATED RESULTS", run 41077643109)
                        own = [h for h in head if not re.match(r"\s*notes?\b", h[0], re.I)]
                        named = "\n".join([h[0] for h in own] + [" ".join(r) for r in grid[:2]])
                        if bool(_CONS_WORD.search(named)) == bool(_ALONE_WORD.search(named)):
                            continue          # no basis named, or both: the table's basis is not its own to tell
                        grids.append(own + grid)
                        continue
                    grids.append(head + grid)
    return grids


def latex_tables(text: str) -> list[list[list[str]]]:
    """The grids of LaTeX tabular environments: rows split on \\\\, cells on &, rules dropped, \\multicolumn{n}{..}{x} as x
    and n-1 empty cells."""
    tables = []
    for body in re.findall(r"\\begin\{tabular\}(?:\{[^}]*\})?(.*?)\\end\{tabular\}", text or "", re.S):
        rows = []
        for line in re.split(r"\\\\", body):
            line = re.sub(r"\\(hline|toprule|midrule|bottomrule|cline\{[^}]*\})", "", line).strip()
            if not line:
                continue
            cells = []
            for cell in line.split("&"):
                m = re.match(r"\s*\\multicolumn\{(\d+)\}\{[^}]*\}\{(.*)\}\s*$", cell, re.S)
                if m:
                    cells += [m.group(2).strip()] + [""] * (int(m.group(1)) - 1)
                else:
                    cells.append(cell.strip())
            rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def mistral_grids(answer: dict) -> list[tuple[int, list[list[str]]]]:
    """(1-based page, grid) for every table of a Mistral OCR answer: the page's ``tables`` (HTML) when it lists them, else the
    HTML or pipe tables written into its markdown."""
    out = []
    for page in answer.get("pages") or []:
        number = int(page.get("index", 0)) + 1
        listed = [t.get("content") or t.get("html") or "" for t in page.get("tables") or []]
        grids = [g for html in listed for g in html_tables(html)]
        if not grids:
            text = page.get("markdown") or ""
            grids = html_tables(text) or markdown_tables(text)
        out.extend((number, g) for g in grids)
    return out


def markdown_tables(text: str) -> list[list[list[str]]]:
    """The grids of the pipe tables in markdown; the ``|---|`` rule line is dropped."""
    tables, rows = [], []
    for line in (text or "").splitlines() + [""]:
        line = line.strip()
        if line.startswith("|") and line.endswith("|") and len(line) > 1:
            cells = [c.strip() for c in line[1:-1].split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c) or not any(cells):
                rows.append(cells)
        elif rows:
            tables.append(rows)
            rows = []
    return tables


class TatrReader(Reader):
    """Microsoft Table Transformer: detection ``table-transformer-detection``, structure
    ``table-transformer-structure-recognition-v1.1-all`` (PubTables-1M + FinTabNet), CPU, pages rendered at 250 dpi. Cell text is
    the text layer's words inside each cell (image to PDF coordinates); on a page with no text layer each cell is read by
    Tesseract (``--psm 7``; a numeric-looking cell is read again with a digits whitelist), independent of the paddle family."""
    name = family = "tatr"
    ocr_family, ocr_engine = "tesseract", "tesseract"
    modules = ("transformers", "timm", "torch", "pymupdf")
    DETECTION = "microsoft/table-transformer-detection"
    STRUCTURE = "microsoft/table-transformer-structure-recognition-v1.1-all"
    RENDER_DPI = 250
    PAD = 20

    def extract(self, sub_pdf):
        import torch
        from transformers import AutoImageProcessor, TableTransformerForObjectDetection
        processor = AutoImageProcessor.from_pretrained(self.DETECTION)
        detector = TableTransformerForObjectDetection.from_pretrained(self.DETECTION).eval()
        s_processor = AutoImageProcessor.from_pretrained(self.STRUCTURE)
        structure = self._structure_model(TableTransformerForObjectDetection).eval()
        scale = self.RENDER_DPI / 72
        out = []
        with _pymupdf().open(stream=sub_pdf, filetype="pdf") as doc:
            for index, page in enumerate(doc, 1):
                words = [(w[0] * scale, w[1] * scale, w[2] * scale, w[3] * scale, w[4]) for w in page.get_text("words")]
                layer = len(" ".join(w[4] for w in words)) >= LAYER_MIN_CHARS
                image = render_pages_one(page, self.RENDER_DPI)
                for box in self._detect(torch, processor, detector, image):
                    x0, y0 = max(0, box[0] - self.PAD), max(0, box[1] - self.PAD)
                    crop = image.crop((x0, y0, min(image.width, box[2] + self.PAD), min(image.height, box[3] + self.PAD)))
                    rows, cols = self._structure(torch, s_processor, structure, crop)
                    if len(rows) < 2 or len(cols) < 2:
                        continue
                    if layer:
                        def text_of(b, _ci, ox=x0, oy=y0):
                            return words_in(words, (b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy))
                    else:
                        def text_of(b, ci, c=crop):
                            return ocr_cell(c, b, numeric=ci > 0)
                    out.append((index, cells_from_structure(rows, cols, text_of)))
        return out

    @staticmethod
    def _longest_side(processor, image):
        """(image, processor kwargs). The structure processor's size is ``{"longest_edge": N}`` only (the published config), which
        transformers 5 refuses ("Size must contain 'height' and 'width' keys or 'shortest_edge' and 'longest_edge' keys", measured
        26 Oct 2026 with transformers 5.21.0). The model's recipe is a resize of the longest side to N, so the image is resized
        here and the processor told not to. A size with both keys, or none, changes nothing."""
        size = getattr(processor, "size", None)
        get = (lambda k: size.get(k)) if isinstance(size, dict) else (lambda k: getattr(size, k, None))
        longest = get("longest_edge") if size is not None else None
        if not longest or get("shortest_edge"):
            return image, {}
        scale = longest / max(image.size)
        return image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale)))), {"do_resize": False}

    @classmethod
    def _structure_model(cls, model_class):
        """The structure model. Its published config (v1.1-all) has ``"dilation": null``, which transformers 5 refuses (the config
        is a strict dataclass: "Field 'dilation' expected bool, got NoneType", the failure of every tatr read on 26 Oct 2026, run
        40388046768); the same config with ``dilation`` false (null means off) loads."""
        try:
            return model_class.from_pretrained(cls.STRUCTURE)
        except Exception as exc:   # noqa: BLE001 - only the config's null field is mended; anything else is raised as it was
            if "dilation" not in str(exc):
                raise
            from huggingface_hub import hf_hub_download
            from transformers import TableTransformerConfig
            with open(hf_hub_download(cls.STRUCTURE, "config.json"), encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("dilation") is None:
                data["dilation"] = False
            return model_class.from_pretrained(cls.STRUCTURE, config=TableTransformerConfig.from_dict(data))

    @staticmethod
    def _detect(torch, processor, model, image) -> list[tuple]:
        inputs = processor(images=image, return_tensors="pt")
        with torch.no_grad():
            outputs = model(**inputs)
        res = processor.post_process_object_detection(outputs, threshold=0.7, target_sizes=[image.size[::-1]])[0]
        labels = model.config.id2label
        return [tuple(float(v) for v in box) for box, lab in zip(res["boxes"], res["labels"]) if labels[int(lab)] == "table"]

    @staticmethod
    def _structure(torch, processor, model, crop) -> tuple[list[tuple], list[tuple]]:
        image, kwargs = TatrReader._longest_side(processor, crop)
        inputs = processor(images=image, return_tensors="pt", **kwargs)
        with torch.no_grad():
            outputs = model(**inputs)
        res = processor.post_process_object_detection(outputs, threshold=0.6, target_sizes=[crop.size[::-1]])[0]
        labels = model.config.id2label
        rows, cols = [], []
        for box, lab in zip(res["boxes"], res["labels"]):
            name, b = labels[int(lab)], tuple(float(v) for v in box)
            if name == "table row":
                rows.append(b)
            elif name == "table column":
                cols.append(b)
        return rows, cols


def render_pages_one(page, dpi: int):
    from PIL import Image
    pix = page.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def ocr_cell(image, box: tuple, numeric: bool = False) -> str:
    """Tesseract on one cell: ``--psm 7`` (a single line); a cell that reads as figures is read again with a digits whitelist."""
    import pytesseract
    cell = image.crop((int(box[0]), int(box[1]), int(box[2]), int(box[3])))
    text = pytesseract.image_to_string(cell, config="--psm 7").strip()
    if numeric and text and re.search(r"\d", text) and sum(bool(_NUMERICISH.match(ch)) for ch in text) / len(text) >= 0.6:
        text = pytesseract.image_to_string(cell, config="--psm 7 -c tessedit_char_whitelist=0123456789.,()-").strip() or text
    return text


READERS: dict[str, Reader] = {r.name: r for r in (
    NativeReader(), CamelotReader(), PdfplumberReader(), TabulaReader(), DoclingReader(), MineruReader(), PaddleReader(),
    RapidTableReader(), MarkerReader(), SuryaReader(), TatrReader(), NumbersFirstReader(), MistralOcrReader(), NemotronParseReader(), NemotronParse2Reader(), NemotronParse35Reader())}

DEFAULT_READERS = "native"


def configured_readers(value: str | None = None) -> list[str]:
    """The readers named by ``PDF_READERS`` (comma list; default ``native``: today's behaviour, no other reader)."""
    raw = value if value is not None else os.environ.get("PDF_READERS", DEFAULT_READERS)
    names = [n.strip().lower() for n in raw.split(",") if n.strip()] or [DEFAULT_READERS]
    unknown = [n for n in names if n not in READERS]
    if unknown:
        raise ValueError(f"unknown PDF reader(s) {unknown}; known: {sorted(READERS)}")
    return list(dict.fromkeys(names))


# --- running a reader in its own environment ---------------------------------------------------------------------

def _run_worker(python: str, name: str, sub_pdf: bytes) -> list[tuple[int, list[list[str]]]]:
    path = _write_temp(sub_pdf)
    out_path = path + ".json"
    try:
        done = subprocess.run([python, "-m", "bse_intel.pdf_readers", "--worker", name, path, out_path],
                              capture_output=True, text=True, timeout=WORKER_TIMEOUT)
        if done.returncode:
            raise RuntimeError(f"{name} worker exit {done.returncode}: {done.stderr[-300:]}")
        with open(out_path, encoding="utf-8") as fh:
            return [(int(i), grid) for i, grid in json.load(fh)]
    finally:
        for p in (path, out_path):
            if os.path.exists(p):
                os.unlink(p)


def _worker_main(argv: list[str]) -> int:
    name, pdf_path, out_path = argv
    with open(pdf_path, "rb") as fh:
        data = fh.read()
    found = READERS[name].extract(data)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump([[i, grid] for i, grid in found], fh)
    return 0


# --- the ensemble over one PDF ----------------------------------------------------------------------------------------

class Ensemble:
    """The configured readers over each PDF, read once (the last few PDFs are kept) and asked for every pair of the PDF."""

    KEEP = 3

    def __init__(self, names: list[str], ocr: bool = True):
        self.names, self.ocr = names, ocr
        self.cache: dict[str, dict] = {}
        self.calls: dict[str, int] = {n: 0 for n in names}
        # readings made earlier, one file a reader (``--read``; the maintenance matrix runs each reader in a job of its own)
        self.tables_dir = os.environ.get("PDF_READER_TABLES_DIR") or None
        self.files: dict[str, dict | None] = {}

    def _stored(self, name: str, key: str):
        """(status, tables) of reader ``name`` for the PDF, from its file in ``tables_dir``."""
        if name not in self.files:
            path = os.path.join(self.tables_dir, f"{name}.json")
            try:
                with open(path, encoding="utf-8") as fh:
                    self.files[name] = json.load(fh).get("pdfs", {})
            except (OSError, ValueError):
                self.files[name] = None
        file = self.files[name]
        entry = file.get(pdf_key(key)) if file is not None else None
        if entry is None:
            return "unavailable", None
        if entry.get("error"):
            return "error", entry["error"][:80]
        return "ok", [Table(name, t["page"], t["cells"], ocr_engine=t.get("ocr_engine", "")) for t in entry["tables"]]

    def _load(self, key: str, payload: bytes) -> dict:
        if key in self.cache:
            return self.cache[key]
        entry: dict = {"layers": {}, "rows": {}, "anywhere": True}
        try:
            entry["layers"] = page_layers(payload)
            entry["anywhere"] = consolidated_anywhere(entry["layers"])      # one basis context for every reader
            pages = statement_pages(entry["layers"])
        except Exception as exc:   # noqa: BLE001 - an unreadable PDF is a reason, not a stop
            log.warning("pdf readers: layers failed (%s)", type(exc).__name__)
            pages = []
        for name in self.names:
            reader = READERS[name]
            if reader.direct:
                entry["rows"][name] = ("direct", None)
                continue
            if self.tables_dir and not isinstance(reader, NativeReader):
                status, tables = self._stored(name, key)
                entry["rows"][name] = (status, tables_to_rows(tables, entry["layers"], entry["anywhere"]) if status == "ok" else tables)
                continue
            if not reader.available():
                entry["rows"][name] = ("unavailable", None)
                continue
            try:
                self.calls[name] += 1
                if isinstance(reader, NativeReader):
                    rows, why = reader.read_rows(payload, self.ocr)
                    entry["rows"][name] = ("ok", rows or []) if rows is not None else ("error", why)
                elif not pages:
                    entry["rows"][name] = ("none", [])
                else:
                    tables = reader.read_tables(payload, pages)
                    entry["rows"][name] = ("ok", tables_to_rows(tables, entry["layers"], entry["anywhere"]))
            except Exception as exc:   # noqa: BLE001 - one reader failing leaves the others
                log.warning("pdf reader %s failed: %s", name, exc)
                entry["rows"][name] = ("error", f"{type(exc).__name__}")
        self.cache[key] = entry
        while len(self.cache) > self.KEEP:
            self.cache.pop(next(iter(self.cache)))
        return entry

    def readings(self, key: str, payload: bytes, period: str, metric: str, basis: str | None) -> list[Reading]:
        entry = self._load(key, payload)
        out = []
        for name in self.names:
            status, rows = entry["rows"][name]
            reader = READERS[name]
            if status == "direct":
                try:
                    out.append(reader.direct_reading(payload, period, metric, basis))
                except Exception as exc:   # noqa: BLE001 - one reader failing leaves the others
                    log.warning("pdf reader %s failed: %s", name, exc)
                    out.append(Reading(name, reader.family, "error", note=type(exc).__name__))
            elif status in ("unavailable", "error"):
                out.append(Reading(name, reader.family, status, note=str(rows or "")))
            elif not rows:
                out.append(Reading(name, reader.family, "none", note="no results row"))
            else:
                out.append(reading_of(reader, rows, entry["layers"], period, metric, basis, entry["anywhere"]))
        return out


def referee_pair_ensemble(src, row: dict, out: dict, listed: list, ours: float, theirs: float, xbrl: float | None) -> dict:
    """The verdict fields of one pair with several readers: the figure must be settled by ``settle``. ``src`` is the referee's
    ``Sources`` (it downloads and caches the PDFs); ``out`` is the verdict dict being filled."""
    from .pdf_referee import MAX_CANDIDATES, verdict_of
    period, metric = row["period"], row["metric"]
    if not row.get("basis"):
        out["reason"] = "the pair names no basis: a figure's basis cannot be proven"
        out["pdf_verdict"] = "pdf_unsure"
        return out
    reasons: list[str] = []
    unsure: list[str] = []
    for f in listed[:MAX_CANDIDATES]:
        payload, why = src.payload(f.pdf_url)
        if payload is None:
            reasons.append(why)
            continue
        readings = src.ensemble.readings(f.pdf_url, payload, period, metric, row.get("basis") or None)
        verdict = settle(readings)
        out["readers"] = verdict.readers_text()
        if verdict.status == "settled":
            v, matches, value, label = verdict_of([(verdict.value, verdict.label, verdict.page)], ours, theirs, xbrl, metric)
            out.update(pdf_verdict=v, pdf_value=value, pdf_label=label, pdf_url=f.pdf_url, matches="|".join(matches),
                       reason="")
            return out
        if verdict.status == "disagree":
            out.update(pdf_verdict="pdf_disagree", pdf_value=verdict.value, pdf_label=verdict.label, pdf_url=f.pdf_url,
                       reason=verdict.reason[:200])
            return out
        if verdict.status == "scanned_lead":
            out.update(pdf_verdict="pdf_scanned_lead", pdf_value=verdict.value, pdf_label=verdict.label, pdf_url=f.pdf_url,
                       reason=verdict.reason)
            return out
        notes = [r.note for r in readings if r.status in ("none", "conflict") and r.note]
        unsure.append(verdict.reason + (f" ({'; '.join(notes[:2])})" if notes and verdict.status == "none" else ""))
        out["pdf_url"] = f.pdf_url
    if unsure:
        out.update(pdf_verdict="pdf_unsure", reason="; ".join(dict.fromkeys(unsure))[:200])
    else:
        out["reason"] = "; ".join(dict.fromkeys(reasons))[:200] or "no results PDF read"
    return out


def pdf_key(url: str) -> str:
    import hashlib
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def fetch_with_retry(src, url: str, attempts: int = 3, pause: float = 4.0) -> tuple[bytes | None, str]:
    """The PDF through ``Sources.payload``, tried again after a pause when the download failed (not when NSE has no file): the
    first trial of 26 Oct 2026 collected 47 PDFs and left four pairs whose PDF was missing from every reader's file, so all
    eleven readers read "unavailable" for them."""
    import time
    data, why = src.payload(url)
    for attempt in range(1, attempts):
        if data or not why.startswith("download failed"):
            break
        time.sleep(pause * attempt)
        src._payload = None                  # the failed answer is kept for the same url: ask again
        data, why = src.payload(url)
    return data, why


def collect(csv_path: str, out_dir: str, limit: int | None = None) -> int:
    """Download the candidate results PDFs of the open pairs of a screener-referee CSV into ``out_dir`` (``<key>.pdf`` and
    ``manifest.json``: key -> url), once, for the per-reader jobs. Reads NSE only."""
    from .nse import FileCapReached, NseClient
    from .pdf_referee import MAX_CANDIDATES, Sources, load_csv, open_pairs
    os.environ["PDF_READERS"] = DEFAULT_READERS
    os.makedirs(out_dir, exist_ok=True)
    with open(csv_path, encoding="utf-8") as fh:
        pairs = open_pairs(load_csv(fh.read()))
    seen: dict[str, str] = {}
    failed: dict[str, str] = {}
    periods = list(dict.fromkeys((p["symbol"], p["period"]) for p in pairs))
    if limit:
        periods = periods[:limit]
    capped = False   # the run's file cap (F213): what is collected so far is kept, the rest waits for the next run
    with NseClient() as nse:
        src = Sources(nse, ocr=False)
        for symbol, period in periods:
            if capped:
                break
            listed = src.filings(symbol, period)
            if isinstance(listed, str):
                continue
            for f in listed[:MAX_CANDIDATES]:
                key = pdf_key(f.pdf_url)
                if key in seen:
                    continue
                try:
                    data, why = fetch_with_retry(src, f.pdf_url)
                except FileCapReached:
                    capped = True
                    print("file cap reached: the rest waits for the next run")
                    break
                if data:
                    with open(os.path.join(out_dir, f"{key}.pdf"), "wb") as fh:
                        fh.write(data)
                    seen[key] = f.pdf_url
                else:
                    failed[f.pdf_url] = why
                    print(f"not collected: {symbol} {period} {f.pdf_url} ({why})")
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(seen, fh)
    with open(os.path.join(out_dir, "failed.json"), "w", encoding="utf-8") as fh:
        json.dump(failed, fh)      # not in the manifest: the readers' files cannot cover these PDFs (the pairs read "unavailable")
    print(f"collected {len(seen)} PDFs for {len(periods)} company periods; {len(failed)} could not be downloaded")
    return 0


def _save_readings(out_path: str, name: str, started: float, result: dict) -> None:
    import time
    tmp = out_path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"reader": name, "seconds": round(time.monotonic() - started), "pdfs": result}, fh)
    os.replace(tmp, out_path)   # a reader killed half-way leaves the last complete file, never a torn one


def read_all(name: str, pdf_dir: str, out_path: str, budget_s: float | None = None) -> int:
    """Run ONE reader over every PDF of ``pdf_dir`` (this process loads only that reader) and write its tables.
    F216: the file is rewritten every 5 PDFs, and after ``budget_s`` seconds (env PDF_READ_BUDGET_S from the CLI) the
    PDFs not yet read are marked "not read: time budget" (settled as unavailable) so the job still uploads what it has."""
    import time
    reader = READERS[name]
    if reader.direct:
        print(f"{name}: reads the PDF itself in the ensemble, it has no tables file")
        return 0
    with open(os.path.join(pdf_dir, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    result: dict[str, dict] = {}
    started = time.monotonic()
    if not reader.available():
        print(f"{name}: unavailable (package not installed)")
        result = {k: {"url": u, "pages": [], "tables": [], "error": "unavailable"} for k, u in manifest.items()}
    else:
        for n, (key, url) in enumerate(manifest.items(), 1):
            entry = {"url": url, "pages": [], "tables": [], "error": ""}
            if budget_s and time.monotonic() - started >= budget_s:
                entry["error"] = "not read: time budget"
                result[key] = entry
                continue
            try:
                with open(os.path.join(pdf_dir, f"{key}.pdf"), "rb") as fh:
                    data = fh.read()
                entry["pages"] = statement_pages(page_layers(data))
                if entry["pages"]:
                    entry["tables"] = [t.as_json() for t in reader.read_tables(data, entry["pages"])]
            except Exception as exc:   # noqa: BLE001 - one PDF failing leaves the rest
                entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
            result[key] = entry
            if n % 5 == 0:
                _save_readings(out_path, name, started, result)
    seconds = round(time.monotonic() - started)
    _save_readings(out_path, name, started, result)
    done = sum(1 for e in result.values() if not e["error"])
    print(f"{name}: {done} of {len(result)} PDFs read in {seconds} s")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if len(argv) == 4 and argv[0] == "--worker":
        sys.exit(_worker_main(argv[1:]))
    if len(argv) in (3, 4) and argv[0] == "--collect":
        sys.exit(collect(argv[1], argv[2], int(argv[3]) if len(argv) == 4 else None))
    if len(argv) == 4 and argv[0] == "--read":
        sys.exit(read_all(argv[1], argv[2], argv[3], float(os.environ.get("PDF_READ_BUDGET_S") or 0) or None))
    print("usage: python -m bse_intel.pdf_readers --worker <reader> <pdf> <out.json> | --collect <csv> <dir> [limit] "
          "| --read <reader> <dir> <out.json>", file=sys.stderr)
    sys.exit(2)
