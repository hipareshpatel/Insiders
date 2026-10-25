"""On/off audit of CARD_TWO_PARTS (F152) over stored cards. No AI calls, nothing written to the site.

Off is the card as stored: every line in one list, as the face shows it today. On is the card as the switch would write
it: `two_parts.hide_part2` run over the stored card (each part 2 line that fails the existing figure, quote or claim
checks removed alone), then `two_parts.split_card` sorting what is left into part 1 and part 2. Both come from the same
stored card and the same filing text, so the difference is only the switch. Sources the checks use are rebuilt as the
pipeline gives them: the filing's text, the headline and subject, the company's memory (the public API's dossier, as it
stands now, not as at filing) and no scale block; that makes the hide check a little stricter or looser than the live one
on a figure that came from the scale block or from memory as it then stood (the limit is listed in docs/TRACKER.md F152).

    python -I -X utf8 scripts/audit_two_parts.py OUT_DIR --cards feed_cards.json [--texts TEXT_DIR] [--download]
    python -I -X utf8 scripts/audit_two_parts.py OUT_DIR --api [--limit 200] [--category RESULTS] [--texts TEXT_DIR] [--download]
    options: --seed 152  --sample 20  --site https://insiders.reply-bd3.workers.dev

--cards: a JSON list of feed cards (each with news_id, scrip_code, symbol, filed_at, pdf_url, card_json), or an object with
a "cards" list. --api reads /api/feed pages and each company's memory (/api/companies/<scrip>). --texts: a folder of
<news_id>.txt, the filing's text; with --download a missing one is fetched from the card's PDF (daily_audit/ext.py).
A card with no text is skipped (its quotes cannot be checked).

Output: diff.json (every card), diff.md (the summary the release check reads: lines per part, lines hidden and why,
cards that would no longer be held are not visible offline, see the limits), blind_sample.json and blind_key.json.
The reviewers' prompt is docs/audit/REVIEWER_PROMPT_TWO_PARTS.md."""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "src"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "daily_audit"))
import audit_card_v2 as v2  # noqa: E402  (its feed reader, text fetch and API getter)
from bse_intel import two_parts  # noqa: E402
from bse_intel.grounding import declared_unit  # noqa: E402
from bse_intel.models import Card  # noqa: E402

SITE = v2.SITE
LIST_FIELDS = ("what_happened", "key_numbers", "quantified_impact", "why_it_matters", "notable_changes", "missing_disclosures")


def _text(field: str, item) -> str:
    if isinstance(item, str):
        return item
    if field == "what_happened":
        return item.get("text") or ""
    if field == "key_numbers":
        return f"{item.get('label')}: {item.get('value')}" + (f" ({item['change']})" if item.get("change") else "")
    if field == "quantified_impact":
        return f"{item.get('label')}: {item.get('result')} {item.get('unit') or ''} - {item.get('interpretation') or ''}".strip()
    if field == "why_it_matters":
        return item.get("text") or ""
    if field == "notable_changes":
        return f"{item.get('metric')}: {item.get('previous') or ''} -> {item.get('current') or ''} ({item.get('change') or ''}) {item.get('why') or ''}"
    return str(item)


def stored_lines(card: dict) -> list[dict]:
    """Every line the card carries as one list, in face order: the off rendering."""
    out = [{"field": "headline", "i": 0, "text": card.get("headline") or ""}]
    if card.get("takeaway"):
        out.append({"field": "takeaway", "i": 0, "text": card["takeaway"]})
    if card.get("core_catalyst"):
        out.append({"field": "core_catalyst", "i": 0, "text": card["core_catalyst"]})
    for field in LIST_FIELDS:
        out += [{"field": field, "i": i, "text": _text(field, it)} for i, it in enumerate(card.get(field) or [])]
    return out


def part_lines(card: dict, parts: dict) -> tuple[list[dict], list[dict]]:
    """The two parts of a card as lines (what a reader of the on rendering sees)."""
    by = {(x["field"], x["i"]): x for x in stored_lines(card)}
    part1 = [by[("headline", 0)]]
    for field in ("what_happened", "key_numbers", "quantified_impact"):
        part1 += [by[(field, i)] for i in parts["part1"].get(field, []) if (field, i) in by]
    part1 += [{"field": "block", "i": 0, "text": b} for b in parts["part1"].get("blocks", [])]
    part2 = [by[(f, 0)] for f in ("takeaway", "core_catalyst") if parts["part2"].get(f) and (f, 0) in by]
    for field in ("why_it_matters", "notable_changes", "what_happened", "key_numbers", "quantified_impact", "missing_disclosures"):
        part2 += [by[(field, i)] for i in parts["part2"].get(field, []) if (field, i) in by]
    part2 += [{"field": "block", "i": 0, "text": b} for b in parts["part2"].get("blocks", [])]
    return part1, part2


def render_on(card: dict, dossier: dict, row: dict, text: str) -> dict:
    """hide_part2, then split_card, over a copy of the stored card."""
    work = json.loads(json.dumps(card))
    model = Card.model_validate({k: work[k] for k in Card.model_fields if k in work})
    sources = (text, row.get("headline") or card.get("headline") or "", row.get("subject") or "", json.dumps(dossier, ensure_ascii=False), "")
    hidden = two_parts.hide_part2(model, sources, text=text, reading="", known=sources[3], unit=declared_unit(text))
    after = {**work, **{k: json.loads(json.dumps(getattr(model, k), default=lambda o: o.model_dump())) for k in
                        ("takeaway", "what_happened", "why_it_matters", "key_numbers", "notable_changes", "quantified_impact")}}
    # the stored quantified_impact carries the pipeline's own check fields: keep them for the part 1 / 2 rule
    stored_q = {q.get("label"): q for q in work.get("quantified_impact") or []}
    after["quantified_impact"] = [stored_q.get(q.get("label"), q) for q in after["quantified_impact"]]
    # the stored facts keep their quotes; take them from the stored card where the text is the same
    stored_w = {(f.get("text") if isinstance(f, dict) else f): f for f in work.get("what_happened") or []}
    after["what_happened"] = [stored_w.get(f.get("text") if isinstance(f, dict) else f, f) for f in after["what_happened"]]
    parts = two_parts.split_card(after, text, "", hidden)
    p1, p2 = part_lines(after, parts)
    return {"parts": parts, "part1": p1, "part2": p2, "hidden": hidden}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--cards")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--category", default="RESULTS")
    ap.add_argument("--texts")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--seed", type=int, default=152)
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--site", default=SITE)
    args = ap.parse_args()
    if bool(args.cards) == bool(args.api):
        ap.error("give --cards FILE or --api")
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    texts = pathlib.Path(args.texts) if args.texts else None
    if texts:
        texts.mkdir(parents=True, exist_ok=True)
    if args.api:
        rows, page = [], 1
        while len(rows) < args.limit:
            d = v2.get(f"{args.site}/api/feed?range=all&category={args.category}&limit=50&page={page}")
            rows += d["cards"]
            if page >= (d.get("pages") or 1):
                break
            page += 1
        rows = rows[:args.limit]
    else:
        loaded = json.load(open(args.cards, encoding="utf-8"))
        rows = loaded["cards"] if isinstance(loaded, dict) else loaded
    dossiers: dict[str, dict] = {}
    report, skipped = [], {"no text": 0, "no memory": 0}
    for row in rows:
        raw = row.get("card_json")
        card = json.loads(raw) if isinstance(raw, str) else raw or row
        scrip = str(row["scrip_code"])
        if scrip not in dossiers:
            dossiers[scrip] = (v2.get(f"{args.site}/api/companies/{scrip}") or {}).get("dossier") or {}
        if not dossiers[scrip]:
            skipped["no memory"] += 1
            continue
        text = v2.filing_text(row, texts, args.download)
        if not text:
            skipped["no text"] += 1
            continue
        try:
            on = render_on(card, dossiers[scrip], row, text)
        except Exception as exc:   # a card the render cannot read is reported, not hidden
            report.append({"news_id": row["news_id"], "symbol": row.get("symbol"), "error": f"{type(exc).__name__}: {exc}"})
            continue
        off = stored_lines(card)
        report.append({"news_id": row["news_id"], "symbol": row.get("symbol"), "scrip_code": scrip,
                       "event_type": card.get("event_type"), "pdf_url": row.get("pdf_url"),
                       "lines_off": len(off), "part1": len(on["part1"]), "part2": len(on["part2"]),
                       "hidden": on["hidden"], "off": off, "on": on})
    done = [r for r in report if "error" not in r]
    hid = [h for r in done for h in r["hidden"]]
    (out / "diff.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    by_field: dict[str, int] = {}
    for h in hid:
        by_field[h["field"]] = by_field.get(h["field"], 0) + 1
    n = max(len(done), 1)
    summary = [
        f"# CARD_TWO_PARTS on/off, {len(done)} cards rendered",
        "",
        f"- lines per card, off (one list): {sum(r['lines_off'] for r in done) / n:.1f}",
        f"- lines per card, on: part 1 {sum(r['part1'] for r in done) / n:.1f}, part 2 {sum(r['part2'] for r in done) / n:.1f}",
        f"- part 2 lines hidden: {len(hid)} on {sum(bool(r['hidden']) for r in done)} cards; by field: {json.dumps(by_field)}",
        f"- render errors: {len(report) - len(done)}; skipped: {json.dumps(skipped)}",
        "",
        "## Hidden lines (the lead reads each against the filing: a hidden line that is right is a false hide)",
    ]
    for r in done:
        for h in r["hidden"]:
            summary.append(f"- {r['symbol']} {r['news_id']} [{h['field']}] {h['text']}  <- {h['why']}")
    (out / "diff.md").write_text("\n".join(summary), encoding="utf-8")
    # blind sample: cards in a seeded shuffle, part 1 and part 2 lines numbered. The hidden lines are mixed into part 2
    # unlabelled (the key says which), so reviewers' verdicts on them show whether hiding was right.
    pool = sorted(done, key=lambda r: r["news_id"])
    rng = random.Random(args.seed)
    rng.shuffle(pool)
    sample, key = [], {}
    for i, r in enumerate(pool[:args.sample], 1):
        cid = f"c{i:02d}"
        p2 = [{"text": x["text"], "hidden": False} for x in r["on"]["part2"] if x["field"] != "block"]
        p2 += [{"text": h["text"], "hidden": True} for h in r["hidden"]]
        rng.shuffle(p2)
        p1 = [{"n": f"1.{k}", "text": x["text"]} for k, x in enumerate(r["on"]["part1"], 1) if x["field"] != "block"]
        sample.append({"id": cid, "news_id": r["news_id"], "symbol": r["symbol"], "scrip_code": r["scrip_code"],
                       "event_type": r["event_type"], "pdf_url": r["pdf_url"], "part1": p1,
                       "part2": [{"n": f"2.{k}", "text": x["text"]} for k, x in enumerate(p2, 1)]})
        key[cid] = {"news_id": r["news_id"], "hidden": [f"2.{k}" for k, x in enumerate(p2, 1) if x["hidden"]]}
    (out / "blind_sample.json").write_text(json.dumps(sample, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "blind_key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(json.dumps({"rendered": len(done), "hidden": len(hid), "sample": len(sample), "errors": len(report) - len(done)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
