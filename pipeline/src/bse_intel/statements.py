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

from . import screener_view as sv
from . import segments
from . import xbrl_extras
from . import xbrl_facts
from .memory_gaps import quarter_end
from .periods import quarter_index

log = logging.getLogger(__name__)

KEY = "statements"
MAX_ENTRIES = 120      # about 12 quarters x 2 bases x 3 tables, plus room; the oldest go first


def _order(period: str) -> int:
    """A column's place in time: a quarter by its index, a year ("FY26") as its March quarter."""
    p = str(period or "")
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
    """The (table, rows, column) the file gives for its own period: always the quarter's P&L; the balance sheet when the period ends
    a half or a full year (Q2, Q4); the 12-month cash flow when it ends the year (Q4)."""
    period = doc.get("period") or ""
    end = quarter_end(period) if period.startswith("Q") else None
    if end is None:
        return []
    facts = xbrl_facts.Facts(doc)
    fam = sv.family(doc.get("template"))
    out = [("quarters", sv.pl_rows(fam, sv._Reader(facts, end=end, months=3), source=source), period)]
    if period.startswith(("Q2", "Q4")):
        out.append(("balance", sv.bs_rows(fam, sv._Reader(facts, instant=end), source, half_year=period.startswith("Q2"),
                                          standalone=doc.get("basis") == sv.STANDALONE), period))
    if period.startswith("Q4"):
        # the year closed by a March file, named as the year ("FY26"), as statements_backfill names it from the same recipes
        out.append(("annual", sv.pl_rows(fam, sv._Reader(facts, end=end, months=12), source=source), period[2:]))
        out.append(("cash_flow", sv.cf_rows(sv._Reader(facts, end=end, months=12), source), period[2:]))
    return out


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
