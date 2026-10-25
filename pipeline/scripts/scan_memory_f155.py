"""Read-only scan of stored dossiers for two memory faults found in the F155 review (25 Oct 2026). Nothing is written.

    python -I -X utf8 scripts/scan_memory_f155.py OUT_DIR [--site https://insiders.reply-bd3.workers.dev] [--limit N]

It reads the company list (`/api/companies`, paged) and each company's dossier (`/api/companies/<scrip>`, 0.3 s apart,
kept in OUT_DIR/dossiers so a second run is offline), then reports into OUT_DIR/f155_scan.json and prints a summary:

  owners_over_profit   a quarter whose profit to owners is above the group's profit by more than a minority share can
                       explain (profit > 0, owners - profit > max(0.5, 1%)): IREDA's Q2FY26 614.76 against 549.33, the
                       owners' tag holding the total comprehensive income. A real minority is a deduction, so owners
                       above the profit means another figure was read as profit (a minority loss is the one exception and
                       is listed by its own count: `minority_loss_possible`, when owners/profit is within 2% of the
                       company's other quarters).
  owners_over_profit_no_minority
                       the subset that matches IREDA's fault: the company's other quarters have owners = profit within 1%
                       (no minority interest) and this quarter's owners are more than 1% above the profit.
  ratio_jump           the owners/profit ratio of a quarter more than 5 points from the median of the company's other
                       quarters while both figures are positive (a company whose minority is stable does not jump).
  future_quarter       a figure whose every source was filed on or before the end of the quarter it is stored for (CIE
                       India's July presentation stored as Q2FY27): refused at write time since F155, listed here so the
                       companies can be re-seeded.

Companies to repair are re-seeded with `python -m bse_intel seed-memory --scrips <list>` (listed here, not run)."""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "src"))
from bse_intel.periods import due_date  # noqa: E402

SITE = "https://insiders.reply-bd3.workers.dev"


def get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def universe(site: str, limit: int | None) -> list[dict]:
    out, offset = [], 0
    while True:
        page = get(f"{site}/api/companies?limit=200&offset={offset}")
        out += page.get("companies") or []
        offset = page.get("next_offset")
        if offset is None or (limit and len(out) >= limit):
            break
        time.sleep(0.3)
    return out[:limit] if limit else out


def analyse(scrip: str, dossier: dict) -> dict:
    by = {(m["metric"], m["period"]): m for m in dossier.get("financial_metrics", [])}
    found: dict[str, list] = {"owners_over_profit": [], "owners_over_profit_no_minority": [], "ratio_jump": [],
                              "future_quarter": []}
    ratios = {p: by[("pat_owners", p)]["value"] / by[("pat", p)]["value"] for (m, p) in by
              if m == "pat_owners" and ("pat", p) in by and p.startswith("Q")
              and by[("pat", p)]["value"] > 0 and by[("pat_owners", p)]["value"] > 0}
    for (metric, period), owners in by.items():
        pat = by.get(("pat", period))
        if metric != "pat_owners" or pat is None:
            continue
        o, p = owners["value"], pat["value"]
        row = {"period": period, "pat": p, "pat_owners": o, "source": owners.get("value_news_id") or owners.get("source_news_id")}
        if p > 0 and o - p > max(0.5, 0.01 * p):
            others = [r for q, r in ratios.items() if q != period]
            row["minority_loss_possible"] = bool(others) and abs(o / p - statistics.median(others)) <= 0.02
            found["owners_over_profit"].append(row)
            if len(others) >= 2 and abs(statistics.median(others) - 1) <= 0.01 and o > 1.01 * p:
                found["owners_over_profit_no_minority"].append(row)
        elif period in ratios:
            others = [r for q, r in ratios.items() if q != period]
            if len(others) >= 3 and abs(ratios[period] - statistics.median(others)) > 0.05:
                found["ratio_jump"].append({**row, "ratio": round(ratios[period], 3), "median": round(statistics.median(others), 3)})
    for (metric, period), entry in by.items():
        end = due_date(period) if period.startswith("Q") else None
        sources = entry.get("sources") or [{"as_of": entry.get("as_of")}]
        if end and sources and all((s.get("as_of") or "9999")[:10] <= end.isoformat() for s in sources):
            found["future_quarter"].append({"metric": metric, "period": period, "value": entry.get("value"),
                                            "source": entry.get("source_news_id"), "as_of": entry.get("as_of")})
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--site", default=SITE)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    (out / "dossiers").mkdir(parents=True, exist_ok=True)
    companies = [c for c in universe(args.site, args.limit) if (c.get("card_count") or 0) > 0]
    report: dict[str, dict] = {}
    for c in companies:
        scrip, path = c["scrip_code"], out / "dossiers" / f"{c['scrip_code']}.json"
        if path.exists():
            dossier = json.loads(path.read_text())
        else:
            try:
                dossier = (get(f"{args.site}/api/companies/{scrip}") or {}).get("dossier") or {}
            except Exception as exc:  # noqa: BLE001
                print(f"{scrip}: {exc}", file=sys.stderr)
                continue
            path.write_text(json.dumps(dossier))
            time.sleep(0.3)
        found = analyse(scrip, dossier)
        if any(found.values()):
            report[scrip] = {"symbol": c.get("symbol"), **found}
    (out / "f155_scan.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"companies read: {len(companies)}")
    for kind in ("owners_over_profit", "owners_over_profit_no_minority", "ratio_jump", "future_quarter"):
        hit = {s: r for s, r in report.items() if r[kind]}
        print(f"{kind}: {sum(len(r[kind]) for r in hit.values())} figures in {len(hit)} companies")
        for s, r in list(hit.items())[:8]:
            print("   ", s, r["symbol"], r[kind][:2])
    print("re-seed (not run): seed-memory --scrips " + ",".join(sorted({s for s, r in report.items()
                                                                       if r["owners_over_profit_no_minority"] or r["future_quarter"]})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
