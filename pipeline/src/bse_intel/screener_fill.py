"""One-time fill of the quarters memory lacks from screener.in's quarterly results table. No AI. TRACKER F161, TODO row 48.

Owner permission (26 Oct 2026): screener.in, one time, at least 3 seconds between calls, a plain browser User-Agent, no
login. It is not an exchange file, so every figure it fills is labelled ``by="screener"`` with the source id
``screener:<SYMBOL>:<period>:<basis>``, kept in the dossier's own section (``dossier.SCREENER_KEY``), and no card reads it
unless MEMORY_SCREENER is on (``dossier.with_screener``).

Measured 26 Oct 2026 on 30 companies (raw pages kept as test fixtures): screener's "Net Profit" is our ``pat`` (profit
including the minority's share) for non-banks, 210 of 223 quarters within ₹1 Cr; banks and insurers disagree, so lenders
are skipped whole. "Sales" equals revenue from operations for most companies and is lower by a steady amount for RELIANCE,
ITC, HINDUNILVR and GAIL, so revenue is filled only for a company whose own overlap proves the line. NMDC's Q4FY25
consolidated column on screener (11,343 sales, 2,027 profit) is not what the company's PDF says (7,004.59, 1,483.18): the
overlap checks below are what keep one such column from filling anything.

A quarter-metric is filled only when all of these hold:

1. memory lacks it: a gap per ``memory_gaps.check`` (after the standalone rule), and no figure of any source, basis or an
   earlier fill is there for that metric and quarter (nothing is ever overwritten);
2. the page is the one on memory's basis for the company (consolidated page for consolidated), the page says so itself,
   and the quarter's column is on it;
3. profit: the company is not a lender (bank, NBFC, insurer) and the profit is at least ₹10 Cr either way;
4. revenue: on every quarter where memory has an exchange-file revenue and screener has the column (at least 3), screener's
   Sales is within ₹1 Cr (or 0.1%) of ours;
5. alignment: on those quarters profit agrees too (at least 3, all within ₹1 Cr or 0.5%), else nothing is filled for the
   company; and where memory holds a year, half year or nine months covering the quarter, the sum of its quarters (memory's
   and the proposed ones) agrees with it within ₹2 Cr or 0.5%, else the quarter is skipped.

A dry run (the default) fetches and decides but writes nothing. ``--apply`` writes through the three-way merge.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time

import httpx

from . import line_map
from .dossier import (SCREENER_KEY, SCREENER_PREFIX, _entry_basis, _norm, keep_concurrent_writes, put_screener,
                      screener_figures)
from .metrics import CONSOLIDATED, STANDALONE, _figures, is_lender
from .periods import quarter_index
from .timeutil import now_iso

log = logging.getLogger(__name__)

BASE = "https://www.screener.in/company/"
# a plain browser User-Agent (owner's permission, 26 Oct 2026); no login, no cookies kept between companies
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
PAUSE_SECONDS = 3.2          # between two requests of one runner: at least 3 s (owner); at most 2 runners at once
MAX_SHARDS = 2
TRIED_KEY = "screenerfill:tried"        # kv: companies a real run already tried
DRY_TRIED_KEY = "screenerfill:dry_tried"   # kv: companies a dry run already looked at

MIN_PROFIT_CR = 10.0
REVENUE_ABS, REVENUE_REL = 1.0, 0.001
PROFIT_ABS, PROFIT_REL = 1.0, 0.005
SUM_ABS, SUM_REL = 2.0, 0.005
MIN_OVERLAPS = 3

METRICS = ("revenue", "pat")
REASONS = ("bank", "small profit", "revenue line differs", "misaligned", "sum check", "page basis missing",
           "no column", "has figure", "no memory basis", "page error")


class ScreenerRefused(RuntimeError):
    """screener.in answered 403, 429 or 503: stop, never push on."""


# --- the page -----------------------------------------------------------------------------------------------------

_MONTH_QUARTER = {"Jun": 1, "Sep": 2, "Dec": 3, "Mar": 4}


def period_of(column: str) -> str | None:
    """"Sep 2025" -> Q2FY26 (the Indian year runs April to March)."""
    m = re.fullmatch(r"\s*(Jun|Sep|Dec|Mar)\w*\s+(20\d{2})\s*", column or "")
    if not m:
        return None
    year = int(m[2]) + (0 if m[1] == "Mar" else 1)
    return f"Q{_MONTH_QUARTER[m[1]]}FY{year % 100:02d}"


def _text(cell: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", cell)).replace("\xa0", " ").strip()


def _number(cell: str) -> float | None:
    text = cell.replace(",", "").replace("%", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _row_of(rows: dict[str, list[float | None]], key: str) -> list[float | None]:
    """The first non-empty row among the names the line map gives the line on screener ("Sales", else "Revenue"); [] when
    none (what ``rows.get(a) or rows.get(b) or []`` was)."""
    for name in line_map.screener_rows(key):
        if rows.get(name):
            return rows[name]
    return []


def _section_table(body: str, section_id: str) -> tuple[list[str], dict[str, list[float | None]], str] | None:
    """A results section of a company page ("quarters", "profit-loss"): its column titles, its rows by label (the
    trailing "+" of an expandable label removed) and the section's own text; None when there is no such table."""
    start = body.find(f'id="{section_id}"')
    if start < 0:
        return None
    end = body.find("</section>", start)
    section = body[start:end if end > 0 else len(body)]
    table = re.search(r"<table.*?</table>", section, re.S)
    if not table:
        return None
    head, _, rest = table.group(0).partition("</thead>")
    columns = [_text(c) for c in re.findall(r"<th[^>]*>(.*?)</th>", head, re.S)][1:]
    rows: dict[str, list[float | None]] = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", rest, re.S):
        cells = [_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if cells:
            rows[re.sub(r"\s*\+$", "", cells[0]).strip()] = [_number(c) for c in cells[1:]]
    return columns, rows, section


def _basis_of(section: str) -> str | None:
    which = re.search(r"(Consolidated|Standalone)\s+Figures", re.sub(r"<[^>]+>", " ", section))
    return {"Consolidated": CONSOLIDATED, "Standalone": STANDALONE}.get(which[1]) if which else None


def parse_page(body: str) -> dict | None:
    """The quarters section of a company page: ``{"basis": CONSOLIDATED | STANDALONE | None, "quarters": {period:
    {"revenue": Sales, "pat": Net Profit}}}``; None when the page has no such section. Whole-crore figures, as printed."""
    got = _section_table(body, "quarters")
    if not got:
        return None
    columns, rows, section = got
    sales = _row_of(rows, "revenue")
    profit = _row_of(rows, "pat")
    quarters: dict[str, dict] = {}
    for i, column in enumerate(columns):
        period = period_of(column)
        if period:
            quarters[period] = {"revenue": sales[i] if i < len(sales) else None,
                                "pat": profit[i] if i < len(profit) else None}
    return {"basis": _basis_of(section), "quarters": quarters}


def year_of(column: str) -> str | None:
    """"Mar 2025" -> FY25 (the annual section's columns; "TTM" is not a year)."""
    m = re.fullmatch(r"\s*Mar\w*\s+(20\d{2})\s*", column or "")
    return f"FY{int(m[1]) % 100:02d}" if m else None


# the six other lines of screener's quarterly table (27 Oct 2026), by our line key; "Tax %" is a ratio, no line of ours
SIX_LINES = ("ebitda", "other_income", "finance_cost", "depreciation", "pbt")
TAX_ROW = "Tax %"
LENDER_ROW = "Financing Profit"   # a lender page's own layout: "Revenue", "Interest", "Financing Profit", "Financing Margin %"


def parse_full(body: str) -> dict | None:
    """parse_page plus EPS per quarter, the six other lines (``ebitda`` = Operating Profit, ``other_income``,
    ``finance_cost`` = Interest, ``depreciation``, ``pbt`` = Profit before tax, ``tax_pct`` = Tax %; None where the page has
    no such row) and the annual profit and loss section: ``{"basis", "lender_layout", "quarters": {period: {"revenue",
    "pat", "eps", ...six}}, "annual": {"FY25": {"revenue", "pat", "eps"}}}`` (``annual`` empty when the page has no such
    section). ``lender_layout`` is true on a page that has Financing Profit (its Interest row is not a non-lender's).
    Used by the cross-check, which reads stored pages."""
    page = parse_page(body)
    if page is None:
        return None
    columns, rows, _ = _section_table(body, "quarters")
    eps = _row_of(rows, "eps")
    six = {key: _row_of(rows, key) for key in SIX_LINES}
    six["tax_pct"] = rows.get(TAX_ROW) or []
    page["lender_layout"] = bool(rows.get(LENDER_ROW))
    for i, column in enumerate(columns):
        period = period_of(column)
        if period:
            page["quarters"][period]["eps"] = eps[i] if i < len(eps) else None
            for key, row in six.items():
                page["quarters"][period][key] = row[i] if i < len(row) else None
    annual: dict[str, dict] = {}
    pl = _section_table(body, "profit-loss")
    if pl:
        columns, rows, _ = pl
        sales = _row_of(rows, "revenue")
        profit = _row_of(rows, "pat")
        eps = _row_of(rows, "eps")
        for i, column in enumerate(columns):
            year = year_of(column)
            if year:
                annual[year] = {"revenue": sales[i] if i < len(sales) else None,
                                "pat": profit[i] if i < len(profit) else None,
                                "eps": eps[i] if i < len(eps) else None}
    page["annual"] = annual
    return page


def url_for(symbol: str, basis: str) -> str:
    return f"{BASE}{symbol}/consolidated/" if basis == CONSOLIDATED else f"{BASE}{symbol}/"


class ScreenerClient:
    """Plain HTTP: a browser User-Agent, no login, at least ``pause`` seconds between two requests."""

    def __init__(self, pause: float = PAUSE_SECONDS, transport: httpx.BaseTransport | None = None, sleep=time.sleep,
                 clock=time.monotonic):
        self._client = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
                                    timeout=30.0, follow_redirects=True, transport=transport)
        self.pause, self._sleep, self._clock = pause, sleep, clock
        self._last: float | None = None
        self.requests = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._client.close()

    def get(self, url: str) -> tuple[int, str]:
        if self._last is not None:
            wait = self.pause - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()
        self.requests += 1
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            return 0, f"{type(exc).__name__}: {exc}"[:200]
        if response.status_code in (403, 429, 503):
            raise ScreenerRefused(f"HTTP {response.status_code} from {url}")
        return response.status_code, response.text if response.status_code == 200 else ""


# --- the decision ---------------------------------------------------------------------------------------------------

def _near(ours: float, theirs: float, absolute: float, relative: float) -> bool:
    return abs(ours - theirs) <= max(absolute, relative * abs(ours))


def _members(total: str) -> list[str] | None:
    """The quarters a year, half year or nine months holds: FY26 -> Q1FY26..Q4FY26."""
    m = re.fullmatch(r"(FY|H1FY|H2FY|9MFY)(\d{2})", total)
    if not m:
        return None
    quarters = {"FY": (1, 2, 3, 4), "H1FY": (1, 2), "H2FY": (3, 4), "9MFY": (1, 2, 3)}[m[1]]
    return [f"Q{q}FY{m[2]}" for q in quarters]


def _known(dossier: dict, basis: str) -> dict[tuple[str, str], float]:
    """Every figure memory holds on this basis, whatever its source (a figure with no basis recorded counts)."""
    out: dict[tuple[str, str], float] = {}
    for entry in dossier.get("financial_metrics", []):
        if isinstance(entry, dict) and entry.get("value") is not None and _entry_basis(entry) in (basis, None):
            out[(_norm(entry["metric"]), entry["period"])] = entry["value"]
    if basis == STANDALONE:
        for entry in (dossier.get("standalone") or {}).get("metrics", []):
            if entry.get("value") is not None:
                out.setdefault((_norm(entry["metric"]), entry["period"]), entry["value"])
    return out


def _held(dossier: dict) -> set[tuple[str, str]]:
    """(metric, period) pairs any figure of any source or basis already covers: never overwritten."""
    held = {(_norm(e["metric"]), e["period"]) for e in dossier.get("financial_metrics", [])
            if isinstance(e, dict) and e.get("value") is not None}
    held |= {(e["metric"], e["period"]) for e in screener_figures(dossier)}
    for e in (dossier.get("standalone") or {}).get("metrics", []):
        if e.get("value") is not None:
            held.add((_norm(e["metric"]), e["period"]))
    return held


def _overlap(dossier: dict, basis: str, page: dict) -> dict[str, list[tuple[str, float, float]]]:
    """Per metric, the quarters where memory has the exchange file's figure and the page has the column: (period, ours,
    theirs). Only a figure from an exchange file counts as ours (metrics._figures)."""
    figures, _ = _figures(dossier, basis)
    out: dict[str, list[tuple[str, float, float]]] = {m: [] for m in METRICS}
    for (metric, period), entry in sorted(figures.items(), key=lambda kv: kv[0][1]):
        if metric in METRICS and quarter_index(period) and entry.get("value") is not None:
            theirs = (page["quarters"].get(period) or {}).get(metric)
            if theirs is not None:
                out[metric].append((period, entry["value"], theirs))
    return out


def decide(dossier: dict, result: dict, page: dict | None, symbol: str) -> dict:
    """What to fill for one company from its page: ``{"fills", "skipped", "evidence"}``. Pure: no request, no write.
    ``result`` is memory_gaps.check's; ``page`` is parse_page's (None: no page / no quarters section)."""
    basis = result.get("basis")
    targets = list(result["missing"]) + list(result.get("partial") or [])
    if result.get("missing_year_ago") and result.get("year_ago") and result["year_ago"] not in targets:
        targets.append(result["year_ago"])
    targets = [p for p in dict.fromkeys(targets) if quarter_index(p)]
    out: dict = {"fills": [], "skipped": [], "evidence": {}}

    def skip_all(reason: str) -> dict:
        out["skipped"] += [{"period": p, "metric": m, "reason": reason} for p in targets for m in METRICS]
        return out

    if not basis:
        return skip_all("no memory basis")
    if is_lender(dossier, basis):
        return skip_all("bank")
    if page is None or page.get("basis") != basis:
        return skip_all("page basis missing")

    held = _held(dossier)
    wanted = []
    for period in targets:
        for metric in METRICS:
            if (metric, period) in held:
                out["skipped"].append({"period": period, "metric": metric, "reason": "has figure"})
            else:
                wanted.append((period, metric))

    overlaps = _overlap(dossier, basis, page)
    revenue_n, profit_n = len(overlaps["revenue"]), len(overlaps["pat"])
    revenue_gap = max((abs(o - t) for _, o, t in overlaps["revenue"]), default=None)
    profit_gap = max((abs(o - t) for _, o, t in overlaps["pat"]), default=None)
    out["evidence"] = {"revenue_overlaps": revenue_n, "revenue_max_diff": revenue_gap,
                       "pat_overlaps": profit_n, "pat_max_diff": profit_gap}
    aligned = profit_n >= MIN_OVERLAPS and all(_near(o, t, PROFIT_ABS, PROFIT_REL) for _, o, t in overlaps["pat"])
    revenue_ok = revenue_n >= MIN_OVERLAPS and all(_near(o, t, REVENUE_ABS, REVENUE_REL) for _, o, t in overlaps["revenue"])
    if not aligned:   # the columns are not proved to be the quarters we think: nothing at all from this company
        out["skipped"] += [{"period": p, "metric": m, "reason": "misaligned"} for p, m in wanted]
        return out

    proposed: dict[tuple[str, str], float] = {}
    for period, metric in wanted:
        value = (page["quarters"].get(period) or {}).get(metric)
        if period not in page["quarters"] or value is None:
            out["skipped"].append({"period": period, "metric": metric, "reason": "no column"})
        elif metric == "pat" and abs(value) < MIN_PROFIT_CR:
            out["skipped"].append({"period": period, "metric": metric, "reason": "small profit"})
        elif metric == "revenue" and not revenue_ok:
            out["skipped"].append({"period": period, "metric": metric, "reason": "revenue line differs"})
        else:
            proposed[(metric, period)] = value

    # a year, half year or nine months memory holds must be matched by its quarters, memory's and ours together
    known = _known(dossier, basis)
    checks: dict[tuple[str, str], int] = {}
    while True:
        failed = set()
        checks = {}
        for (metric, period), value in proposed.items():
            for total in [t for t in {f"FY{period[-2:]}", f"H1FY{period[-2:]}", f"H2FY{period[-2:]}", f"9MFY{period[-2:]}"}
                          if period in (_members(t) or []) and (metric, t) in known]:
                parts = []
                for q in _members(total):
                    got = known.get((metric, q), proposed.get((metric, q)))
                    parts.append(got)
                if any(p is None for p in parts):
                    continue   # a member neither memory nor the page gives: nothing to compare yet
                checks[(metric, period)] = checks.get((metric, period), 0) + 1
                if not _near(known[(metric, total)], sum(parts), SUM_ABS, SUM_REL):
                    failed.add((metric, period))
        if not failed:
            break
        for key in failed:
            proposed.pop(key)
            out["skipped"].append({"period": key[1], "metric": key[0], "reason": "sum check"})
    for (metric, period), value in sorted(proposed.items(), key=lambda kv: (quarter_index(kv[0][1]), kv[0][0])):
        out["fills"].append({"period": period, "metric": metric, "value": value, "basis": basis,
                             "source": f"{SCREENER_PREFIX}{symbol}:{period}:{basis}", "sum_checks": checks.get((metric, period), 0)})
    return out


# --- the run ----------------------------------------------------------------------------------------------------------

def symbol_of(company: dict | None, fallback: str = "") -> str:
    return ((company or {}).get("symbol") or fallback or "").strip().upper()


def run(sink, report: dict, symbols: dict[str, str], client, apply: bool = False, time_budget: float = 17400.0,
        restart: bool = False, shard: tuple[int, int] | None = None, clock=time.monotonic) -> dict:
    """Look at the gap companies of a memory_gaps ``report`` (those only; a company with none costs no request), one
    page each (the page on memory's basis), and decide the fill; with ``apply`` write it. A company already tried by an
    earlier run of the same mode is skipped unless ``restart`` (the list is saved after every company); ``more`` is true
    when the time budget ended the run with companies left. A refusal from screener.in propagates."""
    from . import memory_gaps
    from .backup import RunBackup

    suffix = f":{shard[0]}of{shard[1]}" if shard else ""
    # each dossier is saved to R2 backup/ before its first write; a shard has its own folder (shards start together)
    backup = RunBackup(sink, "screener-fill" + suffix.replace(":", "-")) if apply else None
    key = (TRIED_KEY if apply else DRY_TRIED_KEY) + suffix
    tried = set() if restart else set(json.loads(sink.kv_get(key) or "[]"))
    todo = [s for s, r in sorted(report["companies"].items()) if memory_gaps.has_gap(r)]
    if shard:
        todo = todo[shard[0]::shard[1]]
    totals = {"companies_with_gaps": len(todo), "companies_fetched": 0, "requests_made": 0, "companies_skipped_tried": 0,
              "companies_failed": 0, "companies_with_fills": 0, "fillable": {m: 0 for m in METRICS}, "written": 0,
              "skipped": {}}
    rows: list[dict] = []
    failed: list[str] = []
    more = False
    deadline = clock() + time_budget
    for scrip in todo:
        if scrip in tried:
            totals["companies_skipped_tried"] += 1
            continue
        if clock() >= deadline:
            more = True
            break
        result = report["companies"][scrip]
        dossier = sink.get_dossier(scrip) or {}
        symbol = symbols.get(scrip, "")
        page, error = None, None
        needs_page = bool(result.get("basis")) and not is_lender(dossier, result.get("basis")) and bool(symbol)
        if needs_page:
            before = client.requests
            status, body = client.get(url_for(symbol, result["basis"]))
            totals["requests_made"] += client.requests - before
            if status == 200:
                totals["companies_fetched"] += 1
                page = parse_page(body)
            else:
                error = f"HTTP {status}" if status else body
        elif not symbol and result.get("basis") and not is_lender(dossier, result.get("basis")):
            error = "no symbol"
        if error:
            totals["companies_failed"] += 1
            failed.append(f"{scrip} {symbol}: {error}"[:200])
            decision = decide(dossier, result, None, symbol)
            for s in decision["skipped"]:
                s["reason"] = "page error"
        else:
            decision = decide(dossier, result, page, symbol)
        for s in decision["skipped"]:
            totals["skipped"][s["reason"]] = totals["skipped"].get(s["reason"], 0) + 1
        for fill in decision["fills"]:
            totals["fillable"][fill["metric"]] += 1
            rows.append({"scrip": scrip, "symbol": symbol, "basis": fill["basis"], "period": fill["period"],
                         "metric": fill["metric"], "value": fill["value"], "source": fill["source"],
                         "sum_checks": fill["sum_checks"], **decision["evidence"]})
        if decision["fills"]:
            totals["companies_with_fills"] += 1
            if apply:
                totals["written"] += _write(sink, scrip, symbol, decision["fills"], backup)
        tried.add(scrip)
        sink.kv_set(key, json.dumps(sorted(tried)), now_iso())
    return {"apply": apply, "more": more, "failed": failed, "rows": rows, **totals}


def _write(sink, scrip: str, symbol: str, fills: list[dict], backup=None) -> int:
    """The fills into the company's memory through the three-way merge; never over a figure that is there."""
    read = sink.get_dossier(scrip)
    if read is None:
        return 0
    merged = json.loads(json.dumps(read))
    added = put_screener(merged, fills, symbol, now_iso())
    if added:
        keep_concurrent_writes(merged, read, sink.get_dossier(scrip))
        if backup is not None:
            backup.dossier(scrip)
        sink.put_dossier(scrip, merged)
    return added


def render(outcome: dict) -> str:
    skipped = outcome["skipped"]
    lines = [f"screener fill ({'applied' if outcome['apply'] else 'dry run, nothing written'}):",
             f"companies with gaps          {outcome['companies_with_gaps']}",
             f"already tried, skipped       {outcome['companies_skipped_tried']}",
             f"pages fetched                {outcome['companies_fetched']}",
             f"requests made                {outcome['requests_made']}",
             f"pages that failed            {outcome['companies_failed']}",
             f"companies with a fill        {outcome['companies_with_fills']}",
             f"quarters fillable, revenue   {outcome['fillable']['revenue']}",
             f"quarters fillable, profit    {outcome['fillable']['pat']}"]
    if outcome["apply"]:
        lines.append(f"figures written              {outcome['written']}")
    lines.append("skipped (quarter-metrics) by reason:")
    lines += [f"  {reason:24}{skipped[reason]}" for reason in sorted(skipped, key=lambda r: -skipped[r])] or ["  none"]
    return "\n".join(lines)


CSV_HEADER = ("scrip,symbol,basis,period,metric,value,source_id,revenue_overlaps,revenue_max_diff,pat_overlaps,"
              "pat_max_diff,sum_checks")


def to_csv(outcome: dict) -> str:
    def cell(v):
        return "" if v is None else f"{v:g}" if isinstance(v, float) else str(v)

    out = [CSV_HEADER]
    for r in outcome["rows"]:
        out.append(",".join(cell(r.get(k)) for k in ("scrip", "symbol", "basis", "period", "metric", "value", "source",
                                                      "revenue_overlaps", "revenue_max_diff", "pat_overlaps",
                                                      "pat_max_diff", "sum_checks")))
    return "\n".join(out) + "\n"


def estimate(report: dict, shards: int = 1, pause: float = PAUSE_SECONDS) -> dict:
    """Requests and time a run needs: one request per gap company on a basis, at ``pause`` seconds each per runner."""
    from . import memory_gaps

    companies = sum(1 for r in report["companies"].values() if memory_gaps.has_gap(r) and r.get("basis"))
    return {"requests": companies, "seconds": round(companies * pause / max(1, shards))}
