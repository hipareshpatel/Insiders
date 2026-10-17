"""Local OCR for scanned and unreadable pages: RapidOCR on the CPU, no API quota, no network.

Measured 2026-10-17 on a GitHub-hosted runner (scripts/ocr_probe.py, NSE filings): about 5 s a page,
and on statement pages it put more figures on their own row than any text layer. It is an optional
install (``pip install -e ".[ocr]"``); without it the pipeline falls back to the vision route.

RapidOCR returns one box per run of text. The boxes are put back into lines by their vertical centre,
left to right, so a table row reads as its label followed by its figures - the order the analysis and
the quote checks expect.

Which RapidOCR, and how its boxes become lines, was settled on the extraction benchmark (docs/bench):
the `rapidocr` 3.x package with the settings below put 98.5% of a results statement's figures on their
own row in the current column, and 98% on seven complicated pages, against 36% on those pages for the
older `rapidocr_onnxruntime` with plain grouping by height. That one ran the words of a label together
("EmployeeBenefitsExpense") and merged two close rows with their figures interleaved - "Employee
Benefits Expense Finance Costs 31.7 1.2 48.1 3.6 ...", a wrong column on every figure.
"""

from __future__ import annotations

import logging
import math
import re
import threading
from typing import Callable

log = logging.getLogger(__name__)

# 200 dpi read more figures than 150 (by 3.6 points on the benchmark pages); 300 added nothing but time.
DPI = 200

# The detector and recogniser settings measured on the benchmark (data/bench/scripts/paddle/run_rapidocr.py).
SETTINGS = {
    "Global.max_side_len": 3300, "Global.use_cls": True, "Global.log_level": "warning",
    "EngineConfig.onnxruntime.intra_op_num_threads": 4, "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    "Det.box_thresh": 0.5, "Det.unclip_ratio": 1.6, "Det.limit_type": "min", "Det.limit_side_len": 736,
}

_engine = None
_lock = threading.Lock()  # one page at a time: OCR is rare, and the CPU is shared with the workers


def available() -> bool:
    try:
        import rapidocr  # noqa: F401
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def _new_engine():
    from rapidocr import ModelType, RapidOCR

    return RapidOCR(params={**SETTINGS, "Det.model_type": ModelType("small"), "Rec.model_type": ModelType("small")})


def _boxes(output) -> list[tuple]:
    """RapidOCR's answer as [(box, text, score), ...], whichever form it came in."""
    if output is None:
        return []
    if isinstance(output, tuple):          # (result, elapsed), as the older package and the tests return it
        output = output[0]
    if hasattr(output, "boxes"):           # rapidocr 3.x: an object with boxes, txts and scores
        if output.boxes is None or output.txts is None:
            return []
        return [(box, text, score) for box, text, score in zip(output.boxes, output.txts, output.scores)]
    return list(output or [])


def _skew(items: list[tuple]) -> float:
    """The page's tilt in radians from the box centres alone: the angle whose row histogram is sharpest."""
    if len(items) < 30:
        return 0.0
    import numpy as np

    cx = np.array([i[2] for i in items])
    cy = np.array([i[0] for i in items])
    bin_ = max(2.0, 0.35 * float(np.median([i[1] for i in items])))

    def sharpness(theta: float) -> float:
        y = cy - cx * math.tan(theta)
        counts, _ = np.histogram(y, bins=np.arange(y.min(), y.max() + bin_, bin_))
        return float((counts.astype(float) ** 2).sum())

    base = best_s = sharpness(0.0)
    best = 0.0
    for deg in [d / 10 for d in range(-30, 31)]:
        if (s := sharpness(math.radians(deg))) > best_s:
            best, best_s = math.radians(deg), s
    for step in range(-5, 6):
        theta = best + math.radians(step * 0.02)
        if (s := sharpness(theta)) > best_s:
            best, best_s = theta, s
    return best if best_s > 1.04 * base else 0.0


_NUMBER = re.compile(r"^[\(\[\-−–]?\s*\d[\d,]*(?:\.\d+)?\s*[\)\]]?%?$")


def _repair(token: str) -> str:
    """A figure whose bracket the OCR half-lost, made whole again so a negative stays negative."""
    if not _NUMBER.match(token):
        return token
    t = token.replace("−", "-").replace("–", "-").replace("[", "(").replace("]", ")")
    if t.startswith("(") != t.endswith(")"):
        t = "(" + t.strip("()") + ")"
    return t


def lines_from_boxes(result) -> str:
    """RapidOCR's boxes as text lines, top to bottom and left to right.

    The page's tilt is measured first and taken out, so a slightly skewed scan does not slide one row into
    the next. A box joins the line whose running centre is within half the smaller box's height of its own,
    looking only at the last few lines; a figure whose bracket was half-lost has it put back."""
    items = []
    for box, text, _score in _boxes(result):
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        if str(text).strip():
            items.append(((min(ys) + max(ys)) / 2, max(max(ys) - min(ys), 1.0), min(xs), str(text).strip()))
    if (theta := _skew(items)):
        t = math.tan(theta)
        items = [(yc - x * t, h, x, text) for yc, h, x, text in items]
    items.sort(key=lambda i: (i[0], i[2]))
    lines: list[dict] = []
    for yc, h, x, text in items:
        home = None
        for line in lines[-3:]:
            if abs(yc - line["yc"]) <= 0.5 * min(h, line["h"]):
                home = line
        if home is None:
            lines.append({"yc": yc, "h": h, "items": [(x, text)]})
        else:
            home["items"].append((x, text))
            n = len(home["items"])
            home["yc"] += (yc - home["yc"]) / n
            home["h"] += (h - home["h"]) / n
    return "\n".join("  ".join(re.sub(r"\S+", lambda m: _repair(m.group()), text) for _x, text in sorted(line["items"]))
                     for line in lines)


def lying_flat(result) -> float:
    """The share of RapidOCR's boxes that are wider than they are tall: near 1 on an upright page."""
    boxes = [box for box, text, _score in _boxes(result) if str(text).strip()]
    if not boxes:
        return 1.0
    flat = sum(1 for b in boxes
               if max(p[0] for p in b) - min(p[0] for p in b) >= max(p[1] for p in b) - min(p[1] for p in b))
    return flat / len(boxes)


def _mean_score(result) -> float:
    scores = [float(score) for _box, text, score in _boxes(result) if str(text).strip()]
    return sum(scores) / len(scores) if scores else 0.0


def recognise(png: bytes) -> str:
    """The page image's text, in lines.

    A page printed sideways - an annual report's Form AOC-1 or fixed-asset note, set landscape on a portrait
    page - is read with high confidence, because each run of text is recognised on its own, but its boxes
    stand on end, and putting them back into lines by height then makes the table's columns into rows: the
    benchmark's rotated AOC-1 came back as 17 transposed "rows" (2026-10-17). So when most boxes stand on
    end, the page is read again turned a quarter each way, and the reading whose boxes lie flat is kept.
    """
    global _engine
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    with _lock:
        if _engine is None:
            _engine = _new_engine()
        result = _boxes(_engine(image if image is not None else png))
        if len(result) >= 8 and lying_flat(result) < 0.5 and image is not None:
            best = None
            for turn in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
                turned = _boxes(_engine(cv2.rotate(image, turn)))
                if turned and lying_flat(turned) >= 0.5 and (best is None or _mean_score(turned) > _mean_score(best)):
                    best = turned
            if best is not None:
                result = best
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
