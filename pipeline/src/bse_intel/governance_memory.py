"""The quarterly governance filing into each company's memory (governance_xbrl.py; TRACKER F70).

NSE lists every company's governance XBRL in one all-company list, newest first (docs/SOURCES.md "Integrated filing
lists"). At the end of a live run this step reads the list's first page, keeps the latest file per company and quarter
(a revision's time is `revised_Date`, an original's `broadcast_Date`), and for the companies in the universe files
each report not yet in memory: the dossier's `governance.quarters`, dated by the file's own time, so a card sees only
the quarters known when its filing came out (dossier.view_as_of). No card is made; the PDF stays on the drop list.
`governance-sync --pages N` reads further back for the backfill.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

from . import governance_xbrl, universe
from . import nse as nse_api
from .dossier import annual_profit_cr, merge_governance, new_dossier
from .timeutil import IST, iso_ist

log = logging.getLogger(__name__)

GOVERNANCE = "Integrated Filing- Governance"
PAGE_SIZE = 500
MAX_FILES = 40      # reports read per live run (NSE's pace is 3-5 s a request)


def filed_at(row: dict) -> str | None:
    """A row's time: `revised_Date` for a revision, else `broadcast_Date`, else `creation_Date` (IST)."""
    for key in ("revised_Date", "broadcast_Date", "creation_Date"):
        value = (row.get(key) or "").strip()
        try:
            return iso_ist(datetime.strptime(value.title(), "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST))
        except ValueError:
            continue
    return None


def latest(rows: list[dict]) -> list[dict]:
    """The latest file per company and quarter, newest first."""
    best: dict[tuple[str, str], dict] = {}
    for row in rows:
        url = str(row.get("xbrl") or "")
        when = filed_at(row)
        if not url.endswith(".xml") or not when or not row.get("symbol") or not row.get("qe_Date"):
            continue
        key = (row["symbol"].strip().upper(), row["qe_Date"])
        if key not in best or when > best[key]["_when"]:
            best[key] = {**row, "_when": when}
    return sorted(best.values(), key=lambda r: r["_when"], reverse=True)


def sync(pipeline, deadline: float, pages: int = 1, max_files: int = MAX_FILES, scrips: set[str] | None = None) -> dict:
    """File the governance reports NSE has listed since memory last took them (only `scrips`' when given, as a
    measured round does). Returns what it did."""
    report = {"listed": 0, "in_universe": 0, "filed": 0, "known": 0, "errors": [], "stopped": None}
    nse, sink = pipeline.nse, pipeline.sink
    if nse is None or getattr(pipeline, "_nse_refused", False):
        report["stopped"] = "NSE not asked (off or refused this run)"
        return report
    nse_map = universe.load_nse(sink)
    if not nse_map.built:
        report["stopped"] = "no NSE universe file yet"
        return report
    rows: list[dict] = []
    try:
        for page in range(1, pages + 1):
            rows += nse.integrated_list(GOVERNANCE, page, PAGE_SIZE)
    except nse_api.SourceBlockedError as exc:
        report["stopped"] = f"NSE refused the session: {exc}"
        return report
    for row in latest(rows):
        report["listed"] += 1
        scrip = nse_map.symbols.get(row["symbol"].strip().upper())
        if not scrip or scrip not in nse_map.included or (scrips and scrip not in scrips):
            continue
        report["in_universe"] += 1
        if report["filed"] >= max_files or time.monotonic() >= deadline:
            continue
        dossier = sink.get_dossier(scrip)
        if dossier and any(q.get("source") == row["xbrl"] and q.get("parser") == governance_xbrl.PARSER_VERSION
                           for q in (dossier.get("governance") or {}).get("quarters", [])):
            report["known"] += 1
            continue
        try:
            data = nse.download(row["xbrl"])
        except nse_api.SourceBlockedError as exc:
            report["stopped"] = f"NSE refused the session: {exc}"
            break
        except Exception as exc:  # one file must not end the step; the next run tries it again
            report["errors"].append(f"{row['symbol']}: {type(exc).__name__}: {exc}"[:200])
            continue
        parsed = governance_xbrl.parse(data) if data else None
        if parsed is None:
            report["errors"].append(f"{row['symbol']}: unreadable governance XBRL")
            continue
        if dossier is None:
            company = sink.company(scrip) or {}
            dossier = new_dossier(SimpleNamespace(scrip_code=scrip, company_name=company.get("company_name") or row.get("smName"),
                                                  symbol=row["symbol"]), company)
        if merge_governance(dossier, parsed.memory(annual_profit_cr(dossier)), row["_when"], row["xbrl"]):
            sink.put_dossier(scrip, dossier)
            report["filed"] += 1
            raised = parsed.exceptions(annual_profit_cr(dossier))
            if raised:
                log.info("governance %s %s: %s", row["symbol"], parsed.quarter_end, "; ".join(raised)[:300])
    return report


SHAREHOLDING_DAYS = 10       # days of NSE's shareholding list read each live run
MAX_SHAREHOLDING_FILES = 60  # patterns filed per live run


def shareholding_sync(pipeline, deadline: float, days: int = SHAREHOLDING_DAYS, max_files: int = MAX_SHAREHOLDING_FILES,
                      day_to=None) -> dict:
    """Each universe company's quarterly shareholding pattern (XBRL) into memory (PLAN 18 part 5): promoter,
    pledge, FII, DII and public holdings per quarter, cross-checked against NSE's own list (seed.file_shareholding).
    NSE lists every company's patterns in one answer for a date range (measured 2026-10-19). No AI call, no card."""
    from datetime import timedelta

    from .seed import file_shareholding
    from .timeutil import today_ist

    report = {"listed": 0, "in_universe": 0, "filed": 0, "known": 0, "refused": [], "errors": [], "stopped": None}
    nse, sink = pipeline.nse, pipeline.sink
    if nse is None or getattr(pipeline, "_nse_refused", False):
        report["stopped"] = "NSE not asked (off or refused this run)"
        return report
    nse_map = universe.load_nse(sink)
    if not nse_map.built:
        report["stopped"] = "no NSE universe file yet"
        return report
    end = day_to or today_ist()
    try:
        filings = nse.shareholding_list(end - timedelta(days=days), end)
    except nse_api.SourceBlockedError as exc:
        report["stopped"] = f"NSE refused the session: {exc}"
        return report
    for row in sorted(filings, key=lambda f: f.filed_at, reverse=True):
        report["listed"] += 1
        scrip = nse_map.symbols.get(row.symbol) or nse_map.isins.get((row.isin or "").upper())
        if not scrip or scrip not in nse_map.included:
            continue
        report["in_universe"] += 1
        if report["filed"] >= max_files or time.monotonic() >= deadline:
            continue
        # The upload time is in the file's name ("SHP_1689543_09072026111935_WEB.xml"); the list gives the day only
        row = replace(row, filed_at=nse_api.shareholding_filed_at(row.xbrl_url) or row.filed_at)
        dossier = sink.get_dossier(scrip) or {}
        source = f"xbrl:shp:{scrip}:{row.period}"
        if any(o.get("period") == row.period and o.get("source_news_id") == source and str(o.get("as_of", "")) >= row.filed_at
               for o in dossier.get("ownership", [])):
            report["known"] += 1
            continue
        try:
            data = nse.download(row.xbrl_url)
        except nse_api.SourceBlockedError as exc:
            report["stopped"] = f"NSE refused the session: {exc}"
            break
        except Exception as exc:  # one file must not end the step; the next run tries it again
            report["errors"].append(f"{row.symbol}: {type(exc).__name__}: {exc}"[:200])
            continue
        company = sink.company(scrip) or {}
        problem = file_shareholding(sink, scrip, company.get("company_name") or row.symbol, row, data, company) if data \
            else "unreadable"
        if problem:
            report["refused"].append(problem if problem != "unreadable" else f"{row.symbol} {row.period}: unreadable")
        else:
            report["filed"] += 1
    return report
