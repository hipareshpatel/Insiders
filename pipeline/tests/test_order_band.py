"""An order sized by the filer's own value bands (order_band.py; blind review 22 Oct 2026, L&T nse-106822983)."""

from bse_intel.models import Pass2Output
from bse_intel.order_band import apply, legend, marked_band

LT = ("Re :  L&T Wins Orders (*Large) in New Delhi and  \nAndhra Pradesh \n ... \n*Order Classification \n \nClassification \n"
      "Significant \nLarge \nMajor \nMega \nUltra-Mega \nValue in ₹ Cr \n1,000 to 2,500 \n2,500 to 5,000 \n5,000 to 10,000 \n"
      "10,000 to 15,000 \n> 15,000 \n \n \nMedia Contact:")


def _out(insights):
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "ORDER_WIN", "timeline_entry": "t",
        "card": {"headline": "L&T PAH wins two govt orders", "impact_level": "MODERATE", "takeaway": "t",
                 "what_happened": [{"text": "L&T won an order from CPWD", "quote": "Awarded by the Central Public Works Department"}],
                 "why_it_matters": [{"text": t, "basis": "FILING"} for t in insights]}})


def test_the_band_is_read_from_the_filings_own_table():
    table = legend(LT)
    assert table["Large"][:2] == (2500, 5000) and table["Ultra-Mega"][:2] == (15000, None)
    assert marked_band(LT) == "Large"


def test_a_line_against_the_band_goes_and_the_band_is_stated():
    out = _out(["Orders are classified as 'Large' (₹2,500-5,000 Cr), but actual values are much smaller, representing routine business",
                "New Delhi order includes a 5-year O&M period"])
    notes = apply(out, LT)
    assert [i.text for i in out.card.why_it_matters] == ["New Delhi order includes a 5-year O&M period"]
    added = out.card.what_happened[-1]
    assert "₹2,500-5,000 Cr" in added.text and added.quote == "2,500 to 5,000" and added.quote in LT
    assert len(notes) == 2


def test_no_table_no_change():
    out = _out(["Orders are large"])
    assert apply(out, "L&T wins orders (*Large) in Delhi") == [] and len(out.card.what_happened) == 1
