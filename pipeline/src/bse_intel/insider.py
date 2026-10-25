"""Insider trades, trade by trade, from NSE's SEBI PIT Regulation 7 filings (no AI).

NSE's `/api/corporates-pit-gg?index=equities&from_date=..&to_date=..` lists each Regulation 7(2) / 7(3) disclosure
with its XBRL file (measured 23 Oct 2026 from a cloud session: 9 filings for 20-22 Oct; 3,204 for Aug-Oct without
dates, all with `xmlFileName`). The XBRL (`in-bse-co`, PIT V2.0) holds the filing in context `MainI` and one
`DisclosureN` context per trade: the person and their category, the transaction type (Buy, Sell, Pledge Create /
Invoke / Revoke), shares and value in rupees, holdings before and after as a fraction of the company, the dates and
the mode. Each trade of a universe company is filed under `dossier["insider_trades"]["events"]`, once however often it
is read; a filing already read (its `appId`) is not fetched again. No card is made.
"""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from . import nse as nse_api
from . import universe
from .dossier import new_dossier, section_label
from .timeutil import now_iso, today_ist

log = logging.getLogger(__name__)

MAX_EVENTS = 200       # trades kept per company, newest last
MAX_SEEN = 400         # filing ids remembered per company
_NS = "{http://www.bseindia.com/xbrl/co/2017-09-15/in-bse-co}"
_PREFIX = "SecuritiesAcquiredOrDisposed"
_PERIOD = "DateOfAllotmentAdviceOrAcquisitionOfSharesOrSaleOfSharesSpecify"


def _num(value) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _pct(value) -> float | None:
    """A holding the XBRL states as a fraction (0.0021) as a percentage (0.21)."""
    n = _num(value)
    return round(n * 100, 4) if n is not None else None


def _day(value) -> str | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%b-%Y %H:%M:%S"):
        try:
            return datetime.strptime(text.title() if "%b" in fmt else text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _text(value) -> str | None:
    text = " ".join(str(value or "").split())
    return text if text and text.upper() not in ("NA", "N.A.", "-") else None


def parse(xml: bytes, row: dict | None = None) -> list[dict]:
    """One PIT filing's XBRL as trade events, one per disclosure with a person and a transaction. ``row`` is the
    filing's list row (its appId and broadcast time); without it the XBRL alone dates the filing."""
    row = row or {}
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError(f"PIT XBRL unreadable: {exc}") from exc
    facts: dict[str, dict[str, str]] = {}
    for el in root:
        if el.tag.startswith(_NS) and el.get("contextRef"):
            facts.setdefault(el.get("contextRef"), {})[el.tag[len(_NS):]] = (el.text or "").strip()
    main = facts.get("MainI", {})
    symbol = (main.get("Symbol") or str(row.get("symbol") or "")).strip().upper()
    filed = _day(main.get("DateOfFiling")) or _day(row.get("broadcastDateTime"))
    revised = str(main.get("RevisedFilling") or "").lower() == "true" or str(row.get("typeOfSubmission") or "") == "Revision"
    events = []
    for ctx in sorted((c for c in facts if c.startswith("Disclosure")), key=lambda c: int(c[10:] or 0) if c[10:].isdigit() else 0):
        f = facts[ctx]
        person, side, qty = _text(f.get("NameOfThePerson")), _text(f.get(_PREFIX + "TransactionType")), _num(f.get(_PREFIX + "NumberOfSecurity"))
        if not person or not side or not qty:
            continue
        value = _num(f.get(_PREFIX + "ValueOfSecurity"))
        events.append({
            "filing_id": str(row.get("appId") or "") or None,
            "symbol": symbol,
            "regulation": _text(main.get("DisclosureUnderRegulation") or row.get("regulation")),
            "revised": revised,
            "filed": filed,
            "person": person[:120],
            "category": _text(f.get("CategoryOfPerson")),
            "instrument": _text(f.get("TypeOfInstrument")),
            "side": side.upper(),
            "qty": qty,
            "value_cr": round(value / 1e7, 4) if value is not None else None,
            "before_qty": _num(f.get("SecuritiesHeldPriorToAcquisitionOrDisposalNumberOfSecurity")),
            "before_pct": _pct(f.get("SecuritiesHeldPriorToAcquisitionOrDisposalPercentageOfShareholding")),
            "after_qty": _num(f.get("SecuritiesHeldPostAcquistionOrDisposalNumberOfSecurity")),
            "after_pct": _pct(f.get("SecuritiesHeldPostAcquistionOrDisposalPercentageOfShareholding")),
            "from": _day(f.get(_PERIOD + "FromDate")),
            "to": _day(f.get(_PERIOD + "ToDate")),
            "mode": _text(f.get("ModeOfAcquisitionOrDisposal")),
            "exchange": _text(f.get("ExchangeOnWhichTheTradeWasExecuted")),
            "as_of": f"{filed}T23:59:00+05:30" if filed else None,   # known once the filing is broadcast
        })
    return events


def _key(e: dict) -> tuple:
    # a revision repeats the original's trades: the trade, not the filing, is the key
    return (e.get("person"), e.get("side"), e.get("qty"), e.get("from"), e.get("to"), e.get("instrument"))


def merge(dossier: dict, events: list[dict], filing_id: str | None = None) -> int:
    """Trades into memory, each once, oldest first. Returns how many were new."""
    box = dossier.setdefault("insider_trades", {"events": [], "filings": []})
    known = {_key(e) for e in box.get("events", [])}
    new = []
    for e in events:
        if _key(e) not in known:
            known.add(_key(e))
            new.append(e)
    if new:
        box["events"] = sorted(box.get("events", []) + new,
                               key=lambda e: (e.get("to") or e.get("filed") or "", e.get("person") or ""))[-MAX_EVENTS:]
        section_label(dossier, "insider_trades", now_iso())   # NSE's PIT feed (memory label: file)
    if filing_id and filing_id not in box.setdefault("filings", []):
        box["filings"] = (box["filings"] + [filing_id])[-MAX_SEEN:]
    return len(new)


def sync(pipeline, deadline: float, days: int = 3, scrips: set[str] | None = None, today: date | None = None) -> dict:
    """File the insider trades of universe companies broadcast in the last ``days`` (only `scrips`' when given)."""
    report = {"listed": 0, "in_universe": 0, "read": 0, "filed": 0, "companies": 0, "errors": [], "stopped": None}
    nse, sink = pipeline.nse, pipeline.sink
    if nse is None or getattr(pipeline, "_nse_refused", False):
        report["stopped"] = "NSE not asked (off or refused this run)"
        return report
    nse_map = universe.load_nse(sink)
    if not nse_map.built:
        report["stopped"] = "no NSE universe file yet"
        return report
    end = today or today_ist()   # IST: the runner's date.today() is UTC, a day behind after 18:30 UTC
    rows: list[dict] = []
    start = end - timedelta(days=days)
    while start <= end:   # NSE's list is read a month at a time
        stop = min(start + timedelta(days=29), end)
        try:
            rows += nse.insider_filings(start, stop)
        except nse_api.SourceBlockedError as exc:
            report["stopped"] = f"NSE refused the session: {exc}"
            return report
        except Exception as exc:  # a bot page or a dropped connection: the job's retry reads it again
            report["stopped"] = f"list unreadable: {type(exc).__name__}: {exc}"[:200]
            return report
        start = stop + timedelta(days=1)
    report["listed"] = len(rows)
    by_scrip: dict[str, list[dict]] = {}
    for row in rows:
        scrip = nse_map.symbols.get(str(row.get("symbol") or "").strip().upper())
        if not scrip or scrip not in nse_map.included or (scrips and scrip not in scrips) or not row.get("xmlFileName"):
            continue
        report["in_universe"] += 1
        by_scrip.setdefault(scrip, []).append(row)
    for scrip, mine in by_scrip.items():
        if time.monotonic() >= deadline:
            report["stopped"] = "time budget"
            break
        dossier = sink.get_dossier(scrip)
        if dossier is None:
            company = sink.company(scrip) or {}
            dossier = new_dossier(SimpleNamespace(scrip_code=scrip, company_name=company.get("company_name") or scrip,
                                                  symbol=str(mine[0].get("symbol") or "").upper()), company)
        seen = set((dossier.get("insider_trades") or {}).get("filings") or [])
        added = changed = 0
        for row in sorted(mine, key=lambda r: _day(r.get("broadcastDateTime")) or ""):
            filing_id = str(row.get("appId") or "")
            if filing_id and filing_id in seen:
                continue
            try:
                xml = nse.fetch(row["xmlFileName"], max_bytes=2_000_000)
            except nse_api.SourceBlockedError as exc:
                report["stopped"] = f"NSE refused the session: {exc}"
                break
            except Exception as exc:  # left unread: the next run tries it again
                report["errors"].append(f"{row.get('symbol')} {filing_id}: {type(exc).__name__}: {exc}"[:200])
                continue
            if xml is None:
                report["errors"].append(f"{row.get('symbol')} {filing_id}: XBRL not found")
                continue
            try:
                events = parse(xml, row)
            except ValueError as exc:
                report["errors"].append(f"{row.get('symbol')} {filing_id}: {exc}"[:200])
                continue
            report["read"] += 1
            added += merge(dossier, events, filing_id or None)
            changed += 1
        if changed:
            sink.put_dossier(scrip, dossier)
        if added:
            report["filed"] += added
            report["companies"] += 1
        if report["stopped"]:
            break
    report["errors"] = report["errors"][:20]
    return report
