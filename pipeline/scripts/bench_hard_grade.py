"""Grade text extractors and OCR on the complicated pages against the two-reader key (bench_hard_key.py).

For each row of the key, three questions, strictest first:
  row intact         every printed cell - nils ("-", "Nil", "NA") and text included - in order, on one
                     line that carries the row's label. A dropped nil moves every later figure one column
                     left, which is the wrong_column error the audits keep finding.
  figures in order   the row's numbers alone, in order, on its line.
  figures on line    how many of the row's numbers appear on its line at all.
For prose (the rating letter's rationale), whether each sentence comes out unbroken.

    python scripts/bench_hard_grade.py HARD_DIR [engine ...]     (engines default to every file in out/)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

DASHES = {"–": "-", "—": "-", "−": "-", "‒": "-"}
NUM = re.compile(r"^\(?-?\d[\d,]*(?:\.\d+)?\)?%?$")
NIL = {"-", "nil", "na", "n.a.", "n/a"}


def tokens(text: str) -> list[str]:
    for bad, good in DASHES.items():
        text = text.replace(bad, good)
    text = text.replace("*", " ").replace("( ", "(").replace(" )", ")")
    return [t.lower().strip(",;:") or t.lower() for t in text.split() if t.strip(",;:")]


def is_value(t: str) -> bool:
    return bool(NUM.match(t)) or t in NIL


def find_run(hay: list[str], run: list[str]) -> bool:
    n = len(run)
    return n > 0 and any(hay[i:i + n] == run for i in range(len(hay) - n + 1))


def label_words(label: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", label.lower())}


def grade(key: dict, lines_by_page: dict) -> dict:
    tot = Counter()
    per_page = {}
    for page, spec in key.items():
        lines = [tokens(l) for l in lines_by_page.get(page, [])]
        page_tot = Counter()
        for row in spec["rows"]:
            cells = [c for c in row["cells"] if c not in ("", None)]
            want_all = [t for c in cells for t in tokens(c)]
            want_num = [t for t in want_all if NUM.match(t)]
            if not want_num:
                continue
            words = label_words(row["label"])
            page_tot["rows"] += 1

            def labelled(i):   # the label on this line or, wrapped, on the two above
                if not words:
                    return True
                near = set(w for j in range(max(0, i - 2), i + 1) for t in lines[j] for w in re.findall(r"[a-z]{3,}", t))
                return len(words & near) >= max(1, round(0.5 * len(words)))
            intact = any(find_run(l, want_all) and labelled(i) for i, l in enumerate(lines))
            ordered = intact or any(find_run([t for t in l if NUM.match(t)], want_num) and labelled(i)
                                    for i, l in enumerate(lines))
            best = 0
            for i, l in enumerate(lines):
                if labelled(i):
                    have = Counter(t for t in l if NUM.match(t))
                    best = max(best, sum(min(n, have[t]) for t, n in Counter(want_num).items()))
            page_tot["intact"] += intact
            page_tot["ordered"] += ordered
            page_tot["figs_want"] += len(want_num)
            page_tot["figs_on_line"] += best
        bullets = (spec.get("bullets") or {}).get("a") or []
        if bullets:
            flat = tokens(" ".join(lines_by_page.get(page, []) and [" ".join(lines_by_page[page])] or []))
            for s in bullets:
                page_tot["sentences"] += 1
                page_tot["sentences_intact"] += find_run(flat, tokens(s))
        per_page[page] = page_tot
        tot.update(page_tot)
    return {"total": tot, "per_page": per_page}


def main() -> int:
    hard = Path(sys.argv[1])
    key = json.loads((hard / "key.json").read_text(encoding="utf-8"))
    engines = sys.argv[2:] or sorted(p.stem for p in (hard / "out").glob("*.json") if not p.stem.endswith(".log"))
    pct = lambda a, b: f"{a / b:6.1%}" if b else "   n/a"
    print(f"{'engine':22} {'rows intact':>12} {'figs in order':>14} {'figs on line':>13} {'sentences':>10}")
    results = {}
    for e in engines:
        out = json.loads((hard / "out" / f"{e}.json").read_text(encoding="utf-8"))
        r = grade(key, out)
        t = r["total"]
        results[e] = r
        print(f"{e:22} {pct(t['intact'], t['rows']):>12} {pct(t['ordered'], t['rows']):>14} "
              f"{pct(t['figs_on_line'], t['figs_want']):>13} {t['sentences_intact']:>4}/{t['sentences']}")
    print(f"\n({sum(1 for p in key.values() for r in p['rows'] if any(NUM.match(x) for c in r['cells'] if c for x in tokens(c)))} rows with figures on {len(key)} pages)")
    print("\nrows intact, by page:")
    print(f"{'':22} " + " ".join(f"{p[:9]:>9}" for p in key))
    for e, r in results.items():
        print(f"{e:22} " + " ".join(f"{r['per_page'][p]['intact']:>4}/{r['per_page'][p]['rows']:<4}" for p in key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
