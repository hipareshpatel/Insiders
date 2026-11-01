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

import copy
import json
import logging

from pydantic import ValidationError

from .backup import RunBackup, card_after_row
from .call_summary import card_takeaways, remember_call_points
from .corporate_actions import card_block as corporate_action_block
from .card_context import case_stage, guidance_recall, memory_context, rating_change
from .impact import high_reasons
from .nse import FileCapReached
from . import footer_plausible, guided_actual, one_basis, results_one_line, words_figures, year_ago_label
from .dossier import call_results_snapshot, dossier_as_of, latest_fundamentals, results_snapshot
from .models import Card, Filing, Pass2Output
from .prices import point_in_time
from .signals import SIGNALS_OFF, priced_for, scale_parts, volume_strip
from .settings import card_adjusted_profit_label, card_footer_plausible, card_one_basis, card_results_one_line, card_words_match_figures, card_year_ago_label

log = logging.getLogger(__name__)

# every key blocks() makes: one left out is rebuilt but never saved on its own (corporate_action, 22 Oct 2026: the
# refresh after the corporate-actions history wrote it only where another block happened to change)
BLOCKS = ("results", "volume_strip", "call_memory", "scale", "rating_change", "case_stage", "guidance_recall", "memory_context",
          "fundamentals", "corporate_action")


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
                    else call_results_snapshot(current, filing.filed_at, footer, before) if event_type == "CONCALL_PRESENTATION" else None),
        "volume_strip": volume_strip(current, filing.news_id) if event_type == "MONTHLY_BUSINESS_UPDATE" else None,
        "call_memory": (card_takeaways(current, filing.news_id, filing.filed_at)
                           if event_type == "CONCALL_PRESENTATION" else None),
        "scale": scale_parts(before, out, priced, filing.filed_at),
        "rating_change": rating_change(before, current, filing.news_id, text) if event_type == "DEBT_RATINGS" else None,
        "case_stage": case_stage(event_type, out.card.headline, facts, [w.text for w in out.card.why_it_matters]),
        "guidance_recall": guidance_recall(before, event_type, filing.filed_at),
        "memory_context": memory_context(before, event_type, filing.filed_at, filing.news_id),
        "fundamentals": latest_fundamentals(current, footer),
        # the action itself from NSE's feed (corporate_actions.py): ratio, ex and record dates, a dividend's yield
        "corporate_action": (corporate_action_block(dossier, filing.filed_at, text, (priced or {}).get("last_price"))
                             if event_type == "CORPORATE_ACTION" else None),
    }


def refresh(card: dict, dossier: dict, filing: Filing, company: dict | None, footer=(), prices=None,
            buckets=None, printed: str | None = None) -> tuple[dict, list[str]]:
    """The card with its blocks recomputed and signals of types now off removed; and the keys that changed."""
    # a block today's code cannot rebuild (memory no longer holds the filing's figures) keeps its old version: a
    # refresh never takes a table off a card
    made = blocks(card, dossier, filing, company, footer, prices, buckets, printed)
    new = {**card, **{k: v for k, v in made.items() if v or not card.get(k)}}
    # except a call card's table of a quarter the call does not discuss (E11, 22 Oct 2026): that one was never right
    stored = card.get("results") or {}
    if card.get("event_type") == "CONCALL_PRESENTATION" and stored and not made.get("results"):
        from datetime import date as _date

        from .dossier import _discussed
        from .periods import due_date

        end = due_date(stored.get("period"))
        if end and not _discussed(end, _date.fromisoformat(filing.filed_at[:10])):
            new["results"] = None
    new["signals"] = [s for s in card.get("signals") or [] if s.get("type") not in SIGNALS_OFF]
    if card_one_basis():
        # the table and the key numbers read against the card's stated basis, as at card time (F173; off: nothing). Before
        # 27 Oct 2026 the refresh never did this, so a refreshed card could show a table the live run would have removed
        new = {**new, "key_numbers": [dict(k) for k in new.get("key_numbers") or []]}
        if new.get("results"):
            new["results"] = {**new["results"], "lines": [dict(s) for s in new["results"].get("lines") or []]}
        notes = one_basis.apply_card_json(new, dossier)
        grounding = {k: v for k, v in (new.get("grounding") or {}).items() if k != "one_basis"}   # no stale note
        if notes:
            grounding["one_basis"] = notes
        if grounding or "grounding" in new:
            new["grounding"] = grounding
    if card_results_one_line():
        # the table's notes go to the change log and a figure on another basis is labelled, as at card time (F206; off: nothing)
        new = {**new, "key_numbers": [dict(k) for k in new.get("key_numbers") or []]}
        if new.get("results"):
            new["results"] = dict(new["results"])
        if notes := results_one_line.apply_card_json(new):
            new["grounding"] = {**(new.get("grounding") or {}), "one_line": notes}
    if card_adjusted_profit_label() and new.get("results"):
        # a profit figure that is not the table's reported profit is labelled, as at card time (off: nothing)
        new = {**new, "key_numbers": [dict(k) for k in new.get("key_numbers") or []]}
        if notes := results_one_line.profit_label_card_json(new):
            new["grounding"] = {**(new.get("grounding") or {}), "profit_label": notes}
    if card_words_match_figures() and new.get("results"):
        # a comparison word its own figures contradict is dropped or softened, as at card time (off: nothing)
        new = {**new, **{k: list(new.get(k) or []) for k in ("what_happened", "why_it_matters", "notable_changes")}}
        if notes := words_figures.apply_card_json(new, dossier):
            new["grounding"] = {**(new.get("grounding") or {}), "words_figures": notes}
    if card_year_ago_label():
        # a year-ago label one year too old is put right, as at card time (off: nothing)
        new = copy.deepcopy(new)
        if notes := year_ago_label.apply_card_json(new):
            new["grounding"] = {**(new.get("grounding") or {}), "year_ago_label": notes}
    if guided_actual.card_guided_not_actual():
        # a figure only memory's guidance holds, stated as an actual, is dropped, as at card time (off: nothing)
        new = {**new, **{k: list(new.get(k) or []) for k in ("what_happened", "why_it_matters", "notable_changes")}}
        grounding = {k: v for k, v in (new.get("grounding") or {}).items() if k != "guided_not_actual"}
        if notes := guided_actual.apply_card_json(new, dossier):
            grounding["guided_not_actual"] = notes
        if grounding or "grounding" in new:
            new["grounding"] = grounding
    changed = [k for k in (*BLOCKS, "signals") if json.dumps(new.get(k), sort_keys=True) != json.dumps(card.get(k), sort_keys=True)]
    changed += [k for k in ("headline", "takeaway", "key_numbers", "grounding", "what_happened", "why_it_matters", "notable_changes", "timeline_entry")
                if (card_results_one_line() or card_one_basis() or card_adjusted_profit_label() or card_words_match_figures() or card_year_ago_label()
                    or guided_actual.card_guided_not_actual())
                and k not in changed
                and json.dumps(new.get(k), sort_keys=True) != json.dumps(card.get(k), sort_keys=True)]
    hidden = footer_plausible.card_notes(new) if card_footer_plausible() else []
    if (new.get("grounding") or {}).get("footer_hidden", []) != hidden:   # F182: for the owner's Issues page; a stale note goes
        grounding = {k: v for k, v in (new.get("grounding") or {}).items() if k != "footer_hidden"}
        new["grounding"] = {**grounding, **({"footer_hidden": hidden} if hidden else {})}
        changed.append("grounding")
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


def recheck_calls(card: dict, text: str | None) -> bool:
    """A stored call card's takeaways under today's check (call_summary.TAKEAWAY_CHECK_VERSION), by code, no AI. Only
    ever adds: a takeaway the earlier check passed stays passed (its memory citations were checked then, against the
    memory of the day, which is not at hand here); one it refused is passed when today's check, on the filing alone,
    passes it. Returns whether any takeaway changed. Without the filing's text nothing changes and the card is tried
    again on the next refresh."""
    from .call_summary import TAKEAWAY_CHECK_VERSION, check_ai_takeaways
    from .grounding import declared_unit

    items = card.get("call_takeaways") or []
    if (card.get("takeaway_check") or 1) >= TAKEAWAY_CHECK_VERSION or not items or not text:
        return False
    try:
        shell = Card.model_validate({"impact_level": card.get("impact_level") or "LOW", "headline": card.get("headline") or "",
                                     "what_happened": [], "call_takeaways": items})
    except ValidationError:
        return False
    check_ai_takeaways(shell, text, "", {}, declared_unit(text))
    changed = False
    for stored, now in zip(items, shell.call_takeaways):
        if not stored.get("verified") and now.verified:
            stored["verified"], stored["issue"] = True, None
            changed = True
    card["takeaway_check"] = TAKEAWAY_CHECK_VERSION
    return changed


def _call_text(pipeline, row: dict) -> str | None:
    """A call's text for the re-check: the cache when it has it, else the transcript from the exchange (text layer
    only; a scanned transcript stays as it was)."""
    text = filed_text(pipeline, row["news_id"])
    if text or not row.get("pdf_url"):
        return text
    from .extract import Document

    try:
        from .pipeline import ATTACHMENT_MAX_BYTES

        pdf = pipeline._attachment(row["pdf_url"], ATTACHMENT_MAX_BYTES)
        return Document(pdf, max_ocr_pages=0).select_text(10_000_000, []) or None if pdf else None
    except FileCapReached:
        raise   # the run's file cap (F213): run() stops fetching transcripts; the unchecked cards are re-checked next run
    except Exception as exc:  # noqa: BLE001 - one unreachable transcript must not stop the refresh
        log.warning("call %s: transcript not read for the re-check: %s", row["news_id"], exc)
        return None


def run(pipeline, scrips: set[str] | None = None, dry_run: bool = False, page: int = 50,
        diffs: list | None = None) -> dict:
    """Every stored card (or the given companies'), in date order, written back when a block changed. With ``diffs``,
    each changed card's changed blocks, before and after, are added to it (28 Oct 2026: a dry run that would change
    3,214 of 7,895 cards gave only counts, nothing the owner could read). A real run saves each page's stored rows, and the
    memories it rewrites, to R2 backup/card-refresh-<time>/ before writing them (backup.py; restore puts them back)."""
    sink = pipeline.sink
    backup = None if dry_run else RunBackup(sink, "card-refresh")
    after, seen, written, failed = ["", ""], 0, 0, 0
    changed_keys: dict[str, int] = {}
    dossiers: dict[str, dict | None] = {}
    companies: dict[str, dict | None] = {}
    dirty: set[str] = set()   # companies whose memory took call takeaways from their stored cards
    rechecks = 0              # call cards whose takeaways today's check passed more of (recheck_calls)
    capped = False            # the run's file cap (F213) ended the transcript fetches
    while True:
        rows = sink.query("export_cards", [after[0], after[1], page])
        if not rows:
            break
        after = [rows[-1]["filed_at"], rows[-1]["news_id"]]
        batch, stored_rows = [], []
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
                from .call_summary import TAKEAWAY_CHECK_VERSION

                text = None
                if (new.get("takeaway_check") or 1) < TAKEAWAY_CHECK_VERSION and not capped:
                    try:
                        text = _call_text(pipeline, row)
                    except FileCapReached as exc:
                        capped = True
                        log.warning("file cap reached (%s): no more transcripts are fetched; the rest waits for the next run", exc)
                if (new.get("takeaway_check") or 1) < TAKEAWAY_CHECK_VERSION and not capped:
                    rechecked = recheck_calls(new, text)
                    if new.get("takeaway_check") == TAKEAWAY_CHECK_VERSION:
                        changed.append("call_takeaways")
                        if rechecked:
                            rechecks += 1
                # cards written before the takeaways went into memory (2026-10-21): their checked ones, for the
                # company page's quarterly summary (refresh-summaries rebuilds it)
                before = json.dumps(dossier.get("call_points", []), sort_keys=True)
                remember_call_points(dossier, row["news_id"], row["filed_at"], new["call_takeaways"])
                if json.dumps(dossier.get("call_points", []), sort_keys=True) != before:
                    dirty.add(scrip)
            if not changed:
                continue
            for k in changed:
                changed_keys[k] = changed_keys.get(k, 0) + 1
            if diffs is not None:
                keys = sorted(set(changed) - {"impact"})
                stored = json.loads(row["card_json"])   # the card as stored: the call recheck marks takeaways in place
                diffs.append({"news_id": row["news_id"], "scrip_code": scrip, "symbol": row.get("symbol"),
                              "filed_at": row["filed_at"], "changed": sorted(set(changed)),
                              "impact": [row.get("impact_level"), impact],
                              "impact_reasons": (new.get("score") or {}).get("reasons") if "impact" in changed else None,
                              "before": {k: stored.get(k) for k in keys}, "after": {k: new.get(k) for k in keys}})
            out = dict(row)
            out.pop("card_json")
            batch.append({**out, "impact_level": impact, "card": new})
            stored_rows.append(row)
        if batch and not dry_run:
            backup.cards(stored_rows, [card_after_row(b) for b in batch])   # raises when it does not read back: nothing is written
            written += sink.execute("cards_upsert", batch) or 0
        elif batch:
            written += len(batch)
        if len(rows) < page:
            break
    if not dry_run:
        for scrip in dirty:
            backup.dossier(scrip, dossiers[scrip])
        for scrip in dirty:
            sink.put_dossier(scrip, dossiers[scrip])
    return {"cards": seen, "changed": written, "failed": failed, "by_block": changed_keys, "dry_run": dry_run,
            "memories_with_call_points": len(dirty), "call_cards_rechecked": rechecks, "file_cap_reached": capped,
            "backup": backup.summary() if backup else None}
