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
