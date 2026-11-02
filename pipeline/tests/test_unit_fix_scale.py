"""UNIT_FIX_SCALE_GUARD: the unit fixer makes only a correction the filing proves (the lead's rule after the blind read of release
check 41357717339, 18 changed cards). Each card below is one the blind read judged, its source window from the release check's
TRACE line (docs/audit/live/release-2026-11-02b/unit_fix_scale.txt) or, where the stored text could not re-make it, the printed
figure the lead names. With the guard off the fixer behaves as before."""

from bse_intel import pipeline as P
from test_cards import LAKH_STATEMENT, _results_reply


def _fixed(text: str, filing: str, guard: bool = True) -> dict:
    out = _results_reply([text], [], [])
    return P.fix_unit_slips(out, (filing, "", ""), (), guard)


# --- the fixer was RIGHT: the guard lets these through ------------------------------------------------------------------------

def test_emkay_a_figure_printed_in_mn_proves_the_enlargement():
    """EMKAY nse-106832905: "1,99,782 Mn" carded ₹199.78 Cr is ₹19,978 Cr."""
    assert _fixed("AUM of ₹199.78 Cr at the quarter end.", "(₹ in Mn)\nAssets under management ₹1,99,782 Mn ₹1,52,410 Mn\n") \
        == {"199.78": "19,978"}


def test_mobikwik_a_bracketed_loss_in_mn():
    """MOBIKWIK nse-106618046: "(₹794) Mn" carded as a ₹794 Cr loss is ₹79.4 Cr."""
    assert _fixed("Net loss of ₹794 Cr in FY26.",
                  "1,159 Bn ₹24,774 Mn ₹11,925 Mn ₹3,616\nPAT (₹794) Mn (₹1,215) Mn Growth 57% 31% (3%)\n") == {"794": "79.4"}


def test_fivestar_a_table_figure_with_its_own_mn():
    """FIVESTAR nse-106603286 (reading 3, the figure carries its own "Mn"): AUM ₹1,322.46 Cr is ₹13,224.6 Cr."""
    assert _fixed("AUM ₹1,322.46 Cr at the quarter end.",
                  "(₹ in Mn)\nGross Loan Portfolio 844 ₹ 12,133 Mn ₹ 132,246 Mn +9 +96 +24% -17% +2% +11%\n") \
        == {"1,322.46": "13,224.6"}


def test_heritgfood_a_million_table_with_no_unit_word_in_the_row():
    """HERITGFOOD d7ea9e10: "Total equity 9,471.20" (₹ million) carded ₹9,471 Cr is ₹947.1 Cr."""
    filing = "Balance sheet (Rs. In Mn.)\nEquity share capital 464.00 464.00\nOther equity 9,007.22 7,571.00\n" \
             "Total equity - 9,471.20 8,034.98\nLIABILITIES Non-current liabilities\n"
    assert _fixed("Total equity ₹9,471 Cr at the half year.", filing) == {"9,471": "947.1"}


def test_acevector_a_figure_printed_in_million():
    """ACEVECTOR nse-106828931: "₹13.07 million" carded ₹13.07 Cr is ₹1.31 Cr."""
    assert _fixed("Proceeds of ₹13.07 Cr from the offer.", "The company received an amount of ₹13.07 million from the offer.\n") \
        == {"13.07": "1.31"}


def test_alivus_a_figure_printed_in_million():
    """ALIVUS nse-106835187: "₹278 million" carded ₹278 Cr is ₹27.8 Cr."""
    assert _fixed("Net profit ₹278 Cr in the quarter.", "Highlights\nNet profit at ₹278 million, up 12%\n") == {"278": "27.8"}


def test_tvsmotor_a_whole_rupee_amount_under_the_cards_head():
    """TVSMOTOR nse-106627227: "INR 193,31,19,436.71" cost of acquisition carded ₹1,933 Cr is ₹193.31 Cr."""
    assert _fixed("Cost of acquisition ₹1,933 Cr for the stake.",
                  "8. Cost of acquisition and/or the INR 193,31,19,436.71 price at which the shares are acquired.\n") \
        == {"1,933": "193.31"}


def test_goodyear_a_lakh_table_row_with_no_unit_word():
    """GOODYEAR 3c2d45df: contingent "Income tax matters 15,287" (₹ lakh) carded ₹1,528.7 Cr is ₹152.87 Cr."""
    filing = "Contingent liabilities (₹ in Lakhs)\nA. Excise matters 120 110\nB. Income tax matters* (refer note (i) below) " \
             "15,287 14,525\nC. Sales tax matters 9 9\n"
    assert _fixed("Income tax matters of ₹1,528.7 Cr are contested.", filing) == {"1,528.7": "152.87"}


# --- the fixer was WRONG: the guard stops these -------------------------------------------------------------------------------

def test_cdsl_a_deck_page_that_says_crore():
    """CDSL nse-106838164: the deck's page says "All amounts in crore"; another page's lakh made 272 into 2.72."""
    deck = ("--- Page 1\nSegment revenue (₹ in Lakhs) 1,200.00 1,100.00\n--- Page 2\nAll amounts in crore\n"
            "EBITDA EBITDA w/o Dividend 233 205 339 179 168 272 255 247 212 101 165 Q2FY26 Q3FY26 Q4FY26\n")
    assert _fixed("EBITDA ₹272 Cr in Q2FY27.", deck, guard=False) == {"272": "2.72"}   # what the fixer did
    assert _fixed("EBITDA ₹272 Cr in Q2FY27.", deck) == {}


def test_heritgfood_a_lost_decimal_point_is_no_figure_to_enlarge_by():
    """HERITGFOOD 527b6923 Q2FY27: "62113" between "375.76" and "813.83" is 621.13 (₹ million); the card's ₹62.11 Cr was right."""
    filing = "Segment results (Rs. In Mn.)\nNon-allocable items a Dairy 438.07 375.76 62113 813.83 1,127.03 182755 b. Renewable\n"
    assert _fixed("Dairy segment result ₹62.11 Cr in Q2FY27.", filing, guard=False) == {"62.11": "6,211"}
    assert _fixed("Dairy segment result ₹62.11 Cr in Q2FY27.", filing) == {}


def _never(text: str, filing: str) -> None:
    """The card's figure is the right crore value of the printed figure: the guard never converts it, whatever else the
    filing prints (a whole-rupee amount, a lakh table) that would."""
    assert _fixed(text, filing) == {}, text


def test_tinnarubr_a_lakh_figure_already_in_crore():
    """TINNARUBR nse-106824690: "6,660 lakh" carded ₹66.60 Cr (right); the fixer made ₹0.07 Cr."""
    _never("EBITDA ₹66.60 Cr in Q2FY27.", "EBITDA of Rs 6,660 lakh in the quarter.\nGuarantee of Rs 6,66,000 given.\n")


def test_meil_a_lakh_figure_already_in_crore():
    """MEIL nse-106624393: "9,066 lakh" carded ₹90.66 Cr (right); the fixer made ₹0.091 Cr."""
    _never("Order inflow ₹90.66 Cr in the quarter.", "Orders worth Rs 9,066 lakh were received.\nDeposit Rs 9,06,600 placed.\n")


def test_heritgfood_a_million_figure_already_in_crore():
    """HERITGFOOD 527b6923 Q2FY27: "7,480.10 mn" carded ₹748.01 Cr (right); the fixer made ₹74,801 Cr."""
    _never("Revenue ₹748.01 Cr in Q2FY27.", "(Rs. In Mn.)\nRevenue from operations 7,480.10 mn 6,900.00\n")


def test_icicigi_a_lakh_figure_already_in_crore():
    """ICICIGI nse-106817787: "2,92,178 lakh" carded ₹2,921.78 Cr (right); the fixer made ₹2.92 Cr."""
    _never("Gross premium ₹2,921.78 Cr in Q2FY27.", "(₹ in Lakhs)\nGross direct premium income ₹2,92,178 lakh 2,70,000\n")


def test_hdfcamc_a_million_figure_already_in_crore():
    """HDFCAMC nse-106818607: "10,260 mn" carded ₹1,026 Cr (right); the fixer made ₹10,26,000 Cr."""
    _never("Revenue ₹1,026 Cr in the quarter.", "Revenue from operations ₹10,260 mn\nQUARTERLY AVERAGE AUM ₹1,026 bn\n")


def test_sobha_a_million_figure_already_in_crore():
    """SOBHA nse-106822202: "331 mn" carded ₹33.1 Cr (right); the fixer made ₹3.31 Cr."""
    _never("Net profit ₹33.1 Cr in Q2FY27.", "(₹ in Lakhs)\nNet profit ₹331 mn for the quarter 3,310\n")


# --- the guard's other cases (earlier reviews) ------------------------------------------------------------------------------

def test_off_the_fixer_is_unchanged():
    assert _fixed("Revenue ₹951.96 Cr, PAT ₹4,939.22 Cr", LAKH_STATEMENT, guard=False) == {"4,939.22": "49.39"}
    assert _fixed("Revenue ₹951.96 Cr, PAT ₹4,939.22 Cr", LAKH_STATEMENT) == {"4,939.22": "49.39"}   # a lakh page proves it


def test_a_source_row_naming_another_thing_never_proves():
    """Reviews of #362: a whole-rupee amount needs the card's own head; a table row or a figure with its unit naming something
    else (revenue, a loan) proves nothing."""
    for text, filing in (("Revenue ₹1,250 Cr in the quarter.", "Paid-up capital Rs 1,25,00,00,000 as at 30.09.2026.\n"),
                         ("Net profit ₹1,250 Cr in the quarter.", "Profit before tax Rs 1,25,00,00,000\n"),
                         ("Operating income ₹1,250 Cr in the quarter.", "Operating expenses Rs 1,25,00,00,000 incurred.\n"),
                         ("EBITDA ₹272 Cr for the quarter.", "(₹ in Lakhs)\nRevenue 2,720\nOther income 100\n"),
                         ("Net profit ₹13.07 Cr for the quarter.", "Net profit fell. Loan of ₹13.07 million raised via NCDs.\n")):
        assert _fixed(text, filing) == {}, text
    assert _fixed("Revenue ₹272 Cr for the quarter.", "(₹ in Lakhs)\nRevenue from operations 2,720\n") == {"272": "27.2"}
