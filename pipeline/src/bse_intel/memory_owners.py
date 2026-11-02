"""Take out of the stored dossiers the owners' profit (``pat_owners``) that no file backs and that its own period's file figures
contradict (lead, 2 Nov 2026; ADANIPORTS Q4FY26: memory's 1,238.67 is the owners' share of other comprehensive income beside the
file's whole profit 3,308.30, and it reached the stock page and the old card face). No AI, no exchange.

A row is dropped only when every one of its sources is labelled ``by="unknown"`` (a source the exchange's file, a calculation or a
model labelled stays, and so does a row with no label at all) and, on the row's basis, the same period's file-labelled figures
contradict it:
* with a file minority share (not zero): owners differ from the file's whole profit less that share beyond rounding;
* with none, or a zero (the template's filler): owners differ from the file's whole profit by more than 2%.
A period with no file-labelled whole profit is never judged.

``memory-owners-drop`` is a dry run unless ``--apply``: the report lists every row it would drop (scrip, period, basis, value and
the file figures it was judged against). With ``--apply`` each changed dossier is backed up first (``backup.RunBackup``,
``backup/memory-owners-drop-<time>/``; ``restore`` puts it back) and written through the three-way merge; any failure of the
read, the backup or the write stops the run (``memory_drop.run``'s rule)."""

from __future__ import annotations

import json
import logging

from .dossier import _sources, keep_concurrent_writes

log = logging.getLogger(__name__)

ROUNDING = 0.05      # ₹ Cr: two figures printed to two places that differ by more than this are two figures
ROUNDING_REL = 0.002
NO_MINORITY_GAP = 0.02   # without a minority share, owners and the whole profit are the same figure within 2%


def _basis(entry: dict, source: dict) -> str:
    return str(source.get("basis") or (source.get("lab") or {}).get("basis") or entry.get("basis")
               or (entry.get("lab") or {}).get("basis") or "").upper()


def _file_value(rows: list[dict], metric: str, period: str, basis: str) -> float | None:
    """The file-labelled value of ``metric`` for ``period`` on ``basis`` (a source with no basis counts for any), or None."""
    for entry in rows:
        if not isinstance(entry, dict) or entry.get("metric") != metric or entry.get("period") != period:
            continue
        for source in _sources(entry):
            lab = source.get("lab") if isinstance(source.get("lab"), dict) else {}
            b = _basis(entry, source)
            if lab.get("by") == "file" and isinstance(source.get("value"), (int, float)) and (not b or not basis or b == basis):
                return float(source["value"])
    return None


def _unknown_only(entry: dict) -> bool:
    sources = _sources(entry)
    return bool(sources) and all(isinstance(s.get("lab"), dict) and s["lab"].get("by") == "unknown" for s in sources)


def suspects(dossier: dict | None) -> list[dict]:
    """Each stored owners' profit the rule drops: {period, basis, value, pat, minority, why}."""
    rows = [m for m in (dossier or {}).get("financial_metrics") or [] if isinstance(m, dict)]
    out = []
    for entry in rows:
        if entry.get("metric") != "pat_owners" or not isinstance(entry.get("value"), (int, float)) or not _unknown_only(entry):
            continue
        period = entry.get("period")
        bases = {_basis(entry, s) for s in _sources(entry)}
        basis = next(iter(bases)) if len(bases) == 1 else ""
        pat = _file_value(rows, "pat", period, basis)
        if pat is None:
            continue
        owners = float(entry["value"])
        minority = _file_value(rows, "pat_minority", period, basis)
        if minority:
            expected = pat - minority
            if abs(owners - expected) <= max(ROUNDING, ROUNDING_REL * abs(expected)):
                continue
            why = f"the file's profit {pat:g} less its minority share {minority:g} is {expected:g}"
        else:
            if abs(owners - pat) <= NO_MINORITY_GAP * abs(pat):
                continue
            why = f"the file's profit {pat:g}, no minority share" + (" (0 in the file)" if minority == 0 else "")
        out.append({"period": period, "basis": basis, "value": owners, "pat": pat, "minority": minority, "why": why})
    return out


def drop(dossier: dict) -> list[dict]:
    """Take the suspect owners' rows out of ``dossier`` in place; the rows taken."""
    found = suspects(dossier)
    gone = {(r["period"], r["value"]) for r in found}
    if gone:
        dossier["financial_metrics"] = [
            m for m in dossier.get("financial_metrics") or []
            if not (isinstance(m, dict) and m.get("metric") == "pat_owners" and isinstance(m.get("value"), (int, float))
                    and (m.get("period"), float(m["value"])) in gone and _unknown_only(m))]
    return found


def run(sink, scrips: list[str], apply: bool = False) -> dict:
    """The pass over ``scrips``: a dry run reads and reports; with ``apply`` each changed dossier is backed up, then written. Any
    failure stops the run at once, and ``error`` says what failed."""
    from .backup import RunBackup

    backup = RunBackup(sink, "memory-owners-drop") if apply else None
    out = {"apply": apply, "companies_read": 0, "rows": [], "dossiers_written": 0, "backup": None, "error": None}
    for scrip in sorted(scrips):
        stage = "reading the dossier"
        try:
            read = sink.get_dossier(scrip)
            out["companies_read"] += 1
            if read is None:
                continue
            merged = json.loads(json.dumps(read))
            dropped = drop(merged)
            if not dropped:
                continue
            if apply:
                stage = "saving the backup"
                keep_concurrent_writes(merged, read, sink.get_dossier(scrip))
                backup.dossier(scrip, merged)
                stage = "writing the dossier"
                sink.put_dossier(scrip, merged)
                out["dossiers_written"] += 1
            symbol = (read.get("symbol") or read.get("nse_symbol") or "") if isinstance(read, dict) else ""
            out["rows"] += [{"scrip": scrip, "symbol": symbol, **r} for r in dropped]
        except Exception as exc:   # noqa: BLE001 - BackupError or an outage of the store: nothing more is written
            out["error"] = f"{scrip}, {stage}: {type(exc).__name__}: {exc}"[:300]
            log.error("memory-owners-drop stopped at %s while %s: %s", scrip, stage, exc)
            break
    if backup is not None:
        out["backup"] = backup.summary()
    return out


def render(outcome: dict) -> str:
    verb = "dropped" if outcome["apply"] else "would drop"
    lines = [f"Owners' profit no file backs ({'applied' if outcome['apply'] else 'dry run, nothing written'}): "
             f"{len(outcome['rows'])} rows {verb}, {outcome['companies_read']} companies read"]
    for r in outcome["rows"]:
        lines.append(f"  {r['scrip']} {r['symbol'] or '-'} {r['period']} {r['basis'] or 'no basis'} pat_owners {r['value']:g}: {r['why']}")
    if outcome["backup"]:
        lines.append(f"backup: {outcome['backup']['prefix']} ({outcome['backup']['dossiers']} dossiers); undo with "
                     f"restore --backup {outcome['backup']['prefix']} --scrips <scrip> [--apply]")
    if outcome["error"]:
        lines.append(f"stopped, nothing more written: {outcome['error']}")
    return "\n".join(lines)
