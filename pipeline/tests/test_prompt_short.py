"""The short pass-2 prompt (deep audit B1): each kind of filing gets the shared rules, the reviewers' mistakes and only
the fields it uses, at about a third of the long prompt's length; a share of live filings gets it, the same filing
always the same one, and the card records which wrote it."""

import json
from dataclasses import replace

from bse_intel.models import Filing
from bse_intel.pipeline import prompt_variant
from bse_intel.prompts.engine import PromptEngine, short_schema


def _filing():
    return Filing(news_id="n1", scrip_code="1", company_name="Prism Ltd", headline="h", subject="",
                  filed_at="2026-10-21T10:00:00+05:30", filing_date="2026-10-21")


def _shape(system: str) -> dict:
    return json.loads(system[system.rindex("exactly this shape:") + len("exactly this shape:"):])


def test_each_kind_of_filing_gets_only_its_fields_and_their_rules(settings):
    engine = PromptEngine(settings)
    rating, _ = engine.pass2(_filing(), "DEBT_RATINGS", "Cement", None, "text", variant="short")
    order, _ = engine.pass2(_filing(), "ORDER_WIN", "Cement", None, "text", variant="short")
    call, _ = engine.pass2(_filing(), "CONCALL_PRESENTATION", "Cement", None, "text", variant="short")
    long, _ = engine.pass2(_filing(), "DEBT_RATINGS", "Cement", None, "text")
    assert len(rating) < len(long) / 2
    assert "deal_value" not in _shape(rating)["card"] and "call_read" not in _shape(rating)["card"]
    assert "- deal_value:" not in rating and "Mistakes our reviewers found" in rating
    assert "deal_value" in _shape(order)["card"] and "- deal_value:" in order and "- quantified_impact:" in order
    assert {"call_read", "call_takeaways", "notable_changes"} <= set(_shape(call)["card"]) and "- call_takeaways:" in call
    assert "dossier_delta" in _shape(rating) and "$" not in rating   # every placeholder filled


def test_short_schema_keeps_the_shared_card_fields():
    card = short_schema("LITIGATION_REGULATORY")["card"]
    assert {"headline", "tone", "what_happened", "why_it_matters", "key_numbers", "track_next"} <= set(card)
    assert not {"deal_value", "quantified_impact", "notable_changes", "call_read"} & set(card)


def test_a_share_of_live_filings_gets_the_short_prompt_and_a_filing_keeps_its_variant():
    ids = [f"nse-{i}" for i in range(1000)]
    short = [i for i in ids if prompt_variant(i, False, 0.3) == "short"]
    assert 250 < len(short) < 350
    assert all(prompt_variant(i, False, 0.3) == "short" for i in short)   # stable across runs
    assert all(prompt_variant(i, True, 0.3) == "long" for i in short)     # never the backfill
    assert all(prompt_variant(i, False, 0.0) == "long" for i in ids)


def test_the_card_records_which_prompt_wrote_it(settings):
    from tests.test_pipeline import PASS2, RESULT_TEXT, _filing as make_filing, _pdf, build
    from bse_intel.timeutil import now_ist

    filing = make_filing("n-short", "Unaudited Financial Results", now_ist(), "Result")
    pipeline, sink, _ = build(replace(settings, prompt_short_share=1.0), [filing], {filing.pdf_url: _pdf(RESULT_TEXT)},
                              {"glm-4.5-flash": [json.dumps(PASS2)]}, env={"ZAI_API_KEY": "z"})
    pipeline.run("live", time_budget_s=60)
    rows = sink._db.execute("select card_json from cards").fetchall()
    assert rows and json.loads(rows[0][0])["grounding"]["prompt_variant"] == "short"
