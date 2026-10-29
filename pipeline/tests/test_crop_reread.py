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


def test_a_reread_never_helps_name_a_row():
    # review of 0b30926: revenue printed in one column only; one re-read made the identity checkable in two columns and named
    # revenue, total income and other income on that alone
    t = table(revenue=[None, 1896.41, None, None, None], rereads={(0, 0): nf.figure_from_crop("1,912.15", 2)})
    assert "revenue" not in t.named and "total_income" not in t.named


def test_a_crop_pass_that_fails_part_way_leaves_the_table_as_it_was(monkeypatch):
    # review of 0b30926: the first empty cell's re-read stayed on the table when a later crop raised
    import pytest
    cv2 = pytest.importorskip("cv2")      # the crop pass needs the OCR extra, which CI does not install
    import numpy as np
    from bse_intel import ocr
    labels = ["Revenue from operations", "Other income", "Total income (I+II)", "Cost of materials", "Employee benefits",
              "Total expenses", "Profit before tax", "Tax expense"]
    data = [[None, 1896.41, 1436.43, 3808.56, 6512.46], [17.15, 73.78, 23.63, 90.93, 152.40],
            [1929.30, 1970.19, 1460.06, 3899.49, 6664.86], [900.10, 800.20, None, 1700.30, 3000.10],
            [100.10, 110.20, 120.30, 210.30, 400.10], [1000.20, 910.40, 820.60, 1910.60, 3400.20],
            [929.10, 1059.79, 639.46, 1988.89, 3264.66], [200.10, 210.20, 220.30, 410.30, 800.10]]
    cols = [nf.Column(100 * j, 100 * j + 60, 100 * j + 30, j, d, k, True) for j, (d, k) in enumerate(zip(COLS, KINDS))]
    rows = [nf.NRow(10.0 * (n + 1), 10.0 * n + 5, 10.0 * n + 15, lb, [cell(v) for v in vals]) for n, (lb, vals) in enumerate(zip(labels, data))]
    t = nf.Table_solved(nf.Table(1, "CONSOLIDATED", 1.0, cols, rows, "ocr"))
    png = cv2.imencode(".png", np.full((40, 100, 3), 255, np.uint8))[1].tobytes()

    class Pix:
        def tobytes(self, fmt):
            return png

    class Page:
        rotation = 0

        def get_pixmap(self, clip=None, dpi=300):
            return Pix()

    known = [(i, j) for i, r in enumerate(t.rows) for j, c in enumerate(r.cells) if c is not None and not c.nil and c.strict]
    sample = [known[int(n * len(known) / 6)] for n in range(6)]
    queue = [(f"{t.rows[i].cells[j].value:,.2f}", False) for i, j in sample for _ in range(2)] + [("1,912.15", False)] * 2

    def fake(image, deadline=None):
        if not queue:
            raise RuntimeError("crop failed")
        return queue.pop(0)

    monkeypatch.setattr(ocr, "read_cell", fake)
    try:
        nf.reread_empty_cells(Page(), t, 0.0, 1.0, [220])
    except RuntimeError:
        pass
    assert t.rereads == {}
