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
from . import xbrl_extras
from . import xbrl_facts
from .dossier import keep_concurrent_writes
from .memory_gaps import quarter_end
from .statements import KEY, keep_latest
from .timeutil import now_iso

log = logging.getLogger(__name__)

LIMIT = 50
RESUME_KEY = "statements_backfill:done_through"
REBUILD_RESUME_KEY = "statements_rebuild:done_through"   # statements-rebuild's own (it must not move the fill's)
RATINGS_RESUME_KEY = "statements_backfill:ratings_done_through"   # the put-back's own (review: it must not move the fill's)
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
                values = sv.corrected_pl(values, fam)   # the profit-line rules, as at the live write (screener_view.corrected_pl)
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


def fill_extras(cf: sv.CompanyFacts, dossier: dict, at: str) -> int:
    """What the stored quarters' and annual reports' files say beyond the statements (xbrl_extras.py: audit status and auditors,
    cash-flow detail, related parties, ratios) into the dossier's own keys (in place), where the period and basis hold none yet;
    the number of entries added. Stamped with the period's own end, as fill_segments does. A file that fails is skipped."""
    added = 0
    docs = [(period, basis, cf.result(period, basis)) for period, basis in cf.results if _QUARTER.fullmatch(period)]
    docs += [(fy, basis, cf._load(key)) for (fy, basis), key in cf.annual.items()]
    for period, basis, facts in sorted(docs, key=lambda d: (d[1] != "CONSOLIDATED", d[0])):
        if facts is None:
            continue
        try:
            end = xbrl_extras._end(facts.doc)
            added += xbrl_extras.remember(dossier, facts.doc, f"xbrl-facts:{period}:{basis.lower()}",
                                          end.isoformat() if end else at, at, replace=False, source="stored facts")
        except Exception as exc:  # noqa: BLE001 - an addition: one file's failure leaves the rest
            log.warning("statements-backfill: extras of %s %s not built: %s", period, basis, exc)
    return added


RATING_FIELDS = ("credit_rating", "rating_agency", "rating_outlook")
_SNAPSHOT_META = {"period", "as_of", "source_news_id", "lab", "file_fields", "basis"}


def _held(e: dict) -> set[str]:
    """What a balance-sheet snapshot holds: its figures (``*_cr`` numbers) and its rating fields (a rating filing's snapshot
    has no figure at all: review of PR #256, 30 Oct 2026; the cards read the last rating from here, card_context)."""
    return ({k for k, v in e.items() if k.endswith("_cr") and isinstance(v, (int, float)) and not isinstance(v, bool)}
            | {k for k in RATING_FIELDS if isinstance(e.get(k), str) and e[k].strip()})


def drop_empty_balance(dossier: dict) -> int:
    """Balance-sheet snapshots holding no figure (an AI reading's dated stub: SBI's "Jun-2026" after the file's Q4FY26; stock-page
    audit, 30 Oct 2026) out of memory, the main and the standalone list (in place); the number dropped. Owner, 30 Oct 2026: yes."""
    def real(e) -> bool:
        return isinstance(e, dict) and bool(_held(e))
    dropped = 0
    for holder in (dossier, dossier.get("standalone") if isinstance(dossier.get("standalone"), dict) else None):
        if holder is None or not isinstance(holder.get("balance_sheet"), list):
            continue
        kept = [e for e in holder["balance_sheet"] if real(e)]
        dropped += len(holder["balance_sheet"]) - len(kept)
        if len(kept) != len(holder["balance_sheet"]):
            holder["balance_sheet"] = kept
    return dropped


_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def _balance_end(period) -> str | None:
    """A snapshot's date: Q4FY26 -> 2026-03-31 (the file's periods), "Mar-2026" -> 2026-03 (an AI reading's)."""
    if not isinstance(period, str):
        return None
    if (end := quarter_end(period)) is not None:
        return end.isoformat()[:7]
    m = re.fullmatch(r"([A-Za-z]{3})[a-z]*[- ](\d{4})", period.strip())
    if m and m.group(1).lower() in _MONTHS:
        return f"{m.group(2)}-{_MONTHS[m.group(1).lower()]:02d}"
    return None


def _from_file(e: dict) -> bool:
    lab = e.get("lab") if isinstance(e.get("lab"), dict) else {}
    return lab.get("by") == "file" or str(e.get("source_news_id") or "").startswith("xbrl:")


def drop_file_covered_balance(dossier: dict) -> tuple[int, int]:
    """Balance-sheet snapshots an AI reading wrote for a date the exchange file also covers, out of memory (main and
    standalone lists, in place): SBI's "Mar-2026" net worth 4,72,895 Cr (results PDF) and 5,43,519 Cr (call) beside the file's
    Q4FY26 6,14,899 Cr (owner, 30 Oct 2026: yes). Dropped only when the file's snapshot of that month holds every field the
    reading holds (a figure, a rating), so nothing is lost; (dropped, kept because the reading has a figure the file lacks)."""
    def figures(e) -> set[str]:
        return _held(e) | {k for k, v in e.items() if k not in _SNAPSHOT_META and v not in (None, "", [], {})}
    dropped = kept_extra = 0
    for holder in (dossier, dossier.get("standalone") if isinstance(dossier.get("standalone"), dict) else None):
        if holder is None or not isinstance(holder.get("balance_sheet"), list):
            continue
        filed: dict[str, set[str]] = {}
        for e in holder["balance_sheet"]:
            if isinstance(e, dict) and _from_file(e) and (end := _balance_end(e.get("period"))):
                filed.setdefault(end, set()).update(figures(e))
        kept = []
        for e in holder["balance_sheet"]:
            end = _balance_end(e.get("period")) if isinstance(e, dict) and not _from_file(e) else None
            if end in filed:
                if figures(e) <= filed[end]:
                    dropped += 1
                    continue
                kept_extra += 1
            kept.append(e)
        if len(kept) != len(holder["balance_sheet"]):
            holder["balance_sheet"] = kept
    return dropped, kept_extra


RATINGS_SINCE = "20261030T"   # the runs whose empty-snapshot clean-up (PR #250) also took out rating snapshots


def _rating_id(e: dict) -> tuple:
    """A rating snapshot's identity: the same rating with a field added since (its label) is not a second one."""
    return (e.get("period"), e.get("source_news_id"), *(e.get(k) for k in RATING_FIELDS))


def lost_ratings(sink, since: str = RATINGS_SINCE) -> dict[str, dict[str, list[dict]]]:
    """The rating snapshots (a rating, no figure) the backups of statements-backfill runs since ``since`` held before the run:
    scrip -> {"main": [...], "standalone": [...]}. ``drop_empty_balance`` read them as empty until the review of PR #256."""
    from .backup import PREFIX
    out: dict[str, dict[str, list[dict]]] = {}
    seen: set[str] = set()
    for key in sink.list_objects(f"{PREFIX}statements-backfill-"):
        folder, _, rest = key[len(PREFIX):].partition("/")
        if folder[len("statements-backfill-"):] < since or not rest.startswith("memory/") or not rest.endswith(".json"):
            continue
        body = sink.get_object(key)
        dossier = json.loads(body) if body else None
        if not isinstance(dossier, dict):
            continue
        scrip = rest[len("memory/"):-len(".json")]
        standalone = dossier.get("standalone") if isinstance(dossier.get("standalone"), dict) else {}
        for part, sheets in (("main", dossier.get("balance_sheet")), ("standalone", standalone.get("balance_sheet"))):
            for e in sheets if isinstance(sheets, list) else []:
                if isinstance(e, dict) and _held(e) and _held(e) <= set(RATING_FIELDS):
                    mark = json.dumps([scrip, part, _rating_id(e)])
                    if mark not in seen:
                        seen.add(mark)
                        out.setdefault(scrip, {}).setdefault(part, []).append(e)
    return out


def put_back(dossier: dict, lost: dict[str, list[dict]]) -> int:
    """The lost rating snapshots memory no longer holds, back in date order (in place); the number put back."""
    added = 0
    for part, entries in lost.items():
        if part == "main":
            holder = dossier
        else:
            holder = dossier.setdefault("standalone", {"metrics": [], "balance_sheet": []})
            if not isinstance(holder, dict):
                continue
        sheets = holder.get("balance_sheet") if isinstance(holder.get("balance_sheet"), list) else []
        have = {_rating_id(e) for e in sheets if isinstance(e, dict)}
        new = [e for e in entries if _rating_id(e) not in have]
        if new:
            holder["balance_sheet"] = sorted(sheets + new, key=lambda e: str(e.get("as_of") or "") if isinstance(e, dict) else "")
            added += len(new)
    return added


def _rebuildable(e: dict) -> bool:
    """An entry the stored facts rebuild: the file's own, by screener_view's recipes (never a card's or another source's)."""
    lab = e.get("lab") or {}
    return lab.get("by") == "file" and lab.get("rules", "screener_view") == "screener_view"


def fill(dossier: dict, entries: list[dict], replace: bool = False) -> int:
    """Add the entries memory does not hold yet (in place); the number added. ``replace`` (statements-rebuild): an entry the stored
    facts rebuild is put back with the current recipes when its rows changed (owner, 31 Oct 2026: a recipe rule is site-wide, so
    the stored statements the stock page reads are rebuilt from the same files; the backfill alone only added), counted too."""
    held = [e for e in dossier.get(KEY, []) if isinstance(e, dict)]
    have = {(e.get("period"), e.get("basis"), e.get("table")): e for e in held}
    new = [e for e in entries if (e["period"], e["basis"], e["table"]) not in have]
    changed = []
    if replace:
        changed = [e for e in entries if (old := have.get((e["period"], e["basis"], e["table"]))) is not None
                   and _rebuildable(old) and (old.get("rows") or {}) != (e.get("rows") or {})]
    if new or changed:
        gone = {(e["period"], e["basis"], e["table"]) for e in changed}
        dossier[KEY] = keep_latest([e for e in held if (e.get("period"), e.get("basis"), e.get("table")) not in gone] + new + changed)
    return len(new) + len(changed)


WRITE_WORKERS = 8   # companies written at once (each its own dossier and backup objects)
WORKERS = 24  # companies read at once: each reads its stored facts documents one by one (run 1: 17 min for 50 alone; run 2 at 8: 8.7 min)


def _prepare(sink, scrip: str, at: str, lost: dict | None = None):
    """One company read and worked out (no write): (read, merged, entries, left, segment rows added) or None when it has no dossier or facts."""
    read = sink.get_dossier(scrip)
    keys = sink.list_objects(f"{xbrl_facts.PREFIX}{scrip}/")
    if read is None or not keys:
        return None
    cf = sv.CompanyFacts(keys, sink.get_object)
    merged = json.loads(json.dumps(read))
    entries, left = company_entries(cf, merged, at)
    segments_added = fill_segments(cf, merged, at) + fill_extras(cf, merged, at)   # rows and entries added beyond the statements
    stubs = drop_empty_balance(merged)
    covered, extra = drop_file_covered_balance(merged)
    restored = put_back(merged, lost.get(scrip, {})) if lost else 0
    return read, merged, entries, left, segments_added, stubs, covered, extra, restored


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
        workers: int = WORKERS, write_workers: int = WRITE_WORKERS, ratings: dict | None = None, replace: bool = False) -> dict:
    """``ratings`` (lost_ratings): the rating snapshots to put back, company by company. ``named``: the companies were named (--scrips): the resume point is neither read nor moved (blind review). The companies
    are read ``workers`` at a time and written ``write_workers`` at a time (each company's dossier and backup are its own
    objects; the first write goes alone, as it opens the backup folder). Results are taken in scrip order: the first failure
    stops the run there, and the resume point is the last company of the unbroken run before it, set once at the end (run 4:
    six calls a company one after another were most of its 5.7 minutes). A company written after a failure is written again
    by the next run with nothing to add, so a stop loses nothing."""
    from concurrent.futures import ThreadPoolExecutor

    from .backup import RunBackup

    resume = RATINGS_RESUME_KEY if ratings else REBUILD_RESUME_KEY if replace else RESUME_KEY
    after = "" if (restart or not apply or named) else (sink.kv_get(resume) or "")
    todo = [s for s in sorted(scrips) if s > after][:limit]
    backup = RunBackup(sink, "statements-rebuild" if replace else "statements-backfill") if apply else None
    out = {"apply": apply, "replace": replace, "limit": limit, "after": after, "companies": len(todo), "written": 0, "entries": 0,
           "no_facts": 0, "segments": 0, "balance_stubs": 0, "balance_covered": 0, "balance_kept_extra": 0, "ratings_put_back": 0, "left_out": [], "by_table": {}, "last": None, "more": len([s for s in scrips if s > after]) > len(todo),
           "backup": None, "error": None}
    at = now_iso()

    def safe(scrip):
        try:
            return _prepare(sink, scrip, at, ratings), None
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
        read, merged, entries, left, segments_added, stubs, covered, extra, restored = ready
        out["ratings_put_back"] += restored
        out["balance_stubs"] += stubs
        out["balance_covered"] += covered
        out["balance_kept_extra"] += extra
        out["left_out"] += [f"{scrip} {x}" for x in left]
        have = {(e.get("period"), e.get("basis"), e.get("table")): e for e in merged.get(KEY, []) if isinstance(e, dict)}
        for e in entries:
            old = have.get((e["period"], e["basis"], e["table"]))
            if old is None or (replace and _rebuildable(old) and (old.get("rows") or {}) != (e.get("rows") or {})):
                out["by_table"][e["table"]] = out["by_table"].get(e["table"], 0) + 1
        added = fill(merged, entries, replace)
        out["segments"] += segments_added
        # written when anything changed, a clean-up with nothing added too (30 Oct 2026: filler-zero ratios dropped by
        # xbrl_extras.remember were never saved, the run writing only where entries were added)
        plan.append((scrip, added, (read, merged) if (added or segments_added or merged != read) and apply else None))
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
        sink.kv_set(resume, out["last"], at)
    if backup is not None:
        out["backup"] = backup.summary()
    return out


def render(o: dict) -> str:
    lines = [f"Statements by screener's rules from the stored facts ({'applied' if o['apply'] else 'dry run, nothing written'}): "
             f"{o['companies']} companies after '{o['after']}', {o['entries']} entries {'added' if o['apply'] else 'to add'}"
             f" in {o['written'] if o['apply'] else '-'} dossiers; {o['no_facts']} without stored facts; last {o['last']};"
             f" more left: {o['more']}",
             "  by table: " + ", ".join(f"{k} {v}" for k, v in sorted(o["by_table"].items())) + f"; segment rows and extras (audit, cash-flow detail, related parties, ratios) {o['segments']}"
             f"; empty balance-sheet snapshots dropped {o.get('balance_stubs', 0)}"
             f"; AI balance-sheet snapshots the file covers dropped {o.get('balance_covered', 0)}"
             f" (kept, a figure the file lacks: {o.get('balance_kept_extra', 0)}); rating snapshots put back {o.get('ratings_put_back', 0)}",
             f"  left out ({len(o['left_out'])}):"] + [f"    {x}" for x in o["left_out"][:60]]
    if o["backup"]:
        lines.append(f"backup: {o['backup']['prefix']} ({o['backup']['dossiers']} dossiers); undo with restore --backup "
                     f"{o['backup']['prefix']} --scrips <scrip> [--apply]")
    if o["error"]:
        lines.append(f"stopped: {o['error']}")
    return "\n".join(lines)
