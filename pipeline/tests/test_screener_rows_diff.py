from bse_intel import screener_rows_diff as srd

HEAD = "company,sector,industry,basis,period,table,row,screener,ours,diff,status,recipe note\n"


def csv_of(*rows):
    return HEAD + "".join(f"{c},x,y,CONSOLIDATED,{p},{t},{r},100,{o},0,{s},n\n" for c, p, t, r, o, s in rows)


def test_broken_and_mended_pairs_are_counted_by_class_and_new_pairs_apart():
    prev = csv_of(*[(f"C{i}", "FY25", "annual", "Expenses", 100, "ok") for i in range(6)], ("D", "FY25", "annual", "Sales", 90, "apart"))
    curr = csv_of(*[(f"C{i}", "FY25", "annual", "Expenses", 120, "apart") for i in range(6)], ("D", "FY25", "annual", "Sales", 100, "ok"),
                  ("E", "FY26", "annual", "Sales", 100, "ok"))
    got = srd.compare(prev, curr)
    assert got["broke"][("annual", "Expenses")] == 6 and got["mended"][("annual", "Sales")] == 1 and got["new_pairs"] == 1
    assert srd.worse_classes(got) == [(("annual", "Expenses"), 6, 0)]
    assert got["shares"][0]["annual"] == (6, 7) and got["shares"][1]["annual"] == (2, 8)
    report = srd.render(got)
    assert "annual: Expenses: broke 6, mended 0" in report and "C0 cons FY25: 100 -> 120" in report


def test_pairs_before_fy23_are_not_in_the_shares():
    rows = csv_of(("A", "FY22", "annual", "Sales", 100, "ok"), ("A", "Q1FY26", "quarters", "Sales", 100, "ok"))
    assert srd.exact_shares(srd._rows(rows)) == {"quarters": (1, 1)}
