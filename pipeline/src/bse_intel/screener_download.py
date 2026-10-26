"""One-time download of every company's screener.in pages, kept raw in R2. No AI, no NSE, no memory write. TRACKER F163, TODO 50.

Owner permission (26 Oct 2026): "download financials for all the companies from screener, we will cross check everything to
find issues". One time, at least 3 s between requests (screener_fill's 3.2 s pause, its fetcher and its refusal rule: a 403,
429 or 503 stops the run), a plain browser User-Agent, no login.

Both pages of a company are fetched (``/company/<SYM>/consolidated/`` and ``/company/<SYM>/``) and each page's HTML is stored
gzipped in the object store (R2 in the cloud, a folder on the laptop) at

    raw/screener/<YYYY-MM-DD>/<SYMBOL>_<c|s>.html.gz

A page already stored for that date is not fetched again. The companies a shard finished are kept in a kv key per date and
shard, so a run that ends on its time budget (exit 124) is started again and resumes. ``screener_crosscheck`` reads these
pages and later fills can read them too, so screener is not asked twice.
"""

from __future__ import annotations

import gzip
import json
import logging
import time

from .metrics import CONSOLIDATED, STANDALONE
from .screener_fill import MAX_SHARDS, PAUSE_SECONDS, ScreenerClient, ScreenerRefused, symbol_of, url_for  # noqa: F401
from .timeutil import now_iso

log = logging.getLogger(__name__)

PREFIX = "raw/screener/"
DONE_KEY = "screenerdl:done"          # + ":<day>:<i>of<n>": the symbols a shard finished
BASES = ((CONSOLIDATED, "c"), (STANDALONE, "s"))


def object_key(day: str, symbol: str, basis: str) -> str:
    return f"{PREFIX}{day}/{symbol}_{'c' if basis == CONSOLIDATED else 's'}.html.gz"


def pack(body: str) -> bytes:
    return gzip.compress(body.encode("utf-8"), mtime=0)


def unpack(blob: bytes) -> str:
    return gzip.decompress(blob).decode("utf-8")


def symbols_for(sink, scrips: list[str], by_scrip: dict[str, str]) -> list[tuple[str, str]]:
    """(scrip, NSE symbol) for each company, in symbol order, one row per symbol; the universe file's symbol first, else
    the company row's. A company with no symbol is left out."""
    out: dict[str, str] = {}
    for scrip in scrips:
        symbol = (by_scrip.get(scrip) or "").strip().upper() or symbol_of(sink.company(scrip))
        if symbol:
            out.setdefault(symbol, scrip)
    return [(scrip, symbol) for symbol, scrip in sorted(out.items())]


def estimate(companies: int, shards: int = 1, pause: float = PAUSE_SECONDS) -> dict:
    """Two pages a company, one request each, ``pause`` seconds apart per runner."""
    requests = companies * len(BASES)
    return {"requests": requests, "seconds": round(requests * pause / max(1, shards))}


def run(sink, companies: list[tuple[str, str]], client, day: str, shard: tuple[int, int] | None = None,
        time_budget: float = 17400.0, restart: bool = False, clock=time.monotonic) -> dict:
    """Fetch and store both pages of this shard's companies. A refusal from screener.in propagates (what is stored stays,
    and the companies finished so far are saved). ``more`` is true when the time budget ended the run with companies left."""
    suffix = f":{day}:{shard[0]}of{shard[1]}" if shard else f":{day}:0of1"
    key = DONE_KEY + suffix
    done = set() if restart else set(json.loads(sink.kv_get(key) or "[]"))
    todo = list(companies)
    if shard:
        todo = todo[shard[0]::shard[1]]
    stored = set(sink.list_objects(f"{PREFIX}{day}/"))
    totals = {"day": day, "companies": len(todo), "companies_done_before": 0, "pages_stored": 0, "pages_already_stored": 0,
              "pages_not_found": 0, "pages_failed": 0, "requests_made": 0, "bytes_stored": 0}
    failed: list[str] = []
    more = False
    deadline = clock() + time_budget
    for scrip, symbol in todo:
        if symbol in done:
            totals["companies_done_before"] += 1
            continue
        if clock() >= deadline:
            more = True
            break
        clean = True
        for basis, _ in BASES:
            name = object_key(day, symbol, basis)
            if name in stored:
                totals["pages_already_stored"] += 1
                continue
            before = client.requests
            status, body = client.get(url_for(symbol, basis))
            totals["requests_made"] += client.requests - before
            if status == 200:
                blob = pack(body)
                sink.put_object(name, blob, "application/gzip")
                stored.add(name)
                totals["pages_stored"] += 1
                totals["bytes_stored"] += len(blob)
            elif status == 404:
                totals["pages_not_found"] += 1   # no such company page: nothing to store, nothing to retry
            else:
                clean = False
                totals["pages_failed"] += 1
                failed.append(f"{symbol} {basis}: {'HTTP ' + str(status) if status else body}"[:200])
        if clean:   # a company with a failed page is tried again by the next run (its stored page is not fetched again)
            done.add(symbol)
            sink.kv_set(key, json.dumps(sorted(done)), now_iso())
    return {"more": more, "failed": failed, **totals}


def render(outcome: dict) -> str:
    return "\n".join([
        f"screener download for {outcome['day']}:",
        f"companies in this shard      {outcome['companies']}",
        f"finished by an earlier run   {outcome['companies_done_before']}",
        f"pages stored                 {outcome['pages_stored']}",
        f"pages already stored         {outcome['pages_already_stored']}",
        f"pages not found (404)        {outcome['pages_not_found']}",
        f"pages that failed            {outcome['pages_failed']}",
        f"requests made                {outcome['requests_made']}",
        f"bytes stored (gzip)          {outcome['bytes_stored']}"])
