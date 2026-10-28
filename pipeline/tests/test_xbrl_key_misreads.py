"""The locator's misreads found by checking the first live xbrl-key run's 28 "row found, other value" figures against their PDFs
(28 Oct 2026): figures a text layer cut in two words, a header month with a comma after it, a discontinued business's own
exceptional item and tax taken for the company's, a decimal point lost. Pages are made in the test with PyMuPDF."""

from __future__ import annotations

import pymupdf

from bse_intel import xbrl_key as xk
from test_xbrl_key import COLS, DATES, FILLER, Canvas, exp, one


def _page(rows, dates=DATES, unit="(Rs. in crore)", gap=1.0, headings=True, pad=True):
    """A results statement whose figures may be drawn in pieces: a figure given as a tuple of strings is drawn as separate words
    ``gap`` points apart (the way a text layer cuts "12,314.66" into "12,31" and "4.66")."""
    doc = pymupdf.open()
    c = Canvas(doc)
    rows = [*rows, *FILLER] if pad else rows
    c.text(20, 40, "Statement of Consolidated Unaudited Financial Results for the quarter ended 30 September 2026")
    c.text(20, 56, unit)
    if headings:
        c.text(sum(COLS[:3]) / 3 - 30, 76, "Quarter ended")
        c.text(COLS[3] - 22, 76, "Year ended")
    c.text(20, 90, "Particulars")
    for x, d in zip(COLS, dates):
        c.text(x - 22, 90, d)
    y = 110.0
    for label, figures in rows:
        c.text(20, y, label)
        for x, f in zip(COLS, figures):
            pieces = f if isinstance(f, tuple) else (f,)
            end = x + 25
            for piece in reversed(pieces):
                c.text(end, y, piece, right=True)
                end -= pymupdf.get_text_length(piece, fontsize=8) + gap
        y += 14
    return doc.tobytes()


def _statement(first_total_expenses, **kw):
    return _page([("1 Revenue from operations", ["100.00", "95.00", "80.00", "380.00"]),
                  ("4 Total expenses", [first_total_expenses, "15,492.83", "10,920.53", "51,459.29"])], **kw)


# --- figures cut in two words -----------------------------------------------------------------------------------------

def test_a_figure_cut_inside_its_last_group_is_put_back_ashok_leyland():
    """Ashok Leyland's Q1FY27 text layer: "12,31" and "4.66" for 12,314.66, and "51" ",459.29" for 51,459.29. Read alone, 12,31 is
    12.31, which the key reported as the printed figure."""
    pdf = _statement(("12,31", "4.66"))
    r = one(pdf, exp("total_expenses", 12314.66, "Q2FY27", "CONSOLIDATED"))
    assert r.status == "found_unique" and r.printed_text == "12,314.66" and r.printed_value == 12314.66
    # the year figure drawn as the layer has it: its own comma on the next word

    cut = _page([("1 Revenue from operations", ["100.00", "95.00", "80.00", "380.00"]),
                 ("4 Total expenses", ["12,314.66", "15,492.83", "10,920.53", ("51", ",459.29")])])
    assert one(cut, exp("total_expenses", 51459.29, "FY26", "CONSOLIDATED")).status == "found_unique"


def test_a_thousands_separator_lost_between_two_words_is_put_back_kirloskar_and_wework():
    """Kirloskar Brothers' "10" "246" (10,246 million) and WeWork's "7" "864.39" (7,864.39 million)."""
    for text, value in ((("10", "246"), 10246.0), (("7", "864.39"), 7864.39)):
        r = one(_statement(text), exp("total_expenses", value, "Q2FY27", "CONSOLIDATED"))
        assert r.status == "found_unique", text
        assert r.printed_value == value


def test_a_decimal_point_split_off_is_put_back():
    """BlueStar "(1" ".73)" is (1.73); "41" ".12" is 41.12."""
    for pieces, value in ((("(1", ".73)"), -1.73), (("41", ".12"), 41.12), (("(0.", "13)"), -0.13)):
        pdf = _page([("1 Revenue from operations", ["100.00", "95.00", "80.00", "380.00"]),
                     ("4 Total expenses", [pieces, "15.00", "10.00", "51.00"])])
        r = one(pdf, exp("total_expenses", value, "Q2FY27", "CONSOLIDATED"))
        assert r.status == "found_unique" and r.printed_value == value, pieces


def test_two_figures_in_different_columns_are_never_joined():
    """Only words a space apart are one figure: the same two pieces drawn in their own columns stay two figures."""
    for gap in (6.0, 15.0):
        pdf = _statement(("10", "246"), gap=gap)
        assert one(pdf, exp("total_expenses", 10246.0, "Q2FY27", "CONSOLIDATED")).status != "found_unique", gap


def test_a_lone_line_number_is_not_joined_to_the_figure_after_it():
    """A line number ("2.", "(a)", "iv") with no label word before it, then a figure: "2." "123" is two things, not 2.123."""
    row = [xk.Word(20, 0, 26, 8, "2."), xk.Word(27, 0, 40, 8, "123")]
    assert [w.text for w in xk._mend_numbers(row)] == ["2.", "123"]
    figs, rest = xk.figures_in(row)
    assert [f.num.value for f in figs] == [123.0] and [w.text for w in rest] == ["2."]
    for numbering in ("(a)", "iv", "(2)", "ii."):
        assert [w.text for w in xk._mend_numbers([xk.Word(20, 0, 28, 8, numbering), xk.Word(29, 0, 42, 8, "123")])] \
            == [numbering, "123"], numbering
    labelled = [xk.Word(0, 0, 25, 8, "Total"), xk.Word(30, 0, 36, 8, "2."), xk.Word(37, 0, 50, 8, "123")]
    assert [w.text for w in xk._mend_numbers(labelled)] == ["Total", "2.123"], "after a label word, a cut decimal is still mended"


def test_the_mender_joins_only_what_is_a_number_as_printed():
    words = [xk.Word(0, 0, 10, 8, "10"), xk.Word(13, 0, 28, 8, "246"), xk.Word(100, 0, 110, 8, "7"), xk.Word(112, 0, 130, 8, "86")]
    joined = xk._mend_numbers(words)
    assert [w.text for w in joined] == ["10,246", "7", "86"], "7 and 86 are not a grouped number"
    cut = [xk.Word(0, 0, 25, 8, "12,31"), xk.Word(26, 0, 40, 8, "45")]
    assert [w.text for w in xk._mend_numbers(cut)] == ["12,31", "45"], "12,3145 is not grouped"
    assert xk.parse_number("12,31").value == 12.31   # why a cut group was read as a figure of its own


# --- header dates with a comma after the month --------------------------------------------------------------------------

def test_a_header_month_with_a_comma_is_a_date_styrenix():
    """Styrenix heads its columns "Jun, 30 2026", "Mar, 31 2026": the comma stopped the date reader, and two of the four columns
    were not columns, so the year-ago column (misread "2026" by the page's text layer) became the quarter."""
    dates = ("Jun, 30 2026", "Mar, 31 2026", "Jun 30, 2025", "Mar 31, 2026")
    pdf = _page([("1 Revenue from operations", ["1,010.86", "826.10", "943.50", "3,438.03"])], dates=dates)
    r = one(pdf, exp("revenue", 1010.86, "Q1FY27", "CONSOLIDATED"))
    assert r.status == "found_unique" and r.column_header == "Quarter ended > 30.06.2026" and r.printed_text == "1,010.86"


def test_two_columns_with_the_same_date_prove_nothing():
    """The same page with the year-ago column's text layer reading 2026 too: two columns of one table dated 30.06.2026. The
    figure of the right one is placed, not proven; a stale file that prints the year-ago figure cannot pass as the quarter's."""
    dates = ("Jun, 30 2026", "Mar, 31 2026", "Jun, 30 2026", "Mar, 31 2026")
    pdf = _page([("1 Revenue from operations", ["1,010.86", "826.10", "943.50", "3,438.03"])], dates=dates)
    for value in (1010.86, 943.50):
        r = one(pdf, exp("revenue", value, "Q1FY27", "CONSOLIDATED"))
        assert r.status == "found_ambiguous", value
        assert "date repeated" in r.column_header or any("date repeated" in p["column"] for p in r.placements)
    stale = one(pdf, exp("revenue", 999.0, "Q1FY27", "CONSOLIDATED"))
    assert stale.status == "not_found", "no proven column to name a row in"


def test_a_month_comma_is_taken_off_only_a_month():
    words = [xk.Word(0, 0, 20, 8, "Jun,"), xk.Word(22, 0, 30, 8, "30"), xk.Word(32, 0, 50, 8, "Total,"), xk.Word(52, 0, 60, 8, "Mar.,")]
    assert [w.text for w in xk._month_commas(words)] == ["Jun", "30", "Total,", "Mar."]


# --- a discontinued business's exceptional item and tax ----------------------------------------------------------------

def test_the_discontinued_business_exceptional_item_and_tax_are_not_the_continuing_ones_aditya_birla_real_estate():
    """ABREL's Q2FY27 file has exceptional items 0 and tax 21.67 (continuing operations); the page prints another exceptional item
    (868.12, the gain on the pulp and paper sale) and tax ((73.40)) under its DISCONTINUED OPERATIONS heading."""
    rows = [("1 Income from operations", ["63.66", "62.84", "67.04", "259.79"]),
            ("6 Exceptional items", ["-", "-", "-", "(19.84)"]),
            ("7 Profit before tax", ["84.92", "41.72", "37.70", "121.38"]),
            ("8 Tax expenses of continuing operations", ["", "", "", ""]),
            ("Current Tax", ["12.99", "1.78", "6.73", "26.85"]),
            ("10 DISCONTINUED OPERATIONS", ["", "", "", ""]),
            ("11 Profit before tax from discontinued operations", ["(19.33)", "42.59", "86.19", "240.15"]),
            ("12 Exceptional items (Refer note 2b and 3)", ["868.12", "-", "868.12", "(29.89)"]),
            ("13 Total tax expenses", ["(73.38)", "(10.24)", "(30.69)", "10.97"]),
            ("14 Net Profit for the period from discontinued operations", ["775.39", "32.37", "55.28", "223.25"])]
    pdf = _page(rows)

    def want(metric, value):
        return xk.Expected("n", "X", "CONSOLIDATED", "Q2FY27", metric, value)

    assert one(pdf, want("exceptional_items", 0.0)).status == "not_found", "the 868.12 is not the continuing exceptional item"
    gain = one(pdf, want("exceptional_items", 868.12))
    assert gain.status == "found_ambiguous" and gain.reason == "not_row", "printed, but not on a row that is the company's"
    tax = one(pdf, want("tax_expense", -73.38))
    assert tax.status == "found_ambiguous" and tax.reason == "not_row"
    assert one(pdf, want("pbt", 84.92)).status == "found_unique", "what comes before the section is untouched"


def test_the_section_ends_at_the_next_continuing_heading():
    assert xk._in_discontinued("DISCONTINUED OPERATIONS", False)
    assert xk._in_discontinued("Net Profit for the period", True), "no word of either kind: the section goes on"
    assert not xk._in_discontinued("(a) Other comprehensive income - continuing operations", True)
    assert not xk._in_discontinued("Profit from continuing and discontinued operations", False)
    assert not xk._in_discontinued("Net profit from continuing operations (9-10)", True)
    assert xk._in_discontinued("Profit/(loss) before tax from discontinued operations", False)


# --- a decimal point lost -------------------------------------------------------------------------------------------------

def test_a_lost_decimal_point_is_named_in_the_note_techno_electric():
    """Techno Electric's scanned page: the text layer prints EPS 8.27 as "827". Memory is right; the page is read wrong."""
    pdf = _page([("8 Basic EPS (Rs.)", ["827", "12.33", "8.44", "46.60"])], pad=True)
    r = one(pdf, exp("eps", 8.27, "Q2FY27", "CONSOLIDATED"))
    assert r.status == "row_found_other_value" and r.printed_text == "827"
    assert "decimal point lost" in r.note
    money = one(_page([("1 Revenue from operations", ["23429", "95.00", "80.00", "380.00"])]), exp("revenue", 234.29, "Q2FY27", "CONSOLIDATED"))
    assert "decimal point lost" in money.note
    other = one(_page([("8 Basic EPS (Rs.)", ["9.99", "12.33", "8.44", "46.60"])]), exp("eps", 8.27, "Q2FY27", "CONSOLIDATED"))
    assert "decimal point lost" not in other.note


def test_the_locator_version_moved():
    assert xk.LOCATOR_VERSION == "2026-10-28.4"
