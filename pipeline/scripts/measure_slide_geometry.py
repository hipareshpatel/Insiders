"""TODO 144: measure the slide-geometry check (slide_geometry.py) on the blind-judged call-memory points.

Reads, for each document, its PDF (`--pdf-dir/<news_id>.pdf`, from our store or kept by an earlier run: this script
downloads nothing) and the page-reader flags of its stored text (`--texts/<news_id>/text.txt`, whose "===== PAGE n of N [ocr] ====="
markers say which pages are scanned and so read by OCR boxes). Each judged point (`--points DIR` with `<news_id>.json`
lists, `--verdicts` files of {id, verdict}) is run through `figure_label_verdict` on its page; the table says how many WRONG
and RIGHT points would be dropped (state "other" or "unproven") and how many are left alone ("tied", "unknown").

  python scripts/measure_slide_geometry.py --pdf-dir DIR --texts DIR --points blind150 --verdicts blind150/verdict_A.json blind150/verdict_B.json
  python scripts/measure_slide_geometry.py --pdf-dir DIR --texts DIR --points blindlive --verdicts blindlive/verdict.json

Runnable from a maintenance job once the deck PDFs are in a directory; it needs RapidOCR only for scanned pages.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bse_intel import slide_geometry as sg  # noqa: E402

_MARK = re.compile(r"=====\s*PAGE\s+(\d+)\s+of\s+\d+\s*\[(\w+)\]\s*=====")


def ocr_pages(text_file: Path) -> set[int]:
    try:
        return {int(n) for n, kind in _MARK.findall(text_file.read_text(encoding="utf-8")) if kind.lower() == "ocr"}
    except OSError:
        return set()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--texts", required=True)
    ap.add_argument("--points", required=True)
    ap.add_argument("--verdicts", nargs="+", required=True)
    ap.add_argument("--out", help="write every point's verdict as JSON here")
    args = ap.parse_args()

    judged: dict[str, str] = {}
    for f in args.verdicts:
        for v in json.loads(Path(f).read_text(encoding="utf-8")):
            if judged.get(v["id"]) != "WRONG":   # a point either reviewer calls wrong is wrong
                judged[v["id"]] = v["verdict"]
    cache: dict[tuple[str, int], list] = {}
    rows, table = [], Counter()
    for pts in sorted(Path(args.points).glob("nse-*.json")):
        news_id = pts.stem
        pdf = Path(args.pdf_dir) / f"{news_id}.pdf"
        scanned = ocr_pages(Path(args.texts) / news_id / "text.txt")
        data = pdf.read_bytes() if pdf.exists() else None
        for p in json.loads(pts.read_text(encoding="utf-8")):
            verdict = judged.get(p["id"])
            if verdict is None:
                continue   # not judged: not measured
            if data is None or p.get("value") is None or not p.get("page"):
                state, detail = "no-pdf", ""
            else:
                key = (news_id, p["page"])
                if key not in cache:
                    cache[key] = sg.page_words(data, p["page"], ocr=p["page"] in scanned)
                v = sg.figure_label_verdict(p["value"], p.get("quote", ""), cache[key], p.get("statement", ""))
                state, detail = v.state, v.detail
            dropped = state in ("other", "unproven")
            table[(verdict, "dropped" if dropped else "kept" if state != "no-pdf" else "no-pdf")] += 1
            table[(verdict, state)] += 1
            rows.append({"id": p["id"], "news_id": news_id, "page": p.get("page"), "judged": verdict, "state": state,
                         "detail": detail, "quote": p.get("quote")})
    print(f"{'judged':8} {'points':>7} {'dropped':>8} {'kept':>6} {'no pdf':>7}   by state")
    for verdict in ("WRONG", "RIGHT"):
        total = sum(table[(verdict, s)] for s in ("tied", "other", "unproven", "unknown", "no-pdf"))
        states = {s: table[(verdict, s)] for s in ("tied", "other", "unproven", "unknown", "no-pdf") if table[(verdict, s)]}
        measured = total - table[(verdict, "no-pdf")]
        d = table[(verdict, "dropped")]
        share = f"{100 * d / measured:.1f}%" if measured else "-"
        print(f"{verdict:8} {total:7} {d:8} {table[(verdict, 'kept')]:6} {table[(verdict, 'no-pdf')]:7}   {states}   dropped {share}")
    for r in rows:
        if r["state"] in ("other", "unproven") and r["judged"] == "RIGHT" or r["judged"] == "WRONG":
            print(f"  {r['judged']:5} {r['state']:8} {r['id']} p{r['page']}: {r['quote']!r} -- {r['detail']}")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
