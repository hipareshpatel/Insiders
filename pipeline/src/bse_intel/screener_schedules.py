"""The sub-rows behind each "+" head of the stored screener.in pages, kept raw in R2. No AI, no NSE, no memory write.

Owner permission (29 Oct 2026): "Feel free to even get everything", after the Ambuja test (8 requests): the sub-rows name the
part of a head that differs (Borrowings = long-term + short-term + lease liabilities; Other Income = exceptional items + other
income normal; Other Liabilities holds the non-controlling interest; Net Profit carries the minority share, the exceptional
items after tax and the profit for EPS; Expenses as a percent of Sales). robots.txt disallows ``/company/source/quarter/*``, not
``/api/company/<id>/schedules/``.

Each stored page (``raw/screener/<day>/<SYMBOL>_<c|s>.html.gz``, screener_download.py) names its company id
(``data-company-id``) and its expandable heads (``Company.showSchedule('<head>', '<section>', this)``). For each head one request:

    GET https://www.screener.in/api/company/<id>/schedules/?parent=<head>&section=<section>[&consolidated=]

at screener_download's pace (3.2 s a runner, at most 2 runners, a 403, 429 or 503 stops the run), and the answers of a page are
stored together, gzipped JSON ``{"<section>|<head>": <answer>}``, at

    raw/screener-schedules/<day of the page>/<SYMBOL>_<c|s>.json.gz

A page whose answers are stored is not asked again; ``max_requests`` caps a trial run (the first run: 100).
"""

from __future__ import annotations

import gzip
import json
import re
import time
from urllib.parse import urlencode

from .metrics import CONSOLIDATED

PREFIX = "raw/screener-schedules/"
API = "https://www.screener.in/api/company/{cid}/schedules/"
XHR_HEADERS = {"Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest"}
_COMPANY_ID = re.compile(r'data-company-id="(\d+)"')
_HEAD = re.compile(r"Company\.showSchedule\('([^']+)',\s*'([^']+)',\s*this\)")
_PAGE = re.compile(r"raw/screener/(\d{4}-\d{2}-\d{2})/(.+)_([cs])\.html\.gz")


def heads(html: str) -> tuple[str | None, list[tuple[str, str]]]:
    """(screener's company id, [(head, section)] in page order, each once) of one stored page."""
    m = _COMPANY_ID.search(html)
    seen: list[tuple[str, str]] = []
    for head, section in _HEAD.findall(html):
        if (head, section) not in seen:
            seen.append((head, section))
    return (m[1] if m else None), seen


def url_for(cid: str, head: str, section: str, basis: str) -> str:
    params = {"parent": head, "section": section}
    if basis == CONSOLIDATED:
        params["consolidated"] = ""
    return API.format(cid=cid) + "?" + urlencode(params)


def object_key(page_key: str) -> str | None:
    m = _PAGE.fullmatch(page_key)
    return f"{PREFIX}{m[1]}/{m[2]}_{m[3]}.json.gz" if m else None


def pack(answers: dict) -> bytes:
    return gzip.compress(json.dumps(answers, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0)


def unpack(blob: bytes) -> dict:
    return json.loads(gzip.decompress(blob).decode("utf-8"))


def run(sink, symbols: list[str], pages: dict[str, dict[str, str]], client, shard: tuple[int, int] | None = None,
        time_budget: float = 17400.0, max_requests: int | None = None, clock=time.monotonic) -> dict:
    """Fetch and store the sub-rows of every stored page of this shard's symbols, in the order given. ``pages`` is
    screener_crosscheck.stored_pages' symbol -> {basis: page key}. A refusal propagates (what is stored stays). ``more`` is
    true when the time budget or ``max_requests`` ended the run with pages left."""
    todo = symbols[shard[0]::shard[1]] if shard else list(symbols)
    stored = {k for k in sink.list_objects(PREFIX)}
    totals = {"symbols": len(todo), "pages": 0, "pages_already_stored": 0, "pages_stored": 0, "pages_without_id": 0,
              "heads_asked": 0, "heads_not_json": 0, "requests_made": 0, "bytes_stored": 0}
    failed: list[str] = []
    more = False
    deadline = clock() + time_budget
    for symbol in todo:
        for basis, page_key in sorted((pages.get(symbol) or {}).items()):
            key = object_key(page_key)
            if key is None:
                continue
            totals["pages"] += 1
            if key in stored:
                totals["pages_already_stored"] += 1
                continue
            blob = sink.get_object(page_key)
            if not blob:
                continue
            cid, wanted = heads(gzip.decompress(blob).decode("utf-8"))
            if not cid or not wanted:
                totals["pages_without_id"] += 1
                continue
            if clock() >= deadline or (max_requests is not None and totals["requests_made"] + len(wanted) > max_requests):
                more = True
                return {"more": more, "failed": failed, **totals}
            answers: dict = {}
            for head, section in wanted:
                before = client.requests
                status, body = client.get(url_for(cid, head, section, basis))
                totals["requests_made"] += client.requests - before
                totals["heads_asked"] += 1
                if status != 200:
                    failed.append(f"{symbol} {basis} {section}|{head}: {'HTTP ' + str(status) if status else body}"[:200])
                    continue
                try:
                    answers[f"{section}|{head}"] = json.loads(body)
                except ValueError:
                    totals["heads_not_json"] += 1      # a page, not data: kept out, the page is asked again next run
            if len(answers) == len(wanted):
                packed = pack(answers)
                sink.put_object(key, packed, "application/gzip")
                stored.add(key)
                totals["pages_stored"] += 1
                totals["bytes_stored"] += len(packed)
    return {"more": more, "failed": failed, **totals}


def render(outcome: dict) -> str:
    return "\n".join([
        "screener schedules (the sub-rows of each '+' head):",
        f"symbols in this shard        {outcome['symbols']}",
        f"pages                        {outcome['pages']}",
        f"pages already stored         {outcome['pages_already_stored']}",
        f"pages stored now             {outcome['pages_stored']}",
        f"pages with no company id     {outcome['pages_without_id']}",
        f"heads asked                  {outcome['heads_asked']}",
        f"answers that were not JSON   {outcome['heads_not_json']}",
        f"requests made                {outcome['requests_made']}",
        f"bytes stored (gzip)          {outcome['bytes_stored']}",
        f"more to do                   {outcome['more']}"])
