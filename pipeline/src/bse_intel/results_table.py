"""The Results page's KPI figures from the saved statements only (owner, 30 Oct 2026: "that page should only use saved XBRL
statements, no card"; "redesign the entire page as a KPI report").

The company page's Quarterly results table is ``dossier["statements"]`` in each company's memory file: the exchange's XBRL files by
screener's rules, file-labelled. This job turns that same source into one table per quarter and keeps the KPI figures of each in the
``results_kpi`` table, one row per company and quarter, so the page can filter, sort and summarise them in the database. No card, no
AI, no exchange call. Every statement layout (``family``) gives a row: a corporate filer's revenue, EBITDA (operating profit), margin
and profit; a bank's revenue (interest earned) and profit; an NBFC's revenue, financing profit and financing margin (in the EBITDA and
margin columns) and profit; an insurer's profit only. A quarter with no profit line has no row. The basis is consolidated when the
statements have the quarter on it with a profit line, else standalone."""

from __future__ import annotations

import hashlib
import json
import logging

from . import fact_sheet, screener_view as sv, statements
from .metrics import CONSOLIDATED, STANDALONE
from .periods import prior_quarter_period, prior_year_period

log = logging.getLogger(__name__)

STATEMENT = "results_kpi_upsert"
QUARTERS_KEPT = 10   # the latest quarters a company keeps: the page's eight-quarter trend, and last quarter's growth for momentum
# A change across a loss is a named turn, not a per cent; as a sort key it ranks beside the per cents (a loss turned to profit
# first, a profit turned to loss last)
TURN_KEY = {"LOSS_TO_PROFIT": 1e6, "LOSS_NARROWED": 1e5, "LOSS_WIDENED": -1e5, "PROFIT_TO_LOSS": -1e6}
# family -> (revenue row, EBITDA row, margin row) of its saved statements; None: the family has no such line
LAYOUT = {sv.CORPORATE: ("Sales", "Operating Profit", "OPM %"),
          sv.BANK: ("Revenue", None, None),
          sv.NBFC: ("Revenue", "Financing Profit", "Financing Margin %"),
          sv.INSURER: (None, None, None)}
PAT_ROWS = (fact_sheet.OWNERS, "Net Profit")   # the profit to shareholders when the file has it, else the net profit


def _entry(dossier: dict, period: str | None, basis: str) -> dict | None:
    """The file-labelled quarters-table entry of a period and basis (any family), or None."""
    if not period:
        return None
    for e in dossier.get(statements.KEY, []) or []:
        if (isinstance(e, dict) and e.get("table") == "quarters" and e.get("period") == period and e.get("basis") == basis
                and e.get("family") in LAYOUT and (e.get("lab") or {}).get("by") == "file"):
            return e
    return None


def _line(key: str, row: str, now: dict, before: dict) -> dict | None:
    """One line of a table: its value, the same line a year and a quarter earlier, and the changes worked out here."""
    value = (now.get("rows") or {}).get(row)
    if value is None:
        return None
    line: dict = {"value": round(value, 2)}
    for slot, tag in (("prev_year", "yoy"), ("prev_quarter", "qoq")):
        base = ((before[slot] or {}).get("rows") or {}).get(row)
        if base is None:
            continue
        line[slot] = round(base, 2)
        change = fact_sheet._change(value, base, key)
        if "pct" in change:
            line[f"{tag}_pct"] = change["pct"]
        elif "turn" in change:
            line[f"{tag}_turn"] = change["turn"]
    return line


def table_of(dossier: dict, period: str) -> dict | None:
    """A quarter's table: ``lens`` (the kind: company, bank, nbfc, insurer), period, basis, source filing and one entry per line (revenue, ebitda, pat,
    ebitda_margin), or None when the statements hold no profit line for it."""
    prior = {"prev_year": prior_year_period(period), "prev_quarter": prior_quarter_period(period)}
    for basis in (CONSOLIDATED, STANDALONE):
        now = _entry(dossier, period, basis)
        if now is None:
            continue
        before = {slot: _entry(dossier, p, basis) for slot, p in prior.items()}
        revenue_row, ebitda_row, margin_row = LAYOUT[now["family"]]
        # the profit's comparatives are the same row as its value (a total with minority interest is no base for the owners' profit)
        pat_row = next((r for r in PAT_ROWS if (now.get("rows") or {}).get(r) is not None), None)
        pat = _line("pat", pat_row, now, before) if pat_row else None
        if pat is None:
            continue
        table: dict = {"lens": "company" if now["family"] == sv.CORPORATE else now["family"], "period": period, "basis": basis, "source_news_id": now.get("source_news_id"), "pat": pat}
        for key, row in (("revenue", revenue_row), ("ebitda", ebitda_row)):
            line = _line(key, row, now, before) if row else None
            if line is not None:
                table[key] = line
        margin = (now.get("rows") or {}).get(margin_row) if margin_row else None
        if margin is not None:
            line = {"value": round(margin, 2)}
            for slot, tag in (("prev_year", "yoy"), ("prev_quarter", "qoq")):
                base = ((before[slot] or {}).get("rows") or {}).get(margin_row)
                if base is not None:
                    line[slot] = round(base, 2)
                    line[f"{tag}_bps"] = round((margin - base) * 100)
            table["ebitda_margin"] = line
        return table
    return None


def company_tables(dossier: dict, kept: int = QUARTERS_KEPT) -> dict[str, dict]:
    """Quarter -> table for one company, from its statements only."""
    periods = sorted({e["period"] for e in dossier.get(statements.KEY, []) or []
                      if isinstance(e, dict) and e.get("table") == "quarters" and str(e.get("period", "")).startswith("Q")},
                     key=lambda p: sv.quarter_index(p) or 0, reverse=True)[:kept]
    out: dict[str, dict] = {}
    for period in periods:
        table = table_of(dossier, period)
        if table is not None:
            out[period] = table
    return out


def _growth_key(line: dict, tag: str) -> float | None:
    """The sort key of a line's year-on-year change: its per cent, else its named turn's number, else None."""
    if line.get(f"{tag}_pct") is not None:
        return line[f"{tag}_pct"]
    return TURN_KEY.get(line.get(f"{tag}_turn"))


def kpi_row(scrip: str, table: dict, at: str) -> dict:
    """One ``results_kpi`` row from a quarter's table: the figures, their changes, and a digest of them (an unchanged row is not
    rewritten in the database). The keys are the table's column names."""
    revenue, ebitda, pat, opm = table.get("revenue") or {}, table.get("ebitda") or {}, table.get("pat") or {}, table.get("ebitda_margin") or {}
    kind = table["lens"]
    news_id = table.get("source_news_id")
    row = {"scrip_code": scrip, "period": table["period"], "basis": table["basis"], "kind": kind,
           "source_news_id": news_id if isinstance(news_id, str) and news_id.startswith("nse-") else None,
           "revenue": revenue.get("value"), "revenue_prev": revenue.get("prev_year"),
           "revenue_yoy": revenue.get("yoy_pct"), "revenue_qoq": revenue.get("qoq_pct"),
           "ebitda": ebitda.get("value"), "ebitda_prev": ebitda.get("prev_year"), "ebitda_yoy": ebitda.get("yoy_pct"),
           "ebitda_qoq": ebitda.get("qoq_pct"), "ebitda_turn": ebitda.get("yoy_turn"), "ebitda_key": _growth_key(ebitda, "yoy"),
           "pat": pat.get("value"), "pat_prev": pat.get("prev_year"), "pat_yoy": pat.get("yoy_pct"), "pat_qoq": pat.get("qoq_pct"),
           "pat_turn": pat.get("yoy_turn"), "pat_qoq_turn": pat.get("qoq_turn"), "pat_key": _growth_key(pat, "yoy"),
           "opm": opm.get("value"), "opm_yoy_bps": opm.get("yoy_bps"), "opm_qoq_bps": opm.get("qoq_bps")}
    # profit not from operations: an ordinary company's profit up (or a loss turned to profit) while its EBITDA fell
    row["nfo"] = int(kind == "company"
                     and ((row["pat_yoy"] or 0) > 0 or row["pat_turn"] == "LOSS_TO_PROFIT")
                     and ((row["ebitda_yoy"] or 0) < 0 or row["ebitda_turn"] in ("PROFIT_TO_LOSS", "LOSS_WIDENED")))
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
