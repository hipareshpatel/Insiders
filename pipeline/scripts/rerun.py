"""Reset chosen filings so they can be analysed again, for a measured round.

An audit names the cards that came out wrong. A fix is only proven when those same filings are read
again and the new cards are better, so this puts them back in the queue: the card is deleted, the
filing goes back to PENDING and its attempt count is cleared. Memory is left alone - re-analysing a
filing replaces that filing's own entry, so a card is never counted twice.

    python scripts/rerun.py --from-audit ../docs/audit/round-1.json --verdict WRONG --limit 20 > ids.txt
    python -m bse_intel process --from 2025-01-01 --to 2026-12-31 --bulk --news-ids @ids.txt

Nothing may be writing to the database while this runs (stop the local web server first).
"""
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from pathlib import Path

DB_GLOB = "data/wrangler/v3/d1/miniflare-D1DatabaseObject/*.sqlite"


def find_db(root: Path) -> Path:
    files = [p for p in root.glob(DB_GLOB) if p.name != "metadata.sqlite"]
    if len(files) != 1:
        raise SystemExit(f"expected one D1 database under {root / DB_GLOB}, found {len(files)}")
    return files[0]


def stratified(rows: list[dict], limit: int) -> list[dict]:
    """A sample that covers every error class at least once before it doubles up on any.

    Taking the newest or the first N would have left whole classes of defect unmeasured: round 1's
    wrong cards run from one issue to six, and the rarest classes sit on single cards.
    """
    remaining, chosen = list(rows), []
    seen: collections.Counter = collections.Counter()
    while remaining and len(chosen) < limit:
        def gain(row):
            classes = {i["class"] if isinstance(i, dict) else i for i in row.get("issues", [])}
            return (-sum(1 for c in classes if not seen[c]), sum(seen[c] for c in classes))
        best = min(remaining, key=gain)
        remaining.remove(best)
        chosen.append(best)
        for issue in best.get("issues", []):
            seen[issue["class"] if isinstance(issue, dict) else issue] += 1
    return chosen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("news_ids", nargs="*")
    ap.add_argument("--from-audit", help="an audit JSON written by audit_export.py")
    ap.add_argument("--verdict", default="WRONG")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--root", default=".", help="repository root (default: the working directory)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ids = list(args.news_ids)
    if args.from_audit:
        rows = [r for r in json.loads(Path(args.from_audit).read_text(encoding="utf-8"))
                if r.get("verdict") == args.verdict]
        rows = stratified(rows, args.limit) if args.limit else rows
        ids += [r["news_id"] for r in rows]
    ids = list(dict.fromkeys(i for i in ids if i))
    if not ids:
        raise SystemExit("no news ids given")

    db = find_db(Path(args.root))
    conn = sqlite3.connect(db)
    marks = ",".join("?" * len(ids))
    known = {r[0] for r in conn.execute(f"select news_id from filings where news_id in ({marks})", ids)}
    missing = [i for i in ids if i not in known]
    if missing:
        print(f"not in filings, skipped: {', '.join(i[:8] for i in missing)}", file=sys.stderr)
    if args.dry_run:
        print("\n".join(sorted(known)))
        return 0
    cards = conn.execute(f"delete from cards where news_id in ({marks})", ids).rowcount
    queued = conn.execute(
        f"update filings set status = 'PENDING', attempts = 0, last_error = null where news_id in ({marks})",
        ids).rowcount
    conn.commit()
    print(f"{cards} cards deleted, {queued} filings back in the queue", file=sys.stderr)
    print("\n".join(sorted(known)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
