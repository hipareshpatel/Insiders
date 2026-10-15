"""BSE corporate announcements client.

Endpoint and parameters mirror what https://www.bseindia.com/corporates/ann
itself calls (verified against the site's JS bundle, Oct 2026):

    GET https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w
        ?pageno=1&strCat=-1&strPrevDate=YYYYMMDD&strScrip=&strSearch=P
        &strToDate=YYYYMMDD&strType=C&subcategory=-1

The response carries rows in ``Table`` and the total in ``Table1[0].ROWCNT``.
Attachments live under ``/xml-data/corpfiling/AttachLive/`` (PDFFLAG 0) or
``/xml-data/corpfiling/AttachHis/`` (PDFFLAG 1).

The client opens a normal browser-like session: it loads the announcements
page first (cookies, Referer) and then queries the API. BSE's edge returns
403 to some networks regardless of headers (observed from a non-Indian
datacenter IP); that surfaces as ``SourceBlockedError`` with guidance rather
than a silent empty result.
"""

from __future__ import annotations

import logging
import random
import re
import threading
import time
from collections.abc import Iterator
from datetime import date

import httpx

from .models import Filing
from .timeutil import iso_ist, now_ist, parse_bse_datetime

log = logging.getLogger(__name__)

SITE = "https://www.bseindia.com"
WARMUP_URL = f"{SITE}/corporates/ann"
API_BASE = "https://api.bseindia.com/BseIndiaAPI/api"
ANN_ENDPOINT = f"{API_BASE}/AnnSubCategoryGetData/w"
ATTACH_LIVE = f"{SITE}/xml-data/corpfiling/AttachLive/"
ATTACH_HIS = f"{SITE}/xml-data/corpfiling/AttachHis/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


class SourceBlockedError(RuntimeError):
    """BSE refused the request (HTTP 403), usually because of the caller's network."""


class AttachmentError(RuntimeError):
    """One attachment could not be fetched (refused, server error, timeout). The filing is retried
    on a later run instead of being analysed from its headline alone."""

    def __init__(self, message: str, refused: bool = False):
        super().__init__(message)
        self.refused = refused


def xbrl_url(row: dict) -> str | None:
    """The filing's XBRL instance, when BSE lists one (results, shareholding patterns). BSE has used
    more than one field name for it; a bare file name is resolved like a PDF attachment. Whether a
    file really is XBRL is decided when it is parsed (xbrl.parse)."""
    for key in ("XBRL", "XBRL_URL", "XBRLURL", "XML_NAME", "XMLNAME"):
        value = str(row.get(key) or "").strip()
        if not value.lower().endswith(".xml"):
            continue
        if value.startswith("http"):
            return value
        return f"{SITE}/{value.lstrip('/')}" if "/" in value.strip("/") else ATTACH_LIVE + value.lstrip("/")
    return None


def attachment_url(attachment: str | None, pdf_flag: int | None) -> str | None:
    if not attachment:
        return None
    base = ATTACH_HIS if pdf_flag == 1 else ATTACH_LIVE
    return base + attachment.lstrip("/")


_NSURL_SLUG = re.compile(r"/stock-share-price/[^/]+/([^/]+)/(\d+)/?", re.I)


def _symbol_from_nsurl(nsurl: str | None) -> str | None:
    if not nsurl:
        return None
    match = _NSURL_SLUG.search(nsurl)
    return match.group(1).upper() if match else None


def parse_row(row: dict) -> Filing | None:
    news_id = (row.get("NEWSID") or "").strip()
    scrip = row.get("SCRIP_CD")
    if not news_id or scrip in (None, ""):
        return None
    filed = (
        parse_bse_datetime(row.get("DissemDT"))
        or parse_bse_datetime(row.get("NEWS_DT"))
        or parse_bse_datetime(row.get("DT_TM"))
        or now_ist()
    )
    pdf_flag = row.get("PDFFLAG")
    try:
        pdf_flag = int(pdf_flag) if pdf_flag is not None else None
    except (TypeError, ValueError):
        pdf_flag = None
    headline = (row.get("HEADLINE") or row.get("NEWSSUB") or "").strip()
    return Filing(
        news_id=news_id,
        scrip_code=str(scrip).strip(),
        company_name=(row.get("SLONGNAME") or "").strip() or str(scrip),
        symbol=_symbol_from_nsurl(row.get("NSURL")),
        headline=headline,
        subject=(row.get("NEWSSUB") or "").strip(),
        category=(row.get("CATEGORYNAME") or "").strip(),
        subcategory=(row.get("SUBCATNAME") or "").strip(),
        filed_at=iso_ist(filed),
        filing_date=filed.date().isoformat(),
        pdf_url=attachment_url(row.get("ATTACHMENTNAME"), pdf_flag),
        xbrl_url=xbrl_url(row),
        attachment_size=row.get("Fld_Attachsize"),
        critical=bool(row.get("CRITICALNEWS")),
    )


class BseClient:
    def __init__(self, timeout: float = 30.0, page_delay: float = 0.5, transport: httpx.BaseTransport | None = None,
                 download_delay: tuple[float, float] = (1.2, 2.0)):
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
        )
        self._page_delay = page_delay
        self._download_delay = download_delay  # polite pacing between attachments (blueprint §5.1)
        self._last_download = 0.0
        self._download_lock = threading.Lock()
        self._warmed = False

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BseClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def warm_up(self) -> None:
        if self._warmed:
            return
        try:
            self._client.get(WARMUP_URL, headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
        except httpx.HTTPError as exc:  # warm-up is best effort
            log.warning("BSE warm-up request failed: %s", exc)
        self._warmed = True

    def _get_json(self, url: str, params: dict) -> dict:
        self.warm_up()
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": SITE,
            "Referer": WARMUP_URL,
        }
        for attempt in range(4):
            try:
                resp = self._client.get(url, params=params, headers=headers)
            except httpx.TransportError as exc:
                if attempt == 3:
                    raise
                log.warning("BSE request error (%s), retrying", exc)
                time.sleep(2 ** (attempt + 1))
                continue
            if resp.status_code == 403:
                raise SourceBlockedError(
                    "BSE returned 403 Access Denied. BSE's edge blocks some networks "
                    "(seen from non-Indian datacenter IPs) regardless of headers. Run the "
                    "pipeline from an Indian network, e.g. a self-hosted GitHub Actions runner."
                )
            if resp.status_code >= 500 or resp.status_code == 429:
                if attempt == 3:
                    resp.raise_for_status()
                time.sleep(2 ** (attempt + 1))
                continue
            resp.raise_for_status()
            try:
                return resp.json()
            except ValueError:  # an HTML error page served with 200; treat like a server error
                if attempt == 3:
                    raise
                log.warning("BSE returned a non-JSON body, retrying")
                time.sleep(2 ** (attempt + 1))
        raise RuntimeError("unreachable")

    def announcements(self, day_from: date, day_to: date | None = None, category: str = "-1",
                      known: set[str] | None = None, max_pages: int = 400, scrip: str = "") -> Iterator[Filing]:
        """Yield every announcement disseminated between the two dates (inclusive).

        Pages come newest first. With ``known`` (news ids already recorded), paging stops at the
        first page that holds nothing new, so a run that re-reads today asks BSE for one or two
        pages instead of every page of the day.
        """
        day_to = day_to or day_from
        page, total = 1, None
        ids: set[str] = set()
        while page <= max_pages:
            data = self._get_json(ANN_ENDPOINT, {
                "pageno": page,
                "strCat": category,
                "strPrevDate": day_from.strftime("%Y%m%d"),
                "strScrip": scrip,
                "strSearch": "P",
                "strToDate": day_to.strftime("%Y%m%d"),
                "strType": "C",
                "subcategory": "-1",
            })
            rows = data.get("Table") or []
            if total is None:
                try:
                    total = int((data.get("Table1") or [{}])[0].get("ROWCNT") or 0)
                except (TypeError, ValueError):
                    total = 0
            if not rows:
                break
            fresh = unknown = 0
            for row in rows:
                filing = parse_row(row)
                if filing and filing.news_id not in ids:  # rows shift between pages while BSE adds filings
                    ids.add(filing.news_id)
                    fresh += 1
                    unknown += known is None or filing.news_id not in known
                    yield filing
            if total and len(ids) >= total:
                break
            if not fresh:
                break  # the same page again: BSE gave no row count and is repeating itself
            if not unknown:
                break  # everything on this page is already recorded, and older pages were too
            page += 1
            time.sleep(self._page_delay)

    def _pace_download(self) -> None:
        low, high = self._download_delay
        if high <= 0:
            return
        with self._download_lock:  # one pace for all worker threads
            wait = self._last_download + random.uniform(low, high) - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_download = time.monotonic()

    def download(self, url: str, max_bytes: int = 30_000_000) -> bytes | None:
        """Fetch an attachment; falls back between AttachLive and AttachHis.

        Returns None when the file does not exist (404 on both paths) or is too large to read.
        Raises AttachmentError when it exists but could not be fetched (403, 5xx, timeout), so the
        filing is retried later rather than analysed without its text.
        """
        self.warm_up()
        self._pace_download()
        candidates = [url]
        if ATTACH_LIVE in url:
            candidates.append(url.replace(ATTACH_LIVE, ATTACH_HIS))
        elif ATTACH_HIS in url:
            candidates.append(url.replace(ATTACH_HIS, ATTACH_LIVE))
        problem: AttachmentError | None = None
        for candidate in candidates:
            try:
                with self._client.stream("GET", candidate, headers={"Referer": WARMUP_URL}) as resp:
                    if resp.status_code == 404:
                        continue
                    if resp.status_code == 403:
                        problem = AttachmentError(f"BSE refused the attachment ({candidate})", refused=True)
                        continue
                    resp.raise_for_status()
                    chunks, size = [], 0
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            # A truncated PDF is unreadable (the xref table is at the end).
                            log.warning("Attachment over %d bytes, skipped: %s", max_bytes, candidate)
                            return None
                        chunks.append(chunk)
                    return b"".join(chunks)
            except httpx.HTTPError as exc:
                log.warning("Attachment download failed (%s): %s", candidate, exc)
                problem = AttachmentError(f"attachment download failed: {exc}")
        if problem:
            raise problem
        return None


SCRIP_LIST_ENDPOINT = f"{API_BASE}/ListofScripData_new/w"


def parse_scrip(row: dict) -> dict | None:
    """Map a row of BSE's scrip list to a companies row (fields vary; read defensively)."""
    def pick(*names):
        for name in names:
            value = row.get(name)
            if value not in (None, ""):
                return str(value).strip()
        return None

    scrip = pick("SCRIP_CD", "Scrip_Code", "scripcode")
    name = pick("Issuer_Name", "Scrip_Name", "SCRIP_NAME")
    if not scrip or not name:
        return None
    mktcap = pick("Mktcap", "MKTCAP", "MktCap")
    try:
        mktcap_value = float(mktcap.replace(",", "")) if mktcap else None
    except ValueError:
        mktcap_value = None
    return {
        "scrip_code": scrip,
        "company_name": name,
        "symbol": (pick("scrip_id", "SCRIP_ID") or "").upper() or None,
        "isin": pick("ISIN_NUMBER", "ISIN"),
        "industry": pick("INDUSTRY", "Industry", "industry"),
        "market_cap_cr": mktcap_value,
        "bse_group": (pick("GROUP", "Group", "SCRIP_GROUP", "scrip_group") or "").upper() or None,
    }


def fetch_scrip_list(client: BseClient, segment: str = "Equity", status: str = "Active") -> list[dict]:
    data = client._get_json(SCRIP_LIST_ENDPOINT, {
        "Group": "", "Scripcode": "", "segment": segment, "status": status, "scripName": "",
    })
    rows = data if isinstance(data, list) else data.get("Table", [])
    return [r for r in (parse_scrip(row) for row in rows) if r]
