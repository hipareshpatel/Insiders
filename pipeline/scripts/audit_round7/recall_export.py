"""Audit round 7, missed news: a seeded sample of the filings the round-7 companies had set aside, with their text.

  recall_export.py OUT_DIR [--per-reviewer 10]

Strata: rule drops (from the day noise files; their attachments were never fetched, so they are downloaded now),
pass 1 or pass 2 "not material", timeline-only (D22) and duplicates. Writes OUT_DIR/reviewer_NN/items.json and
<news_id>.pdf.txt."""
import argparse
import collections
import glob
import json
import pathlib
import random
import sqlite3

from bse_intel.bse import BseClient
from bse_intel.nse import NseClient
from bse_intel.extract import Document
from bse_intel.sinks.platform import PlatformSink

HERE = pathlib.Path(__file__).parent
SPEC = json.loads((HERE / "companies.json").read_text())
SCRIPS = {c["scrip_code"] for c in SPEC["companies"]}
NAMES = {c["scrip_code"]: c["company_name"] for c in SPEC["companies"]}
QUOTA = {"rule drop": 25, "not material": 15, "timeline only": 5, "duplicate": 5}

ap = argparse.ArgumentParser()
ap.add_argument("out_dir")
ap.add_argument("--per-reviewer", type=int, default=10)
ap.add_argument("--kinds", default=",".join(QUOTA), help="which strata to export now (rule drops are final once discovery has run; the others once processing has)")
args = ap.parse_args()
kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
db = [p for p in glob.glob(r"D:\Insiders\data\wrangler\v3\d1\miniflare-D1DatabaseObject\*.sqlite") if "metadata" not in p][0]
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
marks = ",".join("?" * len(SCRIPS))
pools: dict[str, list[dict]] = collections.defaultdict(list)
# A filing that got a card is no set-aside filing, whatever its route says: round 6's sample took Ambuja's merger vote
# (route TIMELINE, then a held card) as "timeline only", and its reviewer counted it MISSED
carded = {r[0] for r in c.execute(f"select news_id from cards where scrip_code in ({marks})", sorted(SCRIPS))}
for r in c.execute(f"select * from filings where scrip_code in ({marks})", sorted(SCRIPS)):
    r = dict(r)
    if r["news_id"] in carded:
        continue
    kind = ("not material" if r["status"] == "NOT_MATERIAL" else "timeline only" if r["route"] == "TIMELINE"
            else "duplicate" if r["status"] == "DUPLICATE" else None)
    if kind:
        pools[kind].append(r)
sink = PlatformSink("http://localhost:5173", "dev-local-token")
lo, hi = SPEC["window"]
for key in sink.list_objects("noise/"):
    day = key.split("/")[1]
    if not lo <= day <= hi:
        continue
    body = json.loads(sink.get_object(key) or b"{}")
    for row in body.get("rows", []):
        r = dict(zip(body["fields"], row))
        if r["scrip_code"] in SCRIPS:
            pools["rule drop"].append({**r, "filing_date": day, "status": "DROPPED"})
print({k: len(v) for k, v in pools.items()})
sample = []
for kind in kinds:   # one seeded draw per stratum, so exporting them at different times gives the same sample
    pool = sorted(pools[kind], key=lambda r: r["news_id"])
    random.Random(f"{SPEC['seed']}-{kind}").shuffle(pool)
    sample += [{**r, "_kind": kind} for r in pool[:QUOTA[kind]]]
random.Random(f"{SPEC['seed']}-{args.kinds}").shuffle(sample)

bse = BseClient()
nse = NseClient()   # round 4 is NSE: its attachments are on nsearchives
cache = pathlib.Path(r"D:\Insiders\data\text_cache")
out = pathlib.Path(args.out_dir)
for i, r in enumerate(sample):
    folder = out / f"reviewer_{i // args.per_reviewer + 1:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    nid = r["news_id"]
    text = ""
    path = cache / nid[:2] / f"{nid}.json.gz"
    if path.exists():
        import gzip
        text = Document.from_cache(json.loads(gzip.decompress(path.read_bytes()))).select_text(200_000, [])
    elif r.get("pdf_url"):
        try:
            pdf = (nse.fetch if "nseindia.com" in r["pdf_url"] else bse.download)(r["pdf_url"])
            text = Document(pdf).select_text(200_000, []) if pdf else ""
        except Exception as exc:
            text = f"(attachment not readable: {type(exc).__name__})"
    (folder / f"{nid}.pdf.txt").write_text(text or "(no text)", encoding="utf-8")
    items_path = folder / "items.json"
    items = json.loads(items_path.read_text(encoding="utf-8")) if items_path.exists() else []
    items.append({"news_id": nid, "company": NAMES.get(r["scrip_code"], r.get("company_name")), "headline": r.get("headline"),
                  "subject": r.get("subject"), "category": r.get("category"), "subcategory": r.get("subcategory"),
                  "filed": (r.get("filed_at") or r.get("filing_date") or "")[:10], "reason": r.get("reason")})
    items_path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
(out / "manifest.json").write_text(json.dumps({r["news_id"]: r["_kind"] for r in sample}, indent=1))
print(len(sample), "filings in", len({i // args.per_reviewer for i in range(len(sample))}), "folders;",
      collections.Counter(r["_kind"] for r in sample))
