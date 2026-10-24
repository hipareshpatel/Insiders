"""On/off over stored cards (no AI): which results-table comparatives the stated-change rule removes
(dossier.contradicted, wrong-card trace 25 Oct 2026). Each RESULTS and CONCALL_PRESENTATION card's table is rebuilt from
the company's memory as it is now, with the rule off and on; every line whose comparative goes is listed with the
filings' stated changes, for independent reviewers to check against the PDF.

    python -I onoff_stated.py <cards.json> <out.json>
cards.json: a list of feed cards (/api/feed pages)."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from bse_intel import dossier as d  # noqa: E402

API = "https://insiders.reply-bd3.workers.dev/api"


def fetch(url: str) -> dict:
    return json.loads(subprocess.check_output(["curl", "-s", url], timeout=120))


def table(memory: dict, card: dict, on: bool) -> dict | None:
    saved = d.STATED_POINTS
    d.STATED_POINTS = saved if on else float("inf")
    try:
        if card["event_category"] == "RESULTS":
            return d.results_snapshot(memory, card["news_id"])
        return d.call_results_snapshot(memory, card["filed_at"])
    finally:
        d.STATED_POINTS = saved


def main() -> None:
    cards = [c for c in json.load(open(sys.argv[1], encoding="utf-8"))
             if c.get("event_category") in ("RESULTS", "CONCALL_PRESENTATION")]
    memories, rows, judged = {}, [], 0
    for card in cards:
        scrip = card["scrip_code"]
        if scrip not in memories:
            memories[scrip] = fetch(f"{API}/companies/{scrip}")["dossier"]
        off, on = table(memories[scrip], card, False), table(memories[scrip], card, True)
        if not off:
            continue
        judged += 1
        for key, row in off.items():
            if not isinstance(row, dict) or "value" not in row:
                continue
            new = (on or {}).get(key) or {}
            for slot, change in (("prev_year", "yoy_pct"), ("prev_quarter", "qoq_pct")):
                if slot in row and slot not in new:
                    entry = next((m for m in memories[scrip]["financial_metrics"]
                                  if m["metric"] in dict(d._RESULT_METRICS).get(key, (key,)) and m["period"] == off["period"]), {})
                    rows.append({"news_id": card["news_id"], "symbol": card["symbol"], "event": card["event_category"],
                                 "pdf_url": card.get("pdf_url"), "period": off["period"], "line": key, "slot": slot,
                                 "value": row["value"], "comparative": row[slot], "change_removed": row.get(change),
                                 "stated": [{k: s.get(k) for k in ("news_id", "value", "yoy_pct", "qoq_pct")}
                                            for s in (entry.get("sources") or [entry])]})
        print(card["symbol"], card["event_category"], sum(r["news_id"] == card["news_id"] for r in rows), flush=True)
    json.dump({"cards_judged": judged, "removed": rows}, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("judged", judged, "removed", len(rows))


if __name__ == "__main__":
    main()
