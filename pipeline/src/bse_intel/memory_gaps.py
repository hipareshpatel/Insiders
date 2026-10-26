"""Which universe companies lack exchange-XBRL results quarters in memory, and a fill for them. No AI.

Owner decision (docs/TODO.md, "Owner's answers on memory labels", Q2): a year-ago figure that cannot be checked is left
blank on a card, so every universe company's memory should hold its results from the exchange's own files first.

For each company, over the last ``QUARTERS`` quarters ending at the latest quarter whose filing deadline has passed
(45 days after the quarter end, 60 for the March quarter; periods.RESULTS_DAYS_*), a quarter is *missing* when memory
holds neither an xbrl-sourced revenue nor an xbrl-sourced PAT for it on the company's main basis (consolidated when it
has any machine-tagged consolidated quarter, else standalone). A quarter with no consolidated file, filled by its standalone figures, counts as filled ("standalone_only", F162).
A quarter with one of the two is *partial*: listed in
the JSON, not counted as missing. For the latest quarter the year-ago quarter (the YoY base on its card) is reported
too. Reading uses metrics._figures, the same picker the metrics table uses.

``fill`` calls the seed's per-company results function for the companies with gaps only; the caller re-checks.
"""

from __future__ import annotations

import calendar
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .metrics import CONSOLIDATED, STANDALONE, _figures
from .periods import RESULTS_DAYS_QUARTER, RESULTS_DAYS_YEAR, prior_year_period, quarter_from_index, quarter_index
from .timeutil import now_iso

log = logging.getLogger(__name__)

QUARTERS = 8
READ_WORKERS = 8   # dossiers read at once: 1,855 one after another took 11 minutes over the platform sink
TRIED_KEY = "memgaps:fill_tried"   # kv: companies a fill already tried (a gap NSE cannot close is not retried each pass)


def quarter_end(period: str) -> date | None:
    """Q1FY27 -> 2026-06-30 (the Indian financial year FY27 runs April 2026 to March 2027)."""
    index = quarter_index(period)
    if index is None:
        return None
    fy, q = divmod(index - 1, 4)
    year = 2000 + fy % 100
    month = (6, 9, 12, 3)[q]
    if month != 3:
        year -= 1
    return date(year, month, calendar.monthrange(year, month)[1])


def due_by(period: str) -> date | None:
    end = quarter_end(period)
    if end is None:
        return None
    return end + timedelta(days=RESULTS_DAYS_YEAR if period.startswith("Q4") else RESULTS_DAYS_QUARTER)


def latest_due_quarter(today: date) -> str:
    """The newest quarter whose filing deadline is before ``today``."""
    index = (today.year - 2000 + 1) * 4 + 4   # a quarter well ahead, then walk back
    while True:
        period = quarter_from_index(index)
        if due_by(period) < today:
            return period
        index -= 1


def window(today: date, quarters: int = QUARTERS) -> list[str]:
    """The quarters checked, newest first."""
    top = quarter_index(latest_due_quarter(today))
    return [quarter_from_index(top - i) for i in range(quarters)]


def main_basis(dossier: dict) -> str | None:
    """The basis of the company's newest machine-tagged quarter (revenue or PAT); consolidated when both bases reach
    the same newest quarter, else the one that is newer; none without any. It was "consolidated when memory holds any
    consolidated quarter", which kept a company that stopped filing consolidated results (Bharat Wire Ropes: FY23-FY24
    consolidated, then standalone only) on a basis its newer quarters are not on: every one of them read as missing
    and no fill could close them (gaps fill of 25 Oct 2026)."""
    newest: dict[str, int] = {}
    for basis in (CONSOLIDATED, STANDALONE):
        figures, _ = _figures(dossier, basis)
        indexes = [quarter_index(period) for (metric, period), entry in figures.items()
                   if metric in ("revenue", "pat") and entry.get("value") is not None]
        indexes = [i for i in indexes if i is not None]
        if indexes:
            newest[basis] = max(indexes)
        elif any(metric in ("revenue", "pat") for metric, _ in figures):
            newest[basis] = 0   # only a year or half year on this basis: still a basis, the weakest
    if not newest:
        return None
    return max(newest, key=lambda b: (newest[b], b == CONSOLIDATED))


def check(dossier: dict | None, today: date, quarters: int = QUARTERS) -> dict:
    """One company's gaps: basis, missing quarters, partial quarters, and the latest quarter's year-ago state."""
    periods = window(today, quarters)
    latest = periods[0]
    yago = prior_year_period(latest)
    basis = main_basis(dossier) if dossier else None
    out = {"basis": basis, "latest": latest, "year_ago": yago, "missing": [], "partial": [],
           "no_xbrl": basis is None, "standalone_only": [], "missing_latest": False, "missing_year_ago": False}
    have: dict[str, set[str]] = {}
    standalone_only: set[str] = set()
    if basis:
        figures, _ = _figures(dossier, basis)
        for (metric, period), entry in figures.items():
            if metric in ("revenue", "pat") and entry.get("value") is not None:
                have.setdefault(period, set()).add(metric)
        # A quarter with no consolidated results file (NSE lists only standalone for it) is filled by its standalone
        # figures: they are the company's figures for it (F162; Jyothy Labs after it sold its only subsidiary, ABB India
        # before its first). The seed lists such quarters in ``standalone_only``; and a company whose newest basis is
        # standalone keeps the consolidated quarters it had before as filled.
        other = STANDALONE if basis == CONSOLIDATED else CONSOLIDATED
        listed = set(dossier.get("standalone_only") or [])
        if listed or basis == STANDALONE:
            more, _ = _figures(dossier, other)
            for (metric, period), entry in more.items():
                if metric in ("revenue", "pat") and entry.get("value") is not None \
                        and (basis == STANDALONE or period in listed):
                    if period not in have or metric not in have[period]:
                        if basis == CONSOLIDATED:
                            standalone_only.add(period)
                        have.setdefault(period, set()).add(metric)
    for period in periods:
        got = have.get(period, set())
        if not got:
            out["missing"].append(period)
        elif len(got) == 1:
            out["partial"].append(period)
    out["standalone_only"] = [p for p in periods if p in standalone_only]
    out["missing_latest"] = latest not in have
    out["missing_year_ago"] = bool(yago) and yago not in have
    return out


def has_gap(result: dict) -> bool:
    return bool(result["missing"]) or result["missing_year_ago"]


def summarise(companies: dict[str, dict]) -> dict:
    rows = list(companies.values())
    return {
        "companies_checked": len(rows),
        "no_xbrl_results": sum(r["no_xbrl"] for r in rows),
        "missing_latest_quarter": sum(r["missing_latest"] for r in rows),
        "missing_year_ago_quarter": sum(r["missing_year_ago"] for r in rows),
        "companies_with_gaps": sum(has_gap(r) for r in rows),
        "missing_company_quarters": sum(len(r["missing"]) for r in rows),
        "partial_company_quarters": sum(len(r["partial"]) for r in rows),
        "standalone_only_company_quarters": sum(len(r.get("standalone_only", [])) for r in rows),
    }


def survey(sink, scrips: list[str], today: date, quarters: int = QUARTERS, workers: int = READ_WORKERS) -> dict:
    """Every company's check, and the summary. The dossiers are read ``workers`` at a time (the reads wait on the
    sink); the result is in ``scrips`` order whatever order the reads finish in, so the output does not change. A read
    that fails raises, as in a plain loop."""
    def one(scrip: str) -> dict:
        return check(sink.get_dossier(scrip), today, quarters)

    if workers <= 1 or len(scrips) <= 1:
        results = [one(scrip) for scrip in scrips]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, scrips))
    companies = dict(zip(scrips, results))
    periods = window(today, quarters)
    return {"as_of": today.isoformat(), "latest_quarter": periods[0], "quarters": periods,
            "summary": summarise(companies), "companies": companies}


def gap_rows(report: dict) -> list[dict]:
    """The companies with gaps, for the CSV or JSON."""
    return [{"scrip": scrip, "basis": r["basis"], "missing": r["missing"], "missing_year_ago": r["missing_year_ago"]}
            for scrip, r in sorted(report["companies"].items()) if has_gap(r)]


def render(report: dict) -> str:
    s = report["summary"]
    return "\n".join([
        f"memory gaps as of {report['as_of']}: latest quarter past its deadline {report['latest_quarter']}, "
        f"checked {report['quarters'][-1]}..{report['quarters'][0]}",
        f"companies checked            {s['companies_checked']}",
        f"no xbrl results at all       {s['no_xbrl_results']}",
        f"missing the latest quarter   {s['missing_latest_quarter']}",
        f"missing the year-ago quarter {s['missing_year_ago_quarter']}",
        f"companies with any gap       {s['companies_with_gaps']}",
        f"missing company-quarters     {s['missing_company_quarters']}",
        f"partial (one of revenue/PAT) {s['partial_company_quarters']}",
        f"filled, standalone only      {s.get('standalone_only_company_quarters', 0)}"])


def to_csv(report: dict) -> str:
    out = ["scrip,basis,missing_quarters,missing_year_ago"]
    for row in gap_rows(report):
        out.append(f"{row['scrip']},{row['basis'] or ''},{' '.join(row['missing'])},{str(row['missing_year_ago']).lower()}")
    return "\n".join(out) + "\n"


def since_for(result: dict) -> str:
    """The seed's ``since``: about a quarter before the oldest quarter the company lacks (or its year-ago one)."""
    oldest = min(result["missing"] + [result["year_ago"] or result["latest"]], key=quarter_index)
    return (quarter_end(oldest) - timedelta(days=100)).isoformat()


def fill(sink, report: dict, seed_fn, time_budget: float, restart: bool = False,
         shard: tuple[int, int] | None = None, clock=time.monotonic) -> dict:
    """Seed (results only) the companies with gaps, one ``seed_fn(scrip, since)`` call each: the seed's per-company
    function; a NSE refusal (SourceBlockedError) propagates, as in seed-memory. A company an earlier pass already tried
    is skipped unless ``restart`` (the tried list is saved after every company, so a stopped run resumes). ``more`` is
    true when the time budget ended the run with companies left."""
    from .nse import SourceBlockedError

    key = TRIED_KEY + (f":{shard[0]}of{shard[1]}" if shard else "")
    tried = set() if restart else set(json.loads(sink.kv_get(key) or "[]"))
    todo = [s for s, r in sorted(report["companies"].items()) if has_gap(r)]
    if shard:
        todo = todo[shard[0]::shard[1]]
    attempted, failed, more = [], [], False
    deadline = clock() + time_budget
    for scrip in todo:
        if scrip in tried:
            continue
        if clock() >= deadline:
            more = True
            break
        try:
            seed_fn(scrip, since_for(report["companies"][scrip]))
        except SourceBlockedError:
            raise
        except Exception as exc:
            failed.append(f"{scrip}: {type(exc).__name__}: {exc}"[:200])
            log.warning("memory-gaps fill %s failed: %s", scrip, exc)
        attempted.append(scrip)
        tried.add(scrip)
        sink.kv_set(key, json.dumps(sorted(tried)), now_iso())
    return {"attempted": attempted, "failed": failed, "more": more}
