"""Held cards published without the points their quote did not carry (owner, 2026-10-21: "Needs review · 475 · 20
re-runs queued", cards stored but never published because no one can read them all by hand).

A card held only because some of its points quote a sentence the filing does not have, or state a figure their own quote
does not carry, is published without those points; everything left on it passed every check. New cards get this as they
are made (pipeline.prune_quote_failures); `release-pruned` applies the same rule to the cards already held. Measured
before it was built: of the 108 such cards the 20 Oct hand review read, 77 were right, 20 minor and 11 wrong (10%),
against 11 wrong of 48 published cards in the 21 Oct audit (23%). A card held for anything else (a figure not found,
a sum, a scale, a claim, a garbled scan, the owner's Wrong) stays held. No AI."""

from __future__ import annotations

import json
import logging
import re

from .pipeline import _QUOTE_FACT, _QUOTE_POINT

log = logging.getLogger(__name__)

PREFIX = "Give each fact the filing's own sentence as its quote: "
PUBLISHED_STATUSES = ("UNRESOLVED", "UNCHECKED")


def prune_card(card: dict, statuses: tuple[str, ...] = ("UNRESOLVED",)) -> list[str] | None:
    """Drop, in place, the points a held card's issues name; None when an issue is not of this kind, the card's last
    fact would go, or the card is held for a reason of its own. A published card may also be UNCHECKED (published
    without a second opinion, the flagged ones of 22 Oct 2026): pruning it only takes points off the public site."""
    review = card.get("review") or {}
    issues = review.get("issues") or []
    if review.get("status") not in statuses or review.get("held") or not issues:
        return None
    dropped, taken = [], []
    for issue in issues:
        if not issue.startswith(PREFIX):
            return None
        problem = issue[len(PREFIX):]
        if problem.startswith("dropped: "):
            continue
        point, fact = _QUOTE_POINT.match(problem), _QUOTE_FACT.match(problem)
        if point:
            kind, label = point.group(1), point.group(2)
            field, key = {"key number": ("key_numbers", lambda x: x.get("label") or ""),
                          "notable change": ("notable_changes", lambda x: x.get("metric") or ""),
                          "why it matters": ("why_it_matters", lambda x: (x.get("text") or "")[:48])}[kind]
            items = card.get(field) or []
            kept = [x for x in items if not (isinstance(x, dict) and key(x) == label)]
            if len(kept) == len(items):
                return None
            taken += [_text(kind, x) for x in items if x not in kept]
            card[field] = kept
        elif fact:
            items = card.get("what_happened") or []
            text = lambda x: (x.get("text") if isinstance(x, dict) else str(x)).replace("**", "")[:60]
            kept = [x for x in items if text(x) != fact.group(1)]
            if not 0 < len(kept) < len(items):
                return None
            taken += [x.get("text") if isinstance(x, dict) else str(x) for x in items if x not in kept]
            card["what_happened"] = kept
        else:
            return None
        dropped.append(problem)
    card["review"] = {**review, "status": "PRUNED", "pruned": dropped}
    # behind the tap "Facts the checks could not quote", not deleted (owner, 24 Oct 2026; pipeline.prune_quote_failures)
    card["unchecked"] = list(dict.fromkeys([*(card.get("unchecked") or []), *(t for t in taken if t)])) or None
    return dropped


def _text(kind: str, item: dict) -> str:
    """A pruned key number, notable change or insight as one line (pipeline._point_text)."""
    if kind == "why it matters":
        return item.get("text") or ""
    if kind == "key number":
        label, value = item.get("label"), item.get("value")
    else:
        label, value = item.get("metric"), " → ".join(str(x) for x in (item.get("previous"), item.get("current")) if x)
    text = ": ".join(str(x) for x in (label, value) if x)
    return f"{text} ({item['change']})" if item.get("change") else text


GROUNDING_CLASSES = ("ungrounded", "math_mismatches", "unsupported_claims", "out_of_fit", "call_figure_conflicts")
_DIGITS = re.compile(r"[\d.,]+")


def fault_classes(card: dict) -> list[str]:
    """What keeps a card held or flagged, by class: the checks' grounding keys that are not empty, the owner's hold,
    and each review issue with its figures and quoted text taken out (so like issues count together)."""
    review, grounding = card.get("review") or {}, card.get("grounding") or {}
    out = [key for key in GROUNDING_CLASSES if grounding.get(key)]
    if review.get("held"):
        out.append("owner: " + str(review["held"])[:40])
    for issue in review.get("issues") or []:
        text = issue[len(PREFIX):] if issue.startswith(PREFIX) else issue
        text = re.sub(r'"[^"]*"', '"…"', _DIGITS.sub("N", text))
        out.append(text[:70])
    return out or ["no fault recorded"]


def breakdown(cards: list[tuple[dict, dict]], top: int = 25) -> list[dict]:
    """The commonest fault classes over (row, card) pairs, each with its count and three example cards."""
    tally: dict[str, list[str]] = {}
    for row, card in cards:
        for name in dict.fromkeys(fault_classes(card)):
            tally.setdefault(name, []).append(f"{row.get('symbol') or row['scrip_code']} {row['news_id']}")
    ranked = sorted(tally.items(), key=lambda kv: -len(kv[1]))[:top]
    return [{"class": name, "cards": len(ids), "examples": ids[:3]} for name, ids in ranked]


def _results_quarter(card: dict) -> str | None:
    return (card.get("results") or {}).get("period") if card.get("event_type") == "RESULTS" else None


def _superseded(owned: dict, scrip: str, quarter: str, card: dict) -> bool:
    """A published card owns the quarter, unless the held one is consolidated and the published one is not: the
    consolidated card is the better one, and stays in the review queue (hourly audit, 22 Oct 2026)."""
    bases = owned.get((scrip, quarter))
    if bases is None:
        return False
    return not (card.get("basis") == "CONSOLIDATED" and "CONSOLIDATED" not in bases)


def _stored(sink) -> list[tuple[dict, dict]]:
    after, rows = ["", ""], []
    while True:
        page = sink.query("export_cards", [after[0], after[1], 100])
        if not page:
            break
        after = [page[-1]["filed_at"], page[-1]["news_id"]]
        rows += page
        if len(page) < 100:
            break
    return [(r, json.loads(r["card_json"] or "{}")) for r in rows]


def release(sink, dry_run: bool = False) -> dict:
    """Every held card that pruning releases, written (or only counted with ``dry_run``)."""
    cards = _stored(sink)
    # a published card already owns its results quarter (D20): a held one for the same quarter stays held
    owned: dict[tuple[str, str], set] = {}
    for r, c in cards:
        if not r.get("held") and _results_quarter(c):
            owned.setdefault((r["scrip_code"], _results_quarter(c)), set()).add(c.get("basis"))
    out, skipped, writes, kept = [], {"other faults": 0, "quarter has a card": 0}, [], []
    for row, card in cards:
        if not row.get("held"):
            continue
        quarter = _results_quarter(card)
        if quarter and _superseded(owned, row["scrip_code"], quarter, card):
            skipped["quarter has a card"] += 1
            continue
        if quarter and (row["scrip_code"], quarter) in owned:
            # consolidated behind a published standalone card: never published beside it (D20), kept for review
            skipped["consolidated behind a standalone card"] = skipped.get("consolidated behind a standalone card", 0) + 1
            kept.append((row, card))
            continue
        dropped = prune_card(json.loads(json.dumps(card)))
        if dropped is None:
            skipped["other faults"] += 1
            kept.append((row, card))
            continue
        prune_card(card)
        if quarter:
            owned.setdefault((row["scrip_code"], quarter), set()).add(card.get("basis"))
        out.append({"news_id": row["news_id"], "symbol": row.get("symbol"), "dropped": len(dropped)})
        writes.append({"news_id": row["news_id"], "card_json": json.dumps(card, ensure_ascii=False)})
    # a published card flagged for review only for points its quote does not carry loses those points too: they are on
    # the public site now (21 of the 61 flagged on 22 Oct 2026 had a key number its own quote does not carry)
    flagged = []
    for row, card in cards:
        if row.get("held") or not row.get("needs_review"):
            continue
        dropped = prune_card(json.loads(json.dumps(card)), PUBLISHED_STATUSES)
        if dropped is None:
            flagged.append((row, card))
            continue
        prune_card(card, PUBLISHED_STATUSES)
        out.append({"news_id": row["news_id"], "symbol": row.get("symbol"), "dropped": len(dropped), "published": True})
        writes.append({"news_id": row["news_id"], "card_json": json.dumps(card, ensure_ascii=False)})
    written = 0 if dry_run or not writes else sink.execute("cards_release_pruned", writes)
    log.info("release-pruned: %d released, %s", len(out), skipped)
    return {"released": len(out), "rows_written": written, "dry_run": dry_run, "kept_held": skipped,
            "kept_why": breakdown(kept), "flagged_published": len(flagged), "flagged_why": breakdown(flagged),
            "cards": out, "rerun_ids": [r["news_id"] for r, _ in kept + flagged]}


# A reviewed release (owner, 22 Oct 2026: "Release the 100 cards, then the 108 with their named points removed, through
# the existing release path. No stored data is edited by hand."): a plan file in docs/audit/live names each card a blind
# review read against its PDF, and the whole points to take off it. Only whole list items go, never words in a sentence;
# each named item must still read as the reviewer saw it, so a card re-run since the review is left alone.
_PATH = re.compile(r"^(?:(track_next)\.)?(\w+)(?:\[(\d+)\])?$")
_DROPPABLE = ("what_happened", "why_it_matters", "key_numbers", "notable_changes", "quantified_impact", "signals",
              "missing_disclosures")


def _item_text(item) -> str:
    if isinstance(item, dict):
        return str(item.get("text") or item.get("label") or item.get("metric") or item.get("type") or item.get("value") or "")
    return str(item)


def drop_named(card: dict, drops: list[dict]) -> list[str] | None:
    """Take, in place, each named whole item off a card; None (card untouched) when a path is not a whole item, an item
    no longer reads as ``expect``, or the card's last fact would go."""
    work = json.loads(json.dumps(card))
    lists: dict[tuple, list] = {}
    gone: list[tuple[tuple, int | str]] = []
    for drop in drops:
        m = _PATH.match(drop.get("path") or "")
        if not m:
            return None
        nested, field, index = m.group(1), m.group(2), m.group(3)
        expect = (drop.get("expect") or "").replace("**", "").strip()
        if nested:
            items = (work.get("track_next") or {}).get(field)
        elif field in _DROPPABLE:
            items = work.get(field)
        else:
            return None   # a headline, takeaway or other sentence is never cut: the card stays held
        if index is None or not isinstance(items, list) or int(index) >= len(items):
            return None
        if expect and not _item_text(items[int(index)]).replace("**", "").startswith(expect[:40]):
            return None
        lists[(nested, field)] = items
        gone.append(((nested, field), int(index)))
    for key, index in sorted(set(gone), key=lambda g: -g[1]):
        del lists[key][index]
    if not work.get("what_happened"):
        return None
    card.clear()
    card.update(work)
    return [f'{d["path"]}: {d.get("expect") or ""}'.rstrip(": ") for d in drops]


def drop_results_lines(card: dict, drops: list[dict]) -> tuple[list[dict], list[str]] | None:
    """Split off ``results.<line>`` drops (a line of the results strip, e.g. results.eps) and take them off."""
    rest, gone = [], []
    for drop in drops:
        path = drop.get("path") or ""
        if path.startswith("results."):
            line = path.split(".", 1)[1]
            if not isinstance((card.get("results") or {}).get(line), dict):
                return None
            gone.append(line)
        else:
            rest.append(drop)
    for line in gone:
        card["results"].pop(line, None)
    return rest, ["results." + g for g in gone]


def release_reviewed(sink, plan: list[dict], reviewed: str, dry_run: bool = False) -> dict:
    """Held or flagged cards a blind review cleared, published (or kept published, unflagged) with the named whole points
    taken off (plan: news_id, action, drops). The D20 rule still holds: a held results card whose quarter a published card owns stays held."""
    cards = {r["news_id"]: (r, c) for r, c in _stored(sink)}
    owned: dict[tuple[str, str], set] = {}
    for r, c in cards.values():
        if not r.get("held") and _results_quarter(c):
            owned.setdefault((r["scrip_code"], _results_quarter(c)), set()).add(c.get("basis"))
    out, kept, writes = [], [], []
    for entry in plan:
        news_id = entry["news_id"]
        if entry.get("action") != "release":
            kept.append({"news_id": news_id, "why": "review: " + str(entry.get("reason") or "keep held")[:120]})
            continue
        if news_id not in cards or not (cards[news_id][0].get("held") or cards[news_id][0].get("needs_review")):
            kept.append({"news_id": news_id, "why": "not held or flagged now"})
            continue
        row, card = cards[news_id]
        quarter = _results_quarter(card) if row.get("held") else None   # a flagged card is already the published one
        if quarter and (row["scrip_code"], quarter) in owned:
            kept.append({"news_id": news_id, "why": "quarter has a card"})
            continue
        work = json.loads(json.dumps(card))
        split = drop_results_lines(work, entry.get("drops") or [])
        dropped = None if split is None else drop_named(work, split[0])
        if dropped is None:
            kept.append({"news_id": news_id, "why": "a named point is not a whole item or no longer reads as reviewed"})
            continue
        review = work.get("review") or {}
        work["review"] = {**review, "status": "PRUNED", "released_by": reviewed,
                          "pruned": [*(review.get("pruned") or []), *split[1], *dropped]}
        if quarter:
            owned.setdefault((row["scrip_code"], quarter), set()).add(work.get("basis"))
        out.append({"news_id": news_id, "symbol": row.get("symbol"), "dropped": len(dropped) + len(split[1])})
        writes.append({"news_id": news_id, "card_json": json.dumps(work, ensure_ascii=False)})
    written = 0 if dry_run or not writes else sink.execute("cards_release_pruned", writes)
    log.info("release-reviewed %s: %d released, %d kept", reviewed, len(out), len(kept))
    return {"released": len(out), "rows_written": written, "dry_run": dry_run, "kept": kept, "cards": out}
