"""Round 2 against its re-run: the same 90 filings, verdicts before (docs/audit/round-2.json) and after (the re-run's
findings), by filing and by class.

  python -I -X utf8 scripts/audit_round2/compare_rerun.py RERUN_REVIEW_DIR RERUN_CARDS_JSON

A filing merged into another of the same event is judged on the card that now carries it (`stands_for`); one with no
card now is listed with what became of it.
"""
import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
DOCS = HERE.parents[2] / "docs" / "audit"
review, cards = pathlib.Path(sys.argv[1]), json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
before = {r["news_id"]: r for r in json.loads((DOCS / "round-2.json").read_text(encoding="utf-8"))}
manifest = json.loads((DOCS / "round-2" / "cards-manifest.json").read_text(encoding="utf-8"))
after = {}
for f in review.glob("reviewer_*/findings.json"):
    for r in json.loads(f.read_text(encoding="utf-8")):
        after[r["news_id"]] = r
rows = cards[0]["results"]
now_held = {r["news_id"]: bool(r["held"]) for r in rows}
stands = {r["stands_for"]: r["news_id"] for r in rows if r.get("stands_for")}


def wrong_classes(r):
    return {i["class"] for i in r.get("issues", []) if i["class"] != "memory"} if r and r["verdict"] == "WRONG" else set()


table = []
for nid, b in before.items():
    a = after.get(nid) or after.get(stands.get(nid, ""))
    table.append((nid, b, a, manifest.get(nid, {}).get("held"), now_held.get(nid, now_held.get(stands.get(nid, "")))))

for label, keep in (("published in round 2", lambda h: not h), ("held in round 2", lambda h: h), ("all 90", lambda h: True)):
    sel = [t for t in table if keep(t[3])]
    vb = collections.Counter(t[1]["verdict"] for t in sel)
    va = collections.Counter(t[2]["verdict"] if t[2] else "NO CARD" for t in sel)
    print(f"{label} ({len(sel)}): before {dict(vb)} | after {dict(va)}")

print("\nWRONG cards by class (a card counts once per class; memory tallied apart):")
cb, ca = collections.Counter(), collections.Counter()
for _, b, a, held, _ in table:
    cb.update(wrong_classes(b))
    ca.update(wrong_classes(a))
for c in sorted(set(cb) | set(ca), key=lambda c: -cb[c]):
    print(f"  {c:24} {cb[c]:3} -> {ca[c]:3}")
mb = sum(1 for _, b, *_ in table if any(i["class"] == "memory" for i in b.get("issues", [])))
ma = sum(1 for _, _, a, *_ in table if a and any(i["class"] == "memory" for i in a.get("issues", [])))
print(f"  {'memory (cards)':24} {mb:3} -> {ma:3}")

print("\nverdict moves:")
moves = collections.Counter((b["verdict"], a["verdict"] if a else "NO CARD") for _, b, a, *_ in table)
for (x, y), n in sorted(moves.items()):
    print(f"  {x:6} -> {y:8} {n}")
print("\nWRONG after:")
for nid, b, a, held, nh in table:
    if a and a["verdict"] == "WRONG":
        print(f"  {nid[:8]} (was {b['verdict']}{', held' if held else ''}) {sorted(wrong_classes(a))} {a['headline'][:70]}")
