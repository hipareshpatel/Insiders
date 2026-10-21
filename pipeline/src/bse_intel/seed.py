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
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import xbrl as xbrl_fast_path
from .dossier import forget_source, merge, new_dossier, put_standalone
from .models import Filing, Pass2Output
from .nse import SourceBlockedError
from .periods import canonical_period
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
    standalone_periods: int = 0  # a consolidated filer's standalone quarters, kept apart (dossier.put_standalone)
    failures: list[str] = field(default_factory=list)

    def line(self) -> str:
        return (f"{self.companies} companies: {self.results_periods} results quarters from {self.results_files} XBRL files, "
                f"{self.shareholding_periods} shareholding quarters from {self.shareholding_files} files, "
                f"{self.skipped} skipped, {len(self.failures)} failures"
                + (f", {self.results_from_nse} quarters from NSE where BSE served nothing" if self.results_from_nse else "")
                + (f", {self.rescaled} files in the wrong unit put right" if self.rescaled else ""))


def _cache(root: Path | None, url: str) -> Path | None:
    if not root:
        return None
    return root / "xbrl" / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".xml.gz")


def _fetch(client, url: str, root: Path | None) -> bytes | None:
    """One XBRL file, kept by checksum so a parser fix is a re-parse and not another download."""
    path = _cache(root, url)
    if path and path.exists():
        try:
            return gzip.decompress(path.read_bytes())
        except OSError:
            pass
    data = client.download(url, max_bytes=8_000_000)
    if data and path:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(data))
        except OSError:
            pass
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
        data = _fetch(bse, link.url, cache_root)
        if not data and nse is not None and symbol:
            data = _from_nse(nse, symbol, period, link, cache_root, stats, scrip)
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
        for period, row in _nse_quarters(nse, symbol, since, scrip).items():
            if period in found:
                continue
            data = _fetch(nse, row.xbrl_url, cache_root)
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
    # re-filed Q4FY25 and Q2FY26, T5 2026-10-20) is left to the cards rather than set beside consolidated quarters
    if any(result.basis == "CONSOLIDATED" for _, _, result, _ in found.values()):
        dropped = [p for p, (_, _, result, _) in found.items() if result.basis == "STANDALONE"]
        for period in dropped:
            log.info("seed %s %s: standalone file only, the company files consolidated; left to the cards", scrip, period)
            stats.skipped += 1
            found.pop(period)
        # and out of memory, where an earlier seed put it
        dossier = sink.get_dossier(scrip) if dropped else None
        if dossier is not None and any([forget_source(dossier, f"xbrl:res:{scrip}:{period}") for period in dropped]):
            sink.put_dossier(scrip, dossier)
    for period, (filed_on, url, parsed, _) in found.items():
        others = [m for other, (_, _, result, _) in found.items() if other != period for m in result.metrics]
        if xbrl_fast_path.fix_scale(parsed, others, scrip):
            stats.rescaled += 1
    for period, (filed_on, url, parsed, _) in sorted(found.items()):
        _write_results(sink, scrip, name, company, period, filed_on, url, parsed, stats)
    # a consolidated filer's standalone files too, kept apart for the company page's standalone view (owner,
    # 2026-10-21); the quarters the consolidated ones cover, no more
    consolidated = [p for p, (_, _, result, _) in found.items() if result.basis == "CONSOLIDATED"]
    if nse is not None and symbol and consolidated:
        _seed_standalone(sink, nse, scrip, symbol, since, set(consolidated), cache_root, stats)


def _seed_standalone(sink, nse, scrip: str, symbol: str, since: str, periods: set[str], cache_root, stats) -> None:
    try:
        rows = _nse_rows(nse, symbol)
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
        data = _fetch(nse, row.xbrl_url, cache_root)
        parsed = _parse_results(data, stats) if data else None
        if parsed is None or parsed.basis == "CONSOLIDATED":
            continue
        put_standalone(dossier, parsed.metrics, parsed.balance_sheet, f"{row.filed_at[:10]}T18:00:00+05:30",
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


def _write_results(sink, scrip: str, name: str, company: dict | None, period: str, filed_on: str,
                   url: str, parsed, stats: SeedStats) -> None:
    """One parsed results file into memory."""
    filing = _filing("res", scrip, name, period, f"{filed_on}T18:00:00+05:30", url)
    out = Pass2Output(is_material=False, timeline_entry="")
    out.dossier_delta.financial_metrics = list(parsed.metrics)
    if parsed.balance_sheet and not parsed.balance_sheet.is_empty():
        out.dossier_delta.balance_sheet = parsed.balance_sheet
    dossier = sink.get_dossier(scrip) or new_dossier(filing, company or {})
    sink.put_dossier(scrip, merge(dossier, out, filing, None, now_iso(), basis=parsed.basis))
    stats.results_periods += 1
    log.info("seed %s %s: %d figures from %s (%s)", scrip, period, len(parsed.metrics), url.rsplit("/", 1)[-1],
             parsed.basis or "basis not stated")


def _nse_quarters(nse, symbol: str, since: str, scrip: str) -> dict:
    """The newest filing NSE lists per quarter, consolidated where both bases are filed."""
    try:
        rows = _nse_rows(nse, symbol)
    except SourceBlockedError:
        raise  # NSE limits by IP: the caller stops the seed rather than marking the company done with nothing
    except Exception as exc:
        log.info("seed %s: NSE list unavailable (%s)", scrip, type(exc).__name__)
        return {}
    best: dict = {}
    for row in sorted(rows, key=lambda r: (r.consolidated, r.filed_at)):   # consolidated first, as in seed_company
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


@lru_cache(maxsize=64)
def _nse_rows(nse, symbol: str) -> tuple:
    """NSE's results list for one symbol, fetched once: it is read per quarter and the client paces
    itself by several seconds a call."""
    return tuple(nse.financial_results(symbol))


def _from_nse(nse, symbol: str, period: str, link, cache_root: Path | None, stats: SeedStats,
              scrip: str) -> bytes | None:
    """The same quarter from NSE, when BSE served nothing. Matched on the filing date BSE listed, so the
    row is the same filing and not merely the same company; the basis is matched where NSE states it."""
    try:
        rows = _nse_rows(nse, symbol)
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
    data = _fetch(nse, row.xbrl_url, cache_root)
    if data:
        stats.results_from_nse += 1
        log.info("seed %s %s: BSE served nothing, NSE did (%s)", scrip, period, row.xbrl_url.rsplit("/", 1)[-1])
    return data


def seed_shareholding(sink, nse, scrip: str, symbol: str, name: str, since: str, cache_root: Path | None,
                      stats: SeedStats, company: dict | None = None) -> None:
    """Every quarter's shareholding pattern NSE lists for the symbol, into memory."""
    for filing_row in nse.shareholding(symbol, since=since):
        data = _fetch(nse, filing_row.xbrl_url, cache_root)
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
