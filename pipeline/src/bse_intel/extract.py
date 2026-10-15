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

log = logging.getLogger(__name__)

SCANNED_PAGE_CHARS = 80  # blueprint §5.3: under 80 characters of text and an image means scanned
OcrFn = Callable[[bytes], str]

# PyMuPDF does not support concurrent use from multiple threads, even on
# separate documents. All PyMuPDF calls go through this lock; OCR network
# calls happen outside it.
_MUPDF = threading.Lock()


class Document:
    def __init__(self, pdf_bytes: bytes | None, ocr: OcrFn | None = None, max_ocr_pages: int = 6, dpi: int = 150):
        self._ocr = ocr
        self._max_ocr = max_ocr_pages
        self._dpi = dpi
        self._ocr_cache: dict[int, str] = {}
        self.ocr_pages_used = 0
        self.ocr_error: Exception | None = None  # last OCR failure, if any
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
                self._digital = [page.get_text("text") or "" for page in doc]
                self._has_image = [bool(page.get_images(full=False)) for page in doc]
        except Exception as exc:  # corrupt PDF, or a non-PDF attachment (xml, zip, xlsx)
            self.error = f"unreadable attachment: {exc}"
            log.warning(self.error)

    def to_cache(self) -> dict:
        """Everything read from the PDF (digital text and the pages OCR'd so far), for the text cache."""
        return {"v": 1, "error": self.error, "digital": self._digital, "has_image": self._has_image,
                "ocr": {str(k): v for k, v in self._ocr_cache.items()}}

    @classmethod
    def from_cache(cls, data: dict, ocr: OcrFn | None = None, max_ocr_pages: int = 6) -> "Document":
        doc = cls(None, ocr=ocr, max_ocr_pages=max_ocr_pages)
        doc.error = data.get("error")
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

    def page_text(self, index: int) -> str:
        if index >= self.page_count:
            return ""
        if not self.is_scanned(index):
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

    def select_text(self, budget_chars: int, keywords: Iterable[str] = ()) -> str:
        """Pick the most relevant pages within a character budget, kept in page order.

        The first two pages are always included (cover letter + headline
        numbers); the rest are ranked by keyword hits. Scanned pages cannot be
        ranked before OCR, so they are taken in order once ranked pages run out.
        """
        if not self.page_count:
            return ""
        patterns = [re.compile(re.escape(k), re.I) for k in keywords]
        chosen = [i for i in range(min(2, self.page_count))]
        scored = []
        for i in range(len(chosen), self.page_count):
            if self.is_scanned(i):
                scored.append((-1, i))
                continue
            hits = sum(len(p.findall(self._digital[i])) for p in patterns)
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


_WS = re.compile(r"[ \t ]+")
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
    r"|information is (?:being )?(?:uploaded|available|hosted) on the (?:company's )?website",
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
