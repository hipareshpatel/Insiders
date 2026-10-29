"""Synthetic tests of the crop re-read guards (Solver.mask / table_figure / figure_from_crop)."""
from datetime import date

from bse_intel import pdf_numbers_first as nf

COLS = [date(2026, 9, 30), date(2026, 6, 30), date(2025, 9, 30), date(2026, 9, 30), date(2026, 3, 31)]
KINDS = ["quarter", "quarter", "quarter", "half", "year"]
REVENUE = [None, 1896.41, 1436.43, 3808.56, 6512.46]
OTHER = [17.15, 73.78, 23.63, 90.93, 152.40]
TOTAL = [1929.30, 1970.19, 1460.06, 3899.49, 6664.86]


def cell(v):
    return None if v is None else nf.Cell(v, 2, False, True, None, f"{v:.2f}")


def table(revenue=REVENUE, other=OTHER, total=TOTAL, rereads=None):
    cols = [nf.Column(100 * j, 100 * j + 60, 100 * j + 30, j, d, k, True) for j, (d, k) in enumerate(zip(COLS, KINDS))]
    rows = [nf.NRow(10.0 * (n + 1), 10.0 * n + 5, 10.0 * n + 15, label, [cell(v) for v in vals])
            for n, (label, vals) in enumerate((("Revenue from operations", revenue), ("Other income", other), ("Total income (I+II)", total)))]
    t = nf.Table(1, "CONSOLIDATED", 1.0, cols, rows, "ocr")
    t.rereads = rereads or {}
    return nf.Table_solved(t)


def answer(t):
    value, _tol, _label, why = nf.table_figure(t, "revenue", "quarter", date(2026, 9, 30))
    return value, why


def test_no_reread_no_answer():
    assert answer(table())[0] is None


def test_exact_reread_answers():
    assert answer(table(rereads={(0, 0): nf.figure_from_crop("1,912.15", 2)}))[0] == 1912.15


def test_reread_off_by_a_rounding_digit_gives_no_answer():
    # 1912.16 + 17.15 = 1929.31, not the printed 1929.30: inside the usual rounding tolerance, outside the exact one
    t = table(rereads={(0, 0): nf.figure_from_crop("1,912.16", 2)})
    assert answer(t)[0] is None
    assert all(m is not True for m in t.solver.mask((2, ((0, 1), (1, 1))))[:1])


def test_two_rereads_in_one_identity_and_column_give_no_answer():
    # revenue and other income both missing in the period's column, both re-read to values that fit the total exactly
    t = table(other=[None] + OTHER[1:], rereads={(0, 0): nf.figure_from_crop("1,912.15", 2), (1, 0): nf.figure_from_crop("17.15", 2)})
    assert answer(t)[0] is None


def test_reread_never_loosens_the_row_naming():
    # a wrong re-read in the column that decides nothing else leaves the other columns' proof as it was
    t = table(rereads={(0, 0): nf.figure_from_crop("1,912.16", 2)})
    assert "revenue" in t.named


def test_crop_text_parsing():
    assert nf.figure_from_crop("97 35", 2).value == 97.35
    assert nf.figure_from_crop("1,592,88", 2).value == 1592.88
    assert nf.figure_from_crop("(140,17)", 2).value == -140.17
    assert nf.figure_from_crop("3,951.018", 2) is None            # wrong decimals
    assert nf.figure_from_crop("1,912.15 17.15", 2) is None       # two figures
    assert nf.figure_from_crop("1(1.93)", 2) is None
    assert nf.figure_from_crop("", 2) is None
