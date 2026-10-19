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


def retriage(conn: sqlite3.Connection, ids: list[str]) -> int:
    """Route each filing as discovery would today, so a re-run also measures a rule fix: the annual reports
    pass 1 had typed RESULTS go to the ANNUAL_REPORT fast track (F57). A filing today's rules would drop or
    date is left as it was, and named: re-reading it measures the reading, not the rule."""
    from bse_intel.models import Filing
    from bse_intel.rules import RuleBook
    from bse_intel.settings import Settings

    rules = RuleBook.from_config(Settings().load_toml("taxonomy.toml"))
    marks = ",".join("?" * len(ids))
    changed = 0
    for row in conn.execute(f"select news_id, scrip_code, company_name, headline, subject, category, subcategory, "
                            f"filed_at, filing_date, route, event_type from filings where news_id in ({marks})", ids).fetchall():
        filing = Filing(news_id=row[0], scrip_code=row[1], company_name=row[2] or "", headline=row[3] or "",
                        subject=row[4] or "", category=row[5] or "", subcategory=row[6] or "", filed_at=row[7],
                        filing_date=row[8])
        decision = rules.classify(filing)
        if decision.action in ("DROP", "CALENDAR", "XBRL"):
            print(f"{row[0][:8]}: today's rules say {decision.action} ({decision.reason}); route left as {row[9]}",
                  file=sys.stderr)
            continue
        if (decision.action, decision.event_type) != (row[9], row[10]) and (decision.action != "PASS1" or row[9] != "PASS1"):
            conn.execute("update filings set route = ?, event_type = ? where news_id = ?",
                         (decision.action, decision.event_type, row[0]))
            changed += 1
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("news_ids", nargs="*")
    ap.add_argument("--from-audit", help="an audit JSON written by audit_export.py")
    ap.add_argument("--verdict", default="WRONG")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--root", default=".", help="repository root (default: the working directory)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ids = [i.strip() for i in args.news_ids]  # a Windows shell passes the file's CR along
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
    retyped = retriage(conn, ids)
    conn.commit()
    print(f"{cards} cards deleted, {queued} filings back in the queue, {retyped} routed again by today's rules",
          file=sys.stderr)
    print("\n".join(sorted(known)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
