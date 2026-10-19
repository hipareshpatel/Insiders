"""The vision route on the complicated pages, exactly as the pipeline calls it (render at 150 dpi, the
gateway's own transcription prompt, the route's own choice of model), for bench_hard_grade.py.

    python scripts/bench_hard_vision.py HARD_DIR [--dpi 150] [--name vision-route]
Needs the provider keys in the environment (laptop.ps1 or the keys file). Free models only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pymupdf  # noqa: E402

from bse_intel.ai.gateway import AIGateway  # noqa: E402
from bse_intel.settings import get_settings  # noqa: E402

PAGES = {"A_novartis_statement": ("2ed299f9", 3), "B_jubilant_aoc1_left": ("a42957c1", 214),
         "C_ahluwalia_ppe_note": ("56a8f73b", 162), "D_kanoria_governance_grid": ("69b11463", 2),
         "E_sml_rating_letter": ("c6b7260b", 0), "F_kanoria_statement": ("83d503cf", 8),
         "G_jubilant_results": ("3eec0c2f", 8)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("hard")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--name", default="vision-route")
    args = ap.parse_args()
    hard = Path(args.hard)
    pdfs = hard.parent / "pages" / "pdfs"
    gateway = AIGateway(get_settings().load_toml("providers.toml"))
    out, log = {}, {}
    for key, (prefix, idx) in PAGES.items():
        pdf = pymupdf.open(next(pdfs.glob(f"{prefix}*.pdf")))
        png = pdf[idx].get_pixmap(dpi=args.dpi).tobytes("png")
        before = {k: v.requests for k, v in gateway.usage.items()}
        t = time.monotonic()
        try:
            text = gateway.transcribe_image(png)
        except Exception as exc:
            text, log[key] = "", f"failed: {type(exc).__name__}: {str(exc)[:120]}"
        used = [k for k, v in gateway.usage.items() if v.requests > before.get(k, 0)]
        log.setdefault(key, f"{time.monotonic() - t:.1f}s via {', '.join(used) or '?'}, {len(text):,} chars")
        out[key] = [l.replace("|", " ") for l in text.splitlines() if l.strip(" |-:")]
        print(f"{key:28} {log[key]}", flush=True)
    (hard / "out" / f"{args.name}.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    (hard / "out" / f"{args.name}.log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
