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

Matching by the page's own stock symbol (owner, 26 Oct 2026; measured offline: matching by name found 1,534 of 1,866 companies,
82%; the misses are renames (Eternal = zomato-ltd, KSB = ksb-pumps-limited), brackets, a dropped "and" and Tijori's own typos).
Every financials page names its NSE symbol in ``company_details``, so a run SWEEPS the sitemap: it fetches each slug's financials
page once (the same client, limiter and refusal rules), records ``slug -> the page's symbol`` in the saved slug map (KV
``tijoridl:slugs``, kept between days: a later run fetches our companies straight by slug and sweeps only slugs not yet in it) and
stores the page when its symbol is one of our companies'. A symbol match beats a name match. A page that carries no symbol is
recorded as "" and its slug is matched to a company by the name rule below (that fallback only); a slug with no page (302, 404)
is recorded as "!" and never asked again. Two slugs with one symbol: the first page stored wins, both are listed in the summary.

Slug map by name (the fallback): the sitemap (``/sitemap.xml``, one request a run) lists 5,741 companies as ``/company/<slug>/``; the slugs are
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
# Threads. Measured 26 Oct 2026 (trial run 40341400053): 201 requests in 97 s, about 2 a second though the rate is 6, because
# a GitHub runner's per-request latency is 3-4 s and 8 threads cap the throughput at about 8 / 3.5. With 32 threads the one
# shared limiter (TIJORI_RATE, 6 a second) is the cap again. The rate and the refusal policy are unchanged.
WORKERS = int(os.environ.get("TIJORI_WORKERS", "32"))
MISS_LIMIT = 20                                   # more than this many 302 / 404 answers in a row is a suspected refusal
SAVE_EVERY = 25                                   # finished companies (or swept slugs) between two saves of the done list / slug map
PREFIX = "raw/tijori/"
DONE_KEY = "tijoridl:done"          # + ":<day>": the symbols a run finished
SLUGS_KEY = "tijoridl:slugs"        # {"built": iso, "slugs": {slug: page symbol | "" (none on the page) | "!1:<day>" (no page once, on that day; plain "!1" in older maps; asked again, final only on a later day) | "!" (no page twice)}}, kept between days
SITEMAP_COMPANIES = 5741            # measured 26 Oct 2026; only the estimate before a run uses it
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
    (up to ``WORKERS``, 32, of them: slots reserved before the first refusal still go out at the fast rate) do not count as a second: they are retried at the slow pace."""

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
        self._misses = 0                        # 302 / 404 answers in a row

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
            if response.status_code in (302, 404):
                with self._lock:
                    self._misses += 1
                    streak = self._misses > MISS_LIMIT
                    if streak:
                        self._misses = 0
                if streak:    # real dead slugs are rare: a long run of them is a soft block, so slow down (then stop) and ask again
                    self._refused(f"more than {MISS_LIMIT} answers of 302 or 404 in a row (last from {url})", was_slow)
                    continue
                return response.status_code, ""
            with self._lock:
                self._misses = 0
            if response.status_code != 200:
                return response.status_code, ""
            body = response.text
            if f'id="{TABLES_ID}"' not in body and is_challenge(body):
                self._refused(f"a CAPTCHA or challenge page from {url}", was_slow)
                continue
            return 200, body


# --- the run ------------------------------------------------------------------------------------------------------

def estimate(companies: int, rate: float = RATE, sweep: int = 0) -> dict:
    """One page a company, one page a slug still to sweep, plus the sitemap, ``rate`` requests a second."""
    n = companies + sweep + 1
    return {"requests": n, "seconds": round(n / rate)}


def load_slug_map(sink) -> dict:
    """The saved slug map ``{slug: symbol}`` ({} when none or unreadable)."""
    try:
        data = json.loads(sink.kv_get(SLUGS_KEY) or "{}")
        slugs = data.get("slugs") if isinstance(data, dict) else None
        return {str(k): str(v) for k, v in slugs.items()} if isinstance(slugs, dict) else {}
    except ValueError:
        return {}


def save_slug_map(sink, slugs: dict, built: str) -> None:
    sink.kv_set(SLUGS_KEY, json.dumps({"built": built, "slugs": slugs}, separators=(",", ":"), sort_keys=True), now_iso())


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


def _sweep_fetch(client, slug: str, ours: set) -> dict:
    """One sitemap slug's page read once: ``{"kind": "swept", "symbol": <page symbol, "" if none, "!" if no page>, "blob"?}``;
    the blob (the tables) only when the page's symbol is one of ``ours`` (upper case). "failed" and "suspect" are not recorded."""
    status, body = client.get(url_for(slug))
    if status == 200:
        tables, page = extract_tables(body), identity(body)
        if tables is None and 'id="company_details"' not in body:
            return {"kind": "suspect", "note": f"sweep {slug}: 200 page without tables or company_details"[:200]}
        symbol = page["symbol"].strip().upper()
        out = {"kind": "swept", "symbol": symbol}
        if tables is None:
            out["no_tables"] = True
        elif symbol and symbol in ours:
            out["blob"] = pack(json.dumps(tables, separators=(",", ":"), ensure_ascii=False))
        return out
    if status in (302, 404):    # not final on first sight: ``run`` records "!1" and asks again next run (a soft block redirects)
        return {"kind": "swept", "symbol": "!"}
    return {"kind": "failed", "note": f"sweep {slug}: {'HTTP ' + str(status) if status else body}"[:200]}


def run(sink, companies: list[tuple[str, str, str]], client, day: str, time_budget: float = 17400.0,
        restart: bool = False, clock=time.monotonic, workers: int = WORKERS, rebuild_map: bool = False,
        sweep_limit: int | None = None) -> dict:
    """Fetch and store the financials page of each company ((scrip, symbol, name), in symbol order) on ``workers`` threads
    behind the client's one shared limiter. The sink is written from this thread only. A second refusal propagates as
    ``TijoriRefused`` after what was fetched is stored and the finished companies and the slug map are saved. ``more`` is true
    when the time budget ended the run with companies or slugs left (slugs a failed request or a ``sweep_limit`` left are in
    ``slugs_left_to_sweep`` and the next run sweeps them). A page already stored for ``day`` is not fetched again; a company is finished when its page is stored,
    verified wrong, answered 302 or 404, or had no tables (those do not change on a retry); a network or server error is tried
    again by the next run.

    Order: (1) the sitemap and the saved slug map (``rebuild_map`` re-sweeps every slug, keeping old entries of those not yet re-swept); (2) the SWEEP of every sitemap slug not in the map
    (at most ``sweep_limit``): each page read once, its symbol recorded, stored when it is one of ours; (3) our companies whose
    symbol is in the map but not yet stored today, fetched by slug; (4) the name rule, for the companies still without a slug and
    only against slugs whose page had no symbol."""
    key = f"{DONE_KEY}:{day}"
    done = set() if restart else set(json.loads(sink.kv_get(key) or "[]"))
    done_at_start = set(done)    # "finished by an earlier run" counts only these, not what this run's sweep finished
    stored = set(sink.list_objects(f"{PREFIX}{day}/"))
    totals = {"day": day, "companies": len(companies), "companies_done_before": 0, "pages_stored": 0,
              "pages_already_stored": 0, "pages_no_page": 0, "pages_not_verified": 0, "pages_no_tables": 0,
              "pages_failed": 0, "pages_suspect": 0, "requests_made": 0, "bytes_stored": 0, "slugs_swept": 0}
    before = client.requests
    status, xml = client.get(SITEMAP_URL)
    slugs = sitemap_slugs(xml) if status == 200 else []
    failed: list[str] = [] if slugs else [f"sitemap: {'HTTP ' + str(status) if status else xml}"[:200]]
    not_verified: list[str] = []
    suspect: list[str] = []
    slug_map = load_slug_map(sink)    # a rebuild starts from a copy: a slug not re-swept keeps its old entry, so a cut sweep never shrinks the saved map
    reswept: set[str] = set()
    built = now_iso()
    ours = {symbol.strip().upper(): symbol for _, symbol, _ in companies}
    started = clock()
    deadline = started + time_budget
    deferred = threading.Event()
    map_unsaved = 0
    sweep_no_tables: set[str] = set()    # symbols whose swept page had no tables: finished only when no other slug carries the symbol

    def have(symbol: str) -> bool:
        return symbol in done or object_key(day, symbol) in stored

    def work(fn, *args):
        if clock() >= deadline:
            deferred.set()
            return None
        try:
            return fn(*args)
        except TijoriRefused:
            raise
        except Exception as exc:    # one bad page must not end the run: it is retried by the next one
            log.warning("tijori %s: unexpected %s: %s", args[1] if len(args) > 1 else "", type(exc).__name__, exc)
            return {"kind": "failed", "note": f"{args[1] if len(args) > 1 else ''}: unexpected {type(exc).__name__}: {exc}"[:200]}

    def count(got):
        """The tally of a company page's answer; True when it ends the company for today."""
        kind = got["kind"]
        if kind == "failed":
            totals["pages_failed"] += 1
            failed.append(got["note"])
            return False
        if kind == "suspect":
            totals["pages_suspect"] += 1
            suspect.append(got["note"])
            return False
        if kind != "stored":
            totals[_COUNTER[kind]] += 1
            if kind == "not_verified":
                not_verified.append(got["note"])
        return True

    def finish_totals() -> None:
        totals["requests_made"] = client.requests - before
        totals["elapsed_seconds"] = round(max(clock() - started, 0.0), 1)
        totals["requests_per_second"] = round(totals["requests_made"] / totals["elapsed_seconds"], 2) if totals["elapsed_seconds"] else 0.0

    def put(symbol: str, blob: bytes) -> None:
        sink.put_object(object_key(day, symbol), blob, "application/gzip")
        stored.add(object_key(day, symbol))
        totals["pages_stored"] += 1
        totals["bytes_stored"] += len(blob)

    refused: TijoriRefused | None = None
    unsaved = 0
    by_name_symbols: set[str] = set()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        # (2) the sweep
        to_sweep = [s for s in slugs if rebuild_map or s not in slug_map or slug_map[s].startswith("!1")]    # "!1...": no page last time, asked once more
        if sweep_limit is not None:
            to_sweep = to_sweep[:sweep_limit]
        futures = [(s, pool.submit(work, _sweep_fetch, client, s, set(ours))) for s in to_sweep]
        for slug, future in futures:
            try:
                got = future.result()
            except TijoriRefused as exc:
                refused = refused or exc
                continue
            if got is None:
                continue
            if got["kind"] == "failed":
                totals["pages_failed"] += 1
                failed.append(got["note"])
                continue
            if got["kind"] == "suspect":
                totals["pages_suspect"] += 1
                suspect.append(got["note"])
                continue
            totals["slugs_swept"] += 1
            reswept.add(slug)
            if got["symbol"] == "!":    # a first miss is "!1:<day>" (retried); final only when a later day misses again
                prev = slug_map.get(slug, "")
                first_day = prev[3:] if prev.startswith("!1:") else ""
                if prev == "!1" or (first_day and first_day < day):
                    slug_map[slug] = "!"
                elif prev.startswith("!1:"):
                    slug_map[slug] = prev    # a second miss on the same day: still the first
                else:
                    slug_map[slug] = f"!1:{day}"
            else:
                slug_map[slug] = got["symbol"]
            map_unsaved += 1
            symbol = ours.get(got["symbol"])
            if symbol and "blob" in got and not have(symbol):
                put(symbol, got["blob"])
                done.add(symbol)
                unsaved += 1
            elif symbol and got.get("no_tables") and not have(symbol):
                sweep_no_tables.add(symbol)
            if map_unsaved >= SAVE_EVERY:
                save_slug_map(sink, slug_map, built)
                map_unsaved = 0
            if unsaved >= SAVE_EVERY:
                sink.kv_set(key, json.dumps(sorted(done)), now_iso())
                unsaved = 0
        if slugs:    # a failed or empty sitemap never overwrites the saved map (a --rebuild-map run starts from a copy of it and overwrites only what it re-sweeps)
            save_slug_map(sink, slug_map, built)
        sink.kv_set(key, json.dumps(sorted(done)), now_iso())
        unsaved = 0
        if refused:
            finish_totals()
            raise refused

        # (3) our companies by their symbol in the map, (4) then by name against the slugs with no symbol
        by_symbol: dict[str, list[str]] = {}
        for slug, sym in slug_map.items():
            if sym and sym != "!" and sym in ours:
                by_symbol.setdefault(sym, []).append(slug)
        by_symbol = {k: sorted(v) for k, v in by_symbol.items()}
        for symbol in sorted(sweep_no_tables):    # one slug: its page is the answer; two or more: the todo list tries each in turn
            if len(by_symbol.get(symbol.upper(), [])) <= 1 and not have(symbol):
                totals["pages_no_tables"] += 1
                done.add(symbol)
        todo = []
        rest = []
        for scrip, symbol, name in companies:
            up = symbol.strip().upper()
            if up in by_symbol:
                if symbol in done:
                    if symbol in done_at_start:
                        totals["companies_done_before"] += 1
                elif object_key(day, symbol) in stored:
                    totals["pages_already_stored"] += 1
                    done.add(symbol)
                else:
                    todo.append((symbol, name, by_symbol[up]))
            else:
                rest.append((scrip, symbol, name))
        nosym = [s for s, v in slug_map.items() if v == ""]
        mapping = map_slugs(rest, nosym) if nosym else {"matched": {}, "ambiguous": {}, "unmatched": [m[1] for m in rest]}
        for scrip, symbol, name in rest:
            slug = mapping["matched"].get(symbol) or mapping["ambiguous"].get(symbol)
            if not slug:
                continue
            by_name_symbols.add(symbol)
            if symbol in done:
                if symbol in done_at_start:
                    totals["companies_done_before"] += 1
            elif object_key(day, symbol) in stored:
                totals["pages_already_stored"] += 1
                done.add(symbol)
            else:
                todo.append((symbol, name, slug))
        futures = [(item[0], pool.submit(work, _fetch, client, item[0], item[1], item[2])) for item in todo]
        for symbol, future in futures:
            try:
                got = future.result()
            except TijoriRefused as exc:
                refused = refused or exc
                continue
            if got is None:
                continue
            if not count(got):
                continue
            if got["kind"] == "stored":
                put(symbol, got["blob"])
            done.add(symbol)
            unsaved += 1
            if unsaved >= SAVE_EVERY:
                sink.kv_set(key, json.dumps(sorted(done)), now_iso())
                unsaved = 0
    sink.kv_set(key, json.dumps(sorted(done)), now_iso())
    finish_totals()
    if refused:
        raise refused
    unmatched = [symbol for _, symbol, _ in companies if symbol.strip().upper() not in by_symbol and symbol not in by_name_symbols]
    duplicates = {ours[k]: v for k, v in by_symbol.items() if len(v) > 1}
    left = sum(1 for s in slugs if (s not in reswept if rebuild_map else s not in slug_map) or slug_map.get(s, "").startswith("!1"))
    return {"more": deferred.is_set(), "failed": failed, "suspect": suspect, "not_verified": not_verified,
            "sitemap_companies": len(slugs), "slugs_in_map": len(slug_map), "slugs_left_to_sweep": left,
            "ours_by_symbol": len(by_symbol), "ours_by_name": len(by_name_symbols), "ours_unmatched": unmatched,
            "duplicate_symbols": duplicates,
            "matched": len(by_symbol) + len(mapping["matched"]), "ambiguous": mapping["ambiguous"], "unmatched": unmatched,
            "slowed": client.slowed, "slowed_after_requests": client.slowed_after, "refusal": client.refusal, **totals}


def render(outcome: dict) -> str:
    return "\n".join([
        f"tijori download for {outcome['day']}:",
        f"companies                    {outcome['companies']}",
        f"companies in the sitemap     {outcome['sitemap_companies']}",
        f"slugs swept this run         {outcome['slugs_swept']}",
        f"slugs in the saved map       {outcome['slugs_in_map']} ({outcome['slugs_left_to_sweep']} still to sweep)",
        f"ours matched by symbol       {outcome['ours_by_symbol']}",
        f"ours matched by name         {outcome['ours_by_name']}",
        f"ours unmatched               {len(outcome['ours_unmatched'])}",
        f"symbols on two or more slugs {len(outcome['duplicate_symbols'])}",
        f"finished by an earlier run   {outcome['companies_done_before']}",
        f"pages stored                 {outcome['pages_stored']}",
        f"pages already stored         {outcome['pages_already_stored']}",
        f"no such page (302 or 404)    {outcome['pages_no_page']}",
        f"page not this company        {outcome['pages_not_verified']}",
        f"page without tables          {outcome['pages_no_tables']}",
        f"pages that failed            {outcome['pages_failed']}",
        f"suspect pages (retried)      {outcome['pages_suspect']}",
        f"requests made                {outcome['requests_made']}",
        f"elapsed seconds              {outcome['elapsed_seconds']}",
        f"requests a second            {outcome['requests_per_second']}",
        f"bytes stored (gzip)          {outcome['bytes_stored']}"])
