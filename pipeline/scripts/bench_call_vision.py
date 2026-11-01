"""Option B measurement (owner, 1 Nov 2026; TODO 101/144): replay the blind-judged call-memory deck points through the slide
vision check (call_memory.vision_confirm, switch CALL_MEMORY_VISION_CHECK) and count, against the judges' verdicts, the WRONG
points it keeps and the RIGHT points it drops.

  python scripts/bench_call_vision.py --pdf-dir DIR [--judged docs/bench/geometry/judged-2026-10-31] [--out result.json]

`--pdf-dir` holds `<news_id>.pdf` for the 9 decks (the `deck-pdfs` artifact of run 41069401462, named by news id); this script
downloads nothing. Needs the provider keys of the free `vision` route (providers.toml); no paid route is used. An assembled
point is one whose stored `quote_assembled` is true (set by call_memory.check_points: the quote is not one run of the slide
text); every other point is kept untouched, as in production. Bar: WRONG kept / all kept <= 2% with few RIGHT dropped.
"""
from __future__ import annotations

import argparse
import os
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pymupdf  # noqa: E402

from bse_intel import call_memory  # noqa: E402
from bse_intel.ai.gateway import AIGateway  # noqa: E402
from bse_intel.models import CallPoint  # noqa: E402
from bse_intel.settings import get_settings  # noqa: E402


def _fetch_missing(news_ids: list[str], pdfs: Path) -> list[str]:
    """Each judged deck missing from ``pdfs`` fetched from its filing: the card's pdf_url from the site's public card page, the file
    from NSE's archive with the project's own client (nse.NseClient.fetch). Returns the ones still missing."""
    import httpx
    from bse_intel.nse import NseClient

    site = os.environ.get("SITE_URL", "https://insiders.reply-bd3.workers.dev")
    client, left = NseClient(), []
    pdfs.mkdir(parents=True, exist_ok=True)
    for news_id in news_ids:
        try:
            card = httpx.get(f"{site}/api/cards/{news_id}", timeout=30, headers={"User-Agent": "Mozilla/5.0"}).json()
            url = (card.get("card") or card).get("pdf_url")
            data = client.fetch(url) if url else None
        except Exception as exc:   # noqa: BLE001 - a deck we cannot get stays missing and is reported
            print(f"{news_id}: not fetched ({type(exc).__name__})", file=sys.stderr)
            data = None
        if data:
            (pdfs / f"{news_id}.pdf").write_bytes(data)
        else:
            left.append(news_id)
    return left


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--judged", default=str(root / "docs/bench/geometry/judged-2026-10-31"))
    ap.add_argument("--out")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("--max-calls", type=int, default=call_memory.VISION_MAX_CALLS)
    ap.add_argument("--fetch-missing", action="store_true",
                    help="download a judged deck not in --pdf-dir from its filing (pdf_url from the site's card page; NSE's archive)")
    args = ap.parse_args()
    judged, pdfs = Path(args.judged), Path(args.pdf_dir)
    verdicts = {v["id"]: v["verdict"] for v in json.loads((judged / "verdicts.json").read_text(encoding="utf-8"))}
    rows = [json.loads(line) for line in (judged / "to_judge.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    stored: dict[str, CallPoint] = {}
    for f in sorted((judged / "points").glob("*.json")):
        for raw in json.loads(f.read_text(encoding="utf-8")):
            stored[raw["id"]] = CallPoint.model_validate(raw)
    news_ids = sorted({r["news_id"] for r in rows})
    missing = [n for n in news_ids if not (pdfs / f"{n}.pdf").exists()]
    if missing and args.fetch_missing:
        missing = _fetch_missing(missing, pdfs)
    if missing:
        print(f"missing PDFs in {pdfs}: {', '.join(missing)}\n(dispatch the maintenance job that kept `deck-pdfs`, run 41069401462, "
              "and download that artifact here)", file=sys.stderr)
        return 2
    gateway = AIGateway(get_settings().load_toml("providers.toml"))
    if not gateway.has_route("vision"):
        print("no key for any `vision` route target (providers.toml)", file=sys.stderr)
        return 2

    tally = {"assembled": 0, "WRONG_kept": 0, "WRONG_dropped": 0, "RIGHT_kept": 0, "RIGHT_dropped": 0,
             "contiguous_WRONG": 0, "contiguous_RIGHT": 0}
    detail = []
    calls = [0]

    def ask(png: bytes, question: str):   # counts the requests actually made
        calls[0] += 1
        return gateway.ask_image(png, question)

    no_answer = 0
    for news_id in news_ids:
        doc = pymupdf.open(pdfs / f"{news_id}.pdf")
        points = [stored[r["id"]] for r in rows if r["news_id"] == news_id and r["id"] in stored]

        def render(page: int, doc=doc) -> bytes | None:
            return doc[page - 1].get_pixmap(dpi=args.dpi).tobytes("png") if 1 <= page <= doc.page_count else None

        kept, dropped = call_memory.vision_confirm(points, render, ask, args.max_calls)
        kept_ids = {p.id for p in kept}
        why = {d["point"]["id"]: d["detail"] for d in dropped}
        no_answer += sum(1 for d in dropped if not d["detail"].startswith("the slide does not"))
        for p in points:
            verdict = verdicts.get(p.id, "?")
            if verdict not in ("RIGHT", "WRONG"):
                continue
            if not p.quote_assembled:
                tally[f"contiguous_{verdict}"] += 1
                continue
            tally["assembled"] += 1
            tally[f"{verdict}_{'kept' if p.id in kept_ids else 'dropped'}"] += 1
            if p.quote_assembled and ((verdict == "WRONG") == (p.id in kept_ids)):   # the two errors
                detail.append({"id": p.id, "news_id": news_id, "verdict": verdict, "kept": p.id in kept_ids,
                               "why": why.get(p.id, ""), "statement": p.statement})
        print(f"{news_id}: {len(points)} points, {len(dropped)} dropped by vision", flush=True)
    wrong = tally["WRONG_kept"] + tally["contiguous_WRONG"]
    right = tally["RIGHT_kept"] + tally["contiguous_RIGHT"]
    total_right = right + tally["RIGHT_dropped"]
    kept_all = wrong + right
    kept_assembled = tally["WRONG_kept"] + tally["RIGHT_kept"]
    print(json.dumps(tally))
    print(f"assembled points {tally['assembled']}: kept {kept_assembled}, dropped {tally['assembled'] - kept_assembled} "
          f"({no_answer} of the dropped had no answer / no image / no call left); vision calls {calls[0]}; "
          f"WRONG kept {tally['WRONG_kept']}, RIGHT dropped {tally['RIGHT_dropped']}")
    print(f"WRONG kept {wrong} of {kept_all} kept = {wrong / max(kept_all, 1):.1%} (bar 2%); "
          f"RIGHT dropped {tally['RIGHT_dropped']} of {total_right} = {tally['RIGHT_dropped'] / max(total_right, 1):.1%}")
    if args.out:
        Path(args.out).write_text(json.dumps({"tally": tally, "calls": calls[0], "no_answer": no_answer, "errors": detail}, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
