"""Download NSE's official daily files for a date range, raw, for prices, market cap, liquidity and price adjustment
(owner, 2026-10-19: everything on NSE; Yahoo to be replaced). Nothing is parsed or written to the platform here: the
files are kept as NSE serves them, so they can be read later by whatever builds on them, and re-running skips what
is already on disk.

    python scripts/nse_archives.py --from 2025-04-01 [--to 2026-10-19] [--out ../data/nse/archives]

Per trading day (measured from the cloud 2026-10-19, all three answered):
* bhavcopy (UDiFF, since July 2024): `content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip`, every traded
  security's open, high, low, close, volume, value and trades;
* the "PR" archive: `archives/equities/bhavcopy/pr/PRDDMMYY.zip`, which holds `mcapDDMMYYYY.csv`, every listed
  company's issue size and market cap, plus the day's corporate-action and band files;
and per month, NSE's corporate actions (`/api/corporates-corporateActions`: splits, bonuses, dividends, by ex-date),
which the price history needs to be adjusted.

A weekend is skipped; a holiday answers 404 and is noted. NSE's own client paces the calls (3-5 s) and stops on a
refusal (401/403/429): the script then exits with the work done so far kept, and a re-run continues.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bse_intel.nse import SITE, NseClient, SourceBlockedError  # noqa: E402

BHAVCOPY = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
PR = "https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR{d:%d%m%y}.zip"
ACTIONS = f"{SITE}/api/corporates-corporateActions"


def _fetch(nse: NseClient, url: str, path: Path, report: dict, kind: str) -> None:
    if path.exists():
        report[f"{kind}_kept"] += 1
        return
    try:
        data = nse.fetch(url)
    except SourceBlockedError:
        raise
    except Exception as exc:  # one day's file failing must not end the download; a re-run tries it again
        report["errors"].append(f"{path.name}: {type(exc).__name__}: {exc}"[:200])
        return
    if data is None:
        report[f"{kind}_absent"] += 1   # a holiday (404), or not published yet
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    report[f"{kind}_saved"] += 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", default=date.today().isoformat())
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "data" / "nse" / "archives"))
    args = ap.parse_args()
    start, end, out = date.fromisoformat(args.start), date.fromisoformat(args.end), Path(args.out)
    report = {k: 0 for k in ("bhavcopy_saved", "bhavcopy_kept", "bhavcopy_absent", "pr_saved", "pr_kept", "pr_absent",
                             "action_months")}
    report["errors"] = []
    with NseClient() as nse:
        try:
            day = end
            while day >= start:   # newest first: the most useful days arrive first if the run is cut short
                if day.weekday() < 5:
                    _fetch(nse, BHAVCOPY.format(d=day), out / "bhavcopy" / f"{day:%Y}" / f"{day:%Y%m%d}.csv.zip",
                           report, "bhavcopy")
                    _fetch(nse, PR.format(d=day), out / "pr" / f"{day:%Y}" / f"PR{day:%Y%m%d}.zip", report, "pr")
                day -= timedelta(days=1)
            month = date(end.year, end.month, 1)
            while month >= date(start.year, start.month, 1):
                last = (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                path = out / "corporate_actions" / f"{month:%Y-%m}.json"
                if not path.exists() or month.year == end.year and month.month == end.month:
                    data = nse._get(ACTIONS, {"index": "equities", "from_date": f"{month:%d-%m-%Y}",
                                              "to_date": f"{min(last, end):%d-%m-%Y}"}).json()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                    report["action_months"] += 1
                month = (month - timedelta(days=1)).replace(day=1)
        except SourceBlockedError as exc:
            report["stopped"] = f"NSE refused: {exc}"[:200]
    print(json.dumps(report, indent=2))
    return 2 if report.get("stopped") else 0


if __name__ == "__main__":
    raise SystemExit(main())
