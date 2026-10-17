"""Stage 2: hybrid PDF text extraction.

Digital pages are read with PyMuPDF (milliseconds). Pages with almost no
extractable text *and* an embedded image are treated as scanned: rendered
to PNG and sent to a vision model (a short digital cover page is not), but only for pages that are actually needed and only up to a
per-document OCR budget, so one 80-page scanned annexure cannot drain the
free vision quota.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable, Iterable

import pymupdf

from .ocr import DPI as OCR_DPI

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


def cache_needs_ocr(data: dict) -> bool:
    """A cached document with an unreadable page that was never OCR'd: read the PDF again. Once only: an
    entry written since unreadable pages go to OCR is marked, since reading the PDF again cannot OCR a page
    the run never reached, the OCR cap left out or no vision route could read."""
    if data.get("unreadable_checked"):
        return False
    ocr = data.get("ocr") or {}
    return any(text_unreadable(t) and str(i) not in ocr for i, t in enumerate(data.get("digital") or []))

# PyMuPDF does not support concurrent use from multiple threads, even on
# separate documents. All PyMuPDF calls go through this lock; OCR network
# calls happen outside it.
_MUPDF = threading.Lock()


class Document:
    def __init__(self, pdf_bytes: bytes | None, ocr: OcrFn | None = None, max_ocr_pages: int = 6, dpi: int = OCR_DPI):
        self._ocr = ocr
        self._max_ocr = max_ocr_pages
        self._dpi = dpi
        self._ocr_cache: dict[int, str] = {}
        self.ocr_pages_used = 0
        self.ocr_error: Exception | None = None  # last OCR failure, if any
        self.cache_version = CACHE_VERSION  # an old entry kept as a fallback keeps its own, so it is re-read later
        self.unreadable_checked = True  # read by this code, which sends an unreadable page to OCR
        self.error: str | None = None
        self._doc = None
        self._digital: list[str] = []
        self._has_image: list[bool] = []
        if not pdf_bytes:
            self.error = "no attachment"
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
                self._digital = [page.get_text("text", sort=True) or "" for page in doc]
                self._has_image = [bool(page.get_images(full=False)) for page in doc]
        except Exception as exc:  # corrupt PDF, or a non-PDF attachment (xml, zip, xlsx)
            self.error = f"unreadable attachment: {exc}"
            log.warning(self.error)

    def to_cache(self) -> dict:
        """Everything read from the PDF (digital text and the pages OCR'd so far), for the text cache."""
        return {"v": self.cache_version, "error": self.error, "digital": self._digital, "has_image": self._has_image,
                "ocr": {str(k): v for k, v in self._ocr_cache.items()}, "unreadable_checked": self.unreadable_checked}

    def keep_ocr(self, data: dict) -> None:
        """Reuse the pages an older cache entry already OCR'd: re-reading the text layer does not change them."""
        if len((data.get("digital") or [])) == len(self._digital):
            self._ocr_cache.update({int(k): v for k, v in (data.get("ocr") or {}).items()})

    @classmethod
    def from_cache(cls, data: dict, ocr: OcrFn | None = None, max_ocr_pages: int = 6) -> "Document":
        doc = cls(None, ocr=ocr, max_ocr_pages=max_ocr_pages)
        doc.error = data.get("error")
        doc.cache_version = data.get("v", 1)
        doc.unreadable_checked = bool(data.get("unreadable_checked"))
        doc._digital = list(data.get("digital", []))
        doc._has_image = list(data.get("has_image", [False] * len(doc._digital)))
        doc._ocr_cache = {int(k): v for k, v in (data.get("ocr") or {}).items()}
        return doc

    @property
    def page_count(self) -> int:
        return len(self._digital)

    def is_scanned(self, index: int) -> bool:
        return len(self._digital[index].strip()) < SCANNED_PAGE_CHARS and self._has_image[index]

    @property
    def scanned_ratio(self) -> float:
        if not self._digital:
            return 0.0
        return sum(self.is_scanned(i) for i in range(self.page_count)) / self.page_count

    def is_unreadable(self, index: int) -> bool:
        return text_unreadable(self._digital[index])

    def page_text(self, index: int) -> str:
        if index >= self.page_count:
            return ""
        if not self.is_scanned(index) and not self.is_unreadable(index):
            return self._digital[index]
        if index in self._ocr_cache:
            return self._ocr_cache[index]
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
        self._ocr_cache[index] = text
        return text

    def close(self) -> None:
        if self._doc is not None:
            with _MUPDF:
                self._doc.close()
            self._doc = None

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

    def select_text(self, budget_chars: int, keywords: Iterable[str] = ()) -> str:
        """Pick the most relevant pages within a character budget, kept in page order.

        The first two pages are always included (cover letter + headline numbers). The rest are
        ranked by keyword hits plus the sections that matter for the kind of document (smart
        section chunking): the opening remarks and Q&A of a transcript; financial highlights,
        segments, capex, order book and guidance slides of a presentation; the auditor's report,
        statements, segment, related-party and contingent-liability notes of an annual report.
        Disclaimers, CSR, macro and agenda pages go last. Scanned pages cannot be ranked before OCR,
        so they are taken in order once ranked pages run out.
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
        used = sum(len(strip_boilerplate(_clean(self._digital[i]))) for i in chosen)
        for _, i in scored:
            size = len(strip_boilerplate(_clean(self._digital[i]))) if not self.is_scanned(i) else 3000
            if used + size > budget_chars:
                continue
            chosen.append(i)
            used += size
        parts = []
        for i in sorted(chosen):
            text = strip_boilerplate(_clean(self.page_text(i)))
            if text:
                parts.append(f"--- Page {i + 1} of {self.page_count} ---\n{text}")
        return "\n\n".join(parts)[:budget_chars]


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
