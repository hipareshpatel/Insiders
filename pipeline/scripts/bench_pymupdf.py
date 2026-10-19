"""Baselines for the benchmark, from the PDF library the pipeline already uses: no new dependency.

  text-default  page text in the order the file stores it (what the pipeline read until 2026-10-17)
  text-sorted   the same, in reading order (sort=True; what it reads now)
  find-tables   PyMuPDF's own table finder, one row per table row, cells kept apart
  words-rows    words grouped into lines by their position on the page, numbers kept in column order

    python scripts/bench_pymupdf.py BENCH_DIR
Writes BENCH_DIR/out/<engine>.json for bench_score.py.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pymupdf

_NUMERIC = re.compile(r"^\(?-?[\d,]+(?:\.\d+)?\)?%?$")


def split_line(line: str) -> dict:
    """A line of text as a label followed by its numeric cells.

    A serial or note number before the label ("2  Other income  92  217  358", Schedule III's note
    column) is not a figure: read as one, it took the label with it. Leading numbers are skipped when a
    label follows them; a line of figures alone (wrapped below its label) keeps them all.
    """
    tokens = line.split()
    lead = 0
    while lead < len(tokens) and _NUMERIC.match(tokens[lead]):
        lead += 1
    if lead == len(tokens):
        return {"label": "", "cells": tokens}
    rest = tokens[lead:]
    first_num = next((i for i, t in enumerate(rest) if _NUMERIC.match(t)), len(rest))
    return {"label": " ".join(rest[:first_num]), "cells": [t for t in rest[first_num:] if _NUMERIC.match(t)]}


def text_rows(page, sort: bool) -> list[dict]:
    return [split_line(l) for l in page.get_text("text", sort=sort).splitlines() if l.strip()]


def table_rows(page) -> list[dict]:
    rows = []
    try:
        tables = page.find_tables()
    except Exception:
        return rows
    for table in tables.tables:
        for row in table.extract():
            cells = [(c or "").replace("\n", " ").strip() for c in row]
            label = next((c for c in cells if c and not _NUMERIC.match(c.replace(" ", ""))), "")
            nums = [c for c in cells if c and _NUMERIC.match(c.replace(" ", ""))]
            rows.append({"label": label, "cells": nums})
    return rows


def word_rows(page, tolerance: float = 3.0) -> list[dict]:
    """Words on the same baseline are one row, read left to right: the table without its grid lines."""
    words = page.get_text("words")  # x0, y0, x1, y1, word, block, line, word_no
    lines: list[list] = []
    for w in sorted(words, key=lambda w: (round(w[3]), w[0])):
        if lines and abs(lines[-1][0][3] - w[3]) <= tolerance:
            lines[-1].append(w)
        else:
            lines.append([w])
    out = []
    for line in lines:
        text = " ".join(w[4] for w in sorted(line, key=lambda w: w[0]))
        out.append(split_line(text))
    return out


def main() -> int:
    bench = Path(sys.argv[1])
    manifest = json.loads((bench / "manifest.json").read_text(encoding="utf-8"))
    (bench / "out").mkdir(exist_ok=True)
    engines = {"text-default": lambda p: text_rows(p, False), "text-sorted": lambda p: text_rows(p, True),
               "find-tables": table_rows, "words-rows": word_rows}
    for name, fn in engines.items():
        started, result = time.monotonic(), {}
        for item in manifest:
            doc = pymupdf.open(bench / item["pdf"])
            rows = []
            for i, page in enumerate(doc):
                rows += [{"page": i + 1, **r} for r in fn(page)]
            result[item["news_id"]] = rows
        (bench / "out" / f"{name}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        print(f"{name}: {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__" and not (len(sys.argv) > 2 and sys.argv[2] == "joined"):
    raise SystemExit(main())


def joined_rows(page) -> list[dict]:
    """Reading-order lines, with a label-only line joined to the figures-only line that follows it.

    A long row label wraps ("Profit for the period attributable to" / "owners of the company 100.7 ..."),
    or a PDF puts the label and its figures on separate baselines, and the figures then reach the model
    on a line with no name. 23 of the benchmark's 228 figures arrived like that.
    """
    raw = [split_line(l) for l in page.get_text("text", sort=True).splitlines() if l.strip()]
    out: list[dict] = []
    pending = ""
    for row in raw:
        if row["label"] and not row["cells"]:
            pending = f"{pending} {row['label']}".strip() if pending else row["label"]
            continue
        if row["cells"] and not row["label"] and pending:
            out.append({"label": pending, "cells": row["cells"]})
        else:
            if pending:
                out.append({"label": pending, "cells": []})
            out.append(row)
        pending = ""
    if pending:
        out.append({"label": pending, "cells": []})
    return out


if __name__ == "__main__" and len(sys.argv) > 2 and sys.argv[2] == "joined":
    bench = Path(sys.argv[1])
    manifest = json.loads((bench / "manifest.json").read_text(encoding="utf-8"))
    result = {}
    for item in manifest:
        doc = pymupdf.open(bench / item["pdf"])
        result[item["news_id"]] = [{"page": i + 1, **r} for i, p in enumerate(doc) for r in joined_rows(p)]
    (bench / "out" / "text-joined.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
