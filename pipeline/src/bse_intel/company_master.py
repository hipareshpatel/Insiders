"""The company master from NSE (owner, 2026-10-19: everything on NSE).

Until now the companies table came from BSE's scrip list and each company's industry from BSE's quote header
(`sync-companies` on BSE). BSE refuses GitHub's addresses, so online that sync never ran, and a company listed after
go-live was never in the master: its filings were set aside as "not in the company master (listed on NSE only)".

`sync` reads NSE's main-board equity list (`EQUITY_L.csv`: symbol, name, ISIN, listing date) and:
* a company already in the master (matched by ISIN, else by symbol) keeps its key, the BSE scrip code every card,
  memory file and URL uses, and gets NSE's current symbol, ISIN and name;
* a company the master does not have (a new listing, or one never on BSE) is added under its NSE symbol as its key
  (symbols are never all digits, so they cannot collide with BSE codes).

Industry: NSE's quote page carries a company's industry, but NSE refuses it from cloud and GitHub addresses
(measured 2026-10-19, HTTP 403 from both). So a company without one takes NSE's own industry from the sources that
answer: the `smIndustry` field on its announcements ("Banks", "Computers - Software"; on 560 companies in one week,
measured), else the Industry column of NSE's index lists (Nifty Total Market and Microcap 250, 1,009 companies,
broad: "Capital Goods"). A stored industry is never overwritten; a company with none stays in sector "default".
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# NSE's index constituent lists (static files on nsearchives), each with an Industry column per ISIN
INDEX_LISTS = ("ind_niftytotalmarket_list.csv", "ind_niftymicrocap250_list.csv")
INDEX_URL = "https://nsearchives.nseindia.com/content/indices/{name}"
ANNOUNCEMENT_DAYS = 7     # days of announcements read for their smIndustry field
PAGE = 1000


@dataclass
class SyncReport:
    listed: int = 0           # rows on NSE's equity list
    matched: int = 0          # already in the master
    added: list[str] = field(default_factory=list)       # new companies, keyed by NSE symbol
    updated: int = 0          # matched rows whose symbol, ISIN, name or industry changed
    industry_filled: int = 0  # companies given an industry this run
    without_industry: int = 0

    def as_dict(self) -> dict:
        return {"listed": self.listed, "matched": self.matched, "added": len(self.added),
                "added_sample": self.added[:20], "updated": self.updated, "industry_filled": self.industry_filled,
                "without_industry": self.without_industry}


def parse_index_list(text: str) -> dict[str, str]:
    """{ISIN: Industry} from one of NSE's index constituent CSVs ("Company Name,Industry,Symbol,Series,ISIN Code")."""
    out: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO((text or "").lstrip("﻿"))):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        isin, industry = row.get("isin code", "").upper(), row.get("industry", "")
        if isin and industry:
            out[isin] = industry
    return out


def announcement_industries(rows: list[dict]) -> dict[str, str]:
    """{ISIN: smIndustry} from NSE announcement rows that carry it."""
    out: dict[str, str] = {}
    for row in rows or ():
        isin, industry = (row.get("sm_isin") or "").strip().upper(), (row.get("smIndustry") or "").strip()
        if isin and industry and industry != "-":
            out.setdefault(isin, industry)
    return out


def plan(equities, stored: list[dict], industries: dict[str, str], sector_for, now: str) -> tuple[list[dict], SyncReport]:
    """The company rows to write (pure; `sync` adds the I/O). `stored` are the master's rows (scrip_code, symbol,
    isin, company_name, industry, sector); `industries` NSE's industry by ISIN; `sector_for(industry)` the prompt
    module's name. Only new or changed rows are returned, so a daily run writes a handful of rows, not 2,600."""
    by_isin = {(c.get("isin") or "").strip().upper(): c for c in stored if c.get("isin")}
    by_symbol = {(c.get("symbol") or "").strip().upper(): c for c in stored if c.get("symbol")}
    by_key = {str(c["scrip_code"]): c for c in stored}
    report = SyncReport(listed=len(equities))
    rows: list[dict] = []
    for eq in equities:
        company = by_isin.get(eq.isin) or by_symbol.get(eq.symbol) or by_key.get(eq.symbol)
        industry = industries.get(eq.isin)
        if company is None:
            row = {"scrip_code": eq.symbol, "symbol": eq.symbol, "isin": eq.isin, "company_name": eq.name or eq.symbol,
                   "industry": industry, "sector": sector_for(industry) if industry else "default", "updated_at": now}
            rows.append(row)
            report.added.append(eq.symbol)
            report.industry_filled += bool(industry)
            report.without_industry += not industry
            continue
        report.matched += 1
        row = {"scrip_code": company["scrip_code"]}
        if eq.symbol and eq.symbol != (company.get("symbol") or "").strip().upper():
            row["symbol"] = eq.symbol
        if eq.isin and eq.isin != (company.get("isin") or "").strip().upper():
            row["isin"] = eq.isin
        if eq.name and eq.name != (company.get("company_name") or ""):
            row["company_name"] = eq.name
        if not company.get("industry"):
            if industry:
                row["industry"], row["sector"] = industry, sector_for(industry)
                report.industry_filled += 1
            else:
                report.without_industry += 1
        if len(row) > 1:
            row["updated_at"] = now
            rows.append(row)
            report.updated += 1
    return rows, report


def stored_companies(sink) -> list[dict]:
    """Every company in the master, paged (export_companies)."""
    rows: list[dict] = []
    after = ""
    while True:
        page = sink.query("export_companies", [after, PAGE])
        if not page:
            return rows
        rows += page
        after = page[-1]["scrip_code"]


def nse_industries(client, today) -> dict[str, str]:
    """NSE's industry by ISIN: the index lists first, then the last week's announcement rows (more specific, so
    they win). A source that fails is skipped; the sync goes on with what answered."""
    from datetime import timedelta

    from .nse import ANNOUNCEMENTS_ENDPOINT, SourceBlockedError

    out: dict[str, str] = {}
    for name in INDEX_LISTS:
        try:
            out.update(parse_index_list(client._get(INDEX_URL.format(name=name)).text))
        except SourceBlockedError:
            raise
        except Exception as exc:  # one list missing must not stop the sync
            log.warning("NSE index list %s unavailable: %s", name, exc)
    rows: list[dict] = []
    for back in range(ANNOUNCEMENT_DAYS):
        day = (today - timedelta(days=back)).strftime("%d-%m-%Y")
        try:
            data = client._get(ANNOUNCEMENTS_ENDPOINT, {"index": "equities", "from_date": day, "to_date": day}).json()
        except SourceBlockedError:
            raise
        except Exception as exc:
            log.warning("NSE announcements for %s unavailable: %s", day, exc)
            continue
        got = data.get("data") if isinstance(data, dict) else data
        rows += got if isinstance(got, list) else []
    out.update(announcement_industries(rows))
    return out


def sync(settings, sink, client, sector_for, now: str, today) -> SyncReport:
    """Read NSE's equity list and industries, write the new and changed company rows."""
    equities = client.equity_list()
    rows, report = plan(equities, stored_companies(sink), nse_industries(client, today), sector_for, now)
    written = 0
    for at in range(0, len(rows), 200):
        written += sink.execute("companies_upsert", rows[at:at + 200])
    log.info("company master from NSE: %s (%d rows written)", report.as_dict(), written)
    return report
