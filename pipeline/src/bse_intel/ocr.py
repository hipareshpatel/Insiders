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

import difflib
import logging
import math
import re
import statistics
import threading
from collections import Counter
from collections import Counter
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
    # Plain Python, not numpy: the text layer of a sideways page is put into lines here too, and that path
    # must work without the [ocr] extra (numpy comes with it; without it every PDF read as unreadable).
    cx = [i[2] for i in items]
    cy = [i[0] for i in items]
    bin_ = max(2.0, 0.35 * statistics.median(i[1] for i in items))

    def sharpness(theta: float) -> float:
        t = math.tan(theta)
        y = [yc - x * t for yc, x in zip(cy, cx)]
        low = min(y)
        counts = Counter(int((v - low) // bin_) for v in y)
        return float(sum(n * n for n in counts.values()))

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


_NUMBER = re.compile(r"^[\(\[\{\-−–]?\s*\d[\d,]*(?:\.\d+)?\s*[\)\]\}]?%?$")
_BRACKETS = str.maketrans("[]{}", "()()")


def _repair(token: str) -> str:
    """A figure whose bracket the OCR half-lost, or read as a brace, made whole again so a negative stays
    negative: "(2.0" and "{4,722}" are (2.0) and (4,722)."""
    if not _NUMBER.match(token):
        return token
    t = token.replace("−", "-").replace("–", "-").translate(_BRACKETS)
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


_NILS = {"-", "nil", "na", "n.a.", "n/a"}
_DASHES = str.maketrans({"–": "-", "—": "-", "−": "-"})


# A value that a reader garbled: digits with the letters and marks they are mistaken for - "8L6" for 978,
# "(Z,l64}" for (2,164), "(3.'5g)" for (3,959). Not a label word: "FY25" has letters that are not lookalikes,
# and "Q2" is too short to be taken for a figure.
_GARBLED = re.compile(r"[(\[{]?[\dlLIiJjOoDQSsZzBbgGq|!'.,:~-]+[)\]}]?%?")


def _figure(token: str) -> str | None:
    """A figure's value for matching, the same however it is printed: commas, a bracket sign, a footnote mark."""
    t = _repair(token.translate(_DASHES).strip("*,;"))
    if not _NUMBER.match(t) or not any(c.isdigit() for c in t):
        return None
    negative = t.startswith("(") or t.startswith("-")
    value = t.strip("()-%").replace(",", "")
    return ("-" if negative else "") + value


def _kind(token: str) -> str:
    """"fig" a figure, "nil" a nil cell, "bad" a garbled figure, "" anything else."""
    if _figure(token) is not None:
        return "fig"
    if token.translate(_DASHES).lower() in _NILS:
        return "nil"
    alnum = [c for c in token if c.isalnum()]
    digits = sum(c.isdigit() for c in alnum)
    if len(token) >= 3 and digits and digits >= 0.5 * len(alnum) and _GARBLED.fullmatch(token):
        return "bad"
    return ""


def _value_run(tokens: list[str]) -> int:
    """Where a row's trailing run of figures, nils and garbled figures begins."""
    start = len(tokens)
    while start > 0 and _kind(tokens[start - 1]):
        start -= 1
    return start


def _words(tokens: list[str]) -> set[str]:
    return {w for t in tokens for w in re.findall(r"[a-z]{3,}", t.lower())}


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.strip("(){}[]"), b.strip("(){}[]")).ratio()


def _align(ocr_run: list[str], layer_run: list[str], layer_exact: bool) -> list[str]:
    """One row's values as OCR read them, corrected cell by cell against the text layer's reading of it.

    The two runs are aligned by an edit distance over cells. A nil the text layer has and OCR lost is put
    back. A figure OCR garbled is taken from the layer where the layer's is clean; and where both are clean
    and differ by a digit or two, the layer's is taken when the layer is the PDF's own text, whose
    characters are exact - not a scan's invisible OCR layer, which misreads as often as RapidOCR does. A
    layer figure OCR did not read at all is not added: which cells the row has is OCR's to say."""
    kinds_a = [_kind(t) for t in ocr_run]
    kinds_b = [_kind(t) for t in layer_run]

    def same(i: int, j: int) -> bool:
        if kinds_a[i] == "fig" and kinds_b[j] == "fig":
            return _figure(ocr_run[i]) == _figure(layer_run[j])
        return (kinds_a[i] == kinds_b[j] == "nil") or ocr_run[i] == layer_run[j]

    def substitute(i: int, j: int) -> float:
        if same(i, j):
            return 0.0
        if "nil" in (kinds_a[i], kinds_b[j]):
            return 9.0                            # a nil is never misread as a figure, nor a figure as a nil
        return 2.0 * (1.0 - _similar(ocr_run[i], layer_run[j]))

    def insert(j: int) -> float:                  # a layer cell OCR did not read
        return 0.6 if kinds_b[j] == "nil" else 1.0

    n, m = len(ocr_run), len(layer_run)
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = float(i)
    for j in range(1, m + 1):
        cost[0][j] = cost[0][j - 1] + insert(j - 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i][j] = min(cost[i - 1][j - 1] + substitute(i - 1, j - 1),
                             cost[i - 1][j] + 1.0, cost[i][j - 1] + insert(j - 1))
    out: list[str] = []
    i, j = n, m
    while i or j:
        if i and j and cost[i][j] == cost[i - 1][j - 1] + substitute(i - 1, j - 1):
            a, b, kind = ocr_run[i - 1], layer_run[j - 1], kinds_a[i - 1]
            if kinds_b[j - 1] == "fig" and not same(i - 1, j - 1) and (
                    kind == "bad" or (kind == "fig" and layer_exact and _similar(a, b) >= 0.5)):
                out.append(b)
            else:
                out.append(_repair(a))
            i, j = i - 1, j - 1
        elif i and cost[i][j] == cost[i - 1][j] + 1.0:
            out.append(_repair(ocr_run[i - 1]))
            i -= 1
        else:
            if kinds_b[j - 1] == "nil":
                out.append(layer_run[j - 1])
            j -= 1
    return out[::-1]


def merge_with_text_layer(ocr_text: str, layer_text: str, layer_exact: bool = True) -> str:
    """OCR's reading of a page of figures, checked cell by cell against the page's text layer.

    OCR keeps a table's rows together better than a text layer does - on the benchmark it put 98% of the
    figures on their own row against 60% - but it loses thin cells, a "-" for nil or a "Nil", and every
    later figure in the row slides a column left: Novartis's "(2.0) 0.4 - (1.7) 1.7" came back
    "(2.0) 0.4 (1.7) 1.7". Now and then it misreads a digit: Jubilant's 978 came back "8l6". The text layer
    has both right where it holds the row at all. So each OCR row is matched to the text-layer line that
    carries its figures - every clean figure OCR read, or at least half of them under the same label - and
    the two are aligned cell by cell (_align). A row with no such line, or with two that disagree, is left
    as OCR read it. `layer_exact` is False for a scan's invisible OCR layer: its figures fill gaps but do
    not overrule OCR's."""
    if not layer_text:
        return ocr_text
    layer = []
    whole_lines: dict[tuple, str | None] = {}
    for line in layer_text.splitlines():
        tokens = line.split()
        start = _value_run(tokens)
        clean = Counter(_figure(t) for t in tokens[start:] if _kind(t) == "fig")
        if clean:
            layer.append((tokens[start:], clean, _words(tokens[:start])))
        every = tuple(sorted(Counter(_figure(t) for t in tokens if _kind(t) == "fig").items()))
        if sum(n for _, n in every) >= 2:
            whole_lines[every] = " ".join(tokens) if whole_lines.get(every, " ".join(tokens)) == " ".join(tokens) else None
    out = []
    for line in ocr_text.splitlines():
        tokens = line.split()
        # The PDF's own text, where one of its lines carries exactly this row's figures, is the row: its
        # characters are exact and it keeps every cell - Jubilant's AOC-1 has a "Nil" that OCR read "i!n".
        every = tuple(sorted(Counter(_figure(t) for t in tokens if _kind(t) == "fig").items()))
        if layer_exact and whole_lines.get(every):
            out.append(whole_lines[every])
            continue
        start = _value_run(tokens)
        run = tokens[start:]
        clean = Counter(_figure(t) for t in run if _kind(t) == "fig")
        n_clean, slots = sum(clean.values()), sum(1 for t in run if _kind(t) in ("fig", "bad"))
        words = _words(tokens[:start])
        found = []
        for layer_run, layer_clean, layer_words in layer:
            shared = sum((clean & layer_clean).values())
            labelled = bool(words) and len(words & layer_words) >= 0.5 * len(words)
            whole = shared == n_clean >= 2 and sum(layer_clean.values()) <= slots
            if whole or (labelled and shared >= max(1, 0.5 * n_clean)):
                found.append((shared, labelled, layer_run))
        if found:
            top = max((shared, labelled) for shared, labelled, _ in found)
            rivals = {tuple(r) for shared, labelled, r in found if (shared, labelled) == top}
            if len(rivals) == 1:
                merged = _align(run, list(rivals.pop()), layer_exact)
                if merged != run:
                    out.append("  ".join([" ".join(tokens[:start]), " ".join(merged)]).strip())
                    continue
        out.append(line)
    return "\n".join(out)


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
