"""Try named models on stored filings before they go on a route (owner, 24 Oct 2026: Gemma 4 on OpenRouter). No card
is published: the analysis runs with the local sink, and ONLY_MODEL sends every route that has one of the named models
to it alone (level 1 to one, card writing to another, in one pass).

    ONLY_MODEL=openrouter:google/gemma-4-26b-a4b-it:free,openrouter:google/gemma-4-31b-it:free \\
    BSE_INTEL_SINK=local python -I scripts/model_trial.py scripts/model_trial_filings.json out.json

Each filing: its PDF is downloaded, `analyze-pdf` runs it end to end (level 1 included, so the triage model is tried),
and the outcome, the writing model, the event type and the time taken are written to out.json for review."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


def download(url: str, dest: pathlib.Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.nseindia.com/"})
    with urllib.request.urlopen(request, timeout=120) as response:
        dest.write_bytes(response.read())


def main() -> None:
    filings = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    out_path = pathlib.Path(sys.argv[2])
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for f in filings:
            pdf = pathlib.Path(tmp) / f"{f['news_id']}.pdf"
            row = {"news_id": f["news_id"], "stored_event_type": f["event_type"], "only_model": os.environ.get("ONLY_MODEL")}
            try:
                download(f["pdf_url"], pdf)
            except Exception as exc:  # noqa: BLE001 - one bad download must not stop the trial
                rows.append({**row, "error": f"download: {exc}"[:300]})
                continue
            cmd = [sys.executable, "-m", "bse_intel", "analyze-pdf", str(pdf), "--scrip", f["scrip"],
                   "--company", f["company"], "--headline", f["headline"], "--news-id", f"trial-{f['news_id']}"]
            if f.get("industry"):
                cmd += ["--industry", f["industry"]]
            started = time.monotonic()
            run = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            row["seconds"] = round(time.monotonic() - started, 1)
            try:
                result = json.loads(run.stdout[run.stdout.index("{"):])
            except ValueError:
                rows.append({**row, "error": (run.stderr or run.stdout)[-1500:]})
                continue
            card = result.get("card") or {}
            body = card.get("card_json")
            body = json.loads(body) if isinstance(body, str) else (body or card)
            status = result.get("status") or {}
            row.update({"status": status.get("status") if isinstance(status, dict) else status,
                        "reason": status.get("reason") if isinstance(status, dict) else None,
                        "event_type": body.get("event_type") or (status.get("event_type") if isinstance(status, dict) else None),
                        "writer": body.get("model"), "headline": body.get("headline"), "card": body or None,
                        "gateway_log": [line[-240:] for line in run.stderr.splitlines()
                                        if "bse_intel.ai.gateway" in line or "openrouter" in line][-30:]})
            rows.append(row)
            print(f["news_id"], row.get("status"), row.get("event_type"), row.get("writer"), row["seconds"], flush=True)
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
