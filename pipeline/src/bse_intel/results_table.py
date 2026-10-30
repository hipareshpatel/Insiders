"""The results page's figures from the saved statements only (owner, 30 Oct 2026: "find the source from the company page's Results
tab and use it"; "no card").

The company page's Quarterly results table is ``dossier["statements"]`` in each company's memory file (``memory/<scrip>.json`` in R2):
the exchange's XBRL files by screener's rules, file-labelled. This job turns that same source into one table per quarter
(fact_sheet.fact_sheet: revenue, EBITDA, PBT, PAT, margin, each with its year-ago and previous-quarter figure) and writes them all into
one file, ``raw/results-table/latest.json``, which the Worker serves beside the feed. No card, no AI, no exchange call. A quarter the
statements do not hold, and a bank (its own lines, not these), has no table."""

from __future__ import annotations

import json
import logging

from . import fact_sheet, screener_view as sv, statements

log = logging.getLogger(__name__)

SNAPSHOT_KEY = "raw/results-table/latest.json"
QUARTERS_KEPT = 8   # the latest quarters a company keeps in the file; the page's rows are recent ones


def table_of(sheet: dict) -> dict:
    """A quarter's table in the shape a results card carries (``results_snapshot``): the lens, the quarter, its basis and one entry
    per line, so the page reads it as it reads a card's table."""
    return {"lens": "company", "period": sheet["period"], "basis": sheet["basis"], **sheet["lines"]}


def company_tables(dossier: dict, kept: int = QUARTERS_KEPT) -> dict[str, dict]:
    """Quarter -> table for one company, from its statements only."""
    periods = sorted({e["period"] for e in dossier.get(statements.KEY, []) or []
                      if isinstance(e, dict) and e.get("table") == "quarters" and str(e.get("period", "")).startswith("Q")},
                     key=lambda p: sv.quarter_index(p) or 0, reverse=True)[:kept]
    out: dict[str, dict] = {}
    for period in periods:
        sheet = fact_sheet.fact_sheet(dossier, period)
        if sheet is not None:
            out[period] = table_of(sheet)
    return out


def build(sink, at: str) -> dict:
    """The whole snapshot: rows keyed ``<scrip>|<quarter>``. A company whose read fails is logged and left out, not guessed."""
    rows: dict[str, dict] = {}
    for scrip in sink.list_dossiers():
        try:
            dossier = sink.get_dossier(scrip)
            for period, table in company_tables(dossier or {}).items():
                rows[f"{scrip}|{period}"] = table
        except Exception as exc:  # noqa: BLE001 - one company's bad file must not stop the rest
            log.warning("results-table: %s not read: %s", scrip, exc)
    return {"v": 1, "built_at": at, "rows": rows}


def write(sink, at: str) -> int:
    """Build the snapshot and write it. Returns the number of quarter tables written."""
    snapshot = build(sink, at)
    sink.put_object(SNAPSHOT_KEY, json.dumps(snapshot, separators=(",", ":")).encode("utf-8"))
    return len(snapshot["rows"])
