"""Score OCR output on the page benchmark (bench_pages.py) against each page's own text layer.

An engine writes {"<news_id>:<page>": "the text it read"}. For each page:

  figures exact   the page's figures, as printed, that the OCR also produced (a multiset: a figure
                  printed three times must be read three times). Brackets on a negative, Indian digit
                  grouping ("1,24,500.50") and decimals all have to survive.
  figures digits  the same with separators ignored: whether the digits were right even if a comma or
                  bracket was lost
  precision       of the figures the OCR produced, how many are on the page: invented or misread
                  digits lower it
  words           the page's words the OCR produced

Two limits of the answer key, stated so they are not mistaken for an engine's fault: a text layer can
hold text nobody sees (white or hidden under an image), which no OCR can read, and an image on the page
can carry text the text layer lacks, which an OCR rightly reads and is counted against its precision.

    python scripts/bench_pages_score.py BENCH_PAGES_DIR ocr_output.json [--name NAME] [--by-type]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

NUMBER = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?%?")
WORD = re.compile(r"[A-Za-z]{3,}")


def figures(text: str) -> list[str]:
    return [n for n in NUMBER.findall(text or "") if sum(ch.isdigit() for ch in n) >= 2]


def digits(token: str) -> str:
    return "".join(ch for ch in token if ch.isdigit() or ch == ".")


def overlap(a: list[str], b: list[str]) -> int:
    ca, cb = collections.Counter(a), collections.Counter(b)
    return sum(min(n, cb[k]) for k, n in ca.items())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bench")
    ap.add_argument("output")
    ap.add_argument("--name", default="")
    ap.add_argument("--by-type", action="store_true")
    args = ap.parse_args()
    pages = json.loads((Path(args.bench) / "pages.json").read_text(encoding="utf-8"))
    output = json.loads(Path(args.output).read_text(encoding="utf-8"))
    covered = [p for p in pages if f"{p['news_id']}:{p['page']}" in output]
    tot = collections.Counter()
    by_type: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for p in covered:
        text = output[f"{p['news_id']}:{p['page']}"]
        got, want = figures(text), p["figures"]
        row = collections.Counter(
            want=len(want), got=len(got), exact=overlap(want, got),
            digits=overlap([digits(x) for x in want], [digits(x) for x in got]),
            right=overlap(got, want), wwant=len(p["words"]),
            words=overlap([w.lower() for w in p["words"]], [w.lower() for w in WORD.findall(text)]),
            neg_want=sum(1 for x in want if x.startswith("(")),
            neg_kept=overlap([x for x in want if x.startswith("(")], got))
        tot.update(row)
        by_type[p["event_type"]].update(row)

    def line(name: str, c: collections.Counter) -> str:
        pct = lambda a, b: f"{a / b:6.1%}" if b else "   n/a"
        return (f"{name:28} figures exact {pct(c['exact'], c['want'])}  digits {pct(c['digits'], c['want'])}  "
                f"precision {pct(c['right'], c['got'])}  words {pct(c['words'], c['wwant'])}  "
                f"negatives kept {pct(c['neg_kept'], c['neg_want'])} of {c['neg_want']}")
    label = args.name or Path(args.output).stem
    print(f"{label}: {len(covered)} of {len(pages)} pages" + ("" if len(covered) == len(pages) else " (partial)"))
    print("  " + line("all", tot))
    if args.by_type:
        for t, c in sorted(by_type.items()):
            print("  " + line(t, c))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
