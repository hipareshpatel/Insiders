"""A benchmark set for PDF table extraction, scored against each filing's own XBRL.

A results PDF and the XBRL file filed with it state the same figures. So for each filing here the
XBRL gives the answer: the period's revenue, profit, finance cost and the rest, in crore. An extraction
engine is then scored on whether it puts each of those figures on the same line as its row label in
the right column - the thing the audit's wrong_column and unit_scale classes are about - instead of on
whether its output looks tidy.

    python scripts/bench_manifest.py OUT_DIR [--per-company 2]

Writes OUT_DIR/manifest.json and OUT_DIR/pdfs/<news_id>.pdf. Downloads each PDF once, so engines can be
run side by side without asking BSE for the same file again.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bse_intel import xbrl  # noqa: E402
from bse_intel.bse import BseClient  # noqa: E402
from bse_intel.extract import Document  # noqa: E402
from bse_intel.grounding import declared_unit  # noqa: E402

# The figures a results card states. Ratios are left out: a statement prints the two amounts, not the ratio.
TRUTH = ("revenue", "other_income", "total_income", "employee_cost", "finance_cost", "depreciation",
         "other_expenses", "total_expenses", "pbt", "tax_expense", "pat", "eps",
         "interest_earned", "interest_expended", "provisions", "pre_provision_operating_profit")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--per-company", type=int, default=2)
    args = ap.parse_args()
    out = Path(args.out)
    (out / "pdfs").mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    db = [p for p in glob.glob(str(root / "data/wrangler/v3/d1/miniflare-D1DatabaseObject/*.sqlite"))
          if "metadata" not in p][0]
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    rows = c.execute("""select f.news_id, f.company_name, f.scrip_code, f.pdf_url, f.filing_date,
                        json_extract(c.card_json,'$.xbrl.period') period,
                        json_extract(c.card_json,'$.xbrl.basis') basis
                        from filings f join cards c using(news_id)
                        where json_extract(c.card_json,'$.xbrl.period') is not null
                        order by f.company_name, f.filing_date""").fetchall()
    taken: collections.Counter = collections.Counter()
    picked = []
    for r in rows:
        if taken[r["scrip_code"]] < args.per_company:
            taken[r["scrip_code"]] += 1
            picked.append(r)

    bse = BseClient()
    archive: dict[str, list] = {}
    manifest = []
    for r in picked:
        links = archive.setdefault(r["scrip_code"], bse.results_xbrl(r["scrip_code"]))
        link = next((l for l in links if l.period == r["period"] and l.basis == r["basis"]), None)
        blob = bse.download(link.url) if link else None
        tagged = xbrl.parse(blob) if blob else None
        if not tagged:
            print(f"  {r['news_id'][:8]} {r['company_name'][:22]}: no XBRL to score against, skipped")
            continue
        truth = {m.metric: m.value for m in tagged.metrics
                 if m.period == r["period"] and m.metric in TRUTH and m.value not in (None, 0)}
        pdf = out / "pdfs" / f"{r['news_id']}.pdf"
        if not pdf.exists():
            data = bse.download(r["pdf_url"])
            if not data:
                print(f"  {r['news_id'][:8]}: PDF did not download, skipped")
                continue
            pdf.write_bytes(data)
        doc = Document(pdf.read_bytes())
        text = doc.select_text(10_000_000, [])
        manifest.append({"news_id": r["news_id"], "company": r["company_name"], "period": r["period"],
                         "basis": r["basis"], "pdf": f"pdfs/{pdf.name}", "pages": doc.page_count,
                         "declared_unit": declared_unit(text),   # divisor to crore: 100 lakh, 10 million
                         "text_layer_chars": len(text), "truth_crore": truth})
        print(f"  {r['news_id'][:8]} {r['company_name'][:22]:22} {r['period']}/{r['basis'][:4]} "
              f"{doc.page_count:>3}p unit={declared_unit(text)} truth={len(truth)}")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(manifest)} filings, {sum(len(m['truth_crore']) for m in manifest)} figures to find")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
