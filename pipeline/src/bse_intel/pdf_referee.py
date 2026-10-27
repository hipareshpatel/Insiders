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

Added 26 Oct 2026 (TODO 91; the first trials settled 1 pair of 20):

- lenders: a statement's revenue row is "Total revenue from operations" / "Revenue from operations", else (a bank) "Interest
  earned" / "Total interest income", else "Total income" (rank 0, 1, 2; only the best rank of one table is kept, so a sub-line
  such as "I. Interest Income" is never the revenue). A figure that matches nothing and came from "Total income" alone is
  ``pdf_unsure``: the line includes other income, so a difference is a definition.
- a text layer that runs column by column (all labels, then all figures) or whose figures sit a point or two off their
  label's baseline: the page's words are put into rows by position (``ocr.positioned_lines``, the clustering the OCR text
  uses) and read as a second reading of the page; the one with more proven rows is kept.
- the column of a period: a header date is matched to a figure by position when the row lacks a cell (``Row.aligned``); the
  kind of each column comes from the header's group words or, when they do not tell it (a misread "Quarter Ended"), from the
  standard Indian layout: quarter x3 and year x2 (Q4); quarter x3, half year or nine months x2, year (Q2, Q3); quarter x3 and
  year (Q1). It is accepted only when the header's own dates fit it exactly and no group word contradicts it.
- the basis words are matched with a spelling tolerance ("CONSOUDATED" in a text layer is consolidated).
- a figure printed without the decimals its row's other figures have ("5,081,67") is a garbled layer: its column is unsure.

Verdicts: ``pdf_matches_ours``, ``pdf_matches_screener``, ``pdf_matches_xbrl`` (a figure that agrees with the XBRL
referee's official value, and not ours), ``pdf_matches_none`` (a proven figure that agrees with no value), ``pdf_unsure`` (a
figure on the page but not provably the right column, basis or unit) and ``pdf_unreadable`` (no PDF, not downloaded, no
text, no results row; the reason in ``reason``). ``not_run`` marks pairs cut by ``--limit`` or the time budget. When
several values agree, ``matches`` lists them all.
"""

from __future__ import annotations

import csv
import difflib
import io
import json
import logging
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from .bse import AttachmentError, AttachmentTooLarge
from .extract import _MUPDF, Document, upright_text
from .grounding import _PER_CRORE, unit_before
from .memory_gaps import quarter_end
from .metrics import CONSOLIDATED, STANDALONE
from .nse import FileCapReached, SourceBlockedError
from .periods import explicit_date
from .screener_crosscheck import _close
from .screener_referee import _DATE, _NUMBER, numbers_on
from .screener_xbrl_referee import ours_close

log = logging.getLogger(__name__)

OPEN_VERDICTS = ("neither", "no_file", "screener_matches_official")
VERDICTS = ("pdf_matches_ours", "pdf_matches_screener", "pdf_matches_xbrl", "pdf_matches_none", "pdf_unsure",
            "pdf_unreadable", "not_run")
# Added by the readers ensemble (PDF_READERS other than "native", pdf_readers.py): a disagreement between readers stays open,
# and OCR readers of two engines agreeing on a page with no text layer is a lead, not a verdict. Never set by the default path.
EXTRA_VERDICTS = ("pdf_disagree", "pdf_scanned_lead")
MAX_CANDIDATES = 4          # results PDFs tried for one period
MAX_PAGES = 12              # candidate table pages read in one PDF
WINDOW_DAYS = 120           # a period's results are filed within this many days after its end
MAX_PDF_BYTES = 40_000_000
HEADER_LOOKBACK = 100
GROUP_LINES_ABOVE = 4       # lines above the date line searched for the group words ("Quarter ended")

_GROUP = re.compile(r"(?P<half>half[\s-]*year(?:ly)?|six\s+months|6\s+months)|(?P<nine>nine\s+months|9\s+months)"
                    r"|(?P<year>year\s+ended|twelve\s+months|12\s+months|\byear\b|\bannual\b)"
                    r"|(?P<quarter>quarter|three\s+months|3\s+months)", re.I)
_CONS = re.compile(r"\bconsolidated\b", re.I)
_ALONE = re.compile(r"\bstand[- ]?alone\b", re.I)
_LONG_WORD = re.compile(r"[A-Za-z]{8,}")
_TITLE = re.compile(r"results|statement|financial|profit|particulars", re.I)
_RESULTS = re.compile(r"financial\s+results?|outcome\s+of\s+(?:the\s+)?board|\bresults?\b", re.I)
_NOT_RESULTS = re.compile(r"intimation|trading\s+window|earnings?\s+call|conference\s+call|presentation|transcript|investor|"
                          r"analyst|schedule|press\s+release|clarification|copy\s+of\s+newspaper", re.I)

_REVENUE = re.compile(r"(?:revenue|income|sales)\s+from\s+operations|net\s+sales|total\s+interest\s+earned|"
                      r"^\W*(?:\d+\W+)?interest\s+earned", re.I)
# the revenue line by rank, best first: the top line, a bank's interest earned, then a lender's total income
_INTEREST_TOP = re.compile(r"^\W*(?:\d+\W+)?(?:total\s+)?interest\s+earned\b(?!\s+(?:on|from|by)\b)|total\s+interest\s+income", re.I)
# a bank's sub-line of interest earned: "(a) Interest earned on advances", "Interest earned on investments" (never the total)
_INTEREST_SUB = re.compile(r"^\W*(?:\(?[a-d]\)|\(?[ivx]+\)|[a-d]\.|[ivx]+\.)\s*(?:total\s+)?interest\s+(?:earned|income)|"
                           r"^\W*(?:\d+\W+)?interest\s+earned\s+(?:on|from|by)\b", re.I)
_TOTAL_INCOME = re.compile(r"^\W*(?:[\divx]+\W+|[a-d]\W+)?total\s+income\b(?!\s+(?:from|tax))", re.I)
_PAT_NAME = re.compile(r"^\W*(?:[ivx]+\W+|\d+\W+|[a-d]\)\s*)?(?:net\s+|total\s+)?(?:profit|loss)\b[^\d]{0,40}?"
                       r"(?:for\s+the\s+(?:period|year|quarter)|after\s+tax|after\s+taxes)", re.I)
# the same with a letter before the label ("J. Net Profit/(Loss) for the period (H-I)": Union Bank's lettered lines); 27 Oct 2026, PDF_ROW_FIXES
_PAT_NAME_LETTERED = re.compile(_PAT_NAME.pattern.replace(r"|[a-d]\)\s*)?", r"|[a-d]\)\s*|[a-z][.)]\s*)?", 1), re.I)
_PAT_TOTAL = re.compile(r"for\s+the\s+(?:period|year|quarter)", re.I)
# a "for the period" line printed as the line above less another ("IX Profit for the period / year (VII-VIII)", VIII being the share
# of non-controlling interest): the owners' share, not the bottom line the tie-break below looks for (SPANDANA consolidated: 216.32
# against the profit after tax of 216.33); with PDF_ROW_FIXES such a line is no tie-break and two rows that differ stay a conflict
_PAT_LESS = re.compile(r"\(\s*[\w.]+\s*[-\u2013]\s*[\w.]+\s*\)")
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
    rank: int = 0                          # revenue only: 0 revenue from operations, 1 interest earned, 2 total income
    aligned: list[float | None] | None = None   # the figure under each header date, when the row lacks a cell (by position)
    odd: set[int] | None = None            # indexes of figures without the decimals their siblings print (a garbled layer)
    key: tuple | None = None               # (header line, basis): the table the row belongs to
    unproven: str = ""                     # why the row cannot be trusted at all (figures not on the label's baseline)


# --- reading a page -----------------------------------------------------------------------------------------------

_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
# the page's date pattern with the noise OCR puts after a day ("31{t Dec, 2023", "31* March, 2024", "31st March, 2024")
_DATE_LOOSE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]20\d{2}\b|\b\d{1,2}(?:st|nd|rd|th|[^\w\s]{1,2}t?)?[ -]+" + _MONTH
                         + r",?[ -]+20\d{2}\b|\b" + _MONTH + r" \d{1,2},? 20\d{2}\b", re.I)
_DAY_NOISE = re.compile(r"(?<=\d)(?:st|nd|rd|th|[^\w\s]{1,2}t?)(?=[ -]+[A-Za-z])", re.I)
# the same with a two-digit year after a day and a month name or number ("31-Mar-24", "31Mar-23", "31.03.24"); F215, PDF_DATES_2DIGIT
_DATE_LOOSE_2 = re.compile(_DATE_LOOSE.pattern + r"|(?<![\w./,])\d{1,2}(?:st|nd|rd|th)?[ -]*" + _MONTH + r"[ ,-]*\d{2}(?![\w.,]?\d)(?!(?<=20)\s(?:1[5-9]|2\d)\b(?![-./]))"
                           r"|(?<![\w./,-])\d{1,2}[./-]\d{1,2}[./-]\d{2}(?![\w.,/-]?\d)(?!(?<=20)\s(?:1[5-9]|2\d)\b(?![-./]))", re.I)


def _row_fixes() -> bool:
    from .settings import get_settings
    return get_settings().pdf_row_fixes


def _two_digit() -> bool:
    from .settings import get_settings
    return get_settings().pdf_dates_2digit


def _date_of(text: str, two_digit: bool = False) -> date | None:
    return explicit_date(re.sub(r"[ ]{2,}", " ", _DAY_NOISE.sub("", text)), two_digit)


def _dates_in(line: str) -> list[date]:
    two = _two_digit()
    return [d for m in (_DATE_LOOSE_2 if two else _DATE_LOOSE).finditer(line) if (d := _date_of(m[0], two))]


_MARCH_YEAR = re.compile(r"year\s+ended\W{0,12}(?:on\W+)?(?:\d{1,2}\W{0,3}(?:st|nd|rd|th|t)?\W{0,3}mar|mar|\d{1,2}[./-]0?3[./-])", re.I)
_UNCONS = re.compile(r"\bun-?consolidated\b", re.I)


def _edits(a: str, b: str) -> int:
    """Levenshtein distance of two short words."""
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        new = [i]
        for j, cb in enumerate(b, 1):
            new.append(min(row[j] + 1, new[j - 1] + 1, row[j - 1] + (ca != cb)))
        row = new
    return row[-1]


def _names(text: str, basis: str) -> bool:
    """The text names the basis: the word itself, or a text layer's small misspelling of the whole word ("CONSOUDATED": at
    most two edits, same first and last three letters, so "Consolidating", "Consolidate", "Deconsolidated" are not it).
    "Unconsolidated" is a standalone statement."""
    if basis == "consolidated" and _CONS.search(text):
        return True
    if basis == "standalone" and (_ALONE.search(text) or _UNCONS.search(text)):
        return True
    for w in _LONG_WORD.findall(text):
        w = w.lower()
        if w[:3] == basis[:3] and w[-3:] == basis[-3:] and w != basis and _edits(w, basis) <= 2:
            return True
    return False


def _words_basis(words: str) -> str | None:
    cons, alone = _names(words, "consolidated"), _names(words, "standalone")
    return CONSOLIDATED if cons and not alone else STANDALONE if alone and not cons else None


def _basis_above(lines: list[str], at: int) -> str | None:
    """The basis of the nearest title above ``at`` that names exactly one."""
    for back in range(at - 1, max(-1, at - 120), -1):
        line = lines[back]
        if _TITLE.search(line) and (found := _words_basis(line)):
            return found
    return None


def _basis_above_boxed(lines: list[str], at: int) -> tuple[str | None, bool]:
    """``_basis_above``, but a short heading line between the row and the title that names the other basis ("STANDALONE
    INFORMATION" at the top of a table on a page titled "CONSOLIDATED ... STATEMENT OF ASSETS AND LIABILITIES", EMKAY p12) takes
    the table out of the title's basis: no basis, so no figure (27 Oct 2026, PDF_ROW_FIXES). A heading that names the title's own basis
    changes nothing, and a heading with no title above it is not used. Returns (basis, contested): a contested table is never
    given the "no word means standalone" default either."""
    heading = None
    for back in range(at - 1, max(-1, at - 120), -1):
        line = lines[back]
        if _TITLE.search(line) and (found := _words_basis(line)):
            return (None, True) if heading is not None and heading != found else (found, False)
        if heading is None and len(line.strip()) <= 60 and not any(f for _, f in numbers_on(line)):
            heading = _words_basis(line)
    return None, False


def _groups(region: str, dates: list[date]) -> list[str] | None:
    """The kind of each of the header's dates (quarter, half, nine, year), or None when the words do not say."""
    events: list[tuple[int, str, object]] = []
    for m in _GROUP.finditer(region):
        events.append((m.start(), "g", m.lastgroup))
    two = _two_digit()
    for m in (_DATE_LOOSE_2 if two else _DATE_LOOSE).finditer(region):
        if (d := _date_of(m[0], two)):
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


def _gap_months(a: date, b: date) -> int:
    return (a.year - b.year) * 12 + a.month - b.month


def _pattern_kinds(dates: list[date], march_year_end: bool = False) -> list[str] | None:
    """The kind of each header date by the standard layout of Indian results, when the dates fit it exactly, else None.

    Q4: quarter, quarter, quarter, year, year (current quarter, the one before, the year before; the year, the year before).
    Q2 / Q3: quarter x3, then the half year (nine months) to date and its year-ago twin, then the last year.
    Q1: quarter x3 and the last year (the same date as the quarter before). The dates alone prove it: the first is a quarter end,
    the second one quarter before it, the third a year before it, and the tail repeats them as the layout says. The four and
    five column layouts are only read when the page says the year ends in March ("year ended 31 March"): a company with another
    year end can print the same dates as nine-month columns, so without that word they stay unsure."""
    n = len(dates)
    if n not in (4, 5, 6) or (n < 6 and not march_year_end):
        return None
    d0, d1, d2 = dates[:3]
    if d0.month not in (3, 6, 9, 12) or d0.day < 28 or _gap_months(d0, d1) != 3 or _gap_months(d0, d2) != 12:
        return None
    if n == 5:
        return ["quarter"] * 3 + ["year"] * 2 if d0.month == 3 and dates[3] == d0 and dates[4] == d2 else None
    if n == 4:
        return ["quarter"] * 3 + ["year"] if d0.month == 6 and dates[3] == d1 and d1.month == 3 else None
    if d0.month not in (9, 12) or dates[3] != d0 or dates[4] != d2 or dates[5].month != 3 \
            or _gap_months(d0, dates[5]) != d0.month - 3:
        return None
    return ["quarter"] * 3 + ["half" if d0.month == 9 else "nine"] * 2 + ["year"]


def _revenue_rank(label: str) -> int | None:
    """0 for revenue from operations, 1 for a bank's interest earned (the total line), 2 for total income, 3 for a sub-line of
    interest earned (never a figure: unsure when it stands alone); None when it is none of them."""
    if re.search(r"other\s+(?:operating\s+)?income", label, re.I):
        return None
    if _INTEREST_SUB.search(label):
        return 3
    if _REVENUE.search(label) and not _INTEREST_TOP.search(label):
        return 0
    if _INTEREST_TOP.search(label):
        return 1
    return 2 if _TOTAL_INCOME.search(label) else None


def _centres(words: list[tuple], keep) -> list[tuple[float, str]]:
    return [((x0 + x1) / 2, w) for x0, x1, w, *_ in words if keep(w)]


def _align(row_words: list[tuple], header_words: list[tuple], dates: list[date],
           figures: list[float]) -> list[float | None] | None:
    """The figure under each header date by position, when the row has fewer cells than the header has dates (a nil cell
    printed as nothing). Only when each date is one word, each figure is one word and every figure sits clearly under one date,
    in order; else None."""
    two = _two_digit()
    hdr = _centres(header_words, lambda w: bool((_DATE_LOOSE_2 if two else _DATE).fullmatch(w)) and explicit_date(w, two) is not None)
    figs = [(c, w) for c, w in _centres(row_words, lambda w: True) if (n := numbers_on(w)) and len(n) == 1 and n[0][1]]
    if len(hdr) != len(dates) or len(figs) != len(figures) or len(hdr) < 2:
        return None
    gap = min(b[0] - a[0] for a, b in zip(hdr, hdr[1:]))
    if gap <= 0:
        return None
    out: list[float | None] = [None] * len(dates)
    last = -1
    for (c, _w), value in zip(figs, figures):
        nearest = min(range(len(hdr)), key=lambda k: abs(hdr[k][0] - c))
        if abs(hdr[nearest][0] - c) > 0.45 * gap or nearest <= last:
            return None
        out[nearest] = value
        last = nearest
    return out


_BARE_UNIT = re.compile(r"^(?:in\s+)?(?:\S{1,4}\s+)?(?:in\s+)?(crores?|crs?\.?|lakhs?|lacs?|millions?|mn|thousands?)(?![a-z])"
                        r"[^\w]*(?:except\b.*|\(.*)?$", re.I)


def _bare_unit(lines: list[str], header: int) -> float | None:
    """The unit when the page prints it alone on a short line near the header and OCR lost the currency sign before it
    ("crore", "< in crore", "(in lakhs)"), as figures per crore; None when no such line or when the lines name two units."""
    found = set()
    for line in lines[max(0, header - 8): header + 2]:
        probe = re.sub(r"^[^\w]+|[^\w.)]+$", "", line.strip())
        if len(probe) <= 40 and (m := _BARE_UNIT.match(probe)):
            found.add(_PER_CRORE.get(m[1].lower().rstrip("s.").rstrip("s")))
    return found.pop() if len(found) == 1 and None not in found else None


# A unit line the text layer or OCR garbled: junk or the lost rupee sign before "in", the unit word, a stray letter or two after it
# and a short tail ("(\" in crores unless otherwise stated)", "f{ in crorest", "Ct In Lakhs}"). Only crore, lakh, million and thousand
# are units (27 Oct 2026, PDF_ROW_FIXES); anything else, or two different units near the header, is no unit.
_GARBLED_UNIT = re.compile(r"^[^\w]{0,4}(?:[^\W\d_]{1,3}[^\w]{0,4})?(?:in|ln)\s+(crores?|lakhs?|lacs?|millions?|thousands?)[a-z]{0,2}(?![a-z])"
                           r"[^\w]*(?:(?:unless|except|other)\b[^\d]{0,40})?$", re.I)


def _garbled_units(lines: list[str], header: int) -> tuple[set, set]:
    """(the units named by garbled unit lines, the units named by the lines ``_bare_unit`` reads) near the header; a unit that
    is not in ``_PER_CRORE`` is None."""
    garbled, bare = set(), set()
    for line in lines[max(0, header - 8): header + 2]:
        probe = line.strip()
        if len(probe) <= 70 and (m := _GARBLED_UNIT.match(probe)):
            garbled.add(_PER_CRORE.get(m[1].lower().rstrip("s")))
        clean = re.sub(r"^[^\w]+|[^\w.)]+$", "", probe)
        if len(clean) <= 40 and (m := _BARE_UNIT.match(clean)):
            bare.add(_PER_CRORE.get(m[1].lower().rstrip("s.").rstrip("s")))
    return garbled, bare


def _garbled_unit(lines: list[str], header: int) -> float | None:
    """The unit when a garbled unit line is near the header and every unit line there names the same one, as figures per
    crore; None when there is no such line or two units are named (27 Oct 2026, PDF_ROW_FIXES)."""
    garbled, bare = _garbled_units(lines, header)
    units = garbled | bare
    return units.pop() if garbled and len(units) == 1 and None not in units else None


_DATE_TOKEN = re.compile(r"\d{1,2}\s?[./-]\s?\d{1,2}\s?[./-]\s?[\dOolI\]\[|]{1,4}(?!\d)")


def _with_extra_date(header: str, figures: int) -> str | None:
    """The header line with its last date token, which the text layer garbled ("31 .03.202]"), read again, when the row has one
    figure more than the header has dates and the line shows exactly one date-like token for each figure with only the last one
    unread: a trailing date column the layer lost, not a sub-total. The standard six-column layout (three quarters, the half year
    or nine months and its year-ago twin, then the last year end) says which date it is: 31 March of the first date's year; the
    token's own visible digits must agree ("31 .03.202" starts "2023"). None when the line is not that (F215, PDF_ROW_FIXES)."""
    tokens = list(_DATE_TOKEN.finditer(header))
    dates = _dates_in(header)
    if figures != 6 or len(tokens) != 6 or len(dates) != 5 or _dates_in(tokens[-1][0]):
        return None
    parts = re.findall(r"\d+", tokens[-1][0])
    d0 = dates[0]
    if len(parts) < 3 or (int(parts[0]), int(parts[1])) != (31, 3) or d0.month not in (9, 12) or len(parts[2]) < 3 \
            or not str(d0.year).startswith(parts[2]):
        return None
    return header[:tokens[-1].start()] + f"31.03.{d0.year}" + header[tokens[-1].end():]


def _odd_figures(line: str, start: int) -> set[int]:
    """Indexes of the row's figures printed without the decimals the others have ("5,081,67" for 5,081.67 in a garbled layer)."""
    nums = [m[0] for m, (_, fig) in zip(_NUMBER.finditer(line[start:]), numbers_on(line[start:])) if fig]
    decimals = [("." in n) for n in nums]
    if sum(decimals) < 3:
        return set()
    return {k for k, d in enumerate(decimals) if not d}


# the revenue total a lender prints as "Total (a)" under the heading "(a) Revenue from Operations" (VLS Finance), with the
# income total beside it as "Total Income (a+b)": the total of (a) is the revenue (27 Oct 2026, PDF_ROW_FIXES)
_TOTAL_A = re.compile(r"^\W*total\s*\(\s*a\s*\)", re.I)
_REVENUE_HEADING = re.compile(r"^\W*(?:(?:\(\s*\w+\s*\)|\w{1,4}\.?)\W*)?(?:total\s+)?revenue\s+from\s+operations\W*$", re.I)
_STEP_BREAK = re.compile(r"^\W*(?:\(\s*b\s*\)|total\b)", re.I)
# a sub-line printed with its own letter or roman number ("a. Fees and commission"), never the end of a wrapped label
_SUB_LINE = re.compile(r"^(?:[a-z]|[ivx]{2,4})[.)]\s")


def _revenue_heading_above(lines: list[str], at: int) -> bool:
    """A heading "(a) Revenue from Operations" with only sub-lines between it and line ``at`` (no other total, no "(b)" step)."""
    for back in range(at - 1, max(-1, at - 14), -1):
        line = lines[back].strip()
        if _REVENUE_HEADING.match(line):
            return True
        if _STEP_BREAK.match(line):
            return False
    return False


def parse_page(text: str, page: int, consolidated_anywhere: bool,
               positions: list[list[tuple]] | None = None, bad_lines: frozenset[int] | set[int] = frozenset()) -> list[Row]:
    """The metric rows (revenue, pat, eps) of one page's text, each with the column proof it has. ``positions`` are the words
    of each line of ``text`` with their left and right edges, when the text was built from word positions; ``bad_lines`` are
    the lines whose figures were not nearer their label's baseline than the next label's: those rows are unproven."""
    lines = text.splitlines()
    if positions is not None and len(positions) != len(lines):
        positions = None
    if positions is not None:
        positions = [list(w) for w in positions]
    rows: list[Row] = []
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    lines = list(lines)
    for i in range(len(lines) - 1):      # a label wrapped onto two lines ("Revenue from" / "operations 120.50 ..."): one line
        a, b = lines[i].strip(), lines[i + 1].strip()
        if a and len(a) <= 60 and re.search(r"[A-Za-z]$", a) and not any(f for _, f in numbers_on(a)) \
                and re.match(r"[a-z]", b) and any(f for _, f in numbers_on(b)):
            if _row_fixes() and (_revenue_rank(a) in (0, 1) or _SUB_LINE.match(b)):
                # a revenue heading is not a wrapped label, and its first sub-line must not be read as its total: INDOSTAR's
                # "(a) Revenue from operations" + "interest income 21,742 ..." gave 217.42 against 234.18; CENTRUM's "1. Revenue
                # from operations" + "a. Fees and commission" gave 19.95 against 22.25 (27 Oct 2026, PDF_ROW_FIXES)
                continue
            lines[i], lines[i + 1] = f"{a} {b}", ""
            if positions is not None:
                positions[i], positions[i + 1] = positions[i] + positions[i + 1], []
    for i, line in enumerate(lines):
        label_probe = line.strip()
        if not label_probe:
            continue
        metric, rank = None, 0
        fixes = _row_fixes()
        if fixes and _TOTAL_A.match(label_probe) and _revenue_heading_above(lines, i):
            metric = "revenue"
        elif (rank_ := _revenue_rank(label_probe)) is not None:
            metric, rank = "revenue", rank_
        elif (_PAT_NAME_LETTERED if fixes else _PAT_NAME).search(label_probe) and not _PAT_NOT.search(label_probe):
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
        contested = False
        if fixes:
            basis, contested = _basis_above_boxed(lines, i)
        else:
            basis = _basis_above(lines, i)
        if basis is None and not consolidated_anywhere and not contested:
            basis = STANDALONE
        unit = unit_before(text, offsets[i])
        # header: the nearest line above with two or more dates
        header = next((b for b in range(i - 1, max(-1, i - HEADER_LOOKBACK), -1) if len(_dates_in(lines[b])) >= 2), None)
        if unit is None and header is not None:
            unit = _bare_unit(lines, header)
            if fixes:
                garbled, bare = _garbled_units(lines, header)
                if garbled:      # a garbled unit line is there: it and the clean lines must name one and the same unit
                    units = garbled | bare
                    unit = units.pop() if len(units) == 1 and None not in units else None
        row = Row(metric, label, basis, unit, figures, None, [], set(), page, rank=rank, key=(header, basis))
        row.odd = _odd_figures(line, start) or None
        if i in bad_lines:
            row.unproven = "the row's figures are not nearer its label's baseline than the next label's"
        if header is None:
            row.why = "no header with the period dates above the row"
            rows.append(row)
            continue
        dates = _dates_in(lines[header])
        shown = lines
        if len(figures) == len(dates) + 1 and _row_fixes() and (fixed := _with_extra_date(lines[header], len(figures))):
            shown = lines[:header] + [fixed] + lines[header + 1:]
            dates = _dates_in(fixed)
        row.dates = dates
        wide = "\n".join(shown[max(0, header - GROUP_LINES_ABOVE): min(i, header + 2)])
        row.group_words = {m.lastgroup for m in _GROUP.finditer(wide)}
        if len(figures) != len(dates):
            row.aligned = _align(positions[i], positions[header], dates, figures) if positions is not None else None
            if row.aligned is None:
                row.why = f"{len(figures)} figures on the row but {len(dates)} dates in the header (a cell may be missing)"
                rows.append(row)
                continue
            if row.odd:       # the odd indexes counted the row's own figures: no proof by position over a garbled row
                row.odd = {k for k, v in enumerate(row.aligned) if v is not None and v in [figures[j] for j in row.odd]}
        kinds = None
        for above in range(GROUP_LINES_ABOVE, -1, -1):   # a title line above may add group words: try fewer lines
            region = "\n".join(shown[max(0, header - above): min(i, header + 2)])
            kinds = _groups(region, dates)
            if kinds is not None and len(set(zip(kinds, dates))) == len(dates):   # one word for all five: not a proof
                break
            kinds = None
        march = bool(_MARCH_YEAR.search("\n".join(shown[max(0, header - 12): header + 2])))
        if kinds is None and (pattern := _pattern_kinds(dates, march)) is not None and row.group_words <= set(pattern):
            kinds = pattern
        if kinds is not None:
            row.columns = list(zip(kinds, dates))
        else:
            row.why = "the header's group words (quarter, year) do not tell each date's kind"
        rows.append(row)
    # one revenue line a table: the best rank (revenue from operations, else interest earned, else total income)
    best: dict[tuple, int] = {}
    for r in rows:
        if r.metric == "revenue":
            best[r.key] = min(best.get(r.key, 9), r.rank)
    kept = [r for r in rows if r.metric != "revenue" or r.rank == best[r.key]]
    if _row_fixes():
        # "Total income" includes other income: it is never the revenue from operations when the page has a revenue row on the
        # same basis (AIIL: "Revenue from operations" 886.01 beside "Total Income" 903.11, in another table of a reader's grid).
        # A page whose only revenue line is "Total income" keeps it: ``reading_of`` and ``verdict_of`` then say "only 'Total
        # income' printed" (restated-pdf's Titan page), the explicit reason; 27 Oct 2026, PDF_ROW_FIXES
        revenue_bases = {r.basis for r in kept if r.metric == "revenue" and r.rank in (0, 1)}
        kept = [r for r in kept if not (r.metric == "revenue" and r.rank == 2 and r.basis in revenue_bases)]
    return kept


BASELINE_SHARE = 0.45        # a figure farther than this share of the distance to the next label is not trusted to its row
SYSTEMATIC_SHARE = 0.3       # figures all sitting this far (median) off their labels: the pairing of the page is in doubt


def coordinate_text(page) -> tuple[str, list[list[tuple]], set[int], bool]:
    """A page's words put into rows by position, not by the order the text layer lists them: a layer that runs column by
    column (all labels, then all figures) or sets a figure a point off its label's baseline.

    The words with letters are put into label rows with the OCR's line builder (``ocr.positioned_lines``, without its
    de-skew: a text layer is not tilted); every other word (a figure, a date, a bracket) joins the label row whose baseline is
    nearest. Returns the text, each row's words (left edge, right edge, text, height), the rows holding a figure that is not
    nearer its label's baseline than ``BASELINE_SHARE`` of the distance to the nearest other label, and whether the figures of
    the whole page sit systematically off their labels (median offset over ``SYSTEMATIC_SHARE`` of that distance, where a
    figure may as well belong to the row above or below: no row of the page is then trusted)."""
    from .ocr import positioned_lines

    words = page.get_text("words")
    alpha = [([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], w, 1.0) for x0, y0, x1, y1, w, *_ in words if re.search(r"[A-Za-z]", w)]
    rest = [((x0 + x1) / 2, x0, x1, w, (y0 + y1) / 2) for x0, y0, x1, y1, w, *_ in words
            if not re.search(r"[A-Za-z]", w) and w.strip()]
    rows = [list(line) for line in positioned_lines(alpha, deskew=False)]
    if not rows:
        return "", [], set(), False
    centre = [sum(w[3] for w in row) / len(row) for row in rows]
    order = sorted(range(len(rows)), key=lambda k: centre[k])
    rows, centre = [rows[k] for k in order], [centre[k] for k in order]
    gap = [min((abs(c - o) for k2, o in enumerate(centre) if k2 != k and abs(c - o) > 0.5), default=None) for k, c in enumerate(centre)]
    bad: set[int] = set()
    offsets: list[float] = []
    for _, x0, x1, w, y in rest:
        k = min(range(len(rows)), key=lambda r: abs(centre[r] - y))
        rows[k].append((x0, x1, w, y))
        off = abs(y - centre[k])
        if gap[k] is not None and off >= BASELINE_SHARE * gap[k]:
            bad.add(k)
        if gap[k] is not None and re.search(r"\d\.\d", w):
            offsets.append(off / gap[k])
    offsets.sort()
    systematic = len(offsets) >= 6 and offsets[len(offsets) // 2] > SYSTEMATIC_SHARE
    rows = [sorted(row) for row in rows]
    return "\n".join(" ".join(w[2] for w in row) for row in rows), rows, bad, systematic


def _proven(rows: list[Row]) -> tuple[int, int]:
    """(rows whose figures failed the baseline check, negated; rows with a proven column): the reading with fewer failed rows
    wins, then the one with more proven rows."""
    failed = sum(bool(r.unproven) for r in rows)
    return -failed, sum(not r.unproven and r.columns is not None and (r.aligned is not None or len(r.figures) == len(r.dates))
                        for r in rows)


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
        consolidated_anywhere = any(_names(t, "consolidated") for t in texts.values())
        rows: list[Row] = []
        for i, layer in texts.items():
            text = doc.page_text(i)       # a page of figures is read with OCR first, as the pipeline reads it
            by_position = None if doc.is_scanned(i) else _by_position(doc, i)
            if by_position is not None:
                consolidated_anywhere = consolidated_anywhere or _names(by_position[0], "consolidated")
            candidates = []
            if any(len(_dates_in(line)) >= 2 for line in text.splitlines()):
                candidates.append(parse_page(text, i + 1, consolidated_anywhere or _names(text, "consolidated")))
            if by_position is not None and any(len(_dates_in(line)) >= 2 for line in by_position[0].splitlines()):
                candidates.append(parse_page(by_position[0], i + 1, consolidated_anywhere or _names(by_position[0], "consolidated"),
                                             by_position[1], by_position[2]))
            if by_position is not None and by_position[3]:
                # figures sit systematically off their labels' baselines: either reading may have paired a row with its
                # neighbour's figures, so no row of the page is trusted
                for candidate in candidates:
                    for r in candidate:
                        r.unproven = r.unproven or "the page's figures sit off their labels' baselines (rows may be paired wrongly)"
            if candidates:       # the reading with fewer failed rows, then more proven rows; the page's own order wins a tie
                rows += max(candidates, key=_proven)
        if doc.ocr_error is not None and not rows:
            return None, "OCR failed"
        return rows, "" if rows else "no results row (revenue, profit or EPS with its figures) found"
    finally:
        doc.close()


def _by_position(doc, index: int):
    """The page's words in rows by position, or None for a sideways page (read upright already) or a page with no words."""
    try:
        with _MUPDF:
            page = doc._doc[index]
            if upright_text(page) is not None:
                return None
            text, lines, bad, systematic = coordinate_text(page)
    except Exception:   # noqa: BLE001 - a second reading that fails leaves the first
        return None
    return (text, lines, bad, systematic) if text.strip() else None


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
    siblings: list[list[float]] = []       # per value: the row's other figures, in the same unit (a joined-cell check)
    unsure: list[str] = []
    totals: list[bool] = []                # per value: the label is the bottom-line total ("Profit for the period")
    seen = 0
    for r in rows:
        if r.metric != metric:
            continue
        seen += 1
        if r.basis is None or (basis and r.basis != basis):
            if r.basis is None and basis:
                unsure.append(f"p{r.page}: the table's basis is not told")
            continue
        if r.rank == 3:
            unsure.append(f"p{r.page}: only a sub-line of interest earned is printed, not its total")
            continue
        if r.unproven:
            unsure.append(f"p{r.page}: {r.unproven}")
            continue
        if not any(d == target[1] for d in r.dates):
            continue
        if r.columns is None:
            # kinds not told: one date only in the header, and the header names the kind of the period
            if r.dates.count(target[1]) == 1 and (r.aligned is not None or len(r.figures) == len(r.dates)) \
                    and target[0] in r.group_words:
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
        cell = r.aligned[index] if r.aligned is not None else r.figures[index]
        if cell is None:
            unsure.append(f"p{r.page}: no figure under the period's column (a nil cell)")
            continue
        if r.odd and index in r.odd:
            unsure.append(f"p{r.page}: the period's figure lacks the decimals its row prints (a garbled text layer)")
            continue
        value = cell if metric == "eps" else cell / r.unit
        values.append((value, r.label[:60], r.page))
        totals.append(bool(_PAT_TOTAL.search(r.label)) and not (_row_fixes() and _PAT_LESS.search(r.label)))
        siblings.append([f / (1 if metric == "eps" else r.unit) for k, f in enumerate(r.figures)
                         if k != index and f is not None])
    if metric == "pat" and _row_fixes() and len({round(v, 4) for v, _, _ in values}) > 1 and any(totals):
        # a table with "Profit after tax (5-6)" and, below the share of associates, "Profit for the period (7+8)": the total is
        # the bottom line; the rows above it are steps (F215, PDF_ROW_FIXES). Basis, unit and column proofs are unchanged.
        keep = [k for k, t in enumerate(totals) if t]
        if len({round(values[k][0], 4) for k in keep}) == 1:
            values, siblings = [values[k] for k in keep], [siblings[k] for k in keep]
    return {"values": values, "unsure": "; ".join(dict.fromkeys(unsure)), "found": seen, "siblings": siblings}


def revenue_only(values: list[tuple[float, str, int]]) -> list[tuple[float, str, int]]:
    """The figures of a revenue lookup that are revenue, not "Total income": memory's revenue is revenue from operations, and a
    table that splits it into sub-lines with no total leaves only "Total income" (Titan: 17,868 total income for 17,740
    revenue), which includes other income (restated-pdf trial, 27 Oct 2026)."""
    return [v for v in values if not _TOTAL_INCOME.search(v[1])]


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
    if metric == "revenue" and all(_TOTAL_INCOME.search(lab) for _, lab, _ in values):
        # no revenue from operations or interest earned row: "Total income" includes other income, so neither a match nor a
        # difference is a verdict
        return "pdf_unsure", [], None, f"only 'Total income' printed ({values[0][0]:g}), which includes other income"
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


def _pdf_readers():
    from . import pdf_readers
    return pdf_readers


class Sources:
    """The announcement lists and PDFs of the run, each fetched and read once."""

    def __init__(self, nse, ocr: bool = True):
        self.nse, self.ocr = nse, ocr
        self.lists: dict[tuple[str, str], list | str] = {}      # (symbol, period) -> filings or the reason none
        self.docs: dict[str, tuple[list[Row] | None, str]] = {}
        self.calls = {"lists": 0, "pdfs": 0}
        self.ensemble = None            # several readers (env PDF_READERS), None for "native" alone: today's path
        from . import pdf_readers
        names = pdf_readers.configured_readers()
        if names != [pdf_readers.DEFAULT_READERS]:
            self.ensemble = pdf_readers.Ensemble(names, ocr)
        self._payload: tuple[str, bytes | None, str] | None = None

    def release(self) -> None:
        """Drop what only the company just read needed (its PDFs' rows, the PDF bytes kept for the readers ensemble)."""
        self.docs.clear()
        self._payload = None

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

    def payload(self, url: str) -> tuple[bytes | None, str]:
        """(PDF bytes, why none) for the readers ensemble; the last PDF is kept, as every pair of a filing asks for it."""
        if self._payload and self._payload[0] == url:
            return self._payload[1], self._payload[2]
        data, why = None, ""
        folder = os.environ.get("PDF_CACHE_DIR")
        cached = os.path.join(folder, f"{_pdf_readers().pdf_key(url)}.pdf") if folder else ""
        if cached and os.path.isfile(cached):           # saved earlier by `pdf_readers --collect` (the matrix jobs)
            with open(cached, "rb") as fh:
                self._payload = (url, fh.read(), "")
            return self._payload[1], ""
        try:
            self.calls["pdfs"] += 1
            data = self.nse.fetch(url, max_bytes=MAX_PDF_BYTES)
            if not data:
                data, why = None, "NSE serves no file (404)"
        except SourceBlockedError:
            raise
        except AttachmentTooLarge:
            why = "PDF too large"
        except AttachmentError as exc:
            why = f"download failed ({str(exc)[:60]})"
        except Exception as exc:   # noqa: BLE001
            why = f"download failed ({type(exc).__name__})"
        self._payload = (url, data, why)
        return data, why

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
    if src.ensemble is not None:
        from .pdf_readers import referee_pair_ensemble
        return referee_pair_ensemble(src, row, out, listed, ours, theirs, xbrl)
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


# the explain verdicts that still need the PDF (a row the explain run cut, not_run, included): one list, the explain module's
from .screener_explain import TO_PDF as EXPLAIN_TO_PDF  # noqa: E402


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


def be_gentle() -> None:
    """Leave the machine one core and the lowest priority: OCR on every core starved the GitHub runner's own agent, which
    lost contact and killed the job after 2 h 33 min with nothing saved (maintenance run 40387696323). Memory was measured
    flat (580 MB after 36 reads, peak 1.35 GB on a 14 MB PDF), so CPU is the suspect."""
    try:
        from . import ocr
        ocr.SETTINGS["EngineConfig.onnxruntime.intra_op_num_threads"] = max(1, min(4, (os.cpu_count() or 2) - 1))
    except Exception:   # noqa: BLE001
        pass
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass


PROGRESS_PREFIX = "meta/pdf-referee/"   # R2 (the platform sink's `meta/` prefix): outlives a lost runner, unlike the job's artifact
SAVE_EVERY_PAIRS = 25
SAVE_EVERY_SECONDS = 180.0
_DECIDED_FIELDS = ("pdf_verdict", "pdf_value", "pdf_label", "pdf_url", "matches", "reason")


def pair_key(r: dict) -> tuple[str, ...]:
    """What names a pair across runs: scrip (symbol when the row has none), basis, period, metric, and the figures it
    compares (memory's and screener's), so a newer input with other figures for the same pair is read again."""
    return (str(r.get("scrip") or r.get("symbol") or ""), r.get("basis") or "", r.get("period") or "", r.get("metric") or "",
            str(r.get("memory_value") or ""), str(r.get("screener_value") or ""))


def progress_key(name: str) -> str:
    return f"{PROGRESS_PREFIX}{re.sub(r'[^A-Za-z0-9._-]', '_', name)[:100]}.csv"


def load_progress(sink, name: str) -> list[dict]:
    """The pairs an earlier run of ``name`` already decided (its saved CSV), or none when nothing is saved or R2 does not answer."""
    try:
        body = sink.get_object(progress_key(name))
    except Exception as exc:   # noqa: BLE001 - no saved progress is a fresh start, not a stop
        log.warning("pdf-referee: saved progress unreadable (%s: %s); starting fresh", type(exc).__name__, exc)
        return []
    return load_csv(body.decode("utf-8")) if body else []


def save_progress(sink, name: str, summary: dict) -> bool:
    """Store the decided pairs so far; a failed save is logged, never a stop."""
    try:
        sink.put_object(progress_key(name), to_csv(summary).encode("utf-8"), "text/csv")
        return True
    except Exception as exc:   # noqa: BLE001
        log.warning("pdf-referee: progress not saved (%s: %s)", type(exc).__name__, exc)
        return False


def run(nse, rows: list[dict], limit: int | None = None, time_budget: float | None = None, ocr: bool = True,
        clock=time.monotonic, sample: int = 0, seed: int = 26, explained: bool = False,
        progress=None, saved: list[dict] | None = None, every: int = SAVE_EVERY_PAIRS,
        every_seconds: float = SAVE_EVERY_SECONDS) -> dict:
    """Referee the open pairs among the screener-referee ``rows``, company by company; ``limit`` caps the pairs read (a
    company is finished once started); the rest are ``not_run``. With ``sample`` the pairs are instead a seeded random
    sample of that many pairs where memory already equals the XBRL file (``sample_pairs``); with ``explained`` the rows are
    screener-explain's and its ``unexplained`` ones are taken too (``open_pairs``).

    ``saved`` are the rows an earlier run decided (``load_progress``): a pair with the same scrip, basis, period and metric
    keeps that verdict and is not read again (not_run rows are never kept). ``progress`` gets the summary of the decided pairs
    so far after the company that makes ``every`` new pairs or ``every_seconds`` since its last call, so a lost runner loses
    a few minutes, not the run."""
    pairs = sample_pairs(rows, sample, seed) if sample else open_pairs(rows, explained)
    pool = sum(r.get("verdict") == "ours_matches_official" and r.get("metric") in SAMPLE_METRICS for r in rows) if sample else 0
    by_company: dict[tuple[str, str], list[dict]] = {}
    for r in pairs:
        by_company.setdefault((r["symbol"], r.get("basis") or ""), []).append(r)
    decided = {pair_key(r): r for r in (saved or []) if r.get("pdf_verdict") and r["pdf_verdict"] != "not_run"}
    src = Sources(nse, ocr)
    started, done, blocked, out_of_time, resumed = clock(), 0, False, False, 0
    capped = False   # the run's file cap (F213) was reached: the pairs left are not_run, not decided, and read next run
    last_save, since_save, symbol_now = started, 0, None
    results: list[dict] = []

    def not_run(r: dict, why: str) -> dict:
        return {**r, "pdf_verdict": "not_run", "reason": why, "pdf_value": None, "pdf_label": "", "pdf_url": "", "matches": ""}

    for (symbol, _basis), items in by_company.items():
        if symbol != symbol_now:
            src.release()           # the previous company's PDFs are not asked for again
            symbol_now = symbol
        todo = []
        for r in items:
            old = decided.get(pair_key(r))
            if old is not None:
                results.append({**r, **{k: old.get(k, "") for k in _DECIDED_FIELDS}, "pdf_value": _num(old.get("pdf_value"))})
                resumed += 1
            else:
                todo.append(r)
        if not blocked and time_budget is not None and clock() - started > time_budget:
            out_of_time = True
        why = "blocked" if blocked else "file cap" if capped else "time budget" if out_of_time else "limit" if limit is not None and done >= limit else ""
        if why:
            results += [not_run(r, why) for r in todo]
            continue
        for r in todo:
            if blocked or capped:
                results.append(not_run(r, "blocked" if blocked else "file cap"))
                continue
            try:
                results.append({**r, **referee_pair(src, r)})
                done += 1
                since_save += 1
            except FileCapReached as exc:
                capped = True
                log.warning("file cap reached (%s): stopping the PDF referee; the rest waits for the next run", exc)
                results.append(not_run(r, "file cap"))
            except SourceBlockedError as exc:
                blocked = True
                log.warning("NSE refused (%s): stopping the PDF referee", exc)
                results.append(not_run(r, "blocked"))
        if progress and (since_save >= every or (since_save and clock() - last_save >= every_seconds)):
            progress(summarise([x for x in results if x["pdf_verdict"] != "not_run"], src.calls, len(by_company), blocked,
                               out_of_time, len(rows) - len(pairs)))
            last_save, since_save = clock(), 0
    summary = summarise(results, src.calls, len(by_company), blocked, out_of_time, len(rows) - len(pairs))
    if resumed:
        summary["resumed"] = resumed
    if sample:
        summary["sample"] = {"drawn": len(pairs), "pool": pool, "seed": seed}
    if capped:
        summary["file_cap_reached"] = True
    return summary


def summarise(results: list[dict], calls: dict, companies: int, blocked: bool = False, out_of_time: bool = False,
              left_out: int = 0) -> dict:
    by_before: dict[str, Counter] = {}
    by_metric: dict[str, Counter] = {}
    reasons: Counter = Counter()
    for r in results:
        by_before.setdefault(r.get("verdict", ""), Counter())[r["pdf_verdict"]] += 1
        by_metric.setdefault(r["metric"], Counter())[r["pdf_verdict"]] += 1
        if r["pdf_verdict"] in ("pdf_unreadable", "pdf_unsure", "not_run", "pdf_disagree", "pdf_scanned_lead"):
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
    header = CSV_HEADER + (["readers"] if any("readers" in r for r in summary["rows"]) else [])   # only with PDF_READERS
    writer.writerow(header)
    for r in summary["rows"]:
        writer.writerow([_cell(r.get(k)) for k in header])
    return buffer.getvalue()


def to_json(summary: dict) -> str:
    return json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=1) + "\n"


def _columns(summary: dict) -> tuple:
    return VERDICTS + tuple(v for v in EXTRA_VERDICTS if summary["verdicts"].get(v))


def render(summary: dict) -> str:
    kind = "sampled pairs (memory equals the file)" if summary.get("sample") else "open pairs"
    lines = [f"pdf referee (the filing PDF, read only): {summary['pairs']} {kind}, {summary['companies']} companies, "
             f"{summary['calls']['announcement_lists']} announcement lists, {summary['calls']['pdfs']} PDFs"]
    lines += [f"  {v:24}{summary['verdicts'].get(v, 0)}" for v in _columns(summary)]
    if summary.get("resumed"):
        lines.append(f"  {summary['resumed']} pairs kept from the saved progress of an earlier run (not read again)")
    if summary["blocked"]:
        lines.append("stopped: NSE refused the session")
    if summary["out_of_time"]:
        lines.append("stopped: time budget")
    if summary.get("file_cap_reached"):
        lines.append("file cap reached: the rest waits for the next run")
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
    columns = _columns(summary)
    sep = "|---|" + "---|" * len(columns)

    def table(title: str, groups: dict) -> list[str]:
        rows = [f"## {title}", "", "| Group | " + " | ".join(columns) + " |", sep]
        rows += [f"| {k} | " + " | ".join(str(v.get(x, 0)) for x in columns) + " |" for k, v in sorted(groups.items())]
        return rows + [""]

    out += table("PDF verdict per XBRL verdict", summary["by_xbrl_verdict"]) + table("PDF verdict per metric", summary["by_metric"])
    out += ["## Why unsure, unreadable or not run", ""] + [f"- {k}: {n}" for k, n in summary["reasons"].items()] + [""]
    out += ["Every pair, with the PDF's figure, its row label and the file, is in the CSV artifact.", ""]
    return "\n".join(out)
