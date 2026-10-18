"""Round 2 re-run as a measured round (DATA_QUALITY.md step 6): the same 90 filings round 2 reviewed, read again after
the round's companies were rebuilt under the structural changes (TRACKER F60-F63), with the same model weights.

  python -I -X utf8 scripts/audit_round2/rerun_cards.py OUT.json
  python -I -X utf8 scripts/audit_export.py OUT.json DIR --blind --memory http://localhost:5173 --random 20261018 --limit 0

Writes OUT.json in the shape audit_export.py reads, each row carrying `held` as the card stands now and
`held_before` as round 2 had it, and prints what became of each filing that has no card now.
"""
import glob
import json
import pathlib
import re
import sqlite3
import sys

HERE = pathlib.Path(__file__).resolve().parent
DOCS = HERE.parents[2] / "docs" / "audit"
before = json.loads((DOCS / "round-2.json").read_text(encoding="utf-8"))
manifest = json.loads((DOCS / "round-2" / "cards-manifest.json").read_text(encoding="utf-8"))
held_before = {k: bool(v.get("held")) for k, v in manifest.items()}
ids = [r["news_id"] for r in before]

db = [p for p in glob.glob(str(HERE.parents[2] / "data/wrangler/v3/d1/miniflare-D1DatabaseObject/*.sqlite"))
      if "metadata" not in p][0]
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
marks = ",".join("?" * len(ids))
rows = [dict(r) for r in c.execute(
    "select c.news_id, f.scrip_code, f.filed_at, f.headline headline_filing, f.subject, c.card_json, c.held "
    f"from cards c join filings f using(news_id) where c.news_id in ({marks})", ids)]
for r in rows:
    r["held_before"] = held_before.get(r["news_id"])
have = {r["news_id"] for r in rows}
partners = {}
for r in c.execute(f"select news_id, status, reason from filings where news_id in ({marks})", ids):
    if r["news_id"] not in have:
        print(f"no card now: {r['news_id'][:8]} {r['status']} {r['reason'] or ''}"[:160], file=sys.stderr)
        m = re.search(r"duplicate of ([0-9a-f-]{36})", r["reason"] or "")
        if r["status"] == "DUPLICATE" and m and m.group(1) not in have:
            partners[m.group(1)] = r["news_id"]
# A filing merged into another of the same event: its event's card is the other filing's, reviewed in its place
for r in c.execute("select c.news_id, f.scrip_code, f.filed_at, f.headline headline_filing, f.subject, c.card_json, c.held "
                   f"from cards c join filings f using(news_id) where c.news_id in ({','.join('?' * len(partners))})",
                   list(partners)):
    rows.append({**dict(r), "stands_for": partners[r["news_id"]], "held_before": held_before.get(partners[r["news_id"]])})
    print(f"reviewed in its place: {r['news_id'][:8]} for {partners[r['news_id']][:8]}", file=sys.stderr)
pathlib.Path(sys.argv[1]).write_text(json.dumps([{"results": rows}], ensure_ascii=False), encoding="utf-8")
print(f"{len(rows)} of {len(ids)} filings have a card now; {sum(1 for r in rows if r['held'])} held "
      f"(round 2: {sum(held_before.get(i, False) for i in ids)} held)")
