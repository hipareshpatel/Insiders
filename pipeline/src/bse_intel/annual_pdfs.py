"""Keep companies' annual-report PDFs in R2, once (owner, 29 Oct 2026: "Save those 10 PDFs to R2 now"). No AI, no memory write.

A PDF test of the annual-report reader needs the reports; fetched by hand they are lost with the session, so a test downloads
them through this command instead, and every later test reads them from R2. NSE's annual-report list (PDFs, not XBRL):

    GET https://www.nseindia.com/api/annual-reports?index=equities&symbol=<SYMBOL>

whose rows name the year (``fromYr``, ``toYr``) and the file (``fileName``, on nsearchives). Each file is fetched with the
NSE client unchanged (its headers, pace, retries, a refusal stops the run; one file for the file cap) and kept, gzipped, at

    raw/annual-pdf/<SYMBOL>/<file name>.gz

A stored file is never fetched again. The size limit is the annual-report one (120 MB).
"""

from __future__ import annotations

import gzip

from .nse import SITE

PREFIX = "raw/annual-pdf/"
LIST = f"{SITE}/api/annual-reports"
MAX_BYTES = 120_000_000


def key(symbol: str, url: str) -> str:
    return f"{PREFIX}{symbol.upper()}/{url.rsplit('/', 1)[-1]}.gz"


def rows_for_year(rows: list[dict], to_year: str) -> list[str]:
    """The year's PDF addresses (``toYr`` = the year the report ends: "2026" for FY26), once each."""
    out = []
    for x in rows or []:
        url = (x.get("fileName") or "").strip()
        if str(x.get("toYr")) == str(to_year) and url.lower().endswith((".pdf", ".zip")) and url not in out:
            out.append(url)
    return out


def newest_year(rows: list[dict]) -> str | None:
    years = [str(x.get("toYr")) for x in rows or [] if str(x.get("toYr") or "").isdigit()]
    return max(years) if years else None


def newest_years(rows: list[dict], n: int) -> list[str]:
    years = sorted({str(x.get("toYr")) for x in rows or [] if str(x.get("toYr") or "").isdigit()}, reverse=True)
    return years[:n]


def run(sink, client, symbols: list[str], to_year: str | None = None, years: int = 1) -> dict:
    """``to_year`` None: each company's newest ``years`` reports (owner, 31 Oct 2026: two or three a company to drill into a gap)."""
    out = {"symbols": len(symbols), "listed": 0, "stored_before": 0, "downloaded": 0, "missing": 0, "not_listed": [], "bytes": 0,
           "kept": []}
    for symbol in symbols:
        stored = set(sink.list_objects(f"{PREFIX}{symbol.upper()}/"))
        data = client._get(LIST, {"index": "equities", "symbol": symbol.upper()}).json()
        rows = data.get("data") if isinstance(data, dict) else data
        rows = rows if isinstance(rows, list) else []
        wanted = [to_year] if to_year else newest_years(rows, max(1, years))
        urls = [u for y in wanted for u in rows_for_year(rows, y)]
        if not urls:
            out["not_listed"].append(symbol)
            continue
        for url in urls:
            out["listed"] += 1
            if key(symbol, url) in stored:
                out["stored_before"] += 1
                continue
            body = client.fetch(url, max_bytes=MAX_BYTES)
            if not body:
                out["missing"] += 1
                continue
            sink.put_object(key(symbol, url), gzip.compress(body, 6, mtime=0), content_type="application/gzip")
            out["downloaded"] += 1
            out["bytes"] += len(body)
            out["kept"].append({"symbol": symbol.upper(), "url": url, "bytes": len(body), "key": key(symbol, url)})
    return out
