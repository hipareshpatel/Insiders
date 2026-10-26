"""The release check (F170): the on/off comparison and a blind sample for every card switch that is built but off.
Read-only: no AI calls, nothing written to D1, R2 or memory. Owner rule: a card change is switched on only after (1) an
on/off comparison over the stored cards and (2) a blind sample reviewed by an independent agent. This runs (1) for all
five switches in one pass and prepares (2).

    python -I -X utf8 scripts/release_check.py OUT_DIR --platform [--limit N]               # GitHub job (maintenance.yml)
    python -I -X utf8 scripts/release_check.py OUT_DIR --cards ROWS.json --texts DIR [--dossiers DIR]   # offline
    options: --seed 170  --sample 20  --only ebitda_v2,two_parts,...  --stamp 2026-10-26

--platform reads production through the platform API like audit_precision.py: the cards (`export_cards`), each filing's
text (`text/<news_id>.json.gz` in R2) and each company's memory (`memory/<scrip>.json`). Offline: ROWS.json is a list of
export_cards rows (or {"cards": [...]}), DIR holds <news_id>.json.gz text caches, --dossiers holds <scrip>.json.

What each switch's check does (each reuses the existing script's logic, so the switch's own audit and this one agree):
  ebitda_v2          CARD_EBITDA_PROFIT_V2 (F151): results cards' table and face rendered twice, off and on
                     (audit_card_v2.py). Needs a RESULTS card with a results period, the company's memory and the text.
  same_definition    CARD_SAME_DEFINITION (F155): the same render with only that switch toggled; the table lines that
                     lose a year-ago or previous-quarter figure measured on another definition.
  consolidated_only  CARD_CONSOLIDATED_ONLY (F154): the part of it that acts on a stored card, `standalone_figures_removed`,
                     run over each consolidated RESULTS card with the standalone figures taken from memory. The other
                     part (what the model is shown: no standalone figures in the prompt, the explicit basis in the XBRL
                     table and facts block) changes only what the AI writes, so it cannot be compared without AI calls
                     and is judged by the live review after the switch is on.
  two_parts          CARD_TWO_PARTS (F152): the stored card as one list (off) against `hide_part2` + `split_card` (on)
                     (audit_two_parts.py). A card "changes" when part 2 hides a line; the layout changes on every card.
  quote_exact        QUOTE_EXACT_NUMBERS (F156): the real quote checks run with the switch off and on over the card's
                     facts, key numbers, changes and insights (audit_precision.py's `run_checks`); the lines that newly
                     fail. Replaces audit_quote_exact.py (no text) and audit_quote_rules.py (local database).

Output, per switch NAME: NAME.json (every changed card, what changed, the counts), NAME.txt (the plain-text summary),
NAME-blind.json and NAME-blind.md (a seeded sample of up to --sample changed cards for the reviewer; the two renderings
as X and Y in a seeded order, and for quote_exact the flagged lines with their quotes), NAME-key.json (which of X / Y is
on; keep it from the reviewer). Also release-check.json and release-check.txt (the counts of all five).
Limits shared by all: the text is the filing's own pages (`Document.select_text`), without the XBRL table the pipeline
puts in front or the second reading, and memory is as it stands now, not as at filing."""

from __future__ import annotations

import argparse
import contextlib
import gzip
import json
import os
import pathlib
import random
import sys
from collections import Counter, OrderedDict

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "src"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "daily_audit"))
import audit_card_v2 as v2  # noqa: E402
import audit_precision as prec  # noqa: E402
import audit_two_parts as two  # noqa: E402
from bse_intel import pipeline as P  # noqa: E402
from bse_intel.extract import Document  # noqa: E402
from bse_intel.grounding import declared_unit  # noqa: E402
from bse_intel.models import Card, Pass2Output  # noqa: E402
from onoff_facts import tagged_from_memory  # noqa: E402

ALL_SWITCHES = ("CARD_EBITDA_PROFIT_V2", "CARD_TWO_PARTS", "CARD_CONSOLIDATED_ONLY", "QUOTE_EXACT_NUMBERS", "CARD_SAME_DEFINITION")
CHECKS = (("ebitda_v2", "CARD_EBITDA_PROFIT_V2"), ("same_definition", "CARD_SAME_DEFINITION"),
          ("consolidated_only", "CARD_CONSOLIDATED_ONLY"), ("two_parts", "CARD_TWO_PARTS"), ("quote_exact", "QUOTE_EXACT_NUMBERS"))


# ---------------------------------------------------------------- pure helpers (tested)
def line_key(line: str) -> str | None:
    """What identifies a rendered line across off and on: a table or key-number line by its label, a headline or takeaway
    by its name; a fact has none (it can only be added or removed)."""
    if line.startswith(("TABLE ", "KEY ")):
        return line.split(": ", 1)[0]
    if line.startswith(("HEADLINE ", "TAKEAWAY ", "TIMELINE ")):
        return line.split(" ", 1)[0]
    return None


def line_diff(off: list[str], on: list[str]) -> dict:
    """Lines added, removed and changed (same key, different text) from off to on."""
    removed = [x for x in off if x not in on]
    added = [x for x in on if x not in off]
    changed = []
    for r in list(removed):
        key = line_key(r)
        match = next((a for a in added if key is not None and line_key(a) == key), None)
        if match is not None:
            changed.append({"before": r, "after": match})
            removed.remove(r)
            added.remove(match)
    return {"added": added, "removed": removed, "changed": changed}


def changed_by_diff(diff: dict) -> bool:
    return bool(diff["added"] or diff["removed"] or diff["changed"])


def draw_sample(records: list[dict], seed: int, n: int) -> list[dict]:
    """Up to n records in a seeded shuffle of the records sorted by news_id (so the draw does not depend on read order)."""
    pool = sorted(records, key=lambda r: str(r["news_id"]))
    random.Random(seed).shuffle(pool)
    return pool[:n]


def blind_pairs(records: list[dict], seed: int) -> tuple[list[dict], dict]:
    """The reviewer's items: X and Y are the off and on renderings in a seeded order; the key says which is on."""
    rng = random.Random(seed)
    items, key = [], {}
    for i, r in enumerate(records, 1):
        cid = f"c{i:02d}"
        on_is_x = rng.random() < 0.5
        items.append({"id": cid, "news_id": r["news_id"], "symbol": r.get("symbol"), "scrip_code": r.get("scrip_code"),
                      "pdf_url": r.get("pdf_url"), "X": r["on_lines"] if on_is_x else r["off_lines"],
                      "Y": r["off_lines"] if on_is_x else r["on_lines"]})
        key[cid] = {"news_id": r["news_id"], "on_is": "X" if on_is_x else "Y"}
    return items, key


def sample_markdown(name: str, switch: str, items: list[dict], stamp: str) -> str:
    md = [f"# {switch}: blind sample, {stamp}", "",
          "Each card is rendered two ways, X and Y, from the same stored card and the same filing. For each card judge from "
          "the filing (the pdf link) only which rendering is better for a reader and whether either states anything the "
          "filing does not support: X BETTER, Y BETTER or SAME, and list every WRONG line with its label. Do not reason "
          "about the switch; the key (which one is on) is in a separate file and is never read before the verdicts.", ""]
    for it in items:
        md += [f"## {it['id']}  {it.get('symbol') or it.get('scrip_code')} {it['news_id']}", "", f"filing: {it.get('pdf_url') or 'n/a'}", ""]
        for side in ("X", "Y"):
            md += [f"### {side}", "", *(f"- {x}" for x in it[side]), ""]
    return "\n".join(md)


def quote_lines_markdown(switch: str, items: list[dict], stamp: str) -> str:
    md = [f"# {switch}: blind sample, {stamp}", "",
          "Each line below is a quoted card line the stricter number match would newly fail. For each, judge from the filing "
          "(the quote and the pdf link) only: is the card's figure RIGHT (the filing states it, at the unit and period the "
          "card says) or WRONG (the filing does not support it)? Do not reason about the rule.", ""]
    for it in items:
        md += [f"## {it['id']}  {it.get('symbol') or it.get('scrip_code')} {it['news_id']}", "", f"filing: {it.get('pdf_url') or 'n/a'}", ""]
        md += [f"- {x}" for x in it["X"]] + [""]
    return "\n".join(md)


def summary_text(name: str, switch: str, counts: dict, changed: list[dict], notes: list[str]) -> str:
    out = [f"{switch} on/off ({name}), release check", ""]
    out += [f"- {k}: {json.dumps(v) if isinstance(v, (dict, list)) else v}" for k, v in counts.items()]
    out += ["", *notes, "", f"## Changed cards ({len(changed)})"]
    for r in changed:
        out += ["", f"### {r.get('symbol')} {r['news_id']}" + (f" {r['period']}" if r.get("period") else "")]
        out += [f"- removed: {x}" for x in r["diff"]["removed"]] + [f"- added: {x}" for x in r["diff"]["added"]]
        out += [f"- changed: {c['before']}  ->  {c['after']}" for c in r["diff"]["changed"]]
        out += [f"- {x}" for x in r.get("extra") or []]
    return "\n".join(out)


@contextlib.contextmanager
def switches_on(*names: str):
    """Every card switch off but the named ones on, for the block, restored after (the checks read the environment)."""
    before = {n: os.environ.get(n) for n in ALL_SWITCHES}
    for n in ALL_SWITCHES:
        os.environ[n] = "1" if n in names else "0"
    try:
        yield
    finally:
        for n, v in before.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v


# ---------------------------------------------------------------- the five checks
def _record(row: dict, card: dict, off: list[str], on: list[str], **extra) -> dict:
    return {"news_id": row["news_id"], "symbol": row.get("symbol"), "scrip_code": str(row.get("scrip_code")),
            "pdf_url": row.get("pdf_url"), "period": (card.get("results") or {}).get("period"),
            "off_lines": off, "on_lines": on, "diff": line_diff(off, on), **extra}


def check_table(card: dict, dossier: dict, row: dict, text: str | None, period: str, switch: str) -> dict:
    """ebitda_v2 / same_definition: the results table and face rendered with the one switch off and on."""
    with switches_on():
        off = v2._render(card, dossier, row, text, period, False)
    with switches_on(switch):
        on = v2._render(card, dossier, row, text, period, switch == "CARD_EBITDA_PROFIT_V2")
    return _record(row, card, off, on)


def check_consolidated(card: dict, dossier: dict, row: dict, period: str) -> dict | None:
    """consolidated_only: `standalone_figures_removed` over the stored card, standalone figures from memory."""
    tagged = tagged_from_memory(dossier, period, "CONSOLIDATED")
    if not any(m.period == period for m in tagged.metrics):
        return None
    standalone = tagged_from_memory(dossier, period, "STANDALONE")
    out = Pass2Output.model_validate({"is_material": True, "event_type": card.get("event_type") or "RESULTS",
                                      "timeline_entry": card.get("timeline_entry") or "x",
                                      "card": {k: card[k] for k in Card.model_fields if k in card and card[k] is not None}})

    def lines(o: Pass2Output) -> list[str]:
        return v2.face_lines(o) + [f"TIMELINE {o.timeline_entry}"]
    off = lines(out)
    notes = P.standalone_figures_removed(out, tagged, standalone)
    return _record(row, card, off, lines(out), extra=notes)


def check_two_parts(card: dict, dossier: dict, row: dict, text: str) -> dict:
    """two_parts: one list as stored (off) against part 1 and part 2 after hiding (on). Changed means a line is hidden."""
    on = two.render_on(card, dossier, row, text)
    off_lines = [x["text"] for x in two.stored_lines(card)]
    on_lines = [f"[PART 1] {x['text']}" for x in on["part1"] if x["field"] != "block"] \
        + [f"[PART 2] {x['text']}" for x in on["part2"] if x["field"] != "block"]
    hidden = [h["text"] for h in on["hidden"]]
    kept = [x["text"] for x in on["part1"] + on["part2"] if x["field"] != "block"]
    diff = {"added": [], "removed": [t for t in off_lines if t in hidden and t not in kept], "changed": []}
    rec = _record(row, card, off_lines, on_lines, extra=[f"hidden [{h['field']}] {h['text']}  <- {h['why']}" for h in on["hidden"]],
                  part1=len(on["part1"]), part2=len(on["part2"]), hidden=on["hidden"])
    rec["diff"] = diff
    return rec


def check_quote_exact(card: dict, text: str, row: dict) -> dict:
    """quote_exact: the real quote checks, switch off and on; the problems only the on run raises."""
    unit = declared_unit(text)
    off = prec.run_checks(card, text, unit, "off")
    on = prec.run_checks(card, text, unit, "f156")
    new = [p for p in on if p not in off]
    located = [{**prec.locate(card, p), "figures": prec.figures_of(p), "problem": p} for p in new]
    rec = _record(row, card, off, on, lines=located, extra=[f"newly fails ({x['kind']}) {x['claim']}  | quote: {x['quote']}" for x in located])
    rec["diff"] = {"added": new, "removed": [p for p in off if p not in on], "changed": []}
    return rec


# ---------------------------------------------------------------- reading the stored cards, texts and memory
class PlatformSource:
    def __init__(self, limit: int | None):
        from bse_intel.settings import get_settings
        from bse_intel.sinks import make_sink
        self.sink = make_sink(get_settings())
        self.limit = limit
        self._memory: OrderedDict[str, dict] = OrderedDict()

    def rows(self):
        after, n = ["", ""], 0
        while True:
            page = self.sink.query("export_cards", [after[0], after[1], 100])
            if not page:
                break
            after = [page[-1]["filed_at"], page[-1]["news_id"]]
            for r in page:
                yield r
                n += 1
                if self.limit and n >= self.limit:
                    return
            if len(page) < 100:
                break

    def text_body(self, news_id: str):
        return self.sink.get_object(P.text_key(news_id))

    def dossier(self, scrip: str) -> dict:
        if scrip not in self._memory:
            self._memory[scrip] = self.sink.get_dossier(scrip) or {}
            while len(self._memory) > 48:   # a memory is large and the cards are read in date order, not by company
                self._memory.popitem(last=False)
        return self._memory[scrip]


class FileSource:
    def __init__(self, cards: str, texts: str, dossiers: str | None, limit: int | None):
        loaded = json.load(open(cards, encoding="utf-8"))
        rows = loaded["cards"] if isinstance(loaded, dict) else loaded
        self._rows = rows[:limit] if limit else rows
        self.texts = pathlib.Path(texts)
        self.dossiers = pathlib.Path(dossiers) if dossiers else None

    def rows(self):
        yield from self._rows

    def text_body(self, news_id: str):
        for p in (self.texts / f"{news_id}.json.gz", self.texts / P.text_key(news_id).split("/", 1)[1]):
            if p.exists():
                return p.read_bytes()
        return None

    def dossier(self, scrip: str) -> dict:
        path = self.dossiers / f"{scrip}.json" if self.dossiers else None
        if path and path.exists():
            loaded = json.load(open(path, encoding="utf-8"))
            return loaded.get("dossier", loaded) if isinstance(loaded, dict) else {}
        return {}


# ---------------------------------------------------------------- the run
def run(source, wanted: tuple[str, ...]) -> dict:
    records = {name: [] for name, _ in CHECKS}
    seen = {name: 0 for name, _ in CHECKS}
    skipped = {name: Counter() for name, _ in CHECKS}
    errors = {name: [] for name, _ in CHECKS}
    cards = 0
    for row in source.rows():
        cards += 1
        try:
            raw = row.get("card_json")
            card = json.loads(raw) if isinstance(raw, str) else raw or {}
        except Exception:
            for name in wanted:
                skipped[name]["unreadable card"] += 1
            continue
        results = (card.get("event_type") or row.get("event_type")) == "RESULTS"
        period = (card.get("results") or {}).get("period")
        scrip = str(row.get("scrip_code"))
        body = source.text_body(row["news_id"])
        try:
            text = Document.from_cache(json.loads(gzip.decompress(body))).select_text(10_000_000, []) if body else None
        except Exception:
            text = None
        dossier = None

        def memory():
            nonlocal dossier
            if dossier is None:
                dossier = source.dossier(scrip)
            return dossier

        for name, switch in CHECKS:
            if name not in wanted:
                continue
            try:
                if name in ("ebitda_v2", "same_definition"):
                    if not results or not period:
                        skipped[name]["not a results card with a period"] += 1
                    elif not memory():
                        skipped[name]["no memory"] += 1
                    else:   # a card with no text is rendered without a printed EBITDA, as a refresh with no text would
                        rec = check_table(card, memory(), row, text, period, switch)
                        rec["has_text"] = text is not None
                        seen[name] += 1
                        records[name].append(rec)
                elif name == "consolidated_only":
                    if not results or not period or card.get("basis") != "CONSOLIDATED":
                        skipped[name]["not a consolidated results card"] += 1
                    elif not memory():
                        skipped[name]["no memory"] += 1
                    else:
                        rec = check_consolidated(card, memory(), row, period)
                        if rec is None:
                            skipped[name]["no consolidated figures in memory"] += 1
                        else:
                            seen[name] += 1
                            records[name].append(rec)
                elif name == "two_parts":
                    if text is None:
                        skipped[name]["no text"] += 1
                    elif not memory():
                        skipped[name]["no memory"] += 1
                    else:
                        seen[name] += 1
                        records[name].append(check_two_parts(card, memory(), row, text))
                else:
                    if text is None:
                        skipped[name]["no text"] += 1
                    else:
                        seen[name] += 1
                        records[name].append(check_quote_exact(card, text, row))
            except Exception as exc:   # a card a check cannot read is reported, not hidden
                errors[name].append({"news_id": row.get("news_id"), "error": f"{type(exc).__name__}: {exc}"})
    return {"cards": cards, "records": records, "seen": seen, "skipped": skipped, "errors": errors}


def finish(name: str, switch: str, result: dict, out: pathlib.Path, seed: int, n: int, stamp: str) -> dict:
    recs = result["records"][name]
    if name == "two_parts":
        changed = [r for r in recs if r["hidden"]]
    elif name == "quote_exact":
        changed = [r for r in recs if r["lines"]]
    else:
        changed = [r for r in recs if changed_by_diff(r["diff"])]
    counts: dict = {"cards_in_store": result["cards"], "cards_checked": result["seen"][name], "cards_changed": len(changed),
                    "lines_added": sum(len(r["diff"]["added"]) for r in changed),
                    "lines_removed": sum(len(r["diff"]["removed"]) for r in changed),
                    "lines_changed": sum(len(r["diff"]["changed"]) for r in changed),
                    "skipped": dict(result["skipped"][name]), "errors": len(result["errors"][name])}
    notes: list[str] = []
    if name == "two_parts":
        k = max(len(recs), 1)
        counts["lines_per_card_off"] = round(sum(len(r["off_lines"]) for r in recs) / k, 1)
        counts["part1_per_card_on"] = round(sum(r["part1"] for r in recs) / k, 1)
        counts["part2_per_card_on"] = round(sum(r["part2"] for r in recs) / k, 1)
        counts["part2_lines_hidden"] = sum(len(r["hidden"]) for r in recs)
        counts["hidden_by_field"] = dict(Counter(h["field"] for r in recs for h in r["hidden"]))
        notes.append("Part 2 lines hidden are listed under each card: the lead reads each against the filing (a hidden line "
                     "that is right is a false hide). The layout changes on every card; only a hidden line is counted as a change.")
    if name == "ebitda_v2":
        counts["printed_ebitda_found"] = sum(any("(Filing)" in x for x in r["on_lines"]) for r in recs)
        counts["cards_with_text"] = sum(bool(r.get("has_text")) for r in recs)
        notes.append("A card with no text is rendered without a printed EBITDA or headline profit, so it shows only what the "
                     "switch does with memory alone.")
    if name == "same_definition":
        notes.append("Only that switch is toggled; it acts on the results table (the year-ago and previous-quarter figures).")
    if name == "consolidated_only":
        counts["figures_removed"] = sum(len(r["extra"]) for r in changed)
        notes.append("Only the code that edits a stored card is compared. What the model is shown on a consolidated card "
                     "(no standalone figures, the basis named in the XBRL table and facts block) changes only what the AI writes "
                     "and cannot be compared without AI calls: it is judged by the live review once the switch is on.")
    if name == "quote_exact":
        counts["lines_newly_failing"] = sum(len(r["lines"]) for r in changed)
        notes.append("Upper bound: the XBRL table, memory and the second reading are not available here, so a line that passes "
                     "on those today can show as failing in both runs alike; only the lines the switch adds are counted.")
    # the blind sample
    if name == "quote_exact":
        picked = draw_sample(changed, seed, n)
        items = [{"id": f"c{i:02d}", "news_id": r["news_id"], "symbol": r["symbol"], "scrip_code": r["scrip_code"],
                  "pdf_url": r["pdf_url"],
                  "X": [f"{x['kind']}: {x['claim']} | quote: {x['quote']} | figures not found in the quote: {x['figures']}" for x in r["lines"]]}
                 for i, r in enumerate(picked, 1)]
        key = {it["id"]: {"news_id": it["news_id"], "on_is": "all lines newly fail"} for it in items}
        md = quote_lines_markdown(switch, items, stamp)
    else:
        pool = changed
        if name == "two_parts" and len(changed) < n:
            # fewer hidden-line cards than the sample: fill with layout-only cards, marked in the key
            rest = draw_sample([r for r in recs if not r["hidden"]], seed + 1, n - len(changed))
            pool = changed + rest
        picked = draw_sample(pool, seed, n)
        items, key = blind_pairs(picked, seed)
        for it, r in zip(items, picked):
            key[it["id"]]["changed"] = r in changed
        md = sample_markdown(name, switch, items, stamp)
    (out / f"{name}.json").write_text(json.dumps({"switch": switch, "counts": counts, "errors": result["errors"][name][:50],
                                                  "changed": [{k: v for k, v in r.items() if k not in ("on_lines", "off_lines")}
                                                              | {"off": r["off_lines"], "on": r["on_lines"]} for r in changed]},
                                                 ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"{name}.txt").write_text(summary_text(name, switch, counts, changed, notes), encoding="utf-8")
    (out / f"{name}-blind.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"{name}-blind.md").write_text(md, encoding="utf-8")
    (out / f"{name}-key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    return {"switch": switch, **counts, "sample": len(items)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--platform", action="store_true")
    ap.add_argument("--cards")
    ap.add_argument("--texts")
    ap.add_argument("--dossiers")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--seed", type=int, default=170)
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--only", default=",".join(n for n, _ in CHECKS))
    ap.add_argument("--stamp", default="2026-10-26")
    args = ap.parse_args()
    if bool(args.platform) == bool(args.cards):
        ap.error("give OUT_DIR and one of --platform or --cards FILE --texts DIR")
    wanted = tuple(x for x in args.only.split(",") if x)
    unknown = [x for x in wanted if x not in dict(CHECKS)]
    if unknown:
        ap.error(f"unknown check {unknown}; known: {[n for n, _ in CHECKS]}")
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    source = PlatformSource(args.limit) if args.platform else FileSource(args.cards, args.texts or ".", args.dossiers, args.limit)
    result = run(source, wanted)
    totals = {name: finish(name, switch, result, out, args.seed, args.sample, args.stamp)
              for name, switch in CHECKS if name in wanted}
    (out / "release-check.json").write_text(json.dumps(totals, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "release-check.txt").write_text("\n".join(
        [f"Release check, {args.stamp}: {result['cards']} stored cards read", ""]
        + [f"{n:18} {t['switch']}: checked {t['cards_checked']}, changed {t['cards_changed']}, added {t['lines_added']}, "
           f"removed {t['lines_removed']}, changed lines {t['lines_changed']}, errors {t['errors']}, sample {t['sample']}"
           for n, t in totals.items()]), encoding="utf-8")
    print(json.dumps(totals, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
