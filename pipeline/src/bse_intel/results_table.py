"""The results page's figures from the saved statements only (owner, 30 Oct 2026: "find the source from the company page's Results
tab and use it"; "no card").

The company page's Quarterly results table is ``dossier["statements"]`` in each company's memory file (``memory/<scrip>.json`` in R2):
the exchange's XBRL files by screener's rules, file-labelled. This job turns that same source into one table per quarter
(fact_sheet.fact_sheet: revenue, EBITDA, PBT, PAT, margin, each with its year-ago and previous-quarter figure) and writes a small
file per company, ``raw/results-table/<scrip>.json``; the Worker reads only the companies of the page's rows, so a page costs a few
dozen small reads and no large parse. No card, no AI, no exchange call. A quarter the
statements do not hold, and a bank (its own lines, not these), has no table."""

from __future__ import annotations

import json
import logging

from . import fact_sheet, screener_view as sv, statements

log = logging.getLogger(__name__)

PREFIX = "raw/results-table/"   # one small file per company: {"v": 1, "built_at", "rows": {quarter: table}}
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


def recent_scrips(sink) -> list[str]:
    """The companies with a results card in the live window: the query the results catch-up already uses (event_catchup)."""
    import datetime

    from .event_catchup import MAX_CARDS, RESULTS_DAYS
    from .timeutil import today_ist

    since = (today_ist() - datetime.timedelta(days=RESULTS_DAYS)).isoformat()
    return sorted({r["scrip_code"] for r in sink.query("results_cards_recent", [since, MAX_CARDS]) if r.get("scrip_code")})


def write(sink, at: str, scrips: list[str] | None = None) -> int:
    """Read each company's statements and write its file; ``scrips`` None: every stored company (the full rebuild, which also marks a
    company with no table by an empty file); a list: only those (each pipeline run does the live window's companies, so a run reads
    a few hundred memory files, not all of them). A company whose read fails is logged and keeps its old file. Returns the number of
    quarter tables written."""
    count = 0
    for scrip in (sink.list_dossiers() if scrips is None else scrips):
        try:
            tables = company_tables(sink.get_dossier(scrip) or {})
        except Exception as exc:  # noqa: BLE001 - one company's bad file must not stop the rest
            log.warning("results-table: %s not read: %s", scrip, exc)
            continue
        body = {"v": 1, "built_at": at, "rows": tables}
        sink.put_object(f"{PREFIX}{scrip}.json", json.dumps(body, separators=(",", ":")).encode("utf-8"))
        count += len(tables)
    return count
