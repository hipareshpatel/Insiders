"""Local OCR for scanned and unreadable pages: RapidOCR on the CPU, no API quota, no network.

Measured 2026-10-17 on a GitHub-hosted runner (scripts/ocr_probe.py, NSE filings): about 5 s a page,
and on statement pages it put more figures on their own row than any text layer. It is an optional
install (``pip install -e ".[ocr]"``); without it the pipeline falls back to the vision route.

RapidOCR returns one box per run of text. The boxes are put back into lines by their vertical centre,
left to right, so a table row reads as its label followed by its figures - the order the analysis and
the quote checks expect.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

log = logging.getLogger(__name__)

# 200 dpi read more figures than 150 (by 3.6 points on the benchmark pages); 300 added nothing but time.
DPI = 200

_engine = None
_lock = threading.Lock()  # one page at a time: OCR is rare, and the CPU is shared with the workers


def available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def lines_from_boxes(result) -> str:
    """RapidOCR's [(box, text, score), ...] as text lines, top to bottom and left to right.
    Two boxes share a line when their vertical centres are closer than half the smaller box's height."""
    items = []
    for box, text, _score in result or []:
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        items.append(((min(ys) + max(ys)) / 2, max(max(ys) - min(ys), 1.0), min(xs), str(text).strip()))
    items = [i for i in items if i[3]]
    items.sort(key=lambda i: (i[0], i[2]))
    lines: list[list[tuple]] = []
    for item in items:
        last = lines[-1] if lines else None
        if last and abs(item[0] - last[-1][0]) < min(item[1], last[-1][1]) / 2:
            last.append(item)
        else:
            lines.append([item])
    return "\n".join("  ".join(i[3] for i in sorted(line, key=lambda i: i[2])) for line in lines)


def recognise(png: bytes) -> str:
    """The page image's text, in lines."""
    global _engine
    with _lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
        result, _ = _engine(png)
    return lines_from_boxes(result)


def page_reader(vision: Callable[[bytes], str] | None) -> Callable[[bytes], str] | None:
    """The OCR function for a document: RapidOCR when installed, the vision route when RapidOCR reads
    nothing or fails; the vision route alone when RapidOCR is not installed; None when neither."""
    if not available():
        return vision

    def read(png: bytes) -> str:
        try:
            text = recognise(png)
        except Exception as exc:  # a broken install or a bad image: the vision route, if any, still reads it
            if vision is None:
                raise
            log.warning("local OCR failed (%s); using the vision route", exc)
            return vision(png)
        if len(text.strip()) < 20 and vision is not None:
            return vision(png) or text
        return text

    return read
