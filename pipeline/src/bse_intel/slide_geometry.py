"""Call memory (TODO 144): a slide's figure tied to its label by where the two stand on the page.

Why: on a deck slide (a chart, a pie, a grid of KPI boxes) the text layer puts the labels on one line and the figures on the
next, so the AI that reads the text pairs a figure with the wrong label (ESAF's "CRAR 34.3%", Welspun's TMT volume read from
the stainless-steel row, MTAR's order-book pie, Thyrocare's 12,911 franchisees read as tests). A rule on the text alone fails
(measured 30 Oct 2026 on 205 judged points: "label and figure in one stretch" drops 77 of 133 right ones). Here the words
come with their boxes (PyMuPDF words for a text-layer page, RapidOCR's boxes for a scanned one) and the figure's own
neighbours are read off the page.

The rule, in words. Take the boxes on the page that read as the point's figure. For each, its labels are
  * the row label: the nearest text box to its left on the same row (figures to its left are skipped; a period header such
    as "Q2FY26" is not a label);
  * the column labels: the nearest text box above and the nearest below, in the figure's column band;
  * a label line paired by order: a line of n text boxes directly above or below a line of n figures pairs the k-th with the
    k-th (labels centred over a column of figures that is wider or narrower than they are; a legend written in order).
Each label is one box plus the lines stacked straight over or under it (a label broken over two lines). A figure's score is
how many of the point's label words (the quote's own words, minus periods, units and filler) its labels carry together. The
page's best score is the highest of any figure on the page. The point is
  * "tied" when one of the figure's boxes scores the page's best;
  * "other" when every box scores below it: the label words are on the page, tied to a different figure (dropped);
  * "unproven" when the figure is on the page but no label of it can be read at all, or the label words stand next to none
    of the page's figures (dropped, as the spec asks: a pairing that cannot be proven is not kept);
  * "unknown" when the page gives nothing to judge by (no boxes, the figure not found, no label word in the quote): kept,
    as `_column_verdict` keeps when the page cannot tell.
A pie's segment shares are tied only where the label stands beside the share or the legend is a parallel list of the same
length; a legend by colour is not read (a swatch is not a word), so it is "unproven".
"""
from __future__ import annotations

import re
from typing import NamedTuple


class Word(NamedTuple):
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return max(self.y1 - self.y0, 1.0)


# ---------------------------------------------------------------- boxes from the two readers
def words_from_pymupdf(raw: list[tuple]) -> list[Word]:
    """`page.get_text("words")` rows (x0, y0, x1, y1, text, block, line, word) as Words."""
    return [Word(float(r[0]), float(r[1]), float(r[2]), float(r[3]), str(r[4])) for r in raw if str(r[4]).strip()]


def words_from_ocr(boxes: list[tuple]) -> list[Word]:
    """RapidOCR's boxes ((polygon, text, score), ocr._boxes form) as Words; a box of several words is cut at its spaces,
    each word taking the share of the box's width its characters hold."""
    out: list[Word] = []
    for box, text, *_ in boxes:
        text = str(text).strip()
        if not text:
            continue
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        x0, x1, y0, y1 = float(min(xs)), float(max(xs)), float(min(ys)), float(max(ys))
        parts = text.split()
        total = sum(len(p) for p in parts) + len(parts) - 1
        at = 0.0
        for part in parts:
            a = x0 + (x1 - x0) * at / total
            at += len(part)
            out.append(Word(a, y0, x0 + (x1 - x0) * at / total, y1, part))
            at += 1
    return out


def page_words(pdf_bytes: bytes, page: int, ocr: bool = False, dpi: int = 200) -> list[Word]:
    """The Words of PDF page `page` (1-based): the text layer's, or for a scanned page (`ocr`) RapidOCR's, in the page's own
    points (the OCR image's pixels scaled back by 72/dpi). Not used in the unit tests (they give boxes)."""
    import pymupdf

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        pg = doc[page - 1]
        if not ocr:
            return words_from_pymupdf(pg.get_text("words"))
        from . import ocr as ocr_mod
        scale = 72.0 / dpi
        found = words_from_ocr(ocr_mod.page_boxes(pg.get_pixmap(dpi=dpi).tobytes("png")))
        return [Word(w.x0 * scale, w.y0 * scale, w.x1 * scale, w.y1 * scale, w.text) for w in found]


# ---------------------------------------------------------------- reading the boxes
_NUM = re.compile(r"^[₹$(\[]*-?\d[\d,]*(?:\.\d+)?[)\]]*(?:%|x|X|\*)*$")
_PERIOD = re.compile(r"^(?:(?:Q[1-4]|H[12]|9M)[-]?)?(?:FY|CY)['’]?(?:20)?\d{2}(?:[-–/](?:20)?\d{2})?[*]?$|^(?:Q[1-4]|H[12]|9M)$|^(?:19|20)\d{2}$"
                     r"|^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-'’ ]?\d{2,4}$", re.I)
_FILLER = frozenset("""the and for with from that this its per was were has have had are been will not but all any also
    over under into than then their there which while where when what who how can may more most less one two three
    cent percent pct crore crores cr lakh lakhs lac mn mln million bn billion tonnes tonne mt kmt units rs inr usd
    year years yoy qoq growth increase increased decrease decreased fiscal quarter half period total""".split())
_ROW_TOL = 0.6       # boxes are on one row when their centres are within this many text heights
_STACK_GAP = 0.9     # a label line belongs to the one it stacks on when the gap is within this many heights
_REACH = 9           # a column label is looked for within this many text heights above or below
_BAND = 0.75         # the column band is the figure's width widened this much on each side


def _value(text: str) -> float | None:
    t = text.strip()
    if not _NUM.match(t):
        return None
    neg = t.startswith("(") or t.startswith("[") or t.lstrip("₹$").startswith("-")
    digits = re.search(r"\d[\d,]*(?:\.\d+)?", t)
    if digits is None:
        return None
    v = float(digits.group().replace(",", ""))
    return -v if neg else v


def _is_text(w: Word) -> bool:
    return _value(w.text) is None and not _PERIOD.match(w.text.strip(" ,;:")) and bool(re.search(r"[A-Za-z]{2}", w.text))


def _stem(word: str) -> str:
    w = re.sub(r"[^a-z0-9]", "", word.lower())
    return w if len(w) <= 5 else w[:5]


def label_words(quote: str, statement: str = "") -> set[str]:
    """The stems of the quote's own label words: no figures, periods, units or filler (the statement's words only when the
    quote has none)."""
    def pick(text: str) -> set[str]:
        found = set()
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9&'’.-]*", text or ""):
            tok = tok.strip(".-'’")
            if len(tok) < 2 or tok.lower() in _FILLER or _PERIOD.match(tok):
                continue
            if tok.lower() in ("fy", "cy", "ltm"):
                continue
            found.add(_stem(tok))
        return found
    return pick(quote) or pick(statement)


def _phrases(words: list[Word]) -> list[Word]:
    """Neighbouring text words on one row, a space apart, merged to one phrase; a figure stays a box of its own."""
    out: list[Word] = []
    for w in sorted(words, key=lambda w: (round(w.cy / 3), w.x0)):
        if out and _is_text(w) and _is_text(out[-1]) and abs(out[-1].cy - w.cy) <= _ROW_TOL * min(out[-1].h, w.h) \
                and -0.3 * w.h <= w.x0 - out[-1].x1 <= 0.9 * w.h:
            p = out[-1]
            out[-1] = Word(min(p.x0, w.x0), min(p.y0, w.y0), max(p.x1, w.x1), max(p.y1, w.y1), f"{p.text} {w.text}")
        else:
            out.append(w)
    return out


def _stacked(label: Word, texts: list[Word], numeric: list[Word], fig: Word | None = None) -> str:
    """The label's text with the lines stacked straight over or under it (a label broken over lines), a line with a figure
    on its row not counted."""
    def on_figure_row(p: Word) -> bool:
        return any(n is not fig and abs(n.cy - p.cy) <= _ROW_TOL * max(n.h, p.h) for n in numeric)
    parts = [(label.cy, label.text)]
    for step in (-1, 1):
        cur = label
        while True:
            nxt = None
            for p in texts:
                gap = (cur.y0 - p.y1) if step < 0 else (p.y0 - cur.y1)
                if 0 <= gap <= _STACK_GAP * cur.h and abs(p.x0 - cur.x0) <= 1.5 * cur.h \
                        and not on_figure_row(p) and (nxt is None or gap < nxt[0]):
                    nxt = (gap, p)
            if nxt is None:
                break
            cur = nxt[1]
            parts.append((cur.cy, cur.text))
    return " ".join(t for _, t in sorted(parts))


def _score(text: str, want: set[str]) -> set[str]:
    have = {_stem(t) for t in re.findall(r"[A-Za-z][A-Za-z0-9&'’]*", text)}
    return want & have


def _labels_of(fig: Word, texts: list[Word], numeric: list[Word]) -> list[str]:
    """The text of the labels of one figure box: row label, column label above, column label below."""
    found: list[str] = []
    # the row label: the nearest text box to the left on the row, figures skipped
    row = [p for p in texts if abs(p.cy - fig.cy) <= _ROW_TOL * max(p.h, fig.h) and p.x1 <= fig.x0 + 0.3 * fig.h]
    if row:
        found.append(_stacked(max(row, key=lambda p: p.x1), texts, numeric, fig))
    # the column labels: the nearest text above and below whose box meets the figure's widened band
    lo, hi = fig.x0 - _BAND * (fig.x1 - fig.x0), fig.x1 + _BAND * (fig.x1 - fig.x0)
    for step in (-1, 1):
        near = []
        for p in texts:
            if abs(p.cy - fig.cy) <= _ROW_TOL * max(p.h, fig.h):
                continue
            gap = (fig.y0 - p.y1) if step < 0 else (p.y0 - fig.y1)
            if 0 <= gap <= _REACH * fig.h and p.x1 >= lo and p.x0 <= hi:
                near.append((gap, p))
        if near:
            found.append(_stacked(min(near, key=lambda g: g[0])[1], texts, numeric, fig))
    # a line of n labels over or under a line of n figures pairs by order
    line = sorted((n for n in numeric if abs(n.cy - fig.cy) <= _ROW_TOL * max(n.h, fig.h)), key=lambda n: n.x0)
    if len(line) >= 2 and fig in line:
        k = line.index(fig)
        for step in (-1, 1):
            near = [p for p in texts if (0 < (fig.y0 - p.y1 if step < 0 else p.y0 - fig.y1) <= _REACH * fig.h)]
            rows: dict[int, list[Word]] = {}
            for p in near:
                rows.setdefault(round(p.cy / (0.8 * p.h)), []).append(p)
            for cand in sorted(rows.values(), key=lambda r: abs(r[0].cy - fig.cy)):
                cand = sorted(cand, key=lambda p: p.x0)
                if len(cand) == len(line):
                    found.append(_stacked(cand[k], texts, numeric, fig))
                break   # only the nearest line of labels
    return found


class Verdict(NamedTuple):
    state: str       # "tied" | "other" | "unproven" | "unknown"
    detail: str


def figure_label_verdict(value: float, quote: str, words: list[Word], statement: str = "") -> Verdict:
    """Is the figure `value` of a point on this page tied to the label its quote names? See the module's rule."""
    want = label_words(quote, statement)
    if not words or not want:
        return Verdict("unknown", "no word boxes on the page" if not words else "no label word in the quote")
    phrases = _phrases(words)
    numeric = [w for w in words if _value(w.text) is not None]
    texts = [p for p in phrases if _is_text(p)]
    if not texts:
        return Verdict("unknown", "no label text on the page")
    ours = [n for n in numeric if abs(abs(_value(n.text)) - abs(value)) < 1e-9]
    if not ours:
        return Verdict("unknown", f"the figure {value:g} is not among the page's boxes")
    scores: dict[int, set[str]] = {}
    labelled: dict[int, list[str]] = {}
    for n in numeric:
        labs = _labels_of(n, texts, numeric)
        labelled[id(n)] = labs
        scores[id(n)] = set().union(*[_score(t, want) for t in labs]) if labs else set()
    best = max((len(s) for s in scores.values()), default=0)
    mine = max(len(scores[id(n)]) for n in ours)
    names = ", ".join(sorted(want))
    if best == 0:
        if any(labelled[id(n)] for n in ours):
            return Verdict("unproven", f"none of the quote's label words ({names}) stands by any figure on the page")
        return Verdict("unproven", f"the figure {value:g} has no label to read")
    if mine >= best:
        return Verdict("tied", f"the figure stands by {sorted(set().union(*[scores[id(n)] for n in ours]))}")
    seen = "; ".join(" | ".join(t for t in labelled[id(n)])[:60] for n in ours[:2]) or "no label"
    return Verdict("other", f"the figure {value:g} stands by '{seen}', not by {names}")


def geometry_issue(point, words: list[Word]) -> str | None:
    """The reason a SLIDE point's figure is not tied to its label by the page's boxes, or None (tied, or the page cannot
    tell). `point` is a CallPoint; the figure is its value (the high end of a range is checked the same way)."""
    if point.section != "SLIDE" or point.value is None:
        return None
    v = figure_label_verdict(point.value, point.quote or "", words, point.statement or "")
    if v.state in ("other", "unproven"):
        return f"{v.state}: {v.detail}"
    return None
