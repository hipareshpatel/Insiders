"""The experimental numbers-first reader (pdf_numbers_first.py): small statements drawn with PyMuPDF, no OCR, no network."""

from __future__ import annotations
from datetime import date

import pymupdf
import pytest

from bse_intel import pdf_numbers_first as nf
from bse_intel import pdf_readers as prd

FONT = 8
LEFT = 30
NOTE_RIGHT = 262
COL_RIGHT = [330, 400, 470, 540]          # right edges of the four number columns
DATES = ["30.09.2026", "30.06.2026", "30.09.2025", "31.03.2026"]
KINDS = ["Quarter ended", "Quarter ended", "Quarter ended", "Year ended"]


def fmt(v: float, decimals: int = 2) -> str:
    text = f"{abs(v):,.{decimals}f}"
    return f"({text})" if v < 0 else text


def draw(page, x: float, y: float, text: str) -> None:
    page.insert_text((x, y), text, fontsize=FONT)


def right(page, edge: float, y: float, text: str) -> None:
    draw(page, edge - pymupdf.get_text_length(text, fontsize=FONT), y, text)


def statement(rows: list[tuple[list[str], list[str | float]]], title: str = "Statement of Standalone Unaudited Financial Results",
              unit: str = "(Rs. in Lakhs)", groups: list[str] | None = None, dates: list[str] | None = None,
              cols: list[float] | None = None, notes: dict[int, str] | None = None) -> bytes:
    """A results statement: ``rows`` are (label lines, cells); the cells sit on the label's LAST line, a string cell is printed
    as it is (a "-" is a nil), a number as the printed figure."""
    cols = cols or COL_RIGHT
    groups = groups or KINDS
    dates = dates or DATES
    doc = pymupdf.open()
    page = doc.new_page(width=620, height=842)
    draw(page, LEFT, 40, title)
    draw(page, LEFT, 54, unit)
    for edge, g, d in zip(cols, groups, dates):
        draw(page, edge - 15 - pymupdf.get_text_length(g, fontsize=FONT) / 2, 78, g)
        right(page, edge, 92, d)
    draw(page, LEFT, 92, "Particulars")
    if notes:
        right(page, NOTE_RIGHT, 92, "Note")
    y = 130.0
    for index, (label_lines, cells) in enumerate(rows):
        for k, line in enumerate(label_lines):
            draw(page, LEFT, y + 11 * (k - len(label_lines) + 1), line)
        for edge, cell in zip(cols, cells):
            right(page, edge, y, cell if isinstance(cell, str) else fmt(cell))
        if notes and index in notes:
            right(page, NOTE_RIGHT, y, notes[index])
        y += 11 * len(label_lines) + 8
    out = doc.tobytes()
    doc.close()
    return out


def cols_sum(*rows: list[float]) -> list[float]:
    return [round(sum(v), 2) for v in zip(*rows)]


REVENUE = [1000.00, 900.50, 800.25, 3600.75]
OTHER = [50.10, 40.20, 30.30, 160.40]
EMPLOYEE = [200.00, 190.00, 180.00, 760.00]
FINANCE = [30.55, 31.45, 29.05, 120.10]
DEPRECIATION = [40.00, 41.00, 42.00, 165.00]
OTHER_EXP = [500.25, 480.15, 470.95, 1900.05]
EXCEPTIONAL = [0.0, 0.0, 0.0, 10.0]
CURRENT = [60.00, 55.00, 50.00, 220.00]
DEFERRED = [5.10, 4.20, 3.30, 18.90]


def pl(revenue=REVENUE, other=OTHER, total_label=("Total income (I+II)",), exceptional=EXCEPTIONAL, wrap_pbt=True, pbt_label=None,
       scale=1.0):
    """The rows of a Schedule III profit and loss account, numbers that add up in every column."""
    employee, finance, depreciation, other_exp = ([round(v * scale, 2) for v in line]
                                                  for line in (EMPLOYEE, FINANCE, DEPRECIATION, OTHER_EXP))
    total_income = cols_sum(revenue, other)
    expenses = cols_sum(employee, finance, depreciation, other_exp)
    pbt_before = [round(a - b, 2) for a, b in zip(total_income, expenses)]
    pbt = [round(a - b, 2) for a, b in zip(pbt_before, exceptional)]
    tax = cols_sum(CURRENT, DEFERRED)
    pat = [round(a - b, 2) for a, b in zip(pbt, tax)]
    pbt_wrapped = ["V. Profit / (Loss) before exceptional", "items and tax (III-IV)"] if wrap_pbt else ["V. Profit before exceptional items and tax"]
    rows = [
        (["Revenue from operations"], revenue),
        (["Other income"], other),
        (list(total_label), total_income),
        (["Employee benefits expense"], employee),
        (["Finance costs"], finance),
        (["Depreciation and amortisation"], depreciation),
        (["Other expenses"], other_exp),
        (["Total expenses"], expenses),
        (pbt_wrapped, pbt_before),
        (["Exceptional items"], [fmt(v) if v else "-" for v in exceptional]),
        ([pbt_label or "Profit before tax (V-VI)"], pbt),
        (["Current tax"], CURRENT),
        (["Deferred tax"], DEFERRED),
        (["Total tax expense"], tax),
        (["Profit for the period"], pat),
    ]
    return rows, dict(total_income=total_income, expenses=expenses, pbt_before=pbt_before, pbt=pbt, tax=tax, pat=pat)


def read(pdf: bytes, metric: str, period: str = "Q2FY27", basis: str = "STANDALONE"):
    return nf.reading_from_tables(nf.analyse(pdf), period, metric, basis)


def crore(lakh: float) -> float:
    return lakh / 100


# --- numbers -----------------------------------------------------------------------------------------------------------

def test_figures_indian_grouping_brackets_and_nil():
    assert nf.parse_figure("12,34,567.89").value == 1234567.89
    assert nf.parse_figure("12,34,567.89").decimals == 2
    assert nf.parse_figure("(1,234.50)").value == -1234.5
    assert nf.parse_figure("-45.20").value == -45.2
    for dash in ("-", "–", "Nil"):
        cell = nf.parse_figure(dash)
        assert cell.nil and cell.value == 0.0
    assert nf.parse_figure("2026") is None            # a year is not a figure
    assert nf.parse_figure("30.09.2026") is None      # a date is not a figure
    assert nf.parse_figure("12").strict is False      # a small whole number is a note or serial number until a column claims it


# --- the statement -----------------------------------------------------------------------------------------------------

def test_a_whole_statement_is_named_by_its_arithmetic():
    rows, want = pl()
    pdf = statement(rows)
    got = {m: read(pdf, m) for m in ("revenue", "total_income", "pbt", "pat", "other_income", "expenses", "tax")}
    assert {m: r.status for m, r in got.items()} == {m: "ok" for m in got}
    assert got["revenue"].value == pytest.approx(crore(1000.00))
    assert got["other_income"].value == pytest.approx(crore(50.10))
    assert got["total_income"].value == pytest.approx(crore(want["total_income"][0]))
    assert got["expenses"].value == pytest.approx(crore(want["expenses"][0]))
    assert got["pbt"].value == pytest.approx(crore(want["pbt"][0]))
    assert got["tax"].value == pytest.approx(crore(want["tax"][0]))
    assert got["pat"].value == pytest.approx(crore(want["pat"][0]))
    assert got["pat"].tol == pytest.approx(0.005 / 100)             # half of the last printed digit, in crore
    assert got["pat"].reader == "numfirst" and got["pat"].page == 1


def test_a_wrapped_profit_before_tax_label_is_stitched_and_found():
    rows, want = pl(wrap_pbt=True, pbt_label="Profit / (Loss) before tax")
    pdf = statement(rows)
    table = nf.analyse(pdf)[0]
    labels = [r.label for r in table.rows]
    assert any("before exceptional items and tax" in x for x in labels)          # two printed lines, one label
    assert read(pdf, "pbt").value == pytest.approx(crore(want["pbt"][0]))
    # the profit before exceptional items is named too, from its stitched label and the arithmetic together
    assert nf.Solver(table).solve().explanations["pbt_pre"]


def test_a_bare_total_is_total_income_by_arithmetic():
    rows, want = pl(total_label=("Total",))
    pdf = statement(rows)
    assert nf.label_class("Total") is None
    r = read(pdf, "total_income")
    assert r.status == "ok" and r.value == pytest.approx(crore(want["total_income"][0]))
    assert read(pdf, "revenue").value == pytest.approx(crore(1000.00))          # revenue is its first part, by position


def test_a_bare_roman_numeral_total_is_total_income_too():
    rows, want = pl(total_label=("(I+II)",))
    assert read(statement(rows), "total_income").value == pytest.approx(crore(want["total_income"][0]))


def test_a_nil_cell_counts_as_zero_in_the_sums():
    rows, want = pl(other=[0.0, 40.20, 30.30, 160.40], exceptional=[0.0, 0.0, 0.0, 0.0])
    rows[1] = (["Other income"], ["-", 40.20, 30.30, 160.40])
    pdf = statement(rows)
    r = read(pdf, "total_income")
    assert r.status == "ok" and r.value == pytest.approx(crore(1000.00))        # 1000.00 + nil
    assert read(pdf, "other_income").value == pytest.approx(0.0)
    assert read(pdf, "pbt").status == "ok"


def test_a_bracketed_negative_is_a_loss():
    # expenses larger than income: every profit line is negative and printed in brackets
    rows, want = pl(scale=10.0)
    assert want["pbt"][0] < 0 and want["pat"][0] < 0
    pdf = statement(rows)
    assert read(pdf, "pbt").value == pytest.approx(crore(want["pbt"][0]))
    assert read(pdf, "pat").value == pytest.approx(crore(want["pat"][0]))
    assert read(pdf, "pat").value < 0


def test_the_lakh_unit_is_converted_to_crore_and_a_crore_page_is_not():
    rows, want = pl()
    lakh = read(statement(rows, unit="(Rs. in Lakhs)"), "total_income").value
    crores = read(statement(rows, unit="(Rs. in Crores)"), "total_income").value
    assert lakh == pytest.approx(want["total_income"][0] / 100)
    assert crores == pytest.approx(want["total_income"][0])
    million = read(statement(rows, unit="(Rs. in Million)"), "total_income").value
    assert million == pytest.approx(want["total_income"][0] / 10)
    assert read(statement(rows, unit=""), "total_income").status == "none"       # no unit, no figure


def test_two_columns_with_one_date_are_told_apart_by_their_parent_heading():
    rows, want = pl()
    # the quarter ended 30.09.2026 and the half year ended 30.09.2026 share a date; the half year is twice the quarter
    dates = ["30.09.2026", "30.06.2026", "30.09.2026", "31.03.2026"]
    groups = ["Quarter ended", "Quarter ended", "Half year ended", "Year ended"]
    pdf = statement(rows, dates=dates, groups=groups)
    table = nf.analyse(pdf)[0]
    assert [c.kind for c in table.columns] == ["quarter", "quarter", "half", "year"]
    r = read(pdf, "total_income")
    assert r.value == pytest.approx(crore(want["total_income"][0]))             # the quarter's, not the half year's
    # with no parent heading the same two columns are ambiguous: no answer, not a guess
    bare = statement(rows, dates=dates, groups=["", "", "", ""])
    assert read(bare, "total_income").status == "none"


def test_the_year_column_is_found_by_its_date_and_kind():
    rows, want = pl()
    r = read(statement(rows), "pat", period="FY26")
    assert r.status == "ok" and r.value == pytest.approx(crore(want["pat"][3]))


def test_a_page_whose_arithmetic_fails_gives_no_answer():
    rows, want = pl()
    # total income is printed wrong in every column: the identity holds nowhere, so no row is named
    rows[2] = (rows[2][0], [v + 7.0 for v in want["total_income"]])
    pdf = statement(rows)
    for metric in ("total_income", "pbt", "pat", "expenses", "revenue"):
        r = read(pdf, metric)
        assert r.status == "none" and r.value is None, metric


def test_one_broken_column_is_tolerated_but_never_answered():
    rows, want = pl()
    broken = list(want["total_income"])
    broken[0] += 3.0                                    # the asked column (the quarter) is wrong, the other three hold
    rows[2] = (rows[2][0], broken)
    pdf = statement(rows)
    assert read(pdf, "total_income", "Q2FY27").status == "none"                 # the period's own column must hold
    assert read(pdf, "total_income", "FY26").status == "ok"                     # another column still answers


def test_a_label_that_disagrees_with_the_arithmetic_gives_no_answer():
    rows, want = pl(total_label=("Total expenses",))                           # the row the arithmetic finds is not "expenses"
    assert read(statement(rows), "total_income").status == "none"


def test_the_wrong_basis_is_never_answered():
    rows, want = pl()
    pdf = statement(rows, title="Statement of Standalone Unaudited Financial Results")
    r = read(pdf, "total_income", basis="CONSOLIDATED")
    assert r.status in ("otherbasis", "none") and r.value is None


def test_consolidated_title_gives_the_consolidated_basis():
    rows, want = pl()
    pdf = statement(rows, title="Statement of Consolidated Unaudited Financial Results")
    assert read(pdf, "total_income", basis="CONSOLIDATED").status == "ok"
    assert read(pdf, "total_income", basis="STANDALONE").status == "otherbasis"


def test_the_combination_keeps_the_native_answer_first():
    native = prd.Reading("native", "textlayer-native", "ok", 12.5)
    other = prd.Reading("numfirst", "numbers-first", "ok", 99.0)
    assert nf.combine_readings(native, other) is native
    none = prd.Reading("native", "textlayer-native", "none")
    assert nf.combine_readings(none, other) is other


def test_the_reader_is_bench_only():
    assert prd.DEFAULT_READERS == "native" and prd.configured_readers() == ["native"]
    reader = prd.READERS["numfirst"]
    assert reader.direct and reader.available()
    rows, want = pl()
    ens = prd.Ensemble(["native", "numfirst"], ocr=False)
    got = {r.reader: r for r in ens.readings("k.pdf", statement(rows), "Q2FY27", "total_income", "STANDALONE")}
    assert got["numfirst"].status == "ok" and got["numfirst"].value == pytest.approx(crore(want["total_income"][0]))


def test_a_note_column_of_small_whole_numbers_is_label_text_not_figures():
    rows, want = pl()
    notes = {0: "24", 1: "25", 7: "26", 10: "3", 14: "40"}
    pdf = statement(rows, notes=notes)
    table = nf.analyse(pdf)[0]
    assert len(table.columns) == 4                                            # the Note column is not a column of figures
    labels = [r.label for r in table.rows]
    assert "Revenue from operations 24" in labels[0]                         # the note number stays with the label
    assert read(pdf, "revenue").value == pytest.approx(crore(1000.00))        # not 24, not a figure of the row
    assert read(pdf, "total_income").value == pytest.approx(crore(want["total_income"][0]))
    assert read(pdf, "pat").value == pytest.approx(crore(want["pat"][0]))


def test_a_small_whole_number_lined_up_with_a_column_of_decimals_is_not_a_figure():
    def word(text, x1):
        return nf.Word(x1 - 6 * len(text), x1, 100.0, 8.0, text)
    figures = [word(t, 330.0) for t in ("1,000.00", "50.10", "1,050.10", "200.00")]
    stray = word("24", 330.0)                       # lined up with the column, but a column of decimals has no such figure
    cols, align = nf.find_columns([(w, nf.parse_figure(w.text)) for w in figures], 8.0)
    cells = nf.assign_cells(figures + [stray] + [word("5", 200.0)], cols, align, 8.0)
    assert [w.text for _, w, _ in cells] == [w.text for w in figures]
    # in a column of whole numbers (a statement in whole crore) the same "24" is a figure
    whole = [word(t, 330.0) for t in ("1,000", "2,050", "1,050", "1,200")]
    cols2, _ = nf.find_columns([(w, nf.parse_figure(w.text)) for w in whole], 8.0)
    got = nf.assign_cells(whole + [stray], cols2, "right", 8.0)
    assert "24" in [w.text for _, w, _ in got]


# --- fix set 1 (TATAELXSI Q2FY27, 28 Oct 2026) -------------------------------------------------------------------------

def test_consolidated_as_a_verb_in_prose_is_not_a_consolidated_statement():
    assert not prd.names_consolidated("The Government of India has consolidated 29 labour laws into 4 Labour Codes")
    assert prd.names_consolidated("Statement of Consolidated Financial Results")
    assert prd.names_consolidated("Consolidated")
    assert prd.names_consolidated("The accounts of the subsidiaries have been consolidated")    # a group word near it
    assert prd.names_consolidated("the results of the Company and its subsidiaries are consolidated")
    assert not prd.names_consolidated("nothing about the basis here")


def untitled(rows, note: str):
    """A statement whose title names no basis, with a note line under the table."""
    pdf = statement(rows, title="Statement of Unaudited Financial Results")
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    doc[0].insert_text((LEFT, 800), note, fontsize=FONT)
    out = doc.tobytes()
    doc.close()
    return out


def test_an_untitled_table_is_standalone_when_consolidated_is_only_a_verb_in_a_note():
    rows, want = pl()
    prose = untitled(rows, "The Government of India has consolidated 29 labour laws into 4 Labour Codes.")
    assert read(prose, "pat").status == "ok" and read(prose, "pat").value == pytest.approx(crore(want["pat"][0]))
    group = untitled(rows, "The Consolidated Financial Results of the Group are given separately.")
    assert read(group, "pat").status == "none"      # a consolidated statement exists somewhere: the untitled basis is unproven


def test_a_unit_line_with_the_rupee_sign_glued_and_garbled_is_read():
    assert nf.scan_units(["tlakhs"]) == {100} and nf.scan_units(["(tlakhs)"]) == {100} and nf.scan_units(["₹crore"]) == {1}
    assert nf.scan_units(["tlakhsx"]) == set() and nf.scan_units(["Total lakhs of"]) == set()
    rows, want = pl()
    pdf = statement(rows, unit="tlakhs")
    assert read(pdf, "revenue").value == pytest.approx(crore(1000.00))


def words(*items):
    """Words on one line at a text height of 8: (x0, x1, text)."""
    return [nf.Word(x0, x1, 100.0, 8.0, text) for x0, x1, text in items]


def test_figures_with_space_separated_thousands_are_joined_only_when_they_touch():
    join = lambda *items: [w.text for w in nf.merge_space_groups(words(*items), 8.0)]     # noqa: E731
    assert join((278, 284, "23"), (286, 303, "909.66")) == ["23909.66"]
    assert join((557, 560, "3"), (562, 568, "02"), (570, 588, "060.27")) == ["302060.27"]              # Indian grouping
    assert join((100, 106, "(23"), (108, 125, "909.66)")) == ["(23909.66)"]
    assert join((200, 206, "24"), (208, 230, "1,245.60")) == ["24", "1,245.60"]     # a note number before a comma figure
    assert join((200, 206, "4"), (240, 257, "909.66")) == ["4", "909.66"]           # a column apart, not a group
    assert join((200, 206, "12"), (208, 214, "34")) == ["12", "34"]                 # no three-digit tail
    assert join((200, 206, "3"), (208, 214, "02"), (216, 225, "1060.27")) == ["3", "02", "1060.27"]   # tail of four digits
    assert join((200, 206, "3"), (208, 214, "02"), (216, 224, "060"), (226, 240, "060.27")) == \
        ["3", "02", "060", "060.27"]                                                 # mixed group widths: not joined


def test_a_statement_printed_with_space_separated_thousands_is_read():
    rows, want = pl(revenue=[1000.00, 900.50, 800.25, 3600.75])
    spaced = [(label, [f"{int(v) // 1000} {int(v) % 1000:03d}.{round(v * 100) % 100:02d}" if isinstance(v, float) and v >= 1000
                       else v for v in cells]) for label, cells in rows]
    pdf = statement(spaced)
    got = read(pdf, "pat")
    assert got.status == "ok" and got.value == pytest.approx(crore(want["pat"][0]))
    assert read(pdf, "revenue").value == pytest.approx(crore(1000.00))


SIX = [255, 315, 375, 435, 495, 555]


def q2_rows(break_half: bool = False):
    """A September-quarter statement of six columns (Q2, Q1, Q2 last year, H1, H1 last year, the year) that adds up down
    every column and across: H1 = Q2 + Q1 on every line (unless ``break_half``)."""
    base = {"rev": [1000.00, 900.50, 800.25], "oth": [50.10, 40.20, 30.30], "emp": [200.00, 190.00, 180.00],
            "oex": [500.25, 480.15, 470.95], "cur": [60.00, 55.00, 50.00]}
    for k, (q2, q1, py) in base.items():
        base[k] = [q2, q1, py, round(q2 + q1, 2), round(py * 2.1, 2), round((q2 + q1) * 1.9, 2)]
    if break_half:
        base["oex"][3] = round(base["oex"][3] + 7.0, 2)
    ti = cols_sum(base["rev"], base["oth"])
    te = cols_sum(base["emp"], base["oex"])
    pbt = [round(a - b, 2) for a, b in zip(ti, te)]
    pat = [round(a - b, 2) for a, b in zip(pbt, base["cur"])]
    rows = [(["Revenue from operations"], base["rev"]), (["Other income"], base["oth"]), (["Total income"], ti),
            (["Employee benefits expense"], base["emp"]), (["Other expenses"], base["oex"]), (["Total expenses"], te),
            (["Profit before tax"], pbt), (["Tax expense"], base["cur"]), (["Profit for the period"], pat)]
    return rows, pat


def q2_statement(rows):
    # the half years' header garbled as a scanner's layer has it: only "from April 01" is read, and as a year
    return statement(rows, cols=SIX, groups=["Quarter ended"] * 3 + ["Year to date from"] * 2 + ["Year ended"],
                     dates=["30.09.2026", "30.06.2026", "30.09.2025", "01.04.2026", "01.04.2025", "31.03.2026"])


def test_a_garbled_half_year_header_is_overruled_by_half_year_equals_two_quarters():
    rows, pat = q2_rows()
    pdf = q2_statement(rows)
    tables = nf.analyse(pdf)
    assert tables and not nf.layout_ok(tables[0].columns)      # the header alone does not fit a standard layout
    got = read(pdf, "pat")
    assert got.status == "ok" and got.value == pytest.approx(crore(pat[0]))
    assert read(pdf, "revenue").value == pytest.approx(crore(1000.00))


def test_no_answer_when_the_half_year_is_not_the_sum_of_the_two_quarters():
    rows, _ = q2_rows(break_half=True)
    assert read(q2_statement(rows), "pat").status == "none"


def test_previous_quarter_end():
    from datetime import date
    assert nf.previous_quarter_end(date(2026, 9, 30)) == date(2026, 6, 30)
    assert nf.previous_quarter_end(date(2026, 3, 31)) == date(2025, 12, 31)
    assert nf.previous_quarter_end(date(2026, 6, 30)) == date(2026, 3, 31)


def test_a_note_number_close_to_a_three_digit_figure_is_not_glued_to_it():
    join = lambda *items: [w.text for w in nf.merge_space_groups(words(*items), 8.0)]     # noqa: E731
    assert join((200, 204, "5"), (207, 225, "123.45")) == ["5", "123.45"]           # 3 pt apart at a height of 8
    assert join((200, 204, "5"), (206, 224, "123.45")) == ["5123.45"]               # 2 pt: a space inside one figure


def test_dates_the_header_words_dispute_are_still_used_by_the_half_year_sum():
    # BRIGHOTEL Q2FY27: every date is printed, but the title's "six months" and a "Year to date" read as a year disagree with
    # them, so the columns are dropped (date and kind None); the sum H1 = Q2 + Q1 on every line still tells the quarter
    def disputed(rows):
        tables = nf.analyse(statement(rows, cols=SIX, groups=["Quarter ended"] * 3 + ["Year to date"] * 2 + ["Year ended"],
                                      dates=["30.09.2026", "30.06.2026", "30.09.2025", "30.09.2026", "30.09.2025", "31.03.2026"]))
        for c in tables[0].columns:
            if c.index in (0, 3, 4):
                c.date, c.kind = None, None          # as column_kinds leaves a column whose sources disagree
        return nf.reading_from_tables(tables, "Q2FY27", "pat", "STANDALONE")
    rows, pat = q2_rows()
    got = disputed(rows)
    assert got.status == "ok" and got.value == pytest.approx(crore(pat[0]))
    broken, _ = q2_rows(break_half=True)
    assert disputed(broken).status == "none"


def as_ocr_boxes(pdf: bytes):
    """The words of a drawn page as OCR's boxes would give them: pixels at ``ocr.DPI``, one box a word."""
    from bse_intel import ocr
    k = ocr.DPI / 72
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return [([[x0 * k, y0 * k], [x1 * k, y0 * k], [x1 * k, y1 * k], [x0 * k, y1 * k]], text, 0.99)
                for x0, y0, x1, y1, text, *_ in doc[0].get_text("words")]


def test_a_unit_and_row_labels_the_text_layer_leaves_out_are_read_from_ocr(monkeypatch):
    # NESTLEIND Q2FY27: the figures are in the text layer, the title's unit and every row label are not
    from bse_intel import ocr
    monkeypatch.setattr(ocr, "available", lambda: True)
    rows, want = pl(exceptional=[5.0, 4.0, 3.0, 10.0])
    full = statement(rows)
    bare = statement([([""] * len(label), cells) for label, cells in rows], unit="")
    seen = as_ocr_boxes(full)
    got = {m: nf.reading_from_tables(nf.analyse(bare, ocr_boxes=lambda png: seen), "Q2FY27", m, "STANDALONE")
           for m in ("revenue", "pbt", "pat")}
    assert got["revenue"].value == pytest.approx(crore(1000.00))
    assert got["pbt"].value == pytest.approx(crore(want["pbt"][0]))          # not the line before the exceptional items
    assert got["pat"].value == pytest.approx(crore(want["pat"][0]))
    # without OCR the same page gives no answer (no unit)
    assert nf.reading_from_tables(nf.analyse(bare, ocr_boxes=lambda png: []), "Q2FY27", "pat", "STANDALONE").status == "none"


def test_ocr_never_changes_a_unit_the_text_layer_gives(monkeypatch):
    from bse_intel import ocr
    monkeypatch.setattr(ocr, "available", lambda: True)
    rows, want = pl()
    crore_page = statement(rows, unit="(Rs. in Crore)")
    lakh_ocr = as_ocr_boxes(statement(rows, unit="(Rs. in Lakhs)"))
    got = nf.reading_from_tables(nf.analyse(crore_page, ocr_boxes=lambda png: lakh_ocr), "Q2FY27", "pat", "STANDALONE")
    assert got.value == pytest.approx(want["pat"][0])                         # crore as printed, not divided by 100


# --- the second review's cases: OCR text is used only when it is proved to describe this page -------------------------

def bare_and_ocr(exceptional=(5.0, 4.0, 3.0, 10.0)):
    rows, want = pl(exceptional=list(exceptional))
    full = statement(rows)
    bare = statement([([""] * len(label), cells) for label, cells in rows], unit="")
    return bare, as_ocr_boxes(full), want


def pat_of(pdf, boxes):
    return nf.reading_from_tables(nf.analyse(pdf, ocr_boxes=lambda png: boxes), "Q2FY27", "pat", "STANDALONE")


def test_no_ocr_unit_when_the_layer_names_a_unit_elsewhere_on_the_page(monkeypatch):
    # the layer names two units in its notes (so it gives none); OCR that missed one of them must not decide
    from bse_intel import ocr
    monkeypatch.setattr(ocr, "available", lambda: True)
    bare, seen, _ = bare_and_ocr()
    doc = pymupdf.open(stream=bare, filetype="pdf")
    doc[0].insert_text((LEFT, 780), "(Rs. in Crore)", fontsize=FONT)
    doc[0].insert_text((LEFT, 800), "(Rs. in Lakhs)", fontsize=FONT)
    two_units = doc.tobytes()
    doc.close()
    assert pat_of(two_units, seen).status == "none"


def test_ocr_is_aligned_only_when_its_figures_sit_on_the_layers_cells():
    from bse_intel import ocr
    bare, seen, _ = bare_and_ocr()
    k = 72 / ocr.DPI

    def as_words(boxes):
        return nf.straighten([(x0 * k, y0 * k, x1 * k, y1 * k, t) for x0, y0, x1, y1, t in nf.words_from_boxes(boxes)], True)

    table = nf.analyse(bare, ocr_boxes=lambda png: [], keep_unnamed=True)[0]
    assert nf.ocr_aligned(table, as_words(seen), 8.0)
    shifted = [([[x, y + 12 / k] for x, y in box], text, score) for box, text, score in seen]        # 12 pt lower
    assert not nf.ocr_aligned(table, as_words(shifted), 8.0)


def test_ocr_labels_are_not_used_when_many_rows_stay_unlabelled(monkeypatch):
    # the second review's case: a part of the labels, on the wrong rows ("Profit before tax" on the current tax row), gave a
    # wrong profit before tax and profit; with fewer than nine rows in ten labelled no OCR label is used, so no answer
    from bse_intel import ocr
    monkeypatch.setattr(ocr, "available", lambda: True)
    rows, want = pl(exceptional=[5.0, 4.0, 3.0, 10.0])
    scrambled = ["", "Other income", "Total income (I+II)", "Employee benefits expense", "", "", "Other expenses", "", "", "",
                 "", "Profit before tax (V-VI)", "Deferred tax", "Total tax expense", "Profit for the period"]
    ocr_view = statement([([lb], cells) for lb, (_, cells) in zip(scrambled, rows)])
    bare = statement([([""], cells) for _, cells in rows])           # the same rows, at the same heights, with no labels
    got = {m: nf.reading_from_tables(nf.analyse(bare, ocr_boxes=lambda png: as_ocr_boxes(ocr_view)), "Q2FY27", m, "STANDALONE")
           for m in ("pbt", "pat", "tax")}
    assert all(r.status == "none" or r.value == pytest.approx(crore(want[m][0])) for m, r in got.items()), got   # never wrong


def test_no_ocr_text_on_a_rotated_page(monkeypatch):
    from bse_intel import ocr
    monkeypatch.setattr(ocr, "available", lambda: True)
    bare, seen, _ = bare_and_ocr()
    doc = pymupdf.open(stream=bare, filetype="pdf")
    doc[0].set_rotation(90)
    turned = doc.tobytes()
    doc.close()
    assert pat_of(turned, seen).status == "none"


def test_the_half_year_sum_needs_the_september_column_before_june():
    rows, _ = q2_rows()
    swapped = [(label, [cells[1], cells[0]] + cells[2:]) for label, cells in rows]    # June printed first, September second
    tables = nf.analyse(statement(swapped, cols=SIX, groups=["Quarter ended"] * 3 + ["Year to date"] * 2 + ["Year ended"],
                                  dates=["30.06.2026", "30.09.2026", "30.09.2025", "30.09.2026", "30.09.2025", "31.03.2026"]))
    for c in tables[0].columns:
        if c.index in (1, 3, 4):
            c.date, c.kind = None, None
    assert nf.reading_from_tables(tables, "Q2FY27", "pat", "STANDALONE").status == "none"


def test_a_unit_line_that_names_no_currency_or_names_it_after_the_unit_is_read():
    # SONACOMS Q2FY27 (OCR of a scan): "(Figures in Million , except per share data, unless stated otherwise)" and, on the
    # consolidated page, "(Figures in Million ₹, except ...)"
    assert nf.scan_units(["(Figures in Million , except per share data, unless stated otherwise)"]) == {10}
    assert nf.scan_units(["(Figures in Million ₹, except per share data, unless stated otherwise)"]) == {10}
    assert nf.scan_units(["(All amounts in Crores, unless otherwise stated)"]) == {1}
    assert nf.scan_units(["(Amounts in Lakhs)"]) == {100}
    assert nf.scan_units(["Figures in million tonnes"]) == set()           # a quantity, not money
    assert nf.scan_units(["The figures in millions are"]) == set()


# --- fix set 3 (SONACOMS, ATUL, TBZ) -------------------------------------------------------------------------------------

def test_one_wider_garbled_figure_does_not_move_a_columns_edge_off_the_others():
    # ATUL Q2FY27: garbled wider figures ("1,958.111") in the half-year column put its right edge 9 pt right of the other
    # figures, which were then not assigned to the column; the edge is now the figures' median right edge
    h = 8.0
    figs = [nf.Word(x1 - 30, x1, 100.0 + 10 * i, h, text) for i, (x1, text) in
            enumerate([(300, "1,623.46"), (300, "1,588.60"), (300, "1,409.52"), (300, "3,212.06"), (300, "2,714.08"),
                       (304, "1,958.111"), (309, "2,958.1111")])]
    cols, align = nf.find_columns([(w, nf.parse_figure(w.text)) for w in figs], h)
    assert align == "right" and len(cols) == 1 and cols[0].x1 == 300
    assigned = nf.assign_cells(figs, cols, align, h)
    assert {w.text for _, w, _ in assigned} >= {"1,623.46", "1,588.60", "1,409.52", "3,212.06", "2,714.08"}


def test_a_border_drawn_as_a_letter_inside_a_header_date_is_ignored():
    # ATUL Q2FY27: "September 30," / "I" (a table rule) / "2026" over the quarter column
    doc = pymupdf.open(stream=statement(pl()[0], dates=["September 30,", "30.06.2026", "30.09.2025", "31.03.2026"]), filetype="pdf")
    page = doc[0]
    right(page, COL_RIGHT[0], 100, "2026")
    page.insert_text((COL_RIGHT[0] - 48, 96), "I", fontsize=FONT)
    pdf = doc.tobytes()
    doc.close()
    from datetime import date
    assert nf.analyse(pdf)[0].columns[0].date == date(2026, 9, 30)


def with_image(pdf: bytes) -> bytes:
    """The page with a small picture on it, as a scan with a text layer has."""
    import io
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
    doc[0].insert_image(pymupdf.Rect(560, 20, 580, 40), pixmap=pix)
    out = doc.tobytes()
    doc.close()
    return out


def test_a_scan_whose_layer_garbled_the_dates_is_read_with_ocr(monkeypatch):
    # TBZ Q2FY27: the layer prints "30-Seo-26" for every September date; OCR reads them (two-digit years: the maintenance flag)
    from bse_intel import ocr
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setenv("PDF_DATES_2DIGIT", "1")
    rows, want = pl()
    garbled = with_image(statement(rows, dates=["30-Seo-26", "30-Jun-26", "30-Seo-25", "31-Mar-26"]))
    clean = as_ocr_boxes(statement(rows, dates=["30-Sep-26", "30-Jun-26", "30-Sep-25", "31-Mar-26"]))
    assert nf.reading_from_tables(nf.analyse(garbled, ocr_boxes=lambda png: []), "Q2FY27", "pat", "STANDALONE").status == "none"
    got = nf.reading_from_tables(nf.analyse(garbled, ocr_boxes=lambda png: clean, ocr_garbled=True), "Q2FY27", "pat", "STANDALONE")
    assert got.status == "ok" and got.value == pytest.approx(crore(want["pat"][0])) and got.source == "ocr"
    # OCR that reads no more dates than the layer does not replace the layer's tables: here the layer misses one date only
    # and answers itself; OCR seeing the same page answers nothing new and the answer stays the layer's
    partly = with_image(statement(rows, dates=["30-Sep-26", "30-Jun-26", "30-Seo-25", "31-Mar-26"]))
    same = as_ocr_boxes(statement(rows, dates=["30-Sep-26", "30-Jun-26", "30-Seo-25", "31-Mar-26"]))
    kept = nf.reading_from_tables(nf.analyse(partly, ocr_boxes=lambda png: same, ocr_garbled=True), "Q2FY27", "pat", "STANDALONE")
    assert kept.status == "ok" and kept.source == "textlayer"


def test_a_page_is_ocrd_once_in_one_analyse(monkeypatch):
    # a scan's layer with no unit and garbled dates: the unit fill and the garbled-page read both want the page's OCR, and
    # the page is rendered and OCR'd once, the boxes shared (item 123)
    from bse_intel import ocr
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setenv("PDF_DATES_2DIGIT", "1")
    rows, want = pl()
    garbled = with_image(statement(rows, unit="", dates=["30-Seo-26", "30-Jun-26", "30-Seo-25", "31-Mar-26"]))
    clean = as_ocr_boxes(statement(rows, dates=["30-Sep-26", "30-Jun-26", "30-Seo-25", "31-Mar-26"]))
    calls = []

    def ocr_boxes(png):
        calls.append(png)
        return clean

    nf.analyse(garbled, ocr_boxes=ocr_boxes, ocr_garbled=True)
    assert len(calls) == 1


def test_a_date_with_the_comma_glued_to_the_year_is_read():
    # LOTUSDEV Q2FY27: "Sep 30,2026" over every column
    from datetime import date
    assert nf._dates_in_text("Sep 30,2026") == [date(2026, 9, 30)]
    assert nf._dates_in_text("September 30,2026") == [date(2026, 9, 30)]
    assert nf._dates_in_text("1,2026 crore") == [] and nf._dates_in_text("12,345.67") == []
    rows, want = pl()
    pdf = statement(rows, dates=["Sep 30,2026", "June 30,2026", "Sep 30,2025", "Mar 31,2026"])
    assert read(pdf, "pat").value == pytest.approx(crore(want["pat"][0]))


def test_day_numbers_of_stacked_header_dates_are_not_a_row_of_figures():
    # KIRLPNU Q2FY27 prints whole figures and "Sept 30" over "2026" in every column; the 30s lined up as a numeric row and
    # cut the header off the table (end to end: KIRLPNU in the normal key, 8 of 8)
    line = words((289, 319, "Sept"), (321, 330, "30"), (359, 376, "Jun"), (378, 387, "30,"), (500, 510, "30"),
                 (600, 640, "Margin"), (641, 650, "12"), (700, 720, "May"), (740, 749, "15"))
    parts = sorted((w.x0, w.text) for w in line if id(w) in nf.date_parts(line, 8.0))
    assert parts == [(321, "30"), (378, "30,")]   # "30" alone (x 500) is a figure; "15" stands apart from "May"
    # "Margin 12" stays a figure since the one month rule (TODO 123 part 5): the old prefix rule read "Margin" as "mar..."


# --- fix set 6 (ORIENTCEM) -----------------------------------------------------------------------------------------------

def test_consolidated_called_not_applicable_by_a_company_without_subsidiaries_is_no_consolidated_statement():
    page = ("the Company does not have any subsidiary including an associate and joint venture. Accordingly, preparation \n"
            "of consolidated financial results is not applicable.")
    assert not prd.names_consolidated(page)
    # "not applicable" said of an earlier period by a company that has subsidiaries: a consolidated statement exists
    assert prd.names_consolidated("Consolidated figures for the corresponding quarter are not applicable as the subsidiary was "
                                  "acquired in July.")
    assert prd.names_consolidated("The Company has no subsidiary. Statement of Consolidated Financial Results")


def whole_statement(serial: bool = False, eps: bool = True):
    """ORIENTCEM's layout: crore in small whole figures, three quarter columns of whole numbers below a thousand (no comma, no
    decimals) and three half-year / year columns of larger figures; optionally a serial-number column left of the labels."""
    q = {"rev": [565, 604, 643], "oth": [13, 5, 12], "emp": [35, 34, 33], "oex": [440, 480, 500], "tax": [12, 25, 30]}
    big = {"rev": [1169, 1510, 2793], "oth": [18, 14, 23], "emp": [69, 65, 130], "oex": [920, 1100, 2100], "tax": [37, 60, 110]}
    cols = {k: q[k] + big[k] for k in q}
    ti = [a + b for a, b in zip(cols["rev"], cols["oth"])]
    te = [a + b for a, b in zip(cols["emp"], cols["oex"])]
    pbt = [a - b for a, b in zip(ti, te)]
    pat = [a - b for a, b in zip(pbt, cols["tax"])]
    lines = [("Revenue from operations", cols["rev"]), ("Other income", cols["oth"]), ("Total income", ti),
             ("Employee benefits expense", cols["emp"]), ("Other expenses", cols["oex"]), ("Total expenses", te),
             ("Profit before tax", pbt), ("Tax expense", cols["tax"]), ("Profit for the period", pat)]
    rows = [([label], [f"{v:,}" for v in cells]) for label, cells in lines]
    if eps:
        rows.append((["Basic EPS"], ["1.56", "1.61", "1.70", "3.17", "3.30", "6.40"]))
    pdf = statement(rows, unit="(Rs. in Crore)", cols=SIX, groups=["Quarter ended"] * 3 + ["Six months ended"] * 2 + ["Year ended"],
                    dates=["30.09.2026", "30.06.2026", "30.09.2025", "30.09.2026", "30.09.2025", "31.03.2026"])
    if serial:
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        for i in range(len(rows)):
            right(doc[0], LEFT - 6, 130 + 19 * i, str(i + 1))
        pdf = doc.tobytes()
        doc.close()
    return pdf, dict(rev=cols["rev"][0], ti=ti[0], pbt=pbt[0], pat=pat[0])


def test_columns_of_small_whole_figures_are_read_on_the_grid_of_the_larger_ones(monkeypatch):
    pdf, want = whole_statement()
    table = nf.analyse(pdf)[0]
    assert len(table.columns) == 6 and [c.whole for c in table.columns] == [True, True, True, False, False, False]
    assert read(pdf, "revenue").value == pytest.approx(want["rev"]) and read(pdf, "pat").value == pytest.approx(want["pat"])
    assert read(pdf, "pbt").value == pytest.approx(want["pbt"])
    monkeypatch.setattr(nf, "whole_number_columns", lambda *a, **k: [])
    assert read(pdf, "pat").status == "none"                                   # the strict figures alone make no quarter columns


def test_a_serial_number_column_left_of_the_labels_is_not_a_column_of_figures():
    pdf, want = whole_statement(serial=True)
    assert all(not (c.whole and c.x1 < LEFT) for c in nf.analyse(pdf, keep_unnamed=True)[0].columns)
    assert read(pdf, "pat").value == pytest.approx(want["pat"])


def test_a_consolidated_title_is_never_hidden_by_a_not_applicable_cell_below_it():
    # the sixth review's case: a no-subsidiary sentence, then a real consolidated title and a "Not applicable" cell
    assert prd.names_consolidated("The Company does not have any subsidiary. Statement of Consolidated Financial Results\n"
                                  "Sr No Particulars\n1 Segment Note: Not applicable")
    assert prd.names_consolidated("The Company has no subsidiary in India.\nStatement of Consolidated Financial Results (segment "
                                  "reporting is not applicable)")


def scanned(pdf: bytes, letter: str) -> bytes:
    """A two-page filing: a typed covering letter, then the statement as a picture with no text layer (CMPDI, RIR)."""
    src = pymupdf.open(stream=pdf, filetype="pdf")
    pix = src[0].get_pixmap(dpi=72)
    out = pymupdf.open()
    first = out.new_page(width=620, height=842)
    first.insert_text((LEFT, 60), letter, fontsize=FONT)
    second = out.new_page(width=620, height=842)
    second.insert_image(second.rect, pixmap=pix)
    data = out.tobytes()
    out.close()
    src.close()
    return data


def test_an_untitled_scanned_statement_is_standalone_once_ocr_finds_no_consolidated_page(monkeypatch):
    from bse_intel import ocr
    monkeypatch.setattr(ocr, "available", lambda: True)
    rows, want = pl()
    page = statement(rows, title="Statement of Unaudited Financial Results")
    pdf = scanned(page, "Please find enclosed the Standalone Un-Audited Financial Results for the quarter.")
    boxes = as_ocr_boxes(page)

    def got(ocr_boxes):
        return nf.reading_from_tables(nf.analyse(pdf, ocr_boxes=ocr_boxes), "Q2FY27", "pat", "STANDALONE")

    assert got(lambda png: boxes).value == pytest.approx(crore(want["pat"][0]))
    # OCR of the scanned page names a consolidated statement: the untitled table's basis stays unproven
    noted = as_ocr_boxes(untitled(rows, "Statement of Consolidated Financial Results is on the next page."))
    assert got(lambda png: noted).status == "none"


def test_a_garbled_consolidated_in_ocr_still_leaves_the_basis_unproven():
    for garbled in ("C0NSOLIDATED FINANCIAL RESULTS", "Consolldated Results", "Consoli-\\ndated", "CONSOL IDATED",
                    "StatementofConsolidatedFinancialResults", "Coxsolidated", "Group Financial Results"):
        assert nf._LOOSE_CONSOLIDATED.search(garbled)
    assert not nf._LOOSE_CONSOLIDATED.search("Statement of Unaudited Standalone Financial Results; the Company considers")


def test_the_scanned_standalone_rule_needs_the_word_standalone_and_reaches_only_scanned_pages(monkeypatch):
    from bse_intel import ocr
    monkeypatch.setattr(ocr, "available", lambda: True)
    rows, want = pl()
    page = statement(rows, title="Statement of Unaudited Financial Results")
    silent = scanned(page, "Please find enclosed the Un-Audited Financial Results for the quarter.")     # no "standalone"
    assert nf.reading_from_tables(nf.analyse(silent, ocr_boxes=lambda png: as_ocr_boxes(page)), "Q2FY27", "pat",
                                  "STANDALONE").status == "none"


def test_a_profit_after_tax_carried_on_by_an_associates_share_is_not_the_profit_for_the_period():
    # EMKAY Q2FY25 consolidated: "IX Profit after tax" 2,581.77, "X Share of Profit of Associates" 9.39, "XI Profit for the
    # period from continuing operations" 2,591.16; the reader gave IX (a wrong profit). It may give XI or nothing, never IX
    rows, want = pl()
    share = [9.39, -7.95, -35.5, 25.78]
    bottom = [round(a + b, 2) for a, b in zip(want["pat"], share)]
    rows = rows[:-1] + [(["Profit after tax"], want["pat"]), (["Share of Profit/(Loss) of Associates"], share),
                        (["Profit for the period from continuing operations"], bottom)]
    got = read(statement(rows), "pat")
    assert got.status == "none" or got.value == pytest.approx(crore(bottom[0]))
    assert got.value != pytest.approx(crore(want["pat"][0]))


@pytest.mark.parametrize("between,bottom_label", [
    ([("Share of profit of associates after tax", [9.39, -7.95, -35.5, 25.78])], "Profit for the period"),
    ([("Share of profit of associates after tax", [9.39, -7.95, -35.5, 25.78])], "Profit for the period from continuing operations"),
    ([("Sh4re of Pr0fit of Assoc1ates", [9.39, -7.95, -35.5, 25.78])], "Profit for the period from continuing operations"),
    ([("Other items", ["-", "-", "-", "-"]), ("Share of Profit of Associates", [9.39, -7.95, -35.5, 25.78])],
     "Profit for the period from continuing operations"),
    ([("Exceptional item after tax", [9.39, -7.95, -35.5, 25.78])], "Profit for the period from continuing operations"),
])
def test_a_profit_after_tax_carried_on_further_down_is_never_given_as_the_profit(between, bottom_label):
    # the ninth review's layouts: the intermediate profit after tax must not be the answer (the bottom line, or nothing)
    rows, want = pl()
    share = [c for c in between[-1][1]]
    bottom = [round(a + b, 2) for a, b in zip(want["pat"], share)]
    rows = rows[:-1] + [(["Profit after tax"], want["pat"])] + [([label], cells) for label, cells in between] \
        + [([bottom_label], bottom)]
    got = read(statement(rows), "pat")
    assert got.status == "none" or got.value == pytest.approx(crore(bottom[0])), got


@pytest.mark.parametrize("after", [
    [("Remeasurement of defined benefit plans", "oci"), ("Totl", "pat+oci")],
    [("Items not reclassified", "oci"), ("xx", "pat+oci")],
    [("0ther Compr3hensive Inc0me", "oci"), ("Tota1 Compr3hensive Inc0me", "pat+oci")],
    [("Remeasurement of defined benefit plans", "oci"), ("Net profit after OCI", "pat+oci")],
])
def test_other_comprehensive_income_with_garbled_labels_never_makes_the_total_the_profit(after):
    # the tenth review: total comprehensive income = profit + OCI is the same arithmetic as an associate's share carried on;
    # with labels that do not tell them apart, the profit is no answer, never the total
    rows, want = pl()
    pat, oci = want["pat"], [3.1, -2.0, 4.4, 1.5]
    values = {"oci": oci, "pat+oci": [round(a + b, 2) for a, b in zip(pat, oci)]}
    rows = rows[:-1] + [(["Profit after tax"], pat)] + [([label], values[v]) for label, v in after]
    got = read(statement(rows), "pat")
    assert got.status == "none" or got.value == pytest.approx(crore(pat[0])), got


def eleventh_review_rows(case: str):
    rows, want = pl()
    pat, sh, oci = want["pat"], [9.4, 5.1, 3.3, 12.2], [3.1, -2.0, 4.4, 1.5]
    add = lambda *xs: [round(sum(v), 2) for v in zip(*xs)]       # noqa: E731
    x = add(pat, sh)
    bad = [round(x[0] + 1.0, 2)] + x[1:]                         # a digit error in the period's own column
    extra = {"garbled share, bottom with a bad cell": [(["Shr of prfit"], sh), (["Net prfit"], bad)],
             "share, bad profit row, garbled total": [(["Share of profit of associates"], sh), (["Prfit"], bad),
                                                      (["Remeasurement x"], oci), (["Totl"], add(x, oci))],
             "clean control": [(["Share of profit of associates"], sh), (["Profit for the period"], x),
                               (["Other comprehensive income"], oci), (["Total comprehensive income"], add(x, oci))]}[case]
    return rows[:-1] + [(["Profit after tax"], pat)] + extra, crore(x[0])


@pytest.mark.parametrize("case", ["garbled share, bottom with a bad cell", "share, bad profit row, garbled total"])
def test_a_damaged_cell_in_a_carried_on_profit_never_gives_a_wrong_profit(case):
    # the eleventh review: these gave the profit before the share (2.142) and the total comprehensive income (2.267)
    rows, truth = eleventh_review_rows(case)
    got = read(statement(rows), "pat")
    assert got.status == "none" or got.value == pytest.approx(truth), got


def test_a_clean_associates_layout_still_gives_the_profit_for_the_period():
    rows, truth = eleventh_review_rows("clean control")
    assert read(statement(rows), "pat").value == pytest.approx(truth)


def test_an_unsure_profit_on_one_table_vetoes_a_short_table_of_the_same_basis():
    # the twelfth review: a second standalone table that stops at "Profit after tax" gave the profit before the share
    rows, want = pl()
    pat, sh = want["pat"], [9.4, 5.1, 3.3, 12.2]
    unsure = rows[:-1] + [(["Profit after tax"], pat), (["Shr of prfit"], sh),
                          (["Net prfit"], [round(a + b, 2) for a, b in zip(pat, sh)])]
    short = rows[:-1] + [(["Profit after tax"], pat)]
    doc = pymupdf.open()
    for part in (unsure, short):
        with pymupdf.open(stream=statement(part), filetype="pdf") as one:
            doc.insert_pdf(one)
    pdf = doc.tobytes()
    doc.close()
    assert read(pdf, "pat").status == "none"
    assert read(pdf, "pbt").value == pytest.approx(crore(want["pbt"][0]))       # only the profit is held back


def test_three_garbled_rows_between_still_mark_the_profit_as_carried_on():
    rows, want = pl()
    pat, parts = want["pat"], [[9.4, 5.1, 3.3, 12.2], [1.1, 0.4, 0.2, 2.5], [2.0, 1.5, 0.7, 3.3]]
    bottom = [round(a + b + c + d, 2) for a, b, c, d in zip(pat, *parts)]
    rows = rows[:-1] + [(["Profit after tax"], pat), (["Shr of prfit"], parts[0]), (["Prft frm disc ops"], parts[1]),
                        (["Other adjstmnt"], parts[2]), (["Net prfit"], bottom)]
    got = read(statement(rows), "pat")
    assert got.status == "none" or got.value == pytest.approx(crore(bottom[0])), got


def test_a_label_naming_oci_is_a_total_comprehensive_income_not_a_profit():
    assert nf.label_class("Profit after tax and OCI") == "TCI"
    assert nf.label_class("Profit for the period (after OCI)") == "TCI"
    assert nf.label_class("Profit for the period") == "PAT"


def test_a_discontinued_block_with_its_own_subtotal_still_gives_the_profit_for_the_period():
    # ABREL Q2FY27: 9 profit from continuing operations, 11 profit of discontinued operations, 13 its tax, 14 their net,
    # 15 profit for the period = 9 + 14; asking for 11 and 13 in the sum as well lost the answer
    rows, want = pl()
    cont = want["pat"]
    disc, dtax = [-19.33, 42.59, 86.19, 240.15], [-73.4, -10.22, -30.91, 12.99]
    net = [round(a + b, 2) for a, b in zip(disc, dtax)]
    total = [round(a + b, 2) for a, b in zip(cont, net)]
    rows = rows[:-1] + [(["Net Profit for the period from continuing operations"], cont),
                        (["Profit/(loss) from discontinued operations"], disc),
                        (["Tax (expenses)/credit of discontinued operations"], dtax),
                        (["Net Profit for the period from discontinued operations"], net),
                        (["Net Profit for the period (9 + 14)"], total)]
    got = read(statement(rows), "pat")
    assert got.status == "ok" and got.value == pytest.approx(crore(total[0])), got


def test_a_discontinued_row_no_subtotal_accounts_for_is_never_skipped():
    # the fourteenth review: discontinued profit d and its tax dt, "Profit for the period" = a + d (skipping dt), then the
    # true "Net profit for the period" = a + d - dt; the reader gave a + d
    rows, want = pl()
    a = want["pat"]
    d, dt = [4.0, 3.0, 2.0, 9.0], [1.2, 0.9, 0.6, 2.7]
    first = [round(x + y, 2) for x, y in zip(a, d)]
    true = [round(x + y - z, 2) for x, y, z in zip(a, d, dt)]
    rows = rows[:-1] + [(["Profit after tax from continuing operations"], a), (["Profit from discontinued operations"], d),
                        (["Tax expense of discontinued operations"], dt), (["Profit for the period"], first),
                        (["Net profit for the period"], true)]
    got = read(statement(rows), "pat")
    assert got.status == "none" or got.value == pytest.approx(crore(true[0])), got


def test_a_header_date_whose_year_ocr_read_before_the_day_is_read():
    # PNGSREVA Q2FY27 (OCR): "September" / "2026" / "30," over the quarter column
    from datetime import date
    h = 8.0
    head = words((300, 340, "September"), (310, 330, "2026"), (342, 352, "30,"))
    head[1].y, head[2].y = 99.0, 100.5
    col = [nf.Column(300, 352, 326, 0), nf.Column(400, 452, 426, 1)]
    assert nf.column_dates(head, col, h, 2.0)[0] == date(2026, 9, 30)


def test_a_gross_discontinued_row_above_its_net_is_not_a_subtotal():
    # the fifteenth review: d (pre-tax), dt (tax), n = d - dt; "Profit for the period" = a + d leaves out dt and n, and d = dt + n
    # made the gross row look like their subtotal
    rows, want = pl()
    a = want["pat"]
    d, dt = [4.0, 3.0, 2.0, 9.0], [1.2, 0.9, 0.6, 2.7]
    n = [round(x - y, 2) for x, y in zip(d, dt)]
    rows = rows[:-1] + [(["Profit after tax from continuing operations"], a), (["Profit from discontinued operations"], d),
                        (["Tax expense of discontinued operations"], dt), (["Profit from discontinued operations (net)"], n),
                        (["Profit for the period"], [round(x + y, 2) for x, y in zip(a, d)])]
    got = read(statement(rows), "pat")
    assert got.status == "none" or got.value == pytest.approx(crore(round(a[0] + n[0], 2))), got


def test_the_header_year_reorder_takes_only_a_day_that_ends_a_period():
    from datetime import date
    assert nf.header_dates("September 2026 30,") == [date(2026, 9, 30)]
    for trap in ("Year ended March 2026 12 months", "Quarter ended September 2026 3 months ended", "Dec 2026 9 months",
                 "September 2026 3"):
        assert nf.header_dates(trap) == []


def test_a_statement_on_the_fourteenth_scanned_page_is_reached(monkeypatch):
    # ATGL Q2FY27: thirteen scanned pages; the standalone statement on page 14 was past the old OCR budget of 8 pages
    from bse_intel import ocr
    monkeypatch.setattr(ocr, "available", lambda: True)
    rows, want = pl()
    page = statement(rows)
    src = pymupdf.open(stream=page, filetype="pdf")
    pix = src[0].get_pixmap(dpi=36)
    doc = pymupdf.open()
    for i in range(14):
        p = doc.new_page(width=620, height=842)
        p.insert_image(p.rect, pixmap=pix)
    pdf = doc.tobytes()
    doc.close()
    src.close()
    boxes, calls = as_ocr_boxes(page), []

    def ocr_boxes(png):
        calls.append(1)
        return boxes if len(calls) == 14 else []

    got = nf.reading_from_tables(nf.analyse(pdf, ocr_boxes=ocr_boxes), "Q2FY27", "pat", "STANDALONE")
    assert got.status == "ok" and got.value == pytest.approx(crore(want["pat"][0]))


def test_standalone_said_only_on_another_scanned_page_does_not_label_an_untitled_scan(monkeypatch):
    # the sixteenth review: the evidence must come from a typed page or from OCR of the table's own page
    from bse_intel import ocr
    monkeypatch.setattr(ocr, "available", lambda: True)
    rows, want = pl()
    page = statement(rows, title="Statement of Unaudited Financial Results")
    src = pymupdf.open(stream=page, filetype="pdf")
    pix = src[0].get_pixmap(dpi=36)
    doc = pymupdf.open()
    first = doc.new_page(width=620, height=842)
    first.insert_text((LEFT, 60), "Please find enclosed the Un-Audited Financial Results for the quarter.", fontsize=FONT)
    for _ in range(2):
        p = doc.new_page(width=620, height=842)
        p.insert_image(p.rect, pixmap=pix)
    pdf = doc.tobytes()
    doc.close()
    src.close()
    note = as_ocr_boxes(statement([(["Note"], [1.0, 2.0, 3.0, 4.0])], title="Notes to the Standalone Financial Results"))
    calls = []

    def ocr_boxes(png):
        calls.append(1)
        return note if len(calls) == 1 else as_ocr_boxes(page)        # "Standalone" on page 2's OCR, the statement on page 3

    got = nf.reading_from_tables(nf.analyse(pdf, ocr_boxes=ocr_boxes), "Q2FY27", "pat", "STANDALONE")
    assert got.status == "none"


def test_a_disputed_header_date_does_not_count_as_a_usable_date():
    # RADICO Q2FY27: the layer read every date but the header words disputed two; counting those made the page look dated,
    # so its garbled layer was never read with OCR (end to end: RADICO in the normal key, standalone 4 of 4)
    from datetime import date
    rows, _ = q2_rows()
    table = nf.analyse(q2_statement(rows))[0]
    for c in table.columns[3:5]:
        c.read_date, c.date = c.date or date(2026, 9, 30), None          # as column_kinds leaves a disputed column
    assert nf.usable_dates([table]) == 4


def test_ocr_spellings_of_month_names_in_a_header_still_give_dates():
    # NEWGEN Q2FY27: OCR read "30 Septemher 2026" and "30 Seplember 2025"; a word near no single month stays as it is
    assert nf.header_dates("Quarter ended 30 Septemher 2026 30 Seplember 2025") == [date(2026, 9, 30), date(2025, 9, 30)]
    assert nf.header_dates("30June 2026") == [date(2026, 6, 30)]
    # the fuzzy path proper: the first letters themselves garbled
    assert nf.header_dates("31 Dccember 2025 31 Qctober 2025") == [date(2025, 12, 31), date(2025, 10, 31)]
    assert nf.header_dates("Number of shares 2026") == []
    assert nf.mend_months("remember member employee") == "remember member employee"


def test_amount_in_rupees_lakhs_line_names_the_unit_even_with_ocr_spellings():
    # NEWGEN Q2FY27: "(Amunt in Rupees lakhs)" and "(Amount in Rupces lakhs)"; the unit word itself must be clear
    assert nf.scan_units(["(Amunt in Rupees lakhs)"]) == {100}
    assert nf.scan_units(["(Amount in Rupces lakhs)"]) == {100}
    assert nf.scan_units(["{Amount in Runees lnkhs)"]) == set()
    assert nf.scan_units(["Amount in kind lakhs"]) == set()


def nested_other_income(rows, others_shift=0.0):
    # PRIMESECU Q4FY24: other income printed as its parts and their subtotal between revenue and total income
    interest = [30.00, 25.10, 20.00, 100.00]
    others = [round(o - i + others_shift, 2) for o, i in zip(OTHER, interest)]
    return rows[:1] + [(["Other income", "i) Interest income"], interest), (["ii) Others"], others),
                       (["Total other income"], OTHER)] + rows[2:]


def test_total_income_over_an_other_income_subtotal_printed_with_its_parts():
    rows, want = pl()
    pdf = statement(nested_other_income(rows))
    assert read(pdf, "revenue").value == pytest.approx(crore(1000.00))
    assert read(pdf, "other_income").value == pytest.approx(crore(50.10))
    assert read(pdf, "total_income").value == pytest.approx(crore(want["total_income"][0]))
    assert read(pdf, "pat").value == pytest.approx(crore(want["pat"][0]))
    # parts that do not add up to the subtotal: the nesting is not proved and nothing is named
    broken = statement(nested_other_income(rows, others_shift=7.0))
    assert read(broken, "revenue").status != "ok" and read(broken, "pat").status != "ok"


def revenue_in_parts(rows, n_parts=3):
    # BFINVEST Q2FY25: "1 Revenue from operations (a) Interest income", "(b) Dividend income", ... and no line for the revenue
    shares = [0.5, 0.3, 0.2] if n_parts == 3 else [0.6, 0.4]
    parts = [[round(v * s, 2) for v in REVENUE] for s in shares[:-1]]
    parts.append([round(v - sum(p[j] for p in parts), 2) for j, v in enumerate(REVENUE)])
    names = [["1 Revenue from operations", "(a) Interest income"], ["(b) Dividend income"], ["(c) Net gain on fair value changes"]]
    return [(names[i] if i < n_parts - 1 else names[2], parts[i]) for i in range(n_parts)] + rows[1:]


def test_revenue_printed_only_as_its_parts_is_their_sum():
    rows, want = pl()
    for n in (3, 2):
        pdf = statement(revenue_in_parts(rows, n))
        assert read(pdf, "revenue").value == pytest.approx(crore(1000.00)), n     # never the first part alone
        assert read(pdf, "other_income").value == pytest.approx(crore(50.10))
        assert read(pdf, "total_income").value == pytest.approx(crore(want["total_income"][0]))
        assert read(pdf, "pat").value == pytest.approx(crore(want["pat"][0]))


def test_revenue_parts_that_do_not_add_up_or_a_list_item_other_income_give_no_answer():
    rows, want = pl()
    parts = revenue_in_parts(rows, 3)
    parts[1] = (parts[1][0], [v + 1 for v in parts[1][1]])                      # one part off by one: nothing proved
    assert read(statement(parts), "revenue").status != "ok"
    # "(c) Other income" right after a revenue list may be one of its parts: neither it nor the revenue is named
    listed = revenue_in_parts(rows, 2)
    listed[2] = (["(c) Other income"], OTHER)
    pdf = statement(listed)
    assert read(pdf, "other_income").status != "ok" and read(pdf, "revenue").status != "ok"
    # a note reference is not a list: "Revenue from operations (1) refer note 3" is the revenue itself
    assert not nf._REVENUE_LIST.search("Revenue from operations (1) refer note 3")
    assert nf._REVENUE_LIST.search("1 Revenue from operations (a) Interest income")
    noted = [(["Revenue from operations (1) refer note 3"], REVENUE)] + rows[1:]
    assert read(statement(noted), "revenue").value == pytest.approx(crore(1000.00))


@pytest.mark.parametrize("first", ["(a) Note income", "(a) Referral fees", "a) See above", "I. Interest income", "[a] Sales",
                                   "(a) 1"])
def test_a_first_part_of_revenue_is_never_the_revenue_whatever_its_marker_or_word(first):
    # nineteenth review: "Revenue from operations" over "(a) Note income" and one more part gave part (a) as the revenue
    rows, want = pl()
    parts = revenue_in_parts(rows, 2)
    parts[0] = (["Revenue from operations", first], parts[0][1])
    got = read(statement(parts), "revenue")
    assert got.status != "ok" or got.value == pytest.approx(crore(1000.00))


def test_list_items_and_statement_numbering_are_told_apart():
    assert all(nf.list_item(x) for x in ("(c) Other income", "B. Other income", "c. Other income", "(xi) Others", "(c)Other income"))
    assert not any(nf.list_item(x) for x in ("II. Other income", "2 Other income", "II Other income", "Other income"))


def test_a_glued_garbled_title_in_the_layer_names_the_basis():
    # SUNDARMFIN Q4FY24: the garbled layer runs the title together and OCR cannot read it (big type)
    assert nf.layer_basis("=E. I En :STATEMENTOFAUDITEDCONSOLIl)ATEDFINANCIALRESULTSFORTHEQUARTERANI)YEARENDED31.03.20Z4") == "CONSOLIDATED"
    assert nf.layer_basis("STATEMENTOFUNAUDITEDSTANDALONEFINANCIALRESULTS") == "STANDALONE"
    assert nf.layer_basis("STATEMENTOFCONSOLEFINANCIALRESULTS") is None
    assert nf.layer_basis("STATEMENTOFAUDITEDCONSOLIDATEDFINANCIALRESULTS\nSTATEMENTOFAUDITEDSTANDALONEFINANCIALRESULTS") is None


@pytest.mark.parametrize("second", ["Dividend income", "- Dividend", "1. Dividend", "Add: Dividend"])
def test_a_revenue_row_followed_by_an_unnamed_row_is_not_named_alone(second):
    # twentieth review: "Revenue from operations" over parts marked any way, or not at all, gave the first part as revenue
    rows, want = pl()
    parts = revenue_in_parts(rows, 2)
    parts[0] = (["Revenue from operations", "Sale of products"], parts[0][1])
    parts[1] = ([second], parts[1][1])
    got = read(statement(parts), "revenue")
    assert got.status != "ok" or got.value == pytest.approx(crore(1000.00))


def test_a_glued_title_never_reads_unconsolidated_or_a_spaced_note_naming_both():
    assert nf.layer_basis("STATEMENTOFUNCONSOLIDATEDFINANCIALRESULTS") is None
    assert nf.layer_basis("These standalone results should be read with the Statement of Consolidated Financial Results") is None


def test_an_unnamed_row_above_the_revenue_row_keeps_it_from_being_the_revenue():
    # twenty-first review: "Interest income" (no landmark) over "Net sales" gave the net sales alone as the revenue
    rows, want = pl()
    a = [round(v * 0.6, 2) for v in REVENUE]
    b = [round(v - x, 2) for v, x in zip(REVENUE, a)]
    got = read(statement([(["Interest income"], a), (["Net sales"], b)] + rows[1:]), "revenue")
    assert got.status != "ok" or got.value == pytest.approx(crore(1000.00))


def test_a_title_naming_the_basis_and_a_line_naming_the_other_give_none():
    assert nf.layer_basis("STATEMENTOFSTANDALONEFINANCIALRESULTS\nConsolidated results are separately filed") is None
    assert nf.layer_basis("STATEMENTOFAUDITEDCONSOLIDATEDFINANCIALRESULTS\nStandalone figures are given in a separate statement") is None
    assert nf.layer_basis("STATEMENT OF NON CONSOLIDATED FINANCIAL RESULTS") is None
    assert nf.layer_basis("STATEMENTOFAUDITEDCONSOLIl)ATEDFINANCIALRESULTSFORTHEQUARTER") == "CONSOLIDATED"


def test_a_total_revenue_line_with_a_line_reference_is_the_revenue():
    # EMKAY Q2FY25: "Total Revenue from Operations (1)" is the total, not a list opened by "(1)"
    assert not nf._REVENUE_LIST.search("Total Revenue from Operations (1)")
    rows, want = pl()
    rows[0] = (["Total Revenue from Operations (1)"], REVENUE)
    assert read(statement(rows), "revenue").value == pytest.approx(crore(1000.00))


def test_a_non_consolidated_title_is_never_consolidated():
    # twenty-second review: the text layer's own title path read "Non-Consolidated" as consolidated
    rows, want = pl()
    pdf = statement(rows, title="Statement of Unaudited Non-Consolidated Financial Results")
    assert read(pdf, "pat", basis="CONSOLIDATED").status != "ok"
    assert nf.layer_basis("Statement of Unaudited Non-\nConsolidated Financial Results") is None


def test_a_total_that_leaves_the_revenue_row_above_it_out_names_no_revenue():
    # twenty-second review: "Revenue from operations" over "Interest income" + "Other income" = a total of the two
    rows, want = pl()
    interest = [round(v * 0.6, 2) for v in REVENUE]
    total = cols_sum(interest, OTHER)
    tail = rows[3:]
    got = statement([(["Revenue from operations"], REVENUE), (["Interest income"], interest), (["Other income"], OTHER),
                     (["Total income"], total)] + tail)
    r = read(got, "revenue")
    assert r.status != "ok" or r.value == pytest.approx(crore(1000.00))


@pytest.mark.parametrize("title", ["Statement of Unaudited Financial Results (Not-Consolidated)",
                                   "Statement of Unaudited Financial Results (Un consolidated)"])
def test_not_and_un_consolidated_titles_are_never_consolidated(title):
    rows, want = pl()
    assert read(statement(rows, title=title), "pat", basis="CONSOLIDATED").status != "ok"


def test_a_revenue_row_above_a_sum_that_leaves_it_out_blocks_a_revenue_row_inside_too():
    rows, want = pl()
    part = [round(v * 0.6, 2) for v in REVENUE]
    got = statement([(["Revenue from operations"], REVENUE), (["Net sales"], part), (["Other income"], OTHER),
                     (["Total income"], cols_sum(part, OTHER))] + rows[3:])
    r = read(got, "revenue")
    assert r.status != "ok" or r.value == pytest.approx(crore(1000.00))


def test_an_unnamed_line_below_a_whole_revenue_line_does_not_stop_the_revenue():
    # SONACOMS Q2FY27: "Revenue from operations", "Foreign exchange gain (net)", "Other income" = "Total income"
    rows, want = pl()
    fx = [7.0, 6.0, 5.0, 20.0]
    oi = [round(o - f, 2) for o, f in zip(OTHER, fx)]
    pdf = statement(rows[:1] + [(["Foreign exchange gain (net)"], fx), (["Other income"], oi)] + rows[2:])
    assert read(pdf, "revenue").value == pytest.approx(crore(1000.00))


@pytest.mark.parametrize("second", ["Dividend income", "Sale of services", "Fees and commission", "Other operating income"])
def test_a_whole_revenue_line_over_a_line_that_may_be_a_part_names_no_revenue(second):
    # twenty-fourth review: "Revenue from operations" 70% over "Dividend income" 30% + "Other income" = "Total income"
    rows, want = pl()
    a = [round(v * 0.7, 2) for v in REVENUE]
    b = [round(v - x, 2) for v, x in zip(REVENUE, a)]
    got = read(statement([(["Revenue from operations"], a), ([second], b)] + rows[1:]), "revenue")
    assert got.status != "ok" or got.value == pytest.approx(crore(1000.00))
    assert nf.not_revenue_line("Foreign exchange gain (net)") and nf.not_revenue_line("Other incume")
    assert not nf.not_revenue_line(second)


@pytest.mark.parametrize("second", ["Net gain on fair value changes", "Gain on derecognition of financial instruments"])
def test_a_gain_that_is_a_revenue_part_is_a_part(second):
    # twenty-fifth review: an NBFC's gain on fair value changes is a part of revenue from operations ("Other incomes" is
    # labelled other income, a landmark, and is no part of revenue from operations)
    assert not nf.not_revenue_line(second) and not nf.not_revenue_line("Other incomes")
    rows, want = pl()
    a = [round(v * 0.7, 2) for v in REVENUE]
    b = [round(v - x, 2) for v, x in zip(REVENUE, a)]
    got = read(statement([(["Revenue from operations"], a), ([second], b)] + rows[1:]), "revenue")
    assert got.status != "ok" or got.value == pytest.approx(crore(1000.00))


def test_a_total_revenue_line_over_its_parts_is_the_revenue():
    # SRF Q2FY27: "Revenue from operations a. Sale of products", "b. Other operating revenues", "Total Revenue from operations"
    rows, want = pl()
    a = [round(v * 0.9, 2) for v in REVENUE]
    b = [round(v - x, 2) for v, x in zip(REVENUE, a)]
    pdf = statement([(["1 Revenue from operations", "a. Sale of products"], a), (["b. Other operating revenues"], b),
                     (["Total Revenue from operations"], REVENUE)] + rows[1:])
    assert read(pdf, "revenue").value == pytest.approx(crore(1000.00))


def test_a_row_equal_to_the_revenue_row_above_in_all_but_one_column_is_no_subtotal():
    # twenty-seventh review: "Interest income" equal to "Revenue from operations" above it except in the period's column
    rows, want = pl()
    interest = [600.00] + REVENUE[1:]
    pdf = statement([(["Revenue from operations"], REVENUE), (["Interest income"], interest), (["Other income"], OTHER),
                     (["Total income"], cols_sum(interest, OTHER))] + rows[3:])
    r = read(pdf, "revenue")
    assert r.status != "ok" or r.value == pytest.approx(crore(1000.00))


def test_a_subtotal_that_takes_in_an_other_income_row_is_not_the_revenue():
    # twenty-eighth review: "Revenue from operations" + "Other income" = "Total revenues", then "Other income", "Total income"
    rows, want = pl()
    first_oi = [20.0, 18.0, 16.0, 70.0]
    rev = [round(v - o, 2) for v, o in zip(REVENUE, first_oi)]
    pdf = statement([(["Revenue from operations"], rev), (["Other income"], first_oi), (["Total revenues"], REVENUE),
                     (["Other income"], OTHER), (["Total income"], cols_sum(REVENUE, OTHER))] + rows[3:])
    r = read(pdf, "revenue")
    assert r.status != "ok" or r.value == pytest.approx(crore(rev[0]))
    assert read(pdf, "other_income").status != "ok"


def test_a_total_revenue_from_operations_line_over_parts_that_do_not_add_up_is_still_the_revenue():
    # BAJAJHLDNG Q4FY24: OCR lost one part, so "Total revenue from operations" is not the sum of the rows above it
    rows, want = pl()
    a = [round(v * 0.1, 2) for v in REVENUE]
    pdf = statement([(["Revenue from contracts with customers - Sale of goods"], a),
                     (["Total revenue from operations"], REVENUE)] + rows[1:])
    assert read(pdf, "revenue").value == pytest.approx(crore(1000.00))
    assert not nf._TOTAL_REVENUE.match("Total revenues")


def test_an_undated_third_column_of_a_sebi_layout_is_the_same_quarter_a_year_before():
    # ABCAPITAL Q4FY24 (A5): quarter 31.03.2024, quarter 31.12.2023, an unreadable date, year 31.03.2024, year 31.03.2023
    def cols(kinds_dates):
        out = [nf.Column(0, 1, 0.5, i) for i in range(len(kinds_dates))]
        for c, (k, d) in zip(out, kinds_dates):
            c.kind, c.date = k, d
        return out
    good = cols([("quarter", date(2024, 3, 31)), ("quarter", date(2023, 12, 31)), (None, None), ("year", date(2024, 3, 31)),
                 ("year", date(2023, 3, 31))])
    nf.fill_quarter_slot(good)
    assert (good[2].kind, good[2].date) == ("quarter", date(2023, 3, 31))
    # the second column not the quarter before, a column after it undated, or no column a year before: nothing is filled
    for bad in ([("quarter", date(2024, 3, 31)), ("quarter", date(2023, 3, 31)), (None, None), ("year", date(2024, 3, 31)),
                 ("year", date(2023, 3, 31))],
                [("quarter", date(2024, 3, 31)), ("quarter", date(2023, 12, 31)), (None, None), ("year", date(2024, 3, 31)),
                 (None, None)],
                [("quarter", date(2024, 3, 31)), ("quarter", date(2023, 12, 31)), (None, None), ("year", date(2024, 3, 31))],
                # 31st review: the undated third column is the current year (or nine months) of a layout without the
                # same quarter last year
                [("quarter", date(2024, 3, 31)), ("quarter", date(2023, 12, 31)), (None, None), ("year", date(2023, 3, 31))],
                [("quarter", date(2023, 12, 31)), ("quarter", date(2023, 9, 30)), (None, None), ("nine", date(2022, 12, 31)),
                 ("year", date(2023, 3, 31))]):
        c = cols(bad)
        nf.fill_quarter_slot(c)
        assert c[2].date is None


def test_a_date_given_by_the_layout_does_not_make_a_page_look_dated():
    # CENTRUM Q4FY24: the filled third column made the scan look dated, so its OCR pass (which answers the year) was skipped
    cols = [nf.Column(0, 1, 0.5, i) for i in range(5)]
    for c, (k, d) in zip(cols, [("quarter", date(2024, 3, 31)), ("quarter", date(2023, 12, 31)), (None, None),
                                ("year", date(2024, 3, 31)), ("year", date(2023, 3, 31))]):
        c.kind, c.date = k, d
    nf.fill_quarter_slot(cols)
    table = nf.Table(1, "CONSOLIDATED", 1, cols, [], "textlayer")
    table.named = {"revenue": []}
    assert cols[2].date == date(2023, 3, 31) and nf.usable_dates([table]) == 4


@pytest.mark.parametrize("label", ["04. Share of net profit of associates and joint ventures", "7 Share of net profit of Associates"])
def test_a_numbered_associates_share_carries_the_chain_to_the_profit(label):
    # ATUL Q2FY27 consolidated ("04. Share of net profit of associate and joint venture") and BFINVEST ("7 Share of net profit
    # of Associates"): a row number before the share made it a profit row, which cut the chain to profit before tax and profit
    share = [9.4, 5.1, 3.3, 12.2]
    rows, want = pl(exceptional=[-v for v in share])
    rows[9] = ([label], share)
    for metric in ("pbt", "pat"):
        got = read(statement(rows, title="Statement of Consolidated Financial Results"), metric, basis="CONSOLIDATED")
        assert got.status == "ok" and got.value == pytest.approx(crore(want[metric][0])), (metric, got)


def bank_rows(op_label="7 Operating profit before provisions and contingencies (3-6)", pbt_label="9 Profit before tax (7-8)",
              pat_label="11 Net profit for the period (9-10)"):
    """An RBI-format bank statement (RBLBANK, KARURVYSYA, UNIONBANK Q2FY27): the parent lines over their parts, two subtractions
    before the tax (operating profit, then provisions), an "Of which" line under the provisions that is not taken off again."""
    add = lambda *xs: [round(sum(v), 2) for v in zip(*xs)]       # noqa: E731
    sub = lambda a, b: [round(x - y, 2) for x, y in zip(a, b)]   # noqa: E731
    adv, inv, rbi = [2410.55, 2301.4, 2205.12, 4711.95], [905.3, 880.12, 851.07, 1785.42], [61.2, 58.33, 55.9, 119.53]
    earned = add(adv, inv, rbi)
    other = [912.35, 870.6, 801.44, 1782.95]
    total = add(earned, other)
    expended = [1950.4, 1871.25, 1790.6, 3821.65]
    emp, oth = [610.2, 598.7, 570.15, 1208.9], [720.45, 690.3, 655.8, 1410.75]
    opex = add(emp, oth)
    expenditure = add(expended, opex)
    op = sub(total, expenditure)
    prov, npa = [420.15, 401.3, 380.6, 821.45], [300.1, 290.5, 270.3, 590.6]
    pbt = sub(op, prov)
    tax = [101.25, 95.4, 90.1, 196.65]
    pat = sub(pbt, tax)
    rows = [(["1 Interest earned (a)+(b)+(c)"], earned), (["(a) Interest/discount on advances/bills"], adv),
            (["(b) Income on investments"], inv), (["(c) Interest on balances with RBI"], rbi), (["2 Other income"], other),
            (["3 Total income (1+2)"], total), (["4 Interest expended"], expended), (["5 Operating expenses (i)+(ii)"], opex),
            (["(i) Employees cost"], emp), (["(ii) Other operating expenses"], oth), (["6 Total expenditure (4+5)"], expenditure),
            ([op_label], op), (["8 Provisions (other than tax) and contingencies"], prov),
            (["Of which provisions for non-performing assets"], npa), ([pbt_label], pbt), (["10 Tax expense"], tax),
            ([pat_label], pat)]
    return rows, dict(revenue=earned, total_income=total, op=op, pbt=pbt, pat=pat)


def test_a_bank_statement_is_read_through_its_own_chain():
    # RBLBANK, KARURVYSYA, UNIONBANK Q2FY27: none of a bank's lines was named (its parts stand between the lines a corporate
    # chain adds); the key's revenue for a bank is the interest earned, its profit the net profit
    rows, want = bank_rows()
    pdf = statement(rows)
    for metric in ("revenue", "total_income", "pbt", "pat"):
        got = read(pdf, metric)
        assert got.status == "ok" and got.value == pytest.approx(crore(want[metric][0])), (metric, got)


@pytest.mark.parametrize("labels", [
    dict(op_label="7 Profit before tax (3-6)", pbt_label="9 Profit after tax (7-8)", pat_label="11 Net profit (9-10)"),
    dict(pbt_label="9 Operating profit after provisions (7-8)"),
    dict(pat_label="11 Operating profit before tax"),
])
def test_a_banks_three_profit_levels_are_never_shifted(labels):
    # the outside review's trap: with two subtractions before the tax, the operating profit can be named the profit before tax
    # and that the profit after tax; whatever the labels, no profit is ever given from the wrong level
    rows, want = bank_rows(**labels)
    pdf = statement(rows)
    for metric, wrong in (("pbt", want["op"]), ("pat", want["pbt"]), ("pat", want["op"])):
        got = read(pdf, metric)
        assert got.status != "ok" or got.value != pytest.approx(crore(wrong[0])), (metric, got)


def test_a_banks_segment_table_is_not_its_statement():
    rows, _ = bank_rows()
    rows[0] = (["Segment revenue 1 Treasury"], rows[0][1])
    pdf = statement(rows)
    for metric in ("pbt", "pat"):
        assert read(pdf, metric).status != "ok"


def test_a_banks_profit_carried_on_by_associates_is_not_its_bottom_line():
    # UNIONBANK consolidated: "L. Net profit (H-I-J+K)" after minority and associates; the profit after tax above them is not it
    rows, want = bank_rows()
    share = [12.5, 11.0, 9.8, 23.5]
    rows += [(["12 Share in profit of associates"], share), (["13 Consolidated net profit for the period"],
                                                             [round(a + b, 2) for a, b in zip(want["pat"], share)])]
    got = read(statement(rows), "pat")
    assert got.status != "ok" or got.value != pytest.approx(crore(want["pat"][0])), got


def test_capital_adequacy_ratios_below_a_bank_statement_never_take_its_profit():
    rows, want = bank_rows()
    rows += [(["CET1 ratio (%)"], [12.1, 12.3, 12.0, 12.1]), (["AT1 ratio (%)"], [1.2, 1.2, 1.3, 1.2]),
             (["Tier 1 ratio (%)"], [13.3, 13.5, 13.3, 13.3]), (["Tier 2 ratio (%)"], [2.1, 2.0, 2.2, 2.1]),
             (["Capital adequacy ratio (%)"], [15.4, 15.5, 15.5, 15.4])]
    got = read(statement(rows), "pat")
    assert got.status != "ok" or got.value == pytest.approx(crore(want["pat"][0])), got


def test_a_banks_provisions_that_include_the_tax_never_make_its_net_profit_the_profit_before_tax():
    # the outside reviews' trap: a bank printing one "Provisions and contingencies" line that includes the tax and no tax row;
    # the row after it is the net profit, never the profit before tax
    rows, want = bank_rows()
    tax = [101.25, 95.4, 90.1, 196.65]
    prov = [round(p + t, 2) for p, t in zip(rows[12][1], tax)]
    net = [round(o - p, 2) for o, p in zip(want["op"], prov)]
    rows = rows[:12] + [(["8 Provisions and contingencies (including tax)"], prov), (["9 Net profit for the period (7-8)"], net)]
    pdf = statement(rows)
    got = read(pdf, "pbt")
    assert got.status != "ok" or got.value != pytest.approx(crore(net[0])), got
    got = read(pdf, "pat")
    assert got.status != "ok" or got.value == pytest.approx(crore(net[0])), got


@pytest.mark.parametrize("letter,standalone", [
    ("The Company does not have any subsidiary, associate or joint venture. Accordingly, the Company is not required to "
     "prepare consolidated financial results. Standalone results enclosed.", True),
    # one of the three missing: a company with associates may still publish consolidated results
    ("The Company does not have any subsidiary. Accordingly, the Company is not required to prepare consolidated financial "
     "results. Standalone results enclosed.", False),
    # an exception after the three: the company has one after all
    ("The Company does not have any subsidiary, associate or joint venture except XYZ Ltd. Accordingly, the Company is not "
     "required to prepare consolidated financial results. Standalone results enclosed.", False),
    # the exemption said, but a consolidated statement named elsewhere on the page
    ("The Company does not have any subsidiary, associate or joint venture. Statement of Consolidated Financial Results "
     "attached. Standalone results enclosed.", False),
])
def test_a_company_not_required_to_prepare_consolidated_results_files_standalone(monkeypatch, letter, standalone):
    # SBICARD Q2FY27: the statement is a scan with no title; the filing says the company has no subsidiary, associate or joint
    # venture and is not required to prepare consolidated financial results, which no longer counts as naming them
    from bse_intel import ocr
    monkeypatch.setattr(ocr, "available", lambda: True)
    rows, want = pl()
    page = statement(rows, title="Statement of Unaudited Financial Results")
    got = nf.reading_from_tables(nf.analyse(scanned(page, letter), ocr_boxes=lambda png: as_ocr_boxes(page)), "Q2FY27", "pat",
                                 "STANDALONE")
    if standalone:
        assert got.status == "ok" and got.value == pytest.approx(crore(want["pat"][0]))
    else:
        assert got.status == "none"


def with_note_page(pdf: bytes, text: str) -> bytes:
    """The filing with a typed notes page after the statement."""
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    page = doc.new_page(width=620, height=842)
    page.insert_text((LEFT, 60), text, fontsize=FONT)
    return doc.tobytes()


@pytest.mark.parametrize("note,standalone", [
    ("The Company does not have any subsidiary, associate or joint venture. Accordingly, the Company is not required to "
     "prepare consolidated financial results.", True),
    ("The Company does not have any subsidiary, associate or joint venture except XYZ Ltd. Accordingly, the Company is not "
     "required to prepare consolidated financial results.", False),
])
def test_an_untitled_typed_statement_of_a_company_not_required_to_consolidate_is_standalone(note, standalone):
    # SBICARD Q2FY27: every page has text; the untitled table was standalone only when no page named consolidated results,
    # and the notes page's "not required to prepare consolidated financial results" counted as naming them
    rows, want = pl()
    got = read(with_note_page(statement(rows, title="Statement of Unaudited Financial Results"), note), "pat")
    if standalone:
        assert got.status == "ok" and got.value == pytest.approx(crore(want["pat"][0]))
    else:
        assert got.status == "none"


def test_the_reader_runs_with_its_measured_options_whatever_the_settings(monkeypatch):
    # 29 Oct: the live pipeline runs with PDF_DATES_2DIGIT, PDF_PAGE_RANK and PDF_ROW_FIXES off (the old reader's settings);
    # numbers-first was measured with them on and turns them on for its own calls only
    from bse_intel import settings
    for name in ("PDF_DATES_2DIGIT", "PDF_PAGE_RANK", "PDF_ROW_FIXES"):
        monkeypatch.setenv(name, "0")
    settings.get_settings.cache_clear()
    seen = []
    real = nf.tables_of_page

    def spy(*args, **kwargs):
        seen.append((settings.pdf_option("pdf_dates_2digit"), settings.pdf_option("pdf_page_rank"),
                     settings.pdf_option("pdf_row_fixes")))
        return real(*args, **kwargs)
    monkeypatch.setattr(nf, "tables_of_page", spy)
    rows, _ = pl()
    nf.analyse(statement(rows))
    assert seen and all(s == (True, True, True) for s in seen)
    assert not settings.pdf_option("pdf_row_fixes")          # outside the reader the settings stand
    settings.get_settings.cache_clear()


def nbfc_rows(first_label="(a) Revenue from Operations (i) Interest Income", pat_label="7 Profit for the Period (5+6)",
              tax_label="6 Tax (expense)/credit (net)"):
    """An NBFC's statement in sections (VLSFINANCE Q4FY24): revenue only as "Total (a)" under its parts, other income as
    "Total (b)", total income "(a+b)"; the tax printed signed, as an expense or credit, and added to the profit."""
    add = lambda *xs: [round(sum(v), 2) for v in zip(*xs)]       # noqa: E731
    interest, dividend, fair = [381.16, 381.28, 340.05, 1401.31], [176.99, 164.23, 109.34, 1200.05], [9195.88, 10696.76, -2001.93, 37370.42]
    total_a = add(interest, dividend, fair)
    other = [240.0, 143.82, 124.99, 1019.72]
    ti = add(total_a, other)
    emp, fin, oth = [164.35, 142.85, 160.54, 615.85], [5.72, 6.54, 2.07, 20.56], [494.28, 378.46, 664.43, 1680.14]
    te = add(emp, fin, oth)
    pbt = [round(x - y, 2) for x, y in zip(ti, te)]
    tax = [-1747.94, -1937.17, 846.96, -6092.41]
    pat = add(pbt, tax)
    rows = [([first_label], interest), (["(ii) Dividend Income"], dividend), (["(iii) Net gain on fair value changes"], fair),
            (["Total (a)"], total_a), (["(b) Other Income"], other), (["Total (b)"], other), (["Total Income (a+b)"], ti),
            (["(a) Employee benefits expense"], emp), (["(b) Finance costs"], fin), (["(c) Other Expenses"], oth),
            (["Total expenses"], te), (["5 Profit before tax (3-4)"], pbt), ([tax_label], tax), ([pat_label], pat)]
    return rows, dict(revenue=total_a, total_income=ti, pat=pat, pbt=pbt)


def test_an_nbfc_statement_in_sections_names_revenue_and_a_signed_tax_profit():
    # VLSFINANCE Q4FY24: no row said revenue ("Total (a)"), and the profit adds a tax printed as "(expense)/credit"
    rows, want = nbfc_rows()
    pdf = statement(rows)
    for metric in ("revenue", "total_income", "pat"):
        got = read(pdf, metric)
        assert got.status == "ok" and got.value == pytest.approx(crore(want[metric][0])), (metric, got)


def test_sections_whose_first_part_is_not_revenue_name_no_revenue():
    rows, want = nbfc_rows(first_label="(a) Employee stock options (i) Grant")
    got = read(statement(rows), "revenue")
    assert got.status != "ok", got


def test_a_tax_is_added_only_where_the_labels_say_so():
    # no "(5+6)" and no "credit": PBT + tax = the profit would be arithmetic alone, so no profit is named
    rows, want = nbfc_rows(pat_label="7 Profit for the Period", tax_label="6 Tax expense")
    got = read(statement(rows), "pat")
    assert got.status != "ok" or got.value != pytest.approx(crore(want["pat"][0])), got


def test_a_cost_of_sales_section_is_never_revenue_in_sections():
    # review of 5b84304: "Cost of sales" is revenue-class by its word "sales"; a section it opens is costs
    rows, want = nbfc_rows(first_label="(a) Cost of sales (i) Materials")
    got = read(statement(rows), "revenue")
    assert got.status != "ok" or got.value != pytest.approx(crore(want["revenue"][0])), got


# --- numbered lines with nil cells stitched into one label (AIIL Q4FY24, ARMANFIN Q4FY24) ------------------------------------

def _merged_nil_rows(first, merged_lines, merged_cells):
    rows, want = pl()
    cont = want["pat"]
    # statement() spaces a row by the previous row's lines, so the first row gets as many lines as the merged one
    # (and a blank spacer row of that many lines, so the lines drawn above a row's figures never touch the row before)
    first_lines = [first] + ["(carried)"] * (len(merged_lines) - 1)
    rows = rows[:-1] + [([" "] * len(merged_lines), []), (first_lines, cont), (merged_lines, merged_cells(cont))]
    return rows, cont


def test_the_profit_for_the_period_behind_nil_numbered_lines_is_named():
    # "8 ... 9 ... 10 ..." are nil with no cells, so the figures of "11 Profit for the period (7-10)" take all four labels
    rows, cont = _merged_nil_rows("7 Profit for the period from continuing operations (5-6)", [
        "8 Profit from discontinued operations", "9 Tax expense of discontinued operations",
        "10 Profit from discontinued operations (after tax) (8-9)", "11 Profit for the period (7-10)"], lambda c: c)
    got = read(statement(rows), "pat")
    assert got.status == "ok" and got.value == pytest.approx(crore(cont[0])), got


def test_numbered_lines_ending_in_total_comprehensive_income_are_never_the_profit():
    # the same shape, but the last line is the total comprehensive income: no profit from it
    rows, cont = _merged_nil_rows("7 Profit for the period from continuing operations (5-6)", [
        "8 Other comprehensive income", "9 Total comprehensive income for the period (7+8)"], lambda c: c)
    got = read(statement(rows), "pat")
    assert got.status != "ok", got


def test_numbered_lines_that_do_not_run_on_one_by_one_are_not_a_nil_block():
    rows, cont = _merged_nil_rows("7 Profit for the period from continuing operations (5-6)", [
        "8 Profit from discontinued operations", "12 Profit for the period (7-10)"], lambda c: c)
    got = read(statement(rows), "pat")
    assert got.status != "ok", got


def test_a_profit_before_a_lost_associates_share_is_not_the_profit_behind_nil_lines():
    # the associates' share has cells in no column here but the last line's figures differ from the profit above: the identity fails
    rows, cont = _merged_nil_rows("7 Profit after tax", [
        "8 Share of profit of associates", "9 Profit for the period (7+8)"], lambda c: [round(v + 5.0, 2) for v in c])
    got = read(statement(rows), "pat")
    assert not (got.status == "ok" and got.value == pytest.approx(crore(cont[0]))), got


def _layout(spec):
    out = [nf.Column(0, 1, 0.5, i) for i in range(len(spec))]
    for c, (k, d) in zip(out, spec):
        c.kind, c.date = k, d
    return out


Q, H, Y = "quarter", "half", "year"
SEP = [(Q, date(2026, 9, 30)), (Q, date(2026, 6, 30)), (Q, date(2025, 9, 30)), (H, date(2026, 9, 30)), (H, date(2025, 9, 30)),
       (Y, date(2026, 3, 31))]


@pytest.mark.parametrize("damaged,expect", [
    (0, (Q, date(2026, 9, 30))),      # ANGELONE Q2FY27: the current quarter's date and kind lost
    (1, (Q, date(2026, 6, 30))),      # ARMANFIN Q3FY24: the previous quarter's
    (2, (Q, date(2025, 9, 30)))])     # the year-ago quarter's
def test_the_one_damaged_quarter_of_a_sebi_layout_is_given_by_its_slot(damaged, expect):
    spec = list(SEP)
    spec[damaged] = (None, None)
    cols = _layout(spec)
    nf.fill_quarter_slot(cols)
    assert (cols[damaged].kind, cols[damaged].date, cols[damaged].inferred) == (*expect, True)
    # a date read as the slot's own but with no kind (SUNDARMFIN Q4FY23) gets its kind
    spec[damaged] = (None, SEP[damaged][1])
    cols = _layout(spec)
    nf.fill_quarter_slot(cols)
    assert (cols[damaged].kind, cols[damaged].date) == expect


def test_a_damaged_quarter_is_not_given_when_the_layout_leaves_room_for_doubt():
    def damaged(spec):
        cols = _layout(spec)
        nf.fill_quarter_slot(cols)
        return [(c.kind, c.date) for c in cols] != [(k, d) for k, d in spec]
    assert damaged([(None, None)] + SEP[1:])                                  # control: this one is filled
    assert not damaged([(None, None), (None, None)] + SEP[2:])                # two columns damaged
    assert not damaged([(None, date(2026, 9, 29))] + SEP[1:])                 # a date read that is not the slot's
    assert not damaged([(None, None), (Q, date(2026, 6, 30)), (Q, date(2025, 12, 31))] + SEP[3:])      # the two read disagree on X
    assert not damaged([(None, None)] + SEP[1:3] + [(H, date(2026, 6, 30))] + SEP[4:])                 # no year to date dated X
    assert not damaged([(None, None)] + SEP[1:4] + [(H, date(2025, 3, 31)), (Y, date(2026, 3, 31))])   # none dated a year before X
    assert not damaged([(None, None)] + SEP[1:5] + [(None, None)])            # a tail column undated
    assert not damaged(SEP[:3])                                               # no tail: the first columns may be all there is
    assert not damaged([(None, None), (Q, date(2026, 6, 30)), (H, date(2025, 9, 30))] + SEP[3:])      # the third is not a quarter
    assert not damaged([(None, None)] + SEP[1:] + [(Q, date(2026, 6, 30))])                            # a fourth quarter-like column


def _six_columns(first_date, third_date="30.09.2025"):
    rows, _ = pl()
    rows = [(label, cells[:3] + [cells[0], cells[2], cells[3]]) for label, cells in rows]
    return statement(rows, unit="(Rs. in Lakhs)", cols=[200, 270, 340, 410, 480, 550],
                     groups=["Quarter ended"] * 3 + ["Half year ended"] * 2 + ["Year ended"],
                     dates=[first_date, "30.06.2026", third_date, "30.09.2026", "30.09.2025", "31.03.2026"])


def test_a_current_quarter_whose_date_is_lost_is_found_by_the_layout():
    got = read(_six_columns(""), "revenue")
    assert got.status == "ok" and got.value == pytest.approx(crore(REVENUE[0]))


def test_a_current_quarter_whose_date_is_lost_is_not_guessed_when_the_layout_does_not_fit():
    # the year-ago quarter is not dated a year before the half year to date: the first column could be any quarter
    assert read(_six_columns("", third_date="30.09.2024"), "revenue").value is None


@pytest.mark.parametrize("unit,per_crore", [("CIN: L65110JK1938SGC000048 ( In Crores)", 1), ("[ J (Ks. in Lacs)", 100)])
def test_a_bracketed_unit_ending_a_line_that_holds_other_header_words_is_read(unit, per_crore):
    # J&KBANK ("CIN: ... ( In Crores)", the rupee sign lost) and PARIN ("[ J (Ks. in Lacs)")
    rows, _ = pl()
    got = read(statement(rows, unit=unit), "revenue")
    assert got.status == "ok" and got.value == pytest.approx(REVENUE[0] / per_crore)


@pytest.mark.parametrize("line", [
    "Loans sanctioned ( In Crores) during the quarter",       # the bracket does not close the line: prose about something else
    "Details of loans (Figures in crore) are given in note 4",
    "(Rs. in thousands)",                                     # a unit the reader does not convert
    "Total assets (as per the balance sheet of the in lakhs)",
    "In Crores"])                                             # no bracket
def test_a_bracketed_unit_is_taken_only_at_the_end_of_a_line(line):
    assert nf.scan_units([line], only="tail") == set()


def test_two_bracketed_units_on_one_line_name_no_unit():
    assert nf.scan_units(["Revenue (Rs. in crores) and costs (Rs. in lakhs)"], only="tail") == {None}
    assert nf.scan_units(["(Ks. in Lacs)", "CIN: L1 ( In Crores)"], only="tail") == {100, 1}      # two lines: unit_of then sees two units


def test_trap_tail_unit_share_count_is_not_table_unit():
    from bse_intel.pdf_numbers_first import unit_of
    # a share-count unit in the header region must not become the table's money unit (100x)
    assert unit_of(["Statement of results", "Paid up shares (No. in Lakhs)", "Particulars"], []) is None


def test_roman_numbered_nil_lines_give_the_profit_for_the_period():
    # PARIN Q2FY27: "X Profit from continuing operations", then "XI ... discontinued" and "XII Net Profit for the period" stitched
    rows, cont = _merged_nil_rows("X Profit for the period from continuing operations (VIII-IX)", [
        "XI Profit from discontinued operations (net of tax)", "XII Net Profit for the period"], lambda c: c)
    got = read(statement(rows), "pat")
    assert got.status == "ok" and got.value == pytest.approx(crore(cont[0])), got


def test_roman_numbered_lines_ending_in_comprehensive_income_or_skipping_a_number_are_never_the_profit():
    for last in ("XII Total comprehensive income for the period", "XIII Net Profit for the period"):
        rows, cont = _merged_nil_rows("X Profit for the period from continuing operations (VIII-IX)", [
            "XI Other comprehensive income", last], lambda c: c)
        got = read(statement(rows), "pat")
        assert got.status != "ok", (last, got)


def _nci_rows(label9, minority=(-10.0, -9.0, -8.0, -30.0)):
    rows, want = pl()
    pat = want["pat"]
    owners = [round(a + b, 2) for a, b in zip(pat, minority)]
    return rows[:-1] + [([label9], pat), (["10 (Profit) / Loss attributable to non-controlling interests"], list(minority)),
                        (["11 Profit for the period attributable to owners of the company (9+10)"], owners)], pat


def test_profit_after_tax_including_non_controlling_interests_is_the_profit():
    rows, pat = _nci_rows("9 Profit after tax for the period (including non-controlling interests) (7-8)")
    got = read(statement(rows), "pat")
    assert got.status == "ok" and got.value == pytest.approx(crore(pat[0])), got


def test_a_label_saying_attributable_or_comprehensive_is_not_helped_by_including_non_controlling_interests():
    for label in ("9 Profit attributable to owners of the company (including non-controlling interests) (7-8)",
                  "9 Total comprehensive income for the period (including non-controlling interests) (7-8)"):
        rows, pat = _nci_rows(label)
        got = read(statement(rows), "pat")
        assert got.status != "ok", (label, got)


@pytest.mark.parametrize("label,share_label,bottom_label", [
    ("9 Profit after tax before non-controlling interest and share of profit of associates", "10 Share of profit of associates", "11 Profit for the period"),
    ("9 Profit after tax before non-controlling interest and share of profit of associates", "10 Share of profit of associates", "11 Net profit after share of associates"),
    ("9 Profit for the period before non-controlling interests", "10 Share of profit of associates", "11 Profit for the period"),
    ("9 Profit after tax before non-controlling interest", "10 Share of profit of associates", "11 Profit for the period"),
    ("9 Profit after tax before non-controlling interest", "10 Share of profit of associates", "11 Net income"),
    ("9 Profit after tax before non-controlling interest", "10 Share of profit of associates", "11 Profit for the year, group"),
    ("9 Profit after tax before non-controlling interest", "10 Add: Share in JV", "11 Consolidated net profit"),
    ("9 Profit after tax including non-controlling interests", "10 Share of profit of associates", "11 Group result"),
])
def test_trap_pre_associates_row_never_given(label, share_label, bottom_label):
    rows, want = pl()
    sh = [9.4, 5.1, 3.3, 12.2]
    bottom = [round(a + b, 2) for a, b in zip(want["pat"], sh)]
    rows = rows[:-1] + [([label], want["pat"]), ([share_label], sh), ([bottom_label], bottom)]
    got = read(statement(rows), "pat")
    assert got.status == "none" or got.value == pytest.approx(crore(bottom[0])), (label, bottom_label, got)


def test_trap_pbt_row_labelled_including_nci():
    rows, want = pl()
    # a PBT row mislabelled "for the period before tax including NCI" followed by a nil-tax equal row
    rows = rows[:-1] + [(["Profit for the period before tax including non-controlling interests"], want["pbt"]),
                        (["Tax expense"], ["-", "-", "-", "-"]), (["Profit after tax"], want["pbt"])]
    got = read(statement(rows), "pat")
    print(got)


def test_trap_pbt_labelled_for_the_period_before_tax_incl_nci_is_not_pat_class():
    from bse_intel.pdf_numbers_first import label_class
    assert label_class("Profit for the period before tax including non-controlling interests") != "PAT"
    assert label_class("Profit/(loss) for the year before tax and before non-controlling interests") != "PAT"


def test_trap_mixed_roman_digit_run():
    from bse_intel.pdf_numbers_first import _ROW_MARKER, _ROMAN
    t = "9 Profit from continuing operations X Net profit for the period"
    assert [m[1] for m in _ROW_MARKER.finditer(t)] == ["9", "X"]


def _lost_part(total_label=("Total expenses",), pbt_before_label=None, bad_total=False):
    """A statement whose last expense line has a cell in one column only (so it is no row): the total expenses cannot be summed."""
    rows, want = pl(total_label=("Total income (I+II)",))
    out = []
    for lines, cells in rows:
        if lines == ["Other expenses"]:
            cells = [cells[0], "", "", ""]
        elif lines == ["Total expenses"]:
            lines = list(total_label)
            if bad_total:
                cells = [v + 7.0 for v in cells]
        elif pbt_before_label and lines and lines[0].startswith("V. Profit"):
            lines = [pbt_before_label]
        out.append((lines, cells))
    return out, want

def test_a_total_expenses_row_whose_parts_are_lost_is_named_by_the_profit_identity():
    rows, want = _lost_part()
    pdf = statement(rows)
    for metric, key in (("pbt", "pbt"), ("pat", "pat")):
        got = read(pdf, metric)
        assert got.status == "ok" and got.value == pytest.approx(crore(want[key][0])), (metric, got)

def test_a_bare_total_is_not_named_when_the_parts_do_not_sum():
    rows, want = _lost_part(total_label=("Total",))
    for metric in ("pbt", "pat", "expenses"):
        assert read(statement(rows), metric).status != "ok", metric

def test_an_unlabelled_profit_row_never_names_the_total_expenses_by_itself():
    # the profit before tax row below still says so and holds the identity, so the answer may be given, but only the true one
    rows, want = _lost_part(pbt_before_label="V. Result of the period (III-IV)")
    got = read(statement(rows), "pbt")
    assert got.status != "ok" or got.value == pytest.approx(crore(want["pbt"][0])), got

def test_a_total_expenses_row_that_breaks_the_profit_identity_is_not_named():
    rows, want = _lost_part(bad_total=True)
    for metric in ("pbt", "pat"):
        assert read(statement(rows), metric).status != "ok"

def test_a_profit_before_tax_label_garbled_by_one_letter_is_the_profit_before_tax():
    rows, want = pl(pbt_label="Profit beforc Tax (V-VI)")
    got = read(statement(rows), "pbt")
    assert got.status == "ok" and got.value == pytest.approx(crore(want["pbt"][0])), got

def test_a_garbled_before_does_not_turn_an_after_tax_profit_into_a_profit_before_tax():
    rows, want = pl(pbt_label="Profit aftcr Tax (V-VI)")
    got = read(statement(rows), "pbt")
    assert not (got.status == "ok" and got.value == pytest.approx(crore(want["pbt"][0]))) or got.status != "ok", got


def test_trap_garbled_pbei_label_is_not_the_pbt():
    # REVIEW TRAP: "beforc exceptional items and tax" is a profit before EXCEPTIONAL items; the true PBT row is labelled "after exceptional"
    rows, k = pl(exceptional=[5.0, 6.0, 7.0, 10.0], pbt_label="Profit after exceptional items")
    rows = list(rows)
    rows[8] = (["V. Profit beforc exceptional items and tax (III-IV)"], rows[8][1])
    r = read(statement(rows), "pbt")
    assert r.status == "none" or abs(r.value - crore(k["pbt"][0])) < 1e-6, (r.status, r.value)



def _nrow(label, *values):
    cells = [None if v is None else nf.Cell(v, 2, False, True, None, str(v)) for v in values]    # type: ignore[arg-type]
    return nf.NRow(0.0, 0.0, 0.0, label, cells)


def test_a_line_read_twice_with_no_label_is_dropped_and_the_figures_are_still_answered():
    # CREDITACC Q2FY27: OCR gave the "Other income" figures again as a second row with no label, which cut the sums
    rows, _ = pl()
    twin = list(rows)
    twin.insert(2, ([""], rows[1][1]))
    pdf = statement(twin)
    for metric, want in (("revenue", REVENUE[0]), ("total_income", None), ("pbt", None), ("pat", None)):
        got = read(pdf, metric)
        assert got.status == "ok", metric
        if want:
            assert got.value == pytest.approx(crore(want))
    assert read(pdf, "total_income").value == read(statement(rows), "total_income").value
    assert read(pdf, "pat").value == read(statement(rows), "pat").value


def test_a_row_is_dropped_only_when_it_is_an_unlabelled_exact_copy_of_the_row_above():
    a = _nrow("II Other income", 1.06, 0.92, 0.67, 1.98)
    kept = lambda *rows: len(nf.drop_twin_rows(list(rows)))
    assert kept(a, _nrow("", 1.06, 0.92, 0.67, 1.98)) == 1                       # control: dropped
    assert kept(a, _nrow("", 1.06, 0.92, 0.67, 1.99)) == 2                       # one figure differs
    assert kept(a, _nrow("", 1.06, 0.92, 0.67, None)) == 2                       # a cell missing on one side
    assert kept(a, _nrow("Other income (restated)", 1.06, 0.92, 0.67, 1.98)) == 2   # it has a label of its own
    assert kept(_nrow("", 1.06, 0.92, 0.67, 1.98), _nrow("", 1.06, 0.92, 0.67, 1.98)) == 2     # nothing above to be a copy of
    assert kept(a, _nrow("Total", 5.0, 5.0, 5.0, 5.0), _nrow("", 1.06, 0.92, 0.67, 1.98)) == 3  # not the row just above
    b = _nrow("Exceptional", 1.0, 1.0, None, None)
    assert kept(b, _nrow("", 1.0, 1.0, None, None)) == 2                         # fewer than three figures


HALF_DATES = ["30.09.2026", "30.06.2026", "30.09.2025", "30.09.2026", "30.09.2025", "31.03.2026"]


HALF_KINDS = ["Quarter ended"] * 3 + ["Half year ended"] * 2 + ["Year ended"]


EDGES = [150 + 40 * i for i in range(12)]


def _two_bases(words=("Standalone", "Consolidated"), second_dates=None, scale=2, xs=None):
    rows, want = pl()
    wide = []
    for lines, cells in rows:
        if all(isinstance(c, (int, float)) for c in cells):
            six = list(cells) + list(cells[:2])
            cells = six + [round(v * scale, 2) for v in six]
        else:
            cells = list(cells) + list(cells[:2])
            cells = cells + cells
        wide.append((lines, cells))
    dates = HALF_DATES + (second_dates or HALF_DATES)
    pdf = statement(wide, title="Statement of Financial Results", groups=HALF_KINDS * 2, dates=dates, cols=EDGES)
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    page = doc[0]
    centre = lambda a, b: (EDGES[a] + EDGES[b]) / 2 - 20
    for text, x in zip(words, xs or (centre(0, 5) - 25, centre(6, 11) - 25)):
        page.insert_text((x, 66), text, fontsize=8)
    out = doc.tobytes()
    doc.close()
    return out, want


def test_two_bases_printed_side_by_side_are_read_each_on_its_own_basis():
    pdf, want = _two_bases()
    for metric, key in (("pbt", "pbt"), ("pat", "pat")):
        a = read(pdf, metric, basis="STANDALONE")
        b = read(pdf, metric, basis="CONSOLIDATED")
        assert a.status == "ok" and a.value == pytest.approx(crore(want[key][0])), (metric, a)
        assert b.status == "ok" and b.value == pytest.approx(crore(2 * want[key][0])), (metric, b)


def test_a_header_of_one_phrase_or_two_equal_ones_or_halves_dated_differently_is_not_split():
    for kwargs in (dict(words=("Standalone", "Standalone")), dict(words=("Quarterly", "Particulars")),
                   dict(second_dates=["30.09.2026", "30.06.2025", "30.09.2024", "30.09.2025", "30.09.2024", "31.03.2025"])):
        pdf, want = _two_bases(**kwargs)
        for basis in ("STANDALONE", "CONSOLIDATED"):
            got = read(pdf, "pat", basis=basis)
            assert got.status != "ok" or got.value in (pytest.approx(crore(want["pat"][0])), pytest.approx(crore(2 * want["pat"][0]))), got
            assert not (got.status == "ok" and basis == "STANDALONE" and got.value == pytest.approx(crore(2 * want["pat"][0]))), got


def test_two_side_by_side_headings_with_heading_words_are_read_each_on_its_own_basis():
    # CYIENT Q2FY27: "Consolidated results" over the first six columns, "Standalone results" over the last six; HITECHGEAR
    # Q1FY27: "Standalone Results" first, "Consolidated Results" second
    for words, left, right_basis in ((("Consolidated results", "Standalone results"), "CONSOLIDATED", "STANDALONE"),
                                     (("Standalone Financial Results", "Consolidated Financial Results"), "STANDALONE", "CONSOLIDATED")):
        pdf, want = _two_bases(words=words)
        for metric in ("pbt", "pat"):
            a, b = read(pdf, metric, basis=left), read(pdf, metric, basis=right_basis)
            assert a.status == "ok" and a.value == pytest.approx(crore(want[metric][0])), (words, metric, a)
            assert b.status == "ok" and b.value == pytest.approx(crore(2 * want[metric][0])), (words, metric, b)


def test_trap_side_by_side_headings_that_are_not_two_headings_each_over_its_own_columns_give_no_basis():
    centre = lambda a, b: (EDGES[a] + EDGES[b]) / 2 - 20
    for kwargs in (
        dict(words=("Standalone results", "Quarter ended")),                    # one heading only
        dict(words=("Standalone results", "Standalone results")),               # the same basis twice
        dict(words=("Standalone results", "Consolidated results"), xs=(EDGES[0] - 20, EDGES[2])),    # both over the first half
        dict(words=("Standalone Financial Results", "Consolidated results"), xs=(centre(4, 6) - 40, centre(6, 11) + 30)),
        # ^ the first heading runs on across the second half's columns
        dict(words=("Standalone results for", "Consolidated results")),         # a word that is not a heading word
        dict(words=("Unaudited Standalone results", "Consolidated results")),   # the line does not open on a basis word
    ):
        pdf, want = _two_bases(**kwargs)
        for basis in ("STANDALONE", "CONSOLIDATED"):
            got = read(pdf, "pat", basis=basis)
            assert got.status != "ok", (kwargs, basis, got)


def test_swapped_phrases_name_the_bases_the_other_way_round():
    pdf, want = _two_bases(words=("Consolidated", "Standalone"))
    a = read(pdf, "pat", basis="CONSOLIDATED")
    assert a.status != "ok" or a.value == pytest.approx(crore(want["pat"][0]))


_XS = [658, 826, 996, 1158, 1328, 1488]


_MONTH_LINE = [(573, 710, "September"), (757, 809, "June"), (822, 861, "30,"), (912, 1048, "September"), (1081, 1216, "September"),
               (1248, 1386, "September"), (1421, 1490, "March"), (1504, 1545, "31,")]


_DAY_LINE = [(587, 696, "30,2026"), (775, 844, "2026"), (926, 1034, "30,2025"), (1093, 1202, "30,2026"), (1262, 1372, "30,2025"),
             (1448, 1516, "2026")]


def _header_dates(month_line, day_line):
    ws = [nf.Word(a, b, 500.0, 30.0, t) for a, b, t in month_line] + [nf.Word(a, b, 530.0, 30.0, t) for a, b, t in day_line]
    cols = [nf.Column(x - 60, x, x, i) for i, x in enumerate(_XS)]       # the figures' column centres as the trace printed them
    return nf.column_dates(ws, cols, 30.0, 27.0)


def test_a_month_line_that_runs_into_one_phrase_is_cut_by_column():
    # ICICIBANK Q2FY27 (OCR): "September June 30, September September September March 31," over "30,2026 2026 30,2025 ..."
    assert _header_dates(_MONTH_LINE, _DAY_LINE) == [date(2026, 9, 30), date(2026, 6, 30), date(2025, 9, 30), date(2026, 9, 30),
                                                   date(2025, 9, 30), date(2026, 3, 31)]


def _merged(items):
    return [[nf.Word(a, b, 500.0, 30.0, text) for a, b, text in items]]


def test_a_month_line_is_not_cut_when_the_cut_is_not_certain():
    xs = [float(x) for x in _XS]
    whole = _merged(_MONTH_LINE)
    assert len(nf.column_pieces(whole, xs, 170.0)) == 6                       # control: cut
    moved = list(_MONTH_LINE)
    moved[3] = (760, 896, "September")                                    # two pieces nearest the same column
    assert nf.column_pieces(_merged(moved), xs, 170.0) == _merged(moved)
    wide = list(_MONTH_LINE)
    wide[0] = (400, 710, "September")                                     # a piece wider than a column
    assert nf.column_pieces(_merged(wide), xs, 170.0) == _merged(wide)
    assert nf.column_pieces(_merged(_MONTH_LINE[:3]), xs, 170.0) == _merged(_MONTH_LINE[:3])         # fewer than three month words
    lead = [(540, 570, "Of")] + list(_MONTH_LINE)
    assert nf.column_pieces(_merged(lead), xs, 170.0) == _merged(lead)                                # the phrase does not open on a month
    short = [(573, 640, "Sep"), (650, 700, "Jun"), (710, 760, "Mar")]                           # already narrower than a column
    assert nf.column_pieces(_merged(short), xs, 170.0) == _merged(short)
    # and a header read with a wrong cut never carries a wrong date: every date read is the right one for its column
    right = _header_dates(_MONTH_LINE, _DAY_LINE)
    assert all(d in (None, r) for d, r in zip(_header_dates(moved, _DAY_LINE), right))


def test_trap_non_consolidated_word_is_not_consolidated():
    pdf, want = _two_bases(words=("Standalone", "Non-Consolidated"))
    got = read(pdf, "pat", basis="CONSOLIDATED")
    assert got.status != "ok", got


def test_trap_title_names_other_basis():
    pdf, want = _two_bases(words=("Standalone", "Consolidated"))
    assert nf._basis_word("Non-Consolidated") is None


# --- the lead's review of 8c42311 ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("line", ["Figures (US$ in million)", "x ($ in million)", "Margins (% in lakhs)", "x (# in crores)",
                                  "x (€ in million)", "x (£ in million)"])
def test_a_bracketed_unit_after_another_currency_or_a_symbol_is_not_a_rupee_unit(line):
    assert nf.scan_units([line], only="tail") == set()


def test_a_bracketed_unit_after_a_rupee_sign_is_read():
    assert nf.scan_units(["CIN: L1 (₹ in Crores)"], only="tail") == {1}


def test_a_quarter_date_read_but_disputed_by_the_header_words_is_never_revived():
    spec = [(None, None)] + SEP[1:]
    cols = _layout(spec)
    cols[0].read_date = date(2026, 6, 30)        # column_kinds read a date the header words disputed: date and kind set to None
    nf.fill_quarter_slot(cols)
    assert (cols[0].kind, cols[0].date) == (None, None)
    cols = _layout(spec)
    cols[0].read_date = date(2026, 9, 30)        # the date read is the slot's own: the column is given
    nf.fill_quarter_slot(cols)
    assert (cols[0].kind, cols[0].date) == (Q, date(2026, 9, 30))


def test_a_unit_named_elsewhere_on_a_page_of_two_tables_never_sets_the_first_tables_unit():
    rows, _ = pl()
    doc = pymupdf.open(stream=statement(rows, unit=" "), filetype="pdf")
    page = doc[0]
    draw(page, LEFT, 650, "Statement of segment results")       # a second table below the first, in another unit
    draw(page, LEFT, 664, "(Rs. in Crores)")
    for edge, g, d in zip(COL_RIGHT, KINDS, DATES):
        draw(page, edge - 15 - pymupdf.get_text_length(g, fontsize=FONT) / 2, 688, g)
        right(page, edge, 702, d)
    for k, label in enumerate(["Segment A", "Segment B", "Total"]):
        draw(page, LEFT, 730 + 14 * k, label)
        for edge, v in zip(COL_RIGHT, [10.5, 20.25, 30.75] if k < 2 else [21.0, 40.5, 61.5]):
            right(page, edge, 730 + 14 * k, fmt(v))
    pdf = doc.tobytes()
    doc.close()
    assert read(pdf, "revenue").status != "ok"


def test_the_reader_options_are_off_outside_the_numbers_first_reader_and_on_inside_it():
    from bse_intel import settings
    flags = ("pdf_dates_2digit", "pdf_page_rank", "pdf_row_fixes")
    assert not any(settings.pdf_option(f) for f in flags)
    with settings.pdf_reader_options():
        assert all(settings.pdf_option(f) for f in flags)
    assert not any(settings.pdf_option(f) for f in flags)


def test_the_old_reader_keeps_its_plain_consolidated_word_search():
    text = ("The Company does not have any subsidiary, associate or joint venture. Accordingly, the Company is not required to "
            "prepare consolidated financial results. Standalone results enclosed.")
    layers = {1: prd.PageLayer(text, True, set(), "")}
    assert prd.consolidated_anywhere(layers)                                          # the old reader: the word is there
    assert not prd.consolidated_anywhere(layers, not_required=True, numbers_first=True)   # numbers-first reads the exemption


def test_a_unit_in_a_note_below_the_only_table_never_sets_its_unit():
    rows, _ = pl()
    doc = pymupdf.open(stream=statement(rows, unit=" "), filetype="pdf")
    draw(doc[0], LEFT, 650, "Notes: segment figures below (Rs. in Crores)")
    pdf = doc.tobytes()
    doc.close()
    assert read(pdf, "revenue").status != "ok"


# --- TODO 123: causes in place of patches --------------------------------------------------------------------------------

def test_an_undated_third_column_whose_date_was_read_but_disputed_is_never_revived():
    # one function, one set of guards (TODO 123 part 6): the ABCAPITAL layout's undated third column is filled, but not when
    # column_kinds read a date there that the header words disputed, and not when a column after the three is the quarter before
    def cols(read_date=None, extra=None):
        spec = [("quarter", date(2024, 3, 31)), ("quarter", date(2023, 12, 31)), (None, None), ("year", date(2024, 3, 31)),
                ("year", date(2023, 3, 31))] + ([extra] if extra else [])
        out = [nf.Column(0, 1, 0.5, i) for i in range(len(spec))]
        for c, (k, d) in zip(out, spec):
            c.kind, c.date, c.read_date = k, d, d
        out[2].read_date = read_date
        return out
    good = cols()
    nf.fill_quarter_slot(good)
    assert (good[2].kind, good[2].date) == ("quarter", date(2023, 3, 31))          # control
    disputed = cols(read_date=date(2023, 6, 30))
    nf.fill_quarter_slot(disputed)
    assert (disputed[2].kind, disputed[2].date) == (None, None)
    previous = cols(extra=("nine", date(2023, 12, 31)))
    nf.fill_quarter_slot(previous)
    assert previous[2].date is None


def test_a_label_word_damaged_by_one_letter_is_put_back_from_the_statements_vocabulary():
    # TODO 123 part 4: one repair in place of the spelling-variant rules ("beforc", MOREPENLAB)
    assert nf.mend_label("5. Profit beforc Tax (3+4)") == "5. Profit before Tax (3+4)"
    assert nf.label_class("Proft bcfore tax") == "PBT"                 # two damaged words: the old rule needed "profit" whole
    assert nf.label_class("Share of 0xceptional items") == "EXC"
    assert nf.label_class("V. Profit beforc exceptional items and tax (III-IV)") == "PBEI"


@pytest.mark.parametrize("word", ["after", "loss", "less", "basis", "referred", "point", "owned", "continue", "scontinued",
                                  "ontinued", "deterred", "otter", "Lose"])
def test_trap_a_real_word_is_never_mended_into_another(word):
    # "after" is never "before", "basis" never "basic", "referred" never "deferred" (both printed in the answer keys' PDFs),
    # and "discontinued" with its start lost is never "continued"
    assert nf.mend_label(word) == word


def test_a_word_one_letter_from_two_vocabulary_words_is_not_mended():
    assert nf._one_edit("lass", "loss") and nf._one_edit("lass", "less")
    assert nf.mend_label("tota") == "tota"                              # shorter than five letters


def test_a_bracketed_unit_ending_a_page_line_above_the_header_is_the_page_unit():
    # TODO 123 part 5: the tail family is one of scan_units' families, so the page's lines above the table are read by it too
    assert nf.unit_of(["Particulars"], ["CIN: L1 ( In Crores)"]) == 1
    assert nf.unit_of(["Particulars"], ["Revenue (Rs. in crores) and costs (Rs. in lakhs)"]) is None


def test_a_month_word_is_never_another_word_that_starts_like_one():
    # TODO 123 part 5: one month rule; OCR's spelling of a month is read through mend_months
    assert nf.month_word("Sept.") and nf.month_word("June,") and nf.month_word("Septemher")
    assert not nf.month_word("Market") and not nf.month_word("Decrease") and not nf.month_word("Marketing")


def test_a_month_line_cut_by_nearest_column_keeps_a_damaged_month_word():
    # TODO 123 part 2: the words go to their nearest columns; a month OCR misspelt ("Septemher") still opens its piece
    line = list(_MONTH_LINE)
    line[3] = (912, 1048, "Septemher")
    assert _header_dates(line, _DAY_LINE) == _header_dates(_MONTH_LINE, _DAY_LINE)


def test_words_of_one_line_are_one_line_however_their_heights_round():
    # 11.9 and 12.1 at a text height of 8 round to two different bands of height (1 and 2) but are one printed line
    got = nf.merge_brackets([nf.Word(10.0, 14.0, 12.1, 8.0, "("), nf.Word(15.0, 30.0, 11.9, 8.0, "12.5"),
                             nf.Word(31.0, 34.0, 12.1, 8.0, ")")], 8.0)
    assert [w.text for w in got] == ["(12.5)"]
    got = nf.merge_space_groups([nf.Word(10.0, 20.0, 12.1, 8.0, "23"), nf.Word(21.0, 40.0, 11.9, 8.0, "909.66")], 8.0)
    assert [w.text for w in got] == ["23909.66"]
    assert nf.date_parts([nf.Word(10.0, 30.0, 12.1, 8.0, "Sept"), nf.Word(32.0, 40.0, 11.9, 8.0, "30")], 8.0) != set()
    # a row's label in reading order: 7.6 and 7.0 at a text height of 8 fall in two bands of 0.6 x 8 (2 and 1)
    cols = [nf.Column(400.0, 440.0, 420.0, 0), nf.Column(460.0, 500.0, 480.0, 1)]
    rows = [nf.NRow(7.3, 3.0, 11.0, "", [None, None])]
    nf.stitch_labels(rows, [nf.Word(10.0, 40.0, 7.6, 8.0, "Other"), nf.Word(45.0, 80.0, 7.0, 8.0, "income")], cols, set(), 8.0, 0.0)
    assert rows[0].label == "Other income"


def test_trap_a_bracketed_unit_after_a_figure_is_that_figure_s_unit_never_the_page_s():
    # review of TODO 123 part 5: "Paid up capital Rs. 5,000 (in lakhs)" above a table with no unit of its own never sets the
    # table's unit (a 100x slip); a header line that ends in the unit ("CIN: L65110JK1938SGC000048 ( In Crores)") still does
    page = ["Registered office: Mumbai", "Paid up capital Rs. 5,000 (in lakhs)", "Statement of Standalone Results"]
    assert nf.unit_of(["Statement of Standalone Results"], page) is None
    assert nf.unit_of(["Particulars"], ["CIN: L65110JK1938SGC000048 ( In Crores)"]) == 1


@pytest.mark.parametrize("word", ["alter", "scales", "faxes", "shape", "taxis", "revenge", "warning", "learnings", "learned", "joins"])
def test_trap_a_real_word_one_letter_from_a_statement_word_is_kept(word):
    # review of TODO 123 part 4: "Provision for alter tax" is never "after tax", "warning" never "earning"
    assert nf.mend_label(word) == word


def test_a_half_year_is_read_only_when_its_two_quarters_add_up_to_it(monkeypatch):
    # out-of-sample test, 30 Oct 2026: every H1 figure of a Q2 statement was "no pbt for H1FY27" (5PAISA, ADOR, CYIENT, MAHLOG)
    assert nf.half_year_column("H1FY27") == ("half", date(2026, 9, 30))
    assert nf.half_year_column("Q2FY27") is None and nf.half_year_column("FY27") is None
    def cells(q1, q2):
        got = {date(2026, 6, 30): q1, date(2026, 9, 30): q2}
        return lambda table, metric, kind, when: (got[when], 0.005, "Revenue", "") if kind == "quarter" else (None, 0, "", "")
    monkeypatch.setattr(nf, "table_figure", cells(1500.25, 1600.5))
    assert nf.half_year_proved(None, "revenue", date(2026, 9, 30), 3100.75, 0.005) == (3100.75, "")
    value, why = nf.half_year_proved(None, "revenue", date(2026, 9, 30), 3050.0, 0.005)      # a column that is not the half year
    assert value is None and "not its two quarters' sum" in why
    monkeypatch.setattr(nf, "table_figure", cells(None, 1600.5))
    assert nf.half_year_proved(None, "revenue", date(2026, 9, 30), 3100.75, 0.005)[0] is None   # one quarter unread: unproven


def _image_page(doc, rect=None, text=""):
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), 0)
    pix.clear_with(200)
    page = doc.new_page()
    page.insert_image(rect or page.rect, pixmap=pix)
    if text:
        page.insert_text((60, 120), text, fontsize=9)
    return page


def test_a_prose_page_with_a_logo_is_never_ocrd_and_a_scanned_page_is_wherever_it_is():
    # out-of-sample test, 30 Oct 2026: an AGM outcome of 25 prose pages, each with a logo, had 16 of them OCR'd (59 s, no
    # table); each page is judged on its own, so a scanned page late in the file is still read
    doc = pymupdf.open()
    for n in range(9):
        _image_page(doc, pymupdf.Rect(20, 20, 80, 50), f"Resolution {n} passed with the requisite majority by the members.")
    _image_page(doc, None, "Statement of Unaudited Financial Results")            # page 10: a full-page scan
    calls = []

    def boxes(png):
        calls.append(png)
        return []
    nf.analyse(doc.tobytes(), boxes, ocr_garbled=True)
    assert len(calls) == 1                         # the scan on page 10 only, never the nine logo pages
    L = type("Layer", (), {"words": []})()
    assert not nf.may_hold_statement(doc[0], L, False)
    assert nf.may_hold_statement(doc[9], L, False)
    assert nf.may_hold_statement(doc[0], L, True)                                  # a likely statement page
    figures = type("Layer", (), {"words": [(0, 0, 1, 1, f"{n}.00") for n in range(15)]})()
    assert nf.may_hold_statement(doc[0], figures, False)                           # a page of figures


def test_a_statement_counts_only_with_revenue_pbt_and_pat_and_never_from_a_page_waiting_for_ocr():
    # NUMFIRST_STOP_EARLY (lead, 30 Oct 2026): the scanned-page OCR stops once every basis has a usable statement; ACI Q1FY27's
    # page 2 named a standalone statement in a garbled layer, and stopping on it lost the four standalone figures OCR gives
    from types import SimpleNamespace as NS
    solved = {"revenue": [1], "pbt": [1], "pat": [1]}
    def table(basis, cls, source="textlayer", named=True, explanations=solved):
        return NS(basis=basis, named=named, source=source, solver=NS(cls=cls, explanations=explanations))
    statement = ["REV", "TE", "PBT", "TAX", "PAT"]
    assert nf.is_statement(table("STANDALONE", statement))
    assert nf.is_statement(table("STANDALONE", ["TI", "PBT", "PAT"], explanations={"total_income": [1], "pbt": [1], "pat": [1]}))
    assert not nf.is_statement(table("STANDALONE", ["REV", "PBT"]))                 # a segment or summary table
    assert not nf.is_statement(table("STANDALONE", statement, explanations={"revenue": [1]}))   # labelled, PBT/PAT unsolved
    pages = {2: [table("STANDALONE", statement)], 5: [table("CONSOLIDATED", statement, "ocr")]}
    assert nf.stated_bases(pages, untrusted=[]) == {"STANDALONE", "CONSOLIDATED"}
    assert nf.stated_bases(pages, untrusted=[2]) == {"CONSOLIDATED"}                # page 2's layer is waiting for OCR
    pages[2].append(table("STANDALONE", statement, "ocr"))                          # its OCR read gave the statement
    assert nf.stated_bases(pages, untrusted=[2]) == {"STANDALONE", "CONSOLIDATED"}


def test_with_the_switch_on_the_scanned_page_ocr_stops_once_every_basis_has_a_statement(monkeypatch):
    # ten full-page scans; once the OCR of the first names the one basis the filing needs, the rest are skipped (switch on) or
    # all read (switch off, as before)
    doc = pymupdf.open()
    for n in range(10):
        _image_page(doc, None, f"Page {n} of a scanned filing with enough words to have a text layer here")
    stated = []
    def read(png):
        stated.append(png)
        return []
    monkeypatch.setattr(nf, "stated_bases", lambda by_page, untrusted: {"STANDALONE"} if stated else set())
    from bse_intel import pdf_readers
    monkeypatch.setattr(pdf_readers, "consolidated_anywhere", lambda *a, **k: False)
    monkeypatch.setenv("NUMFIRST_STOP_EARLY", "1")
    nf.analyse(doc.tobytes(), read, ocr_garbled=True)
    on = len(stated)
    stated.clear()
    monkeypatch.setenv("NUMFIRST_STOP_EARLY", "0")
    nf.analyse(doc.tobytes(), read, ocr_garbled=True)
    assert on == 1 and len(stated) == 10
