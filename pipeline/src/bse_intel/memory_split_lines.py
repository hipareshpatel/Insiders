"""Split the operating figures memory kept under one key although two business lines reported them (METRIC_BUSINESS_LINE, owner
1 Nov 2026). EICHERMOT's APR-2026 "volumes" held Royal Enfield's 113,164 with VECV's 7,318 only under ``sources``. No AI, no exchange.

``memory-split-lines`` is a dry run unless ``--apply``. For each company it reads each source filing's stored card (headline and
card headline, ``export_cards``) and the names memory knows (``business_line.known_lines``: lines already stored, segments,
subsidiaries, JVs and brands of the identity), takes the line a filing's text names when it names exactly one, then splits an
operating figure whose sources come from different lines, one entry a line, and (once a company shows two or more readable
lines) tags the figures whose sources share one. A line it cannot read is never invented: those sources stay as the whole
company's figure. Statement lines are never touched; a company with one readable line is left as it is. The switch need not be
on to run it (the rows stay harmless until it is). Each dossier is backed up first (``backup.RunBackup``); ``restore`` undoes it.
Any failure of a read, the backup or a write stops the run; the report so far is still returned."""

from __future__ import annotations

import json
import logging

from . import business_line
from .dossier import keep_concurrent_writes

log = logging.getLogger(__name__)
PAGE = 200


def _cards(sink, scrips: set[str]) -> dict[str, list[dict]]:
    """The stored cards of these companies by scrip (export_cards pages)."""
    out: dict[str, list[dict]] = {}
    after = ["", ""]
    while True:
        rows = sink.query("export_cards", [after[0], after[1], PAGE])
        if not rows:
            return out
        after = [rows[-1]["filed_at"], rows[-1]["news_id"]]
        for row in rows:
            if row["scrip_code"] in scrips:
                out.setdefault(row["scrip_code"], []).append(row)


def run(sink, scrips: list[str], apply: bool = False) -> dict:
    from .backup import RunBackup

    backup = RunBackup(sink, "memory-split-lines") if apply else None
    out = {"apply": apply, "companies_read": 0, "figures": 0, "dossiers_written": 0, "rows": [], "lines": {}, "unread": {},
           "backup": None, "error": None}
    try:
        cards = _cards(sink, set(scrips))
    except Exception as exc:   # noqa: BLE001
        out["error"] = f"reading the cards: {type(exc).__name__}: {exc}"[:300]
        return out
    for scrip in sorted(scrips):
        stage = "reading the dossier"
        try:
            read = sink.get_dossier(scrip)
            out["companies_read"] += 1
            if read is None:
                continue
            merged = json.loads(json.dumps(read))
            lines = business_line.card_lines(cards.get(scrip, []), merged)
            changed = business_line.repair(merged, lines)
            if not changed:
                continue
            out["lines"][scrip] = sorted({p["line"] for r in changed for p in r["into"] if p["line"]})
            out["unread"][scrip] = sum(1 for r in changed for p in r["into"] if not p["line"])
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
            log.error("memory-split-lines stopped at %s while %s: %s", scrip, stage, exc)
            break
    if backup is not None:
        out["backup"] = backup.summary()
    return out


def render(outcome: dict) -> str:
    verb = "split" if outcome["apply"] else "would split"
    lines = [f"Memory split by business line, METRIC_BUSINESS_LINE ({'applied' if outcome['apply'] else 'dry run, nothing written'}), "
             f"{outcome['companies_read']} companies read:"]
    for r in outcome["rows"]:
        into = "; ".join(f"{p['line'] or '(no line)'} {p['value']:g} from {p['from']}" for p in r["into"] if p["value"] is not None)
        was = f"{r['was']:g}" if r["was"] is not None else "-"
        lines.append(f"  {r['scrip']} {r['metric']} {r['period']}: {was} -> {into}")
    lines.append(f"  {outcome['figures']} figures {verb} in {len(outcome['lines'])} companies")
    for scrip, found in outcome["lines"].items():
        lines.append(f"  {scrip}: lines {', '.join(found)}; {outcome['unread'][scrip]} entries kept whole (a filing's line not readable)")
    if outcome["backup"]:
        lines.append(f"backup: {outcome['backup']['prefix']} ({outcome['backup']['dossiers']} dossiers); undo with "
                     f"restore --backup {outcome['backup']['prefix']} --scrips <scrip> [--apply]")
    if outcome["error"]:
        lines.append(f"stopped, nothing more written: {outcome['error']}")
    return "\n".join(lines)
