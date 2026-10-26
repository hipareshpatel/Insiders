"""The filing's own PDF as the last referee of the screener cross-check (owner, 26 Oct 2026, TODO 61). Read only: no memory
write, no card change, no AI, no screener request. It reads NSE (announcement lists, the results PDFs).

Input is the ``screener-referee`` CSV. Only the pairs still open after the XBRL step are taken: verdict ``neither``,
``no_file`` and ``screener_matches_official`` (where the XBRL may itself be wrong). Everything else is left out.

Finding the PDF. NSE's results lists give an XBRL link and no attachment, so the PDF is found as the pipeline finds a
filing's attachment: the company's announcements (``NseClient.announcements``, one call a company and period) in the
window after the period ends (a quarter: the day after its end to 120 days later), keeping the results filings
(subject or headline "financial results" or "outcome of board meeting"), the "Financial Results" subject first. Each PDF
is downloaded once (``NseClient.fetch``, on the archive pace of ``NSE_ARCHIVE_PAUSE_SECONDS``) and read once, with the
pipeline's own ``Document`` (text layer, local OCR on pages of figures and scanned pages when RapidOCR is installed, never
the vision route). At most ``MAX_CANDIDATES`` PDFs are tried for a period; the first one with the figure in a proven
column is used.

Reading the figure. The row and its column are read from each page's text, with the pipeline's own helpers
(``screener_referee.numbers_on`` and its date pattern, ``periods.explicit_date``, ``grounding.unit_before``); no new table
parser. A row is a line whose label names the metric (revenue from operations, interest earned, net profit for the
period, basic EPS) followed by its figures. A figure is *proven* only when all of these hold, else it is ``pdf_unsure``:

- the header line above the row names two or more dates, and the row has exactly as many figures as the header has dates
  (a nil cell a reader dropped would slide a figure into the wrong column: counted, not guessed);
- the column's kind (quarter, half year, nine months, year) is told by the group words of the header, either one per
  date or one before a run of dates; the period's own column is the one of its kind with its end date; when the kinds
  cannot be told, a date that appears once in the header is accepted only if the header says "quarter" (for a quarter);
- the basis comes from the nearest title above the row that names one basis (a document that never says "consolidated"
  is standalone), and equals memory's;
- the unit is declared on the page ahead of the row (crore, lakh, million, ...), except for EPS.

Verdicts: ``pdf_matches_ours``, ``pdf_matches_screener``, ``pdf_matches_xbrl`` (a figure that agrees with the XBRL
referee's official value, and not ours), ``pdf_matches_none`` (a proven figure that agrees with no value), ``pdf_unsure`` (a
figure on the page but not provably the right column, basis or unit) and ``pdf_unreadable`` (no PDF, not downloaded, no
text, no results row; the reason in ``reason``). ``not_run`` marks pairs cut by ``--limit`` or the time budget. When
several values agree, ``matches`` lists them all.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from .bse import AttachmentError, AttachmentTooLarge
from .extract import Document
from .grounding import unit_before
from .memory_gaps import quarter_end
from .metrics import CONSOLIDATED, STANDALONE
from .nse import SourceBlockedError
from .periods import explicit_date
from .screener_crosscheck import _close
from .screener_referee import _DATE, _NUMBER, numbers_on
from .screener_xbrl_referee import ours_close

log = logging.getLogger(__name__)

OPEN_VERDICTS = ("neither", "no_file", "screener_matches_official")
VERDICTS = ("pdf_matches_ours", "pdf_matches_screener", "pdf_matches_xbrl", "pdf_matches_none", "pdf_unsure",
            "pdf_unreadable", "not_run")
MAX_CANDIDATES = 4          # results PDFs tried for one period
MAX_PAGES = 12              # candidate table pages read in one PDF
WINDOW_DAYS = 120           # a period's results are filed within this many days after its end
MAX_PDF_BYTES = 40_000_000
HEADER_LOOKBACK = 60
GROUP_LINES_ABOVE = 4       # lines above the date line searched for the group words ("Quarter ended")

_GROUP = re.compile(r"(?P<half>half[\s-]*year(?:ly)?|six\s+months|6\s+months)|(?P<nine>nine\s+months|9\s+months)"
                    r"|(?P<year>year\s+ended|twelve\s+months|12\s+months|\byear\b|\bannual\b)"
                    r"|(?P<quarter>quarter|three\s+months|3\s+months)", re.I)
_CONS = re.compile(r"\bconsolidated\b", re.I)
_ALONE = re.compile(r"\bstand[- ]?alone\b", re.I)
_TITLE = re.compile(r"results|statement|financial|profit|particulars", re.I)
_RESULTS = re.compile(r"financial\s+results?|outcome\s+of\s+(?:the\s+)?board|\bresults?\b", re.I)
_NOT_RESULTS = re.compile(r"intimation|trading\s+window|earnings?\s+call|conference\s+call|presentation|transcript|investor|"
                          r"analyst|schedule|press\s+release|clarification|copy\s+of\s+newspaper", re.I)

_REVENUE = re.compile(r"(?:revenue|income|sales)\s+from\s+operations|net\s+sales|total\s+interest\s+earned|"
                      r"^\W*(?:\d+\W+)?interest\s+earned", re.I)
_PAT_NAME = re.compile(r"^\W*(?:[ivx]+\W+|\d+\W+|[a-d]\)\s*)?(?:net\s+|total\s+)?(?:profit|loss)\b[^\d]{0,40}?"
                       r"(?:for\s+the\s+(?:period|year|quarter)|after\s+tax|after\s+taxes)", re.I)
_PAT_NOT = re.compile(r"before|attributable|owners|comprehensive|continuing|discontinued|per\s+share|margin|%|"
                      r"minority|non[- ]controlling|exceptional|share\s+of", re.I)
_EPS = re.compile(r"earnings?\s+per\s+(?:equity\s+)?share[^\d]{0,60}basic|^\W*(?:\(?[a-d]\)?\W+)?basic\b", re.I)
_EPS_CONTEXT = re.compile(r"earnings?\s+per|\beps\b", re.I)


@dataclass
class Row:
    metric: str
    label: str
    basis: str | None
    unit: float | None                     # figures per crore
    figures: list[float]
    columns: list[tuple[str, date]] | None  # (kind, end date) per figure, when the header proves them
    dates: list[date]
    group_words: set[str]
    page: int
    why: str = ""                          # why the columns are not proven


# --- reading a page -----------------------------------------------------------------------------------------------

def _dates_in(line: str) -> list[date]:
    return [d for m in _DATE.finditer(line) if (d := explicit_date(m[0]))]


def _words_basis(words: str) -> str | None:
    cons, alone = bool(_CONS.search(words)), bool(_ALONE.search(words))
    return CONSOLIDATED if cons and not alone else STANDALONE if alone and not cons else None


def _basis_above(lines: list[str], at: int) -> str | None:
    """The basis of the nearest title above ``at`` that names exactly one."""
    for back in range(at - 1, max(-1, at - 120), -1):
        line = lines[back]
        if _TITLE.search(line) and (found := _words_basis(line)):
            return found
    return None


def _groups(region: str, dates: list[date]) -> list[str] | None:
    """The kind of each of the header's dates (quarter, half, nine, year), or None when the words do not say."""
    events: list[tuple[int, str, object]] = []
    for m in _GROUP.finditer(region):
        events.append((m.start(), "g", m.lastgroup))
    for m in _DATE.finditer(region):
        if (d := explicit_date(m[0])):
            events.append((m.start(), "d", d))
    events.sort(key=lambda e: e[0])
    kinds = [e for e in events if e[1] == "g"]
    stamps = [e for e in events if e[1] == "d"]
    if len(stamps) != len(dates) or not kinds:
        return None
    if all(g[0] < stamps[0][0] for g in kinds) and len(kinds) == len(stamps):
        return [g[2] for g in kinds]            # one group word a column, written above the dates
    out: list[str] = []
    current = None
    follows_group = False
    for _, what, value in events:
        if what == "g":
            if current is not None and not follows_group:
                return None                      # two group words with no date between: the layout is not told
            current, follows_group = value, False
        else:
            if current is None:
                return None
            out.append(current)
            follows_group = True
    if current is not None and not follows_group:
        return None
    return out if len(out) == len(dates) else None


def parse_page(text: str, page: int, consolidated_anywhere: bool) -> list[Row]:
    """The metric rows (revenue, pat, eps) of one page's text, each with the column proof it has."""
    lines = text.splitlines()
    rows: list[Row] = []
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    for i, line in enumerate(lines):
        label_probe = line.strip()
        if not label_probe:
            continue
        metric = None
        if _REVENUE.search(label_probe) and not re.search(r"other\s+(?:operating\s+)?income", label_probe, re.I):
            metric = "revenue"
        elif _PAT_NAME.search(label_probe) and not _PAT_NOT.search(label_probe):
            metric = "pat"
        elif _EPS.search(label_probe) and any(_EPS_CONTEXT.search(lines[j]) for j in range(max(0, i - 6), i + 1)):
            metric = "eps"
        if metric is None:
            continue
        nums = numbers_on(line)
        first = next((k for k, (_, fig) in enumerate(nums) if fig), None)
        if first is None:
            continue
        # a line with several metrics' words keeps to its first figure onwards
        figures = [v for v, fig in nums[first:] if fig]
        # the label is what stands before the first figure
        start = next((m.start() for m, (_, fig) in zip(_NUMBER.finditer(line), nums) if fig), 0)
        label = line[:start].strip()
        # basis
        basis = _basis_above(lines, i)
        if basis is None and not consolidated_anywhere:
            basis = STANDALONE
        unit = unit_before(text, offsets[i])
        # header: the nearest line above with two or more dates
        header = next((b for b in range(i - 1, max(-1, i - HEADER_LOOKBACK), -1) if len(_dates_in(lines[b])) >= 2), None)
        row = Row(metric, label, basis, unit, figures, None, [], set(), page)
        if header is None:
            row.why = "no header with the period dates above the row"
            rows.append(row)
            continue
        dates = _dates_in(lines[header])
        row.dates = dates
        wide = "\n".join(lines[max(0, header - GROUP_LINES_ABOVE): min(i, header + 2)])
        row.group_words = {m.lastgroup for m in _GROUP.finditer(wide)}
        if len(figures) != len(dates):
            row.why = f"{len(figures)} figures on the row but {len(dates)} dates in the header (a cell may be missing)"
            rows.append(row)
            continue
        kinds = None
        for above in range(GROUP_LINES_ABOVE, -1, -1):   # a title line above may add group words: try fewer lines
            region = "\n".join(lines[max(0, header - above): min(i, header + 2)])
            kinds = _groups(region, dates)
            if kinds is not None:
                break
        if kinds is not None:
            row.columns = list(zip(kinds, dates))
        else:
            row.why = "the header's group words (quarter, year) do not tell each date's kind"
        rows.append(row)
    return rows


def read_document(payload: bytes, ocr: bool = True, max_ocr_pages: int = 6) -> tuple[list[Row] | None, str]:
    """(rows, why none) of the metric rows in a results PDF, read with the pipeline's own ``Document``."""
    ocr_fn = figure_fn = None
    if ocr:
        from .ocr import available, page_reader, recognise
        ocr_fn = page_reader(None)       # local OCR only; never the vision route (an AI call)
        figure_fn = recognise if available() else None
    doc = Document(payload, ocr=ocr_fn, max_ocr_pages=max_ocr_pages, figure_reader=figure_fn)
    try:
        if doc.error:
            return None, doc.error[:100]
        if not doc.page_count:
            return None, "no pages"
        texts: dict[int, str] = {}
        for i in range(doc.page_count):
            layer = doc.page_text(i, figures=False)
            if re.search(r"months?\s+ended|quarter|year\s+ended", layer, re.I) or doc.is_scanned(i):
                texts[i] = layer
            if len(texts) >= MAX_PAGES:
                break
        if not texts:
            return None, "no page names a quarter or year ended"
        consolidated_anywhere = any(_CONS.search(t) for t in texts.values())
        rows: list[Row] = []
        for i, layer in texts.items():
            text = doc.page_text(i)       # a page of figures is read with OCR first, as the pipeline reads it
            if not any(len(_dates_in(line)) >= 2 for line in text.splitlines()):
                continue
            rows += parse_page(text, i + 1, consolidated_anywhere or bool(_CONS.search(text)))
        if doc.ocr_error is not None and not rows:
            return None, "OCR failed"
        return rows, "" if rows else "no results row (revenue, profit or EPS with its figures) found"
    finally:
        doc.close()


# --- the figure of one pair -----------------------------------------------------------------------------------------

def target_column(period: str) -> tuple[str, date] | None:
    if period.startswith("FY") and period[2:].isdigit():
        return "year", date(2000 + int(period[2:]), 3, 31)
    end = quarter_end(period)
    return ("quarter", end) if end else None


def figure_for(rows: list[Row], period: str, metric: str, basis: str | None) -> dict:
    """{"values": [(value, label, page)], "unsure": why} for the period's column of the metric on the basis."""
    target = target_column(period)
    if target is None:
        return {"values": [], "unsure": "", "found": 0, "reason": f"no column for the period {period}"}
    values: list[tuple[float, str, int]] = []
    unsure: list[str] = []
    seen = 0
    for r in rows:
        if r.metric != metric:
            continue
        seen += 1
        if r.basis is None or (basis and r.basis != basis):
            if r.basis is None and basis:
                unsure.append(f"p{r.page}: the table's basis is not told")
            continue
        if not any(d == target[1] for d in r.dates):
            continue
        if r.columns is None:
            # kinds not told: one date only in the header, and the header names the kind of the period
            if r.dates.count(target[1]) == 1 and len(r.figures) == len(r.dates) and target[0] in r.group_words:
                index = r.dates.index(target[1])
            else:
                unsure.append(f"p{r.page}: {r.why}")
                continue
        else:
            matching = [k for k, c in enumerate(r.columns) if c == target]
            if len(matching) != 1:
                unsure.append(f"p{r.page}: {len(matching)} columns for {target[0]} ended {target[1]}")
                continue
            index = matching[0]
        if metric != "eps" and r.unit is None:
            unsure.append(f"p{r.page}: no unit declared above the row")
            continue
        value = r.figures[index] if metric == "eps" else r.figures[index] / r.unit
        values.append((value, r.label[:60], r.page))
    return {"values": values, "unsure": "; ".join(dict.fromkeys(unsure)), "found": seen}


def _same_reading(a: float, b: float) -> bool:
    """Two printed readings of one figure: within half a unit of a coarser printed precision (120.5 and 120.48 Cr, EPS 1.23
    and 1.2), or 0.05% (a figure printed in whole crore beside one to a decimal). Tighter than the cross-check's 1 Cr floor."""
    return abs(a - b) <= max(0.051, 0.0005 * max(abs(a), abs(b)))


def verdict_of(values: list[tuple[float, str, int]], ours: float | None, theirs: float | None, xbrl: float | None,
               metric: str) -> tuple[str, list[str], float | None, str]:
    """(verdict, matches, the figure used, its label) for proven PDF figures against the three values. Proven rows that
    disagree with each other (a segment total, "Total income" beside revenue) are no verdict: ``pdf_unsure``, so one row that
    happens to agree never confirms a figure (independent review, 26 Oct 2026)."""
    distinct: list[float] = []
    for value, _, _ in values:
        if not any(_same_reading(d, value) for d in distinct):
            distinct.append(value)
    if len(distinct) > 1:
        shown = ", ".join(f"{v:g}" for v in distinct[:4])
        return "pdf_unsure", [], None, f"conflicting rows: {shown}"
    best = None
    for value, label, _ in values:
        matches = []
        if ours is not None and ours_close(ours, value, metric):
            matches.append("ours")
        if theirs is not None and _close(value, theirs, metric):
            matches.append("screener")
        if xbrl is not None and ours_close(xbrl, value, metric):
            matches.append("xbrl")
        if matches:
            best = (value, label, matches)
            break
    if best is None:
        value, label, _ = values[0]
        return "pdf_matches_none", [], value, label
    value, label, matches = best
    names = set(matches)
    if "ours" in names:
        v = "pdf_matches_ours"
    elif "screener" in names and "xbrl" not in names:
        v = "pdf_matches_screener"
    else:
        v = "pdf_matches_xbrl"
    return v, matches, value, label


# --- finding and reading the PDFs ----------------------------------------------------------------------------------

def candidate_filings(filings: list, period: str) -> list:
    """The results filings among a company's announcements for the period's window, best first."""
    out = []
    for f in filings:
        if not f.pdf_url:
            continue
        words = f"{f.subject} {f.headline}"
        if not _RESULTS.search(words) or _NOT_RESULTS.search(f"{f.headline}"):
            continue
        out.append(f)
    out.sort(key=lambda f: ("financial result" not in (f.subject or "").lower(),
                            "newspaper" in (f.headline or "").lower(), f.filed_at))
    return out


class Sources:
    """The announcement lists and PDFs of the run, each fetched and read once."""

    def __init__(self, nse, ocr: bool = True):
        self.nse, self.ocr = nse, ocr
        self.lists: dict[tuple[str, str], list | str] = {}      # (symbol, period) -> filings or the reason none
        self.docs: dict[str, tuple[list[Row] | None, str]] = {}
        self.calls = {"lists": 0, "pdfs": 0}

    def filings(self, symbol: str, period: str) -> list | str:
        key = (symbol, period)
        if key not in self.lists:
            target = target_column(period)
            if target is None:
                self.lists[key] = f"no period end for {period}"
            else:
                try:
                    self.calls["lists"] += 1
                    listed = self.nse.announcements(target[1] + timedelta(days=1), target[1] + timedelta(days=WINDOW_DAYS), symbol)
                    found = candidate_filings(listed, period)
                    self.lists[key] = found or f"no results filing with a PDF in NSE's announcements for {period}"
                except SourceBlockedError:
                    raise
                except Exception as exc:   # noqa: BLE001 - one company's list failing is a reason, not a stop
                    self.lists[key] = f"announcement list unavailable ({type(exc).__name__})"
        return self.lists[key]

    def rows(self, url: str) -> tuple[list[Row] | None, str]:
        if url not in self.docs:
            try:
                self.calls["pdfs"] += 1
                data = self.nse.fetch(url, max_bytes=MAX_PDF_BYTES)
            except SourceBlockedError:
                raise
            except AttachmentTooLarge:
                self.docs[url] = (None, "PDF too large")
            except AttachmentError as exc:
                self.docs[url] = (None, f"download failed ({str(exc)[:60]})")
            except Exception as exc:   # noqa: BLE001
                self.docs[url] = (None, f"download failed ({type(exc).__name__})")
            else:
                if not data:
                    self.docs[url] = (None, "NSE serves no file (404)")
                else:
                    try:
                        self.docs[url] = read_document(data, ocr=self.ocr)
                    except Exception as exc:   # noqa: BLE001
                        self.docs[url] = (None, f"unreadable ({type(exc).__name__})")
        return self.docs[url]


def referee_pair(src: Sources, row: dict) -> dict:
    """The verdict fields for one open pair of the screener-referee CSV."""
    period, metric, symbol = row["period"], row["metric"], row["symbol"]
    out = {"pdf_verdict": "pdf_unreadable", "pdf_value": None, "pdf_label": "", "pdf_url": "", "matches": "", "reason": ""}
    ours, theirs, xbrl = _num(row.get("memory_value")), _num(row.get("screener_value")), _num(row.get("official_value"))
    if ours is None or theirs is None:
        out["reason"] = "the row has no figure on one side"
        return out
    listed = src.filings(symbol, period)
    if isinstance(listed, str):
        out["reason"] = listed
        return out
    reasons, unsure = [], []
    for f in listed[:MAX_CANDIDATES]:
        rows, why = src.rows(f.pdf_url)
        if rows is None:
            reasons.append(why)
            continue
        got = figure_for(rows, period, metric, row.get("basis") or None)
        if got["values"]:
            v, matches, value, label = verdict_of(got["values"], ours, theirs, xbrl, metric)
            if v == "pdf_unsure":
                out.update(pdf_verdict=v, pdf_url=f.pdf_url, reason=label)
                return out
            out.update(pdf_verdict=v, pdf_value=value, pdf_label=label, pdf_url=f.pdf_url, matches="|".join(matches))
            return out
        if got["unsure"]:
            unsure.append(got["unsure"])
            out["pdf_url"] = f.pdf_url
        elif not got["found"]:
            reasons.append("no row for the metric")
        else:
            reasons.append(f"no {metric} row of the {period} column on the basis")
    if unsure:
        out.update(pdf_verdict="pdf_unsure", reason="; ".join(dict.fromkeys(unsure))[:200])
    else:
        out["reason"] = "; ".join(dict.fromkeys(reasons))[:200] or "no results PDF read"
    return out


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# screener_explain.TO_PDF: the explain verdicts that still need the PDF (a row the explain run cut, not_run, included)
EXPLAIN_TO_PDF = ("unexplained", "eps_owners_vs_total", "not_run")


def open_pairs(rows: list[dict], explained: bool = False) -> list[dict]:
    """The pairs still open. With ``explained`` the rows are those of ``screener-explain``'s explained.csv: the ones it left
    ``unexplained`` (our figure equals the official file and no corporate action or later file accounts for screener's) plus
    the usual open verdicts it passed through; the rows it explained are left out."""
    def open_(r: dict) -> bool:
        return r.get("verdict") in OPEN_VERDICTS or (explained and r.get("explain_verdict") in EXPLAIN_TO_PDF)
    return [r for r in rows if open_(r) and r.get("metric") and r.get("period") and r.get("symbol")]


SAMPLE_METRICS = ("revenue", "pat")   # EPS left out: screener restates old EPS for bonuses and splits, the PDF prints it as filed


def sample_pairs(rows: list[dict], n: int, seed: int = 26) -> list[dict]:
    """A seeded random sample of ``n`` pairs the XBRL step called ``ours_matches_official``, half revenue and half profit
    (owner, 26 Oct 2026: memory came from NSE's own files, so "ours equals the file" is no check; the PDF is the second,
    independent source). The referee CSV holds only pairs where screener disagreed, so the rate at which the PDF disagrees
    with the file here is an upper bound of the file's error rate, not the rate over all figures."""
    import random

    if n <= 0:
        raise ValueError("--sample takes a number above 0")
    rng = random.Random(seed)
    out: list[dict] = []
    for i, metric in enumerate(SAMPLE_METRICS):
        pool = sorted((r for r in rows if r.get("verdict") == "ours_matches_official" and r.get("metric") == metric
                       and r.get("period") and r.get("symbol")
                       and r.get("explain_verdict", "unexplained") in EXPLAIN_TO_PDF),   # an explained row is no sample
                      key=lambda r: (r["symbol"], r["period"]))
        want = n // len(SAMPLE_METRICS) + (1 if i < n % len(SAMPLE_METRICS) else 0)
        if len(pool) < want:
            log.warning("sample: only %d %s pairs to draw from, %d wanted", len(pool), metric, want)
        out += rng.sample(pool, min(want, len(pool)))
    return out


def load_csv(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def run(nse, rows: list[dict], limit: int | None = None, time_budget: float | None = None, ocr: bool = True,
        clock=time.monotonic, sample: int = 0, seed: int = 26, explained: bool = False) -> dict:
    """Referee the open pairs among the screener-referee ``rows``, company by company; ``limit`` caps the pairs read (a
    company is finished once started); the rest are ``not_run``. With ``sample`` the pairs are instead a seeded random
    sample of that many pairs where memory already equals the XBRL file (``sample_pairs``); with ``explained`` the rows are
    screener-explain's and its ``unexplained`` ones are taken too (``open_pairs``)."""
    pairs = sample_pairs(rows, sample, seed) if sample else open_pairs(rows, explained)
    pool = sum(r.get("verdict") == "ours_matches_official" and r.get("metric") in SAMPLE_METRICS for r in rows) if sample else 0
    by_company: dict[tuple[str, str], list[dict]] = {}
    for r in pairs:
        by_company.setdefault((r["symbol"], r.get("basis") or ""), []).append(r)
    src = Sources(nse, ocr)
    started, done, blocked, out_of_time = clock(), 0, False, False
    results: list[dict] = []

    def not_run(r: dict, why: str) -> dict:
        return {**r, "pdf_verdict": "not_run", "reason": why, "pdf_value": None, "pdf_label": "", "pdf_url": "", "matches": ""}

    for (symbol, _basis), items in by_company.items():
        if not blocked and time_budget is not None and clock() - started > time_budget:
            out_of_time = True
        why = "blocked" if blocked else "time budget" if out_of_time else "limit" if limit is not None and done >= limit else ""
        if why:
            results += [not_run(r, why) for r in items]
            continue
        for r in items:
            if blocked:
                results.append(not_run(r, "blocked"))
                continue
            try:
                results.append({**r, **referee_pair(src, r)})
                done += 1
            except SourceBlockedError as exc:
                blocked = True
                log.warning("NSE refused (%s): stopping the PDF referee", exc)
                results.append(not_run(r, "blocked"))
    summary = summarise(results, src.calls, len(by_company), blocked, out_of_time, len(rows) - len(pairs))
    if sample:
        summary["sample"] = {"drawn": len(pairs), "pool": pool, "seed": seed}
    return summary


def summarise(results: list[dict], calls: dict, companies: int, blocked: bool = False, out_of_time: bool = False,
              left_out: int = 0) -> dict:
    by_before: dict[str, Counter] = {}
    by_metric: dict[str, Counter] = {}
    reasons: Counter = Counter()
    for r in results:
        by_before.setdefault(r.get("verdict", ""), Counter())[r["pdf_verdict"]] += 1
        by_metric.setdefault(r["metric"], Counter())[r["pdf_verdict"]] += 1
        if r["pdf_verdict"] in ("pdf_unreadable", "pdf_unsure", "not_run"):
            reasons[_short_reason(r.get("reason", ""))] += 1
    return {"pairs": len(results), "companies": companies, "left_out": left_out,
            "calls": {"announcement_lists": calls["lists"], "pdfs": calls["pdfs"]}, "blocked": blocked,
            "out_of_time": out_of_time, "verdicts": dict(Counter(r["pdf_verdict"] for r in results)),
            "by_xbrl_verdict": {k: dict(v) for k, v in by_before.items()},
            "by_metric": {k: dict(v) for k, v in by_metric.items()}, "reasons": dict(reasons.most_common(15)),
            "rows": results}


def _short_reason(reason: str) -> str:
    return re.sub(r"Q[1-4]FY\d{2}|FY\d{2}|p\d+: |\d+", "<n>", reason.split("; ")[0])[:100] or "unspecified"


CSV_HEADER = ("scrip,symbol,basis,period,metric,class,memory_value,screener_value,official_value,verdict,pdf_verdict,"
              "pdf_value,matches,pdf_label,pdf_url,reason").split(",")


def _cell(v) -> str:
    return "" if v is None else f"{v:g}" if isinstance(v, float) else str(v)


def to_csv(summary: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for r in summary["rows"]:
        writer.writerow([_cell(r.get(k)) for k in CSV_HEADER])
    return buffer.getvalue()


def to_json(summary: dict) -> str:
    return json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=1) + "\n"


def render(summary: dict) -> str:
    kind = "sampled pairs (memory equals the file)" if summary.get("sample") else "open pairs"
    lines = [f"pdf referee (the filing PDF, read only): {summary['pairs']} {kind}, {summary['companies']} companies, "
             f"{summary['calls']['announcement_lists']} announcement lists, {summary['calls']['pdfs']} PDFs"]
    lines += [f"  {v:24}{summary['verdicts'].get(v, 0)}" for v in VERDICTS]
    if summary["blocked"]:
        lines.append("stopped: NSE refused the session")
    if summary["out_of_time"]:
        lines.append("stopped: time budget")
    return "\n".join(lines)


def to_markdown(summary: dict, date_text: str) -> str:
    sample = summary.get("sample")
    intro = ((f"Read only: a seeded random sample (seed {sample['seed']}) of {sample['drawn']} of the {sample['pool']} revenue and "
              "profit pairs where memory equals NSE's results XBRL, each checked against the filing's own PDF. The referee's input "
              "holds only pairs where screener disagreed, so the share where the PDF disagrees with the file is an upper bound "
              "of the file's error rate, not its rate over all figures.") if sample else
             "Read only: the filing's own PDF decides each pair the XBRL step left open (verdict neither, no_file or "
             "screener_matches_official).")
    out = [f"# PDF referee, {date_text}", "",
           intro + " A figure counts only when its column, basis and unit are proven on the page and the proven rows agree "
           "with each other; otherwise it is `pdf_unsure`. Memory is not written and no card changes.", "",
           f"{summary['pairs']} {'sampled' if sample else 'open'} pairs, {summary['companies']} "
           f"companies, {summary['calls']['announcement_lists']} announcement lists and {summary['calls']['pdfs']} PDFs fetched.", ""]
    if summary["blocked"] or summary["out_of_time"]:
        out += ["The run stopped early (" + ("NSE refused the session" if summary["blocked"] else "time budget")
                + "); the rest is `not_run`.", ""]
    sep = "|---|" + "---|" * len(VERDICTS)

    def table(title: str, groups: dict) -> list[str]:
        rows = [f"## {title}", "", "| Group | " + " | ".join(VERDICTS) + " |", sep]
        rows += [f"| {k} | " + " | ".join(str(v.get(x, 0)) for x in VERDICTS) + " |" for k, v in sorted(groups.items())]
        return rows + [""]

    out += table("PDF verdict per XBRL verdict", summary["by_xbrl_verdict"]) + table("PDF verdict per metric", summary["by_metric"])
    out += ["## Why unsure, unreadable or not run", ""] + [f"- {k}: {n}" for k, n in summary["reasons"].items()] + [""]
    out += ["Every pair, with the PDF's figure, its row label and the file, is in the CSV artifact.", ""]
    return "\n".join(out)
