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

SCANNED_PAGE_CHARS = 50
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
                log.warning("OCR failed on page %d: %s", index + 1, exc)
        self._ocr_cache[index] = text
        return text

    def close(self) -> None:
        if self._doc is not None:
            with _MUPDF:
                self._doc.close()
            self._doc = None

    def first_page_text(self, limit: int = 2500) -> str:
        return _clean(self.page_text(0))[:limit] if self.page_count else ""

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
        used = sum(len(_clean(self._digital[i])) for i in chosen)
        for _, i in scored:
            size = len(_clean(self._digital[i])) if not self.is_scanned(i) else 3000
            if used + size > budget_chars:
                continue
            chosen.append(i)
            used += size
        parts = []
        for i in sorted(chosen):
            text = _clean(self.page_text(i))
            if text:
                parts.append(f"--- Page {i + 1} of {self.page_count} ---\n{text}")
        return "\n\n".join(parts)[:budget_chars]


_WS = re.compile(r"[ \t ]+")
_BLANKS = re.compile(r"\n{3,}")


def _clean(text: str) -> str:
    return _BLANKS.sub("\n\n", _WS.sub(" ", text)).strip()
