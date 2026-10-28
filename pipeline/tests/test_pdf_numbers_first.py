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
