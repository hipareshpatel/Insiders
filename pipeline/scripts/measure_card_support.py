"""Offline measure of the CARD_TEXT_SUPPORT checks (card_support.py) over blind-reviewed cards. Read-only.

Input: folders with, per filing, text.txt and cards.json ({"X": card, "Y": card}), and a verdict.json beside them (a list of
{"news_id", "X": {"wrong": [...]}, "Y": {...}}), as the blind fact-sheet rounds of 30 Oct 2026 wrote them.

    PYTHONPATH=src python scripts/measure_card_support.py DIR [DIR ...] [--show]

Reports the items the checks drop, split into those a reviewer marked WRONG (MARKS below, written by hand from the verdicts,
in scope = classes a, b, c of docs/audit/prompt-audit-2026-10-30.md) and the unmarked ones (likely true content lost).
IN-SAMPLE: the stoplist and threshold were tuned on these same 34 cards.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from bse_intel import card_support
from bse_intel.models import Card, Pass2Output

# (news_id, side or "*", field of the drop, substring of the dropped item's text): the in-scope WRONG items
MARKS = [
    ("nse-106834137", "X", "why_it_matters", "Dalmia"),
    ("nse-106834149", "X", "what_happened", "discontinued"),
    ("nse-106834149", "X", "key_numbers", "discontinued"),
    ("nse-106834149", "Y", "key_numbers", "discontinued"),
    ("nse-106834149", "Y", "what_happened", "discontinued"),
    ("nse-106834184", "X", "notable_changes", "Unit 7"),
    ("nse-106834360", "X", "core_catalyst", "passenger"),
    ("nse-106834360", "X", "why_it_matters", "capacity"),
    ("nse-106834441", "X", "track_next", "inventory"),
    ("nse-106834441", "X", "track_next", "price correction"),
    ("nse-106834441", "Y", "track_next", "pass through"),
    ("nse-106832942", "*", "track_next", "Merino"),
    ("nse-106833840", "X", "track_next", "MSEDCL"),
    ("nse-106834074", "X", "key_numbers", "profit"),
    ("nse-106834074", "X", "track_next", "concall"),
    ("nse-106834074", "X", "track_next", "MCA"),
    ("nse-106834074", "Y", "key_numbers", "profit"),
    ("nse-106834691", "X", "core_catalyst", "AUM"),
    ("nse-106835036", "Y", "track_next", "USFDA"),
    ("nse-106835036", "Y", "track_next", "approvals"),
    ("nse-106835060", "*", "track_next", "October 30"),
]
MARKS = [(a, side, c, d) for a, b, c, d in MARKS for side in (("X", "Y") if b == "*" else (b,))]
# the (c) label class also reaches results.pat/headline text built by code; counted in the report, not in MARKS
CLASSES = {"a": ("Dalmia", "Merino", "MSEDCL", "AUM", "passenger", "capacity", "Unit 7", "USFDA", "MCA", "inventory",
                 "price correction", "pass through", "approvals"),
           "b": ("concall", "October 30"),
           "c": ("discontinued", "profit")}


def _items(card: Card):
    """(field, text) of every item the checks may drop."""
    t = card.track_next
    for name in ("pending_approvals", "catalysts", "risks"):
        for x in getattr(t, name):
            yield "track_next", x
    for m in t.milestones:
        yield "track_next", f"{m.what} {m.when or ''}".strip()
    if card.core_catalyst:
        yield "core_catalyst", card.core_catalyst
    for c in card.notable_changes:
        if c.why:
            yield "notable_changes", c.why
    for i in card.why_it_matters:
        yield "why_it_matters", i.text
    for f in card.what_happened:
        yield "what_happened", f.text
    for k in card.key_numbers:
        yield "key_numbers", f"{k.label} {k.value} {k.change or ''}".strip()


def _blocks(cards: dict) -> str:
    """Stand-in for the blocks the model is given besides the filing text (the XBRL table, memory, scale), which the
    fixture folders do not hold: the quotes of both cards that are not in the PDF text came from them, and the card's own
    `results` labels are the XBRL table's. Memory itself is absent: only MEMORY insights WITH ids are exempt from the
    check, and the fixtures' memory words are what the in-sample tuning has to guess."""
    parts = []
    for side in ("X", "Y"):
        c = cards[side]
        parts.append(json.dumps(c.get("results", {}), ensure_ascii=False))
        for line in (c.get("results") or {}).get("lines", []):
            parts.append(" ".join(str(line.get(k) or "") for k in ("key", "label", "note", "quote")))
        for f in c.get("what_happened", []):
            parts.append(str(f.get("quote") or ""))
        for k in c.get("key_numbers", []):
            parts.append(str(k.get("quote") or ""))
        for i in c.get("why_it_matters", []):
            parts.append(str(i.get("quote") or ""))
            if i.get("basis") == "MEMORY":
                parts.append(i.get("text", ""))   # memory itself is not in the fixtures: a MEMORY point is its own proxy
        for n in c.get("notable_changes", []):
            parts.append(str(n.get("quote") or ""))
    return "\n".join(parts)


def _kind(field: str, text: str) -> str:
    for cls, words in CLASSES.items():
        if any(w.lower() in text.lower() for w in words):
            return cls
    return "?"


def run(dirs: list[Path], show: bool) -> dict:
    marks_hit, marked_total, unmarked, details = set(), len(MARKS), [], []
    cards_n = items_n = 0
    for d in dirs:
        for folder in sorted(p for p in d.iterdir() if p.is_dir()):
            text = (folder / "text.txt").read_text(errors="replace")
            cards = json.loads((folder / "cards.json").read_text())
            for side in ("X", "Y"):
                raw = cards[side]
                card = Card.model_validate(raw)
                cards_n += 1
                before = set(_items(card))
                items_n += len(list(_items(card)))
                out = Pass2Output(is_material=True, card=card, timeline_entry="x")
                sources = (text, "", "", _blocks(cards), "")
                notes = card_support.apply(out, sources, text)   # labels: the document alone (production passes filed_text)
                after = list(_items(out.card))
                after_set = set(after)
                gone = [i for i in _items(Card.model_validate(raw)) if i not in after_set]
                # a notable_changes why is blanked, not removed: it shows as gone too
                for field, t in gone:
                    hit = [m for m in MARKS if m[0] == folder.name and m[1] == side and m[2] == field
                           and m[3].lower() in t.lower()]
                    if hit:
                        marks_hit.add(hit[0])
                    else:
                        unmarked.append((folder.name, side, field, t))
                    details.append((folder.name, side, field, t, bool(hit)))
                if show:
                    for n in notes:
                        print(f"  {folder.name} {side}: {n}")
    wrong_dropped = len(marks_hit)
    by_class = {}
    for m in marks_hit:
        by_class[_kind(m[2], m[3])] = by_class.get(_kind(m[2], m[3]), 0) + 1
    return {"cards": cards_n, "items": items_n, "marked_items": marked_total, "marked_dropped": wrong_dropped,
            "by_class": by_class, "unmarked_dropped": len(unmarked), "unmarked": unmarked,
            "missed": [m for m in MARKS if m not in marks_hit]}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    result = run([Path(a) for a in args], "--show" in sys.argv)
    print(f"cards {result['cards']}, droppable items {result['items']}")
    print(f"WRONG marks hit {result['marked_dropped']} of {result['marked_items']} in-scope marks; by class {result['by_class']}")
    print(f"unmarked items dropped: {result['unmarked_dropped']}")
    for u in result["unmarked"]:
        print("   UNMARKED", u)
    for m in result["missed"]:
        print("   MISSED", m)
