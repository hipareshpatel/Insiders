"""F156: how many quoted lines fail the stricter number match (QUOTE_EXACT_NUMBERS=1) that passed the old one.

Usage: python -I -X utf8 scripts/audit_quote_exact.py CARDS.json OUT.json
CARDS.json is the list of feed rows (public /api/feed?range=all, each with card_json). No filing text is read: each
claim is checked against its own quote (what the gate sees when the scale block and same-table paths do not apply),
with the unit left to the quote, so this is an upper bound on the lines that would fail first; the lead blind-checks them."""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from bse_intel import gate


def lines(k):
    for f in ("what_happened", "why_it_matters", "missing_disclosures"):
        for p in k.get(f) or []:
            if isinstance(p, dict) and p.get("quote"):
                yield f, p.get("text") or "", p["quote"]
    for n in k.get("key_numbers") or []:
        if n.get("quote"):
            yield "key_numbers", " ".join(str(x) for x in (n.get("label"), n.get("value"), n.get("change")) if x), n["quote"]
    for c in k.get("notable_changes") or []:
        if c.get("quote"):
            yield "notable_changes", f"{c.get('previous') or ''} {c.get('current') or ''}", c["quote"]


def main(src, dst):
    rows = json.load(open(src, encoding="utf-8"))
    total = failing = cards_hit = 0
    out = []
    for r in rows:
        try:
            k = json.loads(r["card_json"])
        except Exception:
            continue
        hit = False
        for field, claim, quote in lines(k):
            total += 1
            os.environ["QUOTE_EXACT_NUMBERS"] = "0"
            old = gate.numbers_in_quote(claim, quote)
            os.environ["QUOTE_EXACT_NUMBERS"] = "1"
            new = gate.numbers_in_quote(claim, quote)
            if set(new) - set(old):
                failing += 1
                hit = True
                out.append({"news_id": r["news_id"], "symbol": r.get("symbol"), "field": field, "claim": claim,
                            "quote": quote, "newly_missing": sorted(set(new) - set(old)), "old_missing": old})
        cards_hit += hit
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"cards": len(rows), "quoted_lines": total, "newly_failing_lines": failing, "cards_with_one": cards_hit}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
