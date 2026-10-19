"""Audit round 7, the fourth measured NSE round, after round 6: 20 companies the pipeline has never
read, listed on NSE with a market cap of at least ₹500 Cr (D31), one per sector-and-size stratum, drawn with a fixed
seed. At least 100 published cards are reviewed (owner, 2026-10-19), hence 20 companies where round 3 had 14."""
import glob
import json
import pathlib
import random
import sqlite3

from bse_intel.nse import NseClient

SEED = 20261023  # set before the draw: rounds 2-6 used 20261018-20261022
LARGE, MID = (10_000, 1e9), (500, 10_000)
STRATA = [
    ("banks", LARGE), ("nbfc", LARGE), ("nbfc", MID), ("insurance", LARGE), ("it", LARGE), ("it", MID),
    ("pharma", LARGE), ("pharma", MID), ("capital_goods", LARGE), ("capital_goods", MID), ("chemicals", MID),
    ("metals", MID), ("auto_components", MID), ("fmcg", LARGE), ("consumer_durables", MID), ("construction", MID),
    ("realty", MID), ("textiles", MID), ("cement", LARGE), ("power", LARGE),
]
db = [p for p in glob.glob(r"D:\Insiders\data\wrangler\v3\d1\miniflare-D1DatabaseObject\*.sqlite") if "metadata" not in p][0]
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
seen = {r[0] for r in c.execute("select distinct scrip_code from filings")}
# and every earlier round's companies, filings or not (Sunrakshakk was in round 5's sample with none in its window)
for spec in pathlib.Path(__file__).parent.parent.glob("audit_round*/companies.json"):
    if spec.parent != pathlib.Path(__file__).parent:
        seen |= {c_["scrip_code"] for c_ in json.loads(spec.read_text())["companies"]}
with NseClient() as nse:
    on_nse = {e.isin for e in nse.equity_list()}
rng = random.Random(SEED)
chosen = []
for sector, (lo, hi) in STRATA:
    pool = [dict(r) for r in c.execute("select scrip_code, company_name, symbol, isin, industry, sector, market_cap_cr "
                                       "from companies where sector = ? and market_cap_cr >= ? and market_cap_cr < ? "
                                       "order by scrip_code", (sector, lo, hi))
            if r["scrip_code"] not in seen and r["isin"] in on_nse]
    pick = rng.choice(pool)
    chosen.append({**pick, "stratum": f"{sector} {lo:g}-{hi:g}", "pool": len(pool)})
    print(f"{sector:18} {lo:>7g}+ pool {len(pool):4} -> {pick['scrip_code']} {pick['symbol']:12} {pick['company_name'][:34]:34} "
          f"{pick['market_cap_cr']:>10,.0f} Cr  {pick['industry']}")
out = pathlib.Path(__file__).parent / "companies.json"
out.write_text(json.dumps({"seed": SEED, "window": ["2026-07-15", "2026-10-18"], "companies": chosen}, indent=1))
print(",".join(x["scrip_code"] for x in chosen))
