"""The Results page's KPI figures from the saved statements only (owner, 30 Oct 2026: "that page should only use saved XBRL
statements, no card"; "redesign the entire page as a KPI report").

The company page's Quarterly results table is ``dossier["statements"]`` in each company's memory file: the exchange's XBRL files by
screener's rules, file-labelled. This job turns that same source into one table per quarter (fact_sheet.fact_sheet: revenue, EBITDA,
PBT, PAT and margin, each with its year-ago and previous-quarter figure; consolidated over standalone) and keeps the KPI figures of
each in the ``results_kpi`` table, one row per company and quarter, so the page can filter and sort them in the database. No card, no
AI, no exchange call. A quarter the statements do not hold, and a bank (its own lines, not these), has no row."""

from __future__ import annotations

import hashlib
import json
import logging

from . import fact_sheet, screener_view as sv, statements

log = logging.getLogger(__name__)

STATEMENT = "results_kpi_upsert"
QUARTERS_KEPT = 8   # the latest quarters a company keeps; the page's quarter list is these
# A change across a loss is a named turn, not a per cent; as a sort key it ranks beside the per cents (a loss turned to profit
# first, a profit turned to loss last)
TURN_KEY = {"LOSS_TO_PROFIT": 1e6, "LOSS_NARROWED": 1e5, "LOSS_WIDENED": -1e5, "PROFIT_TO_LOSS": -1e6}


def table_of(sheet: dict) -> dict:
    """A quarter's table in the shape a results card carries (``results_snapshot``): the lens, the quarter, its basis and one
    entry per line."""
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


def _growth_key(line: dict, tag: str) -> float | None:
    """The sort key of a line's year-on-year change: its per cent, else its named turn's number, else None."""
    if line.get(f"{tag}_pct") is not None:
        return line[f"{tag}_pct"]
    return TURN_KEY.get(line.get(f"{tag}_turn"))


def kpi_row(scrip: str, table: dict, at: str) -> dict:
    """One ``results_kpi`` row from a quarter's table: the figures, their changes, and a digest of them (an unchanged row is not
    rewritten in the database)."""
    revenue, ebitda, pat, opm = table.get("revenue") or {}, table.get("ebitda") or {}, table.get("pat") or {}, table.get("ebitda_margin") or {}
    row = {"scrip_code": scrip, "period": table["period"], "basis": table["basis"],
           "revenue": revenue.get("value"), "revenue_yoy": revenue.get("yoy_pct"), "revenue_qoq": revenue.get("qoq_pct"),
           "ebitda": ebitda.get("value"), "ebitda_yoy": ebitda.get("yoy_pct"), "ebitda_qoq": ebitda.get("qoq_pct"),
           "ebitda_turn": ebitda.get("yoy_turn"), "ebitda_key": _growth_key(ebitda, "yoy"),
           "pat": pat.get("value"), "pat_yoy": pat.get("yoy_pct"), "pat_qoq": pat.get("qoq_pct"),
           "pat_turn": pat.get("yoy_turn"), "pat_key": _growth_key(pat, "yoy"),
           "opm": opm.get("value"), "opm_yoy_bps": opm.get("yoy_bps"), "opm_qoq_bps": opm.get("qoq_bps")}
    row["digest"] = hashlib.sha1(json.dumps(row, sort_keys=True).encode()).hexdigest()[:16]
    row["updated_at"] = at
    return row


def company_rows(scrip: str, dossier: dict, at: str) -> list[dict]:
    """The KPI rows of one company, newest quarter first."""
    return [kpi_row(scrip, table, at) for table in company_tables(dossier).values()]


def recent_scrips(sink) -> list[str]:
    """The companies with a results card in the live window: the query the results catch-up already uses (event_catchup)."""
    import datetime

    from .event_catchup import MAX_CARDS, RESULTS_DAYS
    from .timeutil import today_ist

    since = (today_ist() - datetime.timedelta(days=RESULTS_DAYS)).isoformat()
    return sorted({r["scrip_code"] for r in sink.query("results_cards_recent", [since, MAX_CARDS]) if r.get("scrip_code")})


def write(sink, at: str, scrips: list[str] | None = None) -> int:
    """Read each company's statements and put its quarters' KPI rows into the database; ``scrips`` None: every stored company (the full
    rebuild); a list: only those (each pipeline run does the live window's companies, so a run reads a few hundred memory files, not
    all of them). A company whose read fails is logged and keeps its old rows. Returns the number of rows sent."""
    rows: list[dict] = []
    for scrip in (sink.list_dossiers() if scrips is None else scrips):
        try:
            rows += company_rows(scrip, sink.get_dossier(scrip) or {}, at)
        except Exception as exc:  # noqa: BLE001 - one company's bad file must not stop the rest
            log.warning("results-table: %s not read: %s", scrip, exc)
    if rows:
        sink.execute(STATEMENT, rows)
    return len(rows)
