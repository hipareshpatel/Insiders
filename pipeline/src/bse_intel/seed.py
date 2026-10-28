"""Deterministic memory seed: a company's financial and ownership history from XBRL, with no AI call.

Before this, memory started empty at the first analysed filing, so the earliest cards had no year-ago
or previous quarter to compare with, and ownership came from whatever a model read in press releases
(tracker F14, F48, F50). The figures are machine-tagged by the company's own filing agent, so they are
exact, and nothing here can invent a number:

* results, per quarter: BSE's results archive (`Result_Arch_ng`) lists every quarter's XBRL file,
  back years, for BSE-listed companies, consolidated preferred over standalone;
* shareholding, per quarter: NSE's shareholding master lists each quarter's XBRL for the 2,480 of our
  companies that are also on NSE (96% of those above ₹1,000 Cr).

Each file becomes one synthetic filing id ("xbrl:res:<scrip>:<period>"), so every stored figure keeps
its source and a re-run replaces its own earlier entry instead of duplicating it.
"""

from __future__ import annotations

import gzip
import hashlib
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import xbrl as xbrl_fast_path
from . import xbrl_store
from .dossier import forget_source, merge, new_dossier, put_standalone
from .models import FinancialMetric, Filing, Pass2Output
from .nse import SourceBlockedError
from .periods import canonical_period, quarter_index
from .settings import memory_standalone_only
from .timeutil import now_iso

log = logging.getLogger(__name__)


@dataclass
class SeedStats:
    companies: int = 0
    results_files: int = 0
    results_periods: int = 0
    shareholding_files: int = 0
    shareholding_periods: int = 0
    skipped: int = 0
    results_from_nse: int = 0   # quarters BSE would not serve and NSE did
    rescaled: int = 0           # files tagged in the wrong unit, put right against the company's other quarters
    misdated: int = 0           # files whose figures are dated to other months than the quarter NSE lists them for, refused
    derived: int = 0            # quarters worked out as a longer period less the earlier quarters (the file holds no quarter of its own)
    standalone_periods: int = 0  # a consolidated filer's standalone quarters, kept apart (dossier.put_standalone)
    failures: list[str] = field(default_factory=list)
    slip_held: list[str] = field(default_factory=list)   # quarters held out: a unit slip the filing's PDF text layer did not confirm (F200)

    def line(self) -> str:
        return (f"{self.companies} companies: {self.results_periods} results quarters from {self.results_files} XBRL files, "
                f"{self.shareholding_periods} shareholding quarters from {self.shareholding_files} files, "
                f"{self.skipped} skipped, {len(self.failures)} failures"
                + (f", {self.results_from_nse} quarters from NSE where BSE served nothing" if self.results_from_nse else "")
                + (f", {self.rescaled} files in the wrong unit put right" if self.rescaled else "")
                + (f", {len(self.slip_held)} quarters held for an unconfirmed unit slip" if self.slip_held else "")
                + (f", {self.misdated} files dated to the wrong months refused" if self.misdated else "")
                + (f", {self.derived} quarters worked out from a longer period" if self.derived else ""))


def _cache(root: Path | None, url: str) -> Path | None:
    if not root:
        return None
    return root / "xbrl" / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".xml.gz")


def _fetch(client, url: str, root: Path | None, sink=None, max_bytes: int = 8_000_000) -> bytes | None:
    """One XBRL file, kept by checksum so a parser fix is a re-parse and not another download: the local cache first,
    then our copy in R2 (xbrl_store, F191), then the exchange (and R2 gets the file). ``max_bytes`` is the client's size limit
    for the download (8 MB, the seed's own; xbrl-facts passes the annual-report limit for a results file over it)."""
    path = _cache(root, url)
    if path and path.exists():
        try:
            return gzip.decompress(path.read_bytes())
        except OSError:
            pass
    data = xbrl_store.get(sink, url)
    fresh = not data
    if fresh:
        try:
            data = client.download(url, max_bytes=max_bytes)
        except Exception as exc:   # one dead file is that quarter's gap, not the company's: only 404/410 (a refusal still raises)
            if getattr(getattr(exc, "response", None), "status_code", None) not in (404, 410):
                raise
            log.warning("XBRL file gone (HTTP %s): %s", exc.response.status_code, url)
            return None
    if data and path:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(data))
        except OSError:
            pass
    if data and fresh:
        xbrl_store.put(sink, url, data)
    return data


def _filing(kind: str, scrip: str, name: str, period: str, filed_at: str, url: str) -> Filing:
    """A synthetic filing for one XBRL file: memory keys every figure to a source id."""
    return Filing(
        news_id=f"xbrl:{kind}:{scrip}:{period}",
        scrip_code=scrip,
        company_name=name or scrip,
        headline=f"{period} {'results' if kind == 'res' else 'shareholding pattern'} (XBRL, {url.rsplit('/', 1)[-1]})",
        subject="",
        filed_at=filed_at,
        filing_date=filed_at[:10],
    )


def seed_results(sink, bse, scrip: str, name: str, since: str, cache_root: Path | None,
                 stats: SeedStats, company: dict | None = None, nse=None, symbol: str = "") -> None:
    """Every quarter's results XBRL in the company's BSE archive, into memory. Consolidated wins where
    a quarter has both: memory keeps one basis, and the cards quote the consolidated figures.

    With `nse` and `symbol`, NSE is a fallback for the quarters BSE will not serve. BSE's own archive
    lists the NBFC and life-insurance templates under paths that return its homepage to a plain fetch and
    nothing to ours, so Bajaj Finance and Max Financial had no machine-tagged figures at all while the
    archive said the files existed. The same quarters from NSE parse with the tag map already here: 0
    bytes against 23 metrics, measured 2026-10-16 (PLAN item 1i).
    """
    # NSE is the source (owner, 2026-10-19: everything on NSE); BSE's archive is read only when a BSE client is
    # given (`seed-memory --source bse`, on an Indian address), for a company NSE does not list
    links = [link for link in bse.results_xbrl(scrip) if link.filed_at[:10] >= since] if bse is not None else []
    # Every quarter is read before any is written, so a file tagged in the wrong unit can be told by the
    # company's other quarters and put right before it reaches memory (xbrl.fix_scale).
    found: dict[str, tuple[str, str, object, bool]] = {}     # period -> (filed on, url, parsed, from NSE only)
    by_period: dict[str, object] = {}
    # Consolidated wins over standalone whenever a quarter has both, and only then the later filing: Max Financial's
    # standalone files of 13 Jul 2026 (the holding company's ₹17 Cr quarter) had replaced the consolidated quarter of
    # May because they came later, and its cards measured a ₹533 Cr payment as 3135% of revenue (round 5, 2026-10-19)
    for link in sorted(links, key=lambda link: (link.basis == "CONSOLIDATED", link.filed_at)):
        by_period[link.period] = link  # consolidated, then the later filing, wins
    for period, link in sorted(by_period.items()):
        data = _fetch(bse, link.url, cache_root, sink)
        if not data and nse is not None and symbol:
            data = _from_nse(nse, symbol, period, link, cache_root, stats, scrip, sink)
        if not data:
            # Loudly: BSE's own archive listed this file, so nothing coming back means the company is
            # about to be written from PDFs alone with no machine-tagged figure to check against. Two of
            # eight companies surveyed on 2026-10-16 failed this way (Bajaj Finance, Max Financial, both on
            # the NBFCUploadDocument path) and only a counter moved.
            stats.skipped += 1
            stats.failures.append(f"{scrip} {period}: nothing fetched from {link.url}")
            log.warning("seed %s %s: the archive lists %s but nothing came back; this company has no "
                        "machine-tagged results for that quarter", scrip, period, link.url)
            continue
        parsed = _parse_results(data, stats)
        if parsed:
            found[period] = (link.filed_at[:10], link.url, parsed, False)

    # Quarters NSE has that BSE's archive never listed at all. The fallback above only fires for a file
    # BSE named, and since March 2025 the integrated format means BSE often names none: a company that
    # changed over has a gap in memory rather than a failed fetch, which no counter would have shown.
    if nse is not None and symbol:
        for period, row in _nse_quarters(nse, symbol, since, scrip, stats).items():
            if period in found:
                continue
            data = _fetch(nse, row.xbrl_url, cache_root, sink)
            if not data:
                continue
            stats.results_from_nse += 1
            parsed = _parse_results(data, stats)
            if parsed:
                found[period] = (row.filed_at[:10], row.xbrl_url, parsed, True)
                if bse is not None:
                    log.info("seed %s %s: BSE's archive did not list this quarter, NSE did (%s)",
                             scrip, period, row.taxonomy or "template not stated")

    # A company that files consolidated results keeps that basis: a quarter NSE lists only standalone (Heritage's
    # re-filed Q4FY25 and Q2FY26, T5 2026-10-20) is left to the cards rather than set beside consolidated quarters.
    # MEMORY_STANDALONE_ONLY (F162): such a quarter is the company's own figure when no consolidated file exists for it
    # (``found`` already prefers a consolidated file to a standalone one for the same quarter), so it stays, on basis
    # STANDALONE, and is listed in the dossier's ``standalone_only`` for memory_gaps.
    keep_standalone = memory_standalone_only()
    if any(result.basis == "CONSOLIDATED" for _, _, result, _ in found.values()) and not keep_standalone:
        dropped = [p for p, (_, _, result, _) in found.items() if result.basis == "STANDALONE"]
        for period in dropped:
            log.info("seed %s %s: standalone file only, the company files consolidated; left to the cards", scrip, period)
            stats.skipped += 1
            found.pop(period)
        # and out of memory, where an earlier seed put it
        dossier = sink.get_dossier(scrip) if dropped else None
        if dossier is not None and any([forget_source(dossier, f"xbrl:res:{scrip}:{period}") for period in dropped]):
            sink.put_dossier(scrip, dossier)
    from .slip_check import PdfCheck
    check = PdfCheck(nse, symbol)   # the PDF text-layer check of a unit slip: nothing is fetched unless one is found (F200)
    held_slips: dict[str, str] = {}
    unsure: set[str] = set()   # held because no PDF could settle the slip: what memory holds from the file stays
    for period, (filed_on, url, parsed, _) in list(found.items()):
        others = [m for other, (_, _, result, _) in found.items() if other != period for m in result.metrics]
        if xbrl_fast_path.fix_scale(parsed, others, scrip, verify=check):
            stats.rescaled += 1
        elif getattr(parsed, "slip_held", ""):
            held_slips[period] = parsed.slip_held
            if getattr(parsed, "slip_unsure", False):
                unsure.add(period)
            continue
        xbrl_fast_path.drop_long_year(parsed, others, scrip)   # an 18-month "year" dated as twelve (Siemens)
    _hold_slips(sink, scrip, found, held_slips, stats, unsure)
    _drop_misdated(sink, scrip, found, stats)
    _derive_quarters(found, stats)
    for period, (filed_on, url, parsed, from_nse) in sorted(found.items()):
        _write_results(sink, scrip, name, company, period, filed_on, url, parsed, stats, from_nse)
    _flag_slips(sink, scrip, held_slips)
    if keep_standalone and found:
        _mark_standalone_only(sink, scrip, found)
    # a consolidated filer's standalone files too, kept apart for the company page's standalone view (owner,
    # 2026-10-21); the quarters the consolidated ones cover, no more
    consolidated = [p for p, (_, _, result, _) in found.items() if result.basis == "CONSOLIDATED"]
    if nse is not None and symbol and consolidated:
        _seed_standalone(sink, nse, scrip, symbol, since, set(consolidated), cache_root, stats)


def _hold_slips(sink, scrip: str, found: dict, held: dict[str, str], stats: SeedStats,
                unsure: set[str] = frozenset()) -> None:
    """A quarter whose file looks tagged in the wrong unit and whose PDF does not print the corrected figure (or cannot be
    read) is kept out of memory, and what an earlier seed stored from it leaves too (owner, 27 Oct 2026, F200: a missing
    quarter is better than a wrong one). Listed in the dossier's ``scale_held`` and the stats, for memory_gaps and the
    referees; a quarter that later seeds cleanly leaves the list (_write_results)."""
    if not held:
        return
    dossier = sink.get_dossier(scrip)
    changed = False
    for period, why in held.items():
        found.pop(period, None)
        stats.skipped += 1
        stats.slip_held.append(f"{scrip} {period}: {why}")
        if period in unsure:
            continue
        changed = bool(dossier is not None and forget_source(dossier, f"xbrl:res:{scrip}:{period}")) or changed
    if changed:
        sink.put_dossier(scrip, dossier)


def _flag_slips(sink, scrip: str, held: dict[str, str]) -> None:
    """The held quarters in the dossier's ``scale_held`` (after the quarters that did seed are written)."""
    if not held:
        return
    dossier = sink.get_dossier(scrip)
    if dossier is None:
        return
    listed = sorted(set(dossier.get("scale_held") or []) | set(held), key=lambda p: quarter_index(p) or 0)
    if listed != list(dossier.get("scale_held") or []):
        dossier["scale_held"] = listed
        sink.put_dossier(scrip, dossier)


_PERIOD_END_QUARTER = {"Q1": 1, "Q2": 2, "H1": 2, "Q3": 3, "9M": 3, "Q4": 4, "H2": 4, "FY": 4}


def _ends_with_quarter(label: str, quarter: str) -> bool:
    """Whether a figure's period (Q4FY25, H2FY25, FY25, 9MFY25...) ends in the same month as ``quarter`` (Q4FY25)."""
    m = re.fullmatch(r"(Q[1-4]|H[12]|9M|FY)(?:FY)?(\d{2})", label or "")
    return bool(m) and _PERIOD_END_QUARTER[m[1]] == int(quarter[1]) and m[2] == quarter[-2:]


def _drop_misdated(sink, scrip: str, found: dict, stats: SeedStats) -> None:
    """A file NSE lists for a quarter whose figures are dated to other months is not that quarter's: CG Power's Q4FY25
    file (filed 8 May 2025) tags its March-quarter figures (revenue 2,752.77) as 1 Apr - 30 Sep 2024, and memory then
    held them as H1FY25 over the real half year (4,640.21), with no Q4FY25 (gaps fill, 25 Oct 2026). Nothing in the
    file says which months are right, so it is refused, and what an earlier seed stored from it leaves memory."""
    refused = [period for period, (_, _, parsed, _) in found.items()
               if quarter_index(period) and not any(_ends_with_quarter(m.period, period) for m in parsed.metrics)]
    if not refused:
        return
    dossier = sink.get_dossier(scrip)
    changed = False
    for period in refused:
        found.pop(period)
        stats.skipped += 1
        stats.misdated += 1
        log.warning("seed %s %s: the file's figures are dated to other months than this quarter; not kept", scrip, period)
        changed = bool(dossier is not None and forget_source(dossier, f"xbrl:res:{scrip}:{period}")) or changed
    if changed:
        sink.put_dossier(scrip, dossier)


_QUARTER_SUMS = ("revenue", "total_income", "pat", "pbt", "tax_expense")   # lines that add across periods


def _derive_quarters(found: dict, stats: SeedStats) -> None:
    """A quarter whose file holds the longer period and no quarter of its own: the integrated filing of March 2025 holds
    H2FY25 and FY25 only (ZEEL, Solex, PGHL, Sanathan, HEMIPROP: most of the "Q4FY25 only" gaps), NDTV's Q2FY26 file
    only H1FY26 (gaps fill, 25 Oct 2026). The quarter is the longer period less the earlier part, taken from the previous
    quarter's file on the same basis: Q4 = FY less 9M or H2 less Q3 (December file), Q3 = 9M less H1 (September file),
    Q2 = H1 less Q1 (June file). A line with no such pair is left out. Marked `calc` with the lines it came from, so
    nothing reads it as the file's own figure."""
    recipes = {"2": ((("H1", "Q1"),), "1"), "3": ((("9M", "H1"),), "2"), "4": ((("FY", "9M"), ("H2", "Q3")), "3")}
    for period, (_, _, parsed, _) in sorted(found.items()):
        if not quarter_index(period) or period[1] == "1" or any(m.period == period for m in parsed.metrics):
            continue
        pairs, previous = recipes[period[1]]
        year, earlier = period[-2:], found.get(f"Q{previous}FY{period[-2:]}")
        if earlier is None or earlier[2].basis != parsed.basis:
            continue
        own = {(m.metric, m.period): m for m in parsed.metrics}
        before = {(m.metric, m.period): m for m in earlier[2].metrics}
        for metric in _QUARTER_SUMS:
            for whole, part in pairs:
                whole, part = (f"FY{year}" if whole == "FY" else f"{whole}FY{year}"), f"{part}FY{year}"
                a, b = own.get((metric, whole)), before.get((metric, part))
                if a is None or b is None or a.value is None or b.value is None:
                    continue
                value = round(a.value - b.value, 2)
                if metric in ("revenue", "total_income") and value < 0:
                    continue
                parsed.metrics.append(FinancialMetric(
                    metric=metric, period=period, value=value, unit=a.unit, by="calc",
                    derived_from=[f"{metric}:{whole}", f"{metric}:{part}"], file_basis=parsed.basis))
                break
        if any(m.period == period for m in parsed.metrics):
            stats.derived += 1


def _mark_standalone_only(sink, scrip: str, found: dict) -> None:
    """Record the quarters kept on the standalone basis because NSE lists no consolidated file for them (dossier
    ``standalone_only``, a sorted list of periods). A quarter now read as consolidated leaves the list."""
    dossier = sink.get_dossier(scrip)
    if dossier is None:
        return
    only = {p for p, (_, _, result, _) in found.items() if quarter_index(p) and result.basis == "STANDALONE"}
    done = {p for p, (_, _, result, _) in found.items() if result.basis == "CONSOLIDATED"}
    marked = (set(dossier.get("standalone_only") or []) - done) | only
    if sorted(marked) != list(dossier.get("standalone_only") or []):
        dossier["standalone_only"] = sorted(marked, key=quarter_index)
        sink.put_dossier(scrip, dossier)


def _seed_standalone(sink, nse, scrip: str, symbol: str, since: str, periods: set[str], cache_root, stats) -> None:
    try:
        rows = _rows_or_partial(nse, symbol, None, scrip)   # a failed integrated list is recorded by _nse_quarters
    except SourceBlockedError:
        raise
    except Exception:
        return
    best: dict = {}
    for row in sorted((r for r in rows if not r.consolidated), key=lambda r: r.filed_at):
        if not row.period_end or row.period_end < since:
            continue
        label = canonical_period(f"quarter ended {row.period_end[8:10]}.{row.period_end[5:7]}.{row.period_end[:4]}")
        if label in periods:
            best[label] = row
    if not best:
        return
    dossier = sink.get_dossier(scrip)
    if dossier is None:
        return
    for period, row in sorted(best.items()):
        data = _fetch(nse, row.xbrl_url, cache_root, sink)
        parsed = _parse_results(data, stats) if data else None
        if parsed is None or parsed.basis == "CONSOLIDATED":
            continue
        put_standalone(dossier, parsed.memory_metrics(), parsed.balance_sheet, f"{row.filed_at[:10]}T18:00:00+05:30",
                       f"xbrl:res-sa:{scrip}:{period}")
        stats.standalone_periods += 1
    sink.put_dossier(scrip, dossier)


def _parse_results(data: bytes, stats: SeedStats):
    """One results XBRL file parsed; None, counted as skipped, when it holds nothing we can use."""
    stats.results_files += 1
    parsed = xbrl_fast_path.parse(data)
    if not parsed or parsed.kind != "RESULTS" or not parsed.metrics:
        stats.skipped += 1
        return None
    return parsed


def stamp_file(dossier: dict, news_id: str, url: str) -> int:
    """Put the NSE file's full url (as fetched) on the label of every figure this synthetic filing stated (F222): memory kept only the
    source id ``xbrl:res:<scrip>:<period>``, so the file could not be found again without NSE's results list. Returns how
    many labels were stamped."""
    stamped = 0
    for entry in dossier.get("financial_metrics", []):
        rows = entry.get("sources") or ([{"news_id": entry.get("source_news_id"), "lab": entry.get("lab")}] if entry.get("lab") else [])
        for row in rows:
            if row.get("news_id") == news_id and isinstance(row.get("lab"), dict):
                row["lab"]["file_url"] = url
                stamped += 1
    return stamped


def _write_results(sink, scrip: str, name: str, company: dict | None, period: str, filed_on: str,
                   url: str, parsed, stats: SeedStats, from_nse: bool = False) -> None:
    """One parsed results file into memory."""
    filing = _filing("res", scrip, name, period, f"{filed_on}T18:00:00+05:30", url)
    out = Pass2Output(is_material=False, timeline_entry="")
    out.dossier_delta.financial_metrics = parsed.memory_metrics() if hasattr(parsed, "memory_metrics") else list(parsed.metrics)
    if parsed.balance_sheet and not parsed.balance_sheet.is_empty():
        out.dossier_delta.balance_sheet = parsed.balance_sheet
    dossier = sink.get_dossier(scrip) or new_dossier(filing, company or {})
    if period in (dossier.get("scale_held") or []):    # held for an unconfirmed unit slip before, seeds cleanly now (F200)
        left = [p for p in dossier["scale_held"] if p != period]
        dossier["scale_held"] = left
        if not left:
            dossier.pop("scale_held")
    merged = merge(dossier, out, filing, None, now_iso(), basis=parsed.basis,
                   fy_end_month=getattr(parsed, "fy_end_month", None), own_period=period)
    if from_nse:   # only an NSE archive url is stamped: a BSE file's url is no archive-only source (F222)
        stamp_file(merged, filing.news_id, url)
    sink.put_dossier(scrip, merged)
    stats.results_periods += 1
    log.info("seed %s %s: %d figures from %s (%s)", scrip, period, len(parsed.metrics), url.rsplit("/", 1)[-1],
             parsed.basis or "basis not stated")


def _nse_quarters(nse, symbol: str, since: str, scrip: str, stats: "SeedStats | None" = None) -> dict:
    """The newest filing NSE lists per quarter, consolidated where both bases are filed."""
    try:
        rows = _rows_or_partial(nse, symbol, stats, scrip)
    except SourceBlockedError:
        raise  # NSE limits by IP: the caller stops the seed rather than marking the company done with nothing
    except Exception as exc:
        log.info("seed %s: NSE list unavailable (%s)", scrip, type(exc).__name__)
        if stats is not None:   # not silent: the memory-gaps fill must not count this company as done (F195)
            stats.failures.append(f"{scrip}: NSE results list unavailable ({type(exc).__name__})")
        return {}
    best: dict = {}
    # consolidated over standalone, the integrated filing over the older list's row, then the later filing
    for row in sorted(rows, key=lambda r: (r.consolidated, not getattr(r, "legacy", False), r.filed_at)):
        if not row.period_end or row.period_end < since:
            continue
        label = canonical_period(f"quarter ended {row.period_end[8:10]}.{row.period_end[5:7]}.{row.period_end[:4]}")
        if label:
            best[label] = row  # consolidated, then the later filing, wins
    return _recent_and_years(best)


SEED_QUARTERS = 12   # memory keeps 12 quarters (dossier.KEEP_PERIODS); older files are read for their year only


def _recent_and_years(best: dict) -> dict:
    """The latest SEED_QUARTERS quarters' files, and before them only the March quarter's: its file carries the
    year, the March balance sheet and the year's cash flow, all the annual view needs (owner, 2026-10-21: years as
    on screener.in). A file for any other old quarter would only be cut from memory again."""
    ends = sorted({row.period_end for row in best.values()}, reverse=True)
    recent = set(ends[:SEED_QUARTERS])
    return {label: row for label, row in best.items() if row.period_end in recent or row.period_end[5:7] == "03"}


class PartialNseList(RuntimeError):
    """NSE's integrated list failed and only the older list came back (it holds no quarter since December 2024). The
    older rows are still good: callers use ``rows`` and record the failure, so the company is not counted done."""

    def __init__(self, symbol: str, rows: tuple):
        super().__init__(f"NSE's integrated results list for {symbol} was unavailable; only the older list came back")
        self.rows = rows


def _rows_or_partial(nse, symbol: str, stats: "SeedStats | None", scrip: str) -> tuple:
    """``_nse_rows``, keeping the older list's rows when the integrated list failed (recorded as a failure)."""
    try:
        return _nse_rows(nse, symbol)
    except PartialNseList as exc:
        if stats is not None:   # not silent: the memory-gaps fill must not count this company as done (F195)
            stats.failures.append(f"{scrip}: NSE integrated results list unavailable (older list only)")
        return exc.rows


@lru_cache(maxsize=64)
def _nse_rows(nse, symbol: str) -> tuple:
    """NSE's results list for one symbol, fetched once: it is read per quarter and the client paces
    itself by several seconds a call."""
    rows = tuple(nse.financial_results(symbol))
    if symbol.strip().upper() in getattr(nse, "integrated_failed", ()):
        # financial_results fell back to the older list, which holds no quarter since December 2024: the newest
        # quarters would be silently absent and the company marked done (d4 gaps, 26 Oct 2026). Not cached: raise.
        raise PartialNseList(symbol, rows)
    return rows


def _from_nse(nse, symbol: str, period: str, link, cache_root: Path | None, stats: SeedStats,
              scrip: str, sink=None) -> bytes | None:
    """The same quarter from NSE, when BSE served nothing. Matched on the filing date BSE listed, so the
    row is the same filing and not merely the same company; the basis is matched where NSE states it."""
    try:
        rows = _rows_or_partial(nse, symbol, stats, scrip)
    except SourceBlockedError:
        raise
    except Exception as exc:
        log.info("seed %s %s: NSE fallback unavailable (%s)", scrip, period, type(exc).__name__)
        return None
    from datetime import date as _date

    want_consolidated = link.basis == "CONSOLIDATED"
    try:
        when = _date.fromisoformat(link.filed_at[:10])
    except ValueError:
        return None
    # Within a week of the date BSE listed: the two exchanges stamp the same filing a day or two apart.
    near = []
    for r in rows:
        try:
            if abs((_date.fromisoformat(r.filed_at[:10]) - when).days) <= 7:
                near.append(r)
        except ValueError:
            continue
    row = next((r for r in near if r.consolidated == want_consolidated), None) or next(iter(near), None)
    if row is None:
        return None
    data = _fetch(nse, row.xbrl_url, cache_root, sink)
    if data:
        stats.results_from_nse += 1
        log.info("seed %s %s: BSE served nothing, NSE did (%s)", scrip, period, row.xbrl_url.rsplit("/", 1)[-1])
    return data


def seed_shareholding(sink, nse, scrip: str, symbol: str, name: str, since: str, cache_root: Path | None,
                      stats: SeedStats, company: dict | None = None) -> None:
    """Every quarter's shareholding pattern NSE lists for the symbol, into memory."""
    for filing_row in nse.shareholding(symbol, since=since):
        data = _fetch(nse, filing_row.xbrl_url, cache_root, sink)
        if not data:
            stats.skipped += 1
            continue
        stats.shareholding_files += 1
        problem = file_shareholding(sink, scrip, name, filing_row, data, company)
        if problem == "unreadable":
            stats.skipped += 1
        elif problem:
            stats.failures.append(problem)
        else:
            stats.shareholding_periods += 1


def file_shareholding(sink, scrip: str, name: str, filing_row, data: bytes, company: dict | None = None) -> str | None:
    """One quarter's shareholding XBRL into the company's memory. Returns None when filed, "unreadable", or why it
    was refused: a promoter holding that disagrees with NSE's own list by more than 0.5 point is stored nowhere
    (never a figure we cannot stand behind)."""
    parsed = xbrl_fast_path.parse(data)
    if not parsed or parsed.kind != "SHAREHOLDING" or not parsed.ownership:
        return "unreadable"
    own = parsed.ownership
    if filing_row.promoter_pct is not None and own.promoter_pct is not None \
            and abs(filing_row.promoter_pct - own.promoter_pct) > 0.5:
        return (f"{scrip} {filing_row.period}: XBRL promoter {own.promoter_pct}% against "
                f"{filing_row.promoter_pct}% in NSE's list")
    filing = _filing("shp", scrip, name, filing_row.period, filing_row.filed_at, filing_row.xbrl_url)
    out = Pass2Output(is_material=False, timeline_entry="")
    out.dossier_delta.ownership = own
    dossier = sink.get_dossier(scrip) or new_dossier(filing, company or {})
    sink.put_dossier(scrip, merge(dossier, out, filing, None, now_iso()))
    log.info("shareholding %s %s: promoter %s%%, pledge %s%%, FII %s%%, DII %s%%", scrip, filing_row.period,
             own.promoter_pct, own.pledge_pct, own.fii_pct, own.dii_pct)
    return None
