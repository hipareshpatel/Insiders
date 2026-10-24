"""Bulk and block deals, deal by deal, from NSE's large-deals snapshot (no AI).

NSE's `/api/snapshot-capital-market-largedeal` lists the latest session's bulk deals (a client trading 0.5% or more of
a company's shares in a day), block deals (a single trade of ₹10 Cr or more in the block window) and short-selling
rows (measured 22 Oct 2026 from the Actions runner: 111 bulk, 4 block, 99 short; data chain audit §6). The historical
lists (`/api/historical/bulk-deals`, `/block-deals`) answer a cloud session with NSE's bot page, so the history is
built here: each trading morning the snapshot is read and each deal of a universe company not yet in memory is filed
under `dossier["market_deals"]["events"]` (not "deals": that is the M&A and order deals list). The snapshot holds one session only, so a missed morning is a missed session;
the job runs in market-data.yml and the nightly, with retries, and a deal is filed once however often it is read.
Short-selling rows carry no client or price and are not filed. No card is made.

The history before the first morning read comes from `/api/historicalOR/bulk-block-short-deals?...&csv=true`
(measured 22-23 Oct 2026 from the Actions runner and a cloud session: 696 bulk and 17 block lines for 7 days, CSV with
"Date","Symbol",...,"Trade Price / Wght. Avg. Price","Remarks"): `deals-backfill --days N` walks it a week at a time.
"""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from . import nse as nse_api
from . import universe
from .dossier import new_dossier
from .timeutil import today_ist

log = logging.getLogger(__name__)

MAX_EVENTS = 100       # deals kept per company, newest last
_KINDS = {"BULK_DEALS_DATA": "BULK", "BLOCK_DEALS_DATA": "BLOCK"}


def _num(value) -> float | None:
    text = str(value if value is not None else "").replace(",", "").strip()
    try:
        return float(text) if text and text not in ("-", "NA", "N.A.") else None
    except ValueError:
        return None


def _day(value) -> str | None:
    text = str(value or "").strip()
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.title() if "%b" in fmt else text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_row(row: dict, kind: str) -> dict | None:
    """One snapshot row as a memory event, or None when it lacks what a deal needs (a symbol, a date, a side, a
    quantity). The value is the quantity at the weighted average traded price, in ₹ crore."""
    symbol = str(row.get("symbol") or "").strip().upper()
    day = _day(row.get("date"))
    side = str(row.get("buySell") or "").strip().upper()
    qty, price = _num(row.get("qty")), _num(row.get("watp"))
    if not symbol or not day or side not in ("BUY", "SELL") or not qty:
        return None
    remarks = " ".join(str(row.get("remarks") or "").split())
    return {
        "kind": kind,
        "symbol": symbol,
        "date": day,
        "client": " ".join(str(row.get("clientName") or "").split())[:120] or None,
        "side": side,
        "qty": qty,
        "price": price,
        "value_cr": round(qty * price / 1e7, 2) if price else None,
        "remarks": remarks if remarks and remarks != "-" else None,
        "as_of": f"{day}T15:30:00+05:30",   # known at the session's close
    }


def _key(e: dict) -> tuple:
    return (e["kind"], e["date"], e.get("client"), e["side"], e["qty"], e.get("price"))


def merge(dossier: dict, events: list[dict]) -> int:
    """Deals into memory, each once, oldest first. Returns how many were new."""
    box = dossier.setdefault("market_deals", {"events": []})
    known = {_key(e) for e in box.get("events", [])}
    new = []
    for e in events:
        if _key(e) not in known:
            known.add(_key(e))
            new.append(e)
    if new:
        box["events"] = sorted(box.get("events", []) + new, key=lambda e: (e["date"], e["kind"], e.get("client") or ""))[-MAX_EVENTS:]
    return len(new)


_CSV_FIELDS = {"date": "date", "symbol": "symbol", "client name": "clientName", "buy / sell": "buySell",
               "quantity traded": "qty", "trade price / wght. avg. price": "watp", "remarks": "remarks"}


def csv_rows(text: str) -> list[dict]:
    """NSE's deals-history CSV as rows shaped like the snapshot's (headers carry a BOM and trailing spaces)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    rows = []
    for raw in reader:
        row = {}
        for key, value in raw.items():
            name = _CSV_FIELDS.get(" ".join(str(key or "").lower().split()))
            if name:
                row[name] = value
        if row:
            rows.append(row)
    return rows


def _file(sink, nse_map, events: list[dict], report: dict, deadline: float, scrips: set[str] | None) -> None:
    """Deals of universe companies into their memory, each once."""
    by_scrip: dict[str, list[dict]] = {}
    for event in events:
        if event["date"] not in report["sessions"]:
            report["sessions"].append(event["date"])
        scrip = nse_map.symbols.get(event["symbol"])
        if not scrip or scrip not in nse_map.included or (scrips and scrip not in scrips):
            continue
        report["in_universe"] += 1
        by_scrip.setdefault(scrip, []).append(event)
    for scrip, mine in by_scrip.items():
        if time.monotonic() >= deadline:
            report["stopped"] = report["stopped"] or "time budget"
            break
        dossier = sink.get_dossier(scrip)
        if dossier is None:
            company = sink.company(scrip) or {}
            dossier = new_dossier(SimpleNamespace(scrip_code=scrip, company_name=company.get("company_name") or scrip,
                                                  symbol=mine[0]["symbol"]), company)
        added = merge(dossier, mine)
        if added:
            sink.put_dossier(scrip, dossier)
            report["filed"] += added
            report["companies"] += 1


def backfill(pipeline, deadline: float, days: int = 180, scrips: set[str] | None = None,
             today: date | None = None) -> dict:
    """The last ``days`` of bulk and block deals from NSE's deals history, a week at a time, oldest first."""
    report = {"listed": 0, "in_universe": 0, "filed": 0, "companies": 0, "sessions": [], "errors": [], "stopped": None,
              "windows": 0}
    nse, sink = pipeline.nse, pipeline.sink
    if nse is None or getattr(pipeline, "_nse_refused", False):
        report["stopped"] = "NSE not asked (off or refused this run)"
        return report
    nse_map = universe.load_nse(sink)
    if not nse_map.built:
        report["stopped"] = "no NSE universe file yet"
        return report
    end = today or today_ist()   # IST: the runner's date.today() is UTC, a day behind after 18:30 UTC
    start = end - timedelta(days=days)
    while start <= end and not report["stopped"]:
        stop = min(start + timedelta(days=6), end)
        if time.monotonic() >= deadline:
            report["stopped"] = "time budget"
            break
        events = []
        for option, kind in (("bulk_deals", "BULK"), ("block_deals", "BLOCK")):
            try:
                rows = csv_rows(nse.deals_history(option, start, stop))
            except nse_api.SourceBlockedError as exc:
                report["stopped"] = f"NSE refused the session: {exc}"
                break
            except Exception as exc:  # one window unreadable: say so and go on; a re-run files only what is missing
                report["errors"].append(f"{option} {start}..{stop}: {type(exc).__name__}: {exc}"[:200])
                continue
            for row in rows:
                report["listed"] += 1
                event = parse_row(row, kind)
                if event is None:
                    report["errors"].append(f"unreadable {kind} row: {str(row)[:120]}")
                else:
                    events.append(event)
        _file(sink, nse_map, events, report, deadline, scrips)
        report["windows"] += 1
        start = stop + timedelta(days=1)
    report["sessions"] = sorted(report["sessions"])
    report["errors"] = report["errors"][:20]
    return report


def sync(pipeline, deadline: float, scrips: set[str] | None = None) -> dict:
    """File the latest session's bulk and block deals of universe companies (only `scrips`' when given)."""
    report = {"listed": 0, "in_universe": 0, "filed": 0, "companies": 0, "sessions": [], "errors": [], "stopped": None}
    nse, sink = pipeline.nse, pipeline.sink
    if nse is None or getattr(pipeline, "_nse_refused", False):
        report["stopped"] = "NSE not asked (off or refused this run)"
        return report
    nse_map = universe.load_nse(sink)
    if not nse_map.built:
        report["stopped"] = "no NSE universe file yet"
        return report
    try:
        snapshot = nse.large_deals()
    except nse_api.SourceBlockedError as exc:
        report["stopped"] = f"NSE refused the session: {exc}"
        return report
    except Exception as exc:  # a bot page or a dropped connection: the job's retry reads it again
        report["stopped"] = f"snapshot unreadable: {type(exc).__name__}: {exc}"[:200]
        return report
    events = []
    for key, kind in _KINDS.items():
        for row in snapshot.get(key) or []:
            report["listed"] += 1
            event = parse_row(row, kind)
            if event is None:
                report["errors"].append(f"unreadable {kind} row: {str(row)[:120]}")
                continue
            events.append(event)
    _file(sink, nse_map, events, report, deadline, scrips)
    report["errors"] = report["errors"][:20]
    return report
