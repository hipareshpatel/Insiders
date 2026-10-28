"""The XBRL key (xbrl_key.py): small results statements made in the test with PyMuPDF (text at positions), a fake NSE client and a
fake memory, no network."""

from __future__ import annotations

import pymupdf
import pytest

from bse_intel import xbrl_key as xk
from bse_intel.bse import AttachmentError
from bse_intel.models import Filing
from bse_intel.nse import FileCapReached

PAGE_W, PAGE_H = 612, 842
COLS = (300, 380, 460, 540)                       # the centres of four date columns
DATES = ("30.09.2026", "30.06.2026", "30.09.2025", "31.03.2026")

ROWS = [                                           # label, four figures (quarter, quarter before, year-ago quarter, year)
    ("1 Revenue from operations", ["100.00", "95.00", "80.00", "380.00"]),
    ("2 Other income", ["5.00", "4.00", "3.00", "15.00"]),
    ("3 Total income (1+2)", ["105.00", "99.00", "83.00", "395.00"]),
    ("4 Total expenses", ["85.00", "80.00", "70.00", "330.00"]),
    ("5 Profit before tax (3-4)", ["20.00", "19.00", "13.00", "65.00"]),
    ("6 Tax expense", ["5.00", "4.75", "3.25", "16.25"]),
    ("7 Net Profit for the period (5-6)", ["15.00", "14.25", "9.75", "48.75"]),
    ("8 Basic EPS (Rs.)", ["1.50", "1.43", "0.98", "4.88"]),
]


FILLER = [                                          # lines that make a table a results statement (three metrics) without touching a test's figures
    ("Other income", ["7.11", "7.12", "7.13", "7.14"]),
    ("Total income", ["8.22", "8.23", "8.24", "8.25"]),
    ("Profit before tax", ["9.33", "9.34", "9.35", "9.36"]),
]


class Canvas:
    """Texts at reading-frame positions (x right, y down), drawn upright, on a page with a /Rotate flag, or with the text itself
    set running up the page (the way a landscape table sits on a portrait page)."""

    def __init__(self, doc, mode: str = "upright"):
        self.page = doc.new_page(width=PAGE_W, height=PAGE_H)
        self.mode = mode
        if mode == "flag":
            self.page.set_rotation(90)

    def text(self, x: float, y: float, s: str, right: bool = False, size: float = 8) -> None:
        if right:
            x -= pymupdf.get_text_length(s, fontsize=size)
        if self.mode == "content":
            self.page.insert_text((y, PAGE_H - x), s, fontsize=size, rotate=90)
        else:
            self.page.insert_text((x, y), s, fontsize=size)


def draw_table(canvas: Canvas, title="Statement of Standalone Unaudited Financial Results for the quarter ended 30 September 2026",
               unit="(Rs. in crore)", headings=True, dates=DATES, rows=ROWS, y0=40.0, cols=COLS, pad=True) -> float:
    rows = [*rows, *FILLER] if pad else rows
    canvas.text(20, y0, title)
    canvas.text(20, y0 + 16, unit)
    if headings:
        mid = sum(cols[:3]) / 3
        canvas.text(mid - 30, y0 + 36, "Quarter ended")
        canvas.text(cols[3] - 22, y0 + 36, "Year ended")
    canvas.text(20, y0 + 50, "Particulars")
    for x, d in zip(cols, dates):
        canvas.text(x - 22, y0 + 50, d)
    y = y0 + 70
    for label, figures in rows:
        canvas.text(20, y, label)
        for x, f in zip(cols, figures):
            canvas.text(x + 25, y, f, right=True)
        y += 14
    return y


def make_pdf(*pages, mode="upright", **kw) -> bytes:
    doc = pymupdf.open()
    for page in pages or [{}]:
        draw_table(Canvas(doc, mode), **{**kw, **page})
    return doc.tobytes()


def exp(metric, value, period="Q2FY27", basis="STANDALONE", news_id="xbrl:res:1:Q2FY27"):
    return xk.Expected(news_id, "X", basis, period, metric, value)


def one(pdf, *expected):
    got = xk.locate(pdf, list(expected))
    return got[0] if len(got) == 1 else got


@pytest.mark.parametrize("mode", ["upright", "flag", "content"])
def test_upright_rotated_flag_and_sideways_text_find_the_same_figure(mode):
    r = one(make_pdf(mode=mode), exp("revenue", 100.0))
    assert r.status == "found_unique" and r.page == 1 and r.n_strong == 1
    assert r.printed_value == 100.0 and r.printed_unit == "crore" and r.printed_text == "100.00"
    assert "Revenue from operations" in r.row_label
    assert r.column_header == "Quarter ended > 30.09.2026"                    # the full header path, not the nearest date
    x0, y0, x1, y1 = r.bbox
    assert 0 <= x0 < x1 <= PAGE_W and 0 <= y0 < y1 <= PAGE_H


def test_a_sideways_page_box_is_in_the_page_own_coordinates():
    upright = one(make_pdf(), exp("pat", 15.0)).bbox
    sideways = one(make_pdf(mode="content"), exp("pat", 15.0)).bbox
    assert upright != sideways                                                # the box is where the text sits on the page
    assert sideways[2] - sideways[0] < sideways[3] - sideways[1]              # its text runs up the page: a tall box


def test_every_metric_in_every_column_is_placed_uniquely():
    pdf = make_pdf()
    wanted = []
    for label, figures in ROWS:
        metric = {"Revenue": "revenue", "Other": "other_income", "Total i": "total_income", "Total e": "total_expenses",
                  "Profit b": "pbt", "Tax": "tax_expense", "Net": "pat", "Basic": "eps"}[
            next(k for k in ("Revenue", "Other", "Total i", "Total e", "Profit b", "Tax", "Net", "Basic") if k in label)]
        for period, value in zip(("Q2FY27", "Q1FY27", "Q2FY26", "FY26"), figures):
            wanted.append(exp(metric, float(value), period))
    got = xk.locate(pdf, wanted)
    assert [r.status for r in got] == ["found_unique"] * len(wanted)
    # the year and the quarter ended on the same day would be two columns: the parent heading tells them apart
    assert {r.column_header for r in got} == {"Quarter ended > 30.09.2026", "Quarter ended > 30.06.2026",
                                              "Quarter ended > 30.09.2025", "Year ended > 31.03.2026"}


def test_a_lakh_unit_is_compared_in_lakh_within_the_memory_rounding():
    rows = [("1 Revenue from operations", ["12,345.67", "1.00", "1.00", "1.00"])]
    r = one(make_pdf(rows=rows, unit="(Rs. in lakhs)"), exp("revenue", 123.46))       # memory keeps crore to two decimals
    assert r.status == "found_unique" and r.printed_unit == "lakh" and r.printed_value == 12345.67
    assert one(make_pdf(rows=rows, unit="(Rs. in lakhs)"), exp("revenue", 123.47)).status == "row_found_other_value"
    # a million page: 1,234.57 million is 123.457 crore
    rows = [("1 Revenue from operations", ["1,234.57", "1.00", "1.00", "1.00"])]
    assert one(make_pdf(rows=rows, unit="(Rs. in million)"), exp("revenue", 123.46)).printed_unit == "million"
    # thousands
    rows = [("1 Revenue from operations", ["1,234,567", "1", "1", "1"])]
    assert one(make_pdf(rows=rows, unit="(Rs. in thousands)"), exp("revenue", 123.46)).printed_unit == "thousand"


def test_a_whole_unit_figure_matches_within_half_a_unit():
    rows = [("1 Revenue from operations", ["2,646", "1", "1", "1"])]
    assert one(make_pdf(rows=rows), exp("revenue", 2646.37)).status == "found_unique"      # the page prints whole crore
    assert one(make_pdf(rows=rows), exp("revenue", 2647.2)).status == "row_found_other_value"


def test_a_bracket_negative_in_one_or_three_tokens():
    rows = [("7 Net Profit for the period", ["(12.50)", "-3.25", "4.00", "1.00"])]
    pdf = make_pdf(rows=rows)
    r = one(pdf, exp("pat", -12.5))
    assert r.status == "found_unique" and r.printed_value == -12.5
    assert one(pdf, exp("pat", -3.25, "Q1FY27")).printed_value == -3.25
    assert one(pdf, exp("pat", 12.5)).status == "row_found_other_value"           # the sign matters
    # a bracket and a minus sign that are words of their own
    doc = pymupdf.open()
    c = Canvas(doc)
    draw_table(c, rows=[("7 Net Profit for the period", ["4.00", "4.00", "4.00", "4.00"])])
    c.page.draw_rect(pymupdf.Rect(0, 150, PAGE_W, 170), color=None, fill=(1, 1, 1))
    c.text(20, 160, "9 Loss for the period")
    c.text(318, 160, "(")
    c.text(324, 160, "7.25")
    c.text(345, 160, ")")
    c.text(398, 160, "-")
    c.text(404, 160, "2.50")
    got = xk.locate(doc.tobytes(), [exp("pat", -7.25), exp("pat", -2.5, "Q1FY27")])
    assert [r.status for r in got] == ["found_unique"] * 2 and [r.printed_value for r in got] == [-7.25, -2.5]


def test_a_value_equal_in_two_columns_is_told_by_the_header_date():
    rows = [("1 Revenue from operations", ["100.00", "95.00", "100.00", "380.00"])]       # the year-ago quarter equals the quarter
    pdf = make_pdf(rows=rows)
    assert one(pdf, exp("revenue", 100.0, "Q2FY27")).column_header == "Quarter ended > 30.09.2026"
    r = one(pdf, exp("revenue", 100.0, "Q2FY26"))
    assert r.status == "found_unique" and r.column_header == "Quarter ended > 30.09.2025"
    # a quarter and a year that end on the same day, the same value: the parent heading says which is which
    rows = [("1 Revenue from operations", ["100.00", "95.00", "80.00", "100.00"])]
    pdf = make_pdf(rows=rows, dates=("31.03.2026", "31.12.2025", "31.03.2025", "31.03.2026"))
    assert one(pdf, exp("revenue", 100.0, "Q4FY26")).column_header == "Quarter ended > 31.03.2026"
    assert one(pdf, exp("revenue", 100.0, "FY26")).column_header == "Year ended > 31.03.2026"


def test_the_same_date_over_two_columns_with_no_heading_is_ambiguous():
    rows = [("1 Revenue from operations", ["100.00", "95.00", "80.00", "100.00"])]
    pdf = make_pdf(rows=rows, headings=False, dates=("31.03.2026", "31.12.2025", "31.03.2025", "31.03.2026"))
    r = one(pdf, exp("revenue", 100.0, "Q4FY26"))
    assert r.status == "found_ambiguous" and len(r.placements) == 2 and r.n_strong == 0
    assert {p["column"] for p in r.placements} == {"[no heading] > 31.03.2026"}
    assert all("not heading" in p["fit"] for p in r.placements)


def test_a_parent_heading_the_layout_supplied_is_not_proof():
    # five dates in the standard layout (quarter x3, year x2 at Q4) and no heading words: the layout rule knows the kinds,
    # but no heading was read, so the figure is placed and not proven
    pdf = make_pdf(headings=False)
    r = one(pdf, exp("revenue", 100.0))
    assert r.status == "found_ambiguous" and "heading" in r.note
    assert r.column_header == "[no heading] > 30.09.2026"


def test_a_figure_not_on_the_page_gives_the_printed_number_of_its_row():
    r = one(make_pdf(), exp("revenue", 999.99))
    assert r.status == "row_found_other_value" and r.other_value == "100.00" and r.page == 1
    assert r.column_header == "Quarter ended > 30.09.2026" and r.failure_stage == ""
    # a metric the page has no row for
    rows = [("1 Revenue from operations", ["100.00", "95.00", "80.00", "380.00"])]
    r = one(make_pdf(rows=rows), exp("pat", 999.99))
    assert r.status == "not_found" and r.failure_stage == "not_in_text_layer" and r.note == "no row for the metric"
    # the number is on the page, but not as the metric's row in the period's column: in the text, in the wrong place
    r = one(make_pdf(), exp("pat", 380.0))
    assert r.status == "found_ambiguous" and r.failure_stage == "in_text_wrong_place"
    assert r.n_strong == 0 and r.placements[0]["fit"] == "not row+column"


def test_no_text_layer_is_no_text():
    doc = pymupdf.open()
    doc.new_page()
    r = one(doc.tobytes(), exp("revenue", 100.0))
    assert r.status == "no_text" and r.failure_stage == ""


def test_the_basis_is_the_title_of_the_page_and_a_figure_on_the_other_page_is_not_a_placement():
    title_c = "Statement of Consolidated Unaudited Financial Results for the quarter ended 30 September 2026"
    cons = [("1 Revenue from operations", ["500.00", "1.00", "1.00", "1.00"])]
    both = make_pdf({}, {"title": title_c, "rows": cons})
    s, c = xk.locate(both, [exp("revenue", 100.0), exp("revenue", 500.0, basis="CONSOLIDATED")])
    assert (s.status, s.page, c.status, c.page) == ("found_unique", 1, "found_unique", 2)
    # a consolidated figure asked on the standalone basis is not found there, though its number is in the document
    r = one(both, exp("revenue", 500.0))
    assert r.status == "row_found_other_value" and r.other_value == "100.00" and r.page == 1
    # identical figures on both pages: one placement on each basis
    twin = make_pdf({}, {"title": title_c})
    assert [r.page for r in xk.locate(twin, [exp("revenue", 100.0), exp("revenue", 100.0, basis="CONSOLIDATED")])] == [1, 2]


def test_a_page_with_no_title_takes_the_one_before_and_a_document_that_never_says_consolidated_is_standalone():
    doc = pymupdf.open()
    draw_table(Canvas(doc), title="Statement of Consolidated Unaudited Financial Results for the quarter ended 30 September 2026")
    draw_table(Canvas(doc), title="Continued", rows=[("1 Revenue from operations", ["700.00", "1.00", "1.00", "1.00"])])
    r = one(doc.tobytes(), exp("revenue", 700.0, basis="CONSOLIDATED"))
    assert r.status == "found_unique" and r.page == 2 and "previous page" in r.note
    r = one(make_pdf(title="Unaudited Financial Results for the quarter ended 30 September 2026"), exp("revenue", 100.0))
    assert r.status == "found_unique" and "no consolidated anywhere" in r.note


def test_two_lines_of_one_table_that_print_the_same_figure_are_one_figure():
    rows = [("5 Profit before tax", ["20.00", "19.00", "13.00", "65.00"]), ("7 Profit after tax (5-6)", ["15.00", "14.25", "9.75", "48.75"]),
            ("9 Profit for the period (7+8)", ["15.00", "14.25", "9.75", "48.75"])]
    r = one(make_pdf(rows=rows), exp("pat", 15.0))
    assert r.status == "found_unique" and r.n_strong == 2 and r.row_label.startswith("Profit for the period")
    assert "also on the line" in r.note and "Profit after tax" in r.note
    # a segment table that names one metric is told apart from the statement
    seg = [("Segment revenue from operations", ["100.00", "95.00", "80.00", "380.00"])]
    r = one(make_pdf({}, {"rows": seg, "title": "Segment results"}), exp("revenue", 100.0))
    assert r.status == "found_unique" and r.page == 1 and "also printed in another table on page 2" in r.note


def test_the_same_statement_printed_twice_is_one_placement():
    r = one(make_pdf({}, {}), exp("revenue", 100.0))
    assert r.status == "found_unique" and r.n_strong == 1


def test_a_wrapped_date_and_a_date_split_in_two_words_are_read():
    doc = pymupdf.open()
    c = Canvas(doc)
    c.text(20, 40, "(Rs. in crore)")
    c.text(350, 76, "Quarter ended")
    c.text(20, 90, "Particulars")
    for x, (dm, y) in zip(COLS[:3], (("30 September", "2026"), ("30 June", "2026"), ("30 September", "2025"))):
        c.text(x - 25, 90, dm)
        c.text(x - 8, 99, y)
    c.text(20, 120, "1 Revenue from operations")
    for x, f in zip(COLS[:3], ("100.00", "95.00", "80.00")):
        c.text(x + 25, 120, f, right=True)
    c.text(20, 134, "2 Other income")
    for x, f in zip(COLS[:3], ("5.00", "4.00", "3.00")):
        c.text(x + 25, 134, f, right=True)
    c.text(20, 148, "3 Total income")
    for x, f in zip(COLS[:3], ("105.00", "99.00", "83.00")):
        c.text(x + 25, 148, f, right=True)
    got = xk.locate(doc.tobytes(), [exp("revenue", 100.0), exp("revenue", 80.0, "Q2FY26")])
    assert [r.status for r in got] == ["found_unique"] * 2 and got[1].column_header == "Quarter ended > 30.09.2025"


def test_a_figure_row_a_few_points_off_its_label_takes_the_label():
    doc = pymupdf.open()
    c = Canvas(doc)
    draw_table(c, rows=[("1 Revenue from operations", ["1.00", "1.00", "1.00", "1.00"])])
    c.text(20, 200, "Net Profit for the period")
    for x, f in zip(COLS, ("15.00", "14.25", "9.75", "48.75")):
        c.text(x + 25, 207, f, right=True)                                    # seven points below its label
    r = one(doc.tobytes(), exp("pat", 15.0))
    assert r.status == "found_unique" and r.row_label == "Net Profit for the period"


def test_numbers_as_printed():
    p = xk.parse_number
    assert p("1,23,456.78").value == 123456.78 and p("1,23,456.78").decimals == 2
    assert p("(1,234.50)").value == -1234.5 and p("-12").value == -12 and p("12-").value == -12
    assert p("− 4.5") is None or p("−4.5").value == -4.5
    assert p("2,646").decimals == 0 and p("0.05").value == 0.05
    repaired = p("5.58.271.46")                                               # an OCR layer's dots for commas
    assert repaired.value == 558271.46 and repaired.repaired
    assert p("11,45,137,09").value == 1145137.09 and p("11,45,137,09").repaired
    assert p("12%") is None and p("Rs.") is None and p("1,2,3") is None and p("30.09.2026") is None      # a date is no number
    assert p("") is None and p("-") is None and p("(") is None


def test_the_arithmetic_checks_pass_on_a_table_that_adds_up_and_fail_on_one_that_does_not():
    wanted = [exp("revenue", 100.0), exp("other_income", 5.0), exp("total_income", 105.0), exp("total_expenses", 85.0),
              exp("pbt", 20.0)]
    got = xk.locate(make_pdf(), wanted)
    assert {r.expected.metric: (r.arith_income, r.arith_pbt) for r in got} == {
        "revenue": ("pass", "na"), "other_income": ("pass", "na"), "total_income": ("pass", "pass"),
        "total_expenses": ("na", "pass"), "pbt": ("na", "pass")}
    bad = [("1 Revenue from operations", ["100.00", "1.00", "1.00", "1.00"]), ("2 Other income", ["5.00", "1.00", "1.00", "1.00"]),
           ("3 Total income", ["110.00", "1.00", "1.00", "1.00"]), ("4 Total expenses", ["85.00", "1.00", "1.00", "1.00"]),
           ("5 Profit before tax", ["20.00", "1.00", "1.00", "1.00"])]
    got = xk.locate(make_pdf(rows=bad), [exp("revenue", 100.0), exp("other_income", 5.0), exp("total_income", 110.0),
                                          exp("total_expenses", 85.0), exp("pbt", 20.0)])
    assert {r.expected.metric: r.arith_income for r in got}["total_income"] == "fail"
    assert "!= total income" in got[2].arith_note and {r.expected.metric: r.arith_pbt for r in got}["pbt"] == "fail"
    # an exceptional item is allowed for
    rows = [("3 Total income", ["105.00", "1.00", "1.00", "1.00"]), ("4 Total expenses", ["85.00", "1.00", "1.00", "1.00"]),
            ("5 Exceptional items", ["(8.00)", "1.00", "1.00", "1.00"]), ("6 Profit before tax", ["12.00", "1.00", "1.00", "1.00"])]
    got = xk.locate(make_pdf(rows=rows), [exp("total_income", 105.0), exp("total_expenses", 85.0), exp("exceptional_items", -8.0),
                                          exp("pbt", 12.0)])
    assert {r.arith_pbt for r in got} == {"pass"}


def test_the_failure_stage_names_where_each_figure_was_lost():
    pdf = make_pdf()
    assert one(pdf, exp("revenue", 77.77)).failure_stage == ""                            # row found: not a "not found"
    rows = [("1 Revenue from operations", ["100.00", "95.00", "80.00", "380.00"])]
    got = xk.locate(make_pdf(rows=rows, unit=""), [exp("pat", 123.0, news_id="a")])
    assert got[0].failure_stage == "not_in_text_layer"
    # a table found, a number in the text outside it, and no unit line anywhere
    doc = pymupdf.open()
    c = Canvas(doc)
    draw_table(c, unit="(figures)")
    c.text(20, 12, "A total of 77.77 was noted")
    r = one(doc.tobytes(), exp("interest_earned", 77.77))
    assert r.status == "not_found" and r.failure_stage == "unit_unknown"
    # a number that is printed, but no table of dates was tied to the basis
    doc = pymupdf.open()
    c = Canvas(doc)
    for i in range(30):
        c.text(20, 40 + 10 * i, f"Note {i} the sum of 4,321.50 and other amounts is shown here")
    r = one(doc.tobytes(), exp("revenue", 4321.5))
    assert r.status == "not_found" and r.failure_stage == "no_statement_page"


# --- memory and the run -------------------------------------------------------------------------------------------

def dossier():
    def entry(metric, period, value, sid, basis, unit="INR_CR"):
        return {"metric": metric, "period": period, "value": value, "unit": unit, "source_news_id": sid, "basis": basis}

    sid = "xbrl:res:1:Q2FY27"
    rows = [entry("revenue", "Q2FY27", 100.0, sid, "CONSOLIDATED"), entry("revenue", "Q1FY27", 95.0, sid, "CONSOLIDATED"),
            entry("pat", "Q2FY27", 15.0, sid, "CONSOLIDATED"), entry("eps", "Q2FY27", 1.5, sid, "CONSOLIDATED", "INR"),
            entry("ebitda", "Q2FY27", 30.0, sid, "CONSOLIDATED"), entry("pbt", "Q2FY27", 20.0, sid, "CONSOLIDATED", "PCT"),
            entry("revenue", "Q2FY27", 7.0, "card-77", "CONSOLIDATED")]
    return {"financial_metrics": rows}


def test_expected_figures_come_from_the_exchange_files_only_by_filing_period():
    got = xk.expected_from_dossier(dossier(), "X")
    assert set(got) == {"Q2FY27"}
    metrics = {(e.metric, e.period, e.basis, e.value) for e in got["Q2FY27"]}
    # the card-written revenue, the derived EBITDA (not listed) and a percentage in a money line are left out
    assert metrics == {("revenue", "Q2FY27", "CONSOLIDATED", 100.0), ("revenue", "Q1FY27", "CONSOLIDATED", 95.0),
                       ("pat", "Q2FY27", "CONSOLIDATED", 15.0), ("eps", "Q2FY27", "CONSOLIDATED", 1.5)}
    assert all(e.news_id == "xbrl:res:1:Q2FY27" and e.symbol == "X" for e in got["Q2FY27"])


def filing(url="https://nsearchives.nseindia.com/corporate/RES.pdf", subject="Financial Results", headline="Results for the quarter"):
    when = "2026-10-20T10:00:00+05:30"
    return Filing(news_id="nse-9", scrip_code="1", company_name="X", symbol="X", headline=headline, subject=subject,
                  category="", subcategory=subject, filed_at=when, filing_date=when[:10], pdf_url=url)


class FakeNse:
    def __init__(self, filings, pdfs, error=None):
        self.filings, self.pdfs, self.error = filings, pdfs, error
        self.fetches: list[str] = []
        self.lists: list[tuple] = []

    def announcements(self, day_from, day_to=None, symbol=None, scrip_for=None):
        self.lists.append((day_from, day_to, symbol))
        return self.filings

    def fetch(self, url, max_bytes=0):
        self.fetches.append(url)
        if isinstance(self.error, (AttachmentError, FileCapReached)):
            raise self.error
        return self.pdfs.get(url)


class FakeSink:
    def __init__(self, dossiers):
        self.dossiers, self.saved = dossiers, {}

    def get_dossier(self, scrip):
        return self.dossiers.get(scrip)

    def put_object(self, key, body, content_type=""):
        self.saved[key] = body

    def get_object(self, key):
        return self.saved.get(key)


def full_dossier(scrip="1"):
    sid = f"xbrl:res:{scrip}:Q2FY27"
    out = []
    for label, figures in ROWS:
        metric = {"1": "revenue", "2": "other_income", "3": "total_income", "4": "total_expenses", "5": "pbt", "6": "tax_expense",
                  "7": "pat", "8": "eps"}[label.split()[0]]
        out.append({"metric": metric, "period": "Q2FY27", "value": float(figures[0]), "unit": "INR" if metric == "eps" else "INR_CR",
                    "source_news_id": sid, "basis": "STANDALONE"})
    return {"financial_metrics": out}


def test_a_run_reads_each_filing_once_and_writes_a_row_for_every_figure():
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    nse = FakeNse([filing()], {url: make_pdf()})
    sink = FakeSink({"1": full_dossier()})
    saves = []
    out = xk.run(nse, sink, [("1", "X")], limit=5, progress=lambda rows, summary: saves.append(len(rows)), every=1)
    assert nse.fetches == [url] and len(nse.lists) == 1
    assert len(out["rows"]) == 8 and out["statuses"]["found_unique"] == 8 and saves == [8]
    row = out["rows"][0]
    assert row["news_id"] == "xbrl:res:1:Q2FY27" and row["pdf_url"] == url and row["filing_period"] == "Q2FY27"
    csv_text = xk.to_csv(out["rows"])
    assert csv_text.splitlines()[0].split(",") == xk.CSV_HEADER and len(csv_text.splitlines()) == 9
    assert xk.load_csv(csv_text)[0]["column_header"] == "Quarter ended > 30.09.2026"
    assert "| found_unique | 8 |" in xk.to_markdown(out, "2026-10-28")


def test_a_run_that_reaches_the_file_cap_keeps_what_it_read_and_says_so():
    class Capped(FakeNse):
        def fetch(self, url, max_bytes=0):
            self.fetches.append(url)
            if len(self.fetches) > 1:
                raise FileCapReached("file cap reached (1 of 1 files)")
            return self.pdfs.get(url)

    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    nse = Capped([filing()], {url: make_pdf()})
    sink = FakeSink({"1": full_dossier("1"), "2": full_dossier("2")})
    out = xk.run(nse, sink, [("1", "A"), ("2", "B")], limit=5, seed=1, per_company=1)
    assert out["file_cap_reached"] and len(out["rows"]) == 8              # the first company's filing was read, the second stopped
    assert "file cap reached" in xk.to_markdown(out, "2026-10-28")


def test_a_run_stopped_by_its_time_budget_and_resumed_skips_the_filings_it_did():
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    sink = FakeSink({"1": full_dossier("1"), "2": full_dossier("2")})
    ticks = iter([0, 0, 10, 200, 300, 400])
    first = xk.run(FakeNse([filing()], {url: make_pdf()}), sink, [("1", "A"), ("2", "B")], limit=5, seed=1, time_budget=150,
                   clock=lambda: next(ticks))
    assert first["out_of_time"] and len(first["rows"]) == 8
    assert xk.save_progress(sink, "n", first["rows"]) and xk.progress_key("n") in sink.saved
    nse = FakeNse([filing()], {url: make_pdf()})
    second = xk.run(nse, sink, [("1", "A"), ("2", "B")], limit=5, seed=1, saved=xk.load_progress(sink, "n"))
    assert len(second["rows"]) == 16 and len(nse.fetches) == 1               # one more PDF, not two


def test_a_filing_with_no_pdf_gets_not_found_rows_with_the_reason():
    nse = FakeNse([], {})
    out = xk.run(nse, FakeSink({"1": full_dossier()}), [("1", "X")], limit=1)
    assert len(out["rows"]) == 8 and {r["status"] for r in out["rows"]} == {"not_found"}
    assert "no results filing" in out["rows"][0]["note"]


def test_the_summary_counts_the_failure_stages_and_lists_the_other_values():
    rows = [xk.result_row(r) for r in xk.locate(make_pdf(), [exp("revenue", 100.0), exp("revenue", 999.0), exp("pat", 380.0),
                                                              exp("other_income", 1234.0, period="Q9FY99")])]
    summary = xk.summarise(rows, {"lists": 0, "pdfs": 1}, 1)
    assert summary["statuses"]["found_unique"] == 1 and summary["statuses"]["row_found_other_value"] == 1
    assert summary["failure_stages"]["in_text_wrong_place"] == 1 and summary["failure_stages"]["not_in_text_layer"] == 1
    assert summary["other_value_examples"][0]["other_value"] == "100.00"


# --- review fixes (28 Oct 2026) ------------------------------------------------------------------------------------

def test_the_only_placement_in_a_segment_or_summary_table_is_not_found_unique():
    # a table of one line, and a table under a segment heading with three metrics: neither is the results statement
    one_line = [("Revenue from operations", ["100.00", "95.00", "80.00", "380.00"])]
    r = one(make_pdf(rows=one_line, pad=False, title="Segment results"), exp("revenue", 100.0))
    assert r.status == "found_ambiguous" and r.reason == "segment_only" and r.n_strong == 1 and "only 1 metric" in r.note
    doc = pymupdf.open()
    c = Canvas(doc)
    c.text(20, 30, "Segment wise revenue and results")
    draw_table(c, title="", y0=36.0)
    r = one(doc.tobytes(), exp("revenue", 100.0))
    assert r.status == "found_ambiguous" and r.reason == "segment_only" and "segment heading" in r.note


def test_a_placement_made_with_no_declared_unit_is_not_found_unique():
    r = one(make_pdf(unit="(figures)"), exp("revenue", 100.0))
    assert r.status == "found_ambiguous" and r.reason == "unit_not_declared" and r.printed_unit == "?crore"
    assert one(make_pdf(unit="(figures)"), exp("eps", 1.5)).status == "found_unique"      # EPS needs no unit
    assert one(make_pdf(), exp("revenue", 100.0)).reason == ""


def test_the_reason_of_an_ambiguous_figure_is_in_the_csv_and_the_summary():
    rows = [xk.result_row(r) for r in xk.locate(make_pdf(unit="(figures)"), [exp("revenue", 100.0), exp("pat", 380.0)])]
    assert {r["reason"] for r in rows} == {"unit_not_declared", "not_row+column"}
    summary = xk.summarise(rows, {"lists": 0, "pdfs": 1}, 1)
    assert summary["ambiguous_reasons"] == {"unit_not_declared": 1, "not_row+column": 1}
    assert "## Why found_ambiguous" in xk.to_markdown(summary, "2026-10-28")


def test_a_resumed_run_reads_its_saved_rows_back_as_numbers_and_the_report_still_writes():
    import csv
    import io

    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    wrong = full_dossier("1")
    wrong["financial_metrics"][0]["value"] = 123.45                          # revenue: the page prints 100.00, an other-value row
    sink = FakeSink({"1": wrong})
    first = xk.run(FakeNse([filing()], {url: make_pdf()}), sink, [("1", "X")], limit=1)
    assert first["statuses"]["row_found_other_value"] == 1
    assert xk.save_progress(sink, "n", first["rows"])
    saved = xk.load_progress(sink, "n")
    other = next(r for r in saved if r["status"] == "row_found_other_value")
    assert other["xbrl_value"] == 123.45 and other["printed_value"] == 100.0 and other["page"] == 1 and other["n_strong"] == 0
    second = xk.run(FakeNse([filing()], {url: make_pdf()}), sink, [("1", "X")], limit=1, saved=saved)
    assert len(second["rows"]) == 8 and "| X | STANDALONE | Q2FY27 | revenue | 123.45 | 100.00 |" in xk.to_markdown(second, "2026-10-28")
    # even rows still holding strings (a CSV not read through load_csv) do not stop the report
    raw = list(csv.DictReader(io.StringIO(xk.to_csv(first["rows"]))))
    assert "123.45" in xk.to_markdown(xk.summarise(raw, {"lists": 0, "pdfs": 1}, 1), "2026-10-28")


def test_a_failing_progress_callback_never_stops_the_run():
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"

    def boom(rows, summary):
        raise RuntimeError("no disk")

    out = xk.run(FakeNse([filing()], {url: make_pdf()}), FakeSink({"1": full_dossier()}), [("1", "X")], limit=1, progress=boom, every=1)
    assert len(out["rows"]) == 8


def test_a_failed_fetch_is_its_own_status_and_is_read_again_by_a_resume():
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    sink = FakeSink({"1": full_dossier("1"), "2": full_dossier("2")})

    class ListFails(FakeNse):
        def announcements(self, *a, **k):
            raise TimeoutError("timed out")

    first = xk.run(ListFails([], {}), sink, [("1", "A"), ("2", "B")], limit=5, seed=1)
    assert {r["status"] for r in first["rows"]} == {"fetch_failed"} and len(first["rows"]) == 16
    assert first["statuses"]["fetch_failed"] == 16 and first["statuses"]["not_found"] == 0 and first["fetch_failed_filings"] == 2
    assert "2 filings could not be fetched" in xk.to_markdown(first, "2026-10-28")
    # a download that fails is the same
    down = xk.run(FakeNse([filing()], {url: make_pdf()}, AttachmentError("reset")), sink, [("1", "A")], limit=1)
    assert {r["status"] for r in down["rows"]} == {"fetch_failed"}
    # a resume does not take them as finished: it reads both filings again
    assert xk.save_progress(sink, "n", first["rows"])
    nse = FakeNse([filing()], {url: make_pdf()})
    second = xk.run(nse, sink, [("1", "A"), ("2", "B")], limit=5, seed=1, saved=xk.load_progress(sink, "n"))
    assert len(nse.fetches) == 2 and second["statuses"]["fetch_failed"] == 0 and second["statuses"]["found_unique"] == 16
    # a settled answer is not a failure: NSE serves no file, or lists no results filing
    gone = xk.run(FakeNse([filing()], {}), FakeSink({"1": full_dossier()}), [("1", "A")], limit=1)
    assert {r["status"] for r in gone["rows"]} == {"not_found"} and gone["fetch_failed_filings"] == 0
    none = xk.run(FakeNse([], {}), FakeSink({"1": full_dossier()}), [("1", "A")], limit=1)
    assert {r["status"] for r in none["rows"]} == {"not_found"}


def test_a_download_that_failed_but_another_candidate_read_is_a_result():
    good = "https://nsearchives.nseindia.com/corporate/GOOD.pdf"
    bad = "https://nsearchives.nseindia.com/corporate/BAD.pdf"

    class Half(FakeNse):
        def fetch(self, url, max_bytes=0):
            self.fetches.append(url)
            if url == bad:
                raise AttachmentError("reset")
            return self.pdfs.get(url)

    nse = Half([filing(bad), filing(good, headline="Results part two")], {good: make_pdf()})
    out = xk.run(nse, FakeSink({"1": full_dossier()}), [("1", "X")], limit=1)
    assert out["statuses"]["found_unique"] == 8 and out["fetch_failed_filings"] == 0
