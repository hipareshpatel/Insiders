"""Put a backup (backup.py) back: `python -m bse_intel restore --backup backup/<job>-<time>/ [--scrips A,B] [--news-ids X,Y]`.

A dry run by default: for each company and card the backup holds, whether the stored version differs now and in which
parts. With ``--apply`` it first saves the current state of exactly the objects and rows it is about to replace to its own
backup folder (backup/restore-<time>/, read back, page by page before each write), so a restore can itself be undone, and then
writes the backup's versions. Only items that differ are written.

What is restored: ``--scrips`` names companies (their dossiers and their cards in the backup); ``--news-ids`` names cards.
With neither, ``--all`` is required. A dossier the backup records as absent (``null``) is deleted again.
Cards go back through ``cards_upsert``, so a standing owner verdict (card_verdicts) is applied on top, as for any write."""

from __future__ import annotations

import json
import logging

from .backup import PREFIX, RunBackup

log = logging.getLogger(__name__)

PAGE = 50   # cards written (and backed up) at a time, as card_refresh
SCAN = 100


def list_backups(sink) -> list[dict]:
    """Every folder under backup/ with what it holds; a single-file backup (prune-companies) is listed as such."""
    found: dict[str, dict] = {}
    for key in sink.list_objects(PREFIX):
        rest = key[len(PREFIX):]
        name, _, inner = rest.partition("/")
        entry = found.setdefault(name, {"backup": f"{PREFIX}{name}/" if inner else key, "dossiers": 0, "card_parts": 0,
                                        "restorable": bool(inner)})
        entry["dossiers"] += inner.startswith("memory/")
        entry["card_parts"] += inner.startswith("cards/")
    return [found[n] for n in sorted(found)]


def _load(sink, prefix: str, scrips: set[str] | None, news_ids: set[str] | None, everything: bool):
    """The backup's selected dossiers (scrip -> dossier or None) and cards (news_id -> stored row, the first part's wins)."""
    dossiers: dict[str, dict | None] = {}
    cards: dict[str, dict] = {}
    for key in sink.list_objects(prefix):
        rest = key[len(prefix):]
        body = sink.get_object(key)
        if body is None:
            raise RuntimeError(f"{key} is listed but cannot be read")
        if rest.startswith("memory/") and rest.endswith(".json"):
            scrip = rest[len("memory/"):-len(".json")]
            if everything or scrip in (scrips or ()):
                dossiers[scrip] = json.loads(body)
        elif rest.startswith("cards/"):
            for row in json.loads(body)["rows"]:
                if everything or row["news_id"] in (news_ids or ()) or row["scrip_code"] in (scrips or ()):
                    cards.setdefault(row["news_id"], row)
    return dossiers, cards


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


def _parts_differing(old: dict, new: dict) -> list[str]:
    return sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))


def _card_diff(backed: dict, now: dict | None) -> list[str] | None:
    """None: the card is no longer stored. [] : the same. Else the columns, and the card's blocks, that differ."""
    if now is None:
        return None
    columns = sorted(k for k in set(backed) | set(now) if k != "card_json" and backed.get(k) != now.get(k))
    old, cur = json.loads(backed["card_json"]), json.loads(now["card_json"])
    return columns + [f"card.{k}" for k in _parts_differing(old, cur)]


def plan(sink, prefix: str, scrips: set[str] | None = None, news_ids: set[str] | None = None, everything: bool = False) -> dict:
    """The dry-run report (pure reads): each selected dossier and card, with what differs now."""
    if not prefix.startswith(PREFIX):
        raise ValueError(f"a backup prefix starts with {PREFIX}")
    prefix = prefix.rstrip("/") + "/"
    if not (scrips or news_ids or everything):
        raise ValueError("name what to restore (--scrips, --news-ids) or pass --all")
    dossiers, cards = _load(sink, prefix, scrips, news_ids, everything)   # the _ keys of the report hold them for apply
    memory = []
    for scrip in sorted(dossiers):
        now = sink.get_dossier(scrip)
        backed = dossiers[scrip]
        diff = [] if now == backed else (["stored now, none in the backup"] if backed is None else
                ["not stored now"] if now is None else _parts_differing(backed, now))
        memory.append({"scrip_code": scrip, "differs": diff})
    current = _current_cards(sink, cards)
    rows = []
    for news_id in sorted(cards, key=lambda n: (cards[n]["filed_at"], n)):
        diff = _card_diff(cards[news_id], current.get(news_id))
        rows.append({"news_id": news_id, "scrip_code": cards[news_id]["scrip_code"], "differs": diff})
    return {"backup": prefix, "memory": memory, "cards": rows,
            "to_restore": {"memory": sum(bool(m["differs"]) for m in memory),
                           "cards": sum(bool(c["differs"]) for c in rows if c["differs"] is not None)},
            "cards_not_stored": [c["news_id"] for c in rows if c["differs"] is None],
            "_dossiers": dossiers, "_cards": cards}


def render(report: dict) -> str:
    t = report["to_restore"]
    lines = [f"backup {report['backup']}: {len(report['memory'])} dossiers and {len(report['cards'])} cards selected; "
             f"{t['memory']} dossiers and {t['cards']} cards differ now"]
    for m in report["memory"]:
        lines.append(f"  memory {m['scrip_code']}: " + (", ".join(m["differs"]) if m["differs"] else "same as now"))
    for c in report["cards"]:
        what = "not stored now (not restored)" if c["differs"] is None else (", ".join(c["differs"]) or "same as now")
        lines.append(f"  card {c['news_id']} ({c['scrip_code']}): {what}")
    return "\n".join(lines)


def apply(sink, report: dict) -> dict:
    """Back up what is about to be replaced, then put the backup's versions back; same-as-now items are left alone."""
    undo = RunBackup(sink, "restore")
    written = {"memory": 0, "cards": 0}
    for m in report["memory"]:
        if not m["differs"]:
            continue
        scrip = m["scrip_code"]
        undo.dossier(scrip)   # raises when it does not read back: nothing is written
        backed = report["_dossiers"][scrip]
        if backed is None:
            sink.delete_object(f"memory/{scrip}.json")
        else:
            sink.put_dossier(scrip, backed)
        written["memory"] += 1
    todo = [c["news_id"] for c in report["cards"] if c["differs"]]
    current = _current_cards(sink, {n: report["_cards"][n] for n in todo})   # read again: the undo saves the rows as they are now
    todo = [n for n in todo if n in current]
    for at in range(0, len(todo), PAGE):
        ids = todo[at:at + PAGE]
        undo.cards([current[n] for n in ids])
        rows = []
        for n in ids:
            row = dict(report["_cards"][n])
            row["card"] = json.loads(row.pop("card_json"))
            rows.append(row)
        sink.execute("cards_upsert", rows)
        written["cards"] += len(ids)
    log.info("restore: %d dossiers and %d cards put back from %s, undo backup %s", written["memory"], written["cards"],
             report["backup"], (undo.summary() or {}).get("prefix"))
    return {**written, "undo_backup": (undo.summary() or {}).get("prefix")}
