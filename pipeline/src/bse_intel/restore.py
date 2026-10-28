"""Put a backup (backup.py) back: `python -m bse_intel restore --backup backup/<job>-<time>/ [--scrips A,B] [--news-ids X,Y]`.

A three-way restore. A backup holds each item's state before the job ("before") and as the job wrote it ("after"). The live
pipeline writes memory and cards all day, so a restore hours later must not wipe what it wrote since: for every unit it
compares the stored value ("current") with "after".

* current equals after: nothing has touched it since the job, the "before" value goes back (or the unit is removed, if the
  job added it);
* current differs from after, and the job changed it: it was changed again since, a conflict, left exactly as it is
  (``--force`` puts the "before" value back anyway);
* the job did not change it, or current is already "before": nothing to do.

The unit is never smaller than a whole value. For a dossier it is a top-level section; inside a section that is a keyed list
(metric + period + basis, id, news id, period) or a dict, it is one whole entry, never a field of an entry, so a restore never
writes a part of an entry. A restored entry goes back to its earlier position where it can. ``updated_at`` is ignored (the later
writer's stays). A dossier the job created, or deleted, is one unit: deleted only if it equals what the job wrote exactly,
otherwise left alone as a conflict. A card is compared per column that ``cards_upsert`` can write (the card's JSON as one
column); a column it cannot set back (a price reaction that was NULL) is listed as not restorable.

A backup with no after-state (``after/``: a ``requeue-failed --ids`` snapshot, the first version of the backups) has no way to
tell later writes from the job's. It restores only with ``--force``, and the dry run lists every difference now, which includes
whatever the live pipeline wrote since. The same holds for an after-state that is incomplete (``save_after`` writes
``after/pending.json`` first and ``after/sealed.json`` last; a run that stopped between them leaves the first only). The
after-state a ``seed-memory --scrips`` run takes at its end includes whatever the live pipeline wrote to those companies while
the seed ran, and a restore would treat it as the seed's own: restore soon after such a run, or with care. A dict section is
restored one key at a time (each key a whole value), so a section changed in one key since the job still gets its other keys
back. ``--scrips`` names companies (their dossiers and their cards in the backup);
``--news-ids`` names cards; a name the backup does not hold is an error and nothing is written. With neither, ``--all`` is
required. ``--apply`` first saves the state of each item it is about to replace, with the state it writes, to
backup/restore-<time>/ (page by page, read back), so a restore can itself be undone the same way. Cards go back through
``cards_upsert``, so a standing owner verdict applies on top."""

from __future__ import annotations

import json
import logging

from .backup import AFTER, PREFIX, SCAN, RunBackup, check_prefix

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


def _keyed(rows: list) -> dict | None:
    """The entries of a list by key, or None when some have none or two share one."""
    ids = [_ident(e) for e in rows]
    if None in ids or len(set(ids)) != len(ids):
        return None
    return dict(zip(ids, rows))


def _unit(before, after, current, path: str, m: Merge):
    """One whole value (a section, an entry, a dict section's entry): never looked into. ABSENT is a missing one."""
    if current == after:
        if before != after:
            m.restored.append(path)
        return before
    if before == after or current == before:
        return current
    m.conflicts.append(path)
    return before if m.force else current


def _counts(path: str, before, after) -> str:
    """A section that goes back, named with how many entries of a keyed list the job added, removed or changed."""
    rows_b, rows_a = ([] if before is ABSENT else before), ([] if after is ABSENT else after)
    if isinstance(rows_b, list) and isinstance(rows_a, list):
        mb, ma = _keyed(rows_b), _keyed(rows_a)
        if mb is not None and ma is not None:
            return (f"{path} (job added {len(ma.keys() - mb.keys())}, removed {len(mb.keys() - ma.keys())}, "
                    f"changed {sum(mb[i] != ma[i] for i in mb.keys() & ma.keys())} entries)")
    return path


def _section(before, after, current, path: str, m: Merge):
    """A top-level section. Whole when nobody changed it since the job; otherwise, if it is a keyed list or a dict, entry by
    entry (each entry a whole unit); any other section changed by both is a conflict."""
    if current == after:
        if before != after:
            m.restored.append(_counts(path, before, after))
        return before
    if before == after or current == before:
        return current
    if isinstance(after, dict) and isinstance(current, dict) and (before is ABSENT or isinstance(before, dict)):
        base = {} if before is ABSENT else before
        out = {}
        for k in [*current, *(k for k in base if k not in current), *(k for k in after if k not in current and k not in base)]:
            v = _unit(base.get(k, ABSENT), after.get(k, ABSENT), current.get(k, ABSENT), f"{path}.{k}", m)
            if v is not ABSENT:
                out[k] = v
        return ABSENT if before is ABSENT and not out else out
    if isinstance(after, list) and isinstance(current, list) and (before is ABSENT or isinstance(before, list)):
        mb, ma, mc = _keyed([] if before is ABSENT else before), _keyed(after), _keyed(current)
        if mb is not None and ma is not None and mc is not None:
            out = []
            for i, e in mc.items():   # the current order; an entry the job changed, or added, is replaced or taken out in place
                v = _unit(mb.get(i, ABSENT), ma.get(i, ABSENT), e, f"{path}[{_label(i)}]", m)
                if v is not ABSENT:
                    out.append(v)
            for at, (i, e) in enumerate(mb.items()):   # the job took this entry out and nobody has put it back: back at its place
                if i not in mc:
                    v = _unit(e, ma.get(i, ABSENT), ABSENT, f"{path}[{_label(i)}]", m)
                    if v is not ABSENT:
                        out.insert(min(at, len(out)), v)
            return ABSENT if before is ABSENT and not out else out
    m.conflicts.append(path)
    return before if m.force else current


def _strip(d):
    return {k: v for k, v in d.items() if k != "updated_at"} if isinstance(d, dict) else d


def _a(x):
    return ABSENT if x is None else x


def _differs(before, current) -> list[str]:
    """Every section that differs between the backup and what is stored now (for a backup with no after-state)."""
    b, c = _strip(_a(before)), _strip(_a(current))
    if b == c:   # also both absent: nothing to put back
        return []
    if not (isinstance(b, dict) and isinstance(c, dict)):
        return ["(dossier absent in the backup)" if b is ABSENT else "(dossier not stored now)" if c is ABSENT else "(whole)"]
    return [_counts(k, b.get(k, ABSENT), c.get(k, ABSENT)) for k in [*b, *(k for k in c if k not in b)]
            if b.get(k, ABSENT) != c.get(k, ABSENT)]


def decide_dossier(before, after, current, has_after: bool, force: bool) -> dict:
    """What a restore does with one dossier (dicts, or None for none stored): ``new`` is what to store (None: delete)."""
    out = {"restored": [], "conflicts": [], "differs": [], "new": current, "changed": False, "needs_force": False}
    if not has_after:
        out["differs"] = _differs(before, current)
        if out["differs"]:
            if not force:
                out["needs_force"] = True
                return out
            out.update(restored=out["differs"], new=before, changed=True)
        return out
    if before is None or after is None or current is None:
        # created or deleted by the job, or gone since: one unit, compared exactly. Deleted only if it is what the job wrote.
        m = Merge(force)
        label = "(dossier created by the job)" if before is None else "(dossier deleted by the job)" if after is None else "(dossier not stored now)"
        new = _unit(_a(before), _a(after), _a(current), label, m)
        new = None if new is ABSENT else new
        out.update(restored=m.restored, conflicts=m.conflicts, new=new, changed=new != current)
        return out
    m = Merge(force)
    b, a, c = _strip(before), _strip(after), _strip(current)
    new = {}
    for k in [*c, *(k for k in b if k not in c), *(k for k in a if k not in c and k not in b)]:
        v = _section(b.get(k, ABSENT), a.get(k, ABSENT), c.get(k, ABSENT), k, m)
        if v is not ABSENT:
            new[k] = v
    if "updated_at" in current:
        new["updated_at"] = current["updated_at"]   # a later writer's stamp stays: the restore is not a new filing
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
    ``cards_upsert`` cannot set back. ``new`` is the row to upsert (None when nothing changes). With no after-state
    (``after`` None) every column that differs now is listed in ``differs`` and goes back only with ``force``."""
    out = {"restored": [], "conflicts": [], "not_restorable": [], "differs": [], "blocks": [], "new": None, "changed": False,
           "needs_force": False, "gone": current is None}
    if current is None:
        return out
    out["not_restorable"] = [c for c in CARD_FIXED if before.get(c) != current.get(c)]
    for col in CARD_COLUMNS:
        b, c = _col(before, col), _col(current, col)
        a = _col(after, col) if after is not None else None
        if c == b:
            continue
        if after is None:
            out["differs"].append(col)
            if not force:
                out["needs_force"] = True
                continue
        else:
            if a == b:
                continue                              # the job did not change this column
            if c != a:
                out["conflicts"].append(col)          # changed again since the job
                if not force:
                    continue
        if col == "post_event_return_json" and before.get(col) is None:
            out["not_restorable"].append(col)         # the upsert keeps the stored reaction over a NULL
            continue
        out["restored"].append(col)
    if "card_json" in out["restored"] or "card_json" in out["differs"]:
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
    held = {"dossiers": {}, "cards": {}, "after_dossiers": {}, "after_cards": {}, "has_after": False, "after_incomplete": False}
    markers = set()
    for key in sink.list_objects(prefix):
        rest = key[len(prefix):]
        after = rest.startswith(AFTER)
        if after:
            held["has_after"] = True
            rest = rest[len(AFTER):]
            if rest in ("pending.json", "sealed.json"):
                markers.add(rest)
        body = sink.get_object(key)
        if body is None:
            raise RuntimeError(f"{key} is listed but cannot be read")
        if rest.startswith("memory/") and rest.endswith(".json"):
            held["after_dossiers" if after else "dossiers"][rest[len("memory/"):-len(".json")]] = json.loads(body)
        elif rest.startswith("cards/"):
            for row in json.loads(body)["rows"]:
                held["after_cards" if after else "cards"].setdefault(row["news_id"], row)
    if "pending.json" in markers and "sealed.json" not in markers:
        # save_after began and did not finish: some items have no after-file, which must not read as "the job left it alone"
        held["has_after"], held["after_incomplete"] = False, True
    return held


def plan(sink, prefix: str, scrips: set[str] | None = None, news_ids: set[str] | None = None, everything: bool = False,
         force: bool = False) -> dict:
    """The dry-run report (pure reads): each selected dossier and card, with what a restore would do."""
    prefix = check_prefix(sink, prefix)
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
        memory.append({"scrip_code": scrip, "after_incomplete": held["after_incomplete"],
                       **{k: d[k] for k in ("restored", "conflicts", "differs", "changed", "needs_force")}})
    current = _current_cards(sink, cards)
    rows = []
    for news_id in sorted(cards, key=lambda n: (cards[n]["filed_at"], n)):
        d = decide_card(cards[news_id], held["after_cards"].get(news_id, cards[news_id]) if held["has_after"] else None,
                        current.get(news_id), force)
        rows.append({"news_id": news_id, "scrip_code": cards[news_id]["scrip_code"], "after_incomplete": held["after_incomplete"],
                     **{k: d[k] for k in ("restored", "conflicts", "differs", "not_restorable", "blocks", "changed", "needs_force",
                                          "gone")}})
    return {"backup": prefix, "force": force, "has_after": held["has_after"], "memory": memory, "cards": rows,
            "unknown": unknown, "to_restore": {"memory": sum(m["changed"] for m in memory), "cards": sum(c["changed"] for c in rows)},
            "_held": held}


def _say(item: dict) -> str:
    if item.get("gone"):
        return "not stored now (not restored)"
    parts = []
    if item["needs_force"]:
        parts.append(("the after-state of this backup is incomplete (the run that saved it stopped)" if item.get("after_incomplete")
                      else "no after-state in this backup") + ", so a restore needs --force; differences now (these include "
                     "anything written since the job): " + ", ".join(item["differs"]))
    if item["changed"]:
        parts.append("will restore: " + ", ".join(item["restored"]) +
                     (f" (card blocks now different: {', '.join(item['blocks'])})" if item.get("blocks") else ""))
    if item["conflicts"]:
        parts.append(("forced over later changes: " if item["changed"] and set(item["conflicts"]) <= set(item["restored"])
                      else "conflict (changed since the job, left alone): ") + ", ".join(item["conflicts"]))
    if item.get("not_restorable"):
        parts.append("not restorable: " + ", ".join(item["not_restorable"]))
    return "; ".join(parts) or "already as before (or not changed by the job)"


def render(report: dict) -> str:
    t = report["to_restore"]
    lines = [f"backup {report['backup']}: {len(report['memory'])} dossiers and {len(report['cards'])} cards selected; "
             f"{t['memory']} dossiers and {t['cards']} cards would be put back"
             + ("" if report["has_after"] else " (after-state incomplete: --force needed)" if report["_held"]["after_incomplete"]
                else " (no after-state: --force needed)") + (" (--force)" if report["force"] else "")]
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
