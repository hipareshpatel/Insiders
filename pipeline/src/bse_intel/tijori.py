"""Download of every company's financials from Tijori Finance (www.tijorifinance.com), kept raw in R2. No AI, no NSE, no memory
write, no card change. TRACKER F189, TODO 92.

Owner request (26 Oct 2026, TODO 92): "Can you download financial data from Tijori ... so that we have another source to
compare everything like screener". Tijori's robots.txt allows all crawlers (measured 26 Oct 2026). It is a comparison only:
on 26 Oct it copied the exchange filings (ABB's Dec 2025 quarter Net Sales 3,557.01, the same as memory; Apar Industries' Q1FY27
Net Profit 467.45 and EPS 116.3679 against memory's known error, owners' profit -138.56 and EPS -116.37, TODO 90), and it
probably shares a data vendor with screener. So it can catch errors in OUR reading of NSE's files, never errors in NSE's own
files, and it never corrects memory alone (the two-source rule). ``tijori_crosscheck`` reads what this module stores.

What a page carries (measured 26 Oct 2026 on ABB, Apar and Dolphin Offshore): ``/company/<slug>/financials/`` holds all of a
company's tables inside the HTML, in ``<script id="fin_tables_data" type="application/json">`` (about 200 KB; also the largest
JSON block of the page, the fallback here). It is a dict with ``bs_s_s``, ``bs_c_s``, ``bs_s_d``, ``bs_c_d`` (balance sheet,
standalone or consolidated, summary or detailed), ``pl_*`` (the same four splits of the profit and loss), ``cf_s``, ``cf_c``,
``qt_s``, ``qt_c`` (quarterly), ``fr_s``, ``fr_c`` (ratios) and ``growth``. Each section is ``{report_dates, data: [{name,
value: [...], sub_section}]}``, values in crore to 2 to 4 decimals, lined up with ``report_dates`` ("Mar 2026").

The page names its company in ``<script id="company_details">`` (``symbol``, ``company``, ``slug``, ``is_banking``) and in the
``ld+json`` block (``about.tickerSymbol``). A page is kept only when one of them is our company: the NSE symbol, else the same
name after the normalisation below. A wrong slug answers 302 to the home page (the client does not follow redirects, so a 302
is "no such page"); a slug that belongs to another company would be a wrong page that answers 200, which the check catches.

Stored at ``raw/tijori/<YYYY-MM-DD>/<SYMBOL>.json.gz``: the ``fin_tables_data`` dict as compact JSON, gzipped.

Pace and refusal (owner, 26 Oct 2026: 6 requests a second works; measured, see ``TijoriClient``): ``TIJORI_RATE`` requests a
second (default 6) through 8 threads and one shared start-time limiter, a plain browser User-Agent and ``Accept-Language``, no
login, one runner for the whole universe (about 1,900 companies, 5 to 6 minutes). The first refusal (403, 429, 503 or a
Cloudflare / Akamai challenge page) drops the run to one request every 3 s and is recorded; a second one raises ``TijoriRefused`` and stops the run
(exit 75); what is stored stays. A normal Tijori page mentions reCAPTCHA in its own scripts (10 times on Apar's page), so only
an explicit gate marker on a page with no ``fin_tables_data`` and no ``company_details`` is a refusal. A 200 page with neither
block and no marker is "suspect": counted, not stored, not finished (the next run asks again), not a refusal.

Slug map: the sitemap (``/sitemap.xml``, one request a run) lists 5,741 companies as ``/company/<slug>/``; the slugs are
irregular (``aadhar-housing-finance-ltd``, ``sundaram-finance-limited``, ``the-anup-engineering-ltd``), so a company is matched
by name: lowercase, "&" to "and", the words "limited", "ltd" and "the" dropped, punctuation stripped. A name that fits two
slugs is ambiguous: its candidates are fetched in turn and the first page that verifies is kept; both lists and the unmatched companies are in the summary.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from .timeutil import now_iso

log = logging.getLogger(__name__)

SITE = "https://www.tijorifinance.com"
SITEMAP_URL = f"{SITE}/sitemap.xml"
# a plain browser User-Agent and Accept-Language; no login, no cookies kept between companies
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
RATE = float(os.environ.get("TIJORI_RATE", "6"))   # requests a second, shared by all threads
SLOW_PAUSE_SECONDS = 3.0                          # after the first refusal: one request every 3 s
WORKERS = 8
SAVE_EVERY = 25                                   # finished companies between two saves of the done list
PREFIX = "raw/tijori/"
DONE_KEY = "tijoridl:done"          # + ":<day>": the symbols a run finished
TABLES_ID = "fin_tables_data"
DROP_WORDS = frozenset({"limited", "ltd", "the"})
# a page with no financials block is a gate only when it is not a normal company page and has one of these markers
_CHALLENGE = re.compile(r"cf-challenge|challenge-platform|just a moment|attention required|access denied|"
                        r"you have been blocked|error 10\d\d|rate limited|cloudflare ray id|akamai", re.I)
NORMAL_PAGE_BYTES = 50_000    # a company page is about 200 KB; a gate is a few KB


def is_challenge(body: str) -> bool:
    """A refusal page: not a normal company page (its ``company_details`` block, or a large body) and carrying an explicit
    Cloudflare / Akamai marker. A bare "captcha" is not one: a short 200 page with no tables, no ``company_details`` and no
    marker is "suspect" (see ``_fetch``), a normal page without tables is "no_tables"."""
    if 'id="company_details"' in body or len(body) > NORMAL_PAGE_BYTES:
        return False
    return bool(_CHALLENGE.search(body))


class TijoriRefused(RuntimeError):
    """tijorifinance.com answered 403, 429 or 503, or a CAPTCHA / challenge page: stop, never push on."""


def object_key(day: str, symbol: str) -> str:
    return f"{PREFIX}{day}/{symbol}.json.gz"


def pack(body: str) -> bytes:
    return gzip.compress(body.encode("utf-8"), mtime=0)


def unpack(blob: bytes) -> str:
    return gzip.decompress(blob).decode("utf-8")


# --- the page -----------------------------------------------------------------------------------------------------

_SCRIPT = re.compile(r"<script([^>]*)>(.*?)</script>", re.S)


def _json_blocks(body: str) -> list[tuple[str, str]]:
    """(id, text) of every ``application/json`` script of a page."""
    out = []
    for attrs, text in _SCRIPT.findall(body):
        if "application/json" in attrs:
            m = re.search(r'id="([^"]*)"', attrs)
            out.append((m[1] if m else "", text))
    return out


def extract_tables(body: str) -> dict | None:
    """The ``fin_tables_data`` dict of a financials page; when the id is not there, the largest JSON block that parses to a
    dict with the quarterly or profit and loss sections. None when the page has none."""
    blocks = _json_blocks(body)
    ordered = [b for b in blocks if b[0] == TABLES_ID] + sorted((b for b in blocks if b[0] != TABLES_ID),
                                                                key=lambda b: -len(b[1]))
    for _, text in ordered:
        try:
            data = json.loads(text)
        except ValueError:
            continue
        if isinstance(data, dict) and ("qt_c" in data or "pl_c_s" in data or "qt_s" in data):
            return data
    return None


def identity(body: str) -> dict:
    """The company the page says it is: ``{"symbol", "name", "slug"}`` from ``company_details``, else the ld+json block's
    ``about``. Empty strings when neither is there."""
    out = {"symbol": "", "name": "", "slug": ""}
    for block_id, text in _json_blocks(body):
        if block_id == "company_details":
            try:
                data = json.loads(text)
            except ValueError:
                continue
            if isinstance(data, dict):
                out = {"symbol": str(data.get("symbol") or ""), "name": str(data.get("company") or ""),
                       "slug": str(data.get("slug") or "")}
    if not out["symbol"] and not out["name"]:
        for attrs, text in _SCRIPT.findall(body):
            if "ld+json" in attrs:
                try:
                    data = json.loads(text)
                except ValueError:
                    continue
                items = data if isinstance(data, list) else (data.get("@graph") if isinstance(data, dict)
                                                             and isinstance(data.get("@graph"), list) else [data])
                for item in items:
                    about = item.get("about") if isinstance(item, dict) else None
                    if isinstance(about, dict) and (about.get("tickerSymbol") or about.get("name")):
                        out["symbol"], out["name"] = str(about.get("tickerSymbol") or ""), str(about.get("name") or "")
                        break
                if out["symbol"] or out["name"]:
                    break
    return out


def normalise(name: str) -> str:
    """The comparison form of a company name or slug: lowercase, apostrophes removed, "&" to "and", every other punctuation
    a space, and the words limited / ltd / the dropped: "The Anup Engineering Ltd." and ``the-anup-engineering-limited`` both
    give "anup engineering"."""
    text = (name or "").lower().replace("'", "").replace("’", "").replace("&", " and ")
    return " ".join(t for t in re.sub(r"[^a-z0-9]+", " ", text).split() if t not in DROP_WORDS)


def _keys(name: str) -> list[str]:
    """The forms of our name tried against the slugs: with "&" read as "and", and with it dropped (a slug may omit it; not
    confirmed, as no sample slug holds an ampersand)."""
    keys = [normalise(name), normalise((name or "").replace("&", " "))]
    return [k for i, k in enumerate(keys) if k and k not in keys[:i]]


def sitemap_slugs(xml: str) -> list[str]:
    """The company slugs of the sitemap: ``/company/<slug>/`` and nothing deeper (the same company's /financials/,
    /shareholding/ ... pages are not listed again)."""
    seen: dict[str, None] = {}
    for loc in re.findall(r"<loc>\s*(.*?)\s*</loc>", xml):
        m = re.fullmatch(re.escape(SITE) + r"/company/([^/]+)/", loc)
        if m:
            seen.setdefault(m[1])
    return list(seen)


def map_slugs(companies: list[tuple[str, str, str]], slugs: list[str]) -> dict:
    """Our companies ((scrip, symbol, name)) matched to a slug by normalised name. ``matched``: symbol -> slug;
    ``ambiguous``: symbol -> the several slugs its name fits (not fetched); ``unmatched``: symbols with none."""
    by_key: dict[str, list[str]] = {}
    for slug in slugs:
        by_key.setdefault(normalise(slug.replace("-", " ")), []).append(slug)
    matched: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}
    unmatched: list[str] = []
    for _, symbol, name in companies:
        found = sorted({s for key in _keys(name) for s in by_key.get(key, [])})
        if len(found) == 1:
            matched[symbol] = found[0]
        elif found:
            ambiguous[symbol] = found
        else:
            unmatched.append(symbol)
    return {"matched": matched, "ambiguous": ambiguous, "unmatched": unmatched}


def verifies(page: dict, symbol: str, name: str) -> bool:
    """True when the page names this company: its NSE symbol, else its name after ``normalise``. A page that carries a
    symbol which is not ours is another company's, whatever its name."""
    if page["symbol"]:
        return page["symbol"].strip().upper() == symbol.strip().upper()
    return bool(page["name"]) and normalise(page["name"]) in _keys(name)


def url_for(slug: str) -> str:
    return f"{SITE}/company/{slug}/financials/"


class TijoriClient:
    """Plain HTTP, safe to share between threads: a browser User-Agent and Accept-Language, no login. Redirects are not
    followed: a 302 is Tijori's "no such page" (it sends a wrong slug to the home page).

    Pace: ONE shared limiter, not a sleep per thread. Each request takes the next start time under a lock, ``1 / rate`` seconds
    after the one before (``TIJORI_RATE`` requests a second, default 6: measured 26 Oct 2026 from the session's machine, 200 random
    company pages at 6 a second on 8 threads, 200 of 200 HTTP 200 with the data block, 34.7 s, latency median 0.78 s, p95 1.45 s,
    no 403, 429 or 503 and no challenge page). Slow back, then stop (the rule of the NSE archive host, F169): the FIRST refusal
    (403, 429, 503 or a challenge page) drops the whole client to one request every ``SLOW_PAUSE`` seconds for the rest of the run
    and the refused page is asked once more; ``slowed`` records that it happened. A refusal of a request started after that, the
    SECOND, raises ``TijoriRefused`` and every other thread stops with it. Requests already in flight when the first refusal came
    (up to 8 of them, all at the fast rate) do not count as a second: they are retried at the slow pace."""

    def __init__(self, rate: float = RATE, transport: httpx.BaseTransport | None = None, sleep=time.sleep,
                 clock=time.monotonic, slow_pause: float = SLOW_PAUSE_SECONDS):
        self._client = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9",
                                             "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
                                    timeout=30.0, follow_redirects=False, transport=transport)
        self.interval, self.slow_pause, self._sleep, self._clock = 1.0 / max(rate, 0.01), slow_pause, sleep, clock
        self._lock = threading.Lock()
        self._next = clock()
        self.requests = 0
        self.slowed = False
        self.slowed_after: int | None = None    # requests made when the first refusal came
        self.refusal: str | None = None         # the first refusal's reason
        self._stopped: str | None = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._client.close()

    def _slot(self) -> bool:
        """Wait for this request's start time; True when it starts after the slow-down."""
        with self._lock:
            if self._stopped:
                raise TijoriRefused(self._stopped)
            now = self._clock()
            start = max(now, self._next)
            self._next = start + (self.slow_pause if self.slowed else self.interval)
            self.requests += 1
            slowed = self.slowed
        if start > now:
            self._sleep(start - now)
        with self._lock:
            if self._stopped:    # a stop that came while this thread slept: send nothing
                raise TijoriRefused(self._stopped)
        return slowed

    def _refused(self, reason: str, was_slow: bool) -> None:
        with self._lock:
            if was_slow:
                self._stopped = f"a second refusal after slowing down: {reason}"
                raise TijoriRefused(self._stopped)
            if not self.slowed:
                self.slowed, self.slowed_after, self.refusal = True, self.requests, reason
                self._next = max(self._next, self._clock()) + self.slow_pause
                log.warning("tijori refused (%s): one request every %g s from now on", reason, self.slow_pause)

    def get(self, url: str) -> tuple[int, str]:
        """(status, body); the body only on a 200. 0 is a network error (the reason in the body)."""
        while True:
            was_slow = self._slot()
            with self._lock:
                if self._stopped:    # last look before the request leaves
                    raise TijoriRefused(self._stopped)
            try:
                response = self._client.get(url)
            except httpx.HTTPError as exc:
                return 0, f"{type(exc).__name__}: {exc}"[:200]
            if response.status_code in (403, 429, 503):
                self._refused(f"HTTP {response.status_code} from {url}", was_slow)
                continue
            if response.status_code != 200:
                return response.status_code, ""
            body = response.text
            if f'id="{TABLES_ID}"' not in body and is_challenge(body):
                self._refused(f"a CAPTCHA or challenge page from {url}", was_slow)
                continue
            return 200, body


# --- the run ------------------------------------------------------------------------------------------------------

def estimate(companies: int, rate: float = RATE) -> dict:
    """One page a company plus the sitemap, ``rate`` requests a second."""
    return {"requests": companies + 1, "seconds": round((companies + 1) / rate)}


_COUNTER = {"no_tables": "pages_no_tables", "not_verified": "pages_not_verified", "no_page": "pages_no_page"}
_FINAL = {"stored", "no_tables", "not_verified", "no_page"}


def _fetch(client, symbol: str, name: str, slug: str | list[str]) -> dict:
    """One company's page, checked: ``{"kind": "stored" | "no_tables" | "not_verified" | "no_page" | "failed", ...}``. Given
    several candidate slugs (an ambiguous name), they are tried in turn and the first page that verifies wins; when none
    does, a "failed" answer (transient: the symbol is retried) wins, then a "suspect" one, else the last candidate's answer
    stands. "suspect": a 200 page with no tables, no ``company_details`` and no gate marker (a stub or an unknown gate): not
    stored, not finished, not a refusal."""
    if isinstance(slug, list):
        got: dict = {"kind": "no_page"}
        failed = suspect = None
        for one in slug:
            got = _fetch(client, symbol, name, one)
            if got["kind"] == "stored":
                return got
            if got["kind"] == "failed" and failed is None:
                failed = got
            elif got["kind"] == "suspect" and suspect is None:
                suspect = got
        return failed or suspect or got
    status, body = client.get(url_for(slug))
    if status == 200:
        tables, page = extract_tables(body), identity(body)
        if tables is None:
            if 'id="company_details"' not in body:
                return {"kind": "suspect", "note": f"{symbol} {slug}: 200 page without tables or company_details"[:200]}
            return {"kind": "no_tables"}
        if not verifies(page, symbol, name):
            return {"kind": "not_verified",
                    "note": f"{symbol} -> {slug}: page is {page['symbol'] or '?'} / {page['name'] or '?'}"[:200]}
        return {"kind": "stored", "blob": pack(json.dumps(tables, separators=(",", ":"), ensure_ascii=False))}
    if status in (302, 404):
        return {"kind": "no_page"}   # no such page: nothing to store, nothing to retry
    return {"kind": "failed", "note": f"{symbol} {slug}: {'HTTP ' + str(status) if status else body}"[:200]}


def run(sink, companies: list[tuple[str, str, str]], client, day: str, time_budget: float = 17400.0,
        restart: bool = False, clock=time.monotonic, workers: int = WORKERS) -> dict:
    """Fetch and store the financials page of each company ((scrip, symbol, name), in symbol order) on ``workers`` threads
    behind the client's one shared limiter. The sink is written from this thread only. A second refusal propagates as
    ``TijoriRefused`` after what was fetched is stored and the finished companies are saved. ``more`` is true when the time
    budget ended the run with companies left. A page already stored for ``day`` is not fetched again; a company is finished
    when its page is stored, verified wrong, answered 302 or 404, or had no tables (those do not change on a retry); a network
    or server error is tried again by the next run."""
    key = f"{DONE_KEY}:{day}"
    done = set() if restart else set(json.loads(sink.kv_get(key) or "[]"))
    stored = set(sink.list_objects(f"{PREFIX}{day}/"))
    totals = {"day": day, "companies": len(companies), "companies_done_before": 0, "pages_stored": 0,
              "pages_already_stored": 0, "pages_no_page": 0, "pages_not_verified": 0, "pages_no_tables": 0,
              "pages_failed": 0, "pages_suspect": 0, "requests_made": 0, "bytes_stored": 0}
    before = client.requests
    status, xml = client.get(SITEMAP_URL)
    slugs = sitemap_slugs(xml) if status == 200 else []
    mapping = map_slugs(companies, slugs) if slugs else {"matched": {}, "ambiguous": {}, "unmatched": []}
    failed: list[str] = [] if slugs else [f"sitemap: {'HTTP ' + str(status) if status else xml}"[:200]]
    not_verified: list[str] = []
    suspect: list[str] = []
    todo = []
    for scrip, symbol, name in companies:
        if symbol not in mapping["matched"] and symbol not in mapping["ambiguous"]:
            continue
        if symbol in done:
            totals["companies_done_before"] += 1
        elif object_key(day, symbol) in stored:
            totals["pages_already_stored"] += 1
            done.add(symbol)
        else:
            todo.append((symbol, name, mapping["matched"].get(symbol) or mapping["ambiguous"][symbol]))
    deadline = clock() + time_budget
    deferred = threading.Event()

    def work(item):
        if clock() >= deadline:
            deferred.set()
            return None
        symbol, name, slug = item
        try:
            return _fetch(client, symbol, name, slug)
        except TijoriRefused:
            raise
        except Exception as exc:    # one bad page must not end the run: this company is retried by the next one
            log.warning("tijori %s: unexpected %s: %s", symbol, type(exc).__name__, exc)
            return {"kind": "failed", "note": f"{symbol}: unexpected {type(exc).__name__}: {exc}"[:200]}

    refused: TijoriRefused | None = None
    unsaved = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [(item[0], pool.submit(work, item)) for item in todo]
        for symbol, future in futures:
            try:
                got = future.result()
            except TijoriRefused as exc:
                refused = refused or exc
                continue
            if got is None:
                continue
            kind = got["kind"]
            if kind == "failed":
                totals["pages_failed"] += 1
                failed.append(got["note"])
                continue
            if kind == "suspect":
                totals["pages_suspect"] += 1
                suspect.append(got["note"])
                continue
            if kind == "stored":
                sink.put_object(object_key(day, symbol), got["blob"], "application/gzip")
                totals["pages_stored"] += 1
                totals["bytes_stored"] += len(got["blob"])
            else:
                totals[_COUNTER[kind]] += 1
                if kind == "not_verified":
                    not_verified.append(got["note"])
            done.add(symbol)
            unsaved += 1
            if unsaved >= SAVE_EVERY:
                sink.kv_set(key, json.dumps(sorted(done)), now_iso())
                unsaved = 0
    sink.kv_set(key, json.dumps(sorted(done)), now_iso())
    totals["requests_made"] = client.requests - before
    if refused:
        raise refused
    return {"more": deferred.is_set(), "failed": failed, "suspect": suspect, "not_verified": not_verified, "sitemap_companies": len(slugs),
            "matched": len(mapping["matched"]), "ambiguous": mapping["ambiguous"], "unmatched": mapping["unmatched"],
            "slowed": client.slowed, "slowed_after_requests": client.slowed_after, "refusal": client.refusal, **totals}


def render(outcome: dict) -> str:
    return "\n".join([
        f"tijori download for {outcome['day']}:",
        f"companies                    {outcome['companies']}",
        f"companies in the sitemap     {outcome['sitemap_companies']}",
        f"matched to a slug            {outcome['matched']}",
        f"ambiguous (not fetched)      {len(outcome['ambiguous'])}",
        f"unmatched                    {len(outcome['unmatched'])}",
        f"finished by an earlier run   {outcome['companies_done_before']}",
        f"pages stored                 {outcome['pages_stored']}",
        f"pages already stored         {outcome['pages_already_stored']}",
        f"no such page (302 or 404)    {outcome['pages_no_page']}",
        f"page not this company        {outcome['pages_not_verified']}",
        f"page without tables          {outcome['pages_no_tables']}",
        f"pages that failed            {outcome['pages_failed']}",
        f"suspect pages (retried)      {outcome['pages_suspect']}",
        f"requests made                {outcome['requests_made']}",
        f"bytes stored (gzip)          {outcome['bytes_stored']}"])
