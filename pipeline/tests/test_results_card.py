"""Results cards built by code from the XBRL file (results_card.py; owner's PLAN 18 part 4)."""

from __future__ import annotations

from pathlib import Path

from bse_intel import results_card, xbrl
from bse_intel.models import Pass2Output

FIX = Path(__file__).parent / "fixtures"


def _model_card():
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "Q3 revenue rose on lower tax",
        "card": {"impact_level": "MODERATE", "headline": "Ahluwalia Q3 revenue jumps on lower tax and a big order",
                 "takeaway": "Margins held up despite cost pressure.", "core_catalyst": "Lower tax drove profit",
                 "what_happened": ["Revenue rose 12% YoY to ₹952 Cr"],
                 "why_it_matters": [{"text": "One"}, {"text": "Two"}, {"text": "Three"}],
                 "notable_changes": [{"metric": "inventory_change", "previous": "0", "current": "5", "change": "build-up"}],
                 "key_numbers": [{"label": "Revenue", "value": "₹1,952 Cr", "change": "+12% YoY"}]}})


def test_code_writes_the_figures_and_the_model_keeps_a_line_or_two():
    tagged = xbrl.parse((FIX / "bse_main_ind_as_532811_q3fy25.xml").read_bytes())
    out = _model_card()
    notes = results_card.build(out, tagged, "Ahluwalia Contracts (India) Limited")
    card = out.card
    assert card.headline == "Ahluwalia Contracts (India) Q3FY25: revenue ₹951.96 Cr, net profit ₹49.39 Cr"
    table = tagged.table()
    assert all(f.quote in table for f in card.what_happened)          # each fact quotes its table line
    assert [k.label for k in card.key_numbers][:3] == ["Revenue from operations", "EBITDA", "Net profit"]
    assert any(k.label == "EBITDA margin" and k.value == "8.9%" for k in card.key_numbers)
    assert card.notable_changes == [] and card.core_catalyst is None and card.quantified_impact == []
    assert [i.text for i in card.why_it_matters] == ["One", "Two"]
    assert card.takeaway == "Margins held up despite cost pressure." and card.basis == "STANDALONE"
    assert out.timeline_entry.startswith("Q3FY25 results (standalone): revenue ₹951.96 Cr")
    assert notes and "notable changes (1) left out" in notes[0]


def test_a_bank_is_read_on_its_own_lines():
    tagged = xbrl.parse((FIX / "bse_bank_542867_q3fy25.xml").read_bytes())
    out = _model_card()
    results_card.build(out, tagged, "CSB Bank Limited")
    assert out.card.headline.startswith("CSB Bank Q3FY25: interest earned ₹919.38 Cr, net profit ₹151.63 Cr")
    labels = [k.label for k in out.card.key_numbers]
    assert "Operating profit before provisions" in labels and "Provisions" in labels and "EBITDA margin" not in labels


def test_no_file_no_change():
    out = _model_card()
    assert results_card.build(out, None, "X") == [] and out.card.headline.startswith("Ahluwalia Q3 revenue jumps")
