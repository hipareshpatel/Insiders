"""Round 7's export: audit_export.py with the card blocks the site shows since efbe96b (TASKS T3, 2026-10-20).

  python -I -X utf8 scripts/audit_round7/export.py OUT.json DIR --blind --memory http://localhost:5173 --random 20261023 --limit 0

The reviewers judge the card's face as published. Since efbe96b that face includes blocks that audit_export.py's KEEP
list leaves out: the results table (`results`, with its `lines`, the previous-quarter and year-ago columns), the size
of an order or deal (`scale`), the rating move (`rating_change`), the case steps (`case_stage`), "Management said"
(`guidance_recall`) and the price at filing that "Since the filing" and the run-rate P/E are computed from
(`priced_at_filing`). Without them a reviewer cannot mark a wrong figure in a block WRONG. Same arguments as
audit_export.py; nothing else changes.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import audit_export  # noqa: E402

BLOCKS = ("results", "scale", "rating_change", "case_stage", "guidance_recall", "priced_at_filing", "fundamentals")
audit_export.KEEP = tuple(audit_export.KEEP) + tuple(b for b in BLOCKS if b not in audit_export.KEEP)

if __name__ == "__main__":
    raise SystemExit(audit_export.main())
