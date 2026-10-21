"""Recompute a stored card's code-made blocks from memory, with no AI and no PDF (the cached text when there is one).

The blocks on a card's face (the results table in the statement's own lines, the order or deal size, the rating
ladder, the case stage, management's earlier guidance, the fundamentals footer) are computed by code when a card is
written. Cards written before a block existed, or before a fix to one, keep the old version: on 20 Oct 2026 only 14
of 849 live cards carried the blocks of the 19 Oct redesign (design audit, docs/audit/design/cards-2026-10-20.md).
This puts each card's blocks through today's code, from the company's memory as it stood at the filing, and drops
signal types that are now off. What the model wrote is not touched.

The results table's comparatives are judged against the filing's text (dossier.results_snapshot's `printed`): the
cached text is read when this machine has it; without it a refresh never brings back a comparative the stored table
does not have, since that is how a restated column was taken off (review 6, 2026-10-20).
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from .call_summary import card_takeaways, remember_call_points
from .card_context import case_stage, guidance_recall, memory_context, rating_change
from .impact import high_reasons
from .dossier import call_results_snapshot, dossier_as_of, latest_fundamentals, results_snapshot
from .models import Card, Filing, Pass2Output
from .prices import point_in_time
from .signals import SIGNALS_OFF, priced_for, scale_parts, volume_strip

log = logging.getLogger(__name__)

BLOCKS = ("results", "volume_strip", "call_memory", "scale", "rating_change", "case_stage", "guidance_recall", "memory_context",
          "fundamentals")


def blocks(card: dict, dossier: dict, filing: Filing, company: dict | None, footer=(), prices=None, buckets=None,
           printed: str | None = None) -> dict:
    """The card's code blocks as today's code makes them. `card` is the stored card_json; `printed` the filing's
    text, when it is cached."""
    event_type = card.get("event_type") or ""
    before = dossier_as_of(dossier, filing.filed_at, inclusive=False)
    current = dossier_as_of(dossier, filing.filed_at)
    priced = point_in_time(company or {}, filing.filed_at, prices, buckets) if prices else None
    priced = priced or priced_for(company, filing)
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": event_type, "timeline_entry": card.get("timeline_entry") or "",
        "card": {k: card[k] for k in Card.model_fields if k in card},
    })
    facts = [f.text for f in out.card.what_happened]
    # the filing's text is not kept with the card: its headline and points stand in for it (rating_change reads an
    # earlier grade from the letter's "from [ICRA]AA+" only when memory has none)
    text = " ".join([out.card.headline, *facts])
    return {
        "results": (results_snapshot(current, filing.news_id, footer, printed=printed,
                                     like=None if printed else card.get("results")) if event_type == "RESULTS"
                    else call_results_snapshot(current, filing.filed_at, footer) if event_type == "CONCALL_PRESENTATION" else None),
        "volume_strip": volume_strip(current, filing.news_id) if event_type == "MONTHLY_BUSINESS_UPDATE" else None,
        "call_memory": (card_takeaways(current, filing.news_id, filing.filed_at)
                           if event_type == "CONCALL_PRESENTATION" else None),
        "scale": scale_parts(before, out, priced, filing.filed_at),
        "rating_change": rating_change(before, current, filing.news_id, text) if event_type == "DEBT_RATINGS" else None,
        "case_stage": case_stage(event_type, out.card.headline, facts, [w.text for w in out.card.why_it_matters]),
        "guidance_recall": guidance_recall(before, event_type, filing.filed_at),
        "memory_context": memory_context(before, event_type, filing.filed_at, filing.news_id),
        "fundamentals": latest_fundamentals(current, footer),
    }


def refresh(card: dict, dossier: dict, filing: Filing, company: dict | None, footer=(), prices=None,
            buckets=None, printed: str | None = None) -> tuple[dict, list[str]]:
    """The card with its blocks recomputed and signals of types now off removed; and the keys that changed."""
    # a block today's code cannot rebuild (memory no longer holds the filing's figures) keeps its old version: a
    # refresh never takes a table off a card
    made = blocks(card, dossier, filing, company, footer, prices, buckets, printed)
    new = {**card, **{k: v for k, v in made.items() if v or not card.get(k)}}
    new["signals"] = [s for s in card.get("signals") or [] if s.get("type") not in SIGNALS_OFF]
    changed = [k for k in (*BLOCKS, "signals") if json.dumps(new.get(k), sort_keys=True) != json.dumps(card.get(k), sort_keys=True)]
    return new, changed


def filed_text(pipeline, news_id: str) -> str | None:
    """The filing's cached text (the laptop's text cache; GitHub's maintenance runs have none), or None."""
    cached = getattr(pipeline, "_cached_text", None)
    data = cached(news_id) if cached else None
    if not data:
        return None
    from .extract import Document

    try:
        return Document.from_cache(data).select_text(10_000_000, []) or None
    except Exception:  # a damaged cache entry is the same as none
        log.warning("cached text of %s unreadable", news_id)
        return None


def run(pipeline, scrips: set[str] | None = None, dry_run: bool = False, page: int = 50) -> dict:
    """Every stored card (or the given companies'), in date order, written back when a block changed."""
    sink = pipeline.sink
    after, seen, written, failed = ["", ""], 0, 0, 0
    changed_keys: dict[str, int] = {}
    dossiers: dict[str, dict | None] = {}
    companies: dict[str, dict | None] = {}
    dirty: set[str] = set()   # companies whose memory took call takeaways from their stored cards
    while True:
        rows = sink.query("export_cards", [after[0], after[1], page])
        if not rows:
            break
        after = [rows[-1]["filed_at"], rows[-1]["news_id"]]
        batch = []
        for row in rows:
            scrip = row["scrip_code"]
            if scrips and scrip not in scrips:
                continue
            seen += 1
            if scrip not in dossiers:
                dossiers[scrip] = sink.get_dossier(scrip)
                companies[scrip] = sink.company(scrip)
            dossier, company = dossiers[scrip], companies[scrip]
            if not dossier:
                continue
            try:
                card = json.loads(row["card_json"])
                filing = Filing(news_id=row["news_id"], scrip_code=scrip, company_name=row.get("company_name") or "",
                                headline=row.get("headline") or "", subject="", filed_at=row["filed_at"],
                                filing_date=row.get("filing_date") or row["filed_at"][:10])
                footer = pipeline.prompts.sector_for((company or {}).get("industry")).footer
                printed = filed_text(pipeline, row["news_id"]) if card.get("event_type") == "RESULTS" else None
                new, changed = refresh(card, dossier, filing, company, footer, pipeline._prices, pipeline._buckets,
                                       printed)
            except (ValidationError, ValueError, KeyError, TypeError) as exc:
                failed += 1
                log.warning("card %s not refreshed: %s", row.get("news_id"), exc)
                continue
            # the clear-event rule (impact.py) on the new blocks: HIGH whatever the points, never over a veto
            facts = " ".join([new.get("headline") or ""] + [f.get("text", "") if isinstance(f, dict) else str(f)
                                                              for f in new.get("what_happened") or []])
            score = dict(new.get("score") or {})
            impact = row.get("impact_level")
            if impact != "HIGH" and not score.get("vetoes"):
                from .pipeline import top_exit

                why = high_reasons(new, new.get("event_type") or "", new["signals"], top_exit(facts))
                if why:
                    impact = "HIGH"
                    new["score"] = {**score, "impact": "HIGH", "reasons": [*(score.get("reasons") or []), "Impact: " + "; ".join(why)]}
                    changed.append("impact")
            if card.get("event_type") == "CONCALL_PRESENTATION" and card.get("call_takeaways"):
                # cards written before the takeaways went into memory (2026-10-21): their checked ones, for the
                # company page's quarterly summary (refresh-summaries rebuilds it)
                before = json.dumps(dossier.get("call_points", []), sort_keys=True)
                remember_call_points(dossier, row["news_id"], row["filed_at"], card["call_takeaways"])
                if json.dumps(dossier.get("call_points", []), sort_keys=True) != before:
                    dirty.add(scrip)
            if not changed:
                continue
            for k in changed:
                changed_keys[k] = changed_keys.get(k, 0) + 1
            out = dict(row)
            out.pop("card_json")
            batch.append({**out, "impact_level": impact, "card": new})
        if batch and not dry_run:
            written += sink.execute("cards_upsert", batch) or 0
        elif batch:
            written += len(batch)
        if len(rows) < page:
            break
    if not dry_run:
        for scrip in dirty:
            sink.put_dossier(scrip, dossiers[scrip])
    return {"cards": seen, "changed": written, "failed": failed, "by_block": changed_keys, "dry_run": dry_run,
            "memories_with_call_points": len(dirty)}
