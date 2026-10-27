"""PDF reader row fixes from the hard-set diagnosis (27 Oct 2026, docs/bench/hardpdf/why-readers-fail.md): garbled unit lines, the
basis of a boxed table, and revenue / profit labels. All behind PDF_ROW_FIXES (off by default; the off path is the old
behaviour, asserted in each test). The texts are the real pages' lines (SPANDANA, SUNDARMFIN, CENTRUM, EMKAY, INDOSTAR, VLS
Finance, Authum, Union Bank); PDF_DATES_2DIGIT is turned on where the page prints two-digit years, as the maintenance jobs do."""

from __future__ import annotations

import pytest

from bse_intel import pdf_readers as prd
from bse_intel import pdf_referee as pr
from bse_intel.settings import Settings, get_settings


@pytest.fixture
def on(monkeypatch):
    def _set(*names):
        for n in names:
            monkeypatch.setenv(n, "1")
        get_settings.cache_clear()
    return _set


def vals(rows, period, metric, basis):
    return [round(v, 4) for v, _, _ in pr.figure_for(rows, period, metric, basis)["values"]]


def test_the_switch_is_off_by_default():
    assert Settings().pdf_row_fixes is False


# --- 1. garbled unit lines ----------------------------------------------------------------------------------------------------

SPANDANA_P4 = "\n".join([       # p4, standalone: the rupee sign came out as '"' and the tail "unless otherwise stated" follows
    "Statement of Unaudited Standalone Financial results for the Quarter and Half Year ended September 30, 2024",
    '(" in crores unless otherwise stated)',
    "Quarter ended Half year ended Year ended",
    "Sr. No. Particulars 30-Sep-24 30-Jun-24 30-Sep-23 30-Sep-24 30-Sep-23 31-Mar-24",
    "(Unaudited) (Unaudited) (Unaudited) (Unaudited) (Unaudited) (AuditP.d)",
    "Revenue from Operations",
    "(a) Interest Income 561.77 647.32 518.69 1,209.09 987.62 2,117.05",
    "I Total revenue from operations 640.36 663.13 584.31 1,303.48 1,071.15 2,299.76",
    "II Other income 19.11 26.20 29.61 45.31 44.70 107.15",
    "VII Profit/ (Loss) after tax IV-VI) (203.93) 51.29 116.32 (152.65) 227.44 467.88"])

SUNDARM_P3 = "\n".join([        # p3, standalone: "f{ in crorest", dates with four-digit years
    "STATEMENT OF AUDITED STANDALONE FINANCIAL RESULTS FOR THE QUARTER AND YEAR ENDED 31.03.2024",
    "f{ in crorest",
    "Quarter Ended Year Ended",
    "Sl.No Particulars 31.03.2024 31.12.2023 31.03.2023 31.03.2024 31.03.2023",
    "Audited Unaudited Audited Audited Audited",
    "12 Revenue from Operations",
    "Interest Income 1241.30 1194.82 921.05 4524.57 3472.07",
    "Total Revenue from Operations 1571.69 1345.76 1054.23 5479.94 4046.17",
    "Other Income (1.23) 5.94 50.96 14.44 63.74"])

CENTRUM_P6 = "\n".join([        # p6, consolidated: "Ct In Lakhs}" (the rupee sign read as Ct, the bracket as a brace)
    "Statement of Audited Consolidated Financials Results for the Quarter and Year Ended March 31, 2024",
    "Ct In Lakhs} (except per equtty share dala}",
    "Quarter Ended Year Ended",
    "Particulars 31-Mar-24 31-Dec-23 31-Mar-23 31-Mar-24 31-Mar-23",
    "Audiled (Unaudited) Audited (Audited) (Audited)",
    "1 Revenue from operations",
    "a. Interest income 50,858.72 44,875.99 31,156.91 1,72,694.87 94,441.54",
    "Total revenue from operations 65,484.55 57,537.82 39,436.25 2,20,681.03 1,31,005.90",
    "Total Income 65,802.24 59,486.80 40,173.34 2,23,866.43 1,36,549.86"])

GARBLED = [(SPANDANA_P4, "Q2FY25", "revenue", "STANDALONE", [640.36]),
           (SPANDANA_P4, "Q2FY25", "pat", "STANDALONE", [-203.93]),
           (SUNDARM_P3, "Q4FY24", "revenue", "STANDALONE", [1571.69]),
           (CENTRUM_P6, "Q4FY24", "revenue", "CONSOLIDATED", [654.8455])]


@pytest.mark.parametrize("page,period,metric,basis,expected", GARBLED, ids=["spandana-rev", "spandana-pat", "sundaram-rev", "centrum-rev"])
def test_a_garbled_unit_line_gives_the_unit_with_the_switch(on, page, period, metric, basis, expected):
    on("PDF_DATES_2DIGIT")
    rows = pr.parse_page(page, 4, True)
    assert vals(rows, period, metric, basis) == []                  # off: "no unit declared above the row"
    assert all(r.unit is None for r in rows)
    on("PDF_ROW_FIXES")
    rows = pr.parse_page(page, 4, True)
    assert vals(rows, period, metric, basis) == expected


@pytest.mark.parametrize("line,per_crore", [
    ('(" in crores unless otherwise stated)', 1), ("f{ in crorest", 1), ("Ct In Lakhs} (except per equtty share dala}", 100),
    ("(~ in crores unless otherwise st ated)", 1), ('(" in lakhs}', 100), ("(f In Lakhs) (except per equity shant data)", 100),
    ("r{ in crores`", 1), ("(₹ in millions)", 10), ("( in thousand)", 10_000)])
def test_the_garbled_unit_lines_of_the_hard_set(line, per_crore):
    assert pr._garbled_unit(["Statement of Results", line, "31.03.2024 31.12.2023"], 2) == per_crore


@pytest.mark.parametrize("line", [
    "(in rupees)", "( in crorepati)", "(in lakhstan)", "in millionaire terms", "(in kg)", "Annexure-1 ( in crores unless otherwise stated)",
    "( in crores 1,200 lakhs)", "Rs. 934 in crores as at 30 September 2024 and total revenues", "", "crores", "( in )"])
def test_a_line_that_is_not_clearly_a_unit_gives_none(line):
    assert pr._garbled_unit(["Statement of Results", line, "31.03.2024 31.12.2023"], 2) is None


def test_two_different_units_near_the_header_give_none(on):
    on("PDF_ROW_FIXES")
    for second in ('(" in lakhs}', "Ct In Lakhs"):         # a garbled line and a bare one, naming another unit: two units are none
        page = SUNDARM_P3.replace("Quarter Ended Year Ended", second + "\nQuarter Ended Year Ended")
        rows = pr.parse_page(page, 3, True)
        assert vals(rows, "Q4FY24", "revenue", "STANDALONE") == []


# --- 2. the basis of a table with its own heading ----------------------------------------------------------------------------

EMKAY_P12 = "\n".join([         # the box at the top of the consolidated "assets and liabilities" page (p12), then that page's title
    "STANDALONE INFORMATION  ( in Lakhs)",
    "Sr.No.  Particulars  Quarter ended  Half Year ended  Year ended",
    "30.09.2024  30.06.2024  30.09.2023  30.09.2024  30.09.2023  31.03.2024",
    "Unaudited  Unaudited  Unaudited  Unaudited  Unaudited  Audited",
    "1  Revenue from Operations  10,068.76  7,569.02  6,349.35  17,628.75  10,373.99  25,209.17",
    "2  Profit before tax  2,970.13  1,644.23  916.59  4,614.36  480.36  3,400.66",
    "3  Profit after tax  2,456.33  1,353.46  749.99  3,809.79  322.00  2,446.99",
    "4  Total Comprehensive Income  2,434.96  1,307.82  748.61  3,742.78  229.03  2,349.36",
    "Notes:",
    "1  CONSOLIDATED UNAUDITED STATEMENT OF ASSETS AND LIABILITIES  (in Lakhs)",
    "Particulars  As at 30.09.2024  As at 31.03.2024",
    "Unaudited  Audited",
    "A  ASSETS", "1  Financial Assets",
    "(a) Cash and cash equivalents  1,464.35  4,782.44",
    "(b) Bank balance other than cash and cash equivalents  56,547.96  53,498.01",
    "(c) Securities held for trading  653.04  129.68",
    "TOTAL - ASSETS  117,097.10  106,526.62"])

EMKAY_GRID = [["STANDALONE INFORMATION", "", "", "", "", "", "( in Lakhs)"],
              ["Sr.No.", "Particulars", "Quarter ended", "", "", "Half Year ended", "", "Year ended"],
              ["", "", "30.09.2024", "30.06.2024", "30.09.2023", "30.09.2024", "30.09.2023", "31.03.2024"],
              ["", "", "Unaudited", "Unaudited", "Unaudited", "Unaudited", "Unaudited", "Audited"],
              ["1", "Revenue from Operations", "10,068.76", "7,569.02", "6,349.35", "17,628.75", "10,373.99", "25,209.17"],
              ["3", "Profit after tax", "2,456.33", "1,353.46", "749.99", "3,809.79", "322.00", "2,446.99"]]


def _emkay_rows():
    layer = prd.page_layer(EMKAY_P12)
    return prd.tables_to_rows([prd.Table("sim", 12, EMKAY_GRID)], {12: layer}, True)


def test_the_standalone_box_on_a_consolidated_page_is_not_read_as_consolidated(on):
    rows = _emkay_rows()
    # off: the table takes the page's title and the box's standalone figures are given as consolidated (the four readers' error)
    assert vals(rows, "Q2FY25", "revenue", "CONSOLIDATED") == [100.6876]
    assert vals(rows, "Q2FY25", "pat", "CONSOLIDATED") == [24.5633]
    on("PDF_ROW_FIXES")
    rows = _emkay_rows()
    assert vals(rows, "Q2FY25", "revenue", "CONSOLIDATED") == []
    assert vals(rows, "Q2FY25", "pat", "CONSOLIDATED") == []
    # the two bases disagree: the table is read on no basis at all, so it gives no standalone figure either
    assert all(r.basis is None for r in rows)
    assert vals(rows, "Q2FY25", "revenue", "STANDALONE") == []


def test_a_heading_that_agrees_with_the_title_changes_nothing(on):
    on("PDF_ROW_FIXES")
    page = "\n".join(["Statement of Standalone Financial Results for the quarter ended 30 September 2024", "STANDALONE INFORMATION  ( in Lakhs)",
                      "Quarter ended  Half Year ended  Year ended",
                      "30.09.2024  30.06.2024  30.09.2023  30.09.2024  30.09.2023  31.03.2024",
                      "1  Revenue from Operations  10,068.76  7,569.02  6,349.35  17,628.75  10,373.99  25,209.17"])
    assert vals(pr.parse_page(page, 5, True), "Q2FY25", "revenue", "STANDALONE") == [100.6876]


def test_a_contested_basis_is_not_defaulted_to_standalone(on):
    on("PDF_ROW_FIXES")
    page = EMKAY_P12.replace("Notes:\n", "").replace("1  CONSOLIDATED UNAUDITED STATEMENT OF ASSETS AND LIABILITIES  (in Lakhs)", "")
    page = "CONSOLIDATED STATEMENT OF RESULTS\n" + page
    rows = pr.parse_page(page, 12, False)           # the caller says no page names "consolidated": the default would be standalone
    assert [r.basis for r in rows if r.metric == "revenue"] == [None]


# --- 3. labels ----------------------------------------------------------------------------------------------------------------

INDOSTAR_P5 = "\n".join([       # p5 (scan; the bold title is lost by OCR, so the basis is the page-less default, standalone)
    "STAEG  E        S    O O2E  (Rs. in Lakhs)",
    "Quarter ended  Half Year ended  Year ended",
    "Sr. No.  Particulars  30 September 2023  30 June 2023  30 September 2022  30 September 2023  30 September 2022  31 March 2023",
    "(Unaudited)  (Unaudited)  (Unaudited)  (Unaudited)  (Unaudited)  (Audited)",
    "1  Income",
    "(a) Revenue from operations",
    "interest income  21,742  22,286  21,760  44,028  45,209  88,947",
    "Fees and commission income  1,101  1,232  1,306  2,333  2,368  4,707",
    "Total revenue from operations  23,418  24,121  23,725  47,539  49,572  96,888",
    "(b) Other income  9  10  10  19  27  437",
    "Total income (a+b)  23,427  24,131  23,735  47,558  49,599  97,325"])

CENTRUM_P14 = "\n".join([       # p14, standalone
    "Statement of Audited Standalone Financials Results for the Quarter and Year Ended March 31, 2024",
    "( in Lakhs) (except per equity share data)",
    "Quarter Ended  Year Ended",
    "Particulars  31-Mar-24  31-Dec-23  31-Mar-23  31-Mar-24  31-Mar-23",
    "(Audited)  (Unaudited)  (Audited)",
    "1.  Revenue from operations",
    "a. Fees and commision Income  1,995.27  1,233.91  1,173.88  4,950.05  2,090.39",
    "b. Net gain on fair value changes  130.17  22.35  371.95",
    "c. Other operating income  100.00  100.00  100.00  400.00  500.00",
    "Total revenue from operations  2,225.44  1,356.26  1,273.88  5,722.00  2,590.39",
    "Other income  975.57  1,010.97  966.43  3,964.84  3,181.38",
    "Total Income  3,201.01  2,367.23  2,240.31  9,686.84  5,771.77"])


def test_a_revenue_heading_is_not_joined_to_its_first_sub_line_indostar(on):
    rows = pr.parse_page(INDOSTAR_P5, 5, False)
    assert vals(rows, "Q2FY24", "revenue", "STANDALONE") == [217.42, 234.18]       # off: a second revenue row, the interest line
    on("PDF_ROW_FIXES")
    rows = pr.parse_page(INDOSTAR_P5, 5, False)
    assert vals(rows, "Q2FY24", "revenue", "STANDALONE") == [234.18]
    assert vals(rows, "FY23", "revenue", "STANDALONE") == [968.88]


def test_a_numbered_revenue_heading_is_not_joined_to_a_lettered_sub_line_centrum(on):
    on("PDF_DATES_2DIGIT")
    rows = pr.parse_page(CENTRUM_P14, 14, False)
    assert vals(rows, "Q4FY24", "revenue", "STANDALONE") == [19.9527, 22.2544]      # off: 19.95 against 22.25, a conflict
    on("PDF_ROW_FIXES")
    rows = pr.parse_page(CENTRUM_P14, 14, False)
    assert vals(rows, "Q4FY24", "revenue", "STANDALONE") == [22.2544]
    assert vals(rows, "FY24", "revenue", "STANDALONE") == [57.22]


def test_a_real_wrapped_revenue_label_is_still_joined(on):
    on("PDF_ROW_FIXES")
    page = "\n".join(["Statement of Standalone Financial Results for the quarter ended 31 March 2024", "(Rs. in Lakhs)",
                      "Quarter ended  Year ended", "31.03.2024  31.12.2023  31.03.2023  31.03.2024  31.03.2023",
                      "Total income from", "operations  1,000.50  900.00  800.00  3,900.00  3,100.00"])
    assert vals(pr.parse_page(page, 3, True), "Q4FY24", "revenue", "STANDALONE") == [10.005]


VLS_P10 = "\n".join([           # p10, standalone: the revenue total is "Total (a)", the income total "Total Income (a+b)"
    "AUDITED STANDALONE FINANCIAL RESULTS FOR THE QUARTER AND YEAR ENDED 31ST-MAR-2024",
    "(Rs.in Lakhs except Earning per share data)",
    "Standalone",
    "Quarter Ended  Year Ended",
    "S No  Particulars  31st-Mar-2024  31-Dec-2023  31-Mar-2023  31st-Mar-2024  31st Mar-2023",
    "Audited  Unaudited  Audited  Audited  Audited",
    "1  Income",
    "(a) Revenue from Operations",
    "(i) Interest Income  381.16  381.28  340.05  1,401.31  1,084.12",
    "(ii) Dividend Income  176.99  164.23  109.34  1,200.05  1,000.86",
    "(ii) Net gain on fair value changes  9,195.88  10,696.76  (2,001.93)  37,370.42  5,421.86",
    "(iv) Other Operating Income  - - - 17.65 64.50",
    "Total (a)  9,754.03  11,242.27  (1,552.54)  39,989.43  7,571.34",
    "(b) Other Income  240.00  143.82  124.99  1,019.72  153.77",
    "Total (b)  240.00  143.82  124.99  1,019.72  153.77",
    "Total Income (a+b)  9,994.03  11,386.09  (1,427.55)  41,009.15  7,725.11",
    "2  Expenses",
    "7  Profit for the Period (5+6)  7,416.87  8,786.96  (1,550.28)  32,021.99  5,244.00"])


def test_the_total_of_a_revenue_heading_is_the_revenue_not_total_income_vls(on):
    rows = pr.parse_page(VLS_P10, 10, True)
    assert vals(rows, "Q4FY24", "revenue", "STANDALONE") == [99.9403]      # off: "Total Income (a+b)", which includes other income
    on("PDF_ROW_FIXES")
    rows = pr.parse_page(VLS_P10, 10, True)
    assert vals(rows, "Q4FY24", "revenue", "STANDALONE") == [97.5403]      # key: 9,754.03 lakh
    assert vals(rows, "FY24", "revenue", "STANDALONE") == [399.8943]
    assert vals(rows, "Q4FY23", "revenue", "STANDALONE") == [-15.5254]
    assert not any(pr._TOTAL_INCOME.search(r.label) for r in rows if r.metric == "revenue")


def test_total_b_is_not_a_revenue_total(on):
    on("PDF_ROW_FIXES")
    page = VLS_P10.replace("Total (a)  9,754.03", "Subtotal  9,754.03").replace("Total (b)", "Total (a)")
    rows = pr.parse_page(page, 10, True)
    # "Total (a)" now stands under "(b) Other Income", after a "(b)" step: not the revenue total, so only total income is left
    assert vals(rows, "Q4FY24", "revenue", "STANDALONE") == []


UNION_P3 = "\n".join([          # p3, OCR of the standalone page: lettered lines, "Interest Earned" over a figure line
    "Standalone Unaudited Financlal Results for the Quarter & Nine Months ended 31\" December 2024",
    "( In Lakh)",
    "Standalone",
    "Quarter Ended  Nine Months Ended  Year Ended",
    "Particulars  31.12.2024  30.09.2024  31.12.2023  31.12.2024  31.12.2023  31.03.2024",
    "(Unaudited)  (Unaudited)  (Unaudited)  (Unaudited)  (Unaudited)  (Audited)",
    "1  Interest Earned",
    "(a) + (b) + (c) + (d)  26,95,793  26,70,843  25,36,296  80,03,075  73,42,786  99,77,796",
    "2  Other Income  4,41,657  5,32,803  3,77,430  14,25,383  11,37,277  16,08,019",
    "A.  TOTAL INCOME (1+2)  31,37,450  32,03,646  29,13,726  94,28,458  84,80,063  1,15,85,815",
    "I.  Extraordinary items (net of tax expense)",
    "J.  Net Profit/(Loss) for the period (H-I)  4,60,363  4,71,974  3,58,991  13,00,222  10,33,776  13,64,831"])


def test_a_lettered_profit_label_is_read_and_total_income_is_not_revenue_union_bank(on):
    rows = pr.parse_page(UNION_P3, 3, False)
    assert vals(rows, "Q3FY25", "pat", "STANDALONE") == []                   # off: "J." is not a prefix the label matcher knows
    assert vals(rows, "Q3FY25", "revenue", "STANDALONE") == [31374.5]        # off: "A. TOTAL INCOME" as the revenue (wrong)
    on("PDF_ROW_FIXES")
    rows = pr.parse_page(UNION_P3, 3, False)
    assert vals(rows, "Q3FY25", "pat", "STANDALONE") == [4603.63]            # key: 4,60,363 lakh
    assert vals(rows, "Q3FY25", "revenue", "STANDALONE") == []               # total income is not revenue: no figure, never a guess


@pytest.mark.parametrize("label", ["J. Net Profit/(Loss) for the period (H-I)", "iii. Profit for the period (1-2)",
                                   "H. Profit after tax (F-G)", "(c) Net profit for the year (a-b)", "IX Profit/(Loss) for the period"])
def test_letter_or_roman_prefixes_before_the_profit_label(on, label):
    on("PDF_ROW_FIXES")
    assert pr._PAT_NAME_LETTERED.search(label) and not pr._PAT_NOT.search(label)


@pytest.mark.parametrize("label", ["J. Profit before tax", "Profit before tax (3-4)", "K. Other comprehensive income for the period",
                                   "Earnings per share for the period"])
def test_the_prefix_does_not_let_other_lines_in(label):
    assert not (pr._PAT_NAME_LETTERED.search(label) and not pr._PAT_NOT.search(label))


AIIL_HEAD = ["Statement of Audited Standalone Financial Results for the Quarter and Year Ended March 31, 2024", "(Rs In Crores)",
             "Particulars Quarter Ended Year Ended Vear Ended",
             "No. 31.03.2024 31.12.2023 31.03.2023 31.03.2024 31.03.2023",
             "(Audited) {Unaudited) (Audited) (Audited) (Audited)", "Income:"]


def test_total_income_is_not_revenue_when_the_revenue_heading_lost_its_figures_aiil(on):
    # a table reader that left the revenue row's cells empty: only "Other Income" and "Total Income" carry figures
    page = "\n".join(AIIL_HEAD + ["Revenue from operations", "Other Income 17.10 1.58 0.91 21.08 3.13",
                                  "Total Income 903.11 493.11 (117.23) 2,433.09 377.36"])
    rows = pr.parse_page(page, 17, True)
    assert vals(rows, "Q4FY24", "revenue", "STANDALONE") == [903.11]          # off: "Total Income" given as revenue (wrong: 886.01)
    on("PDF_ROW_FIXES")
    rows = pr.parse_page(page, 17, True)
    assert vals(rows, "Q4FY24", "revenue", "STANDALONE") == []


def test_total_income_is_not_revenue_when_a_revenue_row_is_on_the_page_aiil(on):
    # the date header printed again between the two rows (a reader that splits the table): two tables, two keys
    again = ["Particulars Quarter Ended Year Ended Vear Ended", "No. 31.03.2024 31.12.2023 31.03.2023 31.03.2024 31.03.2023"]
    page = "\n".join(AIIL_HEAD + ["Revenue from operations 886.01 491.53 (118.14) 2,412.01 374.22",
                                  "Other Income 17.10 1.58 0.91 21.08 3.13"] + again
                     + ["Total Income 903.11 493.11 (117.23) 2,433.09 377.36"])
    rows = pr.parse_page(page, 17, True)
    assert sorted(vals(rows, "Q4FY24", "revenue", "STANDALONE")) == [886.01, 903.11]      # off: two figures (a conflict, or the wrong one)
    on("PDF_ROW_FIXES")
    rows = pr.parse_page(page, 17, True)
    assert vals(rows, "Q4FY24", "revenue", "STANDALONE") == [886.01]


def test_total_income_still_stands_when_nothing_else_is_printed(on):
    on("PDF_ROW_FIXES")
    page = "\n".join(AIIL_HEAD + ["Other Income 17.10 1.58 0.91 21.08 3.13", "Total Income 903.11 493.11 (117.23) 2,433.09 377.36"])
    rows = pr.parse_page(page, 17, True)
    assert vals(rows, "Q4FY24", "revenue", "STANDALONE") == [903.11]    # as before: reading_of and the referee's verdict treat it as no revenue


SPANDANA_P12 = "\n".join([      # p12, consolidated: the profit after tax (VII) and, after the non-controlling share, the owners' profit (IX)
    "Statement of Unaudited Consolidated Financial Results for the Quarter and Half Year ended September 30, 2024",
    "( in crores unless otherwise stated)",
    "Quarter ended  Half year ended  Year ended",
    "Sr.No.Particulars  30-Sep-24  30-Jun-24  30-Sep-23  30-Sep-24  30-Sep-23  31-Mar-24",
    "(Unaudited)  (Unaudited)  (Unaudited)  (Unaudited)  (Unaudited)  (Audited)",
    "I  Total revenue from operations  686.38  709.89  610.27  1,396.27  1,121.87  2,423.71",
    "VII  Profit / (Loss) after tax (V-VI)  (216.33)  55.71  125.21  (160.62)  244.67  500.72",
    "VIII  Profit / (loss) attributable to Non controlling interest  (0.01)  0.00  0.01  (0.01)  0.03  0.06",
    "IX  Profit / (Loss) for the period / year (VII-VIII)  (216.32)  55.71  125.20  (160.61)  244.64  500.66"])


def test_a_for_the_period_line_that_is_the_line_above_less_another_is_no_tie_break(on):
    on("PDF_DATES_2DIGIT", "PDF_ROW_FIXES")
    page = SPANDANA_P12.replace("( in crores unless otherwise stated)", "(Rs. in crores)")      # a clean unit: only the tie-break is tested
    rows = pr.parse_page(page, 12, True)
    # VII and IX differ by the non-controlling share (0.01, 0.01, 0.06): which is the profit is not told, so two values stay
    # (before: the tie-break took IX, the owners' profit, 216.32 against the key's 216.33)
    assert vals(rows, "Q2FY25", "pat", "CONSOLIDATED") == [-216.33, -216.32]
    assert vals(rows, "FY24", "pat", "CONSOLIDATED") == [500.72, 500.66]
    assert vals(rows, "Q1FY25", "pat", "CONSOLIDATED") == [55.71, 55.71]       # where they agree it is read
    assert vals(rows, "Q2FY25", "revenue", "CONSOLIDATED") == [686.38]


GEOJIT_PAGE = "\n".join([
    "Statement of Consolidated Unaudited Financial Results for the quarter and half year ended 30 September 2023", "(Rs. in lakhs)",
    "Quarter ended  Half year ended  Year ended",
    "30.09.2023  30.06.2023  30.09.2022  30.09.2023  30.09.2022  31.03.2023",
    "7  Profit after tax (5-6)  3621.80  2087.22  2269.29  5709.02  4392.41  9645.61",
    "9  Profit for the period / year (7+8)  3747.66  2207.84  2376.13  5955.50  4577.76  10096.32",
    "Profit attributable to owners  3600.00  2100.00  2300.00  5700.00  4400.00  9600.00"])


def test_a_for_the_period_line_that_adds_a_later_line_is_still_the_tie_break(on):
    on("PDF_ROW_FIXES")
    rows = pr.parse_page(GEOJIT_PAGE, 4, True)       # "9 Profit for the period / year (7+8)": the bottom line, after associates
    assert vals(rows, "Q1FY24", "pat", "CONSOLIDATED") == [22.0784]
