"""The XBRL-key locator against the hand answer keys (docs/bench/hardpdf, docs/bench/normalpdf): how often does it find the
key's figure, and in the right place? Read only, local PDFs, no network.

    python pipeline/scripts/xbrl_key_vs_handkey.py --key docs/bench/normalpdf/key.csv --pdfs DIR --files files.json --out OUT
    python pipeline/scripts/xbrl_key_vs_handkey.py --key docs/bench/hardpdf/key.csv --pdfs DIR --out OUT

``--pdfs`` is a folder of the key's PDFs. For the hard key a PDF is ``<SYMBOL>.pdf`` (the symbol's "&" kept or dropped, "_"
for "&"); for the normal key ``--files`` is the JSON list ({"nid", "sym", "period"}) that maps a filing to ``nse-<nid>.pdf``.
The key's expected figure (crore, as printed) is given to the locator as the XBRL value. The key has no coordinates, so "right
place" is what can be checked independently: the key's page (the normal key has one) and, for a miss, whether the value is
printed on the page at all (a cell of any row, column or unit holds it): a miss with the value on the page is the locator's
row, column or basis proof failing; a miss with no value is a page the text layer cannot read.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from bse_intel import xbrl_key as xk


def pdf_for(folder: Path, symbol: str, period: str, files: list[dict] | None) -> Path | None:
    if files is not None:
        for f in files:
            if f["sym"] == symbol:
                p = folder / f"{f['nid']}.pdf"
                if p.exists():
                    return p
        return None
    for name in (symbol, symbol.replace("&", "_"), symbol.replace("&", "")):
        if (folder / f"{name}.pdf").exists():
            return folder / f"{name}.pdf"
    return None


def value_printed_anywhere(model: xk.DocModel, e: xk.Expected, page: int | None) -> list[str]:
    """The text layer's number tokens of the key's page (the whole document when the key has no page) that hold the value at any
    printed unit, whatever their row, column or basis; as cells where they sit in a table."""
    out = []
    for n_page, num in model.numbers:
        if page is not None and n_page != page:
            continue
        fig = xk.Fig("", num, 0, 0, 0, 0, ())
        if any(xk._matches(e, fig, per) for per in ((1.0,) if e.metric == "eps" else xk._ALL_UNITS)):
            out.append(f"p{n_page} {num.value:g}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--pdfs", required=True)
    ap.add_argument("--files")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    files = json.loads(Path(args.files).read_text()) if args.files else None
    rows = list(csv.DictReader(open(args.key, encoding="utf-8")))
    by_file: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_file[f"{r['symbol']}|{r['pdf_url']}"].append(r)
    out_rows = []
    skipped = Counter()
    for key, items in sorted(by_file.items()):
        symbol = items[0]["symbol"]
        path = pdf_for(Path(args.pdfs), symbol, items[0]["period"], files)
        if path is None:
            skipped["no local PDF"] += len(items)
            continue
        model = xk.read_pdf(path)
        wanted = [r for r in items if r.get("expected_cr") not in (None, "")]
        skipped["not_printed (blank in the key)"] += len(items) - len(wanted)
        expected = [xk.Expected(f"key:{symbol}", symbol, r["basis"], r["period"], r["metric"], float(r["expected_cr"])) for r in wanted]
        results = xk.locate_in(model, expected)
        for k, (r, e) in enumerate(zip(wanted, expected)):
            # a lender's "revenue" in the key is its interest earned when its page prints no revenue from operations
            if e.metric == "revenue" and results[k].status != "found_unique" and re.search(r"lender|bank", r["tags"]):
                alt = xk.locate_in(model, [xk.Expected(e.news_id, e.symbol, e.basis, e.period, "interest_earned", e.value)])[0]
                if alt.status == "found_unique":
                    alt.expected, alt.note = e, "interest earned line, for a lender's revenue"
                    results[k] = alt
        for r, e, res in zip(wanted, expected, results):
            key_page = int(r["page"]) if r.get("page") else None
            where = value_printed_anywhere(model, e, key_page) if res.status != "found_unique" else []
            if res.status == "found_unique":
                if key_page is None or res.page == key_page:
                    verdict = "right place"
                elif value_printed_anywhere(model, e, key_page):
                    verdict = "another page; the value is also on the key's page"
                else:
                    verdict = "wrong page"
            elif res.status == "found_ambiguous":
                pages = {p["page"] for p in res.placements}
                verdict = "ambiguous, key page among them" if key_page in pages else "ambiguous"
            elif res.status == "row_found_other_value":
                verdict = "other value at the key's row and column (the locator's miss, the key being the printed truth)"
            else:
                verdict = "value in the text layer of the page" if where else "value not in the text layer of the page"
            out_rows.append({"symbol": symbol, "basis": r["basis"], "period": r["period"], "metric": r["metric"],
                             "expected_cr": r["expected_cr"], "unit_printed": r["unit_printed"], "key_page": key_page or "",
                             "status": res.status, "verdict": verdict, "page": res.page or "", "printed": res.printed_text,
                             "unit": res.printed_unit, "row_label": res.row_label[:60], "column": res.column_header,
                             "n_strong": res.n_strong, "failure_stage": res.failure_stage, "other_value": res.other_value, "note": res.note,
                             "value_cells": " | ".join(where[:3]), "tags": r["tags"]})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "locator-vs-key.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0]) if out_rows else ["symbol"], lineterminator="\n")
        w.writeheader()
        w.writerows(out_rows)
    status = Counter(r["status"] for r in out_rows)
    verdict = Counter(r["verdict"] for r in out_rows)
    stages = Counter(r["failure_stage"] for r in out_rows if r["failure_stage"])
    by_unit = defaultdict(Counter)
    by_tag = defaultdict(Counter)
    for r in out_rows:
        by_unit[r["unit_printed"]][r["status"]] += 1
        for t in r["tags"].split("|"):
            by_tag[t][r["status"]] += 1
    summary = {"figures": len(out_rows), "skipped": dict(skipped), "status": dict(status), "verdict": dict(verdict), "failure_stage": dict(stages),
               "by_unit": {k: dict(v) for k, v in by_unit.items()}, "by_tag": {k: dict(v) for k, v in sorted(by_tag.items())}}
    (out / "locator-vs-key.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
