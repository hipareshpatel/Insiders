"""The sub-rows behind each "+" head of the stored screener.in pages, kept raw in R2. No AI, no NSE, no memory write.

Owner permission (29 Oct 2026): "Feel free to even get everything", after the Ambuja test (8 requests): the sub-rows name the
part of a head that differs (Borrowings = long-term + short-term + lease liabilities; Other Income = exceptional items + other
income normal; Other Liabilities holds the non-controlling interest; Net Profit carries the minority share, the exceptional
items after tax and the profit for EPS; Expenses as a percent of Sales). robots.txt disallows ``/company/source/quarter/*``, not
``/api/company/<id>/schedules/``.

Each stored page (``raw/screener/<day>/<SYMBOL>_<c|s>.html.gz``, screener_download.py) names its company id
(``data-company-id``) and its expandable heads (``Company.showSchedule('<head>', '<section>', this)``). For each head one request:

    GET https://www.screener.in/api/company/<id>/schedules/?parent=<head>&section=<section>[&consolidated=]

at 2.5 s a runner (owner: 2-3 s), at most 2 runners; a 403, 429 or 503 stops the run, and a sub-row that is itself
expandable ("Material Cost %", "Trade receivables") is asked too. Both pages' answers of a company are stored in one file
(owner, 29 Oct 2026: "1 file for one company"), gzipped JSON ``{"symbol", "company_id", "pages": {<basis>: {"page", "answers":
{"<section>|<head>": <answer>}}}}``, at

    raw/screener-schedules/<day of the pages>/<SYMBOL>.json.gz

A company whose file is stored is not asked again (a page stored by the first, one-file-a-page layout, <SYMBOL>_<c|s>.json.gz, is
read instead of asked); ``max_requests`` caps a trial run. Up to 12 runners (MAX_SHARDS).
"""

from __future__ import annotations

import gzip
import json
import re
import time
from urllib.parse import urlencode

from .metrics import CONSOLIDATED

MAX_SHARDS = 12          # owner, 29 Oct 2026: screener allows several GitHub machines, "you can have 12 machine"
PAUSE_SECONDS = 2.5      # between two requests of one runner (owner, 29 Oct 2026: "2-3 seconds between request"); 2 runners
PREFIX = "raw/screener-schedules/"
API = "https://www.screener.in/api/company/{cid}/schedules/"
XHR_HEADERS = {"Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest"}
_COMPANY_ID = re.compile(r'data-company-id="(\d+)"')
_HEAD = re.compile(r"Company\.showSchedule\('([^']+)',\s*'([^']+)',\s*this\)")
_HEAD_ANY = re.compile(r"Company\.showSchedule\(['\"]([^'\"]+)['\"],\s*['\"]([^'\"]+)['\"]")
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


def company_key(day: str, symbol: str) -> str:
    """One file a company: both bases' answers together."""
    return f"{PREFIX}{day}/{symbol}.json.gz"


def nested(answer: dict) -> list[tuple[str, str]]:
    """The sub-rows of an answer that are themselves expandable ("Material Cost %", "Trade receivables"): (head, section)."""
    out = []
    for row in (answer or {}).values():
        m = _HEAD_ANY.search(str((row or {}).get("isExpandable") or "")) if isinstance(row, dict) else None
        if m:
            out.append((m[1], m[2]))
    return out


def _fetch_page(client, cid: str, wanted: list[tuple[str, str]], basis: str, symbol: str, totals: dict, failed: list) -> dict | None:
    """Every head of one page and every expandable sub-row below it, one request each; None when one failed."""
    answers: dict = {}
    queue, seen, ok = list(wanted), set(wanted), True
    while queue:
        head, section = queue.pop(0)
        before = client.requests
        status, body = client.get(url_for(cid, head, section, basis))
        totals["requests_made"] += client.requests - before
        totals["heads_asked"] += 1
        if status != 200:
            failed.append(f"{symbol} {basis} {section}|{head}: {'HTTP ' + str(status) if status else body}"[:200])
            ok = False
            continue
        try:
            answer = json.loads(body)
        except ValueError:
            totals["heads_not_json"] += 1      # a page, not data: the company is asked again next run
            ok = False
            continue
        answers[f"{section}|{head}"] = answer
        for child in nested(answer):
            if child not in seen:
                seen.add(child)
                queue.append(child)
                totals["nested_heads"] += 1
    return answers if ok else None


def run(sink, symbols: list[str], pages: dict[str, dict[str, str]], client, shard: tuple[int, int] | None = None,
        time_budget: float = 17400.0, max_requests: int | None = None, clock=time.monotonic) -> dict:
    """Fetch and store, one file a company, the sub-rows of every head of its stored pages (both bases) and of every expandable
    sub-row below them, in the order given. ``pages`` is screener_crosscheck.stored_pages' symbol -> {basis: page key}. A page
    stored by the earlier one-file-a-page layout is read, not asked again. A refusal propagates (what is stored stays).
    ``more`` is true when the time budget or ``max_requests`` ended the run with companies left."""
    todo = symbols[shard[0]::shard[1]] if shard else list(symbols)
    stored = {k for k in sink.list_objects(PREFIX)}
    totals = {"symbols": len(todo), "companies_already_stored": 0, "companies_stored": 0, "pages": 0, "pages_reused": 0,
              "pages_without_id": 0, "heads_asked": 0, "nested_heads": 0, "heads_not_json": 0, "requests_made": 0,
              "bytes_stored": 0}
    failed: list[str] = []
    deadline = clock() + time_budget
    for symbol in todo:
        mine = sorted((pages.get(symbol) or {}).items())
        days = [m[1] for _, k in mine if (m := _PAGE.fullmatch(k))]
        if not days:
            continue
        key = company_key(max(days), symbol)
        if key in stored:
            totals["companies_already_stored"] += 1
            continue
        bundle: dict = {"symbol": symbol, "pages": {}}
        complete = True
        for basis, page_key in mine:
            totals["pages"] += 1
            old = object_key(page_key)
            if old in stored:
                bundle["pages"][basis] = {"page": page_key, "answers": unpack(sink.get_object(old))}
                totals["pages_reused"] += 1
                continue
            blob = sink.get_object(page_key)
            if not blob:
                continue
            cid, wanted = heads(gzip.decompress(blob).decode("utf-8"))
            if not cid or not wanted:
                totals["pages_without_id"] += 1
                continue
            if clock() >= deadline or (max_requests is not None and totals["requests_made"] + len(wanted) > max_requests):
                return {"more": True, "failed": failed, **totals}
            answers = _fetch_page(client, cid, wanted, basis, symbol, totals, failed)
            if answers is None:
                complete = False
                continue
            bundle["company_id"] = cid
            bundle["pages"][basis] = {"page": page_key, "answers": answers}
        if complete and bundle["pages"]:
            packed = pack(bundle)
            sink.put_object(key, packed, "application/gzip")
            stored.add(key)
            totals["companies_stored"] += 1
            totals["bytes_stored"] += len(packed)
    return {"more": False, "failed": failed, **totals}


def render(outcome: dict) -> str:
    return "\n".join([
        "screener schedules (the sub-rows of each '+' head, nested ones too, one file a company):",
        f"companies in this shard      {outcome['symbols']}",
        f"companies already stored     {outcome['companies_already_stored']}",
        f"companies stored now         {outcome['companies_stored']}",
        f"pages read                   {outcome['pages']} ({outcome['pages_reused']} from the earlier one-file-a-page layout)",
        f"pages with no company id     {outcome['pages_without_id']}",
        f"heads asked                  {outcome['heads_asked']} ({outcome['nested_heads']} of them nested sub-rows)",
        f"answers that were not JSON   {outcome['heads_not_json']}",
        f"requests made                {outcome['requests_made']}",
        f"bytes stored (gzip)          {outcome['bytes_stored']}",
        f"more to do                   {outcome['more']}"])
