"""Audit round 2: companies the pipeline has never read, one per sector-and-size stratum, drawn with a fixed seed."""
import glob
import json
import pathlib
import random
import sqlite3

SEED = 20261018
SMOKE = {"506525", "532776", "505192", "500672", "530019", "519552", "532811", "543533", "500338", "542867"}
LARGE, MID, SMALL = (10_000, 1e9), (1_000, 10_000), (100, 1_000)
STRATA = [
    ("banks", LARGE), ("insurance", LARGE), ("nbfc", LARGE), ("nbfc", MID), ("it", LARGE), ("it", MID),
    ("pharma", MID), ("capital_goods", MID), ("fmcg", LARGE), ("auto_components", MID), ("metals", LARGE),
    ("power", LARGE), ("chemicals", SMALL), ("consumer_durables", SMALL),
]
db = [p for p in glob.glob(r"D:\Insiders\data\wrangler\v3\d1\miniflare-D1DatabaseObject\*.sqlite") if "metadata" not in p][0]
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
seen = {r[0] for r in c.execute("select distinct scrip_code from filings")}
rng = random.Random(SEED)
chosen = []
for sector, (lo, hi) in STRATA:
    pool = [dict(r) for r in c.execute("select scrip_code, company_name, symbol, industry, sector, market_cap_cr, bse_group "
                                       "from companies where sector = ? and market_cap_cr >= ? and market_cap_cr < ? "
                                       "order by scrip_code", (sector, lo, hi))
            if r["scrip_code"] not in SMOKE | seen]
    pick = rng.choice(pool)
    chosen.append({**pick, "stratum": f"{sector} {lo:g}-{hi:g}", "pool": len(pool)})
    print(f"{sector:18} {lo:>7g}+ pool {len(pool):4} -> {pick['scrip_code']} {pick['company_name'][:34]:34} "
          f"{pick['market_cap_cr']:>10,.0f} Cr  {pick['industry']}")
out = pathlib.Path(__file__).parent / "companies.json"
out.write_text(json.dumps({"seed": SEED, "window": ["2026-07-15", "2026-10-18"], "companies": chosen}, indent=1))
print(",".join(x["scrip_code"] for x in chosen))
