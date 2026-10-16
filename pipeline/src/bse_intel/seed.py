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
from pathlib import Path

from . import xbrl as xbrl_fast_path
from .dossier import merge, new_dossier
from .models import Filing, Pass2Output
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
    failures: list[str] = field(default_factory=list)

    def line(self) -> str:
        return (f"{self.companies} companies: {self.results_periods} results quarters from {self.results_files} XBRL files, "
                f"{self.shareholding_periods} shareholding quarters from {self.shareholding_files} files, "
                f"{self.skipped} skipped, {len(self.failures)} failures")


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
                 stats: SeedStats, company: dict | None = None) -> None:
    """Every quarter's results XBRL in the company's BSE archive, into memory. Consolidated wins where
    a quarter has both: memory keeps one basis, and the cards quote the consolidated figures."""
    links = [link for link in bse.results_xbrl(scrip) if link.filed_at[:10] >= since]
    by_period: dict[str, object] = {}
    for link in sorted(links, key=lambda link: (link.filed_at, link.basis == "CONSOLIDATED")):
        by_period[link.period] = link  # later filing, then consolidated, wins
    for period, link in sorted(by_period.items()):
        data = _fetch(bse, link.url, cache_root)
        if not data:
            stats.skipped += 1
            continue
        stats.results_files += 1
        parsed = xbrl_fast_path.parse(data)
        if not parsed or parsed.kind != "RESULTS" or not parsed.metrics:
            stats.skipped += 1
            continue
        filing = _filing("res", scrip, name, period, f"{link.filed_at[:10]}T18:00:00+05:30", link.url)
        out = Pass2Output(is_material=False, timeline_entry="")
        out.dossier_delta.financial_metrics = list(parsed.metrics)
        if parsed.balance_sheet and not parsed.balance_sheet.is_empty():
            out.dossier_delta.balance_sheet = parsed.balance_sheet
        dossier = sink.get_dossier(scrip) or new_dossier(filing, company or {})
        sink.put_dossier(scrip, merge(dossier, out, filing, None, now_iso()))
        stats.results_periods += 1
        log.info("seed %s %s: %d figures from %s (%s)", scrip, period, len(parsed.metrics), link.url.rsplit("/", 1)[-1],
                 parsed.basis or "basis not stated")


def seed_shareholding(sink, nse, scrip: str, symbol: str, name: str, since: str, cache_root: Path | None,
                      stats: SeedStats, company: dict | None = None) -> None:
    """Every quarter's shareholding pattern NSE lists for the symbol, into memory."""
    for filing_row in nse.shareholding(symbol, since=since):
        data = _fetch(nse, filing_row.xbrl_url, cache_root)
        if not data:
            stats.skipped += 1
            continue
        stats.shareholding_files += 1
        parsed = xbrl_fast_path.parse(data)
        if not parsed or parsed.kind != "SHAREHOLDING" or not parsed.ownership:
            stats.skipped += 1
            continue
        own = parsed.ownership
        if filing_row.promoter_pct is not None and own.promoter_pct is not None \
                and abs(filing_row.promoter_pct - own.promoter_pct) > 0.5:
            stats.failures.append(f"{scrip} {filing_row.period}: XBRL promoter {own.promoter_pct}% against "
                                  f"{filing_row.promoter_pct}% in NSE's list")
            continue  # the two disagree: store neither (never a figure we cannot stand behind)
        filing = _filing("shp", scrip, name, filing_row.period, filing_row.filed_at, filing_row.xbrl_url)
        out = Pass2Output(is_material=False, timeline_entry="")
        out.dossier_delta.ownership = own
        dossier = sink.get_dossier(scrip) or new_dossier(filing, company or {})
        sink.put_dossier(scrip, merge(dossier, out, filing, None, now_iso()))
        stats.shareholding_periods += 1
        log.info("seed %s %s: promoter %s%%, pledge %s%%, FII %s%%, DII %s%%", scrip, filing_row.period,
                 own.promoter_pct, own.pledge_pct, own.fii_pct, own.dii_pct)
