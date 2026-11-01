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


# --- the lead's probes on #362: the proof is the same printed number, decimal-shifted ------------------------------------------

def _guarded(text: str, filing: str, scale: list[float]) -> dict:
    from test_cards import _results_reply

    out = _results_reply([text], [], [])
    return P.fix_unit_slips(out, (filing, "", ""), (), scale)


def test_reading_two_needs_the_cards_own_label_beside_the_rupee_amount():
    # unrelated whole-rupee amounts that are the card's figure shifted: no proof, the guard keeps the figure at its scale
    assert _guarded("Revenue ₹1,250 Cr in the quarter.",
                    "Statement of results.\nPaid-up capital Rs 1,25,00,00,000 as at 30.09.2026.\n", [1000.0]) == {}
    assert _guarded("Revenue ₹125 Cr in the quarter.", "Notes.\nEquity share capital INR 12,50,00,000 fully paid.\n", [100.0]) == {}
    assert _guarded("Order inflow ₹220 Cr in the quarter.", "Notes.\nGuarantee of Rs. 22,00,00,000 given to a bank.\n", [200.0]) == {}
    # TVSMOTOR nse-106627227: the amount sits in the clause the card names ("cost of acquisition"): proven, fixed at any scale
    assert _guarded("Cost of acquisition ₹1,933 Cr for the stake.",
                    "8. Cost of acquisition and/or the INR 193,31,19,436.71 price at which the shares are acquired.\n",
                    [1500.0]) == {"1,933": "193.31"}


def test_reading_one_needs_a_currency_and_no_count():
    # ACEVECTOR's class: "13.07 million shares" is a count, not money: refused at scale
    assert _guarded("Revenue ₹13.07 Cr for the quarter.",
                    "(₹ in Lakhs)\nRevenue from operations 50,000.00 45,000.00\nShares issued 13.07 million shares to investors.\n",
                    [10.0]) == {}
    # HDFCAMC: "₹9,691 bn" is the card's exact figure with its currency and unit
    assert _guarded("Average AUM ₹9,691 Cr for the quarter.", "QUARTERLY AVERAGE AUM ₹9,210 bn ₹6,280 bn ₹9,691 bn ₹6,507 bn\n",
                    [9000.0]) == {"9,691": "969,100"}


def test_reading_three_is_never_proven_when_the_cards_digits_are_printed():
    # CDSL's class with a near number placed first ("271.9"): the filing prints "272", so the card may have copied it
    filing = ("(₹ in Lakhs)\nOther income 271.9 230.0 " + "x" * 100 + "\nEBITDA 272 255 247 212\n"
              "Revenue from operations 39,448.00 30,000.00\n")
    assert _guarded("EBITDA ₹272 Cr for the quarter.", filing, [300.0]) == {}


# --- the second review of #362: the source figure's own row label must carry the card label's head noun ----------------------

def test_a_shared_generic_word_is_no_proof():
    refused = [
        ("Consolidated revenue ₹1,250 Cr in the quarter.", "Consolidated equity Rs 1,25,00,00,000 reported.\n", [1000.0]),   # G1
        ("Operating income ₹1,250 Cr in the quarter.", "Operating expenses Rs 1,25,00,00,000 incurred.\n", [1000.0]),        # G2
        ("Net profit ₹1,250 Cr in the quarter.", "Profit before tax Rs 1,25,00,00,000\n", [1000.0]),                          # G3
        ("Revenue from operations ₹1,250 Cr in the quarter.",
         "Revenue from operations grew; Rs 1,25,00,00,000 was raised as debt from operations.\n", [1000.0]),                  # G4
        ("EBITDA ₹272 Cr for the quarter.", "(₹ in Lakhs)\nRevenue 2,720\nOther income 100\n", [300.0]),                      # R3
        ("Revenue ₹13.07 Cr for the quarter.", "Revenue ₹13.07 million from sale of shares to promoters.\n", [10.0]),         # R1a
        ("Net profit ₹13.07 Cr for the quarter.", "Net profit fell. Loan of ₹13.07 million raised via NCDs.\n", [10.0]),      # R1b
    ]
    for text, filing, scale in refused:
        assert _guarded(text, filing, scale) == {}, text


def test_the_same_head_under_a_table_row_still_proves():
    # FIVESTAR nse-106603286: the loan portfolio row in ₹ Mn, the card's AUM a tenth of it
    assert _guarded("AUM ₹1,322.46 Cr at the quarter end.",
                    "(₹ in Mn)\nGross Loan Portfolio 844 ₹ 12,133 Mn ₹ 132,246 Mn +9 +96\n", [1300.0]) == {"1,322.46": "13,224.6"}
    # a lakh table's row read a power of ten off (GOODYEAR's shape): "Profit for the period 4,939.22" carded ₹493.92 Cr
    from test_cards import LAKH_STATEMENT
    assert _guarded("PAT ₹493.92 Cr in the quarter.", LAKH_STATEMENT, [480.0]) == {"493.92": "49.39"}


def test_other_income_other_equity_and_profit_on_are_no_head():
    """Third review of #362: a bare income, other equity and a qualified profit proved the wrong figure."""
    for text, filing in (("Revenue ₹272 Cr for the quarter.", "(₹ in Lakhs)\nOther income 2,720\n"),
                         ("Revenue ₹272 Cr for the quarter.", "(₹ in Lakhs)\nInterest income 2,720\n"),
                         ("Revenue ₹272 Cr for the quarter.", "(₹ in Lakhs)\nTotal comprehensive income 2,720\n"),
                         ("Net worth ₹272 Cr at the year end.", "(₹ in Lakhs)\nOther equity 2,720\n"),
                         ("PAT ₹272 Cr for the quarter.", "(₹ in Lakhs)\nTax on profit 2,720\n"),
                         ("PAT ₹272 Cr for the quarter.", "(₹ in Lakhs)\nProfit on sale of investments 2,720\n")):
        assert _guarded(text, filing, [272.0]) == {}, (text, filing)
    # the revenue row itself still proves it
    assert _guarded("Revenue ₹272 Cr for the quarter.", "(₹ in Lakhs)\nRevenue from operations 2,720\n", [272.0]) == {"272": "27.2"}
