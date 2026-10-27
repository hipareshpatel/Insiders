"""BSE fill benchmark (owner, 27 Oct 2026): the figures a memory-gaps-fill-bse dry run would write (its CSV artifact) against
screener.in's quarterly table on the same basis. Screener rounds revenue and profit to whole crore, so those are checked
to within 0.5 Cr; EPS is printed to 0.01. Every difference is then settled against the company's own results statement.

    python scripts/bench_bse/compare_screener.py <dir>

<dir> holds memory-gaps-fill-bse.csv and the screener pages as <SYMBOL>-consolidated.html / <SYMBOL>-standalone.html.
Profit is compared as total profit (`pat`), screener's Net Profit, before profit for owners. Writes <dir>/compare.json."""
import csv, json, sys, collections
from pathlib import Path
from bse_intel.screener_fill import parse_full
D = Path(sys.argv[1])
rows = list(csv.DictReader(open(D / "memory-gaps-fill-bse.csv")))
pages = {}
for f in D.glob("*-*.html"):
    sym, basis = f.stem.rsplit("-", 1)
    p = parse_full(f.read_text(errors="replace"))
    pages[(sym, basis.upper())] = p
OURS = {"revenue": ["revenue"], "pat": ["pat", "pat_owners"], "eps": ["eps", "eps_total"]}
by = collections.defaultdict(dict)
for r in rows:
    by[(r["symbol"], r["period"], r["basis"])][r["metric"]] = float(r["value"])
pairs = []
for (sym, period, basis), m in sorted(by.items()):
    page = pages.get((sym, basis))
    if not page or page.get("basis") != basis:
        pairs.append({"sym": sym, "period": period, "basis": basis, "metric": "-", "why": "no screener page on this basis"}); continue
    q = page["quarters"].get(period)
    if not q:
        pairs.append({"sym": sym, "period": period, "basis": basis, "metric": "-", "why": "screener has no column"}); continue
    for metric, names in OURS.items():
        ours = next((m[n] for n in names if n in m), None)
        theirs = q.get(metric)
        if ours is None or theirs is None:
            pairs.append({"sym": sym, "period": period, "basis": basis, "metric": metric, "why": "one side missing"}); continue
        pairs.append({"sym": sym, "period": period, "basis": basis, "metric": metric, "ours": ours, "theirs": theirs,
                      "diff": round(abs(ours - theirs), 4)})
cmp = [p for p in pairs if "diff" in p]
def band(p):
    d = p["diff"]
    if p["metric"] == "eps":
        return "<=0.01" if d <= 0.011 else "<=0.1" if d <= 0.1 else "<=1" if d <= 1 else ">1"
    return "<=0.5 (screener rounding)" if d <= 0.5 + 1e-9 else "<=1" if d <= 1 else ">1"
out = collections.Counter((p["metric"], band(p)) for p in cmp)
print("compared pairs", len(cmp), "not compared", len(pairs) - len(cmp))
print(collections.Counter(p["why"] for p in pairs if "why" in p))
for k in sorted(out): print(k, out[k])
print("--- outside the bands (eps >0.01, money >0.5):")
for p in cmp:
    if (p["metric"] == "eps" and p["diff"] > 0.011) or (p["metric"] != "eps" and p["diff"] > 0.5 + 1e-9):
        print(p)
json.dump(pairs, open(D / "compare.json", "w"), indent=1)
