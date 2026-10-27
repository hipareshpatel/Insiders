"""F215: the PDF page and row matcher fixes from the hard-set root cause. Texts are the real pages' lines (NSE_25042024,
SE_28102024, BFIL, SignedFinancialResults, Authum, Financials_Dec_Quick_Results, Geojit, Prime Securities); each fix is
behind its own switch, off by default, and the off path is the old behaviour."""

from __future__ import annotations

from datetime import date

import pytest

from bse_intel import pdf_bench as pb
from bse_intel import pdf_readers as prd
from bse_intel import pdf_referee as pr
from bse_intel.periods import explicit_date
from bse_intel.settings import Settings, get_settings


@pytest.fixture
def on(monkeypatch):
    def _set(*names):
        for n in names:
            monkeypatch.setenv(n, "1")
        get_settings.cache_clear()
    return _set


# --- 1. two-digit-year dates -----------------------------------------------------------------------------------------

HEADER_YY = "Particulars  31-Mar-24  31-Dec-23  31-Mar-23  31-Mar-24  31-Mar-23"


def test_switches_default_off():
    s = Settings()
    assert (s.pdf_dates_2digit, s.pdf_page_rank, s.pdf_row_fixes) == (False, False, False)


def test_two_digit_years_are_off_by_default_everywhere(on):
    assert explicit_date("31-Mar-24") is None
    assert pr._dates_in(HEADER_YY) == []


def test_two_digit_years_read_in_the_referee_and_readers_only_when_asked(on):
    on("PDF_DATES_2DIGIT")
    assert [d.isoformat() for d in pr._dates_in(HEADER_YY)] == ["2024-03-31", "2023-12-31", "2023-03-31", "2024-03-31", "2023-03-31"]
    assert [d.isoformat() for d in pr._dates_in("-31Mar-23  31-Dec-22")] == ["2023-03-31", "2022-12-31"]   # SignedFinancialResults p10
    assert [d.isoformat() for d in pr._dates_in("30 September 24  30 June 24")] == ["2024-09-30", "2024-06-30"]
    # the live path (periods.explicit_date) never gets the two-digit year unless the caller asks
    assert explicit_date("31-Mar-24") is None and explicit_date("31-Mar-24", two_digit=True) == date(2024, 3, 31)
    assert explicit_date("31.03.24", two_digit=True) == date(2024, 3, 31)


def test_two_digit_years_need_a_day_and_a_month_and_never_make_false_dates(on):
    on("PDF_DATES_2DIGIT")
    for text in ("Rs 31-24", "Rs. 31-24 crore", "1,234.56-78.90", "12-45", "Note 31 Mar", "Mar-24", "31-Mar-99 and 99-99-24",
                 "31.03.20 24"):                 # the last: Authum's year split by a space is not 2020
        assert not any(d.year in (2020, 2099) for d in pr._dates_in(text)) or text.startswith("31-Mar-99"), text
    assert pr._dates_in("Rs 31-24") == [] and pr._dates_in("Mar-24") == [] and pr._dates_in("1,234.56-78.90") == []
    assert explicit_date("Rs 31-24", two_digit=True) is None and explicit_date("31-Mar-99", two_digit=True) is None
    assert explicit_date("31.03.20 24", two_digit=True) is None
    assert pr._dates_in("31-Mar-20  31-Dec-19")[0] == date(2020, 3, 31)


STATEMENT_YY = "\n".join([
    "Statement of Standalone Financial Results for the Quarter and Year ended March 31, 2024", "(Rs. in Lakhs)",
    "Particulars  Quarter ended  Year ended", HEADER_YY, "Revenue from operations  1,136  1,629  1,064  6,151  4,054",
    "Profit for the period  500  400  300  1,500  1,200"])


def test_a_page_with_two_digit_dates_gives_its_row_only_with_the_switch(on):
    assert pr.parse_page(STATEMENT_YY, 8, False) == [] or all(r.columns is None for r in pr.parse_page(STATEMENT_YY, 8, False))
    on("PDF_DATES_2DIGIT")
    got = pr.figure_for(pr.parse_page(STATEMENT_YY, 8, False), "Q4FY24", "revenue", "STANDALONE")
    assert [round(v, 4) for v, _, _ in got["values"]] == [11.36]       # NSE_25042024: 1,136 lakh = 11.36 crore


def test_statement_pages_keep_a_two_digit_year_page(on):
    layers = {1: prd.page_layer("Cover letter, no results here " * 3), 2: prd.page_layer(STATEMENT_YY + " " * 60)}
    assert prd.statement_pages(layers) == []
    on("PDF_DATES_2DIGIT")
    assert prd.statement_pages(layers) == [2]


# --- 2. split date headers and 3-metric pages -------------------------------------------------------------------------

BFIL_PAGE = "\n".join([
    "Statement of Standalone Unaudited Financial Results for the quarter and half year ended September 30, 2024", "(Rs. in million)",
    "Particulars", "Quarter ended", "September 30,", "2024", "June 30,", "2024", "September 30,", "2023",
    "Revenue from operations  1,000.5  900.2  800.1", "Profit for the period  100.5  90.2  80.1",
    "Basic earnings per share  1.5  1.2  1.0"]) + "\n" + "x" * 60


def test_a_header_split_over_lines_passes_the_page_gate_only_with_the_switch(on):
    layers = {1: prd.page_layer(BFIL_PAGE)}
    assert prd.statement_pages(layers) == []
    on("PDF_PAGE_RANK")
    assert prd.statement_pages(layers) == [1]


def test_a_cover_letter_naming_the_quarter_twice_is_not_a_results_page(on):
    on("PDF_PAGE_RANK")
    letter = ("Outcome of the Board Meeting: financial results for the quarter ended September 30, 2024 were approved. "
              "The results for the quarter ended\nSeptember 30, 2024 are enclosed.\n" + "x" * 60)
    assert prd.statement_pages({1: prd.page_layer(letter)}) == []


def test_three_metric_kinds_under_a_results_heading_pass_without_a_two_date_line(on):
    text = "\n".join(["Statement of Audited Financial Results for the year ended", "(in crore)",
                      "Revenue from operations  100.5  90.2", "Profit for the period  10.5  9.2",
                      "Basic earnings per share  1.5  1.2", "x" * 60])
    layers = {1: prd.page_layer(text)}
    assert prd.statement_pages(layers) == []
    on("PDF_PAGE_RANK")
    assert prd.statement_pages(layers) == [1]


def test_dates_each_on_a_line_of_their_own_pass_the_gate(on):
    text = "\n".join(["Statement of standalone financial results for the quarter and year ended March 31, 2023", "(in crore)",
                      "Quarter ended", "Year ended", "S.no. Particulars", "-31Mar-23", "31-Dec-22", "31-Mar-22", "31-Mar-23",
                      "31-Mar-22", "Revenue from operations", "t)", "Interest income", "1,580.59", "x" * 60])
    layers = {10: prd.page_layer(text)}
    on("PDF_PAGE_RANK")
    assert prd.statement_pages(layers) == []             # two-digit years still off
    on("PDF_DATES_2DIGIT")
    assert prd.statement_pages(layers) == [10]


# --- 3. page ranking and the scan limit -------------------------------------------------------------------------------

def _results(kinds_rows: bool = True, segment: bool = False) -> str:
    head = "Statement of Segment wise Revenue Results and Capital Employed for the quarter ended\n" if segment else \
        "Statement of Standalone Financial Results for the quarter ended 30 September 2026\n"
    rows = "Revenue from operations  100.5  90.2\nProfit for the period  10.5  9.2\nBasic earnings per share  1.5  1.2\n" if kinds_rows else ""
    return head + "(Rs. in crore)\n30 September 2026  30 September 2025\n" + rows + "x" * 60


def test_a_results_page_ranks_above_a_segment_page(on):
    pages = {1: _results(False, True), 2: _results(False, True), 3: _results(False, True), 4: _results(False, True),
             5: _results(False, False)}
    layers = {n: prd.page_layer(t) for n, t in pages.items()}
    assert 5 not in prd.statement_pages(layers)             # old order: ties go to the first four pages
    on("PDF_PAGE_RANK")
    assert 5 in prd.statement_pages(layers)


def test_scanned_pdfs_up_to_thirty_pages_are_searched_with_the_switch(on):
    layers = {n: prd.page_layer("") for n in range(1, 27)}      # ABCAPITAL: 26 pages, no text layer
    assert prd.statement_pages(layers) == []
    on("PDF_PAGE_RANK")
    assert prd.statement_pages(layers) == [1, 2, 3, 4]          # never more than MAX_PAGES pages are handed on
    assert prd.statement_pages({n: prd.page_layer("") for n in range(1, 40)}) == []


# --- 4. rows ------------------------------------------------------------------------------------------------------------

JK_PAGE = "\n".join([
    "CONSOLIDATED FINANCIAL RESULTS FOR THE QUARTER AND NINE MONTHS ENDED 31ST DECEMBER, 2023", "(Rs. in Crores)",
    "QUARTER ENDED   NINE MONTHS ENDED   YEAR ENDED",
    "31.12.2023  30.09.2023  31.12.2022  31.12.2023  31.12.2022  31 .03.202]",
    "Interest Earned (a+b+c+d}  2881.20  2764.44  2440.87  8302.85  8842.93  9356.23"])


def test_an_extra_trailing_figure_whose_header_date_the_layer_garbled_is_read_by_position(on):
    off = pr.parse_page(JK_PAGE, 11, True)
    assert off[0].columns is None and "6 figures" in off[0].why
    on("PDF_ROW_FIXES")
    row = pr.parse_page(JK_PAGE, 11, True)[0]
    assert row.columns is not None and len(row.dates) == 6
    assert (row.columns[0][1], row.columns[1][1]) == (date(2023, 12, 31), date(2023, 9, 30))
    assert row.dates[5] == date(2023, 3, 31)     # the six-column layout and the token's "202" agree
    got = pr.figure_for([row], "Q3FY24", "revenue", "CONSOLIDATED")
    assert [round(v, 4) for v, _, _ in got["values"]] == [2881.2]
    assert [round(v, 4) for v, _, _ in pr.figure_for([row], "FY23", "revenue", "CONSOLIDATED")["values"]] == [9356.23]


def test_an_extra_figure_with_no_date_token_to_match_stays_unread(on):
    on("PDF_ROW_FIXES")
    page = JK_PAGE.replace("31.12.2022  31 .03.202]", "31.12.2022")        # five date tokens, six figures: a sub-total, say
    row = pr.parse_page(page, 11, True)[0]
    assert row.columns is None and "6 figures" in row.why
    odd = JK_PAGE.replace("31 .03.202]", "30 .06.202]")                  # a sixth token that is not the layout's year end
    assert pr.parse_page(odd, 11, True)[0].columns is None


GEOJIT_PAGE = "\n".join([
    "Statement of Consolidated Unaudited Financial Results for the quarter and half year ended 30 September 2023", "(Rs. in lakhs)",
    "Quarter ended  Half year ended  Year ended",
    "30.09.2023  30.06.2023  30.09.2022  30.09.2023  30.09.2022  31.03.2023",
    "7  Profit after tax (5-6)  3621.80  2087.22  2269.29  5709.02  4392.41  9645.61",
    "9  Profit for the period / year (7+8)  3747.66  2207.84  2376.13  5955.50  4577.76  10096.32",
    "Profit attributable to owners  3600.00  2100.00  2300.00  5700.00  4400.00  9600.00"])


def test_the_total_profit_row_wins_over_the_step_above_it_with_the_switch(on):
    rows = pr.parse_page(GEOJIT_PAGE, 4, True)
    assert len({round(v, 4) for v, _, _ in pr.figure_for(rows, "Q1FY24", "pat", "CONSOLIDATED")["values"]}) == 2
    on("PDF_ROW_FIXES")
    got = pr.figure_for(rows, "Q1FY24", "pat", "CONSOLIDATED")
    assert [round(v, 4) for v, _, _ in got["values"]] == [22.0784]         # GEOJITFSL Q1FY24 22.08 crore


def test_two_unlabelled_totals_that_differ_are_still_a_conflict(on):
    on("PDF_ROW_FIXES")
    page = GEOJIT_PAGE.replace("9  Profit for the period / year (7+8)", "9  Net profit after tax")
    got = pr.figure_for(pr.parse_page(page, 4, True), "Q1FY24", "pat", "CONSOLIDATED")
    assert len({round(v, 4) for v, _, _ in got["values"]}) == 2


def test_a_table_with_only_total_income_gives_no_revenue_reading_with_the_switch(on):
    page = "\n".join(["Statement of Consolidated Financial Results for the quarter ended 31 March 2024", "(Rs. in Lakhs)",
                      "Quarter ended  Year ended", "31-Mar-24  31-Dec-23  31-Mar-23  31-Mar-24  31-Mar-23",
                      "III  Total income (I+II)  1,282  1,791  1,243  6,664  4,684"])
    rows = pr.parse_page(page.replace("31-Mar-24", "31.03.2024").replace("31-Dec-23", "31.12.2023").replace("31-Mar-23", "31.03.2023"),
                         8, True)

    class Reader:
        name, family, ocr_family = "r", "f", "o"

    old = prd.reading_of(Reader, rows, {}, "Q4FY24", "revenue", "CONSOLIDATED")
    assert old.status == "ok" and old.value == 12.82               # PRIMESECU: wrong against the 11.36 revenue from operations
    on("PDF_ROW_FIXES")
    new = prd.reading_of(Reader, rows, {}, "Q4FY24", "revenue", "CONSOLIDATED")
    assert new.status == "none" and "Total income" in new.note


# --- 5. the bench keeps the reason and the page, and scores scan-only rows apart ---------------------------------------------

def test_answer_pair_stores_the_note_and_page_and_scores_scan_only_rows_apart():
    class FakeEnsemble:
        names = ["native"]

        def readings(self, key, payload, period, metric, basis):
            return [prd.Reading("native", "pymupdf", "none", note="p3: no unit declared above the row", page=0),
                    ]

    pair = {"symbol": "X", "period": "Q4FY24", "metric": "revenue", "basis": "STANDALONE", "pdf_url": "u", "expected": 5.0,
            "tags": ["scanned_no_text_layer"]}
    got = pb.answer_pair(FakeEnsemble(), b"%PDF", pair)
    assert got["readers"]["native"]["note"] == "p3: no unit declared above the row" and "page" in got["readers"]["native"]
    text_pair = {**pair, "tags": ["lender"]}
    ok = pb.answer_pair(type("E", (), {"names": ["native"], "readings": lambda *a: [
        prd.Reading("native", "pymupdf", "ok", 5.0, True, True, "textlayer", "Revenue", 7)]})(), b"%PDF", text_pair)
    assert ok["readers"]["native"]["page"] == 7
    s = pb.score([got, ok])
    assert s["by_layer"]["scan_only"]["native"] == {"right": 0, "wrong": 0, "abstain": 1}
    assert s["by_layer"]["text_layer"]["native"] == {"right": 1, "wrong": 0, "abstain": 0}
    assert s["readers"]["native"] == {"right": 1, "wrong": 0, "abstain": 1}
    assert "Scan-only rows" in pb.to_markdown(s)
