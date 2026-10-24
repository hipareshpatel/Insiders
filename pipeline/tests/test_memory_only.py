"""Older backfill filings go into memory only, with no card (owner, 24 Oct 2026; settings.backfill_cards_from)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from test_pipeline import _filing, _pdf, build, rows

from bse_intel.models import MemoryOutput
from bse_intel.prompts.engine import MEMORY_SCHEMA, PromptEngine

IST = timezone(timedelta(hours=5, minutes=30))
OLD = datetime(2026, 5, 4, 11, 0, tzinfo=IST)          # before the cut: memory only
ORDER_TEXT = ("Demo Cement Ltd has received a Letter of Award from National Highways Authority of India for a road "
              "project worth Rs 120 crore, to be executed by 31 March 2028.")
MEMORY = {"is_material": True, "event_type": "ORDER_WIN", "timeline_entry": "Won a ₹120 Cr NHAI road order (LoA)",
          "deal_value": {"kind": "ORDER", "amount_cr": 120, "counterparty": "National Highways Authority of India",
                         "stage": "LOA", "execution_by": "31 March 2028"},
          "track_next": {"milestones": [{"what": "Project completion", "when": "31 March 2028", "date": "2028-03-31"}]},
          "dossier_delta": {"operating_notes": ["Road EPC order book includes a ₹120 Cr NHAI project"],
                            "upcoming_events": [{"event_type": "OTHER", "date": "2026-06-01", "description": "Appointed date"}]}}


def test_the_memory_prompt_asks_only_for_memory(settings):
    engine = PromptEngine(settings)
    f = _filing("n-m", "Order win", OLD)
    system, user = engine.memory(f, "ORDER_WIN", "Construction", None, ORDER_TEXT)
    card_system, _ = engine.pass2(f, "ORDER_WIN", "Construction", None, ORDER_TEXT)
    assert "dossier_delta" in system and '"deal_value"' in system and "track_next" in system
    assert '"headline"' not in system and "why_it_matters" not in system and "Ground rules" in system
    assert len(system) < len(card_system) * 0.6 and ORDER_TEXT in user
    assert set(MEMORY_SCHEMA) == {"is_material", "event_type", "timeline_entry", "deal_value", "track_next", "dossier_delta"}


def test_an_older_backfill_filing_goes_into_memory_with_no_card(settings):
    f = _filing("n-old", "Receipt of Letter of Award", OLD, "Company Update")
    pipeline, sink, fake = build(replace(settings, backfill_cards_from="2026-08-01"), [f], {f.pdf_url: _pdf(ORDER_TEXT)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(MEMORY)]}, env={"OPENROUTER_API_KEY": "o"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "ORDER_WIN"}), bulk=True)
    assert outcome.card is None and outcome.update["status"] == "ANALYZED"
    assert outcome.update["reason"].startswith("memory only")
    (call,) = fake.calls
    assert "Reply with only one JSON object" in call["messages"][0]["content"]
    assert '"headline"' not in call["messages"][0]["content"]
    memory = sink.get_dossier("999001")
    (deal,) = memory["deals"]
    assert deal["amount_cr"] == 120 and deal["stage"] == "LOA"
    assert any("NHAI" in t.get("summary", "") for t in memory["timeline"])
    assert pipeline.stats.memory_only == 1 and pipeline.stats.analyzed == 0
    assert [c["event_date"] for c in outcome.catalysts] == ["2026-06-01"]


def test_live_filings_recent_ones_and_filings_with_a_card_still_get_a_card(settings):
    cut = replace(settings, backfill_cards_from="2026-08-01")
    f = _filing("n-old", "Receipt of Letter of Award", OLD, "Company Update")
    pipeline, sink, _ = build(cut, [f], {}, {})
    assert pipeline._memory_only(f, bulk=True)
    assert not pipeline._memory_only(f, bulk=False)                               # live: always a card
    recent = _filing("n-new", "Receipt of Letter of Award", datetime(2026, 9, 1, 11, 0, tzinfo=IST))
    assert not pipeline._memory_only(recent, bulk=True)                           # after the cut: a card
    sink.execute("cards_upsert", [{"news_id": "n-old", "scrip_code": "999001", "company_name": "Demo", "filing_date": "2026-05-04",
                                   "filed_at": OLD.isoformat(), "event_category": "ORDER_WIN", "impact_level": "LOW", "headline": "Demo wins ₹120 Cr order", "created_at": "x",
                                   "card": {"headline": "Demo wins ₹120 Cr order"}}])
    assert not pipeline._memory_only(f, bulk=True)                                # it has a card: it keeps one
    assert not build(replace(settings, backfill_cards_from=None), [f], {}, {})[0]._memory_only(f, bulk=True)


def test_a_memory_reading_not_material_and_its_stand_in_card():
    out = MemoryOutput.model_validate(MEMORY)
    assert out.card is not None and out.card.deal_value.amount_cr == 120 and out.card.track_next.milestones
    assert MemoryOutput.model_validate({"is_material": False, "event_type": "OTHER", "reason": "routine"}).card is None
