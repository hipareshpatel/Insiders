"""The balance sheet and the cash flow in the screener cross-check (28 Oct 2026): the page sections are parsed, the lines are
compared on memory's basis against its results-file snapshots, screener's own rules name the gaps, and the pairs are counted
apart from the profit-and-loss ones (``pairs`` and ``by_class`` do not move). The stored sample pages hold the quarters section
only, so the two sections are built to screener's layout and appended to a stored page or to a small page of their own."""

import csv
import io
import json
from pathlib import Path

from bse_intel import screener_crosscheck as sc
from bse_intel import screener_download as sd
from bse_intel.screener_fill import parse_full

FIXTURES = Path(__file__).parent / "fixtures"

BS_ROWS = {  # screener's ten lines, Mar 2025, Mar 2026, Sep 2026 (the latest half year)
    "Equity Capital": [100, 100, 110], "Reserves": [800, 900, 1000], "Borrowings&nbsp;+": [300, 330, 350],
    "Other Liabilities&nbsp;+": [200, 250, 290], "Total Liabilities": [1400, 1580, 1750], "Fixed Assets&nbsp;+": [600, 700, 760],
    "CWIP": [50, 60, 70], "Investments": [250, 280, 300], "Other Assets&nbsp;+": [500, 540, 620], "Total Assets": [1400, 1580, 1750]}
CF_ROWS = {"Cash from Operating Activity&nbsp;+": [150, 180], "Cash from Investing Activity&nbsp;+": [-100, -120],
           "Cash from Financing Activity&nbsp;+": [-30, -40], "Net Cash Flow": [20, 20]}


def section(section_id, rows, columns, basis="Consolidated"):
    head = "".join(f"<th>{c}</th>" for c in columns)
    body = "".join(f"<tr><td>{label}</td>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>" for label, vals in rows.items())
    return (f'<section id="{section_id}"><p>{basis} Figures in Rs. Crores</p><table><thead><tr><th></th>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></section>")


def page_html(bs=BS_ROWS, cf=CF_ROWS, basis="Consolidated"):
    quarters = ('<section id="quarters"><p>' + basis + ' Figures in Rs. Crores</p><table><thead><tr><th></th><th>Mar 2026</th></tr>'
                "</thead><tbody><tr><td>Sales&nbsp;+</td><td>100</td></tr><tr><td>Net Profit&nbsp;+</td><td>10</td></tr>"
                "</tbody></table></section>")
    return (quarters + (section("balance-sheet", bs, ["Mar 2025", "Mar 2026", "Sep 2026"], basis) if bs else "")
            + (section("cash-flow", cf, ["Mar 2025", "Mar 2026"], basis) if cf else ""))


def snap(period, as_of="2026-11-01", source=None, **fields):
    return {"period": period, "as_of": as_of, "source_news_id": source or f"xbrl:res:1:{period}", **fields}


# memory's statements on the same dates, each line equal to screener's
SNAPS = [
    snap("Q4FY25", equity_capital_cr=100.2, reserves_cr=799.6, gross_debt_cr=300.4, total_assets_cr=1400.0, fixed_assets_cr=600.3,
         cwip_cr=50.0, investments_cr=250.1, net_worth_cr=899.8, goodwill_cr=0.0),
    snap("Q4FY26", equity_capital_cr=100.0, reserves_cr=900.0, gross_debt_cr=330.0, total_assets_cr=1580.0, fixed_assets_cr=700.0,
         cwip_cr=60.0, investments_cr=280.0, net_worth_cr=1000.0),
    snap("Q2FY27", equity_capital_cr=110.0, reserves_cr=1000.0, gross_debt_cr=350.0, total_assets_cr=1750.0, fixed_assets_cr=760.0,
         cwip_cr=70.0, investments_cr=300.0, net_worth_cr=1110.0),
]


def entry(metric, period, value):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "basis": "CONSOLIDATED", "as_of": "2026-11-01",
            "source_news_id": f"xbrl:res:1:{period}"}


def dossier(snaps=SNAPS, cash=None, lender=False):
    # a statement takes its basis from the results file it came with: that file's figures carry the basis
    metrics = [entry(name, s["period"], value) for s in snaps for name, value in (("revenue", 100.0), ("pat", 10.0))]
    metrics += [entry(name, period, value) for (name, period), value in (cash or {}).items()]
    d = {"financial_metrics": metrics, "balance_sheet": [dict(s) for s in snaps], "sector": "Demo"}
    if lender:
        d["industry"] = "Financial Services > Banks > Private Sector Bank"
    return d


def compare(d=None, **kw):
    d = d or dossier()
    return sc.compare_company(d, {"CONSOLIDATED": parse_full(page_html(**kw))}, "1", "DEMO")


def bs(result, metric=None, period=None):
    return {(p["period"], p["metric"]): p for p in result["bs_pairs"]
            if (metric is None or p["metric"] == metric) and (period is None or p["period"] == period)}


def cf(result):
    return {(p["period"], p["metric"]): p for p in result["cf_pairs"]}


def with_rows(**changes):
    rows = {k: list(v) for k, v in BS_ROWS.items()}
    for label, vals in changes.items():
        rows[label.replace("_", " ")] = vals
    return rows


# --- the page --------------------------------------------------------------------------------------------------------

def test_the_two_sections_are_read_by_date_and_by_year():
    page = parse_full(page_html())
    assert set(page["balance"]) == {"Q4FY25", "Q4FY26", "Q2FY27"}     # Mar 2026 is Q4FY26, Sep 2026 is Q2FY27
    assert page["balance"]["Q2FY27"] == {"equity_capital": 110.0, "reserves": 1000.0, "borrowings": 350.0, "other_liabilities": 290.0,
                                          "total_liabilities": 1750.0, "fixed_assets": 760.0, "cwip": 70.0, "investments": 300.0,
                                          "other_assets": 620.0, "total_assets": 1750.0}
    assert page["cash_flow"] == {"FY25": {"operating": 150.0, "investing": -100.0, "financing": -30.0, "net": 20.0},
                                 "FY26": {"operating": 180.0, "investing": -120.0, "financing": -40.0, "net": 20.0}}


def test_a_stored_sample_page_has_neither_section_and_still_parses():
    body = (FIXTURES / "screener_abb_standalone.html").read_text(encoding="utf-8")
    page = parse_full(body)
    assert page["balance"] == {} and page["cash_flow"] == {} and page["quarters"]
    both = body.replace("</body>", section("balance-sheet", BS_ROWS, ["Mar 2025", "Mar 2026", "Sep 2026"], "Standalone")
                        + section("cash-flow", CF_ROWS, ["Mar 2025", "Mar 2026"], "Standalone") + "</body>")
    full = parse_full(both)
    assert full["basis"] == "STANDALONE" and full["balance"]["Q4FY26"]["total_assets"] == 1580.0
    assert full["cash_flow"]["FY26"]["operating"] == 180.0 and full["quarters"] == page["quarters"]


def test_a_banks_page_names_its_debt_row_borrowing_and_has_deposits():
    page = parse_full(page_html(bs={"Equity Capital": [10, 10, 10], "Reserves": [90, 95, 99], "Deposits&nbsp;+": [900, 950, 990],
                                     "Borrowing&nbsp;+": [50, 55, 60], "Total Assets": [1050, 1110, 1159]}))
    assert page["balance"]["Q4FY26"] == {"equity_capital": 10.0, "reserves": 95.0, "deposits": 950.0, "borrowings": 55.0,
                                          "total_assets": 1110.0}


# --- the classes -----------------------------------------------------------------------------------------------------

def test_every_line_that_agrees_is_a_match_within_a_crore_or_half_a_percent():
    result = compare()
    assert {p["class"] for p in result["bs_pairs"]} == {"match"}
    # ten lines on each of the three dates, minus the lender-only Deposits row
    assert len(result["bs_pairs"]) == 30 and {p["metric"] for p in result["bs_pairs"]} == set(sc.BS_LINES) - {"deposits"}
    assert {p["class"] for p in result["cf_pairs"]} == set()          # no cash-flow figure in this memory
    # 0.5%: 1,000 against 1,004; a crore: 20 against 20.9
    assert sc.classify_balance("reserves", 1000.0, 1004.0, [], [], False)[0] == "match"
    assert sc.classify_balance("cwip", 20.0, 20.9, [], [], False)[0] == "match"
    assert sc.classify_balance("reserves", 1000.0, 1006.0, [], [], False)[0] == "small_gap"   # past the match, within 1%
    assert sc.classify_balance("reserves", 1000.0, 1020.0, [], [], False)[0] == "mismatch"
    assert sc.classify_balance("cwip", 20.0, 21.1, [], [], False)[0] == "mismatch"           # 1.1 Cr: neither a Cr nor 1%


def test_total_liabilities_is_compared_with_our_total_assets_never_our_total_liabilities():
    snaps = [dict(s, total_liabilities_cr=s["total_assets_cr"] - s["net_worth_cr"]) for s in SNAPS]      # liabilities without equity
    result = compare(dossier(snaps))
    pair = bs(result, "total_liabilities", "Q4FY26")[("Q4FY26", "total_liabilities")]
    assert pair["class"] == "match" and pair["memory_value"] == 1580.0 and pair["screener_value"] == 1580.0


def test_a_larger_screener_borrowings_without_a_found_part_is_never_a_definition():
    # screener's Borrowings hold lease liabilities (rules row 10): 330 in memory, 380 on screener. With no facts stored the part
    # is not shown, so the gap is not explained: independent review, 28 Oct 2026 (a "definition" there hid a missing block)
    rows = with_rows(**{"Borrowings&nbsp;+": [300, 380, 350], "Other_Liabilities&nbsp;+": [200, 200, 290],
                        "Total_Liabilities": [1400, 1580, 1750]})
    result = compare(**{"bs": rows})
    pair = bs(result, "borrowings", "Q4FY26")[("Q4FY26", "borrowings")]
    assert pair["class"] == "unexplained_larger" and "50 more on screener" in pair["note"] and "no XBRL facts stored" in pair["note"]
    assert not any(p["class"].startswith("definition") for p in result["bs_pairs"])
    # the plug carries the same 50 the other way: not a second error
    plug = bs(result, "other_liabilities", "Q4FY26")[("Q4FY26", "other_liabilities")]
    assert plug["memory_value"] == 250.0 and plug["screener_value"] == 200.0
    assert plug["class"] == "derived:part_differs" and "borrowings" in plug["note"] and plug["note"].startswith("informational (plug)")
    # the other direction has no rule: ours bigger than screener's is a mismatch
    smaller = compare(**{"bs": with_rows(**{"Borrowings&nbsp;+": [300, 250, 350]})})
    assert bs(smaller, "borrowings", "Q4FY26")[("Q4FY26", "borrowings")]["class"] == "mismatch"


def test_fixed_assets_with_goodwill_then_with_intangibles_and_right_of_use():
    snaps = [dict(s) for s in SNAPS]
    snaps[1]["goodwill_cr"] = 30.0
    snaps[2]["goodwill_cr"] = 30.0
    goodwill = compare(dossier(snaps), bs=with_rows(**{"Fixed_Assets&nbsp;+": [600, 730, 760]}))
    assert bs(goodwill, "fixed_assets", "Q4FY26")[("Q4FY26", "fixed_assets")]["class"] == "matches_screener_view:goodwill_in_fixed_assets"
    # goodwill does not close Q2FY27 (760 + 30 against 900) and no intangible or right-of-use line is shown: not explained
    wide = compare(dossier(snaps), bs=with_rows(**{"Fixed_Assets&nbsp;+": [600, 730, 900]}))
    assert bs(wide, "fixed_assets", "Q2FY27")[("Q2FY27", "fixed_assets")]["class"] == "unexplained_larger"
    # nothing explains a screener figure below ours
    below = compare(bs=with_rows(**{"Fixed_Assets&nbsp;+": [600, 500, 760]}))
    assert bs(below, "fixed_assets", "Q4FY26")[("Q4FY26", "fixed_assets")]["class"] == "mismatch"


def test_cwip_and_investments_are_not_named_without_a_tagged_part_and_a_lenders_investments_never():
    result = compare(bs=with_rows(CWIP=[50, 90, 70], Investments=[250, 340, 300]))
    assert bs(result, "cwip", "Q4FY26")[("Q4FY26", "cwip")]["class"] == "unexplained_larger"
    assert bs(result, "investments", "Q4FY26")[("Q4FY26", "investments")]["class"] == "unexplained_larger"
    bank = compare(dossier(lender=True), bs=with_rows(Investments=[250, 340, 300]))
    assert bs(bank, "investments", "Q4FY26")[("Q4FY26", "investments")]["class"] == "mismatch"


def test_reserves_from_net_worth_less_capital_when_there_is_no_other_equity_line():
    snaps = [dict(s) for s in SNAPS]
    del snaps[1]["reserves_cr"]                                                  # an insurer's file: net worth and capital only
    only = compare(dossier(snaps))
    pair = bs(only, "reserves", "Q4FY26")[("Q4FY26", "reserves")]
    assert pair["class"] == "match" and pair["memory_value"] == 900.0           # 1,000 - 100
    snaps = [dict(s) for s in SNAPS]
    snaps[1]["reserves_cr"] = 870.0                                              # other equity 870, net worth less capital 900
    view = compare(dossier(snaps))
    assert bs(view, "reserves", "Q4FY26")[("Q4FY26", "reserves")]["class"] == "matches_screener_view:net_worth_less_capital"


def test_the_plugs_need_every_part_and_a_plug_with_all_parts_equal_is_a_plain_mismatch():
    snaps = [dict(s) for s in SNAPS]
    del snaps[1]["gross_debt_cr"]
    result = compare(dossier(snaps))
    assert ("Q4FY26", "other_liabilities") not in bs(result) and ("Q4FY26", "borrowings") not in bs(result)
    assert ("Q4FY26", "other_assets") in bs(result)
    # every part equal, the plug 40 off: screener's own identity does not hold, nothing explains it
    odd = compare(bs=with_rows(**{"Other_Liabilities&nbsp;+": [200, 290, 290]}))
    pair = bs(odd, "other_liabilities", "Q4FY26")[("Q4FY26", "other_liabilities")]
    assert pair["class"] == "mismatch" and pair["memory_value"] == 250.0


def test_a_figure_stored_under_another_date_is_wrong_period():
    snaps = [dict(s) for s in SNAPS]
    snaps[2]["reserves_cr"] = 900.0                  # memory's Sep 2026 reserves are screener's Mar 2026 figure
    result = compare(dossier(snaps))
    pair = bs(result, "reserves", "Q2FY27")[("Q2FY27", "reserves")]
    assert pair["class"] == "wrong_period" and pair["shifted"] == ["Q4FY26"] and "Q4FY26" in pair["note"]


def test_a_unit_slip_is_scale():
    snaps = [dict(s) for s in SNAPS]
    snaps[1]["reserves_cr"] = 90.0
    assert bs(compare(dossier(snaps)), "reserves", "Q4FY26")[("Q4FY26", "reserves")]["class"] == "scale"


def test_only_results_file_statements_on_memorys_basis_are_compared():
    snaps = [dict(s) for s in SNAPS]
    snaps[1]["source_news_id"] = "nse-9"             # a card's figure, not the exchange file's
    assert ("Q4FY26", "total_assets") not in bs(compare(dossier(snaps)))
    d = dossier()
    d["standalone"] = {"metrics": [], "balance_sheet": [snap("Q4FY26", total_assets_cr=1.0, source="xbrl:res-sa:1:Q4FY26")]}
    assert bs(compare(d), "total_assets", "Q4FY26")[("Q4FY26", "total_assets")]["memory_value"] == 1580.0   # not the standalone part


def test_cash_flow_classes():
    cash = {("operating_cash_flow", "FY26"): 180.4, ("investing_cash_flow", "FY26"): 120.0,        # ours has the sign wrong
            ("financing_cash_flow", "FY26"): -30.0,                                                   # ours is screener's FY25
            ("net_cash_flow", "FY26"): 2.0,                                                           # a tenth
            ("operating_cash_flow", "FY25"): 150.0}
    result = compare(dossier(cash=cash))
    got = cf(result)
    assert got[("FY26", "operating")]["class"] == "match" and got[("FY25", "operating")]["class"] == "match"
    assert got[("FY26", "investing")]["class"] == "sign"
    assert got[("FY26", "financing")]["class"] == "wrong_period" and got[("FY26", "financing")]["shifted"] == ["FY25"]
    assert got[("FY26", "net")]["class"] == "scale"
    assert all(p["table"] == "cash_flow" for p in result["cf_pairs"])


def test_the_new_pairs_do_not_touch_the_existing_ones():
    plain = sc.compare_company(dossier(), {"CONSOLIDATED": parse_full(page_html(bs=None, cf=None))}, "1", "DEMO")
    full = compare()
    assert plain["bs_pairs"] == [] and plain["cf_pairs"] == []
    assert full["pairs"] == plain["pairs"] and full["six_pairs"] == plain["six_pairs"] and full["gaps"] == plain["gaps"]


# --- the counts and the files ---------------------------------------------------------------------------------------------

def result_with_gaps():
    rows = with_rows(**{"Borrowings&nbsp;+": [300, 380, 350], "Other_Liabilities&nbsp;+": [200, 200, 290]})
    cash = {("operating_cash_flow", "FY26"): 180.0, ("investing_cash_flow", "FY26"): 120.0}
    return compare(dossier(cash=cash), bs=rows)


def test_summary_counts_the_lines_apart_and_the_rows_reach_the_csv_marked_by_table():
    plain = sc.summarise([sc.compare_company(dossier(), {"CONSOLIDATED": parse_full(page_html(bs=None, cf=None))}, "1", "DEMO")], "2026-10-28")
    out = sc.summarise([result_with_gaps()], "2026-10-28")
    assert out["pairs"] == plain["pairs"] and out["by_class"] == plain["by_class"] and out["six_pairs"] == plain["six_pairs"]
    assert out["bs_pairs"] == 30 and out["cf_pairs"] == 2
    assert list(out["bs_by_line"]) == [line for line in sc.BS_LINES if line != "deposits"]
    assert out["bs_by_line"]["borrowings"]["unexplained_larger"] == 1 and out["bs_by_line"]["borrowings"]["match"] == 2
    assert out["bs_by_line"]["other_liabilities"]["derived:part_differs"] == 1
    assert out["cf_by_line"]["investing"]["sign"] == 1 and out["cf_by_line"]["operating"]["match"] == 1
    # the referees read summary["rows"]: the new rows are not in it
    assert not any(r.get("table") in ("balance_sheet", "cash_flow") for r in out["rows"])
    rows = list(csv.DictReader(io.StringIO(sc.to_csv(out))))
    marked = {(r["table"], r["metric"], r["class"]) for r in rows if r["table"] in ("balance_sheet", "cash_flow")}
    assert marked == {("balance_sheet", "borrowings", "unexplained_larger"),
                      ("balance_sheet", "other_liabilities", "derived:part_differs"), ("cash_flow", "investing", "sign")}
    assert rows[0].keys() >= {"scrip", "symbol", "table", "class", "memory_value", "screener_value"}
    assert all(r["table"] for r in rows)                                                    # every row says which table it is
    assert "table_rows" not in json.loads(sc.to_json(out)) and json.loads(sc.to_json(out))["bs_pairs"] == 30


def test_the_report_and_the_text_summary_carry_per_line_counts():
    out = sc.summarise([result_with_gaps()], "2026-10-28")
    text = sc.render(out)
    assert "balance sheet, pairs" in text and "borrowings" in text and "unexplained_larger 1" in text
    assert "cash flow, pairs" in text and "sign 1" in text
    md = sc.to_markdown(out, "2026-10-28")
    assert "## The balance sheet" in md and "## The cash flow" in md and "| borrowings | 3 |" in md and "| investing | 1 |" in md
    # no balance-sheet or cash-flow pair: no section, and the older reports are as they were
    empty = sc.summarise([sc.compare_company(dossier(), {"CONSOLIDATED": parse_full(page_html(bs=None, cf=None))}, "1", "DEMO")])
    assert "## The balance sheet" not in sc.to_markdown(empty, "2026-10-28") and "balance sheet" not in sc.render(empty)


class Sink:
    def __init__(self, dossiers):
        self.dossiers, self.objects = dossiers, {}

    def list_objects(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))

    def get_object(self, key):
        return self.objects.get(key)

    def get_dossier(self, scrip):
        return self.dossiers.get(scrip)

    def query(self, name, params):
        return []


def test_a_full_run_over_a_stored_page_compares_both_tables_and_writes_nothing():
    sink = Sink({"1": dossier(cash={("operating_cash_flow", "FY26"): 180.0})})
    sink.objects["raw/screener/2026-10-28/DEMO_c.html.gz"] = sd.pack(page_html())
    before = dict(sink.objects)
    out = sc.run(sink, [("1", "DEMO")], workers=1)
    assert out["bs_pairs"] == 30 and out["cf_pairs"] == 1 and out["companies_compared"] == 1
    assert out["bs_by_line"]["total_assets"]["match"] == 3 and sink.objects == before
