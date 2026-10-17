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
import random
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime

import httpx

from .periods import canonical_period

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
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")
BLOCKING_STATUS = (401, 403, 429)


class SourceBlockedError(RuntimeError):
    """NSE refused the session (401, 403 or 429). Stop for this run rather than pressing on."""


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


def parse_results_rows(rows: list[dict]) -> list[ResultsFiling]:
    """NSE's rows, newest first, keeping only those that carry an XBRL instance."""
    out = []
    for row in rows:
        url = (row.get("xbrl") or "").strip()
        if not url:
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
        ))
    return sorted(out, key=lambda r: r.filed_at, reverse=True)


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
        consolidated = "consolidated" in str(row.get("consolidated") or "").lower()
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


class NseClient:
    def __init__(self, timeout: float = 45.0, pause: tuple[float, float] = (3.0, 5.0),
                 retries: int = 3, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*",
                     "Accept-Language": "en-US,en;q=0.9", "Referer": f"{SITE}/"},
        )
        self._pause = pause
        self._retries = max(1, retries)
        self._sleep = sleep
        self._lock = threading.Lock()
        self._calls = 0
        self._warmed = False

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

    def _wait(self) -> None:
        with self._lock:
            if self._calls:
                self._sleep(random.uniform(*self._pause))
            self._calls += 1

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        self.warm_up()
        last: Exception | None = None
        for _ in range(self._retries):
            self._wait()
            try:
                response = self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                last = exc
                continue
            if response.status_code in BLOCKING_STATUS:
                raise SourceBlockedError(
                    f"NSE refused the request (HTTP {response.status_code}) for {url}. NSE limits by IP address: "
                    "stop this run and try later rather than retrying.")
            if response.status_code >= 500:
                last = httpx.HTTPStatusError(f"HTTP {response.status_code}", request=response.request, response=response)
                continue
            response.raise_for_status()
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
                log.info("NSE integrated filings unavailable for %s (%s); using the older list", symbol, exc)
        data = self._get(RESULTS_ENDPOINT, {"index": "equities", "symbol": symbol.strip().upper(),
                                            "period": "Quarterly" if quarterly else "Annual"}).json()
        out.extend(parse_results_rows(data if isinstance(data, list) else []))
        seen: set[str] = set()
        unique = [f for f in out if not (f.xbrl_url in seen or seen.add(f.xbrl_url))]
        return sorted(unique, key=lambda f: f.filed_at, reverse=True)

    def download(self, url: str, max_bytes: int = 8_000_000) -> bytes | None:
        """One XBRL file. None when NSE serves something that is not XML."""
        response = self._get(url)
        body = response.content[:max_bytes]
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
