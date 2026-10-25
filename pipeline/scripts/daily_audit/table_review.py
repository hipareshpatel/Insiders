"""Blind review of a results-table on/off run (onoff_table.py), and its score against PASS_MARKS_TABLE.md.

    python -I table_review.py sample <onoff.json> <out_dir> [--reviewers 4] [--seed 2511] [--max 150]
    python -I table_review.py score <out_dir>

sample: a random `--max` of the changed lines (all of them when fewer), each as versions X and Y in a random order, split
into review_<n>.json for `--reviewers` reviewers; key.json says which version is ON. Reviewers write verdicts_<n>.json:
[{item, X_verdict, Y_verdict, ...}] with RIGHT, WRONG, NOT_SHOWN or UNSURE.
score: the four marks, with the definitions and denominators the 25 Oct measurements used (F126b: mark 1 52/58, mark 2
(52 + 63)/150 against 67/150, mark 3 1/150, mark 4 28/92):
1. ON lines still shown that are RIGHT, over ON lines still shown (UNSURE counts as not RIGHT): >= 85%, Wilson low >= 75%.
2. (ON RIGHT + removed where OFF was WRONG) over all reviewed lines, against OFF RIGHT over all reviewed lines: >= 20 points.
3. Lines RIGHT off and WRONG on, over all reviewed lines: <= 5%.
4. Removed lines that were RIGHT off, over removed lines (UNSURE off counts in the denominator): <= 5%."""

from __future__ import annotations

import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from rates import wilson  # noqa: E402


def sample(onoff: str, out: str, reviewers: int, seed: int, most: int) -> None:
    rows = json.load(open(onoff, encoding="utf-8"))["changed"]
    rng = random.Random(seed)
    picked = rng.sample(rows, most) if len(rows) > most else list(rows)
    folder = pathlib.Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    key, items = [], []
    for n, row in enumerate(picked):
        on_first = rng.random() < 0.5
        x, y = (row["on"], row["off"]) if on_first else (row["off"], row["on"])
        key.append({"item": n, "X": "on" if on_first else "off", "news_id": row["news_id"], "line": row["line"],
                    "on": row["on"], "off": row["off"]})
        items.append({"item": n, **{k: row[k] for k in ("news_id", "symbol", "scrip_code", "event", "pdf_url", "period",
                                                        "line")}, "X": x, "Y": y})
    json.dump(key, open(folder / "key.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for r in range(reviewers):
        json.dump(items[r::reviewers], open(folder / f"review_{r + 1}.json", "w", encoding="utf-8"), ensure_ascii=False,
                  indent=1)
    print(f"changed {len(rows)} sampled {len(picked)} reviewers {reviewers} seed {seed}")


def score(out: str) -> dict:
    folder = pathlib.Path(out)
    key = {k["item"]: k for k in json.load(open(folder / "key.json", encoding="utf-8"))}
    lines = []
    for path in sorted(folder.glob("verdicts_*.json")):
        for v in json.load(open(path, encoding="utf-8")):
            k = key[v["item"]]
            on, off = (v["X_verdict"], v["Y_verdict"]) if k["X"] == "on" else (v["Y_verdict"], v["X_verdict"])
            lines.append({**v, "on_verdict": on, "off_verdict": off})
    missing = sorted(set(key) - {line["item"] for line in lines})
    n = len(lines)
    shown = [x for x in lines if x["on_verdict"] != "NOT_SHOWN"]
    removed = [x for x in lines if x["on_verdict"] == "NOT_SHOWN"]
    right_shown = sum(x["on_verdict"] == "RIGHT" for x in shown)
    on_good = right_shown + sum(x["off_verdict"] == "WRONG" for x in removed)
    off_right = sum(x["off_verdict"] == "RIGHT" for x in lines)
    to_wrong = sum(x["off_verdict"] == "RIGHT" and x["on_verdict"] == "WRONG" for x in lines)
    removed_right = sum(x["off_verdict"] == "RIGHT" for x in removed)
    low, high = wilson(right_shown, len(shown))
    marks = {
        "1_shown_right": {"hits": right_shown, "n": len(shown), "pct": 100 * right_shown / max(1, len(shown)),
                          "wilson": [100 * low, 100 * high], "pass": len(shown) > 0 and right_shown / len(shown) >= 0.85 and low >= 0.75},
        "2_on_vs_off": {"on": on_good, "off": off_right, "n": n, "points": 100 * (on_good - off_right) / max(1, n),
                        "pass": n > 0 and (on_good - off_right) / n >= 0.20},
        "3_right_to_wrong": {"hits": to_wrong, "n": n, "pct": 100 * to_wrong / max(1, n), "pass": n > 0 and to_wrong / n <= 0.05},
        "4_removed_right": {"hits": removed_right, "n": len(removed), "pct": 100 * removed_right / max(1, len(removed)),
                            "pass": not removed or removed_right / len(removed) <= 0.05},
    }
    unsure = {"on": sum(x["on_verdict"] == "UNSURE" for x in lines), "off": sum(x["off_verdict"] == "UNSURE" for x in lines)}
    result = {"reviewed": n, "missing_items": missing, "unsure": unsure, "marks": marks,
              "all_pass": all(m["pass"] for m in marks.values()), "lines": lines}
    json.dump(result, open(folder / "score.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in result.items() if k != "lines"}, indent=1))
    return result


def main() -> None:
    args = sys.argv[1:]
    opt = lambda name, default: type(default)(args[args.index(name) + 1]) if name in args else default  # noqa: E731
    if args[0] == "sample":
        sample(args[1], args[2], opt("--reviewers", 4), opt("--seed", 2511), opt("--max", 150))
    elif args[0] == "score":
        score(args[1])


if __name__ == "__main__":
    main()
