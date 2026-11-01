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


def test_fix_unit_slips_refuses_an_unproven_correction_off_the_companys_scale():
    """The CDSL class (release check 41338082613): the card copies a printed figure's digits ("₹4,939.22 Cr") and a lakh table
    makes it ₹49.39 Cr. No scale (switch off) corrects it; a scale where 4,939.22 sits keeps it."""
    from test_cards import LAKH_STATEMENT, _results_reply

    off = _results_reply(["Revenue ₹951.96 Cr, PAT ₹4,939.22 Cr"], [], [])
    assert P.fix_unit_slips(off, (LAKH_STATEMENT, "", "")) == {"4,939.22": "49.39"}
    on = _results_reply(["Revenue ₹951.96 Cr, PAT ₹4,939.22 Cr"], [], [])
    assert P.fix_unit_slips(on, (LAKH_STATEMENT, "", ""), (), [951.96, 4000.0]) == {}
    assert on.card.what_happened[0].text == "Revenue ₹951.96 Cr, PAT ₹4,939.22 Cr"
    real = _results_reply(["Revenue ₹951.96 Cr, PAT ₹4,939.22 Cr"], [], [])
    assert P.fix_unit_slips(real, (LAKH_STATEMENT, "", ""), (), [49.0, 95.2]) == {"4,939.22": "49.39"}   # off its scale: fixed


def test_a_correction_its_source_proves_is_never_refused():
    """GOODYEAR 3c2d45df / ENGINERSIN nse-106836580 (release check 41338082613): the card shifted the printed figure's decimal
    point ("4,939.22" lakh carded "₹493.92 Cr"); the guard blocked the right correction. Proven, it goes through at any scale."""
    from test_cards import LAKH_STATEMENT, _results_reply

    on = _results_reply(["Revenue ₹951.96 Cr, PAT ₹493.92 Cr"], [], [])
    assert P.fix_unit_slips(on, (LAKH_STATEMENT, "", ""), (), [951.96, 480.0]) == {"493.92": "49.39"}


def test_unit_fix_proven_on_the_traced_cards():
    # release check 41338082613's TRACE lines
    five_star = {"raw": "1,322.46", "reading": 3, "unit": 10, "source": "ment Loan Portfolio 844 ₹ 12,133 Mn ₹ 132,246 Mn +9 +96"}
    goodyear = {"raw": "1,528.7", "reading": 3, "unit": 100, "source": "ome tax matters* (refer note (i) below) 15,287 14,525 C."}
    engineers = {"raw": "2,042.05", "reading": 3, "unit": 10, "source": "Total Order Book 204205 144,242 121,443"}
    tvs = {"raw": "1,933", "reading": 2, "source": "the INR 193,31,19,436.71 price at which the shares are acquire"}
    hdfcamc = {"raw": "9,691", "reading": 1, "source": "ERLY AVERAGE AUM² ₹9,210 bn ₹6,280 bn ₹9,691 bn ₹6,507 bn"}
    assert all(P.unit_fix_proven(t) for t in (five_star, goodyear, engineers, tvs, hdfcamc))
    cdsl = {"raw": "272", "reading": 3, "unit": 100, "source": "DA w/o Dividend 233 205 339 179 168 272 255 247 212 101 165 Q2FY26"}
    heritage = {"raw": "62.11", "reading": 3, "unit": 10, "source": ""}
    assert not any(P.unit_fix_proven(t) for t in (cdsl, heritage, None))
