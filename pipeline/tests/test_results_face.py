"""CARD_RESULTS_FACE_REBUILD (STATUS 17c): a pre-V2 results card's code-written face is rebuilt from memory's file figures, one
profit line; what the model wrote stays. The cards are shaped on release check 41318733817's TATACOMM nse-106596942 and RELIANCE
Q4FY26 (their stored lines)."""

from __future__ import annotations

import copy

from bse_intel import card_refresh
from bse_intel import results_face as F
from bse_intel.models import Filing

FILED = "2026-04-22T16:02:56+05:30"


def _e(metric, period, value, by="file", news="nse-106596942", basis="CONSOLIDATED"):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "as_of": FILED,
            "sources": [{"news_id": news, "as_of": FILED, "value": value, "unit": "INR_CR", "basis": basis,
                         "lab": {"by": by, "doc": "results", "basis": basis}}]}


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


def test_a_v2_face_and_no_memory_are_left(monkeypatch):
    _on(monkeypatch)
    # a V2 card: one profit key, filed after V2 went on
    v2 = _card()
    del v2["key_numbers"][1]
    before = copy.deepcopy(v2)
    assert F.apply_card_json(v2, _memory(), "2026-10-31T10:00:00+05:30", "Tata Communications Limited") == [] and v2 == before
    # memory without the quarter's file figures (a model's reading only): nothing
    card = _card()
    assert F.apply_card_json(card, _memory(by="ai"), FILED, "Tata Communications Limited") == [] and card == _card()
    assert F.apply_card_json(card, None, FILED, "Tata Communications Limited") == []


# --- the lead's four probes on #358 -------------------------------------------------------------------------------------------

def test_probe1_a_model_headline_or_takeaway_in_codes_shape_stays(monkeypatch):
    _on(monkeypatch)
    card = _card()
    card["headline"] = "Tata Communications Q4FY26: profit collapses as treasury gains vanish"
    card["takeaway"] = "Q4FY26: profit fell on weak treasury income."
    assert F.apply_card_json(card, _memory(), FILED, "Tata Communications Limited")
    assert card["headline"] == "Tata Communications Q4FY26: profit collapses as treasury gains vanish"
    assert card["takeaway"] == "Q4FY26: profit fell on weak treasury income."
    assert _profits(card) == ["Net profit to shareholders"]   # the old profit keys are still put right


def test_probe2_unknown_basis_is_left_and_a_known_one_never_reads_the_other(monkeypatch):
    _on(monkeypatch)
    both = _memory()
    both["financial_metrics"] += [_e(m, p, v / 2, basis="STANDALONE") for m, p, v in
                                  [(x["metric"], x["period"], x["value"]) for x in _memory()["financial_metrics"]]]
    card = _card()
    del card["basis"]
    assert F.apply_card_json(card, both, FILED, "Tata Communications Limited") == []
    card = _card()
    F.apply_card_json(card, both, FILED, "Tata Communications Limited")
    assert {k["label"]: k["value"] for k in card["key_numbers"]}["Net profit to shareholders"] == "₹263.24 Cr"   # not 131.62
    # an unlabelled row counts only for a period memory labels nowhere
    t = F.tagged_from_memory({"financial_metrics": both["financial_metrics"] + [
        {"metric": "pat", "period": "Q4FY26", "value": 1.0, "unit": "INR_CR", "as_of": FILED,
         "sources": [{"news_id": "xbrl:res:500483:Q4FY26", "value": 1.0}]}]}, "Q4FY26", "CONSOLIDATED")
    assert {(m.metric, m.period): m.value for m in t.metrics}[("pat", "Q4FY26")] == 259.27


def test_probe3_only_the_old_profit_keys_and_eps_change_in_place(monkeypatch):
    _on(monkeypatch)
    card = _card()
    card["key_numbers"] = [{"label": "Depreciation", "value": "₹700 Cr", "quote": "- depreciation Q4FY26: 700 Cr"},
                           {"label": "Net profit", "value": "₹259.27 Cr", "quote": "- pat Q4FY26: 259.27 Cr"},
                           {"label": "EPS", "value": "₹9.10", "quote": "- eps Q4FY26: 9.1 INR"},
                           {"label": "Net profit to shareholders", "value": "₹263.24 Cr", "quote": "- pat_owners Q4FY26: 263.24 Cr"},
                           {"label": "Total income", "value": "₹6,600 Cr", "quote": "- total_income Q4FY26: 6600 Cr"},
                           {"label": "Revenue from operations", "value": "₹6,554.15 Cr", "quote": "- revenue Q4FY26: 6554.15 Cr"},
                           {"label": "Order book", "value": "₹10,000 Cr", "quote": "order book stood at 10,000 crore"}]
    assert F.apply_card_json(card, _memory(), FILED, "Tata Communications Limited")
    assert [k["label"] for k in card["key_numbers"]] == ["Depreciation", "Net profit to shareholders", "Total income",
                                                         "Revenue from operations", "Order book"]   # nothing added or cut
    assert card["key_numbers"][1]["value"] == "₹263.24 Cr"


def test_probe3b_an_eps_key_alone_is_dropped_for_the_profit_line(monkeypatch):
    # owner rule 26 Oct 2026: no EPS on cards; a pre-V2 card with one profit key and an EPS key (filed before V2)
    _on(monkeypatch)
    card = _card()
    card["key_numbers"] = [card["key_numbers"][2], {"label": "EPS", "value": "₹9.10", "quote": "- eps Q4FY26: 9.1 INR"},
                           card["key_numbers"][3]]
    assert F.apply_card_json(card, _memory(), FILED, "Tata Communications Limited")
    assert [k["label"] for k in card["key_numbers"]] == ["Net profit to shareholders", "Order book"]


def test_probe4_without_the_year_ago_figures_nothing_is_replaced(monkeypatch):
    _on(monkeypatch)
    only_now = {"financial_metrics": [m for m in _memory()["financial_metrics"] if m["period"] == "Q4FY26"]}
    card = _card()
    assert F.apply_card_json(card, only_now, FILED, "Tata Communications Limited") == [] and card == _card()


def test_a_bad_filing_time_is_judged_by_the_profit_keys_only(monkeypatch):
    one = _card()
    del one["key_numbers"][1]
    assert not F.predates_v2(one, "not a time") and not F.predates_v2(one, None)
    assert F.predates_v2(_card(), "not a time")
    _on(monkeypatch)
    card = _card()
    assert F.apply_card_json(card, _memory(), "not a time", "Tata Communications Limited")


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


def test_an_eps_key_beside_a_profit_key_in_the_companys_words_adds_no_second_profit(monkeypatch):
    _on(monkeypatch)
    card = _card()
    card["key_numbers"] = [{"label": "Profit after tax", "value": "₹263.24 Cr", "quote": "- pat_owners Q4FY26: 263.24 Cr"},
                           {"label": "EPS", "value": "₹9.10", "quote": "- eps Q4FY26: 9.1 INR"}]
    F.apply_card_json(card, _memory(), FILED, "Tata Communications Limited")
    assert [k["label"] for k in card["key_numbers"]] == ["Profit after tax"]


# --- blind read of release check 41345924894 (ON better 16, OFF 2; WRONG lines ON 5, OFF 4) ---------------------------------------

def test_an_h1_face_beside_a_q2_table_is_rebuilt_for_the_half(monkeypatch):
    """COALINDIA nse-106834917: the table is Q2FY27, the face H1FY27; the rebuild put Q2's profit on it."""
    _on(monkeypatch)
    rows = [("revenue", "H1FY27", 90433.54), ("revenue", "H1FY26", 80000.0), ("pat", "H1FY27", 15397.24), ("pat", "H1FY26", 10000.0),
            ("pat_owners", "H1FY27", 15368.2), ("pat_owners", "H1FY26", 9990.0),
            ("revenue", "Q2FY27", 44178.74), ("revenue", "Q2FY26", 40000.0), ("pat", "Q2FY27", 6547.43), ("pat", "Q2FY26", 4262.0),
            ("pat_owners", "Q2FY27", 6540.0), ("pat_owners", "Q2FY26", 4255.0)]
    memory = {"financial_metrics": [_e(m, p, v) for m, p, v in rows]}
    card = _card()
    card["results"]["period"] = "Q2FY27"
    card["headline"] = "Coal India H1FY27: revenue ₹90,433.54 Cr, net profit ₹15,397.24 Cr"
    card["key_numbers"][1:3] = [{"label": "Net profit", "value": "₹15,397.24 Cr", "quote": "- pat H1FY27: 15397.2 Cr"},
                                {"label": "Net profit to shareholders", "value": "₹15,368.20 Cr", "quote": "pat_owners H1FY27: 15368.2 Cr"}]
    F.apply_card_json(card, memory, FILED, "Coal India Limited")
    profits = [k["value"] for k in card["key_numbers"] if k["label"].startswith("Net ")]
    assert profits and all("6,547" not in v for v in profits) and profits[0].startswith("₹15,3")


def test_a_loss_against_a_year_ago_profit_has_no_percentage(monkeypatch):
    """c15 nse-106631998: "-2600.1% YoY" on a net loss against a year-ago profit."""
    _on(monkeypatch)
    memory = _memory(pat=-50.0, owners=-50.0, owners_ago=2.0)
    for m in memory["financial_metrics"]:
        if (m["metric"], m["period"]) == ("pat", "Q4FY25"):
            m["value"] = m["sources"][0]["value"] = 2.0
    card = _card()
    F.apply_card_json(card, memory, FILED, "Tata Communications Limited")
    key = next(k for k in card["key_numbers"] if k["label"].startswith("Net "))
    assert key["label"].startswith("Net loss") and "%" not in str(key.get("change") or "")   # no "-2600.1% YoY"


def test_an_owners_figure_no_file_backs_leaves_the_face(monkeypatch):
    """ADANIPORTS nse-106605518: the headline's "net profit to shareholders ₹1,238.67 Cr" is memory's owners' figure with no file
    source (a share of other comprehensive income); the whole profit 3,308.30 is the file's."""
    _on(monkeypatch)
    memory = _memory(pat=3308.3, owners=1238.67, owners_ago=3014.0)
    for m in memory["financial_metrics"]:
        if m["metric"] == "pat_owners":
            m["sources"][0]["lab"]["by"] = "unknown"
    card = _card()
    card["headline"] = F._build(card, F.tagged_from_memory(memory, "Q4FY26", "CONSOLIDATED", any_source=True),
                                "Adani Ports Limited", "", v2=False)["headline"]
    assert "1,238.67" in card["headline"]                    # what the old code wrote from memory as it stood
    F.apply_card_json(card, memory, FILED, "Adani Ports Limited")
    assert "1,238.67" not in card["headline"] and "3,308.3" in card["headline"]


def _value(tagged, metric, period):
    return next((m.value for m in tagged.metrics if (m.metric, m.period) == (metric, period)), None)


def test_the_face_takes_the_file_sources_own_figure_never_the_merged_one(monkeypatch):
    """Lead's review of #370: a row with a file source beside an unknown source whose 1,238.67 is the merged value put 1,238.67 on
    the rebuilt face."""
    _on(monkeypatch)
    memory = _memory()
    row = next(m for m in memory["financial_metrics"] if (m["metric"], m["period"]) == ("pat_owners", "Q4FY26"))
    file_src = row["sources"][0]
    file_src["value"] = 1250.0
    row["value"] = 1238.67
    row["sources"] = [{**file_src, "news_id": "nse-1", "value": 1238.67, "lab": {"by": "unknown", "basis": "CONSOLIDATED"}}, file_src]
    assert _value(F.tagged_from_memory(memory, "Q4FY26", "CONSOLIDATED"), "pat_owners", "Q4FY26") == 1250.0
    assert _value(F.tagged_from_memory(memory, "Q4FY26", "CONSOLIDATED", any_source=True), "pat_owners", "Q4FY26") == 1238.67
    # the file source on the other basis is none for this card
    file_src["basis"] = file_src["lab"]["basis"] = "STANDALONE"
    assert _value(F.tagged_from_memory(memory, "Q4FY26", "CONSOLIDATED"), "pat_owners", "Q4FY26") is None


def test_a_lakh_row_reaches_the_face_in_crore_and_a_dollar_row_never(monkeypatch):
    """Lead's review of #370: tagged_from_memory put a lakh figure on the face as crore."""
    _on(monkeypatch)
    memory = _memory()
    row = next(m for m in memory["financial_metrics"] if (m["metric"], m["period"]) == ("revenue", "Q4FY26"))
    row["value"] = row["sources"][0]["value"] = 655415.0
    row["unit"] = row["sources"][0]["unit"] = "INR_LAKH"
    for any_source in (False, True):
        tagged = F.tagged_from_memory(memory, "Q4FY26", "CONSOLIDATED", any_source=any_source)
        revenue = next(m for m in tagged.metrics if (m.metric, m.period) == ("revenue", "Q4FY26"))
        assert (revenue.value, revenue.unit) == (6554.15, "INR_CR")
    row["unit"] = row["sources"][0]["unit"] = "USD_MN"
    assert _value(F.tagged_from_memory(memory, "Q4FY26", "CONSOLIDATED"), "revenue", "Q4FY26") is None
