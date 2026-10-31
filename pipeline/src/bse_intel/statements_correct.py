"""Put the profit-line rules over the stored statements (owner, 31 Oct 2026: "the stock page must read corrected numbers too").

``screener_view.corrected_pl`` (the owners' profit that does not add up with the minority's share, the filler zero, and the profit on
the wrong side of PBT - Tax) is applied when an entry is written (``statements.remember``, the backfill) and where it is read (fact
sheet, Results). The company page reads the stored rows as they are, and ``statements-backfill`` only adds missing entries, so entries
stored before the rules still hold the slips (ATUL Q2FY26 owners 87.95 beside 182.37; APARINDS Q1FY27 -138.56; 204 filler zeros).
``statements-correct`` rewrites exactly those: every file-labelled ``quarters`` and ``annual`` entry of every stored dossier goes
through the same function, and a dossier is written only when an entry changed. A dry run unless ``--apply``: the changes (scrip,
period, basis, table, row, old, new) are counted and listed, nothing is written.

With ``--apply`` each changed dossier is backed up first (``backup.RunBackup``: as stored and as about to be written, read back), then
written through ``keep_concurrent_writes``, so ``restore`` undoes it. Companies are done ``SAVE_EVERY`` at a time and each chunk is
saved before the next is read; the resume point (kv ``statements_correct:done_through``) moves after every chunk, so a stopped run keeps
its work and the next one carries on (``--restart`` starts again; a named ``--scrips`` run neither reads nor moves it). Any failure of
the read, the backup or the write stops the run; what was done is reported. No NSE, no AI."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from . import screener_view as sv
from .dossier import keep_concurrent_writes
from .statements import KEY
from .timeutil import now_iso

log = logging.getLogger(__name__)

RESUME_KEY = "statements_correct:done_through"
SAVE_EVERY = 50
WORKERS = 16
TABLES = ("quarters", "annual")


def corrections(dossier: dict) -> list[dict]:
    """Correct the dossier's file-labelled quarters and annual entries in place; the changes made, one per row."""
    changes: list[dict] = []
    for e in dossier.get(KEY, []) or []:
        if not (isinstance(e, dict) and e.get("table") in TABLES and (e.get("lab") or {}).get("by") == "file"):
            continue
        rows = e.get("rows") or {}
        fixed = sv.corrected_pl(rows, e.get("family") or "")
        if fixed is rows:
            continue
        for name in sorted(fixed):
            if fixed[name] != rows.get(name):
                changes.append({"period": e.get("period"), "basis": e.get("basis"), "table": e.get("table"), "row": name,
                                "old": rows.get(name), "new": fixed[name]})
        e["rows"] = fixed
    return changes


def run(sink, scrips: list[str], apply: bool = False, limit: int = 0, restart: bool = False, named: bool = False) -> dict:
    """The pass over ``scrips`` (sorted); ``limit`` 0 means all. See the module's docstring."""
    from .backup import RunBackup

    after = "" if (restart or not apply or named) else (sink.kv_get(RESUME_KEY) or "")
    pending = [s for s in sorted(scrips) if s > after]
    todo = pending[:limit] if limit else pending
    backup = RunBackup(sink, "statements-correct") if apply else None
    out: dict = {"apply": apply, "after": after, "companies": len(todo), "read": 0, "changed_dossiers": 0, "changes": [], "written": 0,
                 "last": None, "more": len(pending) > len(todo), "backup": None, "error": None}
    at = now_iso()

    def work(scrip: str):
        try:
            read = sink.get_dossier(scrip)
            if read is None:
                return scrip, None, None, None
            merged = json.loads(json.dumps(read))
            return scrip, read, merged, corrections(merged)
        except Exception as exc:  # noqa: BLE001 - reported in order below, where it stops the run
            return scrip, None, None, exc

    for start in range(0, len(todo), SAVE_EVERY):
        chunk = todo[start:start + SAVE_EVERY]
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(work, chunk))
        for scrip, read, merged, changes in results:
            if isinstance(changes, Exception):
                out["error"] = f"{scrip}, reading: {type(changes).__name__}: {changes}"[:300]
                log.error("statements-correct stopped at %s while reading: %s", scrip, changes)
                break
            out["read"] += 1
            if changes:
                out["changed_dossiers"] += 1
                out["changes"] += [{"scrip": scrip, **c} for c in changes]
                if apply:
                    stage = "saving the backup"
                    try:
                        keep_concurrent_writes(merged, read, sink.get_dossier(scrip))
                        backup.dossier(scrip, merged)
                        stage = "writing"
                        sink.put_dossier(scrip, merged)
                        out["written"] += 1
                    except Exception as exc:  # noqa: BLE001 - BackupError or an outage: nothing more is written
                        out["error"] = f"{scrip}, {stage}: {type(exc).__name__}: {exc}"[:300]
                        log.error("statements-correct stopped at %s while %s: %s", scrip, stage, exc)
                        break
            out["last"] = scrip
        if out["error"]:
            break
        if apply and not named and out["last"]:
            sink.kv_set(RESUME_KEY, out["last"], at)   # saved chunk by chunk: a stopped run resumes here
    if apply and not named and not out["error"] and not out["more"]:
        sink.kv_set(RESUME_KEY, "", at)   # everything done: the next run starts from the first company
    if backup is not None:
        out["backup"] = backup.summary()
    return out


def render(o: dict) -> str:
    rows = {(c["scrip"], c["period"], c["basis"], c["table"]) for c in o["changes"]}
    lines = [f"Profit-line rules over the stored statements ({'applied' if o['apply'] else 'dry run, nothing written'}): "
             f"{o['read']} of {o['companies']} companies read after '{o['after']}', {len(rows)} entries in {o['changed_dossiers']} dossiers "
             f"{'corrected' if o['apply'] else 'to correct'} ({len(o['changes'])} rows), {o['written']} dossiers written; last {o['last']}; more left: {o['more']}"]
    lines += [f"    {c['scrip']} {c['period']} {c['basis']} {c['table']} {c['row']}: {c['old']} -> {c['new']}" for c in o["changes"][:80]]
    if len(o["changes"]) > 80:
        lines.append(f"    ... {len(o['changes']) - 80} more in the JSON and the CSV")
    if o["backup"]:
        lines.append(f"backup: {o['backup']['prefix']} ({o['backup']['dossiers']} dossiers); undo with restore --backup "
                     f"{o['backup']['prefix']} --scrips <scrip> [--apply]")
    if o["error"]:
        lines.append(f"stopped: {o['error']}")
    return "\n".join(lines)


def to_csv(o: dict) -> str:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["scrip", "period", "basis", "table", "row", "old", "new"])
    for c in o["changes"]:
        w.writerow([c["scrip"], c["period"], c["basis"], c["table"], c["row"], c["old"], c["new"]])
    return buf.getvalue()
