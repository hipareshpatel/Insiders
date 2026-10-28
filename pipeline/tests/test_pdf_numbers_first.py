"""The experimental numbers-first reader (pdf_numbers_first.py): small statements drawn with PyMuPDF, no OCR, no network."""

from __future__ import annotations

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
    assert parts == [(321, "30"), (378, "30,"), (641, "12")]   # "30" alone (x 500) is a figure; "15" stands apart from "May"
    # "Margin 12" is taken out too (the month pattern matches "mar..."): that only ever removes a cell, never adds a figure


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
