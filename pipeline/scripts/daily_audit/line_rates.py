"""Per-line accuracy against the card WRONG rate (TODO 17; no AI calls, reads stored audits and a stored line-count file).

A card is WRONG if any one line is wrong, so a card with n lines needs each line right about 1-0.95**(1/n) of the time.
This measures, from the audits already done:
  * lines per card (distribution, by event type, facts part against interpretation part);
  * the per-line fault rate p with a 95% Wilson interval, from the daily audits' `wrong_points` (23-24 Oct, 128 cards)
    and from the one dataset where a reviewer graded every line (critic-review-2026-10-22 and hourly-0713-review);
  * the card WRONG rate that p implies, 1-(1-p)^n card by card, against the observed one, and whether faults cluster;
  * the line accuracy 95% cards need at the median n, and the n a card may carry at the current p.

Line counts come from the cards' stored JSON, saved by `--fetch` (read-only public API, 0.4 s apart) into
docs/audit/line-accuracy-2026-10-25/card_lines.json; every other run reads that file.

    python -I scripts/daily_audit/line_rates.py [--fetch] [--json]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

_spec = importlib.util.spec_from_file_location("audit_rates", Path(__file__).with_name("rates.py"))
rates = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rates)
wilson = rates.wilson

ROOT = Path(__file__).resolve().parents[3]
LIVE = ROOT / "docs" / "audit" / "live"
OUT = ROOT / "docs" / "audit" / "line-accuracy-2026-10-25"
API = "https://insiders.reply-bd3.workers.dev/api/cards/"

# card parts: a line the filing can be checked against (facts) or the card's own reading of it (interpretation)
FACT_LISTS = ("what_happened", "key_numbers", "notable_changes", "quantified_impact")
INTERP_LISTS = ("why_it_matters", "missing_disclosures", "call_takeaways")
TRACK_KEYS = ("milestones", "kpis_to_verify", "pending_approvals", "catalysts", "risks")
RESULT_ROWS = ("revenue", "ebitda", "ebitda_margin", "pbt", "pat", "eps")
TARGET = 0.05


def card_counts(card: dict) -> dict:
    """Lines by part from a card's JSON. headline and takeaway are one line each; results rows count apart."""
    c = {"headline": 1 if card.get("headline") else 0, "takeaway": 1 if card.get("takeaway") else 0}
    for k in FACT_LISTS + INTERP_LISTS:
        c[k] = len(card.get(k) or [])
    track = card.get("track_next") or {}
    c["track_next"] = sum(len(track.get(k) or []) for k in TRACK_KEYS) if isinstance(track, dict) else 0
    res = card.get("results") or {}
    c["results_rows"] = sum(1 for k in RESULT_ROWS if isinstance(res.get(k), dict) and res[k].get("value") is not None)
    return c


def parts(c: dict) -> tuple[int, int, int]:
    """(text lines, facts-part lines, interpretation-part lines); table rows are outside the first and counted apart."""
    facts = c["headline"] + sum(c[k] for k in FACT_LISTS)
    interp = c["takeaway"] + sum(c[k] for k in INTERP_LISTS) + c["track_next"]
    return facts + interp, facts, interp


def fetch(ids: list[str], path: Path) -> dict:
    import urllib.request
    have = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for i in ids:
        if i in have:
            continue
        try:
            with urllib.request.urlopen(urllib.request.Request(API + i, headers={"User-Agent": "line-rates/1"}), timeout=30) as r:
                row = json.load(r)
            card = json.loads(row["card_json"])
            have[i] = {"event_type": card.get("event_type") or row.get("event_category"), "counts": card_counts(card)}
        except Exception as e:  # a card gone from the feed is left out and listed in the report
            have[i] = {"error": str(e)[:80]}
        time.sleep(0.4)
    path.write_text(json.dumps(have, indent=0, sort_keys=True), encoding="utf-8")
    return have


def load_audits() -> dict[str, dict]:
    """Daily audit rows by news_id (latest day wins), each with its day."""
    rows: dict[str, dict] = {}
    for path in sorted(LIVE.glob("*-audit.json")):
        day = path.name[:10]
        for r in json.loads(path.read_text(encoding="utf-8")):
            if str(r.get("verdict", "")).upper() in rates.VERDICTS:
                rows[r["news_id"]] = {**r, "day": day, "verdict": str(r["verdict"]).upper()}
    return rows


def load_graded() -> dict[str, dict]:
    """Cards where a reviewer graded every line: critic-review-2026-10-22 and hourly-0713-review."""
    out = {}
    for name in ("critic-review-2026-10-22.json", "hourly-0713-review.json"):
        for r in json.loads((LIVE / name).read_text(encoding="utf-8")):
            out[r["news_id"]] = r
    return out


PART_WORDS = (("whole_card", r"^\W*(the whole card|whole card|card as a whole)"),
              ("metadata", r"^\W*(event[_ ]type|category[_ ]tag|tone|impact)"),
              ("block", r"^\W*(signal|deal_value|scale|rating_change|rating|score|themes|core_catalyst|timeline|call memory|memory|"
                        r"case_stage|volume)"),
              ("headline", r"^\W*headline"), ("takeaway", r"^\W*(takeaway|our reading)"),
              ("why_it_matters", r"^\W*why[_ ]it[_ ]matters"), ("what_happened", r"^\W*what[_ ]happened"),
              ("key_numbers", r"^\W*key[_ ]numbers?"), ("call_takeaways", r"^\W*call[_ ]?takeaway"),
              ("quantified_impact", r"^\W*quantified[_ ]impact"), ("notable_changes", r"^\W*notable[_ ]change"),
              ("track_next", r"^\W*(pending_approvals|track|milestone|kpis)"),
              ("table", r"^\W*(results|table|basis|yoy|qoq|ebitda|pat |eps|revenue|pbt|margin)"))
# counted lines are the ones the line count covers; the rest (metadata, blocks, a duplicate card) are outside it
OUTSIDE = ("whole_card", "metadata", "block")


def point_part(text: str) -> str:
    t = text.lower()
    for name, pat in PART_WORDS:
        if re.search(pat, t):
            return name
    return "prose line"  # a quoted sentence of the card with no label: a body line, part not stated


def ci(hits: int, n: int) -> str:
    lo, hi = wilson(hits, n)
    return f"{hits / n:.2%} ({lo:.2%}-{hi:.2%})" if n else "-"


def lines_needed(n: float, target: float = TARGET) -> float:
    """The per-line accuracy at which a card of n independent lines is WRONG with probability `target`."""
    return 0.95 ** (1 / n) if target == 0.05 else (1 - target) ** (1 / n)


def max_lines(p: float, target: float = TARGET) -> float:
    """Most lines a card may carry at per-line fault rate p and stay at or under `target` WRONG."""
    return math.log(1 - target) / math.log(1 - p) if 0 < p < 1 else float("inf")


def analyse(audits: dict, lines: dict, graded: dict) -> dict:
    res: dict = {}
    ok = {i: lines[i]["counts"] for i in lines if "counts" in lines[i]}
    res["missing_lines"] = sorted(i for i in set(audits) | set(graded) if i not in ok)

    # 1. lines per card, over every audited card whose card JSON could be read
    dist = {i: parts(c) for i, c in ok.items() if i in audits or i in graded}
    texts = [d[0] for d in dist.values()]
    res["cards_with_lines"] = len(texts)
    res["text_lines"] = {"mean": statistics.mean(texts), "median": statistics.median(texts), "min": min(texts), "max": max(texts),
                         "q1": statistics.quantiles(texts, n=4)[0], "q3": statistics.quantiles(texts, n=4)[2]}
    res["facts_mean"] = statistics.mean(d[1] for d in dist.values())
    res["interp_mean"] = statistics.mean(d[2] for d in dist.values())
    res["rows_mean"] = statistics.mean(ok[i]["results_rows"] for i in dist)
    by_type = defaultdict(list)
    for i in dist:
        by_type[lines[i]["event_type"] or "?"].append(dist[i][0])
    res["by_type"] = {t: (len(v), statistics.median(v), statistics.mean(v)) for t, v in sorted(by_type.items(), key=lambda kv: -len(kv[1]))}
    by_part = Counter()
    for i in dist:
        for k, v in ok[i].items():
            by_part[k] += v
    res["part_totals"] = dict(by_part)

    # 2. observed card WRONG rate and per-line fault rate, daily audits that list wrong points (23-24 Oct)
    pts = {i: r for i, r in audits.items() if "wrong_points" in r and i in ok}
    n_cards = len(pts)
    wrong = [i for i, r in pts.items() if r["verdict"] == "WRONG"]
    minor = [i for i, r in pts.items() if r["verdict"] == "MINOR"]
    N = sum(parts(ok[i])[0] for i in pts)                       # lines judged
    npts = lambda ids: sum(len(pts[i]["wrong_points"] or []) for i in ids)  # noqa: E731
    wp, mp = npts(wrong), npts(minor)
    res["audit"] = {"cards": n_cards, "wrong_cards": len(wrong), "minor_cards": len(minor), "lines": N, "wrong_lines": wp, "minor_lines": mp,
                    "wrong_cards_with_no_points": sum(1 for i in wrong if not pts[i]["wrong_points"]),
                    "right_cards_with_points": sum(1 for i, r in pts.items() if r["verdict"] == "RIGHT" and r["wrong_points"])}
    # whole-card faults (a card that should not exist) are a card fault, not a line fault
    whole = [i for i in wrong if any(point_part(p) == "whole_card" for p in pts[i]["wrong_points"])]
    res["audit"]["whole_card_wrong"] = len(whole)
    res["wrong_points_by_part"] = Counter(point_part(p) for i in wrong for p in pts[i]["wrong_points"])
    res["wrong_points_by_class"] = Counter(pts[i].get("error_class") or "?" for i in wrong)
    res["wrong_cards_by_points"] = Counter(len(pts[i]["wrong_points"]) for i in wrong)

    inline = [(i, p) for i in wrong for p in pts[i]["wrong_points"] if point_part(p) not in OUTSIDE]
    res["audit"]["inline_wrong_lines"] = len(inline)
    res["audit"]["outside_wrong_points"] = wp - len(inline)
    res["audit"]["wrong_cards_inline_only"] = sum(1 for i in wrong if all(point_part(p) in OUTSIDE for p in pts[i]["wrong_points"]))
    res["p_inline"] = len(inline) / N
    # implied card WRONG rate with the pooled p (WRONG-card points only), per-card n; and with every listed point
    def implied(p: float) -> float:
        return statistics.mean(1 - (1 - p) ** parts(ok[i])[0] for i in pts)
    p_hard = wp / N
    p_any = (wp + mp) / N
    res["p_hard"], res["p_any"] = p_hard, p_any
    res["implied_hard"] = (implied(p_hard), implied(wilson(wp, N)[0]), implied(wilson(wp, N)[1]))
    res["implied_any"] = (implied(p_any), implied(wilson(wp + mp, N)[0]), implied(wilson(wp + mp, N)[1]))
    res["implied_inline"] = (implied(res["p_inline"]), implied(wilson(len(inline), N)[0]), implied(wilson(len(inline), N)[1]))
    res["observed_wrong"] = len(wrong) / n_cards
    # the per-line rate that would reproduce the observed card WRONG rate (faults counted once per root cause, not per line)
    def solve(target: float) -> float:
        lo, hi = 0.0, 0.5
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if implied(mid) < target else (lo, mid)
        return lo
    wl, wh = wilson(len(wrong), n_cards)
    res["p_eff"] = (solve(len(wrong) / n_cards), solve(wl), solve(wh))
    # clustering: under independent lines the chance a WRONG card has a 2nd wrong line given the first is about n*p;
    # compare wrong lines per WRONG card with 1 + (n-1)p (expected), and cards with >=2 wrong lines
    exp_multi = 0.0
    for i in pts:
        n, q = parts(ok[i])[0], p_hard
        exp_multi += max(0.0, 1 - (1 - q) ** n - n * q * (1 - q) ** (n - 1))
    res["multi"] = {"observed": sum(1 for i in wrong if len(pts[i]["wrong_points"]) >= 2), "expected_independent": exp_multi,
                    "points_per_wrong_card": wp / len(wrong) if wrong else 0,
                    "expected_points_per_wrong_card": statistics.mean(1 + (parts(ok[i])[0] - 1) * p_hard for i in wrong) if wrong else 0}

    # 3. needed accuracy and affordable lines
    med = res["text_lines"]["median"]
    res["needed"] = {"at_median": 1 - lines_needed(med), "at_mean": 1 - lines_needed(res["text_lines"]["mean"]),
                     "p_hard_lo_hi": wilson(wp, N)}
    res["max_lines"] = {"point": max_lines(p_hard), "at_ci_low": max_lines(wilson(wp, N)[1]), "at_ci_high": max_lines(wilson(wp, N)[0]),
                        "eff": max_lines(res["p_eff"][0]), "eff_lo": max_lines(res["p_eff"][2]), "eff_hi": max_lines(res["p_eff"][1])}
    # all four days: card WRONG rate and lines for the cards whose lines are known
    allw = [i for i in audits if i in ok]
    res["all_days"] = {"cards": len(allw), "wrong": sum(1 for i in allw if audits[i]["verdict"] == "WRONG"),
                       "wrong_by_lines": {}}
    cut = res["text_lines"]["median"]
    for name, sel in (("at or below median", lambda n: n <= cut), ("above median", lambda n: n > cut)):
        ids = [i for i in allw if sel(parts(ok[i])[0])]
        res["all_days"]["wrong_by_lines"][name] = (sum(1 for i in ids if audits[i]["verdict"] == "WRONG"), len(ids))

    # 4. every line graded (critic-review + hourly): direct per-line rates
    g = {i: r for i, r in graded.items() if i in ok}
    hard_v, soft_v = {"WRONG_FIGURE", "INVENTED"}, {"OVERSTATED", "UNSUPPORTED_CAUSE", "MISSING"}
    lines_g = [(i, p) for i, r in g.items() for p in r["points"] if p["id"] != "card" and not str(p["id"]).startswith("card")]
    kinds = Counter(p["verdict"] for _, p in lines_g)
    n_g = len(lines_g)
    bad_hard = sum(kinds[v] for v in hard_v)
    bad_soft = sum(kinds[v] for v in soft_v if v != "MISSING")
    res["graded"] = {"cards": len(g), "lines": n_g, "verdicts": dict(kinds), "hard": bad_hard, "soft": bad_soft,
                     "missing_points": kinds["MISSING"], "overall": dict(Counter(r["overall"] for r in g.values())),
                     "lines_per_card_graded": statistics.mean(len([p for p in r["points"] if p["id"] != "card"]) for r in g.values()),
                     "wrong_cards_by_hard_line": sum(1 for r in g.values() if any(p["verdict"] in hard_v for p in r["points"])),
                     "minor_or_wrong_by_any_line": sum(1 for r in g.values() if any(p["verdict"] != "OK" for p in r["points"]))}
    by_pt = defaultdict(lambda: [0, 0])
    for _, p in lines_g:
        k = re.split(r"[.\[ ]", str(p["id"]))[0]
        by_pt[k][0] += 1
        by_pt[k][1] += p["verdict"] != "OK"
    res["graded"]["by_part"] = {k: tuple(v) for k, v in sorted(by_pt.items(), key=lambda kv: -kv[1][0])}
    res["graded"]["kind_of_bad"] = Counter(p["verdict"] for _, p in lines_g if p["verdict"] != "OK")
    return res


def report(res: dict) -> str:
    t, a, g = res["text_lines"], res["audit"], res["graded"]
    o = [f"Cards with line counts: {res['cards_with_lines']} (no card JSON for {len(res['missing_lines'])}: {', '.join(res['missing_lines'][:8])})",
         "", "LINES PER CARD (headline, takeaway, what happened, key numbers, notable changes, quantified impact, why it matters, "
         "missing disclosures, call takeaways, track-next items; results-table rows apart)",
         f"  mean {t['mean']:.1f}, median {t['median']:.0f}, quartiles {t['q1']:.1f}-{t['q3']:.1f}, range {t['min']}-{t['max']}",
         f"  facts part {res['facts_mean']:.1f} lines a card, interpretation part {res['interp_mean']:.1f}, results-table rows {res['rows_mean']:.1f}",
         "  by event type (cards, median, mean): " + "; ".join(f"{k} {v[0]}, {v[1]:.0f}, {v[2]:.1f}" for k, v in list(res["by_type"].items())[:10]),
         "", f"DAILY AUDITS 23-24 OCT: {a['cards']} cards, {a['lines']} lines, {a['wrong_cards']} WRONG, {a['minor_cards']} MINOR",
         f"  wrong lines on WRONG cards: {a['wrong_lines']} -> p = {ci(a['wrong_lines'], a['lines'])}",
         f"  of those, in the counted lines (not a signal/block, event type or whole-card fault): {a['inline_wrong_lines']} -> "
         f"p = {ci(a['inline_wrong_lines'], a['lines'])}; {a['outside_wrong_points']} points sit outside the line count; "
         f"{a['wrong_cards_inline_only']} WRONG cards have only such outside faults",
         f"  every listed fault line (WRONG and MINOR cards): {a['wrong_lines'] + a['minor_lines']} -> p = {ci(a['wrong_lines'] + a['minor_lines'], a['lines'])}",
         f"  observed card WRONG {ci(a['wrong_cards'], a['cards'])}; implied 1-(1-p)^n with p hard: "
         f"{res['implied_hard'][0]:.1%} ({res['implied_hard'][1]:.1%}-{res['implied_hard'][2]:.1%}); in-line only: "
         f"{res['implied_inline'][0]:.1%} ({res['implied_inline'][1]:.1%}-{res['implied_inline'][2]:.1%}); with every fault line: "
         f"{res['implied_any'][0]:.1%} ({res['implied_any'][1]:.1%}-{res['implied_any'][2]:.1%})",
         f"  WRONG cards with no point listed: {a['wrong_cards_with_no_points']}; whole-card WRONG (not a line fault): {a['whole_card_wrong']}",
         f"  wrong points per WRONG card {res['multi']['points_per_wrong_card']:.2f} (independent lines would give "
         f"{res['multi']['expected_points_per_wrong_card']:.2f}); WRONG cards with 2+ points {res['multi']['observed']} "
         f"(independent lines: {res['multi']['expected_independent']:.1f} of {a['cards']} cards)",
         "  wrong points by part: " + ", ".join(f"{k} {v}" for k, v in res["wrong_points_by_part"].most_common()),
         "  WRONG cards by error class: " + ", ".join(f"{k} {v}" for k, v in res["wrong_points_by_class"].most_common()),
         "", f"EVERY LINE GRADED ({g['cards']} cards, {g['lines']} lines): " + ", ".join(f"{k} {v}" for k, v in g["verdicts"].items()),
         f"  hard faults (wrong figure, invented) {g['hard']} -> p = {ci(g['hard'], g['lines'])}; soft (overstated, unsupported cause) "
         f"{g['soft']} -> {ci(g['soft'], g['lines'])}; any non-OK line {ci(g['hard'] + g['soft'], g['lines'])}",
         f"  cards {g['overall']}; cards with a hard-fault line {g['wrong_cards_by_hard_line']}; with any non-OK line {g['minor_or_wrong_by_any_line']}; "
         f"missing-point notes {g['missing_points']}",
         "  non-OK lines by part (lines, non-OK): " + "; ".join(f"{k} {v[0]}/{v[1]}" for k, v in g["by_part"].items()),
         "", f"NEEDED: at the median {t['median']:.0f} lines each line must be right {1 - res['needed']['at_median']:.2%} of the time "
         f"(fault rate {res['needed']['at_median']:.2%}) for 95% cards; at the mean {t['mean']:.1f} lines, {res['needed']['at_mean']:.2%} fault rate",
         f"CALIBRATED: the per-line rate that reproduces the observed card WRONG rate is {res['p_eff'][0]:.2%} "
         f"({res['p_eff'][1]:.2%}-{res['p_eff'][2]:.2%}); at that rate a card may carry {res['max_lines']['eff']:.1f} lines "
         f"({res['max_lines']['eff_lo']:.1f} to {res['max_lines']['eff_hi']:.1f}) for 5% WRONG",
         f"AFFORDABLE: at p {res['p_hard']:.2%} a card may carry {res['max_lines']['point']:.1f} lines "
         f"({res['max_lines']['at_ci_low']:.1f} to {res['max_lines']['at_ci_high']:.1f} over the interval) and stay at 5% WRONG",
         f"ALL FOUR DAYS ({res['all_days']['cards']} cards with lines): WRONG {ci(res['all_days']['wrong'], res['all_days']['cards'])}; "
         + "; ".join(f"{k}: {v[0]} of {v[1]}" for k, v in res["all_days"]["wrong_by_lines"].items())]
    return "\n".join(o)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fetch", action="store_true", help="read missing cards' line counts from the public API first")
    ap.add_argument("--lines", default=str(OUT / "card_lines.json"))
    args = ap.parse_args()
    audits, graded = load_audits(), load_graded()
    path = Path(args.lines)
    if args.fetch:
        path.parent.mkdir(parents=True, exist_ok=True)
        fetch(sorted(set(audits) | set(graded)), path)
    lines = json.loads(path.read_text(encoding="utf-8"))
    print(report(analyse(audits, lines, graded)))


if __name__ == "__main__":
    main()
