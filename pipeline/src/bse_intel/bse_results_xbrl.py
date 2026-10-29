"""Results XBRL from BSE for the quarters NSE does not list (owner, 29 Oct 2026: "build the BSE results-file download, with its
100-file test ... Ensure all test files must gets saved"). No AI, no NSE, no memory write.

The NSE download (``xbrl-facts --from-nse``) is complete, yet each of the last 13 quarters lacks a results file for about 120-310
companies (screener-rows run 40820489722). Two causes, measured 29 Oct 2026: that download kept 12 quarters, not screener's 13, so
the oldest was missing for nearly every company though NSE lists it (now 13, xbrl_facts.FACTS_QUARTERS); and companies listed on
NSE late, whose earlier quarters NSE never had (Kusumgar, Rhetan, Ardee and Sudeep Pharma list no June 2025 row on either NSE
results list). NSE is the faster source (16 shards), so it runs first and this fill takes only what NSE lacks. BSE's results
archive has those: the 27 Oct fill (``memory-gaps-fill-bse``, F201) read it for memory, but kept no facts docs for the screener
comparison.

For each company, largest first, with a quarter of the window (the last ``QUARTERS`` ended) that has no facts doc on either basis:
BSE's archive is listed through the fill's own client (``bse_gap_fill.PortedBse``: the ported adapter, its headers and pace, a
401/403/429 stops the run); each file of such a quarter is downloaded once and kept in our XBRL store (xbrl_store.py, as every
results file is, a test run's too; a stored file is read from there, never downloaded again), and its facts are saved as the
results doc ``raw/xbrl-facts/<scrip>/<period>-<basis>.json.gz`` with ``exchange: "BSE"`` unless one is stored. A company's
archive answer is kept (``raw/bse-results-xbrl/<scrip>/list.json``) for a week. Files count toward the run's file cap.
"""

from __future__ import annotations

import json
import time
from datetime import date

from . import xbrl_facts as xf
from .memory_gaps import quarter_end
from .periods import quarter_from_index, quarter_index

PREFIX = "raw/bse-results-xbrl/"
QUARTERS = 13                 # screener's quarterly table: Q2FY24 to Q2FY27 on 29 Oct 2026
LIST_FRESH_DAYS = 7
DUE_DAYS, MARCH_DUE_DAYS = 45, 60     # SEBI LODR Reg 33: a quarter's results within 45 days of its end, the year's (March) within 60
BASES = ("CONSOLIDATED", "STANDALONE")


class _Stop(Exception):
    pass


def list_key(scrip: str) -> str:
    return f"{PREFIX}{scrip}/list.json"


def window(today: date) -> list[str]:
    """The last QUARTERS quarters ended by ``today``, newest first."""
    fy = today.year % 100 + (1 if today.month >= 4 else 0)
    q = {4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2, 10: 3, 11: 3, 12: 3, 1: 4, 2: 4, 3: 4}[today.month]
    index = quarter_index(f"Q{q}FY{fy:02d}")
    out = []
    while len(out) < QUARTERS:
        period = quarter_from_index(index)
        end = quarter_end(period)
        if end is not None and end <= today:
            out.append(period)
        index -= 1
    return out


def due(period: str, today: date) -> bool:
    """Whether the quarter's results are past their filing deadline. Before it a company that has not filed is not missing a
    quarter, and asking BSE for its list would bring nothing (owner, 29 Oct 2026: the newest quarter's lists were asked in vain);
    the daily NSE run picks the filing up when it comes."""
    end = quarter_end(period)
    return end is not None and (today - end).days > (MARCH_DUE_DAYS if end.month == 3 else DUE_DAYS)


def missing(scrip: str, stored: set[str], periods: list[str], today: date | None = None) -> set[str]:
    """The window's quarters past their deadline with no facts doc on either basis."""
    return {p for p in periods if (today is None or due(p, today)) and not any(xf.key(scrip, p, b) in stored for b in BASES)}


def _links(bse, sink, scrip: str, stored: set[str], today: date, totals: dict) -> list[dict]:
    key = list_key(scrip)
    if key in stored and (blob := sink.get_object(key)):
        kept = json.loads(blob)
        if (today - date.fromisoformat(kept.get("asked", "2000-01-01"))).days < LIST_FRESH_DAYS:
            totals["lists_reused"] += 1
            return kept.get("links") or []
    links = [{"period": x.period, "basis": x.basis, "url": x.url, "filed_at": x.filed_at} for x in bse.results_xbrl(scrip)]
    totals["lists_asked"] += 1
    sink.put_object(key, json.dumps({"asked": today.isoformat(), "links": links}).encode("utf-8"), content_type="application/json")
    return links


def run(sink, companies: list[tuple[str, str]], bse, time_budget: float = 17400.0, today: date | None = None,
        clock=time.monotonic) -> dict:
    """For each (scrip, symbol): the window's quarters with no facts doc, from BSE's archive. Stops on the file cap (``more``)
    or the time budget; a refusal propagates (what is stored stays). ``bse.keep`` must be the sink, so files go to the store."""
    from .nse import FileCapReached
    from .bse import AttachmentError

    today = today or date.today()
    periods = window(today)
    bse.keep = sink
    totals = {"companies": 0, "not_on_bse": 0, "complete": 0, "lists_asked": 0, "lists_reused": 0, "quarters_missing": 0,
              "quarters_on_bse": 0, "files_wanted": 0, "files_failed": 0, "files_not_results": 0, "period_mismatch": 0,
              "facts_saved": 0, "store_full": False, "more": False, "window": f"{periods[-1]}-{periods[0]}"}
    saved: list[dict] = []
    deadline = clock() + time_budget
    for scrip, symbol in companies:
        if not str(scrip).isdigit():
            totals["not_on_bse"] += 1
            continue
        if clock() >= deadline:
            totals["more"] = True
            break
        totals["companies"] += 1
        stored = set(sink.list_objects(f"{xf.PREFIX}{scrip}/")) | set(sink.list_objects(f"{PREFIX}{scrip}/"))
        gap = missing(scrip, stored, periods, today)
        if not gap:
            totals["complete"] += 1
            continue
        totals["quarters_missing"] += len(gap)
        links = [x for x in _links(bse, sink, scrip, stored, today, totals) if x["period"] in gap]
        totals["quarters_on_bse"] += len({x["period"] for x in links})
        chosen: dict[tuple[str, str], dict] = {}
        for x in sorted(links, key=lambda x: x["filed_at"]):      # a revised filing (later) replaces the original
            chosen[(x["period"], x["basis"])] = x
        try:
            for (period, basis), x in sorted(chosen.items()):
                if xf.key(scrip, period, basis) in stored:
                    continue
                totals["files_wanted"] += 1
                try:
                    body = bse.download(x["url"])
                except AttachmentError:
                    totals["files_failed"] += 1
                    continue
                if not body:
                    totals["files_failed"] += 1
                    continue
                files = getattr(bse, "files", None)
                if files and files.get("downloaded", 0) > files.get("kept", 0):
                    totals["store_full"] = True      # a file came down that the XBRL store did not keep: stop, never refetch
                    totals["more"] = True
                    raise _Stop
                doc = xf.parse_facts(body, scrip=scrip, url=x["url"])
                if doc is None:
                    totals["files_not_results"] += 1
                    continue
                if doc.get("period") != period or (doc.get("basis") or basis) != basis:
                    totals["period_mismatch"] += 1       # the archive's row and the file disagree: kept out, never guessed
                    continue
                xf.save(sink, scrip, period, basis, dict(doc, exchange="BSE"))
                stored.add(xf.key(scrip, period, basis))
                totals["facts_saved"] += 1
                saved.append({"scrip": scrip, "symbol": symbol, "period": period, "basis": basis})
        except FileCapReached:
            totals["more"] = True
            break
        except _Stop:
            break
    return {**totals, "files": dict(getattr(bse, "files", {})), "saved": saved}


def render(out: dict) -> str:
    keys = ("window", "companies", "not_on_bse", "complete", "lists_asked", "lists_reused", "quarters_missing", "quarters_on_bse",
            "files_wanted", "files_failed", "files_not_results", "period_mismatch", "facts_saved", "files", "store_full", "more")
    return "BSE results XBRL (the quarters NSE does not list):\n" + "\n".join(f"{k:18s} {out[k]}" for k in keys)
