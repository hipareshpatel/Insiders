"""Measure the quarterly governance XBRL (governance_xbrl.py) over a quarter's filings on NSE.

    python scripts/governance_scan.py --quarter 30-SEP-2026 --sample 200 --seed 7 [--cache ../data/bench/governance]

Reads NSE's all-company list (`/api/integrated-filing-results?type=Integrated Filing- Governance`), keeps the latest
file per company for the quarter (a revision's time is `revised_Date`, an original's `broadcast_Date`), draws a sample
by seed, parses each file and counts the exceptions by kind. Read-only; files are cached.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import re
from datetime import datetime
from pathlib import Path

from bse_intel import governance_xbrl as g
from bse_intel.nse import SITE, NseClient

LIST = f"{SITE}/api/integrated-filing-results"


def _when(row: dict) -> datetime:
    for key in ("revised_Date", "broadcast_Date", "creation_Date"):
        value = (row.get(key) or "").strip()
        for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%B-%Y %H:%M:%S"):
            try:
                return datetime.strptime(value.title(), fmt)
            except ValueError:
                continue
    return datetime.min


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarter", default="30-SEP-2026")
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--cache", default="../data/bench/governance")
    ap.add_argument("--report")
    args = ap.parse_args()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    with NseClient() as nse:
        rows = []
        for page in range(1, args.pages + 1):
            body = nse._get(LIST, {"type": "Integrated Filing- Governance", "page": page, "size": 1000}).json()
            rows += body.get("data") or []
        latest: dict[str, dict] = {}
        for row in rows:
            if row.get("qe_Date") != args.quarter or not str(row.get("xbrl", "")).endswith(".xml"):
                continue
            if row["symbol"] not in latest or _when(row) > _when(latest[row["symbol"]]):
                latest[row["symbol"]] = row
        symbols = sorted(latest)
        random.Random(args.seed).shuffle(symbols)
        picked = symbols[:args.sample]
        print(f"{len(rows)} rows read, {len(latest)} companies with a file for {args.quarter}; {len(picked)} drawn")
        kinds = collections.Counter()
        examples: dict[str, list[str]] = collections.defaultdict(list)
        parsed = 0
        for symbol in picked:
            url = latest[symbol]["xbrl"]
            path = cache / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".xml")
            if not path.exists():
                try:
                    path.write_bytes(nse._get(url).content)
                except Exception as exc:  # a missing file is a result, not a stop
                    print("  fetch failed", symbol, exc)
                    continue
            report = g.parse(path.read_bytes())
            if report is None:
                kinds["unreadable"] += 1
                continue
            parsed += 1
            seen = set()
            for e in report.exceptions():
                kind = re.sub(r"[:(].*", "", e).replace("₹", "").strip()
                kind = re.sub(r"fine or penalty.*", "fine or penalty (>= ₹1 lakh or amount not stated)", kind)
                kind = re.sub(r"^(guarantee or comfort|loan|security) to .*", r"\1 to insiders", kind)
                if kind not in seen:
                    seen.add(kind)
                    kinds[kind] += 1
                    if len(examples[kind]) < 3:
                        examples[kind].append(f"{symbol}: {e[:140]}")
            kinds["any exception"] += bool(seen)
            kinds["penalty of any size"] += bool(report.penalties)
            kinds["tax litigation update"] += bool(report.tax_litigation)
            kinds["chair related to MD/CEO"] += bool(report.chair_related_to_md)
        print(f"parsed {parsed}")
        for kind, n in kinds.most_common():
            print(f"  {kind}: {n}")
            for ex in examples.get(kind, []):
                print(f"      {ex}")
        if args.report:
            Path(args.report).write_text(json.dumps({"parsed": parsed, "counts": kinds, "examples": examples}, indent=1))


if __name__ == "__main__":
    main()
