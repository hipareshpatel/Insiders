"""Every company's past statements by screener's rules, from the facts already stored, into memory (owner, 30 Oct 2026: "our
stock page having financial statements will be saved as per screener ... we save everything like screener row by row").

`statements-backfill` reads, for each company, the facts documents the bulk download kept in R2 (``raw/xbrl-facts/<scrip>/``:
the results files of the last 12 quarters on both bases, and the annual reports' files) and builds screener.in's four tables
with the recipes the comparison measured (``screener_view._ours``, the same code that scored 96.7% of the FY26 quarters' main
rows): each quarter's P&L, each year's P&L and cash flow (the annual report first, else the March quarter's file), and the
balance sheet at each half year and year end. No request to NSE, BSE or screener.

They go into ``dossier["statements"]`` beside what the live path and the seed write (statements.py), one entry per period,
basis and table, labelled ``file`` with rules ``screener_view``. An entry a filing already wrote is kept (it is the same file,
read when it came); the backfill only adds what is missing. Two checks before an entry goes in:
- a quarter memory holds as unit-slipped (``scale_held``) is left out;
- a quarter's or year's Net Profit more than 1.5x away from memory's own profit for that period and basis is left out
  and listed: memory's figure was checked against the PDF, the stored file may carry a unit slip memory put right.

A dry run unless ``--apply``; at most ``--limit`` companies a run (rule A: 50), in scrip order, resuming after the last company
written (kv ``statements_backfill:done_through``). Each dossier is backed up before it is written (backup.RunBackup), so
``restore`` undoes it. A failure of a read, the backup or a write stops the run."""

from __future__ import annotations

import json
import logging
import re

from . import screener_view as sv
from . import segments
from . import xbrl_facts
from .dossier import keep_concurrent_writes
from .memory_gaps import quarter_end
from .statements import KEY, keep_latest
from .timeutil import now_iso

log = logging.getLogger(__name__)

LIMIT = 50
RESUME_KEY = "statements_backfill:done_through"
SLIP_RATIO = 1.5
_QUARTER = re.compile(r"Q[1-4]FY\d{2}")


def _main_basis(dossier: dict) -> str | None:
    bases = {m.get("basis") for m in dossier.get("financial_metrics", [])} - {None}
    return "CONSOLIDATED" if "CONSOLIDATED" in bases else next(iter(bases), None)


def _memory_profit(dossier: dict, period: str, basis: str) -> float | None:
    """Memory's own whole profit for the period on this basis: the main figures when they are this basis (an entry with no
    basis counts as the main one), else a consolidated filer's standalone block. Profit, not revenue: screener's Sales is net
    of excise duty and memory's revenue is not (ITC), so a top-line check would refuse right rows."""
    if basis == _main_basis(dossier) or _main_basis(dossier) is None:
        rows = [m for m in dossier.get("financial_metrics", []) if m.get("basis") in (basis, None)]
    elif basis == "STANDALONE":
        rows = list((dossier.get("standalone") or {}).get("metrics", []))
    else:
        return None
    for m in rows:
        if m.get("period") == period and m.get("metric") == "pat" and isinstance(m.get("value"), (int, float)):
            return float(m["value"])
    return None


def company_entries(cf: sv.CompanyFacts, dossier: dict, at: str) -> tuple[list[dict], list[str]]:
    """The entries the stored facts give for one company, and the ones left out (with why)."""
    entries, left = [], []
    held = {str(h.get("period")) for h in dossier.get("scale_held", []) if isinstance(h, dict)} \
        | {str(h) for h in dossier.get("scale_held", []) if isinstance(h, str)}
    for basis in sorted({b for _, b in cf.results} | {b for _, b in cf.annual}):
        fam = cf.family(basis)
        memo: dict = {}
        quarters = sorted({p for p, b in cf.results if b == basis and _QUARTER.fullmatch(p)}, key=lambda p: sv.quarter_index(p) or 0)
        years = sorted({p[2:] for p in quarters if p.startswith("Q4")} | {fy for fy, b in cf.annual if b == basis})
        columns = [("quarters", p) for p in quarters] + [("balance", p) for p in quarters if p[:2] in ("Q2", "Q4")] \
            + [("annual", fy) for fy in years] + [("cash_flow", fy) for fy in years]
        for table, period in columns:
            if period in held or f"Q4{period}" in held:
                left.append(f"{basis} {table} {period}: unit slip held in memory")
                continue
            rows, why = sv._ours(cf, fam, basis, table, period, memo)
            values = {name: row.value for name, row in (rows or {}).items() if row.value is not None}
            if not values:
                continue
            if table in ("quarters", "annual"):
                top = values.get("Net Profit")
                mine = _memory_profit(dossier, period, basis)
                if top and mine and abs(mine) >= 1 and (top > 0) == (mine > 0) \
                        and not (1 / SLIP_RATIO <= abs(top) / abs(mine) <= SLIP_RATIO):
                    left.append(f"{basis} {table} {period}: Net Profit {top:g} against memory's profit {mine:g}")
                    continue
            column = period
            entries.append({"period": column, "basis": basis, "table": table, "family": fam, "rows": values,
                            "source_news_id": f"xbrl-facts:{period}:{basis.lower()}", "as_of": at,
                            "lab": {"by": "file", "doc": "results", "basis": basis, "at": at, "rules": "screener_view",
                                    "from": "stored facts"}})
    return entries, left


def fill_segments(cf: sv.CompanyFacts, dossier: dict, at: str) -> int:
    """The business mix of each stored quarter's file into ``dossier["segment_mix"]`` (in place), where no file row of that basis
    holds the period (segments.py); the number of rows added. Consolidated files go first, so a standalone file finds them."""
    added = 0
    for period, basis in sorted(cf.results, key=lambda pb: (pb[1] != "CONSOLIDATED", -(sv.quarter_index(pb[0]) or 0))):
        facts = cf.result(period, basis) if _QUARTER.fullmatch(period) else None
        if facts is not None:
            # stamped with the quarter's own end, not today: the dossier merge keeps the newest rows by stamp, and a
            # backfilled old quarter stamped today would push out the live quarters (blind review)
            end = quarter_end(period)
            added += segments.remember(dossier, facts.doc, f"xbrl-facts:{period}:{basis.lower()}",
                                       end.isoformat() if end else at, at, replace=False, source="stored facts")
    return added


def fill(dossier: dict, entries: list[dict]) -> int:
    """Add the entries memory does not hold yet (in place); the number added."""
    have = {(e.get("period"), e.get("basis"), e.get("table")) for e in dossier.get(KEY, []) if isinstance(e, dict)}
    new = [e for e in entries if (e["period"], e["basis"], e["table"]) not in have]
    if new:
        dossier[KEY] = keep_latest([e for e in dossier.get(KEY, []) if isinstance(e, dict)] + new)
    return len(new)


WRITE_WORKERS = 8   # companies written at once (each its own dossier and backup objects)
WORKERS = 24  # companies read at once: each reads its stored facts documents one by one (run 1: 17 min for 50 alone; run 2 at 8: 8.7 min)


def _prepare(sink, scrip: str, at: str):
    """One company read and worked out (no write): (read, merged, entries, left, segment rows added) or None when it has no dossier or facts."""
    read = sink.get_dossier(scrip)
    keys = sink.list_objects(f"{xbrl_facts.PREFIX}{scrip}/")
    if read is None or not keys:
        return None
    cf = sv.CompanyFacts(keys, sink.get_object)
    merged = json.loads(json.dumps(read))
    entries, left = company_entries(cf, merged, at)
    segments_added = fill_segments(cf, merged, at)
    return read, merged, entries, left, segments_added


def _write(sink, backup, scrip: str, read: dict, merged: dict) -> tuple[str, Exception | None]:
    """One company's write: merged over what landed since it was read, backed up, put. (stage, failure or None)."""
    stage = "saving the backup"
    try:
        keep_concurrent_writes(merged, read, sink.get_dossier(scrip))
        backup.dossier(scrip, merged)
        stage = "writing"
        sink.put_dossier(scrip, merged)
        return stage, None
    except Exception as exc:  # noqa: BLE001 - reported in scrip order by run, where it stops the run
        return stage, exc


def run(sink, scrips: list[str], apply: bool = False, limit: int = LIMIT, restart: bool = False, named: bool = False,
        workers: int = WORKERS, write_workers: int = WRITE_WORKERS) -> dict:
    """``named``: the companies were named (--scrips): the resume point is neither read nor moved (blind review). The companies
    are read ``workers`` at a time and written ``write_workers`` at a time (each company's dossier and backup are its own
    objects; the first write goes alone, as it opens the backup folder). Results are taken in scrip order: the first failure
    stops the run there, and the resume point is the last company of the unbroken run before it, set once at the end (run 4:
    six calls a company one after another were most of its 5.7 minutes). A company written after a failure is written again
    by the next run with nothing to add, so a stop loses nothing."""
    from concurrent.futures import ThreadPoolExecutor

    from .backup import RunBackup

    after = "" if (restart or not apply or named) else (sink.kv_get(RESUME_KEY) or "")
    todo = [s for s in sorted(scrips) if s > after][:limit]
    backup = RunBackup(sink, "statements-backfill") if apply else None
    out = {"apply": apply, "limit": limit, "after": after, "companies": len(todo), "written": 0, "entries": 0,
           "no_facts": 0, "segments": 0, "left_out": [], "by_table": {}, "last": None, "more": len([s for s in scrips if s > after]) > len(todo),
           "backup": None, "error": None}
    at = now_iso()

    def safe(scrip):
        try:
            return _prepare(sink, scrip, at), None
        except Exception as exc:  # noqa: BLE001 - reported in order below, where it stops the run
            return None, exc

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        prepared = list(pool.map(safe, todo))
    plan = []   # (scrip, added, (read, merged) or None), in scrip order, up to the first read failure
    for scrip, (ready, failure) in zip(todo, prepared):
        if failure is not None:
            out["error"] = f"{scrip}, reading: {type(failure).__name__}: {failure}"[:300]
            log.error("statements-backfill stopped at %s while reading: %s", scrip, failure)
            break
        if ready is None:
            out["no_facts"] += 1
            plan.append((scrip, 0, None))
            continue
        read, merged, entries, left, segments_added = ready
        out["left_out"] += [f"{scrip} {x}" for x in left]
        have = {(e.get("period"), e.get("basis"), e.get("table")) for e in merged.get(KEY, []) if isinstance(e, dict)}
        for e in entries:
            if (e["period"], e["basis"], e["table"]) not in have:
                out["by_table"][e["table"]] = out["by_table"].get(e["table"], 0) + 1
        added = fill(merged, entries)
        out["segments"] += segments_added
        plan.append((scrip, added, (read, merged) if (added or segments_added) and apply else None))
    writes = [(scrip, job) for scrip, _, job in plan if job is not None]
    results: dict[str, tuple[str, Exception | None]] = {}
    if writes:
        first, rest = writes[0], writes[1:]
        results[first[0]] = _write(sink, backup, first[0], *first[1])
        if results[first[0]][1] is None and rest:
            with ThreadPoolExecutor(max_workers=max(1, write_workers)) as pool:
                for scrip, outcome in zip([s for s, _ in rest], pool.map(lambda w: _write(sink, backup, w[0], *w[1]), rest)):
                    results[scrip] = outcome
    out["written"] = sum(1 for _, failure in results.values() if failure is None)
    for scrip, added, job in plan:
        if job is not None:
            stage, failure = results.get(scrip, ("writing", RuntimeError("not written: an earlier write failed")))
            if failure is not None:
                out["error"] = f"{scrip}, {stage}: {type(failure).__name__}: {failure}"[:300]
                log.error("statements-backfill stopped at %s while %s: %s", scrip, stage, failure)
                break
        out["entries"] += added
        out["last"] = scrip
    if apply and not named and out["last"]:
        sink.kv_set(RESUME_KEY, out["last"], at)
    if backup is not None:
        out["backup"] = backup.summary()
    return out


def render(o: dict) -> str:
    lines = [f"Statements by screener's rules from the stored facts ({'applied' if o['apply'] else 'dry run, nothing written'}): "
             f"{o['companies']} companies after '{o['after']}', {o['entries']} entries {'added' if o['apply'] else 'to add'}"
             f" in {o['written'] if o['apply'] else '-'} dossiers; {o['no_facts']} without stored facts; last {o['last']};"
             f" more left: {o['more']}",
             "  by table: " + ", ".join(f"{k} {v}" for k, v in sorted(o["by_table"].items())) + f"; segment rows {o['segments']}",
             f"  left out ({len(o['left_out'])}):"] + [f"    {x}" for x in o["left_out"][:60]]
    if o["backup"]:
        lines.append(f"backup: {o['backup']['prefix']} ({o['backup']['dossiers']} dossiers); undo with restore --backup "
                     f"{o['backup']['prefix']} --scrips <scrip> [--apply]")
    if o["error"]:
        lines.append(f"stopped: {o['error']}")
    return "\n".join(lines)
