"""UNIT_FIX_SCALE_GUARD (1 Nov 2026, CDSL nse-106838164): the unit fixer made a deck's "₹272 Cr" standalone revenue ₹2.72 Cr
(and 179, 101, 163 likewise) beside a ₹394 Cr consolidated quarter in memory."""

from bse_intel import pipeline as P

MEMORY = {"financial_metrics": [{"metric": "revenue", "period": "Q2FY27", "value": 394.48},
                                {"metric": "pat", "period": "Q2FY27", "value": 173.85},
                                {"metric": "revenue", "period": "Q2FY24", "value": 5.0}],     # an old quarter is not the scale
          "standalone": {"metrics": [{"metric": "revenue", "period": "Q2FY27", "value": 272.4}]}}


def test_the_scale_is_the_latest_quarters_on_both_bases():
    scale = P.scale_crore(MEMORY, periods=1)
    assert sorted(scale) == [173.85, 272.4, 394.48]
    assert P._at_scale(272, scale) and not P._at_scale(2.72, scale)
    assert P._at_scale(1100, scale) and not P._at_scale(1500, scale)   # within 3x of 394.48, then not


def test_no_memory_no_scale():
    assert P.scale_crore(None) == [] and P.scale_crore({}) == []


def test_fix_unit_slips_refuses_a_correction_off_the_companys_scale():
    """Both modes on the same slip: no scale (switch off) corrects 493.92 -> 49.39; a scale where 493.92 sits keeps it."""
    from test_cards import LAKH_STATEMENT, _results_reply

    off = _results_reply(["Revenue ₹951.96 Cr, PAT ₹493.92 Cr"], [], [])
    assert P.fix_unit_slips(off, (LAKH_STATEMENT, "", "")) == {"493.92": "49.39"}
    on = _results_reply(["Revenue ₹951.96 Cr, PAT ₹493.92 Cr"], [], [])
    assert P.fix_unit_slips(on, (LAKH_STATEMENT, "", ""), (), [951.96, 480.0]) == {}
    assert on.card.what_happened[0].text == "Revenue ₹951.96 Cr, PAT ₹493.92 Cr"
    real = _results_reply(["Revenue ₹951.96 Cr, PAT ₹493.92 Cr"], [], [])
    assert P.fix_unit_slips(real, (LAKH_STATEMENT, "", ""), (), [49.0, 95.2]) == {"493.92": "49.39"}   # a real slip still fixed
