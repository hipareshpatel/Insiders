"""Summarise independent card audits (docs/AUDIT_LOOP.md): verdicts, error classes and the share of WRONG cards.

Usage: python scripts/audit_tally.py AUDIT_DIR [--save docs/audit/round-N.json]
AUDIT_DIR holds reviewer_NN/findings.json files: [{"news_id", "headline", "verdict": OK|MINOR|WRONG,
"issues": [{"field", "card_says", "pdf_says", "class"}]}]. Run with `python -I -X utf8`.
"""
import argparse
import collections
import glob
import json
import pathlib


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audit_dir")
    ap.add_argument("--save")
    args = ap.parse_args()
    cards = []
    for path in sorted(glob.glob(str(pathlib.Path(args.audit_dir) / "*" / "findings.json"))):
        cards += json.load(open(path, encoding="utf-8"))
    verdicts = collections.Counter(c.get("verdict") for c in cards)
    classes = collections.Counter(i.get("class") for c in cards for i in c.get("issues") or [])
    n = max(len(cards), 1)
    print(f"{len(cards)} cards: " + ", ".join(f"{k} {v} ({v / n:.0%})" for k, v in verdicts.most_common()))
    print("issues by class:", ", ".join(f"{k} {v}" for k, v in classes.most_common()))
    models = {}
    for path in glob.glob(str(pathlib.Path(args.audit_dir) / "*" / "*.card.json")):
        card = json.load(open(path, encoding="utf-8"))
        models[card["_filing"]["news_id"]] = str(card.get("model") or "?").split("/", 1)[-1]
    manifest = pathlib.Path(args.audit_dir) / "manifest.json"   # a blind export keeps the model out of the cards
    held = set()
    if manifest.exists():
        for news_id, row in json.load(open(manifest, encoding="utf-8")).items():
            if models.get(news_id, "?") == "?":
                models[news_id] = str(row.get("model") or "?").split("/", 1)[-1]
            if row.get("held"):
                held.add(news_id)
    if held:  # held cards are mixed in blind (round 2): the pass mark is on the published ones
        for name, group in (("published", [c for c in cards if c["news_id"] not in held]),
                            ("held", [c for c in cards if c["news_id"] in held])):
            v = collections.Counter(c.get("verdict") for c in group)
            k = max(len(group), 1)
            print(f"  {name}: {len(group)} cards: " + ", ".join(f"{x} {y} ({y / k:.0%})" for x, y in v.most_common()))
    # Audit round 2: memory points and impact levels are judged too, and reported apart so the WRONG share stays
    # comparable with round 1 (which judged neither)
    memory_only = [c for c in cards if c.get("verdict") == "WRONG"
                   and all(i.get("class") == "memory" for i in c.get("issues") or [])]
    if any(i.get("class") == "memory" for c in cards for i in c.get("issues") or []):
        print(f"memory points wrong on {sum(any(i.get('class') == 'memory' for i in c.get('issues') or []) for c in cards)} "
              f"cards; WRONG only for memory on {len(memory_only)}")
    impact = collections.Counter(str(c.get("impact_ok")) for c in cards if "impact_ok" in c)
    if impact:
        print("impact level fits:", ", ".join(f"{k} {v}" for k, v in impact.most_common()))
    if models:  # which model wrote the card: the weights in providers.toml follow this table
        by_model = collections.defaultdict(lambda: collections.Counter())
        issues_by_model = collections.Counter()
        for c in cards:
            m = models.get(c["news_id"], "?")
            by_model[m][c.get("verdict")] += 1
            issues_by_model[m] += len(c.get("issues") or [])
        print("by writer model:")
        for m, v in sorted(by_model.items(), key=lambda kv: -sum(kv[1].values())):
            n = sum(v.values())
            print(f"  {m[:46]:46} {n:>4} cards  WRONG {v['WRONG'] / n:>4.0%}  OK {v['OK'] / n:>4.0%}  {issues_by_model[m] / n:.1f} issues a card")
    worst = sorted((c for c in cards if c.get("verdict") == "WRONG"), key=lambda c: -len(c.get("issues") or []))[:8]
    for c in worst:
        print(f"  {c['news_id'][:8]} {len(c['issues']):>2} issues  {str(c.get('headline'))[:80]}")
    if args.save:
        pathlib.Path(args.save).write_text(json.dumps(cards, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
