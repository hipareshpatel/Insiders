"""CARD_GROUND_ALL_FIELDS (F204, TODO 105): figures in the timeline entry, core catalyst and track-next lists are grounded
like the points. The three live examples of the 27 Oct 2026 blind audit: NCDs "up to 175 Cr" for 125, dilution "1%" for
4.9%, a margin target 13.1 that no source states."""

from bse_intel.grounding import ground_all_fields
from bse_intel.models import Card, Pass2Output
from bse_intel.settings import card_ground_all_fields

FILING = ("The Board approved the issuance of NCDs of up to Rs. 125 Cr. The issue raises the share count from 100 to 104.9 "
          "lakh shares. Q2 EBITDA margin was 11.4%.")
SOURCES = (FILING, "Share India NCD issue", "", "{}", "")


def _out(**kw):
    card = dict(impact_level="HIGH", headline="Share India approves NCDs of up to ₹125 Cr",
                what_happened=[{"text": "NCDs of up to ₹125 Cr approved.", "quote": "up to Rs. 125 Cr"}])
    card |= kw.pop("card", {})
    return Pass2Output(is_material=True, card=Card(**card), timeline_entry=kw.pop("timeline_entry", "Approved NCDs of up to ₹125 Cr."))


def test_the_switch_is_off_by_default(monkeypatch):
    monkeypatch.delenv("CARD_GROUND_ALL_FIELDS", raising=False)
    assert not card_ground_all_fields()
    monkeypatch.setenv("CARD_GROUND_ALL_FIELDS", "1")
    assert card_ground_all_fields()


def test_a_timeline_figure_the_filing_does_not_state_is_dropped():
    out = _out(timeline_entry="Share India approved the issuance of NCDs of up to ₹175 Cr.")
    notes = ground_all_fields(out, SOURCES)
    assert out.timeline_entry == out.card.headline and notes == ["timeline_entry: ungrounded figure, dropped"]


def test_a_timeline_keeps_its_grounded_sentence():
    out = _out(timeline_entry="Approved NCDs of up to ₹125 Cr. Raised a further ₹175 Cr.")
    ground_all_fields(out, SOURCES)
    assert out.timeline_entry == "Approved NCDs of up to ₹125 Cr."


def test_a_risk_with_a_wrong_small_percentage_is_dropped_and_a_grounded_one_kept():
    out = _out(card={"track_next": {"risks": ["Equity dilution of approx 1% based on share count increase",
                                              "EBITDA margin of 11.4% may not hold"]}})
    notes = ground_all_fields(out, SOURCES)
    assert out.card.track_next.risks == ["EBITDA margin of 11.4% may not hold"]
    assert notes == ["track_next.risks: ungrounded figure, dropped"]


def test_a_kpi_target_in_no_source_is_dropped_and_the_others_kept():
    out = _out(card={"track_next": {"kpis_to_verify": [{"kpi": "EBITDA margin", "target": "13.1", "check_in": "Q3FY27 results"},
                                                       {"kpi": "EBITDA margin", "target": "11.4%"}],
                                    "catalysts": ["NCD proceeds of ₹125 Cr"], "pending_approvals": ["Allotment of ₹999 Cr"],
                                    "milestones": [{"what": "Raise ₹450 Cr", "when": "Q3FY27"}]}})
    out.card.core_catalyst = "Funding of ₹300 Cr"
    ground_all_fields(out, SOURCES)
    t = out.card.track_next
    assert [k.target for k in t.kpis_to_verify] == ["11.4%"]
    assert t.catalysts == ["NCD proceeds of ₹125 Cr"] and t.pending_approvals == [] and t.milestones == []
    assert out.card.core_catalyst is None


def test_a_grounded_core_catalyst_and_timeline_stay():
    out = _out(card={"core_catalyst": "A ₹125 Cr NCD raise"}, timeline_entry="")
    assert ground_all_fields(out, SOURCES) == []
    assert out.card.core_catalyst == "A ₹125 Cr NCD raise" and out.timeline_entry == out.card.headline


def test_a_figure_code_computed_from_the_filing_is_kept():
    # review of F204: the call passed no computed figures, so a verified sum the main check forgives was dropped here first
    out = _out(card={"track_next": {"catalysts": ["NCD proceeds of ₹229.9 Cr in total"]}})
    ground_all_fields(out, SOURCES)
    assert out.card.track_next.catalysts == []
    out = _out(card={"track_next": {"catalysts": ["NCD proceeds of ₹229.9 Cr in total"]}})
    ground_all_fields(out, SOURCES, [229.9])
    assert out.card.track_next.catalysts == ["NCD proceeds of ₹229.9 Cr in total"]


def test_the_pipeline_passes_its_computed_figures():
    # the same list check_card_all forgives: only verified impacts whose inputs are all in the filing
    from types import SimpleNamespace
    from bse_intel import pipeline
    out = _out()
    quant = SimpleNamespace(items=[{"check": "VERIFIED", "computed": 229.9}, {"check": "MISMATCH", "computed": 999.0},
                                   {"check": "VERIFIED", "computed": 450.0, "unsourced_inputs": ["450"]}])
    assert pipeline.derived_figures(out.card, quant, SOURCES) == [229.9]
