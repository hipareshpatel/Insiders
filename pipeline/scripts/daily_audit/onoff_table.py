"""On/off over stored results tables (no AI): every line whose value, comparative or change differs between two versions
of dossier.py, for blind reviewers. OFF is a copy of dossier.py from before the change (e.g. `git show
origin/main:pipeline/src/bse_intel/dossier.py`); ON is the working tree. Each table is rebuilt from the company's memory
as it is now.

    python -I onoff_table.py <cards.json> <dossier_off.py> <out.json>
cards.json: a list of feed cards (/api/feed pages)."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
import bse_intel  # noqa: E402,F401
from bse_intel import dossier as on  # noqa: E402

API = "https://insiders.reply-bd3.workers.dev/api"
SLOTS = ("value", "prev_year", "prev_quarter", "yoy_pct", "qoq_pct", "yoy_bps", "qoq_bps", "yoy_turn", "qoq_turn")


def load_off(path: str):
    spec = importlib.util.spec_from_file_location("bse_intel.dossier_off", path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "bse_intel"
    spec.loader.exec_module(module)
    return module


def table(mod, memory: dict, card: dict) -> dict | None:
    if card["event_category"] == "RESULTS":
        return mod.results_snapshot(memory, card["news_id"])
    return mod.call_results_snapshot(memory, card["filed_at"])


def main() -> None:
    cards = [c for c in json.load(open(sys.argv[1], encoding="utf-8"))
             if c.get("event_category") in ("RESULTS", "CONCALL_PRESENTATION")]
    off_mod = load_off(sys.argv[2])
    memories, rows, judged, failed = {}, [], 0, 0
    for card in cards:
        scrip = card["scrip_code"]
        if scrip not in memories:
            memories[scrip] = json.loads(subprocess.check_output(["curl", "-s", f"{API}/companies/{scrip}"], timeout=120))["dossier"]
        try:
            off, new = table(off_mod, memories[scrip], card), table(on, memories[scrip], card)
        except Exception as exc:  # noqa: BLE001 - one table must not stop the run; counted
            failed += 1
            print("FAILED", card["news_id"], exc, flush=True)
            continue
        if not off and not new:
            continue
        judged += 1
        for key in sorted(set(off or {}) | set(new or {})):
            a, b = (off or {}).get(key), (new or {}).get(key)
            if not (isinstance(a, dict) and "value" in a) and not (isinstance(b, dict) and "value" in b):
                continue
            pa = {s: a.get(s) for s in SLOTS} if isinstance(a, dict) else None
            pb = {s: b.get(s) for s in SLOTS} if isinstance(b, dict) else None
            if pa != pb:
                rows.append({"news_id": card["news_id"], "symbol": card["symbol"], "scrip_code": scrip,
                             "event": card["event_category"], "pdf_url": card.get("pdf_url"),
                             "period": (new or off)["period"], "line": key, "off": pa, "on": pb})
    json.dump({"tables_judged": judged, "failed": failed, "changed": rows}, open(sys.argv[3], "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("judged", judged, "failed", failed, "changed lines", len(rows))


if __name__ == "__main__":
    main()
