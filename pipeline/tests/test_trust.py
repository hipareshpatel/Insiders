"""Memory stores only trusted figures (audit round 2): confirmed at the filing's declared unit and within ten times
of the company's known scale; anything else stays on its card. Each test is a round-2 card."""
from __future__ import annotations

from bse_intel import trust
from bse_intel.models import Pass2Output


def _out(**delta) -> Pass2Output:
    card = {"impact_level": "MODERATE", "headline": "A company reports something", "what_happened": ["x"]}
    deal = delta.pop("deal", None)
    if deal:
        card["deal_value"] = deal
    return Pass2Output.model_validate({"is_material": True, "event_type": "ORDER_WIN", "timeline_entry": "x",
                                       "card": card, "dossier_delta": delta})


def test_magellanic_an_order_in_million_never_enters_memory_as_crore():
    """99f1c20d / 531d99a4: the GAIL LOA said Rs 127.62 million (₹12.76 Cr); memory kept ₹127.62 Cr and ORDER_FLOW
    counted it on three later cards. The card keeps its reading; memory does not."""
    filing = "Letter of Award from GAIL (India) Limited for a total value of Rs. 127.62 million (excluding GST)"
    out = _out(deal={"kind": "ORDER", "amount_cr": 127.62})
    remembered, notes = trust.for_memory(out, filing, {"market_cap_cr": 1393}, {})
    assert out.card.deal_value.amount_cr == 127.62          # the card is unchanged
    assert remembered.card.deal_value.amount_cr is None and notes == ["deal amount 127.62"]
    ok, _ = trust.for_memory(_out(deal={"kind": "ORDER", "amount_cr": 12.76}), filing, {"market_cap_cr": 1393}, {})
    assert ok.card.deal_value.amount_cr == 12.76


def test_bandhan_a_net_worth_100x_too_small_is_refused():
    """Round-2 reviewer_01: memory's net worth ₹261.7 Cr for Bandhan Bank ("contingent liabilities 110x net worth");
    the balance sheet, in ₹ thousand, gives about ₹25,575 Cr."""
    filing = "Balance sheet as at 30 June 2026 (Rs. in '000) Capital and reserves 25,57,50,120"
    dossier = {"balance_sheet": [{"net_worth_cr": 24_900.0, "source_news_id": "xbrl:res:541153:Q4FY26"}]}
    bad, notes = trust.for_memory(_out(balance_sheet={"net_worth_cr": 261.7}), filing, {"market_cap_cr": 27_390}, dossier)
    assert bad.dossier_delta.balance_sheet.net_worth_cr is None and notes
    good, _ = trust.for_memory(_out(balance_sheet={"net_worth_cr": 25_575.01}), filing, {"market_cap_cr": 27_390}, dossier)
    assert good.dossier_delta.balance_sheet.net_worth_cr == 25_575.01


def test_sbi_life_a_ratio_the_filing_does_not_print_is_not_remembered():
    """Round-2 reviewer_02: memory's expense ratio for SBI Life was 100x off, and a signal said it rose 1196 bps.
    A ratio enters memory only as the filing prints it; a change the model worked out is dropped from the figure."""
    filing = "Operating expense ratio 12.05% 9.05%"
    out = _out(financial_metrics=[
        {"metric": "expense_ratio", "period": "Q1FY27", "value": 12.05, "unit": "PCT", "yoy_pct": 33.1},
        {"metric": "expense_ratio", "period": "Q4FY26", "value": 905.0, "unit": "PCT"}])
    remembered, _ = trust.for_memory(out, filing, {"market_cap_cr": 1_67_168}, {})
    kept = [(m.period, m.value, m.yoy_pct) for m in remembered.dossier_delta.financial_metrics]
    assert kept == [("Q1FY27", 12.05, None)]


def test_a_figure_far_outside_the_companys_scale_is_refused_even_if_printed():
    """A revenue printed in the filing but ten times the company's XBRL history is a unit read wrongly."""
    filing = "Revenue from operations 6,812.30 (Rs in lakhs)"
    dossier = {"financial_metrics": [{"metric": "revenue", "period": "Q4FY26", "value": 70.1,
                                      "value_news_id": "xbrl:res:1:Q4FY26"}]}
    out = _out(financial_metrics=[{"metric": "revenue", "period": "Q1FY27", "value": 6812.30, "unit": "INR_CR"},
                                  {"metric": "revenue", "period": "Q1FY26", "value": 68.12, "unit": "INR_CR"}])
    remembered, _ = trust.for_memory(out, filing, {"market_cap_cr": 333}, dossier)
    assert [m.value for m in remembered.dossier_delta.financial_metrics] == [68.12]
