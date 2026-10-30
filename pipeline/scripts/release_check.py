"""The release check (F170): the on/off comparison and a blind sample for every card switch that is built but off.
Read-only: no AI calls, nothing written to D1, R2 or memory. Owner rule: a card change is switched on only after (1) an
on/off comparison over the stored cards and (2) a blind sample reviewed by an independent agent. This runs (1) for all
every switch in one pass and prepares (2).

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

Three more checks (F171-F173), each replayed only as far as the stored card, its memory and its text allow:
  grounded_figures   CARD_GROUNDED_FIGURES (F171): (a) the footer KPI rows of a results table, `results_snapshot` rendered
                     off and on (a figure in MW or GW shown as crore, a base in another unit); (b) a card whose deal stage is
                     CANCELLED, `gate.is_terminated` run on the filing text (the Reg 30 template row "withdrawal /
                     cancellation or suspension ... Not Applicable"); (c) an order amount of the event XBRL: the card stores
                     the orders it read (`event_xbrl.orders`), so an amount under Rs 1 lakh is found exactly; when it was the
                     deal's only order the model's own figure, which the 0 replaced, is not stored: NOT REPLAYABLE (the
                     cards are listed). With two orders of which one is dropped the deal is replayed with `apply_orders`.
  guidance_dated     CARD_GUIDANCE_DATED (F172): `signals._promises` replayed with the real code over memory before and after
                     the filing, the model's promise and watch updates taken from the status histories that memory recorded
                     for this filing (and `dossier.merge`'s refusal counted from the same entries). A stored guidance signal
                     that the off replay does not reproduce (memory rewritten since, an update memory never recorded) is NOT
                     REPLAYABLE and is listed, as is a card with such a signal and no memory.
  one_basis          CARD_ONE_BASIS (F173): `one_basis.apply` on the stored card's words (tagged figures and history from
                     memory) and `one_basis.apply_card_json` on the stored card, off against on. Complete.
  year_check        MEMORY_YEAR_CHECK (F177): a results card's table and face (`results_snapshot`, `results_card.build` over memory's
                     file figures) rendered off and on, plus a MEMORY line for each figure the table would have read and the
                     switch holds, with its reason. A card with a results table and no memory is NOT REPLAYABLE (listed). Not
                     replayable at all: a year figure the model wrote into a card's words from the PDF (only the table and the
                     face are code's), and an event card that quotes a full-year figure.
  footer_plausible  CARD_FOOTER_PLAUSIBLE (F182): the footer KPIs of the stored card (its sector rows of the results table and
                     the `fundamentals` strip) worked out again from memory off and on, the figures the switch hides listed with
                     their reason (GIC Housing's NIM 19.63%). A card with a footer KPI and no memory is NOT REPLAYABLE (listed).
  eps_follows_profit CARD_EPS_FOLLOWS_PROFIT (F183): a results table's EPS line, `results_snapshot` off and on over memory
                     (an EPS change far above the profit change, with no share-count event, is not shown; dilution is
                     shown). Needs a RESULTS card with a table and memory.
  eps_whole         CARD_EPS_WHOLE (F188): a results table's EPS line, `results_snapshot` off and on over memory (the whole
                     company's EPS with the continuing one beside it when they differ). Needs a RESULTS card with a table and
                     memory; memory read again since F188 for the periods it shows, else the line is unchanged.
  text_support      CARD_TEXT_SUPPORT (TODO 142): `card_support.apply` (names, words, small counts, dates and profit labels the sources do
                     not print) on a deep copy of each stored card; every item it drops is listed (news_id, company, field,
                     text, the missing words, a 300-character window of the filing near the best-matching place). Out of sample:
                     the 34 in-sample cards of scripts/measure_card_support.py (its MARKS) are left out and counted. `sources`
                     are built as pipeline.ground builds them, (text, headline, subject, memory view, scale block), EXCEPT:
                     (1) text is the filing's own pages without the XBRL table the pipeline puts in front, so the card's stored
                     `results` block (code-built from that table) is appended to it; (2) memory is `view_as_of(dossier,
                     filed_at)` as it stands now, without the `printed` periods and `filing_text` the live call also passes;
                     (3) the scale block (market cap, revenue, net worth, debt) is empty. Each can only make a drop that live
                     would not make, so the drop list is an upper bound. The blind sample (up to 60 dropped items, seeded, no
                     verdict hints) is for a reviewer to judge TRUE (supported, the drop loses true content) or FALSE.
A card or part that cannot be replayed is never faked: it is counted as "not_replayable", written to NAME-unreplayable.json
and NAME-unreplayable.md (the stored lines and the pdf link, for the blind sample: judge the stored card as it is).

Output, per switch NAME: NAME.json (every changed card, what changed, the counts), NAME.txt (the plain-text summary),
NAME-blind.json and NAME-blind.md (a seeded sample of up to --sample changed cards for the reviewer; the two renderings
as X and Y in a seeded order, and for quote_exact the flagged lines with their quotes), NAME-key.json (which of X / Y is
on; keep it from the reviewer). Also release-check.json and release-check.txt (the counts of all the switches).
Limits shared by all: the text is the filing's own pages (`Document.select_text`), without the XBRL table the pipeline
puts in front or the second reading, and memory is as it stands now, not as at filing."""

from __future__ import annotations

import argparse
import contextlib
import copy
import gzip
import json
import os
import pathlib
import random
import re
import signal
import sys
import time
import tomllib
from collections import Counter, OrderedDict

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "src"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "daily_audit"))
import audit_card_v2 as v2  # noqa: E402
import audit_precision as prec  # noqa: E402
import audit_two_parts as two  # noqa: E402
from bse_intel import card_support, event_xbrl, gate, one_basis, signals  # noqa: E402
from bse_intel import pipeline as P  # noqa: E402
from bse_intel.dossier import dossier_as_of, latest_fundamentals, results_snapshot, view_as_of, with_year_hold  # noqa: E402
from bse_intel.extract import Document  # noqa: E402
from bse_intel.grounding import declared_unit  # noqa: E402
from bse_intel.models import Card, DealValue, Filing, Pass2Output  # noqa: E402
from bse_intel.sinks.base import SinkUnavailable  # noqa: E402
from measure_card_support import MARKS as IN_SAMPLE_MARKS  # noqa: E402
from onoff_facts import tagged_from_memory  # noqa: E402

ALL_SWITCHES = ("CARD_EBITDA_PROFIT_V2", "CARD_TWO_PARTS", "CARD_CONSOLIDATED_ONLY", "QUOTE_EXACT_NUMBERS", "CARD_SAME_DEFINITION",
                "CARD_GROUNDED_FIGURES", "CARD_GUIDANCE_DATED", "CARD_ONE_BASIS", "MEMORY_YEAR_CHECK",
                "CARD_FOOTER_PLAUSIBLE", "CARD_EPS_FOLLOWS_PROFIT", "CARD_EPS_WHOLE", "CARD_TEXT_SUPPORT")
CHECKS = (("ebitda_v2", "CARD_EBITDA_PROFIT_V2"), ("same_definition", "CARD_SAME_DEFINITION"),
          ("consolidated_only", "CARD_CONSOLIDATED_ONLY"), ("two_parts", "CARD_TWO_PARTS"), ("quote_exact", "QUOTE_EXACT_NUMBERS"),
          ("grounded_figures", "CARD_GROUNDED_FIGURES"), ("guidance_dated", "CARD_GUIDANCE_DATED"), ("one_basis", "CARD_ONE_BASIS"),
          ("year_check", "MEMORY_YEAR_CHECK"), ("footer_plausible", "CARD_FOOTER_PLAUSIBLE"),
          ("eps_follows_profit", "CARD_EPS_FOLLOWS_PROFIT"), ("eps_whole", "CARD_EPS_WHOLE"),
          ("text_support", "CARD_TEXT_SUPPORT"))
TEXT_SUPPORT_SAMPLE = 60


# ---------------------------------------------------------------- pure helpers (tested)
def line_key(line: str) -> str | None:
    """What identifies a rendered line across off and on: a table or key-number line by its label, a headline or takeaway
    by its name; a fact has none (it can only be added or removed)."""
    if line.startswith(("TABLE ", "KEY ", "DEAL ", "SIGNAL ", "MEMORY ", "WHY ")):
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


# ---------------------------------------------------------------- the three checks of F171-F173
GUIDANCE_SIGNALS = ("PROMISE_DELIVERED", "GUIDANCE_BREACH", "WATCH_RESOLVED")
_SECTOR_FOOTERS: list[dict] | None = None


def _footer_specs() -> list[dict]:
    """Every sector's footer figure (config/sectors.toml): a stored KPI line is matched to its spec by metric and label."""
    global _SECTOR_FOOTERS
    if _SECTOR_FOOTERS is None:
        loaded = tomllib.loads((HERE.parent / "config" / "sectors.toml").read_text(encoding="utf-8"))
        _SECTOR_FOOTERS = [dict(spec) for entry in loaded.values() if isinstance(entry, dict) for spec in entry.get("footer", [])]
    return _SECTOR_FOOTERS


def footer_spec(line: dict) -> dict:
    metric = str(line.get("key") or "")[4:]
    mine = [s for s in _footer_specs() if s.get("metric") == metric]
    found = next((s for s in mine if s.get("label") == line.get("label")), mine[0] if mine else None)
    if found:
        return found
    return {"metric": metric, "label": line.get("label") or metric,
            "format": {"pct": "pct", "cr": "cr", "inr": "inr"}.get(line.get("unit"), "num"), "aliases": []}


def kpi_lines(snap: dict | None, specs: list[dict]) -> list[str]:
    out = []
    for spec in specs:
        row = (snap or {}).get(f"kpi:{spec['metric']}")
        if isinstance(row, dict):
            out.append(f"TABLE {spec['label']}: " + ", ".join(f"{k} {row[k]}" for k in row))
        else:
            out.append(f"TABLE {spec['label']}: (not shown)")
    return out


def deal_line(kind: str, deal) -> str:
    if deal is None:
        return f"DEAL {kind}: (no deal)"
    return (f"DEAL {kind}: kind {deal.kind}, amount_cr {deal.amount_cr}, counterparty {deal.counterparty}, "
            f"includes_gst {deal.includes_gst}, stage {deal.stage}")


def _unrep(row: dict, reason: str, lines: list[str] | None = None) -> dict:
    return {"news_id": row["news_id"], "symbol": row.get("symbol"), "pdf_url": row.get("pdf_url"), "reason": reason,
            "stored": lines or []}


def stored_lines(card: dict) -> list[str]:
    """The stored card's words and table, as a reviewer reads them."""
    def text(x):
        return x.get("text") if isinstance(x, dict) else str(x)
    lines = [f"HEADLINE {card.get('headline')}", f"TAKEAWAY {card.get('takeaway')}"]
    lines += [f"FACT {text(f)}" for f in card.get("what_happened") or []]
    lines += [f"KEY {k.get('label')}: {k.get('value')}" + (f" ({k.get('change')})" if k.get("change") else "")
              for k in card.get("key_numbers") or [] if isinstance(k, dict)]
    deal = card.get("deal_value")
    if isinstance(deal, dict):
        lines.append("DEAL " + ", ".join(f"{k} {deal[k]}" for k in ("kind", "amount_cr", "counterparty", "stage") if k in deal))
    lines += v2.table_lines(card.get("results"))
    return lines


def check_grounded(card: dict, dossier: dict | None, row: dict, text: str | None, period: str | None, results: bool) -> dict:
    """grounded_figures: the three parts of F171, each as far as the stored card, memory and text replay it."""
    off, on, unrep = [], [], []
    info: Counter = Counter()
    # (a) the footer KPI rows of the results table: `results_snapshot` with the switch off and on
    kpis = [x for x in (card.get("results") or {}).get("lines") or [] if str(x.get("key") or "").startswith("kpi:")]
    if results and period and kpis:
        if not dossier:
            unrep.append(_unrep(row, "footer KPI rows: the company's memory is not available", stored_lines(card)))
        else:
            specs = [footer_spec(x) for x in kpis]
            current = dossier_as_of(dossier, row["filed_at"])
            like = None if text else card.get("results")
            with switches_on():
                off += kpi_lines(results_snapshot(current, row["news_id"], specs, printed=text, like=like), specs)
            with switches_on("CARD_GROUNDED_FIGURES"):
                on += kpi_lines(results_snapshot(current, row["news_id"], specs, printed=text, like=like), specs)
            info["footer_kpi_cards_checked"] += 1
    # (b) a deal marked cancelled: the filing's text must terminate something (pipeline.apply_deal_guards)
    deal = card.get("deal_value")
    if isinstance(deal, dict) and deal.get("stage") == "CANCELLED":
        if text is None:
            unrep.append(_unrep(row, "cancelled deal: the filing text is not in R2", stored_lines(card)))
        else:
            with switches_on():
                was = gate.is_terminated(text[:20000])
            with switches_on("CARD_GROUNDED_FIGURES"):
                now = gate.is_terminated(text[:20000])
            info["cancelled_deals_checked"] += 1
            if not was:
                info["cancelled_deal_not_reproduced_off"] += 1   # the text read here does not terminate it even off
            off.append("DEAL stage: CANCELLED")
            on.append("DEAL stage: CANCELLED" if (now or not was) else "DEAL stage: OTHER")
    # (c) an order amount of the event XBRL
    orders = ((card.get("event_xbrl") or {}).get("orders")) or []
    if orders:
        info["cards_with_event_xbrl_orders"] += 1
        try:
            found = [event_xbrl.Order(**o) for o in orders]
        except TypeError:
            found = None
            unrep.append(_unrep(row, "order amount: the stored orders are unreadable", stored_lines(card)))
        if found is not None:
            kept = [o for o in found if o.amount_cr >= 0.01]
            if len(kept) != len(found):
                info["order_amount_under_1_lakh"] += 1
                if len(found) == 1:
                    unrep.append(_unrep(row, "order amount: the file's figure was read as rupees and stored as "
                                        f"{found[0].amount_cr:g} Cr; with the switch on the deal keeps the model's own figure, "
                                        "which the stored card no longer holds", stored_lines(card)))
                elif len(kept) == 1:
                    stored = DealValue.model_validate(deal) if isinstance(deal, dict) else None
                    shell = type("Shell", (), {"deal_value": copy.deepcopy(stored)})()
                    event_xbrl.apply_orders(shell, kept)
                    off.append(deal_line("order", stored))
                    on.append(deal_line("order", shell.deal_value))
    rec = _record(row, card, off, on)
    rec["info"], rec["unreplayable"] = dict(info), unrep
    return rec


def _promise_updates(dossier: dict, news_id: str) -> tuple[list[dict], list[dict]]:
    """The updates memory recorded for this filing, as the model's updates (the status histories keep the filing's id)."""
    promises = [{"guidance_id": g["id"], "status": h["status"], "evidence": h.get("evidence") or ""}
                for g in dossier.get("guidance") or [] for h in g.get("status_history") or [] if h.get("source_news_id") == news_id]
    watches = [{"watch_id": w["id"], "status": h["status"], "evidence": h.get("evidence") or ""}
               for w in dossier.get("watchlist") or [] for h in w.get("status_history") or [] if h.get("source_news_id") == news_id]
    return promises, watches


def _signal_line(s) -> str:
    return f"SIGNAL {s.ref or ''}: {s.type} {s.severity} | {s.text}"


def _stored_signal_line(s: dict) -> str:
    return f"SIGNAL {s.get('ref')}: {s.get('type')} {s.get('severity')} | {s.get('text')}"


def check_guidance(card: dict, dossier: dict | None, row: dict) -> dict:
    """guidance_dated: `signals._promises` (the real code) over memory before and after the filing, off and on; the
    refusal in `dossier.merge` counted from the same recorded updates."""
    stored = [s for s in card.get("signals") or [] if isinstance(s, dict) and s.get("type") in GUIDANCE_SIGNALS]
    if not dossier:
        rec = _record(row, card, [], [])
        rec["info"] = {}
        rec["unreplayable"] = ([_unrep(row, "guidance signals on the card, but the company's memory is not available",
                                       [_stored_signal_line(s) for s in stored])] if stored else [])
        return rec
    news_id, filed_at = row["news_id"], row["filed_at"]
    before, after = dossier_as_of(dossier, filed_at, inclusive=False), dossier_as_of(dossier, filed_at)
    promises, watches = _promise_updates(dossier, news_id)
    out = Pass2Output.model_validate({"is_material": True, "event_type": card.get("event_type") or "OTHER", "timeline_entry": "x",
                                      "card": {"impact_level": "LOW", "headline": "Guidance update", "takeaway": "x", "what_happened": ["x"]},
                                      "dossier_delta": {"promise_updates": promises, "watch_updates": watches}})
    filing = Filing(news_id=news_id, scrip_code=str(row.get("scrip_code")), company_name=row.get("company_name") or row.get("symbol") or "x",
                    headline=row.get("headline") or "", subject="", filed_at=filed_at, filing_date=filed_at[:10],
                    event_type=card.get("event_type"))
    with switches_on():
        off_sig = signals._promises(before, after, out, filing)
    with switches_on("CARD_GUIDANCE_DATED"):
        on_sig = signals._promises(before, after, out, filing)
    off, on = [_signal_line(s) for s in off_sig], [_signal_line(s) for s in on_sig]
    # dossier.merge: an update that memory recorded and the switch would have refused (the target stays as said)
    from bse_intel.guidance_dated import why_no_verdict
    for g in dossier.get("guidance") or []:
        for h in g.get("status_history") or []:
            if h.get("source_news_id") == news_id and h.get("status") in ("DELIVERED", "ON_TRACK", "DELAYED", "MISSED") \
                    and (g.get("given_on") or "") < h.get("as_of", ""):
                why = why_no_verdict(g, after.get("financial_metrics", []), news_id)
                off.append(f"MEMORY {g['id']}: status {h['status']} recorded")
                on.append(f"MEMORY {g['id']}: " + (f"status {h['status']} recorded" if not why else f"not recorded, stays as said ({why})"))
    # fidelity: the stored guidance signals the off replay reproduces; the rest cannot be replayed
    have = {(s.type, s.ref) for s in off_sig}
    missing = [s for s in stored if (s.get("type"), s.get("ref")) not in have]
    rec = _record(row, card, off, on)
    rec["info"] = {"stored_guidance_signals": len(stored), "stored_signals_reproduced_off": len(stored) - len(missing)}
    rec["unreplayable"] = ([_unrep(row, "stored guidance signal not reproduced from memory's recorded updates (memory rewritten since, "
                                        "or the update was never recorded)", [_stored_signal_line(s) for s in missing])]
                           if missing else [])
    return rec


def check_year(card: dict, dossier: dict | None, row: dict, text: str | None, period: str | None) -> dict:
    """year_check: the results table and face, `v2._render`, with MEMORY_YEAR_CHECK off and on, and the figures it holds."""
    if not dossier:
        rec = _record(row, card, [], [])
        rec["info"] = {}
        rec["unreplayable"] = [_unrep(row, "results table on the card, but the company's memory is not available", stored_lines(card))]
        return rec
    current = dossier_as_of(dossier, row["filed_at"])
    with switches_on():
        off = v2._render(card, dossier, row, text, period, False)
    with switches_on("MEMORY_YEAR_CHECK"):
        on = v2._render(card, dossier, row, text, period, False)
        held = (results_snapshot(current, row["news_id"], (), printed=text, like=None if text else card.get("results")) or {}).get("held") or []
        whole = with_year_hold(current)
    on += [f"MEMORY held {h['metric']} {h['period']}: {h['reason']}" for h in held]
    rec = _record(row, card, off, on)
    rec["info"] = {"cards_with_a_held_figure_in_memory": 1 if (whole or {}).get("year_held") else 0}
    rec["unreplayable"] = []
    return rec


def _basis_lines(card: dict) -> list[str]:
    """A stored card's words, key numbers and results table, in the order a reader meets them (keyed for the diff)."""
    def text(x):
        return x.get("text") if isinstance(x, dict) else str(x)
    lines = [f"HEADLINE {card.get('headline')}", f"TAKEAWAY {card.get('takeaway')}", f"TIMELINE {card.get('timeline_entry')}"]
    lines += [f"FACT {text(f)}" for f in card.get("what_happened") or []]
    lines += [f"WHY {i}: {text(w)}" for i, w in enumerate(card.get("why_it_matters") or [], 1)]
    lines += [f"KEY {i}: {k.get('label')} | {k.get('value')} | {k.get('change') or ''}"
              for i, k in enumerate(card.get("key_numbers") or [], 1) if isinstance(k, dict)]
    results = card.get("results")
    if isinstance(results, dict):
        for spec in results.get("lines") or []:
            r = results.get(spec["key"])
            if isinstance(r, dict):
                lines.append(f"TABLE {spec['key']}: {spec.get('label')} | {spec.get('note') or ''} | "
                             + ", ".join(f"{k} {r[k]}" for k in r))
    else:
        lines.append("TABLE: (none)")
    return lines


def check_one_basis(card: dict, dossier: dict | None, row: dict, period: str | None) -> dict:
    """one_basis: `apply` on the stored card's words (figures and history from memory), then `apply_card_json` on the card."""
    shown = {k: card[k] for k in Card.model_fields if k in card and card[k] is not None}
    out = Pass2Output.model_validate({"is_material": True, "event_type": card.get("event_type") or "OTHER",
                                      "timeline_entry": card.get("timeline_entry") or "x", "card": shown})
    dossier = dossier or {}
    current = dossier_as_of(dossier, row["filed_at"]) if dossier else {}
    history = (current or {}).get("financial_metrics") or []
    tagged = tagged_from_memory(dossier, period, card.get("basis")) if dossier and period else None

    def with_words(base: dict) -> dict:
        merged = copy.deepcopy(base)
        merged.update(out.card.model_dump())
        merged["timeline_entry"] = out.timeline_entry
        return merged

    off_card = with_words(card)   # normalised the same way as the on card, so only the switch can differ
    with switches_on("CARD_ONE_BASIS"):
        notes = one_basis.apply(out, tagged, history, card.get("event_type"))
        on_card = with_words(card)
        notes += one_basis.apply_card_json(on_card, current)
    rec = _record(row, card, _basis_lines(off_card), _basis_lines(on_card), extra=notes)
    rec["info"], rec["unreplayable"] = {}, []
    return rec


def _kpi_specs(card: dict) -> list[dict]:
    """The footer specs a stored card shows: its results table's kpi rows and its fundamentals strip's labels."""
    specs = [footer_spec(x) for x in (card.get("results") or {}).get("lines") or [] if str(x.get("key") or "").startswith("kpi:")]
    for k in (card.get("fundamentals") or {}).get("kpis") or []:
        found = next((x for x in _footer_specs() if x.get("label") == k.get("label")), None)
        if found and found not in specs:
            specs.append(found)
    return specs


def _fundamentals_lines(block: dict | None) -> list[str]:
    return [f"TABLE footer {k.get('label')}: {k.get('value')} ({k.get('period')})" for k in (block or {}).get("kpis") or []]


def check_footer(card: dict, dossier: dict | None, row: dict, text: str | None, period: str | None) -> dict:
    """footer_plausible: the footer rows of the results table and the fundamentals strip, off and on, and the figures hidden."""
    specs = _kpi_specs(card)
    if not dossier:
        rec = _record(row, card, [], [])
        rec["info"], rec["unreplayable"] = {}, [_unrep(row, "footer KPI on the card, but the company's memory is not available", stored_lines(card))]
        return rec
    current = dossier_as_of(dossier, row["filed_at"])
    like = None if text else card.get("results")

    def render() -> tuple[list[str], list[dict]]:
        snap = results_snapshot(current, row["news_id"], specs, printed=text, like=like) if card.get("results") and period else None
        funds = latest_fundamentals(current, specs)
        return kpi_lines(snap, [x for x in specs if card.get("results")]) + _fundamentals_lines(funds), \
            [*((snap or {}).get("footer_hidden") or []), *(funds.get("footer_hidden") or [])]

    with switches_on():
        off, _ = render()
    with switches_on("CARD_FOOTER_PLAUSIBLE"):
        on, hidden = render()
    on += [f"MEMORY hidden {h['label']} {h['period']}: {h['reason']}" for h in hidden]
    rec = _record(row, card, off, on)
    rec["info"], rec["unreplayable"] = {"cards_with_a_footer_figure_hidden": 1 if hidden else 0}, []
    return rec


def check_eps(card: dict, dossier: dict | None, row: dict, text: str | None, period: str | None,
              switch: str = "CARD_EPS_FOLLOWS_PROFIT") -> dict:
    """eps_follows_profit / eps_whole: the results table (`results_snapshot`), with that EPS switch off and on."""
    if not dossier:
        rec = _record(row, card, [], [])
        rec["info"], rec["unreplayable"] = {}, [_unrep(row, "results table on the card, but the company's memory is not available", stored_lines(card))]
        return rec
    current = dossier_as_of(dossier, row["filed_at"])
    like = None if text else card.get("results")

    def lines(snap: dict | None) -> list[str]:
        eps = (snap or {}).get("eps")
        out = ["TABLE EPS: " + (", ".join(f"{k} {eps[k]}" for k in eps) if isinstance(eps, dict) else "(not shown)")]
        return out + [f"MEMORY hidden EPS change: {h['reason']}" for h in (snap or {}).get("eps_hidden") or []]

    with switches_on():
        off = lines(results_snapshot(current, row["news_id"], (), printed=text, like=like))
    with switches_on(switch):
        on = lines(results_snapshot(current, row["news_id"], (), printed=text, like=like))
    rec = _record(row, card, off, on)
    rec["info"], rec["unreplayable"] = {}, []
    return rec


# ---------------------------------------------------------------- text_support (TODO 142)
IN_SAMPLE_IDS = frozenset(m[0] for m in IN_SAMPLE_MARKS)
IN_SAMPLE_REASON = "in-sample card (measure_card_support MARKS)"


def support_items(card: Card):
    """(field, text) of every item card_support may drop (the same reading as scripts/measure_card_support.py)."""
    t = card.track_next
    for name in ("pending_approvals", "catalysts", "risks"):
        for x in getattr(t, name):
            yield "track_next", x
    for m in t.milestones:
        yield "track_next", f"{m.what} {m.when or ''}".strip()
    if card.core_catalyst:
        yield "core_catalyst", card.core_catalyst
    for c in card.notable_changes:
        if c.why:
            yield "notable_changes", c.why
    for i in card.why_it_matters:
        yield "why_it_matters", i.text
    for f in card.what_happened:
        yield "what_happened", f.text
    for k in card.key_numbers:
        yield "key_numbers", f"{k.label} {k.value} {k.change or ''}".strip()


def text_window(item: str, text: str, missing: list[str], width: int = 300) -> str | None:
    """`width` characters of the filing around the best-matching place for the item: the item's own words the filing does
    print (the rarest of them, at its first print); None when none of them is there."""
    low = text.lower()
    gone = {w.lower() for w in missing}
    best = None
    for word in {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]{4,}", item)} - gone:
        n = low.count(word)
        if n and (best is None or n < best[0] or (n == best[0] and len(word) > len(best[1]))):
            best = (n, word)
    if best is None:
        return None
    at = low.find(best[1])
    start = max(0, at - (width - len(best[1])) // 2)
    return " ".join(text[start:start + width].split())


TEXT_SUPPORT_SOURCES: dict[str, tuple[str, str]] = {}   # news_id -> (filing text, memory view) of the cards with a drop


def check_text_support(card: dict, dossier: dict | None, row: dict, text: str) -> dict:
    """text_support: `card_support.apply` over a deep copy of the stored card; every dropped item with its reason."""
    shown = {k: card[k] for k in Card.model_fields if k in card and card[k] is not None}
    out = Pass2Output.model_validate({"is_material": True, "event_type": card.get("event_type") or "OTHER",
                                      "timeline_entry": card.get("timeline_entry") or "x", "card": shown})
    before = list(support_items(out.card))
    view = view_as_of(dossier, row["filed_at"]) if dossier else None
    results = json.dumps(card.get("results") or {}, ensure_ascii=False)   # stands in for the XBRL table ahead of the text
    sources = (f"{text}\n{results}", row.get("headline") or "", row.get("subject") or "",
               json.dumps(view or {}, ensure_ascii=False), "")
    work = copy.deepcopy(out)
    notes = card_support.apply(work, sources, text)
    left = Counter(support_items(work.card))
    src = card_support._Sources(sources)
    label_notes = [n for n in notes if "label '" in n]
    drops = []
    for field, item in before:
        if left[(field, item)] > 0:
            left[(field, item)] -= 1
            continue
        why = card_support._rejected(item, src) if field not in ("what_happened", "key_numbers") else []
        missing = list(why)
        if not why:
            why = [n for n in label_notes if n.startswith(field)][:1] or ["(profit label not on the figure's line)"]
        drops.append({"news_id": row["news_id"], "company": row.get("symbol") or row.get("company_name"), "field": field,
                      "item": item, "note": why, "filing_window": text_window(item, text, missing)})
    if drops:   # kept for the blind sample's judges: the filing text and memory as the check read them
        TEXT_SUPPORT_SOURCES[row["news_id"]] = (text, json.dumps(view or {}, ensure_ascii=False, indent=1))
    kept = [f"{f}: {t}" for (f, t), n in left.items() for _ in range(n)]
    rec = _record(row, card, [f"{f}: {t}" for f, t in before], kept, drops=drops)
    rec["diff"] = {"added": [], "removed": [f"{d['field']}: {d['item']}" for d in drops], "changed": []}
    rec["info"], rec["unreplayable"] = {"items_checked": len(before), "items_dropped": len(drops),
                                        "cards_without_memory": int(not dossier)}, []
    return rec


def text_support_markdown(switch: str, drops: list[dict], stamp: str) -> str:
    md = [f"# {switch}: every dropped item by field, {stamp}", ""]
    for field in sorted({d["field"] for d in drops}):
        group = [d for d in drops if d["field"] == field]
        md += [f"## {field} ({len(group)})", ""]
        for d in group:
            md += [f"- {d['company']} {d['news_id']}: {d['item']}", f"  - note: {'; '.join(d['note'])}",
                   f"  - filing near it: {d['filing_window'] or '(none of its words found)'}"]
        md.append("")
    return "\n".join(md)


def text_support_blind(drops: list[dict], rows: dict, seed: int, n: int) -> tuple[list[dict], dict, str]:
    """Up to n dropped items in a seeded random order. No note, no check field, no verdict hint: only the company, the item
    as the card said it, the card's headline and the filing link. The key (field and note) is kept apart."""
    pool = sorted(drops, key=lambda d: (d["news_id"], d["field"], d["item"]))
    random.Random(seed).shuffle(pool)
    items, key = [], {}
    for i, d in enumerate(pool[:n], 1):
        r = rows.get(d["news_id"]) or {}
        items.append({"id": f"t{i:02d}", "news_id": d["news_id"], "company": d["company"], "headline": r.get("headline"),
                      "pdf_url": r.get("pdf_url"), "item": d["item"]})
        key[f"t{i:02d}"] = {"news_id": d["news_id"], "field": d["field"], "note": d["note"]}
    md = [f"# CARD_TEXT_SUPPORT: blind sample of {len(items)} items", "",
          "Each item is a sentence from a published card. From the filing (the pdf link) judge: TRUE (the filing, or what it "
          "reports of the company's own earlier disclosures, supports it, so removing it loses true content) or FALSE (nothing "
          "supports it: invented, from outside knowledge, or wrong). One verdict and a one-line reason each.", ""]
    for it in items:
        md += [f"## {it['id']}  {it['company']} {it['news_id']}", "", f"filing: {it['pdf_url'] or 'n/a'}",
               f"card headline: {it['headline']}", "", f"- {it['item']}", ""]
    return items, key, "\n".join(md)


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
_STOP: list[str] = []   # a SIGTERM or SIGINT (GitHub's cancel) puts its name here; the loop then ends cleanly
DEAD_RUN = 10   # cards in a row whose platform reads all failed: the Worker is down, so stop and keep what is done


def _on_signal(signum, _frame) -> None:
    _STOP.append(signal.Signals(signum).name)


def run(source, wanted: tuple[str, ...], out: pathlib.Path | None = None, deadline: float | None = None) -> dict:
    """One pass over the stored cards. F216: every record is appended to out/records.jsonl as it is computed, and the
    pass ends cleanly (`stopped` says why) at the deadline (time.monotonic), on SIGTERM/SIGINT, or when the platform
    stops answering, so a long run always has something to upload."""
    records = {name: [] for name, _ in CHECKS}
    seen = {name: 0 for name, _ in CHECKS}
    skipped = {name: Counter() for name, _ in CHECKS}
    errors = {name: [] for name, _ in CHECKS}
    cards = 0
    stopped = None
    dead = 0
    row_index: dict[str, dict] = {}
    sink_file = open(out / "records.jsonl", "a", encoding="utf-8") if out else None

    def keep(name: str, rec: dict) -> None:
        records[name].append(rec)
        if sink_file:
            sink_file.write(json.dumps({"check": name, "record": rec}, ensure_ascii=False, default=str) + "\n")

    rows = iter(source.rows())
    while True:
        if _STOP:
            stopped = f"stopped by {_STOP[0]}"
            break
        if deadline is not None and time.monotonic() >= deadline:
            stopped = "time budget reached"
            break
        if dead >= DEAD_RUN:
            stopped = f"the platform did not answer for {DEAD_RUN} cards in a row"
            break
        try:
            row = next(rows)
        except StopIteration:
            break
        except SinkUnavailable as exc:
            stopped = f"the platform did not answer the card list ({exc})"
            break
        cards += 1
        dead_card = False
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
        try:
            body = source.text_body(row["news_id"])
        except SinkUnavailable:
            dead += 1
            for name in wanted:
                skipped[name]["platform did not answer"] += 1
            continue
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
                        keep(name, rec)
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
                            keep(name, rec)
                elif name == "two_parts":
                    if text is None:
                        skipped[name]["no text"] += 1
                    elif not memory():
                        skipped[name]["no memory"] += 1
                    else:
                        seen[name] += 1
                        keep(name, check_two_parts(card, memory(), row, text))
                elif name == "grounded_figures":
                    seen[name] += 1
                    keep(name, check_grounded(card, memory() or None, row, text, period, results))
                elif name == "guidance_dated":
                    if not any(isinstance(x, dict) and x.get("type") in GUIDANCE_SIGNALS for x in card.get("signals") or []) \
                            and not memory():
                        skipped[name]["no guidance signal and no memory"] += 1
                    else:
                        seen[name] += 1
                        keep(name, check_guidance(card, memory() or None, row))
                elif name == "year_check":
                    if not results or not period:
                        skipped[name]["not a results card with a period"] += 1
                    else:
                        seen[name] += 1
                        keep(name, check_year(card, memory() or None, row, text, period))
                elif name == "footer_plausible":
                    if not _kpi_specs(card):
                        skipped[name]["no footer KPI on the card"] += 1
                    else:
                        seen[name] += 1
                        keep(name, check_footer(card, memory() or None, row, text, period if results else None))
                elif name in ("eps_follows_profit", "eps_whole"):
                    if not results or not period:
                        skipped[name]["not a results card with a period"] += 1
                    else:
                        seen[name] += 1
                        keep(name, check_eps(card, memory() or None, row, text, period, switch))
                elif name == "text_support":
                    if row["news_id"] in IN_SAMPLE_IDS:
                        skipped[name][IN_SAMPLE_REASON] += 1
                    elif text is None:
                        skipped[name]["no text"] += 1
                    else:
                        seen[name] += 1
                        keep(name, check_text_support(card, memory() or None, row, text))
                        row_index[row["news_id"]] = {"headline": row.get("headline"), "pdf_url": row.get("pdf_url")}
                elif name == "one_basis":
                    seen[name] += 1
                    keep(name, check_one_basis(card, memory() or None, row, period if results else None))
                else:
                    if text is None:
                        skipped[name]["no text"] += 1
                    else:
                        seen[name] += 1
                        keep(name, check_quote_exact(card, text, row))
            except Exception as exc:   # a card a check cannot read is reported, not hidden
                errors[name].append({"news_id": row.get("news_id"), "error": f"{type(exc).__name__}: {exc}"})
                dead_card = dead_card or isinstance(exc, SinkUnavailable)
        dead = dead + 1 if dead_card else 0
        if sink_file:
            sink_file.flush()   # this card's records are on disk before the next one is read
    if sink_file:
        sink_file.close()
    return {"cards": cards, "records": records, "seen": seen, "skipped": skipped, "errors": errors, "stopped": stopped,
            "row_index": row_index}


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
    unrep = [u for r in recs for u in r.get("unreplayable") or []]
    for r in recs:
        for k, v in (r.get("info") or {}).items():
            counts[k] = counts.get(k, 0) + v
    if unrep or name in ("grounded_figures", "guidance_dated", "year_check", "footer_plausible"):
        counts["not_replayable"] = dict(Counter(u["reason"] for u in unrep))
        counts["not_replayable_cards"] = len({u["news_id"] for u in unrep})
        notes.append("NOT REPLAYABLE offline (listed in NAME-unreplayable.json and .md for the blind sample, which judges the "
                     "stored card as it is): " + "; ".join(f"{n} x {why}" for why, n in counts["not_replayable"].items()) + ".")
    if name == "grounded_figures":
        notes.append("Replayed: (a) the footer KPI rows of a results table through `results_snapshot`, (b) a CANCELLED deal through "
                     "`gate.is_terminated` on the stored text, (c) an event-XBRL order amount from the orders the card stores, "
                     "where a second order remains to apply. Not replayable: a deal whose only order was read as rupees (the "
                     "model's own figure is gone from the stored card).")
    if name == "guidance_dated":
        notes.append("`signals._promises` is run as it is, over memory before and after the filing; the model's updates are the "
                     "ones memory recorded for the filing (status histories). The MEMORY lines are updates `dossier.merge` would "
                     "not have recorded. Memory is as it stands now (restated figures, later screener fills).")
    if name == "year_check":
        notes.append("`results_snapshot` and `results_card.build` (over memory's file figures) rendered with the switch off and on; "
                     "a MEMORY line names each held figure the table reads, with its reason. Replayed: the results table and "
                     "the card's face. Not replayable: a full-year figure the model wrote into a card's words from the PDF, and "
                     "an event card that quotes a year (only the table and the face are code's). Memory is as it stands now.")
    if name == "footer_plausible":
        notes.append("`results_snapshot` and `latest_fundamentals` over memory with the switch off and on, for the footer KPIs the "
                     "card shows; a MEMORY line names each hidden figure with its reason. Memory is as it stands now, so a figure "
                     "the card stored from another reading (the AI's own, GIC Housing's NIM) is replayed only when memory holds it.")
    if name == "eps_follows_profit":
        notes.append("`results_snapshot` over memory with the switch off and on; a MEMORY line names an EPS change not shown. "
                     "Corporate actions are read from memory as it stands now.")
    if name == "eps_whole":
        notes.append("`results_snapshot` over memory with the switch off and on; the TABLE EPS line shows the whole company's "
                     "figure and `continuing` where they differ. Memory is as it stands now: a period whose file was not read "
                     "again since F188 has no whole-company EPS in it, and its line stays as it was.")
    if name == "one_basis":
        notes.append("`one_basis.apply` on the stored words (figures from memory's results rows, history from memory as of the "
                     "filing) and `apply_card_json` on the stored card. Memory is as it stands now, not as at filing.")
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
    if name == "text_support":
        drops = [d for r in recs for d in r["drops"]]
        counts["in_sample_cards_excluded"] = result["skipped"][name][IN_SAMPLE_REASON]
        counts["items_by_field"] = dict(Counter(d["field"] for d in drops))
        notes.append("Out of sample: the in-sample cards are left out. `sources` differ from the live call: the filing text without "
                     "the XBRL table (the card's stored `results` block stands in), memory as it stands now through `view_as_of` "
                     "without the printed-period and filing-text arguments, and an empty scale block; a drop here can be one live "
                     "would not make, so the counts are an upper bound.")
        items, key, md = text_support_blind(drops, result.get("row_index") or {}, seed, TEXT_SUPPORT_SAMPLE)
        (out / "text_support.md").write_text(text_support_markdown(switch, drops, stamp), encoding="utf-8")
        (out / f"{name}-blind.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / f"{name}-blind.md").write_text(md, encoding="utf-8")
        (out / f"{name}-key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
        sources_dir = out / f"{name}-sources"   # what the judges read: each sampled card's filing text and its memory
        for it in items:
            text, memory = TEXT_SUPPORT_SOURCES.get(it["news_id"], ("", "{}"))
            sources_dir.mkdir(exist_ok=True)
            (sources_dir / f"{it['news_id']}.filing.txt").write_text(text, encoding="utf-8")
            (sources_dir / f"{it['news_id']}.memory.json").write_text(memory, encoding="utf-8")
        (out / f"{name}.json").write_text(json.dumps({"switch": switch, "counts": counts, "errors": result["errors"][name][:50],
                                                      "dropped": drops}, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / f"{name}.txt").write_text(summary_text(name, switch, counts, changed, notes), encoding="utf-8")
        return {"switch": switch, **counts, "sample": len(items)}
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
    if unrep:
        (out / f"{name}-unreplayable.json").write_text(json.dumps(unrep, ensure_ascii=False, indent=1), encoding="utf-8")
        md_unrep = [f"# {switch}: not replayable offline, {stamp}", "",
                    "These stored cards carry a line the switch could change, but the change cannot be replayed from the stored "
                    "card, its memory and its text. For each, judge from the filing (the pdf link) only whether the stored line "
                    "is RIGHT or WRONG, and say what the correct figure or status is.", ""]
        for i, u in enumerate(draw_sample(unrep, seed, n), 1):
            md_unrep += [f"## u{i:02d}  {u.get('symbol')} {u['news_id']}", "", f"filing: {u.get('pdf_url') or 'n/a'}",
                         f"why not replayable: {u['reason']}", "", *(f"- {x}" for x in u["stored"]), ""]
        (out / f"{name}-unreplayable.md").write_text("\n".join(md_unrep), encoding="utf-8")
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
    ap.add_argument("--time-budget", type=float, default=0,
                    help="seconds; the pass stops cleanly then and the summaries are written from what is done (0 = none)")
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
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    deadline = time.monotonic() + args.time_budget if args.time_budget > 0 else None
    result = run(source, wanted, out, deadline)
    if result["stopped"]:
        print(f"::warning::release check stopped early ({result['stopped']}); results below cover {result['cards']} cards")
    totals = {name: finish(name, switch, result, out, args.seed, args.sample, args.stamp)
              for name, switch in CHECKS if name in wanted}
    (out / "release-check.json").write_text(json.dumps(totals, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "release-check.txt").write_text("\n".join(
        [f"Release check, {args.stamp}: {result['cards']} stored cards read"
         + (f" (PARTIAL, stopped early: {result['stopped']})" if result["stopped"] else ""), ""]
        + [f"{n:18} {t['switch']}: checked {t['cards_checked']}, changed {t['cards_changed']}, added {t['lines_added']}, "
           f"removed {t['lines_removed']}, changed lines {t['lines_changed']}, errors {t['errors']}, sample {t['sample']}"
           f", not replayable {t.get('not_replayable_cards', 0)}"
           for n, t in totals.items()]), encoding="utf-8")
    print(json.dumps(totals, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
