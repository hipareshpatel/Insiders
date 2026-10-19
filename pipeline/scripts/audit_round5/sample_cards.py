"""Audit round 5: the cards to review, drawn with the round's seed once the run has ended.

  python -I -X utf8 scripts/audit_round4/sample_cards.py OUT.json [--published 110] [--held 10]

Published cards: a seeded shuffle within each company, then one company at a time in turn, so every company is
covered before any doubles up. Held cards: a seeded draw of up to --held. Writes OUT.json in the shape
audit_export.py reads ([{"results": rows}], rows carrying held), then:

  python -I -X utf8 scripts/audit_export.py OUT.json DIR --blind --memory http://localhost:5173 --random 20261021 --limit 0
"""
import argparse
import glob
import json
import pathlib
import random
import sqlite3

HERE = pathlib.Path(__file__).parent
SPEC = json.loads((HERE / "companies.json").read_text())
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--published", type=int, default=110)
ap.add_argument("--held", type=int, default=10)
args = ap.parse_args()

scrips = [c["scrip_code"] for c in SPEC["companies"]]
lo, hi = SPEC["window"]
db = [p for p in glob.glob(r"D:\Insiders\data\wrangler\v3\d1\miniflare-D1DatabaseObject\*.sqlite") if "metadata" not in p][0]
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
marks = ",".join("?" * len(scrips))
rows = [dict(r) for r in c.execute(
    "select c.news_id, f.scrip_code, f.filed_at, f.headline headline_filing, f.subject, c.card_json, c.held, c.impact_level "
    f"from cards c join filings f using(news_id) where f.scrip_code in ({marks}) "
    "and f.filing_date between ? and ? order by c.news_id", (*scrips, lo, hi))]
rng = random.Random(SPEC["seed"])
by_company: dict[str, list[dict]] = {}
for r in rows:
    if not r["held"]:
        by_company.setdefault(r["scrip_code"], []).append(r)
for queue in by_company.values():
    rng.shuffle(queue)
published = []
while len(published) < args.published and any(by_company.values()):
    for scrip in scrips:
        if by_company.get(scrip) and len(published) < args.published:
            published.append(by_company[scrip].pop(0))
held = [r for r in rows if r["held"]]
rng.shuffle(held)
held = held[:args.held]
pathlib.Path(args.out).write_text(json.dumps([{"results": published + held}], ensure_ascii=False), encoding="utf-8")
print(f"{len(rows)} cards on {len({r['scrip_code'] for r in rows})} companies ({sum(1 for r in rows if r['held'])} held); "
      f"sampled {len(published)} published from {len({r['scrip_code'] for r in published})} companies and {len(held)} held")
