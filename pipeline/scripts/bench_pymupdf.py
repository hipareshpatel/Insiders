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
    """A line of text as a label followed by its numeric cells."""
    tokens = line.split()
    first_num = next((i for i, t in enumerate(tokens) if _NUMERIC.match(t)), len(tokens))
    # keep a leading serial ("1.", "(a)") with the label, not as a figure
    label = " ".join(tokens[:first_num])
    cells = [t for t in tokens[first_num:] if _NUMERIC.match(t)]
    return {"label": label, "cells": cells}


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


if __name__ == "__main__":
    raise SystemExit(main())
