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
DPI = 200
WORKER_TIMEOUT = 900        # seconds for one reader on one PDF
LAYER_MIN_CHARS = 40        # fewer characters on a page: no text layer
HEADER_LINES = 25           # lines at the top of a page kept as the table's title and unit context

_UNIT_WORD = re.compile(r"\b(crores?|lakhs?|lacs?|millions?|thousands?|mn|cr)\b", re.I)
_CONS_WORD = re.compile(r"\bconsolidated\b", re.I)
_ALONE_WORD = re.compile(r"\bstand[- ]?alone\b", re.I)
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
    words: list = field(default_factory=list)      # (x0, y0, x1, y1, text) of the page's words, when read from the PDF
    _bands: list | None = None

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
        if not nums and (named := _words_basis(label)):
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
    return re.sub(r"\s+", " ", str(text if text is not None else "")).strip()


def table_text(cells: list[list[str]]) -> str:
    """A grid written as lines: the non-empty cells of a row joined by two spaces (what the text layer would give)."""
    lines = []
    for row in cells:
        parts = [clean_cell(c) for c in row]
        line = "  ".join(p for p in parts if p)
        if line:
            lines.append(line)
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
    if len(bases) == 1:                       # one basis on the page: its title can stand above any table of it
        context += [ln for ln in top if _CONS_WORD.search(ln) or _ALONE_WORD.search(ln)]
    if len(kinds) == 1:                       # one unit on the page; two units would be a guess, so none is given
        context += units[:2]
    return PageLayer(text, has, numbers, "\n".join(dict.fromkeys(context)))


def _safe_float(token: str) -> bool:
    try:
        float(token.replace(",", ""))
        return True
    except ValueError:
        return False


def consolidated_anywhere(layers: dict[int, PageLayer], tables: list[Table] | None = None) -> bool:
    """Shared by every reader of a PDF: a table with no title of its own is read as standalone only when every page's text
    layer is there to say "consolidated" and does not. A page with no layer, or a layer that names consolidated anywhere,
    leaves such a table's basis unproven."""
    if any(not layer.has_layer for layer in layers.values()) or not layers:
        return True
    if any(_CONS_WORD.search(layer.text) for layer in layers.values()):
        return True
    return any(_CONS_WORD.search(table_text(t.cells)) for t in tables or [])


def tables_to_rows(tables: list[Table], layers: dict[int, PageLayer], anywhere: bool | None = None) -> list:
    """The referee's ``Row`` objects of every table, each parsed with ``pdf_referee.parse_page`` under its page's title and unit."""
    from .pdf_referee import parse_page
    texts = []
    for t in tables:
        layer = layers.get(t.page)
        body = table_text(t.cells)
        if body:
            texts.append((t.page, (layer.context + "\n" if layer and layer.context else "") + body))
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


def _other(basis: str | None) -> str | None:
    from .pdf_referee import CONSOLIDATED, STANDALONE
    return {CONSOLIDATED: STANDALONE, STANDALONE: CONSOLIDATED}.get(basis or "")


def reading_of(reader: "Reader", rows: list, layers: dict[int, PageLayer], period: str, metric: str, basis: str | None,
               anywhere: bool = True) -> Reading:
    """One reader's figure for the pair, with the proof the rule needs: the basis proven from a title (rows with no proven
    basis are never taken), the printed cell found in the text layer on its row and column, the source and the printed precision."""
    from .pdf_referee import figure_for
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


def statement_pages(layers: dict[int, PageLayer], max_pages: int = MAX_PAGES) -> list[int]:
    """Pages that hold a results table: a "Statement of ... Results" heading or a header with two dates and the period
    words (a page of the text layer), best first; pages with no text layer fill what is left in a short PDF."""
    from .pdf_referee import _dates_in
    scored: list[tuple[int, int]] = []
    for page, layer in layers.items():
        if not layer.has_layer:
            continue
        dated = any(len(_dates_in(line)) >= 2 for line in layer.text.splitlines())
        if not dated:
            continue
        score = (2 if _RESULTS_HEAD.search(layer.text) else 0) + (1 if _PERIOD_WORDS.search(layer.text) else 0)
        if score:
            scored.append((-score, page))
    pages = [p for _, p in sorted(scored)][:max_pages]
    if len(pages) < max_pages and len(layers) <= SCAN_PAGE_LIMIT:
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
            self._row.append(clean_cell("".join(self._cell)))
            for k in range(1, self._span):
                self._row.append("")
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
                    cells.append(cell.text if start == (r, c) else "")      # a spanned cell's text once, at its origin
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
        pipeline = PPStructureV3(use_table_recognition=True, use_formula_recognition=False, use_chart_recognition=False,
                                 use_seal_recognition=False, use_doc_orientation_classify=False, use_doc_unwarping=False)
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


class RapidTableReader(Reader):
    """rapid-table (SLANet-plus, ONNX), the PP-StructureV3 table models without the Paddle framework. The page is rendered at
    200 dpi; the cell text comes from the page's text-layer words (boxes scaled to the image) when it has a layer, else from
    RapidOCR. The whole page image is passed (no layout step), so it suits a page that is mostly the statement."""
    name = family = "rapidtable"
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
        structure = TableTransformerForObjectDetection.from_pretrained(self.STRUCTURE).eval()
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
    def _detect(torch, processor, model, image) -> list[tuple]:
        inputs = processor(images=image, return_tensors="pt")
        with torch.no_grad():
            outputs = model(**inputs)
        res = processor.post_process_object_detection(outputs, threshold=0.7, target_sizes=[image.size[::-1]])[0]
        labels = model.config.id2label
        return [tuple(float(v) for v in box) for box, lab in zip(res["boxes"], res["labels"]) if labels[int(lab)] == "table"]

    @staticmethod
    def _structure(torch, processor, model, crop) -> tuple[list[tuple], list[tuple]]:
        inputs = processor(images=crop, return_tensors="pt")
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
    RapidTableReader(), MarkerReader(), SuryaReader(), TatrReader())}

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
            if status in ("unavailable", "error"):
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


def collect(csv_path: str, out_dir: str, limit: int | None = None) -> int:
    """Download the candidate results PDFs of the open pairs of a screener-referee CSV into ``out_dir`` (``<key>.pdf`` and
    ``manifest.json``: key -> url), once, for the per-reader jobs. Reads NSE only."""
    from .nse import NseClient
    from .pdf_referee import MAX_CANDIDATES, Sources, load_csv, open_pairs
    os.environ["PDF_READERS"] = DEFAULT_READERS
    os.makedirs(out_dir, exist_ok=True)
    with open(csv_path, encoding="utf-8") as fh:
        pairs = open_pairs(load_csv(fh.read()))
    seen: dict[str, str] = {}
    periods = list(dict.fromkeys((p["symbol"], p["period"]) for p in pairs))
    if limit:
        periods = periods[:limit]
    with NseClient() as nse:
        src = Sources(nse, ocr=False)
        for symbol, period in periods:
            listed = src.filings(symbol, period)
            if isinstance(listed, str):
                continue
            for f in listed[:MAX_CANDIDATES]:
                key = pdf_key(f.pdf_url)
                if key in seen:
                    continue
                data, _why = src.payload(f.pdf_url)
                if data:
                    with open(os.path.join(out_dir, f"{key}.pdf"), "wb") as fh:
                        fh.write(data)
                    seen[key] = f.pdf_url
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(seen, fh)
    print(f"collected {len(seen)} PDFs for {len(periods)} company periods")
    return 0


def read_all(name: str, pdf_dir: str, out_path: str) -> int:
    """Run ONE reader over every PDF of ``pdf_dir`` (this process loads only that reader) and write its tables."""
    import time
    reader = READERS[name]
    with open(os.path.join(pdf_dir, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    result: dict[str, dict] = {}
    started = time.monotonic()
    if not reader.available():
        print(f"{name}: unavailable (package not installed)")
        result = {k: {"url": u, "pages": [], "tables": [], "error": "unavailable"} for k, u in manifest.items()}
    else:
        for key, url in manifest.items():
            entry = {"url": url, "pages": [], "tables": [], "error": ""}
            try:
                with open(os.path.join(pdf_dir, f"{key}.pdf"), "rb") as fh:
                    data = fh.read()
                entry["pages"] = statement_pages(page_layers(data))
                if entry["pages"]:
                    entry["tables"] = [t.as_json() for t in reader.read_tables(data, entry["pages"])]
            except Exception as exc:   # noqa: BLE001 - one PDF failing leaves the rest
                entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
            result[key] = entry
    seconds = round(time.monotonic() - started)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"reader": name, "seconds": seconds, "pdfs": result}, fh)
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
        sys.exit(read_all(argv[1], argv[2], argv[3]))
    print("usage: python -m bse_intel.pdf_readers --worker <reader> <pdf> <out.json> | --collect <csv> <dir> [limit] "
          "| --read <reader> <dir> <out.json>", file=sys.stderr)
    sys.exit(2)
