"""Measure the join of NSE's event XBRL files to their announcements (PLAN 18 part 3; event_xbrl.py).

    python scripts/event_xbrl_join.py --from 13-10-2026 --to 18-10-2026 [--cache ../data/bench/event_xbrl]

Ground truth is the same file: the XBRL row points at the announcement's own attachment, re-attaches a PDF of exactly
its size, or zips a PDF of that size. On those pairs the content rule alone (event_xbrl.confirm, family or generic
subject) is scored: does it pick the announcement the file was filed with, and which other announcements of the
company does it also take (a press release of the same order is right to; a different order is not). Then the
whole join's coverage: how many files reach an announcement at all. Read-only; downloads are cached.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from datetime import datetime
from pathlib import Path

from bse_intel import event_xbrl as ex
from bse_intel.extract import Document
from bse_intel.nse import SITE, NseClient, parse_announcement


def _cached(nse: NseClient, url: str, cache: Path) -> bytes | None:
    path = cache / hashlib.sha1(url.encode()).hexdigest()[:16]
    if path.exists():
        data = path.read_bytes()
        return data or None
    try:
        data = nse.fetch(url) or b""
    except Exception as exc:  # a missing file is a result, not a stop
        print("  fetch failed", url, exc)
        data = b""
    path.write_bytes(data)
    return data or None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="day_from", required=True)
    ap.add_argument("--to", dest="day_to", required=True)
    ap.add_argument("--cache", default="../data/bench/event_xbrl")
    ap.add_argument("--report")
    args = ap.parse_args()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    lists = cache / f"lists_{args.day_from}_{args.day_to}.json"
    with NseClient() as nse:
        if lists.exists():
            raw = json.loads(lists.read_text())
        else:
            raw = {}
            for kind in ex.KINDS:
                body = nse._get(f"{SITE}/api/XBRL-announcements", {"index": "equities", "from_date": args.day_from,
                                                                   "to_date": args.day_to, "type": kind}).json()
                raw[kind] = body.get("data") if isinstance(body, dict) else body
            body = nse._get(f"{SITE}/api/corporate-announcements", {"index": "equities", "from_date": args.day_from,
                                                                    "to_date": args.day_to}).json()
            raw["ann"] = body.get("data") if isinstance(body, dict) else body
            lists.write_text(json.dumps(raw))
        # Director and KMP changes get no card (owner, 2026-10-18): their files are not joined
        files = [f for kind in ex.KINDS for f in ex.parse_list(raw[kind], kind) if f.family not in ex.NO_CARD_FAMILIES]
        filings = [f for f in (parse_announcement(r, lambda i, s: "1") for r in raw["ann"]) if f]
        by_symbol = collections.defaultdict(list)
        for f in filings:
            by_symbol[f.symbol].append(f)
        facts: dict[str, ex.EventFacts | None] = {}

        def read(file: ex.EventFile):
            if file.app_id not in facts:
                facts[file.app_id] = ex.parse(_cached(nse, file.xbrl_url, cache), file.app_id) if file.xbrl_url else None
            return facts[file.app_id]

        texts: dict[str, str] = {}

        def text(filing) -> str:
            if filing.news_id not in texts:
                pdf = _cached(nse, filing.pdf_url, cache) if filing.pdf_url and filing.pdf_url.lower().endswith(".pdf") else None
                try:
                    texts[filing.news_id] = Document(pdf).layer_text() if pdf else ""
                except Exception:
                    texts[filing.news_id] = ""
            return texts[filing.news_id]

        # Ground truth: the announcement each file was filed with
        truth: dict[str, str] = {}
        for file in files:
            near = [f for f in by_symbol.get(file.symbol, [])
                    if file.broadcast_at - ex.AFTER <= datetime.fromisoformat(f.filed_at) <= file.broadcast_at + ex.BEFORE]
            near = [f for f in near if f.pdf_url != file.xbrl_url]   # the zip's own announcement row is not the PDF
            same = [f for f in near if ex.same_file(file, f.pdf_url, f.attachment_size)]
            if not same and file.xbrl_url and file.xbrl_url.lower().endswith(".zip"):
                same = [f for f in near if ex.same_file(file, f.pdf_url, f.attachment_size, read(file))]
            if len(same) == 1:
                truth[file.app_id] = same[0].news_id
        print(f"{len(files)} files; {len(truth)} with a same-file announcement (ground truth)")

        # The content rule alone on the ground-truth files
        score = collections.Counter()
        others = []
        for file in files:
            if file.app_id not in truth:
                continue
            facts_ = read(file)
            if facts_ is None:
                score["xml unreadable"] += 1
                continue
            right = next(f for f in filings if f.news_id == truth[file.app_id])
            for f in by_symbol[file.symbol]:
                at = datetime.fromisoformat(f.filed_at)
                if not (at - ex.BEFORE <= file.broadcast_at <= at + ex.AFTER):
                    continue
                eligible = ex.family(f.subject) == file.family or ex.generic(f.subject)
                hit = eligible and ex.confirm(facts_, text(f), strict=ex.family(f.subject) != file.family)
                if f.news_id == right.news_id:
                    score["right announcement taken" if hit else "right announcement missed"] += 1
                    if not hit:
                        score[f"  missed: {'no text' if not text(f) else 'family' if not eligible else 'content'}"] += 1
                elif hit:
                    score["another announcement also taken"] += 1
                    others.append((file.symbol, file.event_type[:40], right.subject[:30], f.subject[:30], f.filed_at[:16],
                                   f.pdf_url and f.pdf_url.rsplit("/", 1)[-1][:50]))
        for k, v in sorted(score.items()):
            print(f"  {k}: {v}")
        print("other announcements the content rule also took (same event or a mistake? check by hand):")
        for row in others:
            print("   ", row)

        # Coverage: the whole join from the announcement side
        matched = collections.Counter()
        taken = collections.defaultdict(set)
        for f in filings:
            if not any(x.symbol == f.symbol for x in files):
                continue
            if not (ex.family(f.subject) or ex.generic(f.subject)):
                continue
            got, _ = ex.match(f, files, read, text(f))
            for m in got:
                taken[m.file.app_id].add((f.news_id, m.how))
                matched[m.how] += 1
        reached = len(taken)
        wrong = sum(1 for a, got in taken.items() if a in truth and truth[a] not in {n for n, _ in got})
        print(f"coverage: {reached} of {len(files)} files reach an announcement ({matched['same file']} same-file pairs,"
              f" {matched['content']} by content); ground-truth files joined elsewhere only: {wrong}")
        by_family = collections.Counter((x.family, x.app_id in taken) for x in files)
        for fam in sorted({k for k, _ in by_family}, key=str):
            print(f"  {fam}: {by_family[(fam, True)]} of {by_family[(fam, True)] + by_family[(fam, False)]}")
        if args.report:
            Path(args.report).write_text(json.dumps({"score": score, "others": others, "reached": reached,
                                                     "files": len(files), "truth": len(truth), "wrong": wrong,
                                                     "matched": matched}, default=list, indent=1))


if __name__ == "__main__":
    main()
