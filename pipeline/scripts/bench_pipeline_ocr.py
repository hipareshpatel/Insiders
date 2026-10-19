"""The pipeline's own OCR (bse_intel.ocr, exactly as analyze() calls it) on both benchmark sets, so its
numbers can be compared with the engines measured on their own.

    python scripts/bench_pipeline_ocr.py BENCH_DIR [--dpi 200] [--as-pipeline] [--hard-only]
Writes BENCH_DIR/out/pipeline-ocr.json (results set, rows for bench_score.py) and
BENCH_DIR/hard/out/pipeline-ocr.json (complicated pages, lines for bench_hard_grade.py).

--as-pipeline reads every page the way analyze() now does (extract.Document.page_text): local OCR on a
page of figures with the text layer's nils put back, the text layer on every other page. Written as
pipeline-reader.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pymupdf  # noqa: E402

from bench_pymupdf import split_line  # noqa: E402
from bse_intel import ocr  # noqa: E402
from bse_intel.extract import Document  # noqa: E402

HARD = {"A_novartis_statement": ("2ed299f9", 3), "B_jubilant_aoc1_left": ("a42957c1", 214),
        "C_ahluwalia_ppe_note": ("56a8f73b", 162), "D_kanoria_governance_grid": ("69b11463", 2),
        "E_sml_rating_letter": ("c6b7260b", 0), "F_kanoria_statement": ("83d503cf", 8),
        "G_jubilant_results": ("3eec0c2f", 8)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bench")
    ap.add_argument("--dpi", type=int, default=ocr.DPI)
    ap.add_argument("--as-pipeline", action="store_true")
    ap.add_argument("--hard-only", action="store_true", help="the seven complicated pages only")
    args = ap.parse_args()
    name = "pipeline-reader.json" if args.as_pipeline else "pipeline-ocr.json"
    bench = Path(args.bench)
    assert ocr.available(), "install the ocr extra: pip install -e .[ocr]"
    times = []

    documents: dict[Path, Document] = {}

    def read(page) -> str:
        t = time.monotonic()
        if args.as_pipeline:
            path = Path(page.parent.name)
            if path not in documents:
                documents[path] = Document(path.read_bytes(), ocr=ocr.page_reader(None), max_ocr_pages=10**6,
                                           figure_reader=ocr.recognise, max_figure_pages=10**6, dpi=args.dpi)
            text = documents[path].page_text(page.number)
        else:
            text = ocr.recognise(page.get_pixmap(dpi=args.dpi).tobytes("png"))
        times.append(time.monotonic() - t)
        return text

    hard = {}
    for key, (prefix, idx) in HARD.items():
        doc = pymupdf.open(next((bench / "pages" / "pdfs").glob(f"{prefix}*.pdf")))
        hard[key] = read(doc[idx]).splitlines()
        print(f"  {key:28} {times[-1]:.1f}s", flush=True)
    (bench / "hard" / "out" / name).write_text(json.dumps(hard, ensure_ascii=False), encoding="utf-8")
    if args.hard_only:
        return 0

    results = {}
    for item in json.loads((bench / "manifest.json").read_text(encoding="utf-8")):
        doc = pymupdf.open(bench / item["pdf"])
        rows = []
        for i, page in enumerate(doc):
            rows += [{"page": i + 1, **split_line(re.sub(r"\s{2,}", " ", line))} for line in read(page).splitlines()]
        results[item["news_id"]] = rows
        print(f"  {item['news_id'][:8]} {item['company'][:20]:20} {doc.page_count:>3}p", flush=True)
    (bench / "out" / name).write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    print(f"{len(times)} pages, mean {sum(times) / len(times):.1f}s a page")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
