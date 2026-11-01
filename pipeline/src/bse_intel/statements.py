"""The screener-rule statements of a live results filing, kept in memory when the filing is read (owner, 30 Oct 2026: "live
results should get stored as per screener rules").

When the live path reads a results XBRL (``Pipeline._xbrl``), this module turns the same file into its facts
(``xbrl_facts.parse_facts``, kept in R2 under ``raw/xbrl-facts/`` as the bulk job keeps them) and into the rows of screener.in's
tables by the same recipes the comparison measures (``screener_view``: the quarter's P&L; the balance sheet at a half year or a
year end; the year's P&L and cash flow in a March quarter's file, named as the year). The rows go into the dossier's ``statements``: one entry per period,
basis and table, each row with its value and the recipe note that built it, labelled ``file``. A later filing of the same
period, basis and table replaces the entry (a revised file), so memory holds the company's latest statement.

Nothing here changes a figure the cards read (``financial_metrics`` and ``balance_sheet`` are written as before); the rows are
the screener-style view of the same file, for the company page and the fact sheet. A failure of any part is logged and the
filing goes on: the statements are an addition, never a reason to fail a filing."""

from __future__ import annotations

import logging
import re

from . import screener_view as sv
from . import segments
from . import xbrl_extras
from . import xbrl_facts
from .memory_gaps import quarter_end
from .periods import quarter_index

log = logging.getLogger(__name__)

KEY = "statements"
MAX_ENTRIES = 120      # about 60 a basis (a quarter, a balance sheet at most quarters, the years); the oldest go first


def _order(period: str) -> int:
    """A column's place in time: a quarter by its index, a year ("FY26") as its March quarter, a year to another month ("YE:2025-12")
    as the quarter that ends it (Q3FY26), so keep_latest never drops it first as the oldest."""
    p = str(period or "")
    if m := re.fullmatch(r"YE:(\d{4})-(\d{2})", p):
        y, mo = int(m[1]), int(m[2])
        return quarter_index(f"Q{(mo - 4) % 12 // 3 + 1}FY{(y + (mo > 3)) % 100:02d}") or 0
    return quarter_index(f"Q4{p}" if p.startswith("FY") else p) or 0


def keep_latest(entries: list[dict]) -> list[dict]:
    """The newest MAX_ENTRIES entries by period (a revision of an old quarter does not push out a newer one)."""
    return sorted(entries, key=lambda e: _order(e.get("period")))[-MAX_ENTRIES:]


def corrected_entry(e: dict) -> dict:
    """A quarters or annual entry with its profit lines made consistent (``screener_view.corrected_pl``); the same entry when nothing
    changes. Applied when an entry is written (``remember``, the backfill) and where it is read (fact sheet, Results), so a dossier not
    yet rebuilt reads right too."""
    if e.get("table") not in ("quarters", "annual"):
        return e
    rows = e.get("rows") or {}
    fixed = sv.corrected_pl(rows, e.get("family") or "")
    return e if fixed is rows else {**e, "rows": fixed}


def rows_of(doc: dict, source: str = "") -> list[tuple[str, dict[str, sv.Row], str]]:
    """The (table, rows, column) the file gives for its own period, as the stored-facts rebuild (statements_backfill) builds them:
    always the quarter's P&L; the balance sheet at any quarter whose file has one; the year's P&L and cash flow when the file holds
    twelve months to its quarter end: a March file's year named "FY26", any other month's "YE:2025-12" (1 Nov 2026: a December,
    June or September company's year-end result, VBL or ABB, was written by the rebuild only, never by the live run)."""
    period = doc.get("period") or ""
    end = quarter_end(period) if period.startswith("Q") else None
    if end is None:
        return []
    facts = xbrl_facts.Facts(doc)
    fam = sv.family(doc.get("template"))
    out = [("quarters", sv.pl_rows(fam, sv._Reader(facts, end=end, months=3), source=source), period)]
    q4 = period.startswith("Q4")
    # a quarter with no balance sheet in its file gives no rows, and remember() writes nothing for it
    out.append(("balance", sv.bs_rows(fam, sv._Reader(facts, instant=end), source, half_year=not q4,
                                      standalone=doc.get("basis") == sv.STANDALONE), period))
    year = period[2:] if q4 else f"YE:{end.year}-{end.month:02d}"
    # a March company's December file has nine months, not twelve, so its 12-month reader gives no rows and no year is written
    year_reader = sv._Reader(facts, end=end, months=12)
    out.append(("annual", sv.pl_rows(fam, year_reader, source=source), year))
    out.append(("cash_flow", sv.cf_rows(year_reader, source), year))
    return out


# Tables a live file never overwrites once the stored-facts rebuild (statements_backfill) has written them: the rebuild reads the
# year's annual report before its results file, as screener does, and a re-read of an old results file put the results file's
# figures back (1 Nov 2026: RITES FY26 cash from operations 165.97 over the report's 327.48, screener 327; VINATIORGA Q4FY26
# total liabilities 3,589.53 over 3,579.04; pipeline run 41252490055 re-reading their May filings).
REBUILT_KEPT = ("annual", "cash_flow", "balance")


def _from_stored_facts(e: dict) -> bool:
    return (e.get("lab") or {}).get("from") == "stored facts"


def remember(dossier: dict, doc: dict, news_id: str, as_of: str, at: str) -> int:
    """Put the file's screener-rule rows into ``dossier[KEY]`` (in place); the number of entries written."""
    period, basis = doc.get("period"), doc.get("basis")
    if not period:
        return 0
    entries = [e for e in dossier.get(KEY, []) if isinstance(e, dict)]
    written = 0
    for table, rows, column in rows_of(doc, source=f"results file {period}"):
        values = {name: row.value for name, row in rows.items() if row.value is not None}
        if not values:
            continue
        if table in REBUILT_KEPT and any(_from_stored_facts(e) for e in entries
                                         if (e.get("period"), e.get("basis"), e.get("table")) == (column, basis, table)):
            continue   # the rebuild already read this file with every other one and took the year's annual report first
        values = sv.corrected_pl(values, sv.family(doc.get("template"))) if table in ("quarters", "annual") else values
        entries = [e for e in entries if (e.get("period"), e.get("basis"), e.get("table")) != (column, basis, table)]
        entries.append({"period": column, "basis": basis, "table": table, "family": sv.family(doc.get("template")),
                        "rows": values,   # the recipe behind each row is screener_view's, by family; not stored a row
                        "source_news_id": news_id, "as_of": as_of,
                        "lab": {"by": "file", "doc": "results", "basis": basis, "at": at, "rules": "screener_view"}})
        written += 1
    if written:
        dossier[KEY] = keep_latest(entries)
    return written


def from_file(sink, dossier: dict, data: bytes, scrip: str, url: str, news_id: str, as_of: str, at: str) -> int:
    """The whole step for one live results file: its facts kept in R2, its screener-rule rows in the dossier. Never raises."""
    try:
        doc = xbrl_facts.parse_facts(data, scrip, url)
        if doc is None:
            return 0
        try:
            xbrl_facts.save(sink, scrip, doc["period"], doc.get("basis"), doc)
        except Exception as exc:  # noqa: BLE001 - R2 is best effort; the rows still go into memory
            log.warning("statements: facts of %s not kept: %s", url, exc)
        try:
            segments.remember(dossier, doc, news_id, as_of, at)      # the business mix from the same file (TODO 137)
        except Exception as exc:  # noqa: BLE001 - likewise an addition
            log.warning("statements: segments of %s not built: %s", url, exc)
        try:
            xbrl_extras.remember(dossier, doc, news_id, as_of, at)   # audit, cash-flow detail, related parties, ratios (TODO 138)
        except Exception as exc:  # noqa: BLE001 - likewise an addition
            log.warning("statements: extras of %s not built: %s", url, exc)
        return remember(dossier, doc, news_id, as_of, at)
    except Exception as exc:  # noqa: BLE001 - an addition: a failure is logged, the filing goes on
        log.warning("statements: %s %s not built: %s", scrip, url, exc)
        return 0
