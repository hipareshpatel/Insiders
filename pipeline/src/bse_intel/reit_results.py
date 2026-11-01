"""REIT and InvIT results on the Results page (owner, 30 Oct 2026: "REITs need to check XBRL"; plan in docs/STATUS.md item 12, step 1).

NSE lists the trusts' results XBRL under index=reitsinvits (nse.reit_invit_results; measured 30 Oct 2026: 193 filings from 27
trusts). Each file carries the quarter, the basis, the trust's ISIN, symbol and BSE code, and the same Ind AS lines a company files. This
reads them into the page's table (results_kpi, kind reit or invit) by Screener's rules, which matched on Embassy's Sep 2026
file: sales = revenue from operations, operating profit = sales less expenses other than finance cost and depreciation, profit = profit for
the period. A file has only its own quarter (and the year to date), so the comparatives come from the same trust's earlier files, as
for companies. Every file kept in R2 (raw/reit-xbrl/): a run reads what is stored and downloads only the rest, under the file cap.

A trust is not on NSE's equity list, so it is put into companies here (ISIN, symbol, name, classification) and its ISIN in kv
reit_trust_isins, which prune-companies honours. Net distributable cash flow, distribution per unit and the other trust figures
in the same file are step 2."""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime

from . import results_table, statements, xbrl
from .metrics import CONSOLIDATED, STANDALONE
from .nse import FileCapReached

log = logging.getLogger(__name__)

STORE_PREFIX = "raw/reit-xbrl/"
TRUSTS_KEY = "reit_trust_isins"      # kv: JSON list of the trusts' ISINs (prune-companies keeps these companies)
CRORE = 1e7                          # the file's amounts are in rupees (measured on Embassy's Sep 2026 file: revenue 13,026,340,000)
FAMILY = {"REITs": "reit", "InvITs": "invit"}   # NSE's own word for the trust, to the layout name (results_table.LAYOUT)

# The NSE classification Screener shows for each trust, measured 30 Oct 2026 (a repeated step is left out, as our stored paths do).
# A trust we do not list is stored without one ("Unclassified" on the page).
INDUSTRY = {
    "ANANTAM": "Services > Transport Infrastructure > Road Assets-Toll, Annuity, Hybrid-Annuity",
    "ANZEN": "Utilities > Power > Power - Transmission",
    "BAGMANE": "Consumer Discretionary > Realty > Real Estate Investment Trusts (REITs)",
    "BIRET": "Consumer Discretionary > Realty > Real Estate Investment Trusts (REITs)",
    "CAPINVIT": "Industrials > Construction > Civil Construction",
    "CITIUSINVT": "Services > Transport Infrastructure > Road Assets-Toll, Annuity, Hybrid-Annuity",
    "CUBEINVIT": "Services > Transport Infrastructure > Road Assets-Toll, Annuity, Hybrid-Annuity",
    "EMBASSY": "Consumer Discretionary > Realty > Real Estate Investment Trusts (REITs)",
    "INDIGRID": "Utilities > Power > Power - Transmission",
    "INDUSINVIT": "Services > Transport Infrastructure > Road Assets-Toll, Annuity, Hybrid-Annuity",
    "INTERISE": "Services > Transport Infrastructure > Road Assets-Toll, Annuity, Hybrid-Annuity",
    "IRBINVIT": "Services > Transport Infrastructure > Road Assets-Toll, Annuity, Hybrid-Annuity",
    "IRBIT": "Services > Transport Infrastructure > Road Assets-Toll, Annuity, Hybrid-Annuity",
    "KRT": "Consumer Discretionary > Realty > Real Estate Investment Trusts (REITs)",
    "MINDSPACE": "Consumer Discretionary > Realty > Real Estate Investment Trusts (REITs)",
    "NDRINVIT": "Services > Commercial Services & Supplies > Diversified Commercial Services",
    "NHIT": "Services > Transport Infrastructure > Road Assets-Toll, Annuity, Hybrid-Annuity",
    "NXST": "Consumer Discretionary > Realty > Real Estate Investment Trusts (REITs)",
    "NXT-INFRA": "Industrials > Construction > Civil Construction",
    "OSEINTRUST": "Industrials > Construction > Civil Construction",
    "PGINVIT": "Utilities > Power > Power - Transmission",
    "RIIT": "Services > Transport Infrastructure > Road Assets-Toll, Annuity, Hybrid-Annuity",
    "ROADSTAR": "Services > Transport Infrastructure > Road Assets-Toll, Annuity, Hybrid-Annuity",
    "SEITINVIT": "Utilities > Power > Power Generation",
    "SHREMINVIT": "Industrials > Construction > Civil Construction",
    "TVSINVIT": "Services > Commercial Services & Supplies > Diversified Commercial Services",
    "VERTIS": "Services > Transport Infrastructure > Road Assets-Toll, Annuity, Hybrid-Annuity",
}


def stamp(row: dict) -> datetime:
    """When NSE broadcast a filing (a revision's has no submission date)."""
    for key in ("broadcast", "submissionDate", "revisedDate"):
        try:
            return datetime.strptime(str(row.get(key)), "%d-%b-%Y %H:%M:%S")
        except ValueError:
            continue
    return datetime.min


def pick(rows: list[dict]) -> list[dict]:
    """One filing for each trust, basis, quarter name and listed period (a revision beats its original), newest first. The list's own
    period is not trusted for the quarter (the Sep 2026 files of Embassy and IRB InvIT say 31-Mar-2027): the file's contexts are."""
    best: dict[tuple, dict] = {}
    for row in rows:
        if not row.get("xbrl") or not row.get("symbol"):
            continue
        key = (row["symbol"], row.get("consNoncons"), row.get("relatedTo"), row.get("periodEnded"))
        if key not in best or stamp(row) > stamp(best[key]):
            best[key] = row
    return sorted(best.values(), key=stamp, reverse=True)


def _basis(text: str | None) -> str:
    return CONSOLIDATED if (text or "").strip().lower().startswith("consolidated") else STANDALONE


def read(data: bytes) -> dict | None:
    """One results file's quarter: {period, basis, isin, symbol, scrip, rows} (amounts in rupees crore, screener's row names), or
    None when it is not an XBRL instance, has no three-month period with a revenue or profit line, or no profit."""
    try:
        root = ET.fromstring(xbrl.as_utf8(data))
    except ET.ParseError:
        return None
    contexts = xbrl._contexts(root)
    facts = list(xbrl._facts(root))
    text = {name: value for name, _ctx, unit, value in facts if unit is None}
    by: dict[str, dict[str, float]] = defaultdict(dict)
    for name, ctx, unit, value in facts:
        number = xbrl._num(value) if unit is not None else None
        if number is not None:
            by[name].setdefault(ctx, number)
    quarter = None
    for ctx in list(by.get("RevenueFromOperations", {})) + list(by.get("ProfitLossForPeriod", {})):
        info = contexts.get(ctx) or {}
        if info.get("dims") or xbrl._months(info) != 3:
            continue
        if quarter is None or info["endDate"] > contexts[quarter]["endDate"]:
            quarter = ctx
    if quarter is None:
        return None

    def amount(tag: str) -> float | None:
        return by.get(tag, {}).get(quarter)

    revenue, expenses, pat = amount("RevenueFromOperations"), amount("Expenses"), amount("ProfitLossForPeriod")
    if pat is None:
        return None
    rows: dict[str, float] = {"Net Profit": round(pat / CRORE, 2)}
    owners, minority = amount("ProfitOrLossAttributableToOwnersOfParent"), amount("ProfitOrLossAttributableToNonControllingInterests")
    # the owners' share only when it and the minority's add up to the profit: some files fill both with 0 (measured 31 Oct 2026: TVS
    # Jun 2026, profit 17.74 Cr, owners 0, minority 0), and a filler zero is no profit to the unitholders
    if owners is not None and abs(owners + (minority or 0) - pat) <= max(CRORE / 100, abs(pat) / 200):
        rows["Net Profit (owners)"] = round(owners / CRORE, 2)
    if revenue is not None:
        rows["Sales"] = round(revenue / CRORE, 2)
        if expenses is not None:
            operating = revenue - (expenses - (amount("FinanceCosts") or 0) - (amount("DepreciationDepletionAndAmortisationExpense") or 0))
            rows["Operating Profit"] = round(operating / CRORE, 2)
            if revenue:
                rows["OPM %"] = round(operating / revenue * 100, 2)
    return {"period": xbrl.period_label(contexts[quarter]), "basis": _basis(text.get("NatureOfReportStandaloneConsolidated")),
            "isin": (text.get("ISIN") or "").strip().upper(), "symbol": (text.get("Symbol") or "").strip().upper(),
            "scrip": (text.get("ScripCode") or "").strip(), "rows": rows}


def _file(client, sink, row: dict, counts: dict) -> bytes | None:
    """The file's bytes: the stored copy, else downloaded (one file for the cap) and stored."""
    url = row["xbrl"]
    key = STORE_PREFIX + url.rsplit("/", 1)[-1]
    data = sink.get_object(key)
    if data is not None:
        counts["stored"] += 1
        return data
    data = client.download(url)
    if data is None:
        counts["not_xml"] += 1
        return None
    sink.put_object(key, data, "application/xml")
    counts["downloaded"] += 1
    return data


def entries(parsed: list[dict], family: str) -> list[dict]:
    """The trust's quarters as saved-statement entries (the shape results_table reads): one for each quarter and basis, the latest filing's."""
    kept: dict[tuple, dict] = {}
    for p in parsed:
        key = (p["period"], p["basis"])
        if key not in kept or p["stamp"] > kept[key]["stamp"]:
            kept[key] = p
    return [{"table": "quarters", "period": p["period"], "basis": p["basis"], "family": family, "lab": {"by": "file"}, "rows": p["rows"],
             "source_news_id": None} for p in kept.values() if p["period"]]


def run(client, sink, at: str, day_from: date | None = None) -> dict:
    """List NSE's trust filings, read each (stored or downloaded under the file cap), put the trusts into companies and their quarters
    into results_kpi. Returns the counts. A file that cannot be read is left out and counted; the cap ends the run early, not as a failure."""
    listed = client.reit_invit_results(day_from)
    chosen = pick(listed)
    counts = {"listed": len(listed), "files": len(chosen), "stored": 0, "downloaded": 0, "not_xml": 0, "unreadable": 0, "no_quarter": 0, "no_sales": 0}
    parsed: dict[str, list[dict]] = defaultdict(list)
    meta: dict[str, dict] = {}
    capped = False
    for row in chosen:
        try:
            data = _file(client, sink, row, counts)
        except FileCapReached:
            capped = True
            break
        if data is None:
            continue
        got = read(data)
        if got is None or not got["period"]:
            counts["no_quarter" if got is None else "unreadable"] += 1
            continue
        if got["rows"].get("Sales") == 0:
            counts["no_sales"] += 1   # a trust's quarter before it held its assets (Bagmane, Mar 2026): no sales, no result to show (owner, 31 Oct 2026)
            continue
        got["stamp"] = stamp(row)
        symbol = row["symbol"]
        parsed[symbol].append(got)
        meta.setdefault(symbol, {"name": row.get("companyName"), "family": FAMILY.get(row.get("reitsInvits"), "reit"),
                                 "isin": got["isin"], "scrip": got["scrip"]})
    companies, kpi, kept = [], [], []
    for symbol, found in parsed.items():
        info = meta[symbol]
        if not info["isin"]:
            log.warning("reit-results: %s has no ISIN in its file; left out", symbol)
            continue
        if not info["scrip"].strip("0"):
            # not on BSE: the file says 000000 (measured 31 Oct 2026: six trusts, Nxt-Infra, NDR, Oriental, SEIT, Shrem, TVS), so the key is
            # the NSE symbol, as for an NSE-only company (nse.py); the rows once saved under the shared 000000 are removed below
            if info["scrip"]:
                kept.append({"scrip_code": info["scrip"], "periods": []})
            info["scrip"] = f"NSE:{symbol}"
        companies.append({"scrip_code": info["scrip"], "symbol": symbol, "company_name": info["name"], "isin": info["isin"],
                          "industry": INDUSTRY.get(symbol), "updated_at": at})
        rows = results_table.company_rows(info["scrip"], {statements.KEY: entries(found, info["family"])}, at)
        kpi += rows
        if rows:
            kept.append({"scrip_code": info["scrip"], "periods": [r["period"] for r in rows]})
    if companies:
        sink.execute("companies_upsert", companies)
        known = set(json.loads(sink.kv_get(TRUSTS_KEY) or "[]"))
        sink.kv_set(TRUSTS_KEY, json.dumps(sorted(known | {c["isin"] for c in companies})), at)
    if kpi:
        sink.execute(results_table.STATEMENT, kpi)
        placeholders = sorted({k["scrip_code"] for k in kept if not k["periods"]})
        if placeholders:   # the shared 000000 company row once named after one of them shadows that trust's own (the guards of companies_prune hold)
            sink.execute("companies_prune", [{"scrip_code": s} for s in placeholders])
        for i in range(0, len(kept), results_table.PRUNE_BATCH):
            sink.execute(results_table.PRUNE_STATEMENT, kept[i:i + results_table.PRUNE_BATCH])
    per_period: dict[str, int] = defaultdict(int)
    for r in kpi:
        per_period[r["period"]] += 1
    return {**counts, "capped": capped, "trusts": len(companies), "rows": len(kpi), "per_quarter": dict(sorted(per_period.items()))}
