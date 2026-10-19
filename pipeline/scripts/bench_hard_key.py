"""Merge two independent readings of the complicated pages into one answer key.

Two readers transcribed each page from its image, without any extraction tool and without seeing each
other's work. A cell enters the key only where both read it the same; every disagreement is listed so it
can be settled by looking at the page. That keeps one reader's slip - or the merger's - out of the key.

    python scripts/bench_hard_key.py HARD_DIR      (reads reader_a/key.json, reader_b/key.json)
Writes HARD_DIR/key.json (agreed rows; disputed cells as null) and HARD_DIR/disputes.json.
"""
from __future__ import annotations

import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

DASHES = {"–": "-", "—": "-", "−": "-"}


def norm(cell) -> str:
    s = " ".join(str(cell if cell is not None else "").split())
    for bad, good in DASHES.items():
        s = s.replace(bad, good)
    return s.replace(" ,", ",").replace("( ", "(").replace(" )", ")")


def main() -> int:
    hard = Path(sys.argv[1])
    a = json.loads((hard / "reader_a" / "key.json").read_text(encoding="utf-8"))
    b = json.loads((hard / "reader_b" / "key.json").read_text(encoding="utf-8"))
    key, disputes, stats = {}, [], {}
    for page in sorted(set(a) | set(b)):
        ra, rb = (a.get(page) or {}).get("rows", []), (b.get(page) or {}).get("rows", [])
        rows, agree, total = [], 0, 0
        for i in range(max(len(ra), len(rb))):
            x = ra[i] if i < len(ra) else None
            y = rb[i] if i < len(rb) else None
            if x is None or y is None:
                disputes.append({"page": page, "row": i, "issue": "only one reader has this row",
                                 "a": x, "b": y})
                continue
            la, lb = norm(x.get("label")), norm(y.get("label"))
            same_label = SequenceMatcher(None, la.lower(), lb.lower()).ratio() >= 0.85
            ca, cb = [norm(c) for c in x.get("cells", [])], [norm(c) for c in y.get("cells", [])]
            if len(ca) != len(cb) or not same_label:
                disputes.append({"page": page, "row": i, "issue": "rows do not line up", "a": x, "b": y})
                continue
            cells = []
            for j, (p, q) in enumerate(zip(ca, cb)):
                total += 1
                if p == q:
                    agree += 1
                    cells.append(p)
                else:
                    cells.append(None)
                    disputes.append({"page": page, "row": i, "label": la, "col": j, "a": p, "b": q})
            rows.append({"label": la if len(la) >= len(lb) else lb, "cells": cells})
        key[page] = {"columns": (a.get(page) or {}).get("columns") or (b.get(page) or {}).get("columns"),
                     "rows": rows}
        if "bullets" in (a.get(page) or {}):
            key[page]["bullets"] = {"a": a[page].get("bullets"), "b": (b.get(page) or {}).get("bullets")}
        stats[page] = f"{agree}/{total} cells agree, {len(rows)} rows"
    (hard / "key.json").write_text(json.dumps(key, indent=1, ensure_ascii=False), encoding="utf-8")
    (hard / "disputes.json").write_text(json.dumps(disputes, indent=1, ensure_ascii=False), encoding="utf-8")
    for page, s in stats.items():
        print(f"  {page:28} {s}")
    print(f"{len(disputes)} disputes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
