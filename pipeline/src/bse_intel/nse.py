"""NSE client for the structured filings BSE does not expose.

BSE's announcement feed carries PDFs only: 0 of 1,166 rows had an XBRL link (tracker F50), so the
shareholding fast path never fired and ownership history came from text the model read. NSE publishes
the same companies' XBRL as downloadable XML, and our own parser reads it unchanged:

    GET /api/corporate-share-holdings-master?index=equities&symbol=<SYMBOL>
        -> one row per quarter (20 quarters for Ahluwalia, back to Sep 2021), each with a direct
           `xbrl` link to nsearchives.nseindia.com/corporate/xbrl/SHP_*.xml, plus the quarter end,
           ISIN, promoter and public percentages and the revision fields.

2,480 of our 5,111 companies are listed on NSE: 77% of those above ₹100 Cr, 96% above ₹1,000 Cr.
BSE-only companies (almost all micro caps) keep having no structured ownership history.

The client is deliberately polite, as NSE rate-limits by IP: one browser identity, a warm-up visit
for cookies, 3-5 s between calls, a few retries on network errors and 5xx, and a hard stop on
401/403/429 (pressing on gets the address blocked for longer).
"""

from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
from urllib.parse import urlparse
from dataclasses import dataclass
from datetime import date, datetime

import csv
import html
import io

import httpx

from .bse import AttachmentError, AttachmentTooLarge
from .file_cap import files
from .bse import SourceBlockedError as _SourceBlocked
from .models import Filing
from .periods import canonical_period
from .timeutil import IST, iso_ist

log = logging.getLogger(__name__)

SITE = "https://www.nseindia.com"
SHAREHOLDING_ENDPOINT = f"{SITE}/api/corporate-share-holdings-master"
# Results XBRL, where BSE's own archive will not serve it: BSE's NBFCUploadDocument path
# returns its homepage to a plain fetch and nothing to ours, so Bajaj Finance and Max Financial
# had no machine-tagged figures at all. NSE lists the same quarters and they parse with the tag
# map already here - 0 bytes against 23 metrics, measured 2026-10-16.
RESULTS_ENDPOINT = f"{SITE}/api/corporates-financial-results"
# SEBI's Integrated Filing replaced the standalone results filing for quarters from March 2025, which is
# why the list above stops there and why a 2025-on NBFC appeared to have no machine-tagged results at all.
# NSE kept both surfaces: the old page for what was filed the old way (and for SME, debt and REIT/InvIT,
# which still are), a new one for the integrated format. We read both and merge them, so a company's
# history does not break at the changeover.
INTEGRATED_ENDPOINT = f"{SITE}/api/integrated-filing-results"
INTEGRATED_FINANCIALS = "Integrated Filing- Financials"
# An annual report's financial statements as filed with MCA, one XBRL instance per year and basis (annual_xbrl.py).
# Read from the "Annual Reports XBRL" page's own call on 2026-10-18.
ANNUAL_REPORT_ENDPOINT = f"{SITE}/api/annual-reports-xbrl"
ANNUAL_REPORT_MAX_BYTES = 40_000_000   # 2.5-4.5 MB for the smoke-test companies; a large group's runs longer
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")
BLOCKING_STATUS = (401, 403, 429)
# Every company listed on NSE's main board, one row each: symbol, name, series, listing date, ISIN.
# Measured 2026-10-18: 2,605 rows; 2,477 of them are among our 5,111 companies by ISIN.
EQUITY_LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
# NSE Emerge (SME platform) list, same shape with underscores in the headers (measured 2026-10-25: 582 rows, series ST/SM).
SME_LIST_URL = "https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv"
ENCUMBRANCE_ENDPOINT = "https://www.nseindia.com/api/corporate-pledgedata-sast3132"
LARGE_DEALS_ENDPOINT = "https://www.nseindia.com/api/snapshot-capital-market-largedeal"
PIT_ENDPOINT = "https://www.nseindia.com/api/corporates-pit-gg"
DEALS_HISTORY_ENDPOINT = "https://www.nseindia.com/api/historicalOR/bulk-block-short-deals"
# Every announcement of a day (about 500-600 on a weekday, measured 12-16 Oct 2026), all in one answer, each
# with its PDF and whether event XBRL exists. Read from the "Corporate Filings - Announcements" page's own call.
ANNOUNCEMENTS_ENDPOINT = f"{SITE}/api/corporate-announcements"
NEWS_ID_PREFIX = "nse-"
# Event XBRL files (Reg 30: orders, litigation, actions, director changes...), listed by type; event_xbrl.py
EVENT_XBRL_ENDPOINT = f"{SITE}/api/XBRL-announcements"


class SourceBlockedError(_SourceBlocked):
    """NSE refused the session (401, 403 or 429). Stop for this run rather than pressing on. A kind of BSE's
    error of the same name, so the pipeline stops on either source the same way."""


class FileCapReached(SourceBlockedError):
    """The run has downloaded its FILE_CAP NSE/BSE files (file_cap.py, F213). Not a refusal: callers stop their loop, leave
    the rest queued, spend no attempt and mark nothing tried or failed; the next run goes on."""


def stop_reason(exc: SourceBlockedError) -> str:
    """The report line for a stop on this error: the file cap (F213) is a planned stop, not a refusal, and the command's
    exit code (75 for "NSE refused") must not read it as one."""
    if isinstance(exc, FileCapReached):
        return "file cap reached: the rest waits for the next run"
    return f"NSE refused the session: {exc}"


@dataclass(frozen=True)
class Equity:
    """One company on NSE's main-board equity list."""

    symbol: str
    name: str
    isin: str
    series: str = ""
    listed_on: str | None = None   # ISO date


def parse_equity_list(text: str) -> list[Equity]:
    """NSE's EQUITY_L.csv. Its headers carry stray spaces (" ISIN NUMBER"), so they are stripped."""
    out: list[Equity] = []
    for row in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        row = {(k or "").strip().upper(): (v or "").strip() for k, v in row.items()}
        symbol, isin = row.get("SYMBOL", "").upper(), row.get("ISIN NUMBER", "").upper()
        if not symbol or not isin:
            continue
        listed = None
        try:
            listed = datetime.strptime(row.get("DATE OF LISTING", ""), "%d-%b-%Y").date().isoformat()
        except ValueError:
            pass
        out.append(Equity(symbol, row.get("NAME OF COMPANY", ""), isin, row.get("SERIES", ""), listed))
    return out


def parse_sme_list(text: str) -> list[Equity]:
    """NSE Emerge's SME_EQUITY_L.csv ("SYMBOL,NAME_OF_COMPANY,SERIES,DATE_OF_LISTING,...,ISIN_NUMBER,...")."""
    out: list[Equity] = []
    for row in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        row = {(k or "").strip().upper().replace("_", " "): (v or "").strip() for k, v in row.items()}
        symbol, isin = row.get("SYMBOL", "").upper(), row.get("ISIN NUMBER", "").upper()
        if symbol and isin:
            out.append(Equity(symbol, row.get("NAME OF COMPANY", ""), isin, row.get("SERIES", "")))
    return out


def _nse_datetime(value: str | None) -> datetime | None:
    """NSE's announcement times: "17-Oct-2026 13:37:56" (an_dt) or "2026-10-17 13:37:56" (sort_date), IST."""
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%b-%Y"):
        try:
            return datetime.strptime((value or "").strip(), fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def parse_announcement(row: dict, scrip_for) -> Filing | None:
    """One row of /api/corporate-announcements as a Filing.

    ``scrip_for(isin, symbol)`` gives our company key (the BSE scrip code the company table is keyed by) or None for a
    company not in the master; such a filing gets ``NSE:<symbol>`` so it can be set aside with its reason. NSE's own
    subject (``desc``, e.g. "Bagging/Receiving of orders/contracts") stands where BSE's subcategory stood, so the
    rule book's subcategory lists match it; the exchange's one-line summary (``attchmntText``) is the headline."""
    seq = str(row.get("seq_id") or "").strip()
    symbol = (row.get("symbol") or "").strip().upper()
    if not seq or not symbol:
        return None
    filed = _nse_datetime(row.get("an_dt")) or _nse_datetime(row.get("sort_date"))
    if filed is None:
        return None
    desc = html.unescape(row.get("desc") or "").strip()
    text = " ".join(html.unescape(row.get("attchmntText") or "").split())
    isin = (row.get("sm_isin") or "").strip().upper() or None
    scrip = scrip_for(isin, symbol)
    attachment = (row.get("attchmntFile") or "").strip() or None
    return Filing(
        news_id=f"{NEWS_ID_PREFIX}{seq}",
        scrip_code=scrip or f"NSE:{symbol}",
        company_name=(row.get("sm_name") or "").strip() or symbol,
        symbol=symbol,
        headline=text or desc,
        subject=desc,
        category="",
        subcategory=desc,
        filed_at=iso_ist(filed),
        filing_date=filed.date().isoformat(),
        pdf_url=attachment if attachment and attachment != "-" else None,
        attachment_size=row.get("attFileSize") or row.get("fileSize"),
        has_xbrl=bool(row.get("hasXbrl")),
    )


@dataclass(frozen=True)
class ShareholdingFiling:
    """One quarter's shareholding pattern as the master list describes it."""

    symbol: str
    period: str              # Q2FY27
    quarter_end: str         # 2026-09-30
    xbrl_url: str
    filed_at: str            # ISO, the broadcast time
    isin: str | None = None
    promoter_pct: float | None = None   # as the list states it, for a cross-check against the XBRL
    public_pct: float | None = None
    revised: bool = False


def _float(value) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _nse_date(value: str | None) -> date | None:
    """"30-JUN-2026" or "09-JUL-2026 11:19:39" as a date."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text.split()[0], "%d-%b-%Y").date()
    except ValueError:
        return None


def _iso(day: date | None) -> str:
    return day.isoformat() if day else ""


@dataclass(frozen=True)
class ResultsFiling:
    """One row of NSE's financial-results list: the XBRL instance and what it covers."""

    period: str          # as NSE words it, e.g. "Quarterly"
    consolidated: bool
    audited: str
    filed_at: str        # ISO date, best effort from the broadcast or filing date
    xbrl_url: str
    is_bank: bool
    period_end: str = ""     # ISO date of the quarter end, where the row states it
    taxonomy: str = ""       # INDAS, NBFC_INDAS, BANKING, GI or LI, from the file name
    revised: bool = False
    legacy: bool = False     # from the older results list (before the integrated filing): the seed reads it, cards do not


def parse_results_rows(rows: list[dict]) -> list[ResultsFiling]:
    """NSE's rows, newest first, keeping only those that carry an XBRL instance."""
    out = []
    for row in rows:
        url = (row.get("xbrl") or "").strip()
        if not url.lower().endswith(".xml"):   # NSE's older list writes ".../corporate/xbrl/-" when there is no file
            continue
        if not url.startswith("http"):
            url = f"https://nsearchives.nseindia.com/{url.lstrip('/')}"
        filed = _nse_date(row.get("filingDate") or row.get("broadCastDate") or row.get("exchdisstime"))
        out.append(ResultsFiling(
            period=str(row.get("period") or row.get("cumulative") or "").strip(),
            consolidated="non" not in str(row.get("consolidated") or "").lower()
            and "consolidated" in str(row.get("consolidated") or "").lower(),
            audited=str(row.get("audited") or "").strip(),
            filed_at=filed.isoformat() if filed else "",
            xbrl_url=url,
            is_bank=str(row.get("bank") or "").strip().lower() in ("yes", "true", "1"),
            # the quarter end, which the seed needs to reach the years before the integrated filing (deep audit A-02,
            # 2026-10-21: without it the seed stopped at Q4FY25)
            period_end=_iso(_nse_date(row.get("toDate"))),
            legacy=True,
        ))
    return sorted(out, key=lambda r: r.filed_at, reverse=True)


def results_links(filings: list[ResultsFiling]) -> list:
    """NSE's results files as the pipeline's quarter links (bse.XbrlLink: period, basis, url, filed_at), so an NSE
    filing finds its file, and its year-ago and previous-quarter files, as a BSE one did. Rows without a quarter end
    (the older results list) are left out: the integrated filing covers every quarter since December 2024."""
    from .bse import XbrlLink

    out = []
    for f in filings:
        if not f.period_end or f.legacy:
            continue
        end = date.fromisoformat(f.period_end)
        period = canonical_period(f"quarter ended {end:%d.%m.%Y}")
        if period.startswith("Q"):
            out.append(XbrlLink(period, "CONSOLIDATED" if f.consolidated else "STANDALONE", f.xbrl_url, f.filed_at))
    return out


_INTEGRATED_NAME = re.compile(r"INTEGRATED_FILING_(.+?)_\d+_\d{14}_", re.I)


def parse_integrated_rows(rows: list[dict]) -> list[ResultsFiling]:
    """The Integrated Filing list as filings, newest first.

    A revision supersedes the original for the same quarter and basis - NSE lists both, and the original
    is the one with the mistake the revision was filed to correct.
    """
    best: dict[tuple[str, bool], ResultsFiling] = {}
    for row in rows:
        url = (row.get("xbrl") or "").strip()
        quarter_end = _nse_date(row.get("qe_Date"))
        if not url.lower().endswith(".xml") or not quarter_end:
            continue
        if not url.startswith("http"):
            url = f"https://nsearchives.nseindia.com/{url.lstrip('/')}"
        basis = str(row.get("consolidated") or "").lower()
        # "Consolidated" or "Standalone" (measured 2026-10-18: 380 and 620 of 1,000); "Non-Consolidated" is standalone
        consolidated = "consolidated" in basis and "non" not in basis
        filed = _nse_date(row.get("broadcast_Date")) or _nse_date(row.get("revised_Date"))             or _nse_date(row.get("creation_Date")) or quarter_end
        family = _INTEGRATED_NAME.search(url)
        filing = ResultsFiling(
            period="Quarterly",
            consolidated=consolidated,
            audited=str(row.get("audited") or "").strip(),
            filed_at=filed.isoformat(),
            xbrl_url=url,
            is_bank=bool(family) and family.group(1).upper() == "BANKING",
            period_end=quarter_end.isoformat(),
            taxonomy=family.group(1).upper() if family else "",
            revised=str(row.get("type_Sub") or "").strip().lower() == "revision",
        )
        key = (filing.period_end, consolidated)
        kept = best.get(key)
        if kept is None or (filing.revised and not kept.revised) or                 (filing.revised == kept.revised and filing.filed_at > kept.filed_at):
            best[key] = filing
    return sorted(best.values(), key=lambda f: (f.period_end, f.filed_at), reverse=True)


@dataclass(frozen=True)
class AnnualReportFiling:
    """One row of NSE's annual-report XBRL list: the statements of one financial year on one basis."""

    from_year: int
    to_year: int         # the year the financial year ends in: 2025 for 2024-25
    basis: str           # CONSOLIDATED or STANDALONE
    filed_at: str        # ISO, the broadcast time
    xbrl_url: str
    report_type: str = ""


def parse_annual_report_rows(rows: list[dict]) -> list[AnnualReportFiling]:
    """The list's rows, newest year first. A file filed again for the same year and basis supersedes the
    earlier one (the later broadcast wins)."""
    best: dict[tuple[int, str], AnnualReportFiling] = {}
    for row in rows:
        url = str(row.get("fileName") or "").strip()
        basis = str(row.get("submission_type") or "").strip().upper()
        try:
            years = int(str(row.get("fromYr")).strip()), int(str(row.get("toYr")).strip())
        except ValueError:
            continue
        if not url.lower().endswith(".xml") or basis not in ("CONSOLIDATED", "STANDALONE"):
            continue
        try:
            filed = datetime.strptime(str(row.get("broadcast_dttm") or "").strip(), "%d-%b-%Y %H:%M:%S")
        except ValueError:
            filed = None
        filing = AnnualReportFiling(
            from_year=years[0], to_year=years[1], basis=basis,
            filed_at=filed.strftime("%Y-%m-%dT%H:%M:%S+05:30") if filed else "",
            xbrl_url=url if url.startswith("http") else f"https://nsearchives.nseindia.com/{url.lstrip('/')}",
            report_type=str(row.get("report_type") or "").strip())
        kept = best.get((filing.to_year, basis))
        if kept is None or filing.filed_at > kept.filed_at:
            best[(filing.to_year, basis)] = filing
    return sorted(best.values(), key=lambda f: (f.to_year, f.basis), reverse=True)


def parse_shareholding_rows(rows: list[dict]) -> list[ShareholdingFiling]:
    """The master list's rows as filings, newest quarter first. A revised filing supersedes the
    original for the same quarter (NSE lists both)."""
    best: dict[str, ShareholdingFiling] = {}
    for row in rows:
        quarter_end = _nse_date(row.get("date"))
        url = str(row.get("xbrl") or "").strip()
        if not quarter_end or not url.lower().endswith(".xml"):
            continue
        period = canonical_period(f"quarter ended {quarter_end:%d.%m.%Y}")
        filed = _nse_date(row.get("broadcastDate")) or _nse_date(row.get("submissionDate")) or quarter_end
        filing = ShareholdingFiling(
            symbol=str(row.get("symbol") or "").strip().upper(),
            period=period,
            quarter_end=quarter_end.isoformat(),
            xbrl_url=url if url.startswith("http") else f"https://nsearchives.nseindia.com/{url.lstrip('/')}",
            filed_at=f"{filed.isoformat()}T00:00:00+05:30",
            isin=str(row.get("isin") or "").strip() or None,
            promoter_pct=_float(row.get("pr_and_prgrp")),
            public_pct=_float(row.get("public_val")),
            revised=str(row.get("revisedData") or "").strip().upper() == "Y"
            or str(row.get("revisedStatus") or "").strip().lower() == "revised",
        )
        kept = best.get(period)
        if kept is None or (filing.revised and not kept.revised) or filing.filed_at > kept.filed_at:
            best[period] = filing
    return sorted(best.values(), key=lambda f: f.quarter_end, reverse=True)


def pause_from_env() -> tuple[float, float]:
    """Seconds between two NSE requests: 3-5 by default; NSE_PAUSE_SECONDS="1.5,2.5" sets another range for a
    one-off bulk load on the laptop (the go-live history). The daily path keeps the default."""
    try:
        low, high = (float(x) for x in os.environ.get("NSE_PAUSE_SECONDS", "").split(","))
    except ValueError:
        return (3.0, 5.0)
    return (low, high) if 1.0 <= low <= high else (3.0, 5.0)


ARCHIVE_HOST = "nsearchives.nseindia.com"
ARCHIVE_REFUSALS = (403, 429, 503)


def archive_pause_from_env() -> tuple[float, float] | None:
    """Seconds between two requests to the archive host (nsearchives): NSE_ARCHIVE_PAUSE_SECONDS="0,0" (same "low,high"
    form as NSE_PAUSE_SECONDS, 0 allowed). None when unset or malformed: the archive then shares the API's pace and
    lock, exactly as before (F169)."""
    try:
        low, high = (float(x) for x in os.environ.get("NSE_ARCHIVE_PAUSE_SECONDS", "").split(","))
    except ValueError:
        return None
    return (low, high) if 0.0 <= low <= high else None


def _is_archive(url: str | None) -> bool:
    return bool(url) and (urlparse(url).hostname or "").lower() == ARCHIVE_HOST


class NseClient:
    def __init__(self, timeout: float = 45.0, pause: tuple[float, float] | None = None,
                 retries: int = 3, transport: httpx.BaseTransport | None = None, sleep=time.sleep,
                 archive_pause: tuple[float, float] | None = None):
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*",
                     "Accept-Language": "en-US,en;q=0.9", "Referer": f"{SITE}/"},
        )
        self._pause = pause or pause_from_env()
        self._retries = max(1, retries)
        self._sleep = sleep
        self._lock = threading.Lock()
        self._calls = 0
        # the archive host's own pace, lock and counter; None = it shares the API's (today's behaviour). A refusal from
        # the archive host sets it back to None for the rest of the run (_note_refusal)
        self._archive_pause = archive_pause if archive_pause is not None else archive_pause_from_env()
        self._archive_lock = threading.Lock()
        self._archive_calls = 0
        self._warmed = False
        self.raw = None  # a raw.RawStore: every JSON answer is saved as received, before it is parsed
        self.integrated_failed: set[str] = set()   # symbols whose integrated list failed in financial_results (older list only)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NseClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def warm_up(self) -> None:
        """One visit to the site for cookies. Best effort: the APIs answered a 403 warm-up anyway."""
        if self._warmed:
            return
        self._warmed = True
        try:
            self._client.get(f"{SITE}/", headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
        except httpx.HTTPError as exc:
            log.info("NSE warm-up request failed (%s); continuing", exc)

    def _wait(self, url: str | None = None) -> None:
        pause = self._archive_pause
        if pause is not None and _is_archive(url):
            with self._archive_lock:
                if self._archive_calls and pause[1] > 0:
                    self._sleep(random.uniform(*pause))
                self._archive_calls += 1
            return
        with self._lock:
            if self._calls:
                self._sleep(random.uniform(*self._pause))
            self._calls += 1

    def _note_refusal(self, url: str, status: int) -> None:
        """A 403, 429 or 503 from the archive host while it runs on its own fast pace: back to the API's pace (3-5 s, and
        its lock, so one request at a time) for the rest of the run. A 404 is a missing file, not a refusal."""
        if status in ARCHIVE_REFUSALS and _is_archive(url) and self._archive_pause is not None:
            self._archive_pause = None
            log.warning("NSE archive host answered HTTP %s: archive pace back to the API pace (%s s) for the rest of "
                        "this run", status, "-".join(f"{x:g}" for x in self._pause))

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        self.warm_up()
        last: Exception | None = None
        for _ in range(self._retries):
            self._wait(url)
            try:
                response = self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                last = exc
                continue
            self._note_refusal(url, response.status_code)
            if response.status_code in BLOCKING_STATUS:
                raise SourceBlockedError(
                    f"NSE refused the request (HTTP {response.status_code}) for {url}. NSE limits by IP address: "
                    "stop this run and try later rather than retrying.")
            if response.status_code >= 500:
                last = httpx.HTTPStatusError(f"HTTP {response.status_code}", request=response.request, response=response)
                continue
            response.raise_for_status()
            if self.raw is not None and "json" in response.headers.get("content-type", ""):
                self.raw.save(url, params, response.status_code, response.content)
            return response
        raise RuntimeError(f"NSE request failed after {self._retries} attempts: {last}")

    def shareholding(self, symbol: str, since: str | None = None) -> list[ShareholdingFiling]:
        """Every shareholding pattern NSE lists for the symbol, newest quarter first.
        `since` is an ISO date; quarters ending before it are left out."""
        data = self._get(SHAREHOLDING_ENDPOINT, {"index": "equities", "symbol": symbol.strip().upper()}).json()
        rows = data.get("data") if isinstance(data, dict) else data
        filings = parse_shareholding_rows(rows if isinstance(rows, list) else [])
        return [f for f in filings if not since or f.quarter_end >= since]

    def integrated_filings(self, symbol: str) -> list[ResultsFiling]:
        """The symbol's Integrated Filing (Financials) XBRL, newest quarter first. This is the current
        format: banks, NBFCs and insurers all file here, each on its own SEBI template."""
        data = self._get(INTEGRATED_ENDPOINT, {"symbol": symbol.strip().upper(),
                                               "type": INTEGRATED_FINANCIALS, "page": 1, "size": 50}).json()
        rows = data.get("data") if isinstance(data, dict) else data
        return parse_integrated_rows(rows if isinstance(rows, list) else [])

    def financial_results(self, symbol: str, quarterly: bool = True) -> list[ResultsFiling]:
        """Every results XBRL NSE lists for the symbol, newest first, from both surfaces. Used only as a
        fallback: BSE's own archive is the first source, and this fills the templates it will not serve
        (NBFC, banking, life and general insurance)."""
        out: list[ResultsFiling] = []
        if quarterly:
            try:
                out.extend(self.integrated_filings(symbol))
            except SourceBlockedError:
                raise
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                # the older list has no quarter since December 2024: a caller that needs them (the seed) reads this
                self.integrated_failed.add(symbol.strip().upper())
                log.info("NSE integrated filings unavailable for %s (%s); using the older list", symbol, exc)
        data = self._get(RESULTS_ENDPOINT, {"index": "equities", "symbol": symbol.strip().upper(),
                                            "period": "Quarterly" if quarterly else "Annual"}).json()
        out.extend(parse_results_rows(data if isinstance(data, list) else []))
        seen: set[str] = set()
        unique = [f for f in out if not (f.xbrl_url in seen or seen.add(f.xbrl_url))]
        return sorted(unique, key=lambda f: f.filed_at, reverse=True)

    def annual_reports(self, symbol: str) -> list[AnnualReportFiling]:
        """Every annual-report XBRL NSE lists for the symbol (both bases), newest year first."""
        data = self._get(ANNUAL_REPORT_ENDPOINT, {"index": "equities", "symbol": symbol.strip().upper()}).json()
        rows = data.get("data") if isinstance(data, dict) else data
        return parse_annual_report_rows(rows if isinstance(rows, list) else [])

    def equity_list(self) -> list[Equity]:
        """NSE's main-board equity list (the universe's starting point; universe.build_nse)."""
        return parse_equity_list(self._get(EQUITY_LIST_URL).text)

    def sme_list(self) -> list[Equity]:
        """NSE Emerge's SME list (prune-companies tells an SME scrip from a BSE-only one)."""
        return parse_sme_list(self._get(SME_LIST_URL).text)

    def announcements(self, day_from: date, day_to: date | None = None, symbol: str | None = None,
                      scrip_for=lambda isin, symbol: None) -> list[Filing]:
        """Every announcement NSE disseminated between the two dates (inclusive), newest first. NSE answers a whole
        range at once; without a symbol, ask for one day at a time (a day is about 400 KB)."""
        params = {"index": "equities", "from_date": day_from.strftime("%d-%m-%Y"),
                  "to_date": (day_to or day_from).strftime("%d-%m-%Y")}
        if symbol:
            params["symbol"] = symbol.strip().upper()
        data = self._get(ANNOUNCEMENTS_ENDPOINT, params).json()
        rows = data.get("data") if isinstance(data, dict) else data
        seen: set[str] = set()
        out: list[Filing] = []
        for row in rows if isinstance(rows, list) else []:
            filing = parse_announcement(row, scrip_for)
            if filing and filing.news_id not in seen:
                seen.add(filing.news_id)
                out.append(filing)
        return out

    def shareholding_list(self, day_from: date, day_to: date) -> list[ShareholdingFiling]:
        """Every company's shareholding patterns broadcast between the two dates, the latest per company and quarter
        (measured 2026-10-19: 1,651 rows for 1-18 Oct 2026, every one with its XBRL)."""
        data = self._get(SHAREHOLDING_ENDPOINT, {"index": "equities", "from_date": day_from.strftime("%d-%m-%Y"),
                                                 "to_date": day_to.strftime("%d-%m-%Y")}).json()
        rows = data.get("data") if isinstance(data, dict) else data
        by_symbol: dict[str, list[dict]] = {}
        for row in rows if isinstance(rows, list) else []:
            by_symbol.setdefault(str(row.get("symbol") or "").strip().upper(), []).append(row)
        return [f for symbol, group in by_symbol.items() if symbol for f in parse_shareholding_rows(group)]

    def encumbrances(self, day_from: date, day_to: date) -> list[dict]:
        """SAST Regulation 31 encumbrance disclosures of every company broadcast between the two dates, as NSE's rows
        (pledges.py; measured 2026-10-19: 40 rows for 1-19 Oct, one per promoter event)."""
        data = self._get(ENCUMBRANCE_ENDPOINT, {"from_date": day_from.strftime("%d-%m-%Y"), "to_date": day_to.strftime("%d-%m-%Y")}).json()
        rows = data.get("data") if isinstance(data, dict) else data
        return rows if isinstance(rows, list) else []

    def large_deals(self) -> dict:
        """The latest session's bulk, block and short-selling deals as NSE's lists (deals.py; measured 22 Oct 2026 from
        the Actions runner: BULK_DEALS_DATA 111, BLOCK_DEALS_DATA 4, SHORT_DEALS_DATA 99 rows)."""
        data = self._get(LARGE_DEALS_ENDPOINT).json()
        return data if isinstance(data, dict) else {}

    def insider_filings(self, day_from: date, day_to: date) -> list[dict]:
        """SEBI PIT Regulation 7 disclosures broadcast between the two dates, one row per filing with its XBRL file
        (`xmlFileName`) (insider.py; measured 23 Oct 2026 from a cloud session: 9 filings for 20-22 Oct, and 3,204 for
        Aug-Oct without dates, every one with its XBRL)."""
        data = self._get(PIT_ENDPOINT, {"index": "equities", "from_date": day_from.strftime("%d-%m-%Y"),
                                        "to_date": day_to.strftime("%d-%m-%Y")}).json()
        rows = data.get("data") if isinstance(data, dict) else data
        return rows if isinstance(rows, list) else []

    def deals_history(self, kind: str, day_from: date, day_to: date) -> str:
        """NSE's bulk or block deals (``kind`` "bulk_deals" or "block_deals") between the two dates as its CSV (deals.py
        backfill; measured 22 Oct 2026 from the Actions runner: 696 bulk and 17 block lines for 7 days)."""
        return self._get(DEALS_HISTORY_ENDPOINT, {"optionType": kind, "from": day_from.strftime("%d-%m-%Y"),
                                                  "to": day_to.strftime("%d-%m-%Y"), "csv": "true"}).text

    def integrated_list(self, kind: str, page: int = 1, size: int = 500) -> list[dict]:
        """One page of NSE's all-company integrated-filing list ("Integrated Filing- Financials" or "...- Governance"),
        newest first, as NSE's rows (measured 2026-10-18: up to 1,000 rows a page honoured)."""
        data = self._get(INTEGRATED_ENDPOINT, {"type": kind, "page": page, "size": size}).json()
        rows = data.get("data") if isinstance(data, dict) else data
        return rows if isinstance(rows, list) else []

    def event_xbrl(self, kind: str, day_from: date, day_to: date | None = None, symbol: str | None = None) -> list:
        """NSE's event XBRL files of one type ("announcements", "para-b", "action") broadcast between the two dates
        (event_xbrl.py). One answer for the range, as the "Announcements XBRL" tab asks for it."""
        from . import event_xbrl

        params = {"index": "equities", "from_date": day_from.strftime("%d-%m-%Y"),
                  "to_date": (day_to or day_from).strftime("%d-%m-%Y"), "type": kind}
        if symbol:
            params["symbol"] = symbol.strip().upper()
        data = self._get(EVENT_XBRL_ENDPOINT, params).json()
        return event_xbrl.parse_list(data.get("data") if isinstance(data, dict) else data, kind)

    def fetch(self, url: str, max_bytes: int = 30_000_000) -> bytes | None:
        """An announcement's attachment (PDF, sometimes a ZIP) from nsearchives. None when it does not exist;
        AttachmentTooLarge when it is larger than ``max_bytes`` (a truncated PDF is unreadable). A refusal stops the run (SourceBlockedError); a
        network failure raises AttachmentError, so the filing is tried again rather than read without its text.
        One file for the file cap (file_cap.py, F213); past it FileCapReached."""
        files.take(url)
        self.warm_up()
        problem: Exception | None = None
        for _ in range(self._retries):
            self._wait(url)
            try:
                with self._client.stream("GET", url) as resp:
                    if resp.status_code == 404:
                        return None
                    self._note_refusal(url, resp.status_code)
                    if resp.status_code in BLOCKING_STATUS:
                        raise SourceBlockedError(f"NSE refused the attachment (HTTP {resp.status_code}): {url}")
                    if resp.status_code >= 500:
                        problem = AttachmentError(f"NSE answered HTTP {resp.status_code} for {url}")
                        continue
                    resp.raise_for_status()
                    chunks, size = [], 0
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            log.warning("Attachment over %d bytes, skipped: %s", max_bytes, url)
                            raise AttachmentTooLarge(url, max_bytes)
                        chunks.append(chunk)
                    return b"".join(chunks)
            except httpx.HTTPError as exc:
                problem = AttachmentError(f"attachment download failed: {exc}")
        raise problem or AttachmentError(f"attachment download failed: {url}")

    def download(self, url: str, max_bytes: int = 8_000_000) -> bytes | None:
        """One XBRL file. None when NSE serves something that is not XML, or a file over ``max_bytes``.
        One file for the file cap (file_cap.py, F213); past it FileCapReached."""
        files.take(url)
        response = self._get(url)
        body = response.content
        if len(body) > max_bytes:
            # cut at the cap it was well-formed at its start and failed later as a parse error; a file this large is
            # skipped as the PDF downloads are
            log.warning("XBRL file over %d bytes, skipped: %s", max_bytes, url)
            return None
        return body if body.lstrip()[:200].lower().lstrip(b"\xef\xbb\xbf").startswith((b"<?xml", b"<xbrl")) else None


_SHP_NAME = re.compile(r"SHP_\d+_(\d{14})_", re.I)


def shareholding_filed_at(url: str) -> str | None:
    """The upload time encoded in an SHP file name ("SHP_1689543_09072026111935_WEB.xml")."""
    m = _SHP_NAME.search(url or "")
    if not m:
        return None
    try:
        stamp = datetime.strptime(m.group(1), "%d%m%Y%H%M%S")
    except ValueError:
        return None
    return stamp.strftime("%Y-%m-%dT%H:%M:%S+05:30")
