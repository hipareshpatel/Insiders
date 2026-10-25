"""Two parts on every card (owner-approved TODO 21, F152), behind CARD_TWO_PARTS (default off).

Part 1, "From the filing (checked)": the headline, the facts and key numbers that carry a quote code found in the
filing, computed figures whose inputs are all sourced, and the blocks code makes from the exchange's files (results
table, deal size, rating change, volume strip, corporate action, annual-report checks). Part 2, "Our reading (AI)":
everything else - takeaway, core catalyst, why it matters, notable changes, track next, call takeaways, signals,
memory context, and any fact, key number or estimate with no code-verified source. The sort is a code rule
(`split_card`); the model never says which part a line is in.

A line in part 1 that fails its check is handled as before (dropped, or the card held). A line in part 2 that states a
number or claim failing the existing checks (grounding.check_card, pipeline.check_quoted_numbers, grounding.check_claims,
quant.check) is hidden alone (`hide_part2`), so the card is not held for it. No check is changed or loosened: the same
functions run, on one line at a time, and what they refuse is removed from part 2 before the whole-card checks run.
No AI."""

from __future__ import annotations

from types import SimpleNamespace

from . import gate
from .grounding import check_card, check_claims
from .models import Fact, TrackNext

VERSION = 1

# Blocks (whole fields of the card's JSON) by part; list fields are sorted line by line in `split_card`.
PART1_BLOCKS = ("results", "scale", "deal_value", "rating_change", "volume_strip", "corporate_action", "annual_checks",
                "fundamentals")
PART2_BLOCKS = ("signals", "memory_context", "guidance_recall", "call_memory", "case_stage", "call_read", "themes")
PART2_LISTS = ("why_it_matters", "notable_changes", "missing_disclosures")


def _quote_ok(quote: str | None, text: str, reading: str) -> bool:
    """The quote is the filing's own sentence, whole or with small differences (the test check_quotes applies)."""
    if not quote or not text:
        return False
    return gate.quote_found(quote, text, reading) or gate.quote_near(quote, text, reading) is not None


def _get(item, key):
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def part_of(field: str, item, text: str, reading: str = "") -> int:
    """1 or 2: the part one line of a list field belongs to (the mapping table in docs/TRACKER.md, F152)."""
    if field in ("what_happened", "key_numbers"):
        quote = None if isinstance(item, str) else _get(item, "quote")
        return 1 if _quote_ok(quote, text, reading) else 2
    if field == "quantified_impact":
        inputs = _get(item, "inputs") or []
        sourced = bool(inputs) and all(_get(i, "source") in ("FILING", "MEMORY") for i in inputs)
        return 1 if _get(item, "check") == "VERIFIED" and not _get(item, "unsourced_inputs") and sourced else 2
    return 2


def split_card(card: dict, text: str, reading: str = "", hidden: list[dict] | None = None) -> dict:
    """The `parts` block of a stored card: for each list field the indexes in part 1 and in part 2, the blocks in each
    part, and what part 2 hid. Index lists point at the card's final lists, so it is built after every edit."""
    part1: dict = {"headline": True}
    part2: dict = {}
    for field in ("what_happened", "key_numbers", "quantified_impact"):
        items = card.get(field) or []
        sides = [part_of(field, it, text, reading) for it in items]
        if 1 in sides:
            part1[field] = [i for i, s in enumerate(sides) if s == 1]
        if 2 in sides:
            part2[field] = [i for i, s in enumerate(sides) if s == 2]
    part1["blocks"] = [b for b in PART1_BLOCKS if card.get(b)]
    if card.get("takeaway"):
        part2["takeaway"] = True
    if card.get("core_catalyst"):
        part2["core_catalyst"] = True
    for field in PART2_LISTS:
        if card.get(field):
            part2[field] = list(range(len(card[field])))
    shown = [i for i, it in enumerate(card.get("call_takeaways") or []) if isinstance(it, dict) and it.get("verified")]
    if shown:   # only a verified takeaway is shown (call_summary.check_ai_takeaways)
        part2["call_takeaways"] = shown
    track = card.get("track_next") or {}
    if any(track.get(k) for k in ("milestones", "kpis_to_verify", "pending_approvals", "catalysts", "risks")):
        part2["track_next"] = True
    part2["blocks"] = [b for b in PART2_BLOCKS if card.get(b)]
    return {"v": VERSION, "part1": part1, "part2": part2, "hidden": list(hidden or [])}


def hide_part2(card, sources: tuple[str, ...], *, text: str, reading: str, known: str, unit: int | None) -> list[dict]:
    """Remove, in place, each part 2 line whose number or claim fails the existing checks; return what was hidden.

    A line is run through the same checks the whole card gets, alone in a probe card: grounding.check_card (every
    figure against the sources, at the filing's unit), pipeline.check_quoted_numbers (a point's figures against its own
    quote), grounding.check_claims ("first", "record") and quant.check (an estimate's inputs and arithmetic). Part 1
    lines are never touched here. The card's last fact is never hidden."""
    from . import pipeline as P   # late: pipeline imports this module

    if card is None:
        return []
    quant_all = P.check_quant(card.quantified_impact, *sources)
    derived_all = [i["computed"] for i in quant_all.items
                   if i.get("check") == "VERIFIED" and not i.get("unsourced_inputs") and i.get("computed") is not None]

    def probe(**changes):
        base = {"headline": "Probe line for the checks", "takeaway": "", "what_happened": [Fact(text="Probe", quote=None)],
                "why_it_matters": [], "key_numbers": [], "notable_changes": [], "track_next": TrackNext(),
                "quantified_impact": [], "deal_value": None, "call_takeaways": [], "missing_disclosures": []}
        return card.model_copy(update={**base, **changes})

    def problems(p, quotes=True) -> list[str]:
        out = [f"figure not found: {u}" for u in check_card(p, *sources, derived=derived_all).ungrounded]
        out += [f"claim not supported: {c}" for c in check_claims(p, *sources)]
        if quotes:
            out += P.check_quoted_numbers(SimpleNamespace(card=p), text, unit, reading, known)[0]
        return out

    hidden: list[dict] = []

    def hide(field: str, label: str, why: list[str]) -> None:
        hidden.append({"field": field, "text": label[:300], "why": "; ".join(why)[:300]})

    if card.takeaway:
        why = problems(probe(takeaway=card.takeaway), quotes=False)
        if why:
            hide("takeaway", card.takeaway, why)
            card.takeaway = ""
    kept = []
    for ins in card.why_it_matters:
        why = problems(probe(why_it_matters=[ins]))
        if why:
            hide("why_it_matters", ins.text, why)
        else:
            kept.append(ins)
    card.why_it_matters = kept
    kept = []
    for ch in card.notable_changes:
        why = problems(probe(notable_changes=[ch]))
        if why:
            hide("notable_changes", " ".join(str(x) for x in (ch.metric, ch.previous, ch.current, ch.change) if x), why)
        else:
            kept.append(ch)
    card.notable_changes = kept
    kept = []
    for kpi in card.track_next.kpis_to_verify:
        why = problems(probe(track_next=TrackNext(kpis_to_verify=[kpi])), quotes=False)
        if why:
            hide("track_next", f"{kpi.kpi} {kpi.target or ''}".strip(), why)
        else:
            kept.append(kpi)
    card.track_next.kpis_to_verify = kept
    kept = []
    for kn in card.key_numbers:
        why = [] if part_of("key_numbers", kn, text, reading) == 1 else problems(probe(key_numbers=[kn]))
        if why:
            hide("key_numbers", f"{kn.label}: {kn.value} {kn.change or ''}".strip(), why)
        else:
            kept.append(kn)
    card.key_numbers = kept
    kept, left = [], len(card.what_happened)
    for fact in card.what_happened:
        why = [] if part_of("what_happened", fact, text, reading) == 1 else problems(probe(what_happened=[fact]), quotes=False)
        if why and left > 1:   # never the card's last fact
            hide("what_happened", fact.text, why)
            left -= 1
        else:
            kept.append(fact)
    card.what_happened = kept
    kept = []
    for est in card.quantified_impact:
        q = P.check_quant([est], *sources)
        item = q.items[0] if q.items else est
        why = [] if part_of("quantified_impact", item, text, reading) == 1 else (
            [f"input not found: {u}" for u in q.unsourced] + (["arithmetic does not match"] if q.mismatches else []))
        if why:
            hide("quantified_impact", est.label, why)
        else:
            kept.append(est)
    card.quantified_impact = kept
    if not card.takeaway and card.why_it_matters:   # the feed row needs one line; a checked point stands in
        card.takeaway = card.why_it_matters[0].text[:240]
    return hidden
