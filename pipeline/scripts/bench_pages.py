"""A page-level OCR benchmark across announcement types, with the page's own text layer as the answer.

Results have XBRL to check against; every other announcement - order wins, ratings, acquisitions,
fundraises, litigation, presentations, transcripts - has nothing but its PDF. Many of those are
digital with a good text layer, and a good text layer is an exact transcript of the page. So: render
such a page to an image, OCR it, and compare with the text layer. That measures what an OCR engine
would get right on the pages that are scanned, for each kind of announcement, without anyone
labelling anything by hand.

    python scripts/bench_pages.py OUT_DIR [--per-type 6]

Writes OUT_DIR/pages.json (one entry per page: news_id, event type, page, the text layer's numbers
and words) and OUT_DIR/pdfs/<news_id>.pdf. Pages are chosen with many figures on them, since figures
are what a card gets wrong, and only where the text layer is readable.
"""
from __future__ import annotations

import argparse
import collections
import glob
import gzip
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bse_intel.bse import BseClient  # noqa: E402
from bse_intel.extract import SCANNED_PAGE_CHARS, text_unreadable  # noqa: E402
from bse_intel.settings import get_settings  # noqa: E402

NUMBER = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?%?")
WORD = re.compile(r"[A-Za-z]{3,}")


def figures(text: str) -> list[str]:
    """The figures on a page as a card would quote them: two digits or more, separators kept."""
    return [n for n in NUMBER.findall(text) if sum(ch.isdigit() for ch in n) >= 2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--per-type", type=int, default=6)
    args = ap.parse_args()
    out = Path(args.out)
    (out / "pdfs").mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    db = [p for p in glob.glob(str(root / "data/wrangler/v3/d1/miniflare-D1DatabaseObject/*.sqlite"))
          if "metadata" not in p][0]
    c = sqlite3.connect(db)
    meta = {r[0]: (r[1], r[2], r[3]) for r in c.execute(
        "select news_id, coalesce(event_type, 'OTHER'), pdf_url, company_name from filings")}
    candidates = collections.defaultdict(list)   # event type -> (figures on page, news_id, page, text)
    for p in glob.glob(str(get_settings().text_cache_dir / "*" / "*.json.gz")):
        nid = p.replace("\\", "/").rsplit("/", 1)[-1][:36]
        if nid not in meta or meta[nid][0] == "RESULTS" or not (meta[nid][1] or "").startswith("http"):
            continue
        d = json.loads(gzip.decompress(open(p, "rb").read()))
        for i, t in enumerate(d.get("digital") or []):
            if len(t.strip()) < max(SCANNED_PAGE_CHARS, 400) or text_unreadable(t):
                continue
            n = len(figures(t))
            if n >= 12:
                candidates[meta[nid][0]].append((n, nid, i, t))
    bse = BseClient()
    pages = []
    for etype, rows in sorted(candidates.items()):
        rows.sort(key=lambda r: -r[0])
        taken, seen_filings = 0, set()
        for n, nid, i, t in rows:
            if taken >= args.per_type or nid in seen_filings:
                continue
            pdf = out / "pdfs" / f"{nid}.pdf"
            if not pdf.exists():
                data = bse.download(meta[nid][1])
                if not data:
                    continue
                pdf.write_bytes(data)
            seen_filings.add(nid)
            taken += 1
            pages.append({"news_id": nid, "event_type": etype, "company": meta[nid][2], "page": i,
                          "pdf": f"pdfs/{nid}.pdf", "figures": figures(t), "words": WORD.findall(t)})
        print(f"  {etype:26} {taken} pages")
    (out / "pages.json").write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    print(f"{len(pages)} pages, {sum(len(p['figures']) for p in pages)} figures, "
          f"{len({p['event_type'] for p in pages})} announcement types")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
