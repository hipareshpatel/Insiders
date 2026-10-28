"""Put a backup (backup.py) back: `python -m bse_intel restore --backup backup/<job>-<time>/ [--scrips A,B] [--news-ids X,Y]`.

A three-way restore. A backup holds each item's state before the job ("before") and as the job wrote it ("after"). The live
pipeline writes memory and cards all day, so a restore hours later must not wipe what it wrote since: for every part of an
item it compares the stored value ("current") with "after".

* current equals after: nothing has touched it since the job, the "before" value goes back;
* current differs from after, and the job changed it: it was changed again since, a conflict, left alone (``--force`` puts the
  "before" value back anyway);
* the job did not change it, or current is already "before": nothing to do.

A dossier is compared by top-level section, and inside a section by entry where entries have a stable key (metric and period,
id, news id, period; ``updated_at`` is ignored), and by field inside an entry. A dossier that did not exist before the job is
deleted only when nothing changed it since; otherwise only the job's own entries are taken out. A card is compared per
column that ``cards_upsert`` can write (the card's JSON as one column); a column it cannot set back (a price reaction that
was NULL) is listed as not restorable.

A backup with no after-state (``after/``) has no way to tell later writes from the job's: it restores only with ``--force``;
``--seal`` records the current state of a ``start_scope`` backup as its after-state once the work (the live run re-reading
named filings) is done.

``--scrips`` names companies (their dossiers and their cards in the backup); ``--news-ids`` names cards; a name the backup does
not hold is an error and nothing is written. With neither, ``--all`` is required. ``--apply`` first saves the state of each
item it is about to replace, with the state it writes, to backup/restore-<time>/ (page by page, read back), so a restore can
itself be undone the same way. Cards go back through ``cards_upsert``, so a standing owner verdict applies on top."""

from __future__ import annotations

import json
import logging

from .backup import AFTER, PREFIX, SCAN, RunBackup, card_after_row

log = logging.getLogger(__name__)

PAGE = 50   # cards written (and backed up) at a time, as card_refresh


class _Absent:
    def __repr__(self) -> str:
        return "<absent>"


ABSENT = _Absent()

# the columns cards_upsert rewrites on an existing card; the others identify the card and are never changed
CARD_COLUMNS = ("symbol", "company_name", "sector", "event_category", "impact_level", "headline", "grounding_score",
                "needs_review", "memory_complete", "card_json", "pdf_url", "model", "created_at", "market_session",
                "actionability_score", "is_actionable_signal", "held", "post_event_return_json")
CARD_FIXED = ("news_id", "scrip_code", "filing_date", "filed_at")


def list_backups(sink) -> list[dict]:
    """Every folder under backup/ with what it holds; a single-file backup (prune-companies) is listed as such."""
    found: dict[str, dict] = {}
    for key in sink.list_objects(PREFIX):
        rest = key[len(PREFIX):]
        name, _, inner = rest.partition("/")
        entry = found.setdefault(name, {"backup": f"{PREFIX}{name}/" if inner else key, "dossiers": 0, "card_parts": 0,
                                        "after_state": False, "restorable": bool(inner)})
        entry["dossiers"] += inner.startswith("memory/")
        entry["card_parts"] += inner.startswith("cards/")
        entry["after_state"] |= inner.startswith(AFTER)
    return [found[n] for n in sorted(found)]


# --- the three-way comparison of a dossier -------------------------------------------------------------------------

class Merge:
    def __init__(self, force: bool):
        self.force, self.restored, self.conflicts = force, [], []


def _ident(entry):
    """What tells a list entry apart from its neighbours: None when it has no stable key."""
    if not isinstance(entry, dict):
        return None
    if "metric" in entry and "period" in entry:
        return ("metric", str(entry["metric"]), str(entry["period"]), str(entry.get("basis")))
    for names in (("id",), ("news_id", "date", "summary"), ("news_id", "date", "text"), ("period",), ("news_id",), ("as_of",)):
        if all(entry.get(n) is not None for n in names):
            return (*names, *(json.dumps(entry[n], sort_keys=True) for n in names))
    return None


def _label(ident) -> str:
    return " ".join(p for p in ident[1:] if p != "None") if ident[0] == "metric" else str(ident[-1]).strip('"')


def _describe(before, after, path: str) -> list[str]:
    """What a part that goes back as a whole is called in the report: at the root, each section the job changed, with how many
    entries of a keyed list it added, removed or changed."""
    if path:
        return [path]
    if before is ABSENT:
        return ["(dossier created by the job)"]
    if not (isinstance(before, dict) and isinstance(after, dict)):
        return ["(whole)"]
    out = []
    for k in [*after, *(k for k in before if k not in after)]:
        b, a = before.get(k, ABSENT), after.get(k, ABSENT)
        if b == a:
            continue
        rows_b, rows_a = ([] if b is ABSENT else b), ([] if a is ABSENT else a)
        if isinstance(rows_b, list) and isinstance(rows_a, list):
            ids_b, ids_a = [_ident(e) for e in rows_b], [_ident(e) for e in rows_a]
            if None not in ids_b + ids_a and len(set(ids_b)) == len(ids_b) and len(set(ids_a)) == len(ids_a):
                mb, ma = dict(zip(ids_b, rows_b)), dict(zip(ids_a, rows_a))
                out.append(f"{k} (job added {len(ma.keys() - mb.keys())}, removed {len(mb.keys() - ma.keys())}, "
                           f"changed {sum(mb[i] != ma[i] for i in mb.keys() & ma.keys())} entries)")
                continue
        out.append(k)
    return out or ["(whole)"]


def merge3(before, after, current, path: str, m: Merge):
    """The value to store: ``before`` where ``current`` is still ``after``, ``current`` where it changed since (a conflict,
    unless the job changed nothing there). ABSENT stands for a missing key or entry."""
    if current == after:
        if before != after:
            m.restored.extend(_describe(before, after, path))
        return before
    if before == after or current == before:
        return current
    # the job changed this part and so did a later writer: go a level down where there is a level to go to
    if isinstance(after, dict) and isinstance(current, dict) and (before is ABSENT or isinstance(before, dict)):
        base = {} if before is ABSENT else before
        keys = list(current) + [k for k in base if k not in current] + [k for k in after if k not in current and k not in base]
        out = {}
        for k in keys:
            v = merge3(base.get(k, ABSENT), after.get(k, ABSENT), current.get(k, ABSENT), f"{path}.{k}" if path else k, m)
            if v is not ABSENT:
                out[k] = v
        return ABSENT if before is ABSENT and not out else out
    if isinstance(after, list) and isinstance(current, list) and (before is ABSENT or isinstance(before, list)):
        maps = []
        for rows in ([] if before is ABSENT else before, after, current):
            ids = [_ident(e) for e in rows]
            if None in ids or len(set(ids)) != len(ids):
                maps = None
                break
            maps.append(dict(zip(ids, rows)))
        if maps is not None:
            mb, ma, mc = maps
            out = []
            for i, e in mc.items():
                v = merge3(mb.get(i, ABSENT), ma.get(i, ABSENT), e, f"{path}[{_label(i)}]", m)
                if v is not ABSENT:
                    out.append(v)
            for i, e in mb.items():   # the job took this entry out and nobody has put it back: it goes back
                if i not in mc:
                    v = merge3(e, ma.get(i, ABSENT), ABSENT, f"{path}[{_label(i)}]", m)
                    if v is not ABSENT:
                        out.append(v)
            return ABSENT if before is ABSENT and not out else out
    m.conflicts.append(path or "(whole)")
    return before if m.force else current


def _strip(d):
    return {k: v for k, v in d.items() if k != "updated_at"} if isinstance(d, dict) else d


def _a(x):
    return ABSENT if x is None else x


def decide_dossier(before, after, current, has_after: bool, force: bool) -> dict:
    """What a restore does with one dossier (dicts, or None for none stored): ``new`` is what to store (None: delete)."""
    out = {"restored": [], "conflicts": [], "new": current, "changed": False, "needs_force": False}
    b, c = _strip(_a(before)), _strip(_a(current))
    if not has_after:
        if c != b:
            if not force:
                out["needs_force"] = True
                return out
            out.update(restored=["(whole dossier, no after-state)"], new=before, changed=True)
        return out
    m = Merge(force)
    new = merge3(b, _strip(_a(after)), c, "", m)
    if isinstance(new, dict) and isinstance(current, dict) and "updated_at" in current:
        new["updated_at"] = current["updated_at"]   # a later writer's stamp stays: the restore is not a new filing
    new = None if new is ABSENT else new
    out.update(restored=m.restored, conflicts=m.conflicts, new=new, changed=new != current)
    return out


# --- a card, column by column ----------------------------------------------------------------------------------------

def _col(row: dict, col: str):
    value = row.get(col)
    if col in ("card_json", "post_event_return_json") and isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def decide_card(before: dict, after: dict | None, current: dict | None, force: bool) -> dict:
    """What a restore does with one card row: the columns that go back, the ones changed since the job (conflicts), the ones
    ``cards_upsert`` cannot set back. ``new`` is the row to upsert (None when nothing changes)."""
    out = {"restored": [], "conflicts": [], "not_restorable": [], "new": None, "changed": False, "needs_force": False,
           "gone": current is None}
    if current is None:
        return out
    out["not_restorable"] = [c for c in CARD_FIXED if before.get(c) != current.get(c)]
    out["blocks"] = []
    for col in CARD_COLUMNS:
        b, c = _col(before, col), _col(current, col)
        a = _col(after, col) if after is not None else None
        if c == b:
            continue
        if after is not None and a == b:
            continue                                  # the job did not change this column
        if after is not None and c != a:
            out["conflicts"].append(col)              # changed again since the job
            if not force:
                continue
        elif after is None and not force:
            out["needs_force"] = True
            continue
        if col == "post_event_return_json" and before.get(col) is None:
            out["not_restorable"].append(col)         # the upsert keeps the stored reaction over a NULL
            continue
        out["restored"].append(col)
    if out["needs_force"]:
        out["restored"] = []
    if "card_json" in out["restored"]:
        old, new = _col(before, "card_json"), _col(current, "card_json")
        if isinstance(old, dict) and isinstance(new, dict):
            out["blocks"] = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))   # which blocks of the card differ now
    if out["restored"]:
        row = dict(current)
        for col in out["restored"]:
            row[col] = before.get(col)
        out["new"], out["changed"] = row, True
    return out


def _upsert_row(row: dict) -> dict:
    out = {k: v for k, v in row.items() if k != "card_json"}
    out["card"] = json.loads(row["card_json"])
    return out


def _current_cards(sink, wanted: dict[str, dict]) -> dict[str, dict]:
    """The stored rows of the wanted cards, read by keyset from the earliest wanted filed_at to the latest."""
    if not wanted:
        return {}
    keys = sorted((r["filed_at"], r["news_id"]) for r in wanted.values())
    after, last = [keys[0][0], ""], keys[-1]
    now: dict[str, dict] = {}
    while True:
        rows = sink.query("export_cards", [after[0], after[1], SCAN])
        for row in rows:
            if (row["filed_at"], row["news_id"]) > last:
                return now
            if row["news_id"] in wanted:
                now[row["news_id"]] = row
        if len(rows) < SCAN:
            return now
        after = [rows[-1]["filed_at"], rows[-1]["news_id"]]


# --- plan and apply ----------------------------------------------------------------------------------------------------

def _load(sink, prefix: str) -> dict:
    """Everything the backup holds: before and after dossiers (scrip -> dossier or None) and card rows (news_id -> row)."""
    held = {"dossiers": {}, "cards": {}, "after_dossiers": {}, "after_cards": {}, "has_after": False}
    for key in sink.list_objects(prefix):
        rest = key[len(prefix):]
        after = rest.startswith(AFTER)
        if after:
            held["has_after"] = True
            rest = rest[len(AFTER):]
        body = sink.get_object(key)
        if body is None:
            raise RuntimeError(f"{key} is listed but cannot be read")
        if rest.startswith("memory/") and rest.endswith(".json"):
            held["after_dossiers" if after else "dossiers"][rest[len("memory/"):-len(".json")]] = json.loads(body)
        elif rest.startswith("cards/"):
            for row in json.loads(body)["rows"]:
                held["after_cards" if after else "cards"].setdefault(row["news_id"], row)
    return held


def plan(sink, prefix: str, scrips: set[str] | None = None, news_ids: set[str] | None = None, everything: bool = False,
         force: bool = False) -> dict:
    """The dry-run report (pure reads): each selected dossier and card, with what a restore would do."""
    if not prefix.startswith(PREFIX):
        raise ValueError(f"a backup prefix starts with {PREFIX}")
    prefix = prefix.rstrip("/") + "/"
    scrips, news_ids = set(scrips or ()), set(news_ids or ())
    if not (scrips or news_ids or everything):
        raise ValueError("name what to restore (--scrips, --news-ids) or pass --all")
    held = _load(sink, prefix)
    known_scrips = set(held["dossiers"]) | {r["scrip_code"] for r in held["cards"].values()}
    unknown = sorted(scrips - known_scrips) + sorted(news_ids - set(held["cards"]))
    dossiers = sorted(held["dossiers"] if everything else scrips & set(held["dossiers"]))
    cards = {n: r for n, r in held["cards"].items() if everything or n in news_ids or r["scrip_code"] in scrips}
    memory = []
    for scrip in dossiers:
        d = decide_dossier(held["dossiers"][scrip], held["after_dossiers"].get(scrip, held["dossiers"][scrip]),
                           sink.get_dossier(scrip), held["has_after"], force)
        memory.append({"scrip_code": scrip, **{k: d[k] for k in ("restored", "conflicts", "changed", "needs_force")}})
    current = _current_cards(sink, cards)
    rows = []
    for news_id in sorted(cards, key=lambda n: (cards[n]["filed_at"], n)):
        d = decide_card(cards[news_id], held["after_cards"].get(news_id, cards[news_id]) if held["has_after"] else None,
                        current.get(news_id), force)
        rows.append({"news_id": news_id, "scrip_code": cards[news_id]["scrip_code"],
                     **{k: d[k] for k in ("restored", "conflicts", "not_restorable", "blocks", "changed", "needs_force", "gone")}})
    return {"backup": prefix, "force": force, "has_after": held["has_after"], "memory": memory, "cards": rows,
            "unknown": unknown, "to_restore": {"memory": sum(m["changed"] for m in memory), "cards": sum(c["changed"] for c in rows)},
            "_held": held}


def _say(item: dict) -> str:
    parts = []
    if item["needs_force"]:
        parts.append("no after-state in this backup: cannot tell later writes from the job's, restores only with --force")
    if item.get("gone"):
        return "not stored now (not restored)"
    if item["changed"]:
        parts.append("will restore: " + ", ".join(item["restored"]) +
                     (f" (card blocks now different: {', '.join(item['blocks'])})" if item.get("blocks") else ""))
    if item["conflicts"]:
        parts.append(("forced over later changes: " if item["changed"] and item["restored"] and set(item["conflicts"]) <= set(item["restored"])
                      else "conflict (changed since the job, left alone): ") + ", ".join(item["conflicts"]))
    if item.get("not_restorable"):
        parts.append("not restorable: " + ", ".join(item["not_restorable"]))
    return "; ".join(parts) or "already as before (or not changed by the job)"


def render(report: dict) -> str:
    t = report["to_restore"]
    lines = [f"backup {report['backup']}: {len(report['memory'])} dossiers and {len(report['cards'])} cards selected; "
             f"{t['memory']} dossiers and {t['cards']} cards would be put back"
             + ("" if report["has_after"] else " (no after-state: --force needed)") + (" (--force)" if report["force"] else "")]
    for m in report["memory"]:
        lines.append(f"  memory {m['scrip_code']}: {_say(m)}")
    for c in report["cards"]:
        lines.append(f"  card {c['news_id']} ({c['scrip_code']}): {_say(c)}")
    for name in report["unknown"]:
        lines.append(f"  NOT IN THE BACKUP: {name}")
    return "\n".join(lines)


def apply(sink, report: dict) -> dict:
    """Back up what is about to be replaced (with what replaces it), then put the backup's versions back where the plan
    says so, deciding again on what is stored now. Returns what was done."""
    if report["unknown"]:
        raise ValueError("not in the backup: " + ", ".join(report["unknown"]))
    held, force = report["_held"], report["force"]
    undo = RunBackup(sink, "restore")
    written = {"memory": 0, "cards": 0}
    skipped = {"conflicts": [], "needs_force": []}
    vanished: list[str] = []
    for m in report["memory"]:
        scrip = m["scrip_code"]
        before = held["dossiers"][scrip]
        d = decide_dossier(before, held["after_dossiers"].get(scrip, before), sink.get_dossier(scrip), held["has_after"], force)
        skipped["conflicts"] += [f"memory {scrip}: {c}" for c in d["conflicts"] if not force]
        if d["needs_force"]:
            skipped["needs_force"].append(f"memory {scrip}")
        if not d["changed"]:
            continue
        undo.dossier(scrip, d["new"])   # raises when it does not read back: nothing is written
        if d["new"] is None:
            sink.delete_object(f"memory/{scrip}.json")
        else:
            sink.put_dossier(scrip, d["new"])
        written["memory"] += 1
    wanted = {c["news_id"]: held["cards"][c["news_id"]] for c in report["cards"]}
    current = _current_cards(sink, wanted)   # read again: what is stored now, not what the dry run saw
    todo = []
    for news_id, before in wanted.items():
        d = decide_card(before, held["after_cards"].get(news_id, before) if held["has_after"] else None, current.get(news_id), force)
        if d["gone"]:
            vanished.append(news_id)
        skipped["conflicts"] += [f"card {news_id}: {c}" for c in d["conflicts"] if not force]
        if d["needs_force"]:
            skipped["needs_force"].append(f"card {news_id}")
        if d["changed"]:
            todo.append((news_id, d["new"]))
    for at in range(0, len(todo), PAGE):
        page = todo[at:at + PAGE]
        undo.cards([current[n] for n, _ in page], [row for _, row in page])
        sink.execute("cards_upsert", [_upsert_row(row) for _, row in page])
        written["cards"] += len(page)
    summary = undo.summary() or {}
    log.info("restore: %d dossiers and %d cards put back from %s, undo backup %s", written["memory"], written["cards"],
             report["backup"], summary.get("prefix"))
    return {**written, "vanished": vanished, "left_alone": skipped, "undo_backup": summary.get("prefix")}
