"""The model's call takeaways (owner, 2026-10-20: "connect facts from previous calls, results, other announcements"):
the schema, and the code checks that decide which ones the card's face shows. No model is called."""

import json

from bse_intel.call_summary import check_ai_takeaways
from bse_intel.models import MAX_CALL_TAKEAWAYS, Card
from bse_intel.prompts.engine import pass2_schema

TEXT = """Earnings conference call, Q2FY27. Good morning everyone and thank you for joining us.
For FY27 we now expect volume growth of 12-14%, supported by the new capacity in the East.
The 2 MTPA grinding unit at Jajpur will be commissioned in Q1FY28 at a capex of Rs 650 crore.
EBITDA per tonne was Rs 1,040 in the quarter as fuel costs eased.
Net debt stood at Rs 1,250 crore at the end of September."""

VIEW = {
    "guidance": [
        {"id": "g_vol", "statement": "Volume growth of 10-12% in FY27", "target": "10-12%", "due": "FY27",
         "source_type": "CONCALL", "given_on": "2026-08-14T19:00:00+05:30", "status": "OPEN"},
        {"id": "g_jaj", "statement": "Commission 2 MTPA grinding unit at Jajpur", "due": "Q4FY27",
         "given_on": "2026-08-14T19:00:00+05:30", "status": "OPEN"},
    ],
    "recent_timeline": [{"id": "t_res", "date": "2026-10-10T16:00:00+05:30", "event_type": "RESULTS",
                         "summary": "Q2FY27 EBITDA per tonne ₹980"}],
    "watchlist": [], "deals": [],
}


def _card(*items):
    return Card.model_validate({"impact_level": "MODERATE", "headline": "Cement X raises FY27 volume guidance to 12-14%",
                                "what_happened": [{"text": "Volume guidance raised", "quote": "volume growth of 12-14%"}],
                                "call_takeaways": list(items)})


def _item(text, quote, refs=(), versus=None, category="Guidance"):
    return {"category": category, "text": text, "quote": quote, "memory_refs": list(refs), "versus_prior": versus}


def test_schema_asks_for_takeaways_only_on_calls():
    assert "call_takeaways" in pass2_schema("CONCALL_PRESENTATION")["card"]
    assert "call_takeaways" not in pass2_schema("RESULTS")["card"]
    json.dumps(pass2_schema("CONCALL_PRESENTATION"))


def test_model_reply_is_normalised_capped_and_never_self_verified():
    items = [{**_item(f"Takeaway number {i} with figure {i}", "q"), "verified": True} for i in range(20)]
    items.append("not a dict")
    items.append({"category": "capex plans", "text": "short"})   # too short: dropped
    card = _card(*items, {"category": "Capex plans", "text": "A long enough capex takeaway"})
    assert len(card.call_takeaways) == MAX_CALL_TAKEAWAYS
    assert not any(t.verified for t in card.call_takeaways)
    assert _card({"category": "capex plans", "text": "New line at Jajpur"}).call_takeaways[0].category == "Capex & capacity"
    assert _card({"category": "RISK", "text": "Pricing pressure in the East"}).call_takeaways[0].category == "Risks"
    assert _card({"category": "weather", "text": "Monsoon was normal this year"}).call_takeaways[0].category == "Other"
    assert Card.model_validate({"impact_level": "LOW", "headline": "Cement X files call transcript",
                                "what_happened": [{"text": "x"}]}).call_takeaways == []


def test_quoted_takeaway_compared_with_memory_is_verified():
    card = _card(_item("FY27 volume growth guided at 12-14%", "For FY27 we now expect volume growth of 12-14%",
                       ["g_vol"], "raised from 10-12% in the Q1FY27 call"))
    assert check_ai_takeaways(card, TEXT, "", VIEW) == []
    assert card.call_takeaways[0].verified and card.call_takeaways[0].issue is None


def test_a_figure_from_a_cited_memory_item_passes():
    card = _card(_item("EBITDA per tonne ₹1,040, up from ₹980 in the results", "EBITDA per tonne was Rs 1,040 in the quarter",
                       ["t_res"], "₹980 in Q2FY27 results", "Margins & costs"))
    check_ai_takeaways(card, TEXT, "", VIEW)
    assert card.call_takeaways[0].verified


def test_an_invented_prior_figure_is_rejected():
    card = _card(_item("FY27 volume growth guided at 12-14%", "For FY27 we now expect volume growth of 12-14%",
                       ["g_vol"], "raised from 8-10% in the Q1FY27 call"))
    notes = check_ai_takeaways(card, TEXT, "", VIEW)
    assert not card.call_takeaways[0].verified and "8" in card.call_takeaways[0].issue and notes
    # a period memory does not hold
    card = _card(_item("FY27 volume growth guided at 12-14%", "For FY27 we now expect volume growth of 12-14%",
                       ["g_vol"], "raised from 10-12% in the Q4FY26 call"))
    check_ai_takeaways(card, TEXT, "", VIEW)
    assert "Q4FY26" in card.call_takeaways[0].issue
    # a comparison with no memory cited, or with an id the model was not shown
    card = _card(_item("FY27 volume growth guided at 12-14%", "For FY27 we now expect volume growth of 12-14%",
                       ["g_made_up"], "raised from 10-12%"))
    check_ai_takeaways(card, TEXT, "", VIEW)
    assert not card.call_takeaways[0].verified and card.call_takeaways[0].memory_refs == []


def test_failures_quote_figure_boilerplate():
    card = _card(
        _item("FY27 volume growth guided at 12-14%", "We expect volumes to grow strongly next year"),      # not in filing
        _item("Jajpur unit capex ₹700 Cr, commissioning Q1FY28",
              "The 2 MTPA grinding unit at Jajpur will be commissioned in Q1FY28 at a capex of Rs 650 crore",
              category="Capex & capacity"),                                                            # 700 invented
        _item("Thank you for joining us on the call today", "Good morning everyone and thank you for joining us."),
        _item("Net debt ₹1,250 Cr at end-September", None, category="Balance sheet & funding"),         # no quote
        _item("Net debt ₹1,250 Cr at end-September", "Net debt stood at Rs 1,250 crore at the end of September",
              category="Balance sheet & funding"),
    )
    notes = check_ai_takeaways(card, TEXT, "", VIEW)
    got = [(t.verified, t.issue) for t in card.call_takeaways]
    assert got[0] == (False, "quote not in the filing")
    assert got[1][0] is False and "700" in got[1][1]
    assert got[2][0] is False and "greeting" in got[2][1]
    assert got[3] == (False, "no quote")
    assert got[4] == (True, None)
    assert len(notes) == 4


def test_an_earlier_figure_the_quote_itself_states_needs_no_memory():
    """Indian Bank's call (live, 2026-10-21): "I had guided for deposit growth of 9-11%, and I am revising that to
    11-12%" carries its own earlier figure; it was failed for citing no memory."""
    card = _card(_item("Deposit growth guidance revised upward to 11-12% from 9-11%",
                       "I had guided for deposit growth of 9-11%, and I am revising that to 11-12%.", [], "raised from 9-11%"))
    text = "On guidance, I had guided for deposit growth of 9-11%, and I am revising that to 11-12%."
    check_ai_takeaways(card, text, view={})
    assert card.call_takeaways[0].verified
    # an earlier figure the quote does not state still needs memory
    other = _card(_item("Deposit growth guidance revised upward to 11-12%", "I am revising that to 11-12%.", [], "raised from 9-11%"))
    check_ai_takeaways(other, "I am revising that to 11-12%.", view={})
    assert not other.call_takeaways[0].verified
    # nor does a "reiterated" with no figure: an earlier statement only memory can show
    said = _card(_item("Volume growth guidance of 15% maintained", "We maintain our guidance of 15% volume growth.", [], "reiterated"))
    check_ai_takeaways(said, "We maintain our guidance of 15% volume growth.", view={})
    assert not said.call_takeaways[0].verified


def test_verified_takeaways_feed_the_quarterly_summary():
    from bse_intel.call_summary import remember_call_points, summarize_calls

    card = _card(_item("Deposit growth guidance revised upward to 11-12% from 9-11%",
                       "I had guided for deposit growth of 9-11%, and I am revising that to 11-12%.", [], "raised from 9-11%"),
                 _item("Credit cost guided below 0.5% for FY27", "not in the filing", []))
    text = "I had guided for deposit growth of 9-11%, and I am revising that to 11-12%."
    check_ai_takeaways(card, text, view={})
    d = {"timeline": [{"news_id": "c1", "date": "2026-10-21T20:18:00+05:30", "event_type": "CONCALL_PRESENTATION",
                       "summary": "Q2FY27 earnings call transcript"}], "guidance": []}
    remember_call_points(d, "c1", "2026-10-21T20:18:00+05:30", card.call_takeaways)
    assert len(d["call_points"]) == 1                     # only the verified one is kept
    points = [p for c in summarize_calls(d)[0]["categories"] for p in c["points"]]
    assert points[0]["text"].startswith("Deposit growth") and points[0]["versus"] == "raised from 9-11%"


def test_a_figure_from_the_same_answer_or_one_subtraction_is_the_filings_own():
    """22 Oct 2026, Tech Mahindra's call: "within 20 bps of the 15% target" (15% - 14.8%) and "LTM TCV US$4,270
    million" (said two sentences after the quote) were failed as figures not in the quote. A small figure from
    elsewhere in the answer, or one too far away, still fails."""
    text = ("Our EBIT margin for the quarter was 14.8%. We reiterate that we remain on track to achieve our full-year "
            "FY27 EBIT margin target of 15%. Our total deal wins for the quarter stand at US$1,023 million. "
            "On an LTM basis, deal wins are US$4,270 million, up 34.8% year-on-year. We added 7 new logos.")
    margin = _card(_item("EBIT margin 14.8%, within 20 bps of the 15% FY27 target",
                         "Our EBIT margin for the quarter was 14.8%. We reiterate that we remain on track to achieve our "
                         "full-year FY27 EBIT margin target of 15%."))
    check_ai_takeaways(margin, text, view={})
    assert margin.call_takeaways[0].verified, margin.call_takeaways[0].issue
    deals = _card(_item("Q2 deal wins of US$1,023 million; LTM TCV US$4,270 million",
                        "Our total deal wins for the quarter stand at US$1,023 million.", category="Demand & orders"))
    check_ai_takeaways(deals, text, view={})
    assert deals.call_takeaways[0].verified, deals.call_takeaways[0].issue
    small = _card(_item("Deal wins US$1,023 million with 9 new logos",
                        "Our total deal wins for the quarter stand at US$1,023 million.", category="Demand & orders"))
    check_ai_takeaways(small, text, view={})
    assert not small.call_takeaways[0].verified                        # 9 is not said, and small figures need the quote
    far = text + " " + "Filler sentence about the weather. " * 120 + "Our attrition was 11.9%."
    away = _card(_item("Q2 deal wins of US$1,023 million; attrition 11.9%",
                       "Our total deal wins for the quarter stand at US$1,023 million.", category="Demand & orders"))
    check_ai_takeaways(away, far, view={})
    assert not away.call_takeaways[0].verified                         # said, but in another part of the call


def test_an_earlier_figure_in_the_quote_may_name_the_quarter_the_quote_names():
    text = "In Q1FY27 I had guided for deposit growth of 9-11%, and I am revising that to 11-12%."
    card = _card(_item("Deposit growth guidance revised to 11-12%", text, [], "from 9-11% in Q1FY27"))
    check_ai_takeaways(card, text, view={})
    assert card.call_takeaways[0].verified, card.call_takeaways[0].issue
    other = _card(_item("Deposit growth guidance revised to 11-12%", text, [], "from 9-11% in Q4FY26"))
    check_ai_takeaways(other, text, view={})
    assert not other.call_takeaways[0].verified                        # a quarter the filing does not name
