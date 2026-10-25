"""Stage 2: hybrid PDF text extraction.

Digital pages are read with PyMuPDF (milliseconds). Pages with almost no
extractable text *and* an embedded image are treated as scanned: rendered
to PNG and sent to a vision model (a short digital cover page is not), but only for pages that are actually needed and only up to a
per-document OCR budget, so one 80-page scanned annexure cannot drain the
free vision quota.

A page of figures - a statement, a note, a segment table - is read by local OCR first where it is
installed, and checked cell by cell against the text layer (FIGURE_PAGE_AMOUNTS, ocr.merge_with_text_layer).
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
import threading
from collections.abc import Callable, Iterable

import pymupdf

from .ocr import DPI as OCR_DPI
from .ocr import lines_from_boxes, merge_with_text_layer

log = logging.getLogger(__name__)

SCANNED_PAGE_CHARS = 80  # blueprint §5.3: under 80 characters of text and an image means scanned
# 2: the text layer is read in reading order (sort=True). An entry written before that is re-read once.
CACHE_VERSION = 2
OcrFn = Callable[[bytes], str]

# A text layer can be present and still unreadable: a font whose glyphs map to the wrong letters. On
# 929 cached filings, 32 pages in 4 filings were like that - Jubilant's statements read "ŝŶ ŵŝůůŝŽŶͿ zĞĂƌ
# ŶĚĞĚ ϯϬ" for "in million) Year Ended 30", digits included; a takeover disclosure read "FRPSDQ\VHFUHWDU\"
# for "company secretary", every letter moved three places. Each is long enough to pass for a text page,
# so none was OCR'd and the model was handed the garbage. Two signs, calibrated on all 10,873 text pages
# by eye: letters from scripts an English filing does not use (ligatures such as "ﬁ" are fine), and
# control characters. Two control characters are benign substitutes and are not counted: one stands for
# a space (Jubilant's readable pages, "Year<03>Ended", repaired by _clean) and one for a bullet in
# sustainability reports - counting it flagged a good page at exactly the threshold.
UNREADABLE_FOREIGN = 0.10
UNREADABLE_CONTROL = 0.02
_BENIGN_GLYPHS = frozenset((chr(3), chr(7)))


def text_unreadable(text: str | None) -> bool:
    """The page's text layer is in a broken or shifted font: OCR it rather than trust it."""
    visible = [c for c in (text or "") if not c.isspace() and c not in _BENIGN_GLYPHS]
    if len(visible) < 150:
        return False
    control = sum(1 for c in visible if ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0)
    letters = [c for c in visible if c.isalpha()]
    foreign = sum(1 for c in letters if ord(c) > 0x24F and not 0xFB00 <= ord(c) <= 0xFB06)
    return control >= UNREADABLE_CONTROL * len(visible) or foreign >= UNREADABLE_FOREIGN * max(1, len(letters))


# A page of a table is read by local OCR first and the text layer second (2026-10-17). On the extraction
# benchmark (docs/bench) OCR put 99% of a results statement's figures on their own row in the current
# column against 80% for the text layer, and 98% against 60% on seven complicated pages - a stamped
# statement, two sideways tables, a governance grid - where the text layer's rows come apart. A page is a
# table when it prints at least 15 amounts: on 10,957 cached pages that is 19% of them, the statements,
# notes, segment tables and rating annexures, and almost no letter or prose page.
FIGURE_PAGE_AMOUNTS = 15
_AMOUNT = re.compile(r"^\(?-?(?:\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+\.\d+)\)?%?$")
# 1: figure pages read by local OCR, and pages OCR'd before the OCR's line-building was fixed (ocr.py)
# read again. An entry without it is read from the PDF once more where local OCR is installed.
LOCAL_OCR_VERSION = 1
# OCR's reading is kept only when it holds most of the amounts the text layer prints: a page it could not
# read - a faint scan behind a clean text layer, a chart - keeps the text layer.
FIGURE_SHARE = 0.8
# An image covering this much of the page makes it a scan, whatever its text layer claims to be.
SCAN_COVER = 0.9


def amounts(text: str | None) -> int:
    return sum(1 for token in (text or "").split() if _AMOUNT.match(token))


def figure_page(text: str | None) -> bool:
    """The page is a table of figures: read it with OCR first."""
    return amounts(text) >= FIGURE_PAGE_AMOUNTS


def upright_text(page) -> str | None:
    """A page printed sideways, its text layer read in rows; None for an upright page.

    An annual report sets a wide table - Form AOC-1, the fixed-asset note - landscape on a portrait page.
    Its text runs up the page, and PyMuPDF's reading order then makes the table's columns into lines: the
    benchmark's AOC-1 kept none of its 16 rows. Its words, turned a quarter so the text runs left to right,
    are put into lines the way OCR's boxes are (ocr.lines_from_boxes), and every row comes back whole, nils
    included (2026-10-17)."""
    lines = [line for block in page.get_text("dict", flags=0)["blocks"] for line in block.get("lines", [])]
    vertical = [line for line in lines if abs(line["dir"][1]) > 0.9]
    if not lines or len(vertical) < 0.6 * len(lines):
        return None
    up = sum(line["dir"][1] for line in vertical) < 0       # the text runs up the page: turn it clockwise
    boxes = []
    for x0, y0, x1, y1, word, *_ in page.get_text("words"):
        nx0, nx1, ny0, ny1 = (-y1, -y0, x0, x1) if up else (y0, y1, -x1, -x0)
        boxes.append(([[nx0, ny0], [nx1, ny0], [nx1, ny1], [nx0, ny1]], word, 1.0))
    return lines_from_boxes(boxes)


def cache_needs_ocr(data: dict, local_ocr: bool = False, max_ocr_pages: int | None = None) -> bool:
    """A cached document with an unreadable page that was never OCR'd: read the PDF again. Once only: an
    entry written since unreadable pages go to OCR is marked, since reading the PDF again cannot OCR a page
    the run never reached, the OCR cap left out or no vision route could read.

    With local OCR installed, an entry written before figure pages went to it is read again too, once, if
    it has a figure page or a page OCR'd by the older line-building."""
    if local_ocr and data.get("local_ocr", 0) < LOCAL_OCR_VERSION:
        if data.get("ocr") or any(figure_page(t) for t in data.get("digital") or []):
            return True
    ocr = data.get("ocr") or {}
    if max_ocr_pages and data.get("ocr_cap", 6) < max_ocr_pages:
        # Written under a lower OCR cap (6 before RapidOCR): a scanned page the cap left out was never read,
        # and a cached document has no PDF to render it from, so it is read again once under today's cap.
        digital, images = data.get("digital") or [], data.get("has_image") or []
        if any(len(t.strip()) < SCANNED_PAGE_CHARS and i < len(images) and images[i] and str(i) not in ocr
               for i, t in enumerate(digital)):
            return True
    if data.get("unreadable_checked"):
        return False
    return any(text_unreadable(t) and str(i) not in ocr for i, t in enumerate(data.get("digital") or []))

def _block_reading(page) -> str:
    """The page's text layer block by block, top to bottom and left to right, each block whole.

    The reading the analysis uses (sort=True) puts every line that shares a height on one line, which keeps
    a statement's row together across its columns but runs a two-column page, or a table whose cells take
    several lines, across both columns at once. PyMuPDF's blocks keep a cell or a column together. Kept
    beside the main reading for the quote checks only (gate.quote_found): what the model reads is unchanged."""
    return "\n".join(b[4].strip() for b in page.get_text("blocks", sort=True) if b[6] == 0 and b[4].strip())


def _layer_text(page) -> str:
    """The page's text layer in reading order; a sideways page of figures turned upright first."""
    text = page.get_text("text", sort=True) or ""
    return (upright_text(page) or text) if figure_page(text) else text


# PyMuPDF does not support concurrent use from multiple threads, even on
# separate documents. All PyMuPDF calls go through this lock; OCR network
# calls happen outside it.
_MUPDF = threading.Lock()


AUDIO = (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".amr", ".wma", ".mp4")
ZIP_MAX_BYTES = 120_000_000   # a member larger than the attachment cap is not unpacked


def unzip_pdfs(data: bytes) -> tuple[bytes | None, str | None]:
    """A ZIP attachment's PDFs as one PDF, in the order of their names (owner, 25 Oct 2026: PGEL's auditor resignation
    came as a ZIP of a PDF and its XML and was lost). Returns (pdf, None), or (None, why) when there is no PDF to read:
    a call's audio, or no PDF at all."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as box:
            members = [m for m in box.infolist() if not m.is_dir()]
            pdfs = sorted((m for m in members if m.filename.lower().endswith(".pdf") and m.file_size <= ZIP_MAX_BYTES),
                          key=lambda m: m.filename)
            if not pdfs:
                names = [m.filename for m in members]
                if names and all(n.lower().endswith(AUDIO) for n in names):
                    return None, "audio only (a ZIP of a recording): no text"
                return None, f"a ZIP with no PDF in it ({', '.join(names[:5]) or 'empty'})"
            parts = [box.read(m) for m in pdfs]
    except (zipfile.BadZipFile, OSError) as exc:
        return None, f"unreadable ZIP: {exc}"
    if len(parts) == 1:
        return parts[0], None
    with _MUPDF:
        out = pymupdf.open()
        for part in parts:
            try:
                with pymupdf.open(stream=part, filetype="pdf") as one:
                    out.insert_pdf(one)
            except Exception as exc:  # one broken PDF in the box must not lose the others
                log.warning("a PDF inside a ZIP attachment is unreadable: %s", exc)
        merged = out.tobytes() if out.page_count else None
        out.close()
    return merged, None if merged else "a ZIP whose PDFs are all unreadable"


def cut_short(data: bytes) -> bool:
    """A PDF whose end-of-file marker is missing: the download, or the file NSE holds, stops part-way."""
    return data[:5] == b"%PDF-" and b"%%EOF" not in data[-2048:]


class Document:
    def __init__(self, pdf_bytes: bytes | None, ocr: OcrFn | None = None, max_ocr_pages: int = 6, dpi: int = OCR_DPI,
                 figure_reader: OcrFn | None = None, max_figure_pages: int = 12):
        self._ocr = ocr
        self._max_ocr = max_ocr_pages
        self.ocr_cap = max_ocr_pages  # the cap this reading was made under; an old entry kept as a fallback keeps its own
        self._dpi = dpi
        # Local OCR only, never the vision route: a figure page has a text layer to fall back on, and a
        # model reading a statement's small print swaps digits without saying so (docs/bench).
        self._figures = figure_reader
        self._max_figures = max_figure_pages
        self._ocr_cache: dict[int, str] = {}
        self.ocr_pages_used = 0
        self.figure_pages_used = 0
        self.ocr_error: Exception | None = None  # last OCR failure, if any
        self.cache_version = CACHE_VERSION  # an old entry kept as a fallback keeps its own, so it is re-read later
        self.unreadable_checked = True  # read by this code, which sends an unreadable page to OCR
        self.local_ocr = LOCAL_OCR_VERSION if figure_reader else 0
        self.error: str | None = None
        self._doc = None
        self._digital: list[str] = []
        self._has_image: list[bool] = []
        self._blocks: list[str] = []
        self._blocks_read = True  # an old cache entry kept as a fallback has none, and must stay marked so
        self.selected: list[int] = []   # the pages the last select_text took
        if not pdf_bytes:
            self.error = "no attachment"
            return
        if pdf_bytes[:2] == b"PK":
            pdf_bytes, why = unzip_pdfs(pdf_bytes)
            if pdf_bytes is None:
                self.error = why
                return
        try:
            with _MUPDF:
                doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
                if doc.needs_pass and not doc.authenticate(""):
                    raise ValueError("password-protected PDF")
                self._doc = doc
                # sort=True: in reading order, so a figure stays on the line with its own row label and
                # the unit header comes before the numbers it governs. Measured on Kanoria's FY25
                # consolidated P&L, 0% of the lines carrying a figure also carried its label without this
                # and 100% with it; the year columns arrived after all the rows rather than above them.
                # That ordering is where the wrong-column and unit-scale errors come from (audit round 1).
                self._digital = [_layer_text(page) for page in doc]
                self._has_image = [bool(page.get_images(full=False)) for page in doc]
                self._blocks = [_block_reading(page) for page in doc]
        except Exception as exc:  # corrupt PDF, or a non-PDF attachment (xml, zip, xlsx)
            self.error = f"unreadable attachment: {exc}"
            log.warning(self.error)
        if not self._digital and cut_short(pdf_bytes):
            # NSE serves some files cut short (Apollo Hospitals' 20 May 2026 outcome: 3.47 of 12.45 MB, no end of file;
            # owner, 25 Oct 2026): told apart from a scan or a broken file, so the filing can wait for NSE to fix it
            self.error = f"cut short: {len(pdf_bytes) / 1e6:.2f} MB with no end of file"

    def to_cache(self) -> dict:
        """Everything read from the PDF (digital text and the pages OCR'd so far), for the text cache."""
        return {"v": self.cache_version, "error": self.error, "digital": self._digital, "has_image": self._has_image,
                "ocr": {str(k): v for k, v in self._ocr_cache.items()}, "unreadable_checked": self.unreadable_checked,
                "local_ocr": self.local_ocr, "ocr_cap": self.ocr_cap, **({"blocks": self._blocks} if self._blocks_read else {})}

    def keep_ocr(self, data: dict) -> None:
        """Reuse the pages an older cache entry already OCR'd: re-reading the text layer does not change them.
        Not when this document reads with a newer local OCR than the entry was written with: reading the
        page again costs no quota, and the older OCR merged close rows and interleaved their figures."""
        if self.local_ocr > data.get("local_ocr", 0):
            return
        if len((data.get("digital") or [])) == len(self._digital):
            self._ocr_cache.update({int(k): v for k, v in (data.get("ocr") or {}).items()})

    @classmethod
    def from_cache(cls, data: dict, ocr: OcrFn | None = None, max_ocr_pages: int = 6) -> "Document":
        doc = cls(None, ocr=ocr, max_ocr_pages=max_ocr_pages)
        doc.error = data.get("error")
        doc.cache_version = data.get("v", 1)
        doc.unreadable_checked = bool(data.get("unreadable_checked"))
        doc.local_ocr = data.get("local_ocr", 0)
        doc._digital = list(data.get("digital", []))
        doc._has_image = list(data.get("has_image", [False] * len(doc._digital)))
        doc._blocks = list(data.get("blocks") or [])
        doc._blocks_read = "blocks" in data
        doc.ocr_cap = data.get("ocr_cap", 6)
        doc._ocr_cache = {int(k): v for k, v in (data.get("ocr") or {}).items()}
        return doc

    @property
    def page_count(self) -> int:
        return len(self._digital)

    def block_text(self, pages: Iterable[int]) -> str:
        """The text layer of these pages read block by block (_block_reading), for the quote checks."""
        return "\n".join(self._blocks[i] for i in pages if i < len(self._blocks) and self._blocks[i])

    def is_scanned(self, index: int) -> bool:
        return len(self._digital[index].strip()) < SCANNED_PAGE_CHARS and self._has_image[index]

    @property
    def scanned_ratio(self) -> float:
        if not self._digital:
            return 0.0
        return sum(self.is_scanned(i) for i in range(self.page_count)) / self.page_count

    def is_unreadable(self, index: int) -> bool:
        return text_unreadable(self._digital[index])

    def page_text(self, index: int, figures: bool = True) -> str:
        """The page as the analysis reads it. figures=False keeps a page of figures to its text layer:
        the duplicate check compares filings by their text and needs it the same however they were read."""
        if index >= self.page_count:
            return ""
        readable = not self.is_scanned(index) and not self.is_unreadable(index)
        if readable and not (figures and figure_page(self._digital[index])):
            return self._digital[index]
        if index in self._ocr_cache:
            return self._ocr_cache[index]
        if readable:
            return self._figure_text(index)
        text = self._digital[index]
        if self._ocr and self._doc is not None and self.ocr_pages_used < self._max_ocr:
            with _MUPDF:
                png = self._doc[index].get_pixmap(dpi=self._dpi).tobytes("png")
            self.ocr_pages_used += 1
            try:
                text = self._ocr(png) or text
            except Exception as exc:
                self.ocr_error = exc
                log.warning("OCR failed on page %d: %s", index + 1, exc)
            # Kept as read only when it was read. A page past the OCR cap, or with nothing to OCR it, was stored
            # as its empty text layer and counted as OCR'd, so no later run read it (audit, 2026-10-18).
            self._ocr_cache[index] = text
        return text

    def _figure_text(self, index: int) -> str:
        """A table page as local OCR reads it, with the nil cells OCR drops put back from the text layer
        (ocr.merge_with_text_layer); the text layer when OCR is not installed, failed, or read too little."""
        layer = self._digital[index]
        if self._figures is None or self._doc is None or self.figure_pages_used >= self._max_figures:
            return layer
        with _MUPDF:
            page = self._doc[index]
            png = page.get_pixmap(dpi=self._dpi).tobytes("png")
            # A scan's text layer is an OCR of its own, laid invisibly over the image (render mode 3) or
            # drawn beneath it (Heritage Foods' statements, where it reads "Total e.-.:pcnscs"): it misreads
            # like any OCR, so it fills OCR's gaps but does not overrule its figures.
            trace = page.get_texttrace()
            area = abs(page.rect) or 1.0
            cover = max((abs(pymupdf.Rect(info["bbox"]) & page.rect) / area for info in page.get_image_info()), default=0.0)
            exact = cover < SCAN_COVER and sum(span.get("type") == 3 for span in trace) < 0.5 * max(1, len(trace))
        self.figure_pages_used += 1
        try:
            read = self._figures(png) or ""
        except Exception as exc:  # the text layer is still there: no failure to report, nothing to retry
            log.warning("local OCR failed on figure page %d: %s", index + 1, exc)
            return layer
        if amounts(read) < FIGURE_SHARE * amounts(layer):
            log.info("OCR read %d of the %d amounts on page %d; keeping the text layer",
                     amounts(read), amounts(layer), index + 1)
            text = layer
        else:
            text = merge_with_text_layer(read, layer, layer_exact=exact)
        self._ocr_cache[index] = text
        return text

    def close(self) -> None:
        if self._doc is not None:
            with _MUPDF:
                self._doc.close()
            self._doc = None

    def layer_text(self) -> str:
        """Every page's own text layer and no OCR: enough to look a figure up anywhere in a 300-page report."""
        return "\n".join(self._digital)

    def first_page_text(self, limit: int = 2500) -> str:
        return strip_boilerplate(_clean(self.page_text(0)))[:limit] if self.page_count else ""

    def kind(self) -> str:
        """TRANSCRIPT, PRESENTATION, ANNUAL_REPORT or OTHER, from the digital text (blueprint §5.3)."""
        head = " ".join(self._digital[:3]).lower()
        whole = " ".join(self._digital).lower()
        if whole.count("moderator") >= 3 or ("conference call" in head and "participant" in whole):
            return "TRANSCRIPT"
        if "annual report" in head or (self.page_count >= 60 and "directors' report" in whole):
            return "ANNUAL_REPORT"
        if "investor presentation" in head or "earnings presentation" in head or "corporate presentation" in head:
            return "PRESENTATION"
        return "OTHER"

    def select_text(self, budget_chars: int, keywords: Iterable[str] = (), figures: bool = True,
                    headers: bool = False) -> str:
        """Pick the most relevant pages within a character budget, kept in page order.

        The first two pages are always included (cover letter + headline numbers). The rest are
        ranked by keyword hits plus the sections that matter for the kind of document (smart
        section chunking): the opening remarks and Q&A of a transcript; financial highlights,
        segments, capex, order book and guidance slides of a presentation; the auditor's report,
        statements, segment, related-party and contingent-liability notes of an annual report.
        Disclaimers, CSR, macro and agenda pages go last. Scanned pages cannot be ranked before OCR,
        so they are taken in order once ranked pages run out.

        With ``headers`` each page's marker also names the page's heading and its own unit (``page_header``), for the
        model: one note on the whole filing's unit cannot say which page is in lakh and which in rupees.
        """
        if not self.page_count:
            return ""
        patterns = [re.compile(re.escape(k), re.I) for k in keywords]
        keep, skip = _SECTIONS.get(self.kind(), (None, None))
        chosen = [i for i in range(min(2, self.page_count))]
        scored = []
        for i in range(len(chosen), self.page_count):
            if self.is_scanned(i):
                scored.append((-1, i))
                continue
            page = self._digital[i]
            hits = sum(len(p.findall(page)) for p in patterns)
            if keep is not None:
                hits += 20 * len(keep.findall(page[:1500]))  # section titles sit at the top of a page or slide
                if skip.search(page[:600]) and not keep.search(page[:600]):
                    hits = -0.5  # after every ranked page, before scanned ones
            scored.append((hits, i))
        scored.sort(key=lambda item: (-item[0], item[1]))
        mark = HEADER_CHARS if headers else 0   # room for each page's heading and unit in its marker
        used = sum(len(strip_boilerplate(_clean(self._digital[i]))) + mark for i in chosen)
        for _, i in scored:
            size = (len(strip_boilerplate(_clean(self._digital[i]))) if not self.is_scanned(i) else 3000) + mark
            if used + size > budget_chars:
                continue
            chosen.append(i)
            used += size
        self.selected = sorted(chosen)
        pages = [(i, strip_boilerplate(_clean(self.page_text(i, figures)))) for i in sorted(chosen)]
        pages = [(i, text) for i, text in pages if text]
        repeated = _running_lines([text for _, text in pages]) if headers else set()
        parts = []
        for i, text in pages:
            extra = page_header(text, repeated) if headers else ""
            parts.append(f"--- Page {i + 1} of {self.page_count}{extra} ---\n{text}")
        return "\n\n".join(parts)[:budget_chars]


HEADING_LINES = 8      # a page's heading is among its first lines
HEADING_CHARS = 80
HEADER_CHARS = 130     # what a page marker's heading and unit can add
_PAGE_MARK = re.compile(r"^\W*(?:page\s*)?\d+(?:\s*(?:of|/)\s*\d+)?\W*$", re.I)
_SEGMENT_HEADING = re.compile(r"\bsegment|\bdivision\b|\bbusiness\s+units?\b|\bverticals?\b", re.I)
# a rupee amount written in full with Indian grouping, a crore or more: "INR 99,09,87,896" (LIC's GST demand)
_FULL_RUPEES = re.compile(r"(?<![\d,.])\d{1,2}(?:,\d\d){2,},\d{3}(?![\d,])")
_PAGE_UNIT_NAMES = {1: "₹ crore", 100: "₹ lakh", 10: "₹ million", 10_000: "₹ thousand", 0.01: "₹ billion"}


def _heading_candidates(text: str) -> list[str]:
    lines = [ln.strip(" \t:-–|") for ln in text.splitlines()]
    return [ln for ln in lines if ln][:HEADING_LINES]


def _running_lines(pages: list[str]) -> set[str]:
    """Lines at the top of most pages (the letterhead, the company's name on every slide): no page's heading."""
    if len(pages) < 3:
        return set()
    counts: dict[str, int] = {}
    for text in pages:
        for line in set(_heading_candidates(text)):
            counts[line.lower()] = counts.get(line.lower(), 0) + 1
    return {line for line, n in counts.items() if n * 2 >= len(pages)}


def page_header(text: str, repeated: set[str] = frozenset()) -> str:
    """What a page's marker says about it: ' · "Segment information" · scope: segment · amounts in ₹ lakh'.

    The heading is the first short line of words near the top that is not a running line or a page number. The unit
    is the one the page itself declares ("(₹ in lakh)"); a page that declares several says so, and a page that
    declares none but writes rupees in full ("99,09,87,896") is marked as whole rupees. LIC's GST demand of INR
    99,09,87,896 became ₹9.91 Cr where it is ₹99.10 Cr, and Cyient's segment target was read as the company's: the
    page's own heading and unit sat far above the figure (live reviews, 2026-10-20)."""
    from .grounding import _DECLARED_UNIT, _PER_CRORE   # the statements' unit headers, read as the checks read them
    parts = []
    for line in _heading_candidates(text):
        letters = sum(ch.isalpha() for ch in line)
        digits = sum(ch.isdigit() for ch in line)
        if (letters >= 4 and len(line) <= HEADING_CHARS and digits <= 0.3 * len(line) and line.lower() not in repeated
                and not _PAGE_MARK.match(line) and not _DECLARED_UNIT.fullmatch(line.strip("()[] "))):
            parts.append(f'"{line}"')
            if _SEGMENT_HEADING.search(line):
                parts.append("scope: segment")
            break
    units = {_PER_CRORE.get(next(g for g in m.groups() if g).lower().rstrip("s")) for m in _DECLARED_UNIT.finditer(text)}
    units.discard(None)
    if len(units) == 1:
        parts.append(f"amounts in {_PAGE_UNIT_NAMES.get(units.pop(), 'the unit its header names')}")
    elif units:
        parts.append("units vary on this page: read each table's own header")
    elif _FULL_RUPEES.search(text):
        parts.append("amounts in whole rupees (Indian digit grouping), not lakh or crore")
    return "".join(f" · {p}" for p in parts)


def _rx(*words: str) -> re.Pattern:
    return re.compile("|".join(words), re.I)


# Per document kind: (sections to favour, pages to put last). Blueprint §5.3.
_SECTIONS = {
    "TRANSCRIPT": (
        _rx(r"opening remarks", r"\bq\s*&\s*a\b", r"question[- ]and[- ]answer", r"\bguidance\b", r"\bcapex\b",
            r"order book", r"\bmargins?\b", r"\butili[sz]ation\b", r"commission", r"\bfy\s?2?\d\b"),
        _rx(r"safe harbou?r", r"disclaimer", r"forward[- ]looking statements", r"list of participants",
            r"^\s*participants\b"),
    ),
    "PRESENTATION": (
        _rx(r"financial highlights", r"key highlights", r"performance (?:highlights|overview|update)", r"segment",
            r"\bcapex\b", r"capacity", r"project", r"roadmap", r"order book", r"guidance", r"outlook",
            r"\brevenue\b", r"\bebitda\b", r"profit and loss", r"balance sheet", r"\bdebt\b"),
        _rx(r"safe harbou?r", r"disclaimer", r"forward[- ]looking statements", r"\bcsr\b", r"\besg\b",
            r"sustainab", r"awards?\b", r"board of directors", r"industry overview", r"global econom", r"macro",
            r"^\s*thank you\s*$", r"^\s*agenda\b"),
    ),
    "ANNUAL_REPORT": (
        _rx(r"independent auditor", r"emphasis of matter", r"qualified opinion", r"basis for (?:qualified )?opinion",
            r"\bcaro\b", r"annexure .{0,10} to the (?:independent )?auditor", r"statement of profit and loss",
            r"balance sheet", r"cash flow", r"segment (?:information|reporting)", r"related party",
            r"contingent liabilit", r"key audit matters"),
        _rx(r"notice (?:of|is hereby given)", r"e-?voting", r"corporate social responsibility",
            r"business responsibility", r"\bbrsr\b", r"profile of directors", r"route map", r"proxy form",
            r"chairman'?s message"),
    ),
}


# Spaces, plus control characters some PDFs use as spaces (Jubilant Pharmova's statements read
# "Revenue\x03from\x03operations"); left in, they hide words from the model and every pattern.
_WS = re.compile(r"[ \t\u00a0\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+")
_BLANKS = re.compile(r"\n{3,}")


# Short lines that never carry decision-relevant information: exchange addresses, salutations,
# sign-offs, signature blocks and contact footers. Removed before the text reaches the AI, so the
# budget goes to the substance and nothing in them can be mistaken for a fact about the company.
_BOILERPLATE = re.compile(
    r"^(?:to,?|the (?:general )?manager\b.*|the secretary\b.*|(?:the )?listing (?:department|compliance)\b.*"
    r"|(?:the )?department of corporate (?:services|relations)\b.*|corporate relationship department\b.*)$"
    r"|^(?:bse|bse limited|bse ltd\.?|national stock exchange of india(?: limited| ltd\.?)?)[,.]?$"
    r"|phiroze jeejeebhoy|dalal street|exchange plaza"
    r"|bandra[- ]kurla complex|bandra \(e(?:ast)?\)|\bfort,? mumbai|mumbai\s*[-–]?\s*400\s?0\d\d"
    r"|^(?:dear sirs?(?:\s*/\s*madam)?|dear sir/ma'?am|respected sirs?(?:/madam)?|sir/madam)[,.]?$"
    r"|yours (?:faithfully|sincerely|truly)|^thanking you|^thank you,?$|for and on behalf of"
    r"|take (?:the|this|the same|the above)(?: information)? on (?:your )?record"
    r"|this is for your (?:kind )?information|for your (?:kind )?information and (?:records|dissemination)"
    r"|digitally signed by|^date: ?\d{4}\.\d{2}\.\d{2}|\+05'?30'?$|^(?:company secretary|compliance officer)\b"
    r"|^(?:membership no|m\.? ?no)\.?\b|^\(?din:? ?\d{8}\)?$|^encl(?:osure)?s?\b|e-?mail\.? ?(?:id)?\.?:|website\.?:"
    r"|\btel(?:ephone)?\.? ?(?:no\.?)?:|\bfax\.?:|^phone(?: no\.?)?\s*:|\bcin:? ?[lu]\d{5}|\bgstin\b"
    r"|^regd\.? office\b|^registered office\s*:"
    r"|information is (?:being )?(?:uploaded|available|hosted) on the (?:company's )?website"
    # earnings-call chatter (operator instructions, moderator hand-offs, pleasantries)
    r"|^moderator:.{0,120}(?:next question|please go ahead|line of|queue|ask a question)"
    r"|press (?:\*|star) (?:and|then) (?:1|one)|all participant lines (?:are|will be) in (?:the )?listen[- ]only"
    r"|^(?:thank you|thanks)(?: (?:very much|so much))?(?:,? (?:sir|madam|ma'?am))?[.!]?$",
    re.I | re.M,
)


_SIGN_OFF = re.compile(r"^for,?\s+(.{3,70}?)\s*(?:limited|ltd\.?)\s*$", re.I)


def _is_sign_off(line: str) -> bool:
    """"For, Om Power Transmission Limited" above a signature; every word capitalised, no figures."""
    m = _SIGN_OFF.match(line)
    return bool(m) and all(w[:1].isupper() or w in ("&", "and", "of") for w in re.split(r"[\s,]+", m[1]) if w) \
        and not re.search(r"\d", line)


def strip_boilerplate(text: str) -> str:
    kept = [line for line in text.splitlines()
            if not (len(line) <= 160 and (_BOILERPLATE.search(line.strip()) or _is_sign_off(line.strip())))]
    return _BLANKS.sub("\n\n", "\n".join(kept)).strip()


def _clean(text: str) -> str:
    return _BLANKS.sub("\n\n", _WS.sub(" ", text)).strip()
