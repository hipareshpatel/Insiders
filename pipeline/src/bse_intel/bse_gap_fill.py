"""One-time fill of the results quarters memory lacks, for companies NSE holds no results for, from BSE's results XBRL. No AI.
TRACKER F201, TODO row 100 (owner, 27 Oct 2026).

The gap list (``memory_gaps.survey``) holds ~920 company-quarters whose company NSE lists nothing for: companies listed on
NSE in 2026 whose earlier quarters exist only on BSE (NIRLON, PERMAGN, VELJAN, GRAUWEIL, ASHIKAG). The daily pipeline stays
NSE only; this is a manual maintenance run (``memory-gaps-fill-bse``) that reads BSE's results archive through the seed's own
BSE path (``seed.seed_results`` with a BSE client and no NSE one), so the files are parsed and checked exactly as an NSE file is.

A company is filled only when all of these hold (each failure is counted under its reason):

1. it has a gap (``memory_gaps.has_gap``) and its stored market cap is at least the universe floor
   (``settings.universe_min_mcap_cr``, 500 Cr; an unknown market cap is skipped, not assumed);
2. NSE's results list, read now and not taken from any earlier file, is empty (both its lists: the integrated one and the older
   one; a list that did not load is "nse list unavailable", never "empty");
3. BSE's results archive lists files for it.

With ``BSE_FILL_PRE_NSE`` on (F214, TODO 108), rule 2 is relaxed for a company NSE does list: its gap quarters strictly older
than its first NSE results row (listed late: 531201, 544602, 532767) are candidates, and nothing else. A quarter NSE holds, or
a gap inside NSE's range, is never filled from BSE. A company whose NSE rows show no quarter is left alone. Off (the default),
any NSE row skips the company, as before.

A figure is written only for a (metric, quarter) that memory holds no value for (any source, any basis): nothing is ever
overwritten. It is written as the seed writes an exchange file's figure (source id ``xbrl:res:<scrip>:<period>``, so memory
gaps and the metrics table count it) and carries its exchange: the entry and every source in it have ``exchange: "BSE"`` and
the BSE file's address, and the label ``lab.exchange`` too. Nothing but ``financial_metrics`` is taken from the BSE run.

The seed runs on a copy of the dossier (``_Scratch``): a dry run (the default) stops there and writes nothing, not even the
R2 copy of a file; ``--apply`` writes the new figures into the stored dossier through the three-way merge.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date

from .bse import SourceBlockedError
from .dossier import _norm, keep_concurrent_writes
from .memory_gaps import has_gap, main_basis, since_for
from .periods import canonical_period, quarter_index
from .timeutil import now_iso

log = logging.getLogger(__name__)

EXCHANGE = "BSE"
TRIED_KEY = "bsefill:tried"            # kv: companies a real run already handled
REASONS = ("mcap below cut-off", "mcap unknown", "no symbol", "nse list unavailable", "nse has results",
           "bse lists nothing", "bse fetch failed", "no new quarter", "quarter held", "basis differs", "not a gap quarter")


class _Scratch:
    """A sink for the seed that reads the real one and keeps what the seed writes to itself. It is not a PlatformSink, so the
    seed neither reads nor writes the R2 copy of a file."""

    def __init__(self, sink, scrip: str, dossier: dict | None):
        self._sink, self._scrip = sink, scrip
        self.dossier = json.loads(json.dumps(dossier)) if dossier else None

    def get_dossier(self, scrip: str):
        return json.loads(json.dumps(self.dossier)) if self.dossier is not None and scrip == self._scrip else None

    def put_dossier(self, scrip: str, dossier: dict) -> None:
        self.dossier = dossier

    def kv_get(self, key: str):
        return None

    def kv_set(self, *args, **kwargs) -> None:
        return None

    def company(self, scrip: str):
        return self._sink.company(scrip)


class _RecordingBse:
    """The BSE client, remembering which files the archive listed."""

    def __init__(self, bse):
        self._bse, self.links = bse, []

    def results_xbrl(self, scrip: str):
        self.links = list(self._bse.results_xbrl(scrip))
        return self.links

    def download(self, *args, **kwargs):
        return self._bse.download(*args, **kwargs)


def chosen_urls(links) -> dict[str, str]:
    """period -> the file the seed read for it: consolidated over standalone, then the later filing (as seed_results picks)."""
    out: dict[str, str] = {}
    for link in sorted(links, key=lambda link: (link.basis == "CONSOLIDATED", link.filed_at)):
        out[link.period] = link.url
    return out


def held_keys(dossier: dict | None) -> set[tuple[str, str]]:
    """(metric, period) memory holds a value for, from any source and on any basis."""
    return {(_norm(e.get("metric", "")), e.get("period")) for e in (dossier or {}).get("financial_metrics", [])
            if isinstance(e, dict) and e.get("value") is not None}


def first_nse_index(rows) -> int | None:
    """The ``quarter_index`` of the oldest quarter any NSE results row covers, from the row's quarter end; None when no row
    shows one (then nothing can be called older than NSE's range)."""
    found = []
    for row in rows:
        end = getattr(row, "period_end", None)
        if not end:
            continue
        try:
            idx = quarter_index(canonical_period(f"quarter ended {date.fromisoformat(end):%d.%m.%Y}"))
        except ValueError:
            continue
        if idx:
            found.append(idx)
    return min(found) if found else None


def _stamp(entry: dict, url: str | None) -> dict:
    """The entry as the seed wrote it, labelled as BSE's: on the entry, on each source and on its label."""
    out = json.loads(json.dumps(entry))
    for row in [out, *out.get("sources", [])]:
        row["exchange"] = EXCHANGE
        if url:
            row["source_url"] = url
        if isinstance(row.get("lab"), dict):
            row["lab"]["exchange"] = EXCHANGE
    return out


def _from_bse_file(entry: dict, scrip: str) -> bool:
    ids = [str(s.get("news_id") or "") for s in entry.get("sources") or []] or [str(entry.get("source_news_id") or "")]
    return any(i.startswith(f"xbrl:res:{scrip}:") for i in ids)


def new_figures(before: dict | None, after: dict | None, scrip: str, wanted: set[str],
                urls: dict[str, str]) -> tuple[list[dict], dict]:
    """The entries of ``after`` (the seeded copy) to add to ``before``: a metric memory holds no value for, in a quarter that
    is a gap, from a BSE file (id ``xbrl:res:<scrip>:``). Returns (entries stamped as BSE's, skipped counts by reason)."""
    held = held_keys(before)
    basis = main_basis(before) if before else None
    skipped: dict[str, int] = {}
    out: list[dict] = []
    for entry in (after or {}).get("financial_metrics", []):
        if not isinstance(entry, dict) or entry.get("value") is None or not _from_bse_file(entry, scrip):
            continue
        period = entry.get("period")
        if (_norm(entry.get("metric", "")), period) in held:
            if period in wanted:
                skipped["quarter held"] = skipped.get("quarter held", 0) + 1
            continue
        if period not in wanted:
            skipped["not a gap quarter"] = skipped.get("not a gap quarter", 0) + 1
            continue
        got = entry.get("basis") or next((s.get("basis") for s in entry.get("sources") or [] if s.get("basis")), None)
        if basis and got not in (None, basis):
            skipped["basis differs"] = skipped.get("basis differs", 0) + 1
            continue
        out.append(_stamp(entry, urls.get(period)))
    return out, skipped


def run(sink, report: dict, symbols: dict[str, str], nse, bse, settings, apply: bool = False,
        time_budget: float = 17400.0, restart: bool = False, clock=time.monotonic,
        pre_nse: bool | None = None) -> dict:
    """The fill over the gap companies of a ``memory_gaps.survey`` report. ``nse`` needs ``financial_results(symbol)`` (and may
    carry ``integrated_failed``); ``bse`` needs ``results_xbrl`` and ``download``. A refusal (SourceBlockedError) from either
    propagates. ``more`` is true when the time budget ended the run with companies left. Only a real run (``apply``) keeps the
    list of companies handled; a dry run keeps no state. ``pre_nse`` (default: the ``BSE_FILL_PRE_NSE`` switch) lets a company
    NSE lists be filled for the quarters older than its first NSE results row."""
    from .seed import SeedStats, seed_results
    from .settings import bse_fill_pre_nse

    if pre_nse is None:
        pre_nse = bse_fill_pre_nse()

    tried = set() if restart or not apply else set(json.loads(sink.kv_get(TRIED_KEY) or "[]"))
    floor = float(settings.universe_min_mcap_cr)
    todo = [s for s, r in sorted(report["companies"].items()) if has_gap(r)]
    totals = {"companies_with_gaps": len(todo), "companies_skipped_tried": 0, "companies_class_b": 0, "companies_pre_nse": 0,
              "companies_filled": 0, "quarters_filled": 0, "figures_filled": 0, "figures_written": 0, "skipped": {}}
    skipped = totals["skipped"]

    def skip(reason: str, n: int = 1) -> None:
        skipped[reason] = skipped.get(reason, 0) + n

    def done(scrip: str) -> None:
        tried.add(scrip)
        if apply:
            sink.kv_set(TRIED_KEY, json.dumps(sorted(tried)), now_iso())

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
        company = sink.company(scrip) or {}
        symbol = symbols.get(scrip, "")
        cap = company.get("market_cap_cr")
        reason = "mcap unknown" if cap is None else "mcap below cut-off" if float(cap) < floor else "no symbol" if not symbol else None
        if reason:
            skip(reason)
            done(scrip)
            continue
        # NSE's list now: empty in both lists (class b), or the company is not ours to fill
        try:
            nse_rows = list(nse.financial_results(symbol))
        except SourceBlockedError:
            raise
        except Exception as exc:
            failed.append(f"{scrip} {symbol}: NSE list {type(exc).__name__}"[:200])
            skip("nse list unavailable")
            continue   # not handled: a later pass looks again
        if symbol.strip().upper() in getattr(nse, "integrated_failed", ()):
            failed.append(f"{scrip} {symbol}: NSE integrated list did not load")
            skip("nse list unavailable")
            continue
        wanted = set(result["missing"])
        if result.get("missing_year_ago") and result.get("year_ago"):
            wanted.add(result["year_ago"])
        if nse_rows:
            first = first_nse_index(nse_rows) if pre_nse else None
            wanted = {q for q in wanted if first is not None and (quarter_index(q) or 0) < first}
            if not wanted:
                skip("nse has results")
                done(scrip)
                continue
            totals["companies_pre_nse"] += 1
        else:
            totals["companies_class_b"] += 1
        # TODO(batch counter): the shared batch-of-100 download counter hooks in here, before BSE is called for the company
        before = sink.get_dossier(scrip)
        scratch = _Scratch(sink, scrip, before)
        recorder = _RecordingBse(bse)
        stats = SeedStats()
        try:
            seed_results(scratch, recorder, scrip, company.get("company_name") or scrip, since_for(result),
                         settings.text_cache_dir, stats, company, nse=None, symbol="")
        except SourceBlockedError:
            raise
        except Exception as exc:
            failed.append(f"{scrip} {symbol}: {type(exc).__name__}: {exc}"[:200])
            skip("bse fetch failed")
            continue
        if stats.failures:
            failed.append(f"{scrip} {symbol}: " + "; ".join(stats.failures)[:160])
        if not recorder.links:
            skip("bse lists nothing")
            done(scrip)
            continue
        fresh, why = new_figures(before, scratch.dossier, scrip, wanted, chosen_urls(recorder.links))
        for reason, n in why.items():
            skip(reason, n)
        if not fresh:
            skip("bse fetch failed" if stats.failures else "no new quarter")
            if not stats.failures:
                done(scrip)
            continue
        periods = {e["period"] for e in fresh}
        totals["companies_filled"] += 1
        totals["quarters_filled"] += len(periods)
        totals["figures_filled"] += len(fresh)
        for entry in sorted(fresh, key=lambda e: (quarter_index(e["period"]) or 0, e["metric"])):
            rows.append({"scrip": scrip, "symbol": symbol, "period": entry["period"], "metric": entry["metric"],
                         "value": entry["value"], "basis": entry.get("basis"), "source": EXCHANGE,
                         "url": entry.get("source_url")})
        if apply:
            totals["figures_written"] += _write(sink, scrip, fresh, scratch.dossier)
        if not stats.failures:
            done(scrip)
    return {"apply": apply, "more": more, "failed": failed, "rows": rows, "min_mcap_cr": floor, **totals}


def _write(sink, scrip: str, fresh: list[dict], seeded: dict | None = None) -> int:
    """The entries into the stored dossier through the three-way merge; never over a value that is there. A company with no
    stored dossier starts from the seeded copy emptied of every figure and statement (the new entries are added below)."""
    read = sink.get_dossier(scrip)
    if read is None:
        if seeded is None:
            return 0
        base = json.loads(json.dumps(seeded))
        base["financial_metrics"], base["balance_sheet"] = [], []
        base.pop("standalone", None)
        merged = base
    else:
        merged = json.loads(json.dumps(read))
    held = held_keys(merged)
    added = 0
    for entry in fresh:
        key = (_norm(entry["metric"]), entry["period"])
        if key in held:
            continue
        held.add(key)
        merged.setdefault("financial_metrics", []).append(json.loads(json.dumps(entry)))
        added += 1
    if added:
        keep_concurrent_writes(merged, read, sink.get_dossier(scrip))
        sink.put_dossier(scrip, merged)
    return added


def render(outcome: dict) -> str:
    s = outcome["skipped"]
    lines = [f"BSE fill of memory gaps ({'applied' if outcome['apply'] else 'dry run, nothing written'}), market cap at least "
             f"{outcome['min_mcap_cr']:g} Cr:",
             f"companies with a gap           {outcome['companies_with_gaps']} ({outcome['companies_skipped_tried']} handled before)",
             f"NSE lists nothing (class b)    {outcome['companies_class_b']}",
             f"NSE lists only later quarters  {outcome['companies_pre_nse']}",
             f"companies filled               {outcome['companies_filled']}",
             f"quarters filled                {outcome['quarters_filled']}",
             f"figures filled                 {outcome['figures_filled']} (written {outcome['figures_written']})",
             f"more left (time budget)        {outcome['more']}",
             "skipped, by reason:"]
    lines += [f"  {reason}: {s[reason]}" for reason in REASONS if s.get(reason)] or ["  none"]
    return "\n".join(lines)


def to_csv(outcome: dict) -> str:
    out = ["scrip,symbol,period,metric,value,basis,source,url"]
    for r in outcome["rows"]:
        out.append(f"{r['scrip']},{r['symbol']},{r['period']},{r['metric']},{r['value']},{r.get('basis') or ''},"
                   f"{r['source']},{r.get('url') or ''}")
    return "\n".join(out) + "\n"
