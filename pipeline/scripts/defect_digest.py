"""What the code's own checks flagged, grouped by error class, so a day's fixing starts from classes.

The 100-card audit (docs/AUDIT_LOOP.md) is the measure of truth, but it costs ten independent reviewers
and cannot run daily. Every card already carries what the checks found - ungrounded numbers, unsupported
claims, a maths mismatch, a dropped quote, a unit the code had to correct, an unresolved second opinion -
and nothing reads it back. This does, with no AI call and no reviewer: counts by class, the writer model
behind each, and a few real cards to open. The order of the list is the order to fix in, because one class
is one change in code (the owner's rule: fix in batches, not card by card).

Usage:
  npx wrangler d1 execute insiders --local --persist-to ../data/wrangler --json --command \
    "SELECT c.news_id, c.scrip_code, c.needs_review, c.grounding_score, f.filed_at, f.route, c.card_json \
     FROM cards c JOIN filings f USING(news_id)" > cards.json
  python -I -X utf8 scripts/defect_digest.py cards.json [--examples 3] [--json out.json]
"""
import argparse
import collections
import difflib
import json
import pathlib
import re


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()).split())


def _day(at: str) -> int:
    try:
        return int(at[:4]) * 372 + int(at[5:7]) * 31 + int(at[8:10])
    except (ValueError, IndexError):
        return 0


def classes(cards: list[dict]) -> dict[str, list[dict]]:
    """Each card filed under every class it trips. A card can appear in several."""
    found: dict[str, list[dict]] = collections.defaultdict(list)
    for row in cards:
        c = row["card"]
        g = c.get("grounding") or {}
        review = c.get("review") or {}
        who = {"news_id": row["news_id"], "scrip": row.get("scrip_code"), "model": c.get("model"),
               "route": row.get("route"), "headline": (c.get("headline") or "")[:90]}
        if review.get("status") == "UNRESOLVED":
            found["second opinion could not resolve it (a flagged error shipped)"].append(who)
        if g.get("unsupported_claims"):
            found["claim not supported by the filing"].append(who | {"detail": g["unsupported_claims"][:2]})
        if g.get("ungrounded"):
            found["number not found in the filing or memory"].append(who | {"detail": g["ungrounded"][:4]})
        if g.get("math_mismatches"):
            found["a stated calculation does not come out"].append(who)
        if g.get("quotes_dropped"):
            found["fact dropped: neither its quote nor its figures are in the filing"].append(
                who | {"detail": g["quotes_dropped"][:2]})
        if g.get("quotes_missing"):
            found["fact carried no quote at all"].append(who)
        if g.get("unit_fixes"):
            found["unit read wrong, corrected in code"].append(who | {"detail": g["unit_fixes"]})
        if g.get("change_fixes"):
            found["change recomputed in code"].append(who | {"detail": g["change_fixes"][:2]})
        if row.get("needs_review") and review.get("status") != "UNRESOLVED":
            found["held for review on its grounding score"].append(who)
    return found


def duplicate_pairs(cards: list[dict], days: int = 30, ratio: float = 0.62) -> list[dict]:
    """Cards of one company, close in time, that read as the same announcement."""
    by: dict[str, list[dict]] = collections.defaultdict(list)
    for row in cards:
        by[row.get("scrip_code")].append(row)
    pairs = []
    for group in by.values():
        group.sort(key=lambda r: r.get("filed_at") or "")
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                gap = abs(_day(b.get("filed_at") or "") - _day(a.get("filed_at") or ""))
                if gap > days:
                    continue
                score = max(
                    difflib.SequenceMatcher(None, _norm(a["card"].get("headline")), _norm(b["card"].get("headline"))).ratio(),
                    difflib.SequenceMatcher(None, _norm(a["card"].get("timeline_entry")), _norm(b["card"].get("timeline_entry"))).ratio())
                if score >= ratio:
                    pairs.append({"score": round(score, 2), "days": gap, "scrip": a.get("scrip_code"),
                                  "kept": a["news_id"], "repeat": b["news_id"], "route": b.get("route"),
                                  "events": [a["card"].get("event_type"), b["card"].get("event_type")],
                                  "headline": (b["card"].get("headline") or "")[:90]})
    return sorted(pairs, key=lambda p: -p["score"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cards_json")
    ap.add_argument("--examples", type=int, default=3)
    ap.add_argument("--json", dest="out_json", help="write the digest as JSON too")
    args = ap.parse_args()
    rows = json.loads(pathlib.Path(args.cards_json).read_text(encoding="utf-8"))[0]["results"]
    cards = [dict(r, card=json.loads(r["card_json"])) for r in rows]
    total = len(cards)
    found = classes(cards)
    pairs = duplicate_pairs(cards)

    print(f"{total} cards\n")
    print(f"{'cards':>6}  {'share':>6}  class")
    print(f"{'-' * 6}  {'-' * 6}  {'-' * 52}")
    for name, hits in sorted(found.items(), key=lambda kv: -len(kv[1])):
        print(f"{len(hits):>6}  {100 * len(hits) / total:>5.0f}%  {name}")
    print(f"{len(pairs):>6}  {100 * len(pairs) / total:>5.0f}%  the same announcement as another card")

    print("\nBy writer model, cards with at least one flag:")
    flagged = collections.Counter()
    for hits in found.values():
        flagged.update({h["news_id"]: 1 for h in hits}.keys())
    per_model = collections.Counter(c["card"].get("model") for c in cards)
    flagged_model = collections.Counter(c["card"].get("model") for c in cards if c["news_id"] in flagged)
    for model, n in per_model.most_common():
        bad = flagged_model[model]
        print(f"  {(model or '?').split('/')[-1]:<34} {bad:>4} of {n:>4}  {100 * bad / n:>3.0f}%")

    for name, hits in sorted(found.items(), key=lambda kv: -len(kv[1])):
        print(f"\n{name} ({len(hits)})")
        for h in hits[:args.examples]:
            detail = f"  {h['detail']}" if h.get("detail") else ""
            print(f"  {h['news_id'][:8]} {h['scrip']} {(h['model'] or '?').split('/')[-1]:<26} {h['headline']}{detail}")
    if pairs:
        print(f"\nthe same announcement as another card ({len(pairs)})")
        for p in pairs[:args.examples]:
            print(f"  [{p['score']}] {p['scrip']} {p['days']}d {p['events'][0]}/{p['events'][1]} "
                  f"{p['repeat'][:8]} ({p['route']}) {p['headline']}")

    if args.out_json:
        pathlib.Path(args.out_json).write_text(json.dumps(
            {"cards": total, "classes": {k: len(v) for k, v in found.items()}, "duplicate_pairs": len(pairs),
             "detail": {k: v[:20] for k, v in found.items()}, "pairs": pairs[:40]},
            indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\nwritten to {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
