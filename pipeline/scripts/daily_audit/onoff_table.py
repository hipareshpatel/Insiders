"""On/off over stored results tables (no AI): every line whose value, comparative or change differs between two versions
of dossier.py, for blind reviewers. OFF is a copy of dossier.py from before the change (e.g. `git show
origin/main:pipeline/src/bse_intel/dossier.py`); ON is the working tree. Each table is rebuilt from the company's memory
as it is now.

    python -I onoff_table.py <cards.json> <dossier_off.py> <out.json> [--since 2026-10-25T09:00] [--pdf-dir DIR]
        [--memory-dir DIR]
cards.json: a list of feed cards (/api/feed pages). With --pdf-dir each filing's PDF is read with PyMuPDF (ext.py) and
its text passed as the pipeline passes it (the OCR the pipeline also runs is not, so a scanned page reads emptier).
--since keeps cards filed from that time: a re-measure on tables no change was tuned on. --memory-dir saves each
company's memory on first read and reuses it, so a measurement can be re-run on the same inputs."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
import bse_intel  # noqa: E402,F401
from bse_intel import dossier as on  # noqa: E402

API = "https://insiders.reply-bd3.workers.dev/api"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
SLOTS = ("value", "prev_year", "prev_quarter", "yoy_pct", "qoq_pct", "yoy_bps", "qoq_bps", "yoy_turn", "qoq_turn")


def load_off(path: str):
    spec = importlib.util.spec_from_file_location("bse_intel.dossier_off", path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "bse_intel"
    spec.loader.exec_module(module)
    return module


def text_of(card: dict, pdf_dir: str | None) -> str | None:
    if not pdf_dir or not card.get("pdf_url"):
        return None
    folder = pathlib.Path(pdf_dir) / card["news_id"]
    folder.mkdir(parents=True, exist_ok=True)
    pdf = folder / "filing.pdf"
    if not pdf.exists():
        subprocess.run(["curl", "-s", "-L", "-A", UA, "-H", "Referer: https://www.nseindia.com/", "-o", str(pdf),
                        card["pdf_url"]], timeout=180)
    ext = pathlib.Path(__file__).with_name("ext.py")
    return subprocess.run([sys.executable, "-I", str(ext), str(pdf)], capture_output=True, text=True).stdout or None


def memory_of(scrip: str, memory_dir: str | None) -> dict:
    """The company's memory as the live API gives it; with --memory-dir it is saved there on first read and read back
    from there after, so a re-run judges the same memory."""
    saved = pathlib.Path(memory_dir) / f"{scrip}.json" if memory_dir else None
    if saved and saved.exists():
        return json.loads(saved.read_text(encoding="utf-8"))
    for attempt in range(4):
        try:
            dossier = json.loads(subprocess.check_output(["curl", "-s", "--fail", f"{API}/companies/{scrip}"], timeout=120))["dossier"]
            break
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    if saved:
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_text(json.dumps(dossier, ensure_ascii=False), encoding="utf-8")
    return dossier


def table(mod, memory: dict, card: dict, text: str | None) -> dict | None:
    if card["event_category"] == "RESULTS":
        return mod.results_snapshot(memory, card["news_id"], printed=text)
    try:
        return mod.call_results_snapshot(memory, card["filed_at"], text=text)
    except TypeError:   # a version from before the text argument
        return mod.call_results_snapshot(memory, card["filed_at"])


def main() -> None:
    args = sys.argv[1:]
    since = args[args.index("--since") + 1] if "--since" in args else ""
    pdf_dir = args[args.index("--pdf-dir") + 1] if "--pdf-dir" in args else None
    memory_dir = args[args.index("--memory-dir") + 1] if "--memory-dir" in args else None
    cards = [c for c in json.load(open(args[0], encoding="utf-8"))
             if c.get("event_category") in ("RESULTS", "CONCALL_PRESENTATION") and (c.get("filed_at") or "") >= since]
    off_mod = load_off(args[1])
    memories, rows, judged, failed = {}, [], 0, 0
    for card in cards:
        scrip = card["scrip_code"]
        if scrip not in memories:
            memories[scrip] = memory_of(scrip, memory_dir)
        try:
            text = text_of(card, pdf_dir)
            off, new = table(off_mod, memories[scrip], card, text), table(on, memories[scrip], card, text)
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
    json.dump({"tables_judged": judged, "failed": failed, "changed": rows}, open(args[2], "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("judged", judged, "failed", failed, "changed lines", len(rows))


if __name__ == "__main__":
    main()
