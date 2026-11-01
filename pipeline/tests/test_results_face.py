"""CARD_RESULTS_FACE_REBUILD (STATUS 17c): a pre-V2 results card's code-written face is rebuilt from memory's file figures, one
profit line; what the model wrote stays. The cards are shaped on release check 41318733817's TATACOMM nse-106596942 and RELIANCE
Q4FY26 (their stored lines)."""

from __future__ import annotations

import copy

from bse_intel import card_refresh
from bse_intel import results_face as F
from bse_intel.models import Filing

FILED = "2026-04-22T16:02:56+05:30"


def _e(metric, period, value, by="file", news="nse-106596942"):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "as_of": FILED,
            "sources": [{"news_id": news, "as_of": FILED, "value": value, "unit": "INR_CR", "basis": "CONSOLIDATED",
                         "lab": {"by": by, "doc": "results", "basis": "CONSOLIDATED"}}]}


def _memory(pat=259.27, owners=263.24, owners_ago=1040.3, by="file"):
    rows = [("revenue", "Q4FY26", 6554.15), ("revenue", "Q4FY25", 5990.0), ("revenue", "Q3FY26", 6400.0),
            ("pat", "Q4FY26", pat), ("pat", "Q4FY25", 1040.0), ("pat_owners", "Q4FY26", owners),
            ("pat_owners", "Q4FY25", owners_ago), ("ebitda", "Q4FY26", 1200.0), ("ebitda", "Q4FY25", 1150.0),
            ("other_income", "Q4FY26", 42.58), ("other_income", "Q4FY25", 700.0), ("depreciation", "Q4FY26", 700.0),
            ("depreciation", "Q4FY25", 650.0), ("finance_cost", "Q4FY26", 150.0), ("finance_cost", "Q4FY25", 140.0),
            ("tax_expense", "Q4FY26", 183.27), ("tax_expense", "Q4FY25", 60.0)]
    return {"financial_metrics": [_e(m, p, v, by) for m, p, v in rows]}


def _card(owners_key="₹263.24 Cr"):
    return {"event_type": "RESULTS", "impact_level": "MEDIUM", "basis": "CONSOLIDATED", "results": {"period": "Q4FY26"},
            "headline": "Tata Communications Q4FY26: net profit to shareholders ₹263.24 Cr (-74.7% YoY)",
            "takeaway": "Q4FY26 net profit of ₹259.27 Cr against net profit of ₹1,040 Cr a year earlier; the largest move was "
                        "other income of ₹42.58 Cr against ₹700 Cr a year earlier.",
            "what_happened": [{"text": "Net profit Q4FY26: ₹259.27 Cr.", "quote": "- pat Q4FY26: 259.27 Cr"},
                              {"text": "The board recommended a dividend of ₹25 a share.", "quote": "dividend of Rs 25 per share"}],
            "key_numbers": [{"label": "Revenue from operations", "value": "₹6,554.15 Cr", "quote": "- revenue Q4FY26: 6554.15 Cr"},
                            {"label": "Net profit", "value": "₹259.27 Cr", "quote": "- pat Q4FY26: 259.27 Cr"},
                            {"label": "Net profit to shareholders", "value": owners_key, "quote": "- pat_owners Q4FY26: 263.24 Cr"},
                            {"label": "Order book", "value": "₹10,000 Cr", "quote": "order book stood at 10,000 crore"}]}


def _on(monkeypatch, on=True):
    monkeypatch.setenv("CARD_RESULTS_FACE_REBUILD", "1" if on else "0")


def _profits(card):
    return [k["label"] for k in card["key_numbers"] if k["label"].startswith("Net ")]


def test_off_changes_nothing(monkeypatch):
    _on(monkeypatch, False)
    card = _card()
    assert F.apply_card_json(card, _memory(), FILED, "Tata Communications Limited") == [] and card == _card()


def test_tatacomm_two_profit_lines_become_one(monkeypatch):
    _on(monkeypatch)
    card = _card()
    notes = F.apply_card_json(card, _memory(), FILED, "Tata Communications Limited")
    assert notes and _profits(card) == ["Net profit to shareholders"]
    assert card["takeaway"].startswith("Q4FY26 net profit to shareholders of ₹263.24 Cr")   # one profit with the headline's
    assert card["headline"] == _card()["headline"]
    # the model's own key and facts stay, the code fact too (only the headline, keys and takeaway are rebuilt)
    assert card["key_numbers"][-1]["label"] == "Order book" and card["what_happened"] == _card()["what_happened"]


def test_reliance_key_that_disagrees_with_the_headline_is_rebuilt(monkeypatch):
    # RELIANCE Q4FY26 as stored: the key "to shareholders" shows the whole profit (20,589), the headline the owners' (16,971)
    _on(monkeypatch)
    card = _card()
    card["headline"] = "Reliance Industries Q4FY26: net profit to shareholders ₹16,971 Cr (-12.6% YoY)"
    card["key_numbers"][1:3] = [{"label": "Net profit", "value": "₹20,589.00 Cr", "quote": "- pat Q4FY26: 20589 Cr"},
                                {"label": "Net profit to shareholders", "value": "₹20,589.00 Cr", "quote": "- pat_owners Q4FY26: 20589 Cr"}]
    memory = _memory(pat=20589.0, owners=16971.0, owners_ago=19407.0)
    assert F.apply_card_json(card, memory, FILED, "Reliance Industries Limited")
    keys = {k["label"]: k["value"] for k in card["key_numbers"]}
    assert keys["Net profit to shareholders"] == "₹16,971 Cr" and "Net profit" not in keys


def test_a_v2_face_a_model_headline_and_no_memory_are_left(monkeypatch):
    _on(monkeypatch)
    # a V2 card: one profit key, filed after V2 went on
    v2 = _card()
    del v2["key_numbers"][1]
    before = copy.deepcopy(v2)
    assert F.apply_card_json(v2, _memory(), "2026-10-31T10:00:00+05:30", "Tata Communications Limited") == [] and v2 == before
    # a headline and takeaway the model wrote stay, the code keys are still rebuilt
    card = _card()
    card["headline"] = "Tata Communications profit falls 75% as other income dries up"
    card["takeaway"] = "Profit fell sharply on lower treasury income."
    assert F.apply_card_json(card, _memory(), FILED, "Tata Communications Limited")
    assert card["headline"].startswith("Tata Communications profit falls") and card["takeaway"].startswith("Profit fell")
    assert _profits(card) == ["Net profit to shareholders"]
    # memory without the quarter's file figures (a model's reading only): nothing
    card = _card()
    assert F.apply_card_json(card, _memory(by="ai"), FILED, "Tata Communications Limited") == [] and card == _card()
    assert F.apply_card_json(card, None, FILED, "Tata Communications Limited") == []


def test_predates_v2_by_its_profit_keys_or_its_filing_time():
    assert F.predates_v2(_card(), "2026-10-31T10:00:00+05:30")             # two profit keys, whenever filed
    one = _card()
    del one["key_numbers"][1]
    assert F.predates_v2(one, "2026-10-30T00:30:00+05:30") and not F.predates_v2(one, "2026-10-30T00:50:00+05:30")


def test_the_refresh_rebuilds_the_face_with_the_switch_on(monkeypatch):
    filing = Filing(news_id="nse-106596942", scrip_code="500483", company_name="Tata Communications Limited", headline="h",
                    subject="", filed_at=FILED, filing_date=FILED[:10], event_type="RESULTS")
    _on(monkeypatch, False)
    off, _ = card_refresh.refresh(_card(), _memory(), filing, None)
    assert len(_profits(off)) == 2
    _on(monkeypatch)
    on, changed = card_refresh.refresh(_card(), _memory(), filing, None)
    assert _profits(on) == ["Net profit to shareholders"] and "key_numbers" in changed and on["grounding"]["results_face"]
