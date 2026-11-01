"""CARD_GUIDED_NOT_ACTUAL (blind audit 1 Nov 2026, BIRLACORPN nse-106838226): management's expected FY27 peak net debt of
4,000 Cr was kept as a balance sheet and a card said "Net debt was ₹4,000 Cr at the end of FY26"."""

import copy

from bse_intel import guided_actual as G

CALL_TAKEAWAY = "FY27 capex guided at ₹900 Cr, with peak net debt expected around ₹4,000 Cr."
SNAP_CALL = {"net_debt_cr": 4000.0, "as_of": "2026-05-14T16:16:55+05:30", "source_news_id": "nse-106622547",
             "lab": {"by": "ai", "doc": "call", "at": "2026-05-14T16:16:55+05:30"}}
FILE_SNAP = {"period": "Q2FY27", "gross_debt_cr": 2917.3, "cash_cr": 32.92, "as_of": "2026-10-31T10:00:00+05:30",
             "lab": {"by": "file", "doc": "results"}}
MEMORY = {"balance_sheet": [SNAP_CALL, FILE_SNAP],
          "guidance": [{"id": "g1", "statement": "We expect peak net debt around 4,000 crore in FY27", "metric": "net debt",
                        "target": "4000", "due": "FY27", "status": "OPEN"}]}
CARD = {"headline": "Birla Corp approves up to ₹250 Cr NCD issue",
        "what_happened": [{"text": "Board approved NCDs up to ₹250 Cr.", "quote": "NCD aggregating upto ₹2,50,00,00,000/-"}],
        "why_it_matters": [{"text": "Net debt was ₹4,000 Cr at the end of FY26; gross long-term borrowings stood at ₹2,268.54 Cr.",
                            "basis": "BALANCE_SHEET", "quote": None},
                           {"text": "Operating margin contracted to 9.59%.", "basis": "FILING", "quote": "Operating Margin 9.59%"}]}


def on(monkeypatch):
    monkeypatch.setenv("CARD_GUIDED_NOT_ACTUAL", "1")


def test_off_nothing_changes(monkeypatch):
    monkeypatch.setenv("CARD_GUIDED_NOT_ACTUAL", "0")
    card = copy.deepcopy(CARD)
    assert G.apply_card_json(card, MEMORY) == [] and card == CARD
    assert G.guided_balance_fields({"net_debt_cr": 4000.0}, "call", [CALL_TAKEAWAY]) == []
    assert G.view_balance(SNAP_CALL, {"net_debt_cr": 4000.0}) == {"net_debt_cr": 4000.0}
    assert G.summary_marker(SNAP_CALL) == "" and G.guided_label() == "Management said"


def test_a_guided_figure_stated_as_an_actual_is_dropped(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    notes = G.apply_card_json(card, MEMORY)
    assert [i["text"] for i in card["why_it_matters"]] == ["Operating margin contracted to 9.59%."]
    assert len(notes) == 1 and "guided figure as an actual" in notes[0]


def test_the_periodless_call_balance_alone_is_not_an_actual(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    memory = {"balance_sheet": [SNAP_CALL]}   # Birla's memory: no guidance entry, only the call's balance figure
    assert G.apply_card_json(card, memory)
    assert len(card["why_it_matters"]) == 1


def test_an_actual_in_memory_or_in_the_cards_own_quote_keeps_the_point(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(CARD)
    held = {**MEMORY, "balance_sheet": [*MEMORY["balance_sheet"], {"period": "Q4FY26", "net_debt_cr": 4000.0,
                                                                    "lab": {"by": "file", "doc": "results"}}]}
    assert G.apply_card_json(card, held) == [] and card == CARD
    quoted = copy.deepcopy(CARD)
    quoted["why_it_matters"][0]["quote"] = "Net debt as on 31 March 2026 4,000"
    assert G.apply_card_json(quoted, MEMORY) == []
    guided = copy.deepcopy(CARD)
    guided["why_it_matters"][0]["text"] = "Management expects peak net debt of about ₹4,000 Cr in FY27."
    assert G.apply_card_json(guided, MEMORY) == []   # worded as guidance: kept


def test_a_call_figure_worded_as_guided_is_not_stored_as_a_balance(monkeypatch):
    on(monkeypatch)
    assert G.guided_balance_fields({"net_debt_cr": 4000.0}, "call", [CALL_TAKEAWAY]) == ["net_debt_cr"]
    assert G.guided_balance_fields({"net_debt_cr": 4000.0}, "call", ["Net debt stood at ₹4,000 Cr at the end of Q4."]) == []
    assert G.guided_balance_fields({"net_debt_cr": 4000.0}, "results", [CALL_TAKEAWAY]) == []


def test_merge_leaves_the_guided_net_debt_out_of_memory(monkeypatch):
    from bse_intel.dossier import merge
    from bse_intel.models import Filing, Pass2Output

    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "CONCALL_PRESENTATION", "timeline_entry": "call",
        "card": {"impact_level": "LOW", "headline": "Birla Corp Q4 earnings call highlights", "what_happened": [{"text": "x"}],
                 "call_takeaways": [{"category": "Guidance", "text": CALL_TAKEAWAY}]},
        "dossier_delta": {"balance_sheet": {"net_debt_cr": 4000.0}}})
    filing = Filing.model_construct(news_id="nse-1", scrip_code="500335", company_name="Birla", headline="Earnings call transcript",
                                    subject="Transcript", event_type="CONCALL_PRESENTATION", filed_at="2026-05-14T16:16:55+05:30")
    monkeypatch.setenv("CARD_GUIDED_NOT_ACTUAL", "0")
    assert merge({}, out, filing, None, "2026-05-14T16:16:55+05:30")["balance_sheet"]
    on(monkeypatch)
    assert not merge({}, out, filing, None, "2026-05-14T16:16:55+05:30").get("balance_sheet")


def test_the_ai_is_shown_a_periodless_call_figure_as_possibly_guided(monkeypatch):
    on(monkeypatch)
    shown = G.view_balance(SNAP_CALL, {"net_debt_cr": 4000.0})
    assert "guided" in shown["note"] and "not an actual" in shown["note"]
    assert G.view_balance(FILE_SNAP, {"gross_debt_cr": 2917.3}) == {"gross_debt_cr": 2917.3}   # a file's: as is
    assert "guided" in G.summary_marker(SNAP_CALL) and G.summary_marker(FILE_SNAP) == ""
    assert "guided" in G.guided_label()


def test_memory_context_labels_guidance_as_guided(monkeypatch):
    from bse_intel.card_context import memory_context

    before = {"guidance": [{"id": "g", "statement": "Capex of ₹900 Cr in FY27", "metric": "capex", "target": "900 Cr", "due": "FY27",
                            "due_date": "2027-03-31", "status": "OPEN", "given_on": "2026-05-14T10:00:00+05:30",
                            "source_type": "CONCALL"}]}
    monkeypatch.setenv("CARD_GUIDED_NOT_ACTUAL", "0")
    assert memory_context(before, "FUNDRAISE", "2026-10-31T10:00:00+05:30")[0]["label"].startswith("Management said")
    on(monkeypatch)
    first = memory_context(before, "FUNDRAISE", "2026-10-31T10:00:00+05:30")[0]
    assert "guided" in first["label"] and "by FY27" in first["text"]


def test_a_dated_actual_beside_a_later_target_is_not_refused_as_guided(monkeypatch):
    on(monkeypatch)
    said = ["Net debt stood at ₹3,500 Cr as of Sep 30, and management will target ₹3,000 Cr by FY28."]
    assert G.guided_balance_fields({"net_debt_cr": 3500.0}, "call", said) == []
    assert G.guided_balance_fields({"net_debt_cr": 3000.0}, "call", said) == ["net_debt_cr"]
    assert G.guided_balance_fields({"cash_cr": 800.0}, "call", ["Cash of ₹800 Cr as of Sep 30 will fund the project."]) == []


def test_the_refused_field_is_recorded_on_memory(monkeypatch):
    from bse_intel.dossier import merge
    from bse_intel.models import Filing, Pass2Output

    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "CONCALL_PRESENTATION", "timeline_entry": "call",
        "card": {"impact_level": "LOW", "headline": "Birla Corp Q4 earnings call highlights", "what_happened": [{"text": "x"}],
                 "call_takeaways": [{"category": "Guidance", "text": CALL_TAKEAWAY}]},
        "dossier_delta": {"balance_sheet": {"net_debt_cr": 4000.0}}})
    filing = Filing.model_construct(news_id="nse-1", scrip_code="500335", company_name="Birla", headline="Earnings call transcript",
                                    subject="Transcript", event_type="CONCALL_PRESENTATION", filed_at="2026-05-14T16:16:55+05:30")
    on(monkeypatch)
    kept = merge({}, out, filing, None, "2026-05-14T16:16:55+05:30")
    assert kept["guided_refused"][0]["field"] == "net_debt_cr" and kept["guided_refused"][0]["value"] == 4000.0


def test_coincident_numbers_are_not_a_guided_figure_stated_as_actual(monkeypatch):
    on(monkeypatch)
    memory = {"guidance": [{"id": "g", "statement": "We target 15% revenue growth, 100 MTPA capacity and capex of ₹900 Cr", "metric": "revenue",
                            "target": "15%", "status": "OPEN"}],
              "financial_metrics": [{"metric": "capex", "period": "FY26", "value": 900.0}]}
    card = {"what_happened": [{"text": "Revenue rose 15% YoY.", "quote": "growth 15.2%"},
                              {"text": "Capacity is 100 MTPA currently.", "quote": None},
                              {"text": "Capex was ₹900 Cr in FY26.", "quote": None, "basis": "MEMORY"}]}
    before = copy.deepcopy(card)
    assert G.apply_card_json(card, memory) == [] and card == before


def test_a_filing_point_with_no_quote_is_noted_not_dropped(monkeypatch):
    on(monkeypatch)
    card = {"why_it_matters": [{"text": "Net debt was ₹4,000 Cr at the end of FY26.", "basis": "FILING", "quote": None}]}
    notes = G.apply_card_json(card, MEMORY)
    assert len(card["why_it_matters"]) == 1 and notes and "left for review" in notes[0]


def test_a_quote_within_rounding_keeps_the_point(monkeypatch):
    on(monkeypatch)
    card = {"why_it_matters": [{"text": "Net debt was ₹4,000 Cr at the end of FY26.", "basis": "FILING",
                                "quote": "Net debt 4,010"}]}
    assert G.apply_card_json(card, MEMORY) == [] and len(card["why_it_matters"]) == 1
