"""The owner's verdicts on cards (private launch, owner 2026-10-19), tallied like a blind review round.

  python -I -X utf8 scripts/owner_verdicts.py [--db PATH] [--since YYYY-MM-DD]

Reads card_verdicts from the local D1 file (the laptop's site), or from a copy of the deployed database
(`wrangler d1 export bse-index --remote --table card_verdicts`, loaded into SQLite). Prints the share WRONG of
published and of held cards, per event type, and every WRONG and MINOR note, so each can be traced to its error
class (docs/DATA_QUALITY.md) before it is fixed.
"""
from __future__ import annotations

import argparse
import collections
import glob
import pathlib
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[2]


def local_db() -> str:
    files = [p for p in glob.glob(str(ROOT / "data/wrangler/v3/d1/miniflare-D1DatabaseObject/*.sqlite")) if "metadata" not in p]
    return files[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--since", default="2000-01-01")
    args = ap.parse_args()
    conn = sqlite3.connect(f"file:{args.db or local_db()}?mode=ro", uri=True)
    rows = list(conn.execute(
        "select news_id, scrip_code, event_category, verdict, note, held, created_at from card_verdicts "
        "where created_at >= ? order by created_at", (args.since,)))
    if not rows:
        print("no verdicts yet")
        return 0
    for label, part in (("published", [r for r in rows if not r[5]]), ("held", [r for r in rows if r[5]])):
        n = collections.Counter(r[3] for r in part)
        total = sum(n.values())
        share = f"{100 * n['WRONG'] / total:.0f}% WRONG" if total else "-"
        print(f"{label}: {total} judged, RIGHT {n['RIGHT']}, MINOR {n['MINOR']}, WRONG {n['WRONG']} ({share})")
    by_type = collections.defaultdict(collections.Counter)
    for r in rows:
        by_type[r[2] or "?"][r[3]] += 1
    print("\nby event type (RIGHT / MINOR / WRONG):")
    for event, n in sorted(by_type.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"  {event:28} {n['RIGHT']:3} {n['MINOR']:3} {n['WRONG']:3}")
    print("\nnotes:")
    for news_id, scrip, event, verdict, note, held, at in rows:
        if verdict != "RIGHT":
            print(f"  {verdict:5} {'held ' if held else ''}{scrip} {event} {news_id[:12]}: {note or '(no note)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
