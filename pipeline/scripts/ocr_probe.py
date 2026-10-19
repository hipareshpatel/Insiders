"""Does RapidOCR run on a GitHub-hosted runner, how fast, and how much of a page does it recover?
Read-only: NSE's announcement list, a handful of its PDFs, a few pages of each rendered and OCR'd.
Each page's text layer is the answer key where it has one (a good text layer is an exact transcript
of the page): the share of its figures that OCR also reads. Writes nothing, calls no AI model.

    python scripts/ocr_probe.py [--files 8] [--pages 3] [--dpi 150] [--report probe.md]
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import timedelta

import pymupdf

from bse_intel.nse import SITE, NseClient
from bse_intel.timeutil import today_ist

ANNOUNCEMENTS = f"{SITE}/api/corporate-announcements"
FIGURE = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?")
# Kinds of filing worth a card, so the sample is what the pipeline would actually read.
WANTED = re.compile(r"result|outcome|presentation|order|acqui|credit rating|allot|press release", re.I)


def figures(text: str) -> list[str]:
    """Figures with at least two digits, normalised to their digits (grouping and brackets aside)."""
    out = []
    for raw in FIGURE.findall(text):
        digits = re.sub(r"[^\d.]", "", raw)
        if sum(ch.isdigit() for ch in digits) >= 2:
            out.append(digits)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", type=int, default=8)
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--report")
    args = parser.parse_args()

    started = time.monotonic()
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR()
    load_s = time.monotonic() - started

    today = today_ist()
    lines: list[str] = []
    with NseClient() as nse:
        listed = nse._get(ANNOUNCEMENTS, {"index": "equities",
                                          "from_date": (today - timedelta(days=3)).strftime("%d-%m-%Y"),
                                          "to_date": today.strftime("%d-%m-%Y")}).json()
        rows = listed if isinstance(listed, list) else listed.get("data", [])
        picks, seen = [], set()
        for r in rows:
            url = r.get("attchmntFile") or ""
            if url.lower().endswith(".pdf") and WANTED.search(f"{r.get('desc', '')} {r.get('attchmntText', '')}") \
                    and r.get("symbol") not in seen:
                seen.add(r.get("symbol"))
                picks.append(r)
            if len(picks) >= args.files:
                break
        lines.append(f"NSE listed {len(rows):,} announcements over 4 days; {len(picks)} PDFs taken, "
                     f"up to {args.pages} pages each. OCR engine loaded in {load_s:.1f} s.")

        table = ["| Filing | Page | Text layer chars | OCR chars | OCR seconds | Text-layer figures OCR also read |",
                 "|---|---|---|---|---|---|"]
        total_pages = total_s = 0.0
        hit = key = 0
        for r in picks:
            label = f"{r.get('symbol')} {str(r.get('desc', ''))[:40]}".replace("|", "/")
            try:
                body = nse._client.get(r["attchmntFile"], timeout=60).content
                doc = pymupdf.open(stream=body, filetype="pdf")
            except Exception as exc:  # one bad file does not end the probe
                table.append(f"| {label} | - | download or open failed: {type(exc).__name__} | | | |")
                continue
            for index in range(min(args.pages, doc.page_count)):
                page = doc[index]
                layer = page.get_text("text", sort=True)
                png = page.get_pixmap(dpi=args.dpi).tobytes("png")
                t0 = time.monotonic()
                result, _ = engine(png)
                seconds = time.monotonic() - t0
                ocr = "\n".join(item[1] for item in (result or []))
                total_pages += 1
                total_s += seconds
                expected = figures(layer)
                if len(layer.strip()) >= 80 and expected:
                    got = set(figures(ocr))
                    found = sum(1 for f in expected if f in got)
                    hit, key = hit + found, key + len(expected)
                    share = f"{found}/{len(expected)} ({found / len(expected):.0%})"
                else:
                    share = "no text layer to compare" if len(layer.strip()) < 80 else "no figures"
                table.append(f"| {label} | {index + 1} | {len(layer.strip()):,} | {len(ocr):,} | {seconds:.1f} | {share} |")
            doc.close()

    summary = [f"## RapidOCR at {args.dpi} dpi: {int(total_pages)} pages, "
               f"{(total_s / total_pages if total_pages else 0):.1f} s a page on average", ""]
    if key:
        summary.append(f"Figures in the text layer that OCR also read: {hit:,} of {key:,} ({hit / key:.1%}).")
    report = "\n".join(summary + lines + [""] + table) + "\n"
    print(report)
    if args.report:
        with open(args.report, "a", encoding="utf-8") as fh:
            fh.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
