"""Re-rank stored figures under TODO 118 B (29 Oct 2026): a live filing's figure the XBRL reader built (labelled ``file``
or ``calc``) now outranks a model's later reading (``dossier._metric_entry``). New writes follow the rule; this job puts the
stored figures the rule changes right. No AI, no exchange.

``memory-rerank`` is a dry run unless ``--apply``. It touches a stored figure only when all three hold: it has two or more
sources, its stored value is the one the old rule gives (so a figure some other writer or rule set is left alone), and the new
rule gives another value. That figure is rebuilt from its own sources as ``memory_drop`` rebuilds one; nothing else in the
dossier changes. Measured over stored memory on 29 Oct: 128 figures in 46 companies, each an AI reading beaten by the file.

At most ``limit`` figures a run (the owner's rule A, 50): companies are taken in scrip order and a company whose changes would
pass the limit waits for the next run, so a company is never half done (one with more than ``limit`` goes alone, first). Before any write each dossier is saved through
``backup.RunBackup`` (as stored, and as about to be written, read back): ``restore`` undoes it. Any failure of a read, the backup
or a write stops the run; the report of what was done so far is still returned.

What it does not do: recompute the changes (yoy, qoq) other stored figures carry against a corrected one; a re-read does that."""

from __future__ import annotations

import json
import logging

from .dossier import _metric_entry, _sources, keep_concurrent_writes

log = logging.getLogger(__name__)
LIMIT = 50


def _old_value(entry: dict, sources: list[dict]):
    """The value under the rule before 118 B: the labels are what the new rule reads, so without them it is the old one."""
    return _metric_entry(entry["metric"], entry["period"], [{k: v for k, v in s.items() if k != "lab"} for s in sources])["value"]


def rerank(dossier: dict) -> list[dict]:
    """Rebuild in place the figures of ``dossier`` the new rule changes; returns one row per figure changed."""
    rows, out = [], []
    for entry in dossier.get("financial_metrics", []):
        sources = _sources(entry) if isinstance(entry, dict) else []
        if len(sources) < 2 or entry.get("value") != _old_value(entry, sources):
            rows.append(entry)
            continue
        new = _metric_entry(entry["metric"], entry["period"], sources)
        if new["value"] == entry["value"]:
            rows.append(entry)
            continue
        out.append({"metric": entry["metric"], "period": entry["period"], "old": entry["value"], "new": new["value"],
                    "from": new.get("value_news_id"), "was_from": entry.get("value_news_id")})
        rows.append(new)
    dossier["financial_metrics"] = rows
    return out


def run(sink, scrips: list[str], apply: bool = False, limit: int = LIMIT) -> dict:
    from .backup import RunBackup

    backup = RunBackup(sink, "memory-rerank") if apply else None
    out = {"apply": apply, "limit": limit, "companies_read": 0, "figures": 0, "dossiers_written": 0, "rows": [],
           "waiting": [], "backup": None, "error": None}
    for scrip in sorted(scrips):
        stage = "reading the dossier"
        try:
            read = sink.get_dossier(scrip)
            out["companies_read"] += 1
            if read is None:
                continue
            merged = json.loads(json.dumps(read))
            changed = rerank(merged)
            if not changed:
                continue
            if out["figures"] and out["figures"] + len(changed) > limit:   # a company over the limit alone still goes, alone
                out["waiting"].append(scrip)
                continue
            if apply:
                stage = "saving the backup"
                keep_concurrent_writes(merged, read, sink.get_dossier(scrip))
                backup.dossier(scrip, merged)
                stage = "writing the dossier"
                sink.put_dossier(scrip, merged)
                out["dossiers_written"] += 1
            out["figures"] += len(changed)
            out["rows"] += [{"scrip": scrip, **r} for r in changed]
        except Exception as exc:   # noqa: BLE001 - BackupError or an outage of the store: nothing more is written
            out["error"] = f"{scrip}, {stage}: {type(exc).__name__}: {exc}"[:300]
            log.error("memory-rerank stopped at %s while %s: %s", scrip, stage, exc)
            break
    if backup is not None:
        out["backup"] = backup.summary()
    return out


def render(outcome: dict) -> str:
    verb = "corrected" if outcome["apply"] else "would correct"
    lines = [f"Memory re-rank, TODO 118 B ({'applied' if outcome['apply'] else 'dry run, nothing written'}), "
             f"{outcome['companies_read']} companies read:"]
    for r in outcome["rows"]:
        lines.append(f"  {r['scrip']} {r['metric']} {r['period']}: {r['old']} -> {r['new']} (from {r['from']}, was {r['was_from']})")
    lines.append(f"  {outcome['figures']} figures {verb} in {len({r['scrip'] for r in outcome['rows']})} companies "
                 f"(limit {outcome['limit']}); {len(outcome['waiting'])} companies wait for the next run")
    if outcome["backup"]:
        lines.append(f"backup: {outcome['backup']['prefix']} ({outcome['backup']['dossiers']} dossiers); undo with "
                     f"restore --backup {outcome['backup']['prefix']} --scrips <scrip> [--apply]")
    if outcome["error"]:
        lines.append(f"stopped, nothing more written: {outcome['error']}")
    return "\n".join(lines)
