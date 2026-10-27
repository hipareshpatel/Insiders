"""On/off audit of a candidate number-matching rule ("match at the precision the filing prints") over stored cards.
Read-only: no AI, nothing written to the site. The live checks are never changed; the candidate is a function in this
file that is swapped in for `gate.numbers_in_quote` while the real card checks (`pipeline.check_quotes`,
`pipeline.check_quoted_numbers`) run, then put back.

The candidate (owner question, 26 Oct 2026; docs/audit/root-causes-2026-10-25.md P4; docs/audit/precision-2026-10-26.md):
  * a card figure matches a source figure when they agree at the SOURCE's printed precision: source "10,738" matches card
    10,737.58 (rounds to 10,738); source "10,737.58" needs 10,737.58, or its rounding to the card's own decimals;
  * the whole number must match: a prefix never does ("95" of "951.96", "1,95,000" of "19,500");
  * a figure cut (not rounded) at the card's last digit no longer matches ("554" of 554.65 stays a rounding, "79" of 796 mn
    does not);
  * units are respected as today (card Cr / lakh / million against the quote's own unit or the filing's declared unit).
Variants run over every card:  off = today's checks;  f156 = QUOTE_EXACT_NUMBERS=1 (the shipped-but-off switch);
  on = the candidate;  on_display = the candidate with the card's crore figures first shown the way the owner proposed
  (>= 1,000 Cr in whole crore, smaller to one decimal).

    python -I -X utf8 scripts/audit_precision.py OUT_DIR --platform [--limit N]          # GitHub job (maintenance.yml)
    python -I -X utf8 scripts/audit_precision.py OUT_DIR --cards ROWS.json --texts DIR   # offline: export_cards rows and
                                                                                         # DIR/<news_id>.json.gz text caches
    python -I -X utf8 scripts/audit_precision.py --selftest
    options: --seed 2610  --sample 20  --doc ../docs/audit/precision-sample-2026-10-26.md

Output: summary.json, lines.json (every changed line), and the blind-review sample markdown (--doc). A card whose text is
not in R2 / DIR, or that does not validate, is counted as skipped and not judged. Text is the filing's own pages
(`Document.select_text`, as audit_quote_rules.py reads it): the XBRL table the pipeline puts in front, memory and the
second reading are not available here, so a line that today passes on memory or the table may show as a problem in
every variant alike; compare the variants with each other, not with the stored verdicts (`reproduced` says how many stored
number issues the off run finds again)."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import pathlib
import random
import re
import signal
import sys
import time
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "src"))
from bse_intel import gate, pipeline as P  # noqa: E402
from bse_intel.extract import Document  # noqa: E402
from bse_intel.grounding import declared_unit  # noqa: E402
from bse_intel.models import Card, Pass2Output  # noqa: E402

PREFIX = "Give each fact the filing's own sentence as its quote: "
EPS = 1e-9
# a stored or re-run problem about a figure its quote does not carry (key number / notable change / insight, or a fact)
NUMBER_PROBLEM = re.compile(r'^(?:(?:key number|notable change|why it matters) )?".*" states .*, which its own quote does not$', re.S)
GROUNDING_KEYS = ("ungrounded", "math_mismatches", "unsupported_claims", "out_of_fit", "call_figure_conflicts")


# ---------------------------------------------------------------- the candidate rule
def display_cap(value: float, decimals: int) -> tuple[float, int]:
    """The owner's display: a crore figure of 1,000 or more in whole crore, smaller to one decimal."""
    dec = 0 if abs(value) >= 1000 else 1
    if decimals <= dec:
        return value, decimals
    return round(value + math.copysign(EPS, value), dec), dec


def make_candidate(display: bool):
    """`numbers_in_quote` with the candidate matching; same signature and same exemptions (percentages, bps, period labels,
    dates, days of the month, foreign currency) as gate.numbers_in_quote, only the figure comparison differs."""

    def numbers_in_quote(claim: str, quote: str, unit: int | None = None) -> list[str]:
        if not quote:
            return []
        flat_quote = gate._SPACED_THOUSANDS.sub(r"\1\2", gate._DECIMAL_COMMA.sub(r"\1.\2", gate._flat(quote)))
        digits = {m.group(0).replace(",", "") for m in gate._CLAIM_NUMBER.finditer(flat_quote)}
        # each source figure in crore at every unit it may be in, with the step its own print leaves (its decimals, in crore)
        in_crore, as_printed = [], []
        for m in gate._CLAIM_NUMBER.finditer(flat_quote):
            raw = m.group(0).replace(",", "")
            try:
                value = float(raw)
            except ValueError:
                continue
            decs = len(raw.partition(".")[2])
            # a note number or a day ("23") is not a rounded amount: only a figure with a decimal or three digits has a step
            step = 10 ** -decs if (decs or len(raw.lstrip("0")) >= 3) else 0.0
            own = gate._unit_after(flat_quote, m.end()) or (1 if re.search(r"_cr\s*:?\s*$", flat_quote[:m.start()]) else None)
            in_crore += [(value / s, step / s) for s in ([own] if own else [s for s in (unit, 1e7) if s and s > 1])]
            if own is None and not (unit and unit > 1):
                in_crore.append((value, step))
            as_printed.append((value, step))
        missing = []
        flat_claim = gate._PERIOD_LABEL.sub(" ", gate._WRITTEN_DATE.sub(" ", gate._flat(claim)))
        for m in gate._CLAIM_NUMBER.finditer(flat_claim):
            after = flat_claim[m.end():m.end() + 14].lstrip()
            if after.startswith(("bps", "bp ", "bp,", "bp.", "pp", "basis point", "percentage point")) or after.startswith("%"):
                continue
            value = m.group(0).replace(",", "")
            card_unit = gate._unit_after(flat_claim, m.end())
            if card_unit is not None and gate._FOREIGN.search(flat_claim[max(0, m.start() - 8):m.start()]):
                card_unit = None
            if card_unit is None and value in digits:
                continue   # the same token, no unit written on the card: the quote's own figure (as today)
            try:
                number = float(value)
            except ValueError:
                continue
            decimals = len(value.partition(".")[2])
            if not decimals and number <= 31:
                continue
            if display and card_unit == 1:
                number, decimals = display_cap(number, decimals)
            scale = card_unit or 1
            target = number / scale
            card_step = 10 ** -decimals / scale
            candidates = in_crore if card_unit is not None else in_crore + as_printed
            # agree at the coarser of the two prints: the source's, or the card's own last digit
            if any(abs(c - target) <= 0.5 * max(card_step, step) + EPS + abs(target) * 1e-9 for c, step in candidates):
                continue
            missing.append(m.group(0))
        return missing

    return numbers_in_quote


# ---------------------------------------------------------------- running the real checks under a variant
def set_variant(name: str):
    real = gate.numbers_in_quote
    env = os.environ.get("QUOTE_EXACT_NUMBERS")
    if name == "off":
        os.environ["QUOTE_EXACT_NUMBERS"] = "0"
    elif name == "f156":
        os.environ["QUOTE_EXACT_NUMBERS"] = "1"
    else:
        gate.numbers_in_quote = make_candidate(display=name == "on_display")

    def restore():
        gate.numbers_in_quote = real
        if env is None:
            os.environ.pop("QUOTE_EXACT_NUMBERS", None)
        else:
            os.environ["QUOTE_EXACT_NUMBERS"] = env
    return restore


def card_output(card: dict) -> Pass2Output:
    return Pass2Output.model_validate({"is_material": True, "event_type": card.get("event_type") or "OTHER",
                                       "timeline_entry": card.get("timeline_entry") or "x",
                                       "card": {k: card[k] for k in Card.model_fields if k in card and card[k] is not None}})


def run_checks(card: dict, text: str, unit: int | None, variant: str) -> list[str]:
    """Every figure problem the two quote checks raise on the card under the variant (what_happened facts, key numbers,
    notable changes, insights)."""
    restore = set_variant(variant)
    try:
        out = card_output(card)
        facts = P.check_quotes(out, text, "", unit)[0]
        out = card_output(card)
        points = P.check_quoted_numbers(out, text, unit)[0]
    finally:
        restore()
    return [p for p in facts + points if NUMBER_PROBLEM.match(p)]


def locate(card: dict, problem: str) -> dict:
    """The card line a problem is about: its text and its quote."""
    m = P._QUOTE_POINT.match(problem)
    out = card_output(card).card
    if m:
        for kind, label, claim, quote, _ in P._quoted_claims(out):
            if kind == m.group(1) and label == m.group(2):
                return {"kind": kind, "label": label, "claim": claim.strip(), "quote": quote}
    f = P._QUOTE_FACT.match(problem)
    if f:
        for fact in out.what_happened:
            if fact.text.replace("**", "")[:60] == f.group(1)[:60] or fact.text.replace("**", "") == f.group(1):
                return {"kind": "fact", "label": f.group(1), "claim": fact.text.replace("**", ""), "quote": fact.quote}
    return {"kind": "?", "label": problem[:60], "claim": problem, "quote": None}


def figures_of(problem: str) -> str:
    m = re.search(r'states (.*), which its own quote does not', problem, re.S)
    return m.group(1) if m else ""


def stored_issues(card: dict) -> list[str]:
    return [i[len(PREFIX):] if i.startswith(PREFIX) else i for i in (card.get("review") or {}).get("issues") or []]


def hold_reasons(card: dict) -> list[str]:
    """What holds a card, by class (prune.fault_classes), numbers and quoted words taken out."""
    from bse_intel.prune import fault_classes
    return fault_classes(card)


# ---------------------------------------------------------------- reading the stored cards and texts
def rows_from_platform(limit: int | None):
    from bse_intel.settings import get_settings
    from bse_intel.sinks import make_sink
    sink = make_sink(get_settings())
    after, n = ["", ""], 0
    while True:
        page = sink.query("export_cards", [after[0], after[1], 100])
        if not page:
            break
        after = [page[-1]["filed_at"], page[-1]["news_id"]]
        for r in page:
            yield r, lambda nid, s=sink: s.get_object(P.text_key(nid))
            n += 1
            if limit and n >= limit:
                return
        if len(page) < 100:
            break


def rows_from_files(cards_path: str, texts: str):
    loaded = json.load(open(cards_path, encoding="utf-8"))
    rows = loaded["cards"] if isinstance(loaded, dict) else loaded
    root = pathlib.Path(texts)

    def getter(nid: str):
        for p in (root / f"{nid}.json.gz", root / P.text_key(nid).split("/", 1)[1]):
            if p.exists():
                return p.read_bytes()
        return None
    for r in rows:
        yield r, getter


def filing_text(body: bytes) -> str:
    return Document.from_cache(json.loads(gzip.decompress(body))).select_text(10_000_000, [])


# ---------------------------------------------------------------- the audit
VARIANTS = ("off", "f156", "on", "on_display")


_STOP: list[str] = []   # SIGTERM / SIGINT (GitHub's cancel): the loop ends cleanly and the summaries are written


def _on_signal(signum, _frame) -> None:
    _STOP.append(signal.Signals(signum).name)


def audit(rows, args) -> dict:
    """F216: each card's off/on problems are appended to out/cards.jsonl as they are found, and the pass ends cleanly
    (summary.stopped) at --time-budget, on a cancel signal, or when the platform stops answering."""
    cards, skipped = 0, Counter()
    per_card = []
    stopped = None
    deadline = time.monotonic() + args.time_budget if getattr(args, "time_budget", 0) > 0 else None
    out_dir = getattr(args, "out_dir", None)
    log = open(pathlib.Path(out_dir) / "cards.jsonl", "a", encoding="utf-8") if out_dir else None
    rows = iter(rows)
    while True:
        if _STOP:
            stopped = f"stopped by {_STOP[0]}"
            break
        if deadline is not None and time.monotonic() >= deadline:
            stopped = "time budget reached"
            break
        try:
            row, get_text = next(rows)
        except StopIteration:
            break
        except Exception as exc:   # the card list itself (the platform) stopped answering
            stopped = f"the card list could not be read ({type(exc).__name__}: {exc})"
            break
        try:
            card = json.loads(row["card_json"]) if isinstance(row.get("card_json"), str) else (row.get("card_json") or {})
            body = get_text(row["news_id"])
            if not body:
                skipped["no text"] += 1
                continue
            text = filing_text(body)
            unit = declared_unit(text)
            probs = {v: run_checks(card, text, unit, v) for v in VARIANTS}
        except Exception as exc:  # a card the checks cannot read is reported, not hidden
            skipped[f"error {type(exc).__name__}"] += 1
            continue
        cards += 1
        held = bool(row.get("held"))
        stored = [i for i in stored_issues(card) if NUMBER_PROBLEM.match(i)]
        issues = stored_issues(card)
        reasons = hold_reasons(card) if held else []
        grounding = any((card.get("grounding") or {}).get(k) for k in GROUNDING_KEYS)
        only_quote_numbers = held and bool(issues) and len(stored) == len(issues) and not grounding \
            and not (card.get("review") or {}).get("held")
        per_card.append({"row": row, "card": card, "text": text, "held": held, "probs": probs, "stored": stored,
                         "reasons": reasons, "only_quote_numbers": only_quote_numbers, "n_issues": len(issues)})
        if log:
            log.write(json.dumps({"news_id": row.get("news_id"), "held": held, "probs": probs, "stored": stored},
                                 ensure_ascii=False) + "\n")
            log.flush()
    if log:
        log.close()
    summary = {"cards_checked": cards, "skipped": dict(skipped), "variants": {}, "stopped": stopped}
    lines = []
    for v in VARIANTS[1:]:
        s = {"held_cards": 0, "published_cards": 0, "held_only_quote_number_reasons": 0,
             "held_released_loose": 0, "held_released_strict": 0, "held_lines_cleared": 0,
             "held_reasons_gone": Counter(), "published_newly_fail": 0, "published_newly_fail_lines": 0,
             "published_lines_cleared": 0, "lines_cleared": 0, "lines_added": 0,
             "stored_number_issues": 0, "reproduced_by_off": 0, "cards_changed": 0}
        for c in per_card:
            off, new = c["probs"]["off"], c["probs"][v]
            gone = [p for p in off if p not in new]
            added = [p for p in new if p not in off]
            s["held_cards" if c["held"] else "published_cards"] += 1
            if c["held"]:
                s["stored_number_issues"] += len(c["stored"])
                s["reproduced_by_off"] += sum(1 for i in c["stored"] if i in off)
                s["held_only_quote_number_reasons"] += int(c["only_quote_numbers"])
            if gone or added:
                s["cards_changed"] += 1
            s["lines_cleared"] += len(gone)
            s["lines_added"] += len(added)
            for p in gone:
                lines.append({"variant": v, "news_id": c["row"]["news_id"], "held": c["held"], "change": "cleared",
                              "problem": p, "figures": figures_of(p), **locate(c["card"], p)})
            for p in added:
                lines.append({"variant": v, "news_id": c["row"]["news_id"], "held": c["held"], "change": "newly_fails",
                              "problem": p, "figures": figures_of(p), **locate(c["card"], p)})
            if c["held"]:
                s["held_lines_cleared"] += len(gone)
                for i in c["stored"]:
                    if i in off and i not in new:
                        s["held_reasons_gone"]["quote-number: " + re.sub(r'"[^"]*"', '"..."', re.sub(r"[\d.,]+", "N", i))[:70]] += 1
                if c["only_quote_numbers"] and not new:
                    s["held_released_loose"] += 1
                    if all(i in off and i not in new for i in c["stored"]):
                        s["held_released_strict"] += 1
            else:
                s["published_lines_cleared"] += len(gone)
                if added:
                    s["published_newly_fail"] += 1
                    s["published_newly_fail_lines"] += len(added)
        s["held_reasons_gone"] = dict(s["held_reasons_gone"])
        summary["variants"][v] = s
    # what holds the held cards, by class, and how many hold for numbers alone
    held = [c for c in per_card if c["held"]]
    reasons = Counter(r for c in held for r in dict.fromkeys(c["reasons"]))
    summary["held_total"] = len(held)
    summary["held_reason_classes"] = dict(reasons.most_common(25))
    summary["held_with_a_quote_number_issue"] = sum(1 for c in held if c["stored"])
    summary["held_only_quote_number_reasons"] = sum(1 for c in held if c["only_quote_numbers"])
    summary["held_only_number_reasons_incl_grounding"] = sum(
        1 for c in held if c["n_issues"] == len(c["stored"]) and (c["stored"] or any(
            (c["card"].get("grounding") or {}).get(k) for k in ("ungrounded", "math_mismatches")))
        and not any((c["card"].get("grounding") or {}).get(k) for k in ("unsupported_claims", "out_of_fit", "call_figure_conflicts"))
        and not (c["card"].get("review") or {}).get("held"))
    return {"summary": summary, "lines": lines, "per_card": per_card}


def snippet(text: str, quote: str | None, figures: str) -> str:
    """The quote as the card cites it, else the first source line carrying one of the missing figures."""
    if quote:
        return quote.strip()[:600]
    for fig in re.findall(r"[\d.,]+", figures):
        for ln in text.splitlines():
            if fig in ln:
                return ln.strip()[:400]
    return ""


def write_sample(result: dict, args) -> None:
    rng = random.Random(args.seed)
    by_id = {c["row"]["news_id"]: c for c in result["per_card"]}
    which = "on"
    lines = [x for x in result["lines"] if x["variant"] == which]
    released = sorted((x for x in lines if x["change"] == "cleared"), key=lambda x: (x["news_id"], x["label"]))
    failed = sorted((x for x in lines if x["change"] == "newly_fails"), key=lambda x: (x["news_id"], x["label"]))
    rng.shuffle(released)
    rng.shuffle(failed)
    md = [f"# Precision rule: blind sample, {args.stamp}", "",
          "Candidate rule `on` (docs/audit/precision-2026-10-26.md): a card figure matches a source figure at the source's "
          "printed precision; the whole number must match (no prefix); units as today. Each line below is a card line the "
          "rule changes. For each, judge from the filing (the quote and the pdf link) only: is the card's figure RIGHT "
          "(the filing states it, at the unit and period the card says) or WRONG (the filing does not support it)? "
          "Do not reason about the rule. The key (which list a line came from) is at the bottom, after the lines; "
          "reviewers read the lines first and the key never.", ""]
    picked = [("A", x) for x in released[:args.sample]] + [("B", x) for x in failed[:args.sample]]
    rng.shuffle(picked)
    key = []
    for n, (grp, x) in enumerate(picked, 1):
        c = by_id[x["news_id"]]
        row = c["row"]
        md += [f"## L{n:02d}  {row.get('symbol') or row.get('scrip_code')} {x['news_id']}", "",
               f"- card ({x['kind']}): {x['claim']}",
               f"- the card's quote: {snippet(c['text'], x['quote'], x['figures'])}",
               f"- figures the quote is said not to carry: {x['figures']}",
               f"- filing: {row.get('pdf_url') or 'n/a'}", ""]
        key.append(f"L{n:02d}={'released' if grp == 'A' else 'newly-failed'}")
    md += ["---", "", "Key (do not read before judging):", "", "`" + ", ".join(sorted(key)) + "`", "",
           f"Sample drawn with seed {args.seed} from {len(released)} released and {len(failed)} newly-failed lines "
           f"({min(args.sample, len(released))} and {min(args.sample, len(failed))} taken)."]
    pathlib.Path(args.doc).write_text("\n".join(md), encoding="utf-8")


def selftest() -> int:
    f = make_candidate(False)
    d = make_candidate(True)
    ok = True

    def check(name, got, want):
        nonlocal ok
        if got != want:
            ok = False
            print("FAIL", name, got, want)
    check("prefix", f("Revenue Rs 95 Cr", "Revenue 951.96 Cr"), ["95"])
    check("prefix lakh grouping", f("fine of 1,95,000", "fine of 19,500"), ["1,95,000"])
    check("source coarser", f("Rs 10,737.58 Cr", "Rs 10,738 Cr"), [])
    check("source precise", f("Rs 10,737.6 Cr", "Rs 10,737.58 Cr"), [])
    check("source precise mismatch", f("Rs 10,738 Cr", "Rs 10,737.58 Cr"), [])   # at the card's own decimals 10,738 = 10,737.58
    check("wrong digit", f("Rs 10,739 Cr", "Rs 10,737.58 Cr"), ["10,739"])
    check("cut not rounded", f("Rs 79 Cr", "Revenue 796 million"), ["79"])
    check("lakh to crore", f("Rs 16.53 Cr", "Revenue 1,653 lakh", 100), [])
    check("ten times", f("Rs 458 Cr", "Revenue 457.86 million", 10), ["458"])
    check("display whole crore", d("Rs 10,737.58 Cr", "Rs 10,738 Cr"), [])
    check("display one decimal", d("Rs 12.34 Cr", "Rs 12.3 Cr"), [])
    print("selftest", "ok" if ok else "FAILED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?")
    ap.add_argument("--platform", action="store_true")
    ap.add_argument("--cards")
    ap.add_argument("--texts")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--seed", type=int, default=2610)
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--doc")
    ap.add_argument("--stamp", default="2026-10-26")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--time-budget", type=float, default=0, help="seconds; the pass then ends cleanly and writes what is done (0 = none)")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.out or bool(args.platform) == bool(args.cards):
        ap.error("give OUT_DIR and one of --platform or --cards FILE --texts DIR")
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    args.doc = args.doc or str(out / "precision-sample.md")
    rows = rows_from_platform(args.limit) if args.platform else rows_from_files(args.cards, args.texts or ".")
    args.out_dir = str(out)
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    result = audit(rows, args)
    if result["summary"].get("stopped"):
        print(f"::warning::precision audit stopped early ({result['summary']['stopped']}); {result['summary']['cards_checked']} cards done")
    (out / "summary.json").write_text(json.dumps(result["summary"], ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "lines.json").write_text(json.dumps(result["lines"], ensure_ascii=False, indent=1), encoding="utf-8")
    write_sample(result, args)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
