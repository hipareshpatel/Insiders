"""Take the figures on the known-wrong list (known_wrong.py) out of the stored dossiers (F223, 28 Oct 2026). No AI, no exchange.

``memory-drop-known-wrong`` is a dry run unless ``--apply``. It removes exactly the listed figures: a source of a stored figure
goes only when its metric, period, basis and VALUE are the listed ones, so a later correct figure for the same key stays, and
a figure of another basis stays. A stored figure with several sources keeps the others and is rebuilt from them as
``dossier._forget`` rebuilds one (the value of the latest machine-tagged source that remains). The company's standalone block
is read for a STANDALONE entry.

Before any write each company's dossier is saved through ``backup.RunBackup`` (the dossier as stored, and the one about to be
written, read back before the write goes ahead): ``restore`` puts it back, keeping what any later writer stored. A backup that
does not read back stops the run before that company is written.

What it does not do: write the right figure (the list keeps it as evidence; a right figure comes from a re-read of a corrected
file or from the owner's two-source rule, never from here), or recompute the changes (yoy, qoq) other stored figures carry
against the dropped one; a re-read of the company does that."""

from __future__ import annotations

import json

from . import known_wrong as kw
from .dossier import STANDALONE_KEY, _metric_entry, _sources, keep_concurrent_writes


def _source_basis(entry: dict, source: dict) -> str | None:
    return source.get("basis") or entry.get("basis") or (source.get("lab") or {}).get("basis")


def _hit(wrong: kw.KnownWrong, entry: dict, source: dict) -> bool:
    return kw.same_value(source.get("value"), wrong.wrong) and kw.basis_fits(wrong, _source_basis(entry, source))


def drop_figure(dossier: dict, wrong: kw.KnownWrong) -> dict:
    """Take one listed figure out of ``dossier`` (in place). Returns {"found", "dropped", "kept"}: the stored sources whose
    key matched (value or not), the ones removed, and the values of those that did not match the listed value."""
    report = {"found": 0, "dropped": 0, "kept": []}
    rows = []
    for entry in dossier.get("financial_metrics", []):
        if not (isinstance(entry, dict) and kw.norm_metric(entry.get("metric")) == wrong.metric and entry.get("period") == wrong.period):
            rows.append(entry)
            continue
        sources = _sources(entry)
        keep = [s for s in sources if not _hit(wrong, entry, s)]
        report["found"] += len(sources)
        report["dropped"] += len(sources) - len(keep)
        report["kept"] += [s.get("value") for s in keep if s.get("value") is not None and kw.basis_fits(wrong, _source_basis(entry, s))]
        if len(keep) == len(sources):
            rows.append(entry)
        elif keep:
            rows.append(_metric_entry(entry["metric"], entry["period"], keep))
    dossier["financial_metrics"] = rows
    if wrong.basis in ("", "STANDALONE"):
        part = dossier.get(STANDALONE_KEY)
        if isinstance(part, dict):
            kept_rows = []
            for entry in part.get("metrics", []):
                if isinstance(entry, dict) and kw.norm_metric(entry.get("metric")) == wrong.metric and entry.get("period") == wrong.period:
                    report["found"] += 1
                    if kw.same_value(entry.get("value"), wrong.wrong):
                        report["dropped"] += 1
                        continue
                    report["kept"].append(entry.get("value"))
                kept_rows.append(entry)
            part["metrics"] = kept_rows
    return report


def _row(wrong: kw.KnownWrong, report: dict | None, apply: bool) -> dict:
    status = "no dossier" if report is None else "dropped" if report["dropped"] and apply else "would drop" if report["dropped"] \
        else "other value kept" if report["kept"] else "not in memory"
    return {"scrip": wrong.scrip, "basis": wrong.basis, "period": wrong.period, "metric": wrong.metric, "wrong": wrong.wrong,
            "right": wrong.right, "status": status, "sources_dropped": report["dropped"] if report else 0,
            "values_kept": report["kept"] if report else []}


def run(sink, scrips=None, apply: bool = False, entries: dict | None = None) -> dict:
    """The drop over the listed companies (or the named ones among them). A dry run reads and reports; with ``apply`` each
    changed dossier is backed up, then written through the three-way merge."""
    from .backup import BackupError, RunBackup

    table = kw.BY_SCRIP if entries is None else entries
    names = sorted(table)
    unknown = sorted(set(scrips or ()) - set(names))
    if scrips:
        names = [s for s in names if s in set(scrips)]
    backup = RunBackup(sink, "memory-drop-known-wrong") if apply else None
    out = {"apply": apply, "rows": [], "dossiers_written": 0, "unknown": unknown, "backup": None, "error": None}
    for scrip in names:
        read = sink.get_dossier(scrip)
        if read is None:
            out["rows"] += [_row(w, None, apply) for w in kw.for_scrip(scrip, table)]
            continue
        merged = json.loads(json.dumps(read))
        reports = [(w, drop_figure(merged, w)) for w in kw.for_scrip(scrip, table)]
        changed = merged != read
        if apply and changed:
            try:
                keep_concurrent_writes(merged, read, sink.get_dossier(scrip))
                backup.dossier(scrip, merged)   # the dossier as stored (once) and the one about to be written, read back
            except BackupError as exc:   # nothing more is written
                out["error"] = f"{type(exc).__name__}: {exc}"[:300]
                out["rows"] += [{**_row(w, r, False), "status": "not written (backup failed)"} for w, r in reports]
                break
            sink.put_dossier(scrip, merged)
            out["dossiers_written"] += 1
        out["rows"] += [_row(w, r, apply and changed) for w, r in reports]
    if backup is not None:
        out["backup"] = backup.summary()
    return out


def render(outcome: dict) -> str:
    lines = [f"Known-wrong figures in memory ({'applied' if outcome['apply'] else 'dry run, nothing written'}):"]
    for r in outcome["rows"]:
        lines.append(f"  {r['scrip']} {r['basis'] or 'any basis'} {r['period']} {r['metric']} {r['wrong']:g} "
                     f"(statement {r['right'] if r['right'] is not None else 'unknown'}): {r['status']}"
                     + (f"; memory also holds {r['values_kept']}" if r["values_kept"] else ""))
    counts: dict[str, int] = {}
    for r in outcome["rows"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    lines.append("  " + (", ".join(f"{n} {s}" for s, n in sorted(counts.items())) or "nothing listed"))
    if outcome["unknown"]:
        lines.append("  not on the list: " + ", ".join(outcome["unknown"]))
    if outcome["backup"]:
        lines.append(f"backup: {outcome['backup']['prefix']} ({outcome['backup']['dossiers']} dossiers); undo with "
                     f"restore --backup {outcome['backup']['prefix']} --scrips <scrip> [--apply]")
    if outcome["error"]:
        lines.append(f"stopped, nothing more written: {outcome['error']}")
    return "\n".join(lines)
