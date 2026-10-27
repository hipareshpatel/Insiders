"""Read-only speed measurement of NSE's two hosts (F168, owner 26 Oct 2026: "if we are getting it from the NSE archive
site, I think there is no stopping there; test with 100 companies as a sample").

Why: a full memory reload downloads ~40,000 results XBRL files, one request at a time with a 3-5 s pause before EVERY
request (``NseClient._wait``: one lock, one counter, both hosts, so parallel workers would still queue). The two hosts
may not behave the same: www.nseindia.com/api (listing a company's files) is known to refuse; nsearchives.nseindia.com
(the files) is believed not to throttle. This measures it and writes nothing: no D1, no R2, no memory, no cache.

1. a seeded sample of universe companies; 2. their file links listed as the seed lists them (NseClient.financial_results,
normal pacing), timed per company, and the same companies read from NSE's all-company list (integrated_list) when it
answers; 3. downloads from nsearchives only, in rounds on different files, at a shrinking pause (A 3-5 s as today, B 1 s,
C 0.3 s, D 0 s, E four parallel workers at 0 s), each file kept only long enough to check it is complete XML; a round stops
at the first 403/429/503 or the third timeout, waits 60 s, and no faster round starts after a refusal; 4. a summary.
No AI is called.
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from .file_cap import files

from . import nse as nse_api

log = logging.getLogger(__name__)

ARCHIVE_HOST = "nsearchives.nseindia.com"
REFUSALS = (403, 429, 503)
MAX_TIMEOUTS = 3
COOL_DOWN_SECONDS = 60.0
FULL_RELOAD_FILES = 40_000
FULL_RELOAD_LISTING_CALLS = 1_850
ALL_LIST_PAGE_SIZE = 1000
ALL_LIST_MAX_PAGES = 40

# name, pause range in seconds between two requests (per worker), workers. A is the pipeline's own default.
ROUNDS: tuple[tuple[str, tuple[float, float], int], ...] = (
    ("A", (3.0, 5.0), 1),
    ("B", (1.0, 1.0), 1),
    ("C", (0.3, 0.3), 1),
    ("D", (0.0, 0.0), 1),
    ("E", (0.0, 0.0), 4),
)


@dataclass
class Response:
    status: int = 0          # 0 = no answer
    body: bytes = b""
    seconds: float = 0.0
    error: str = ""          # "timeout" or the exception class
    timeout: bool = False


class HttpFetcher:
    """One timed GET with the pipeline's own session and headers (NseClient's httpx client, cookies from its warm-up),
    no retry and no pause: the speed test sets those itself."""

    def __init__(self, client: nse_api.NseClient):
        self._client = client
        client.warm_up()

    def get(self, url: str) -> Response:
        files.take(url)   # a file for the file cap (F213)
        start = time.monotonic()
        try:
            r = self._client._client.get(url)
        except httpx.TimeoutException:
            return Response(seconds=time.monotonic() - start, error="timeout", timeout=True)
        except httpx.HTTPError as exc:
            return Response(seconds=time.monotonic() - start, error=type(exc).__name__)
        return Response(r.status_code, r.content, time.monotonic() - start)


def xml_complete(body: bytes) -> bool:
    try:
        ET.fromstring(body)
    except ET.ParseError:
        return False
    return True


def xbrl_reads(body: bytes) -> bool:
    from . import xbrl

    try:
        return xbrl.parse(body) is not None
    except Exception:  # a file the reader cannot use is a finding, not a crash
        return False


@dataclass
class RoundResult:
    name: str
    pause: tuple[float, float]
    workers: int
    planned: int
    requests: list[dict] = field(default_factory=list)
    elapsed: float = 0.0
    stopped: str = ""        # why the round ended early; "" = every file was asked for
    not_run: str = ""        # why the round never started


def _record(url: str, resp: Response) -> dict:
    complete = resp.status == 200 and xml_complete(resp.body)
    return {"url": url, "status": resp.status, "bytes": len(resp.body), "seconds": round(resp.seconds, 3),
            "error": resp.error, "complete_xml": complete,
            "xbrl_parses": complete and xbrl_reads(resp.body)}


def run_round(name: str, pause: tuple[float, float], workers: int, urls: list[str], fetcher, sleep=time.sleep,
              rng: random.Random | None = None) -> RoundResult:
    """Download ``urls`` (all on the archive host) at ``pause`` between a worker's requests. Stops at the first refusal or
    the third timeout; files already in flight finish and are recorded."""
    rng = rng or random.Random()
    result = RoundResult(name, pause, workers, len(urls))
    stop = threading.Event()
    lock = threading.Lock()
    queue = list(urls)
    timeouts = 0

    def worker() -> None:
        nonlocal timeouts
        first = True
        while not stop.is_set():
            with lock:
                if not queue:
                    return
                url = queue.pop(0)
            if not first and pause[1] > 0:
                sleep(rng.uniform(*pause))
            first = False
            try:
                resp = fetcher.get(url)
            except nse_api.FileCapReached:
                with lock:   # the run's file cap (F213): this file and the rest of the list wait for the next run
                    result.stopped = result.stopped or "file cap reached"
                stop.set()
                return
            row = _record(url, resp)
            with lock:
                result.requests.append(row)
                if resp.status in REFUSALS:
                    if not result.stopped:
                        result.stopped = f"HTTP {resp.status} on request {len(result.requests)}"
                    stop.set()
                elif resp.timeout:
                    timeouts += 1
                    if timeouts >= MAX_TIMEOUTS and not result.stopped:
                        result.stopped = f"{MAX_TIMEOUTS} timeouts"
                        stop.set()

    start = time.monotonic()
    threads = [threading.Thread(target=worker) for _ in range(max(1, workers))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    result.elapsed = time.monotonic() - start
    return result


def run_rounds(urls: list[str], fetcher, per_round: int = 80, rounds=ROUNDS, sleep=time.sleep, cool_down=COOL_DOWN_SECONDS,
               rng: random.Random | None = None) -> list[RoundResult]:
    """Each round takes its own slice of ``urls`` (no file twice). After a refusal or three timeouts: wait ``cool_down``
    seconds and run no further round, since every later one is faster."""
    out: list[RoundResult] = []
    refused = False
    for i, (name, pause, workers) in enumerate(rounds):
        chunk = urls[i * per_round:(i + 1) * per_round]
        if refused:
            out.append(RoundResult(name, pause, workers, len(chunk), not_run="an earlier round was refused"))
            continue
        if not chunk:
            out.append(RoundResult(name, pause, workers, 0, not_run="no files left"))
            continue
        res = run_round(name, pause, workers, chunk, fetcher, sleep, rng)
        out.append(res)
        if res.stopped:
            refused = True
            sleep(cool_down)
    return out


def _round_summary(r: RoundResult) -> dict:
    n = len(r.requests)
    ok = [q for q in r.requests if q["status"] == 200]
    complete = sum(1 for q in ok if q["complete_xml"])
    errors: dict[str, int] = {}
    for q in r.requests:
        key = str(q["status"]) if q["status"] else (q["error"] or "no answer")
        if key != "200":
            errors[key] = errors.get(key, 0) + 1
    lat = sorted(q["seconds"] for q in r.requests)
    per_min = round(n * 60 / r.elapsed, 1) if r.elapsed > 0 and n else 0.0
    # safe = every planned file asked for, no refusal or timeout, and nothing but complete XML came back (404 is a
    # file that is gone, not a limit, so it does not make a round unsafe)
    clean = (not r.not_run and not r.stopped and n == r.planned and n > 0
             and all(q["status"] in (200, 404) for q in r.requests) and complete == len(ok))
    return {"round": r.name, "pause_seconds": list(r.pause), "workers": r.workers, "planned": r.planned, "requests": n,
            "ok": len(ok), "complete_xml": complete, "xbrl_parses": sum(1 for q in ok if q["xbrl_parses"]),
            "bytes": sum(q["bytes"] for q in r.requests), "elapsed_seconds": round(r.elapsed, 1),
            "files_per_minute": per_min, "median_latency": lat[len(lat) // 2] if lat else None,
            "max_latency": lat[-1] if lat else None, "errors": errors, "stopped": r.stopped, "not_run": r.not_run,
            "safe": clean}


def _hours(files: int, per_min: float, listing_seconds: float) -> float | None:
    if per_min <= 0:
        return None
    return round((files / per_min * 60 + listing_seconds) / 3600, 2)


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 3) if xs else None


def summarise(listing: dict, rounds: list[RoundResult]) -> dict:
    rs = [_round_summary(r) for r in rounds]
    safe = [r for r in rs if r["safe"]]
    fastest = max(safe, key=lambda r: r["files_per_minute"]) if safe else None
    today = next((r for r in rs if r["round"] == "A" and r["files_per_minute"] > 0), None)
    per_company = listing.get("api_seconds_per_company")
    calls = listing.get("api_calls_per_company") or 2.0
    all_list = listing.get("all_list_seconds")
    # the reload's ~1,850 listing calls at the measured seconds per call (per-company seconds / calls per company)
    listing_seconds = FULL_RELOAD_LISTING_CALLS * per_company / calls if per_company else 0.0
    projection = {
        "files": FULL_RELOAD_FILES, "listing_calls": FULL_RELOAD_LISTING_CALLS,
        "listing_seconds_per_company_api": per_company,
        "listing_hours_per_company_calls": round(listing_seconds / 3600, 2),
        "listing_seconds_all_company_list": all_list,
        "today_round": "A" if today else None,
        "today_hours": _hours(FULL_RELOAD_FILES, today["files_per_minute"], listing_seconds) if today else None,
        "fastest_safe_round": fastest["round"] if fastest else None,
        "fastest_safe_hours": _hours(FULL_RELOAD_FILES, fastest["files_per_minute"], listing_seconds) if fastest else None,
        "fastest_safe_hours_with_all_company_list":
            _hours(FULL_RELOAD_FILES, fastest["files_per_minute"], all_list) if fastest and all_list else None,
    }
    return {"listing": {k: v for k, v in listing.items() if k != "per_company"}, "rounds": rs,
            "fastest_safe_round": fastest["round"] if fastest else None, "projection": projection,
            "per_file_archive_seconds": _mean([q["seconds"] for r in rounds for q in r.requests if q["status"] == 200])}


def pick_symbols(symbols: list[str], count: int, seed: int) -> list[str]:
    pool = sorted(set(symbols))
    return random.Random(seed).sample(pool, min(count, len(pool)))


def list_per_company(nse, symbols: list[str], clock=time.monotonic) -> dict:
    """The seed's way: ``financial_results`` per symbol, normal pacing. Time per company, with the pause the client slept
    separated from the time the requests took."""
    slept = {"total": 0.0}
    inner = nse._sleep

    def counting_sleep(seconds: float) -> None:
        slept["total"] += seconds
        inner(seconds)

    nse._sleep = counting_sleep
    rows, links, refused = [], {}, ""
    calls0 = nse._calls
    t0 = clock()
    try:
        for sym in symbols:
            c0, s0, t = nse._calls, slept["total"], clock()
            try:
                filings = nse.financial_results(sym)
            except nse_api.SourceBlockedError as exc:
                refused = str(exc)[:200]
                break
            except Exception as exc:  # one company must not end the sample
                rows.append({"symbol": sym, "error": f"{type(exc).__name__}: {exc}"[:150]})
                continue
            wall = clock() - t
            links[sym] = [f.xbrl_url for f in filings if f.xbrl_url]
            rows.append({"symbol": sym, "calls": nse._calls - c0, "seconds": round(wall, 2),
                         "request_seconds": round(wall - (slept["total"] - s0), 2), "files": len(links[sym])})
    finally:
        nse._sleep = inner
    total = clock() - t0
    done = [r for r in rows if "calls" in r]
    return {"symbols": len(symbols), "listed": len(done), "refused": refused, "api_calls": nse._calls - calls0,
            "api_seconds_total": round(total, 1),
            "api_seconds_per_company": round(total / len(done), 2) if done else None,
            "api_request_seconds_per_company": _mean([r["request_seconds"] for r in done]),
            "api_calls_per_company": round(sum(r["calls"] for r in done) / len(done), 2) if done else None,
            "files_found": sum(r["files"] for r in done), "per_company": rows, "links": links}


def list_all_company(nse, symbols: list[str], clock=time.monotonic, max_pages: int = ALL_LIST_MAX_PAGES) -> dict:
    """NSE's all-company results list (TODO 42): pages of ``ALL_LIST_PAGE_SIZE`` rows until a short page, timed, then the
    sample's rows picked out of it."""
    wanted = {s.upper() for s in symbols}
    found: dict[str, set[str]] = {}
    pages, rows_seen, refused, error = 0, 0, "", ""
    t0 = clock()
    try:
        for page in range(1, max_pages + 1):
            rows = nse.integrated_list(nse_api.INTEGRATED_FINANCIALS, page, ALL_LIST_PAGE_SIZE)
            pages += 1
            rows_seen += len(rows)
            for row in rows:
                sym = str(row.get("symbol") or "").strip().upper()
                url = str(row.get("xbrl") or "").strip()
                if sym in wanted and url.lower().endswith(".xml"):
                    full = url if url.startswith("http") else f"https://{ARCHIVE_HOST}/{url.lstrip('/')}"
                    found.setdefault(sym, set()).add(full)
            if len(rows) < ALL_LIST_PAGE_SIZE:
                break
    except nse_api.SourceBlockedError as exc:
        refused = str(exc)[:200]
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:200]
    seconds = clock() - t0
    return {"all_list_pages": pages, "all_list_rows": rows_seen, "all_list_seconds": round(seconds, 1),
            "all_list_seconds_per_page": round(seconds / pages, 2) if pages else None,
            "all_list_companies_found": len(found), "all_list_files_found": sum(len(v) for v in found.values()),
            "all_list_refused": refused, "all_list_error": error}


def archive_urls(links: dict[str, list[str]], seed: int) -> list[str]:
    """Distinct archive-host file links of the sample, shuffled by the seed."""
    seen: set[str] = set()
    out = []
    for urls in links.values():
        for u in urls:
            if urlparse(u).hostname == ARCHIVE_HOST and u.lower().endswith(".xml") and u not in seen:
                seen.add(u)
                out.append(u)
    random.Random(seed).shuffle(out)
    return out


def run(nse, symbols: list[str], seed: int = 26, per_round: int = 80, sleep=time.sleep, fetcher=None,
        cool_down=COOL_DOWN_SECONDS) -> dict:
    listing = list_per_company(nse, symbols)
    links = listing.pop("links")
    if not listing["refused"]:
        listing.update(list_all_company(nse, symbols))
    urls = archive_urls(links, seed)
    rounds = [] if listing["refused"] else run_rounds(urls, fetcher or HttpFetcher(nse), per_round, sleep=sleep,
                                                     cool_down=cool_down)
    report = summarise(listing, rounds)
    report["seed"], report["files_available"], report["files_per_round"] = seed, len(urls), per_round
    report["per_company"] = listing["per_company"]
    report["requests"] = [dict(q, round=r.name) for r in rounds for q in r.requests]
    return report


def render(report: dict) -> str:
    lst, proj = report["listing"], report["projection"]
    lines = [f"NSE speed test (seed {report['seed']}, read only): {lst['listed']} of {lst['symbols']} companies listed, "
             f"{report['files_available']} archive files found",
             f"Listing (www.nseindia.com/api): {lst.get('api_seconds_per_company')} s per company with pauses "
             f"({lst.get('api_request_seconds_per_company')} s of request time, {lst.get('api_calls_per_company')} calls each)"]
    if lst.get("refused"):
        lines.append(f"  NSE refused the listing: {lst['refused']}")
    if "all_list_pages" in lst:
        lines.append(f"All-company list: {lst['all_list_pages']} pages, {lst['all_list_seconds']} s, found "
                     f"{lst['all_list_companies_found']} of the sample's companies, {lst['all_list_files_found']} files "
                     f"(per-company listing found {lst['files_found']})"
                     + (f"; refused: {lst['all_list_refused']}" if lst["all_list_refused"] else "")
                     + (f"; error: {lst['all_list_error']}" if lst["all_list_error"] else ""))
    lines.append(f"Archive (nsearchives): mean {report['per_file_archive_seconds']} s per file")
    for r in report["rounds"]:
        if r["not_run"]:
            what = f"not run ({r['not_run']})"
        else:
            what = (f"{r['requests']}/{r['planned']} files, {r['files_per_minute']}/min, {r['complete_xml']} complete XML, "
                    f"errors {r['errors'] or 'none'}" + (f", STOPPED: {r['stopped']}" if r["stopped"] else "")
                    + (", safe" if r["safe"] else ""))
        lines.append(f"  round {r['round']} (pause {r['pause_seconds'][0]}-{r['pause_seconds'][1]} s, "
                     f"{r['workers']} worker): {what}")
    lines.append(f"Fastest safe round: {report['fastest_safe_round']}")
    lines.append(f"Full reload (~{proj['files']} files, ~{proj['listing_calls']} listing calls): today {proj['today_hours']} h, "
                 f"at the fastest safe pace {proj['fastest_safe_hours']} h"
                 + (f" ({proj['fastest_safe_hours_with_all_company_list']} h with the all-company list)"
                    if proj["fastest_safe_hours_with_all_company_list"] else ""))
    return "\n".join(lines)


def write_json(report: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
