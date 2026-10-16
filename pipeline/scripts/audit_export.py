"""Export cards and their filing text for an independent card-vs-PDF audit (docs/AUDIT_LOOP.md).

Usage:
  npx wrangler d1 execute bse-index --local --persist-to ../data/wrangler --json --command \
    "SELECT c.news_id, c.scrip_code, f.headline headline_filing, f.subject, c.card_json FROM cards c JOIN filings f USING(news_id) ..." > cards.json
  python scripts/audit_export.py cards.json OUT_DIR [--per-reviewer 10] [--skip audited_ids.txt]

Writes OUT_DIR/reviewer_NN/<news_id>.card.json and <news_id>.pdf.txt (the same cached text the pipeline read, not a
re-download). Reviewers write findings.json beside them; scripts/audit_tally.py summarises. Run with `python -I -X utf8`.
"""
import argparse
import gzip
import json
import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from bse_intel.extract import Document  # noqa: E402
from bse_intel.settings import get_settings  # noqa: E402

KEEP = ("headline", "takeaway", "core_catalyst", "what_happened", "why_it_matters", "key_numbers", "notable_changes",
        "deal_value", "quantified_impact", "track_next", "signals", "timeline_entry", "event_type", "impact_level",
        "missing_disclosures", "grounding", "review", "xbrl", "model")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cards_json")
    ap.add_argument("out_dir")
    ap.add_argument("--per-reviewer", type=int, default=10)
    ap.add_argument("--skip", help="file with news_ids already audited, one per line")
    args = ap.parse_args()
    rows = json.load(open(args.cards_json, encoding="utf-8"))[0]["results"]
    skip = set(pathlib.Path(args.skip).read_text().split()) if args.skip else set()
    rows = [r for r in rows if r["news_id"] not in skip]
    cache = get_settings().text_cache_dir
    out = pathlib.Path(args.out_dir)
    written = 0
    for i, row in enumerate(rows):
        folder = out / f"reviewer_{i // args.per_reviewer + 1:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        card = json.loads(row["card_json"])
        keep = {k: card.get(k) for k in KEEP}
        keep["_filing"] = {"news_id": row["news_id"], "headline": row.get("headline_filing"), "subject": row.get("subject")}
        (folder / f"{row['news_id']}.card.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
        path = cache / row["news_id"][:2] / f"{row['news_id']}.json.gz"
        text = (Document.from_cache(json.loads(gzip.decompress(path.read_bytes()))).select_text(10_000_000, [])
                if path.exists() else "(no cached text)")
        (folder / f"{row['news_id']}.pdf.txt").write_text(text, encoding="utf-8")
        written += 1
    print(f"{written} cards in {len({i // args.per_reviewer for i in range(written)})} reviewer folders under {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
