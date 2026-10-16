"""Check a dossier's period figures against each other, with no PDF and no AI.

Indian results are filed cumulatively, so for any flow metric H1 = Q1 + Q2, 9M = H1 + Q3 and
FY = 9M + Q4. A figure that breaks that identity is wrong whoever wrote it, and because every later
card reads its year-ago figure out of memory, one wrong quarter sends a wrong YoY onto every card
that follows (audit round 1: Kanoria's Q1FY26 revenue sat in memory as 453.78 where H1 minus Q2
gives 201.38, and every Kanoria card comparing with Q1FY26 inherited it).

Usage: python -I -X utf8 scripts/memory_check.py BACKUP_DIR [--quiet]
BACKUP_DIR is what `bse-intel backup --out DIR` wrote: DIR/memory/<scrip>.json.
"""
import argparse
import json
import pathlib

# Flows accumulate over a financial year; balances, margins and per-share figures do not.
FLOWS = {"revenue", "total_income", "total_expenses", "ebitda", "pbt", "pat", "pat_continuing",
         "other_income", "employee_cost", "other_expenses", "depreciation", "finance_cost",
         "tax_expense", "current_tax", "deferred_tax", "exceptional_items", "cost_of_materials",
         "purchases_stock_in_trade", "raw_material_cost", "inventory_change", "operating_cash_flow"}
TOLERANCE = 0.02  # 2%: a filing's own crore figures are rounded


def problems(scrip: str, metrics: list[dict]) -> list[dict]:
    by: dict[str, dict[str, tuple[float, str]]] = {}
    for m in metrics:
        if m.get("metric") not in FLOWS or m.get("unit") != "INR_CR" or m.get("value") is None:
            continue
        by.setdefault(m["metric"], {})[m["period"]] = (m["value"], m.get("source_news_id") or "")
    found = []
    for metric, periods in sorted(by.items()):
        years = sorted({p[-4:] for p in periods if p[-4:].startswith("FY")})
        for fy in years:
            q = {i: periods.get(f"Q{i}{fy}") for i in (1, 2, 3, 4)}
            h1, m9, full = periods.get(f"H1{fy}"), periods.get(f"9M{fy}"), periods.get(fy)
            for label, whole, parts in (("H1", h1, (q[1], q[2])), ("9M", m9, (h1, q[3])), ("FY", full, (m9, q[4]))):
                if whole is None or any(p is None for p in parts):
                    continue
                total = sum(p[0] for p in parts)
                if abs(total - whole[0]) <= max(0.05, abs(whole[0]) * TOLERANCE):
                    continue
                found.append({"scrip": scrip, "metric": metric, "period": f"{label}{fy}" if label != "FY" else fy,
                              "stated": round(whole[0], 2), "parts_sum": round(total, 2),
                              "difference": round(whole[0] - total, 2),
                              "sources": sorted({s for _, s in (whole,) + parts if s})})
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("backup_dir")
    ap.add_argument("--quiet", action="store_true", help="print only the count")
    args = ap.parse_args()
    root = pathlib.Path(args.backup_dir) / "memory"
    if not root.is_dir():
        print(f"no memory directory under {args.backup_dir}: run `bse-intel backup --out` first")
        return 1
    all_found, dossiers = [], 0
    for path in sorted(root.glob("*.json")):
        dossiers += 1
        all_found += problems(path.stem, json.loads(path.read_text(encoding="utf-8")).get("financial_metrics") or [])
    from_cards = [p for p in all_found if any(not s.startswith("xbrl:") for s in p["sources"])]
    print(f"{dossiers} dossiers, {len(all_found)} flow figures that do not reconcile "
          f"({len(from_cards)} involve a figure a card wrote)")
    if not args.quiet:
        for p in all_found:
            print(f"  {p['scrip']} {p['metric']} {p['period']}: stated {p['stated']:,.2f}, parts sum to "
                  f"{p['parts_sum']:,.2f} ({p['difference']:+,.2f}); sources {', '.join(p['sources'])}")
    return 1 if all_found else 0


if __name__ == "__main__":
    raise SystemExit(main())
