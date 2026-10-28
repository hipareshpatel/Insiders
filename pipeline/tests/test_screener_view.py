"""screener_view.py: one fixed recipe per screener website row (owner, 28 Oct 2026), the comparison command screener-rows."""

import csv
import io
import json
from datetime import date
from pathlib import Path

import pytest

from bse_intel import cli, screener_view as sv, xbrl_facts as xf

FIXTURES = Path(__file__).parent / "fixtures"
CR = 1e7


def results(name):
    return xf.Facts(xf.parse_facts((FIXTURES / name).read_bytes(), "1"))


# --- a small synthetic facts doc ----------------------------------------------------------------------------------------

def doc(facts, kind="annual", template="MCA-INDAS", year=2026):
    """``facts``: (element, context, crore value or text). Contexts: D<year> (12 months), Q<year> (3 months to March), I<year>
    (instant at the year end), and the dimensional ones of ROWS below."""
    contexts = {}
    for y in (year, year - 1):
        contexts[f"D{y}"] = {"s": f"{y - 1}-04-01", "e": f"{y}-03-31", "m": 12}
        contexts[f"Q{y}"] = {"s": f"{y}-01-01", "e": f"{y}-03-31", "m": 3}
        contexts[f"I{y}"] = {"i": f"{y}-03-31"}
        for member in ("M1", "M2", "M3", "M4"):
            # an annual report: a row's description on the duration, its amount on the instant, the same (typed) member
            contexts[f"D{y}_{member}"] = {"s": f"{y - 1}-04-01", "e": f"{y}-03-31", "m": 12, "d": {"RowAxis": member}}
            contexts[f"I{y}_{member}"] = {"i": f"{y}-03-31", "d": {"RowAxis": member}}
    rows = []
    for el, ctx, value in facts:
        if isinstance(value, str):
            rows.append([el, ctx, None, value, None])
        else:
            rows.append([el, ctx, "INR", int(round(value * CR)), -5])
    return {"v": 1, "kind": kind, "template": template, "basis": "CONSOLIDATED", "contexts": contexts, "units": {"INR": "MONEY"},
            "facts": rows}


ANNUAL = [
    ("RevenueFromOperations", "D2026", 1000.0), ("ExciseDuty", "D2026", 100.0), ("OtherIncome", "D2026", 30.0),
    ("Expenses", "D2026", 750.0), ("FinanceCosts", "D2026", 20.0), ("DepreciationDepletionAndAmortisationExpense", "D2026", 40.0),
    (sv.LOSS_ON_DISPOSAL, "D2026", 5.0), ("ExceptionalItemsBeforeTax", "D2026", -10.0), ("ProfitBeforeTax", "D2026", 270.0),
    ("TaxExpense", "D2026", 70.0), ("ProfitLossForPeriod", "D2026", 200.0), ("ProfitOrLossAttributableToOwnersOfParent", "D2026", 190.0),
    ("ProfitOrLossAttributableToNonControllingInterests", "D2026", 10.0),
    # balance sheet
    ("EquityShareCapital", "I2026", 10.0), ("OtherEquity", "I2026", 500.0), ("BorrowingsNoncurrent", "I2026", 100.0),
    ("BorrowingsCurrent", "I2026", 50.0), ("PropertyPlantAndEquipment", "I2026", 300.0), ("Goodwill", "I2026", 20.0),
    ("OtherIntangibleAssets", "I2026", 10.0), ("CapitalWorkInProgress", "I2026", 15.0), ("IntangibleAssetsUnderDevelopment", "I2026", 5.0),
    ("NoncurrentInvestments", "I2026", 60.0), ("CurrentInvestments", "I2026", 40.0), ("InvestmentsAccountedForUsingEquityMethod", "I2026", 25.0),
    ("Assets", "I2026", 1000.0), ("DeferredTaxAssetsNet", "I2026", 8.0), ("DeferredTaxLiabilitiesNet", "I2026", 3.0),
    # rows: a non-current lease (DescriptionOther..., no "Of"), a current lease, a current maturity, a right-of-use asset
    ("DescriptionOtherNoncurrentFinancialLiabilitiesOthers", "D2026_M1", "Lease liabilities"),
    ("OtherNoncurrentFinancialLiabilitiesOthers", "I2026_M1", 30.0),
    ("DescriptionOfOtherCurrentFinancialLiabilitiesOthers", "D2026_M2", "Current lease liabilities"),
    ("OtherCurrentFinancialLiabilitiesOthers", "I2026_M2", 12.0),
    ("DescriptionOfOtherCurrentFinancialLiabilitiesOthers", "D2026_M3", "Current maturities of deferred payment liabilities"),
    ("OtherCurrentFinancialLiabilitiesOthers", "I2026_M3", 7.0),
    ("DescriptionOfOtherNoncurrentAssetsOthers", "D2026_M4", "Right-of-use assets"),
    ("OtherNoncurrentAssetsOthers", "I2026_M4", 45.0),
    # cash flow
    ("CashFlowsFromUsedInOperatingActivities", "D2026", 210.0), ("CashFlowsFromUsedInInvestingActivities", "D2026", -90.0),
    ("EffectOfExchangeRateChangesOnCashAndCashEquivalents", "D2026", 2.0), ("CashFlowsFromUsedInFinancingActivities", "D2026", -100.0),
    ("IncreaseDecreaseInCashAndCashEquivalents", "D2026", 22.0),
]
END = date(2026, 3, 31)


def annual_facts(extra=()):
    return xf.Facts(doc(ANNUAL + list(extra)))


def values(rows):
    return {k: (None if r.value is None else round(r.value, 2)) for k, r in rows.items()}


def test_corporate_profit_and_loss_by_the_fixed_recipes():
    got = values(sv.corporate_pl(sv._Reader(annual_facts(), end=END, months=12)))
    assert got["Sales"] == 900.0                       # 1,000 less excise 100
    assert got["Expenses"] == 750 - 20 - 40 - 100 - 5  # less finance costs, depreciation, excise and the loss on disposal
    assert got["Operating Profit"] == 900 - 585
    assert got["Interest"] == 20.0 and got["Depreciation"] == 40.0
    # the identity: PBT + depreciation + interest - operating profit = other income + exceptional - loss on disposal
    assert got["Other Income"] == 270 + 40 + 20 - 315 == 30 - 10 - 5
    assert got["Profit before tax"] == 270.0 and round(got["Tax %"], 2) == round(100 * 70 / 270, 2)
    assert got["Net Profit"] == 200.0 and got["Net Profit (owners)"] == 190.0 and got["Minority share"] == 10.0
    tax_on = 70 * -10 / 270
    assert got["Exceptional items AT"] == round(-10 - tax_on, 2) and got["Profit for PE"] == round(190 - (-10 - tax_on), 2)


def test_associates_and_a_utilitys_regulatory_deferral_movement_are_in_pbt_and_other_income():
    """SEBI's results format puts both below the filed PBT; screener's PBT holds them (Coal India Q4FY26 14,510.7 + 116.1 =
    14,626.75; NTPC Q1FY26 5,281.2 + 2,007.3 + 476.6 = 7,765.06; measured 28 Oct 2026 on the owner's Excel files)."""
    extra = [(sv.ASSOCIATES, "D2026", 9.0), (sv.REGULATORY_DEFERRAL, "D2026", 6.0)]
    rows = sv.corporate_pl(sv._Reader(annual_facts(extra), end=END, months=12))
    assert rows["Profit before tax"].value == pytest.approx(270 + 9 + 6) and rows["PBT as filed"].value == pytest.approx(270.0)
    assert rows["Other Income"].value == pytest.approx(15.0 + 9 + 6) and "differ" not in rows["Other Income"].note
    assert rows["Tax %"].value == pytest.approx(100 * 70 / 285)


def test_the_other_income_note_says_when_the_parts_and_the_identity_differ():
    stray = [("ProfitBeforeTax", "D2026", 273.0)]   # a PBT 3 above what its lines add up to
    facts = xf.Facts(doc([x for x in ANNUAL if x[0] != "ProfitBeforeTax"] + stray))
    rows = sv.corporate_pl(sv._Reader(facts, end=END, months=12))
    assert rows["Other Income"].value == pytest.approx(18.0)
    assert "parts" in rows["Other Income"].note and "differ by 3.00" in rows["Other Income"].note


def test_sales_tax_and_discount_rows_of_the_other_expenses_breakdown_leave_sales_and_expenses():
    contexts_extra = [("DescriptionOfOtherExpenses", "D2026_M1", "Sales tax"), ("OtherExpenses", "D2026_M1", 6.0),
                      ("DescriptionOfOtherExpenses", "D2026_M2", "Discounts"), ("OtherExpenses", "D2026_M2", 4.0)]
    got = values(sv.corporate_pl(sv._Reader(annual_facts(contexts_extra), end=END, months=12)))
    assert got["Sales"] == 890.0 and got["Expenses"] == 575.0 and got["Operating Profit"] == 315.0


def test_the_financial_services_finance_cost_moves_to_interest_and_is_read_from_the_q4_file_for_an_annual_report():
    q4 = xf.Facts(doc([("DescriptionOfOtherExpenses", "D2026_M1", "Finance cost of financial services business and finance lease activity"),
                       ("OtherExpenses", "D2026_M1", 25.0)], kind="results", template="INDAS"))
    rows = sv.corporate_pl(sv._Reader(annual_facts(), end=END, months=12), fallback=sv._Reader(q4, end=END, months=12))
    assert rows["Interest"].value == pytest.approx(45.0) and "Q4 results file" in rows["Interest"].note
    assert rows["Expenses"].value == pytest.approx(560.0)
    assert rows["Other Income"].value == pytest.approx(15.0)     # unchanged: the cost moves from one line to the other


def test_the_segment_interest_element_is_not_added_to_interest():
    seg = [("InterestExpenseReportableSegment", "D2026", 20.0)]   # Wipro FY26: equal to its finance costs
    assert sv.corporate_pl(sv._Reader(annual_facts(seg), end=END, months=12))["Interest"].value == pytest.approx(20.0)


def test_corporate_balance_sheet_reads_rows_described_on_the_year_with_amounts_at_the_year_end():
    got = values(sv.corporate_bs(sv._Reader(annual_facts(), instant=END)))
    assert got["Borrowings"] == 100 + 50 + 30 + 12 + 7
    assert got["Fixed Assets"] == 300 + 20 + 10 + 45
    assert got["CWIP"] == 20.0 and got["Investments"] == 125.0
    assert got["Total Assets"] == got["Total Liabilities"] == 997.0           # less min(DTA 8, DTL 3)
    assert got["Other Liabilities"] == 997 - 10 - 500 - 199
    assert got["Other Assets"] == 997 - 375 - 20 - 125


def test_lease_elements_win_over_lease_rows_and_current_maturities_rows_still_count():
    got = values(sv.corporate_bs(sv._Reader(annual_facts([("LeaseLiabilitiesNoncurrent", "I2026", 3.0),
                                                           ("LeaseLiabilitiesCurrent", "I2026", 1.0)]), instant=END)))
    assert got["Borrowings"] == 100 + 50 + 3 + 1 + 7


def test_the_joined_reader_is_off_by_default_so_the_crosscheck_does_not_move():
    facts = annual_facts()
    assert facts.described(("OtherNoncurrentFinancialLiabilitiesOthers",), "lease", instant=END) == []
    assert facts.described(("OtherNoncurrentFinancialLiabilitiesOthers",), "lease", instant=END, joined=True) == \
        [("OtherNoncurrentFinancialLiabilitiesOthers", "Lease liabilities", 30.0)]


def test_cash_flow_investing_holds_the_exchange_effect():
    got = values(sv.cf_rows(sv._Reader(annual_facts(), end=END, months=12)))
    assert got == {"Cash from Operating Activity": 210.0, "Cash from Investing Activity": -88.0,
                   "Cash from Financing Activity": -100.0, "Net Cash Flow": 22.0}


def test_a_missing_element_is_no_value_with_the_reason():
    rows = sv.corporate_pl(sv._Reader(xf.Facts(doc([("RevenueFromOperations", "D2026", 5.0)])), end=END, months=12))
    assert rows["Sales"].value == 5.0 and rows["Expenses"].value is None and "missing Expenses" in rows["Expenses"].note


# --- the fixtures -------------------------------------------------------------------------------------------------------

def test_hdfc_bank_quarter_and_half_year_by_the_bank_recipe():
    facts = results("nse_hdfcbank_q2fy27_cons.xml")
    assert sv.family(facts.doc["template"]) == sv.BANK
    q = sv.bank_pl(sv._Reader(facts, end=date(2026, 9, 30), months=3))
    assert q["Revenue"].value == pytest.approx(facts.cr("InterestEarned", end=date(2026, 9, 30), months=3))
    # a negative exceptional item is added back to PBT (HDFC Bank: screener's PBT is before it); none goes to other income
    assert q["Profit before tax"].value == pytest.approx(27825.48 + 837.06, abs=0.01)
    assert q["Other Income"].value == pytest.approx(34227.06, abs=0.01)
    assert q["Depreciation"].value is None and q["Expenses"].value is None      # the quarter has no cash flow
    h = sv.bank_pl(sv._Reader(facts, end=date(2026, 9, 30), months=6))
    assert h["Expenses"].value == pytest.approx(100308.45 + 8011.84 - 2218.68, abs=0.02)
    assert h["Financing Profit"].value == pytest.approx(h["Revenue"].value - h["Interest"].value - h["Expenses"].value)
    bs = sv.bank_bs(sv._Reader(facts, instant=date(2026, 9, 30)))
    assert set(bs) == {"Equity Capital", "Deposits", "Borrowing"} and bs["Borrowing"].value == pytest.approx(594143.54, abs=0.01)


def test_a_positive_bank_exceptional_item_goes_to_other_income_and_pbt_stays_as_filed():
    facts = xf.Facts(doc([("InterestEarned", "D2026", 100.0), ("OtherIncome", "D2026", 10.0), ("ExceptionalItems", "D2026", 3.0),
                          ("ProfitLossFromOrdinaryActivitiesBeforeTax", "D2026", 40.0)], template="BANKING"))
    rows = sv.bank_pl(sv._Reader(facts, end=END, months=12))
    assert rows["Other Income"].value == pytest.approx(13.0) and rows["Profit before tax"].value == pytest.approx(40.0)


def test_titan_quarter_by_the_corporate_recipe():
    facts = results("nse_old_titan_q2fy24.xml")
    rows = sv.corporate_pl(sv._Reader(facts, end=date(2023, 9, 30), months=3))
    assert rows["Sales"].value == pytest.approx(facts.cr("RevenueFromOperations", end=date(2023, 9, 30), months=3))
    assert rows["Net Profit"].value == pytest.approx(915.7, abs=0.01) and rows["Net Profit (owners)"].value == pytest.approx(915.0)
    op = rows["Operating Profit"].value
    assert rows["Other Income"].value == pytest.approx(rows["Profit before tax"].value + rows["Depreciation"].value
                                                       + rows["Interest"].value - op)


def test_family_by_template_only():
    assert [sv.family(t) for t in ("INDAS", "BANKING", "LEGACY_BANKING", "NBFC", "LI", "GI", "OTHERTHANBANK", "", None)] == \
        [sv.CORPORATE, sv.BANK, sv.BANK, sv.NBFC, sv.INSURER, sv.INSURER, sv.CORPORATE, sv.CORPORATE, sv.CORPORATE]


# --- the year's source ----------------------------------------------------------------------------------------------------

def _store(docs):
    objects = {key: xf.dumps(d) for key, d in docs.items()}
    return sv.CompanyFacts(list(objects), objects.get)


def test_a_year_comes_from_the_newest_annual_report_that_holds_it_else_the_q4_file():
    fy26 = doc([("RevenueFromOperations", "D2026", 1.0), ("RevenueFromOperations", "D2025", 2.0), ("Assets", "I2025", 9.0)])
    fy25 = doc([("RevenueFromOperations", "D2025", 3.0)], year=2025)
    q4 = doc([("RevenueFromOperations", "D2024", 4.0)], kind="results", template="INDAS", year=2024)
    cf = _store({xf.annual_key("1", "FY26", "CONSOLIDATED"): fy26, xf.annual_key("1", "FY25", "CONSOLIDATED"): fy25,
                 xf.key("1", "Q4FY24", "CONSOLIDATED"): q4})
    facts, label, _ = cf.year("FY25", "CONSOLIDATED", sv.CORPORATE)
    assert label == "annual report FY26" and facts.cr("RevenueFromOperations", end=date(2025, 3, 31), months=12) == 2.0
    assert cf.year("FY25", "CONSOLIDATED", sv.CORPORATE, instant=True)[1] == "annual report FY26"
    assert cf.year("FY24", "CONSOLIDATED", sv.CORPORATE)[1] == "results file Q4FY24"
    assert cf.year("FY25", "CONSOLIDATED", sv.BANK)[1] == "results file Q4FY25"     # a lender: always the Q4 file


# --- the page and the comparison ------------------------------------------------------------------------------------------

def section(section_id, rows, columns):
    head = "".join(f"<th>{c}</th>" for c in columns)
    body = "".join(f"<tr><td>{label}</td>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>" for label, vals in rows.items())
    return (f'<section id="{section_id}"><p>Consolidated Figures in Rs. Crores</p><table><thead><tr><th></th>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></section>")


PAGE = (section("profit-loss", {"Sales&nbsp;+": [900, 50], "Expenses&nbsp;+": [600, 1], "Net Profit&nbsp;+": [200, 1],
                                "EPS in Rs": [9, 1], "Dividend Payout %": [10, 1]}, ["Mar 2026", "Mar 2024"])
        + section("balance-sheet", {"Borrowings&nbsp;+": ["1,99", 1], "Deposits": [5, 1]}, ["Mar 2026", "Mar 2024"])
        + section("cash-flow", {"Cash from Investing Activity&nbsp;+": [-88, 1]}, ["Mar 2026", "Dec 2024"]))


def test_compare_marks_each_pair_ok_apart_no_facts_or_no_recipe():
    page = sv.parse_page(PAGE.replace('"1,99"', "199"))
    assert page["basis"] == "CONSOLIDATED" and "EPS in Rs" not in page["tables"]["annual"]
    cf = _store({xf.annual_key("1", "FY26", "CONSOLIDATED"): doc(ANNUAL)})
    rows = {(r["table"], r["row"], r["period"]): r for r in sv.compare(page, cf, "1", "DEMO")}
    assert rows[("annual", "Sales", "FY26")]["status"] == "ok" and "annual report FY26" in rows[("annual", "Sales", "FY26")]["note"]
    assert rows[("annual", "Expenses", "FY26")]["status"] == "apart" and rows[("annual", "Expenses", "FY26")]["diff"] == -15.0
    assert rows[("annual", "Sales", "FY24")]["status"] == "no_facts"
    assert rows[("balance", "Borrowings", "Q4FY26")]["status"] == "ok"
    assert rows[("balance", "Deposits", "Q4FY26")]["status"] == "no_recipe"
    assert rows[("cash_flow", "Cash from Investing Activity", "FY26")]["status"] == "ok"
    assert rows[("cash_flow", "Cash from Investing Activity", "YE:2024-12")]["status"] == "no_facts"
    summary = sv.summarise([{"scrip": "1", "symbol": "DEMO", "rows": list(rows.values()), "skipped": None}], "2026-10-28")
    assert summary["by_row"]["annual: Sales"]["exact_share"] == 1.0
    assert summary["per_company"][0]["rows_apart"] == ["annual: Expenses"]
    table = list(csv.reader(io.StringIO(sv.to_csv(summary))))
    assert tuple(table[0]) == sv.CSV_HEADER and len(table) == 1 + summary["pairs"]
    assert "| annual: Sales | 1 | 0 | 100.0% |" in sv.to_markdown(summary, "2026-10-28")


def test_tolerance_is_one_crore_or_five_hundredths_of_a_percent_and_half_a_point_for_percent_rows():
    assert sv.exact(100.9, 100.0, "Sales") and not sv.exact(101.2, 100.0, "Sales")
    assert sv.exact(100_040.0, 100_000.0, "Sales") and not sv.exact(100_060.0, 100_000.0, "Sales")
    assert sv.exact(25.4, 25.0, "Tax %") and not sv.exact(25.6, 25.0, "Tax %")


class Sink:
    def __init__(self, objects):
        self.objects = objects

    def list_objects(self, prefix):
        return [k for k in self.objects if k.startswith(prefix)]

    def get_object(self, key):
        return self.objects.get(key)


def test_run_reads_only_stored_pages_and_facts():
    from bse_intel import screener_download as sd

    objects = {f"{sd.PREFIX}2026-10-27/DEMO_c.html.gz": __import__("gzip").compress(PAGE.encode()),
               xf.annual_key("1", "FY26", "CONSOLIDATED"): xf.dumps(doc(ANNUAL))}
    summary = sv.run(Sink(objects), [("1", "DEMO"), ("2", "NONE")], workers=1)
    assert summary["pages_day"] == "2026-10-27" and summary["by_status"]["ok"] >= 2
    assert {c["symbol"]: c["skipped"] for c in summary["per_company"]} == {"DEMO": None, "NONE": "no stored page"}
    assert json.loads(sv.to_json(summary))["companies"] == 2


def test_the_cli_takes_the_fifty_largest_by_default(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(cli, "make_sink", lambda settings: object(), raising=False)
    monkeypatch.setattr(cli, "_universe_companies", lambda s, scrips: [("1", "A"), ("2", "B")])
    monkeypatch.setattr(cli, "_largest_by_mcap", lambda s, companies, n: seen.setdefault("n", n) and companies)
    monkeypatch.setattr(sv, "run", lambda sink, companies, workers, day: sv.summarise([], None))
    assert cli.main(["screener-rows", "--json", str(tmp_path / "s.json"), "--csv", str(tmp_path / "r.csv"),
                     "--md", str(tmp_path / "r.md")]) == 0
    assert seen["n"] == 50 and (tmp_path / "r.csv").read_text(encoding="utf-8").startswith("company,basis,period")


def test_workflow_runs_screener_rows_read_only_and_always_uploads():
    import yaml

    text = (Path(__file__).parents[2] / ".github" / "workflows" / "maintenance.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(text)
    on = wf.get("on") or wf.get(True)
    assert "screener-rows" in on["workflow_dispatch"]["inputs"]["command"]["options"]
    assert '"screener-rows"' in text and "maint-ro-{0}" in text
    steps = [s for job in wf["jobs"].values() for s in job.get("steps", [])]
    run = next(s for s in steps if s.get("if") == "inputs.command == 'screener-rows'")
    assert 'screener-rows ${IDS:+--scrips "$IDS"} --top-mcap "${LIMIT:-50}"' in run["run"] and "--apply" not in run["run"]
    upload = next(s for s in steps if s.get("if") == "always() && inputs.command == 'screener-rows'")
    assert upload["with"]["name"] == "screener-rows"


# --- the review's findings (28 Oct 2026) -----------------------------------------------------------------------------------

def test_a_text_counts_once_even_on_two_members_as_the_older_files_tag_the_year_to_date():
    """Reliance Q2FY24: "Excise duty recovered" on the quarter and again on the year to date, both with the quarter's dates and
    each its own member; counted once (run 40725169900 took it twice in 24 quarters)."""
    extra = [("DescriptionOtherNoncurrentFinancialLiabilitiesOthers", "D2026_M3", "Lease liabilities"),
             ("OtherNoncurrentFinancialLiabilitiesOthers", "I2026_M3", 4.0)]
    facts = xf.Facts(doc([r for r in ANNUAL if r[1] not in ("D2026_M3", "I2026_M3")] + extra))
    got = facts.described(("OtherNoncurrentFinancialLiabilitiesOthers",), "lease", instant=END, joined=True)
    assert [v for _, _, v in got] == [30.0]


def test_a_balance_sheet_with_no_debt_line_has_borrowings_of_zero():
    facts = xf.Facts(doc([r for r in ANNUAL if not r[0].startswith(("Borrowings", "OtherCurrentFinancial", "OtherNoncurrentFinancial",
                                                                      "DescriptionOfOtherCurrentFinancial",
                                                                      "DescriptionOtherNoncurrentFinancial"))]))
    row = sv.corporate_bs(sv._Reader(facts, instant=END))["Borrowings"]
    assert row.value == 0.0 and "no borrowings" in row.note


def test_one_company_failing_is_that_company_skipped_not_the_run_lost():
    class Broken:
        def list_objects(self, prefix):
            raise RuntimeError("listing failed")

        def get_object(self, key):
            return None

    from bse_intel import screener_download as sd

    sink = Sink({f"{sd.PREFIX}2026-10-27/DEMO_c.html.gz": __import__("gzip").compress(PAGE.encode())})
    sink.list_objects_ok = sink.list_objects
    sink.list_objects = lambda prefix: Broken().list_objects(prefix) if prefix.startswith(xf.PREFIX) else sink.list_objects_ok(prefix)
    summary = sv.run(sink, [("1", "DEMO")], workers=1)
    assert summary["per_company"][0]["skipped"].startswith("error: RuntimeError")


def test_the_newest_results_file_decides_the_family_by_quarter_order_not_text():
    assert sorted(["Q4FY26", "Q1FY27"], key=lambda p: sv.quarter_index(p), reverse=True)[0] == "Q1FY27"


def test_a_file_without_a_balance_sheet_has_no_cwip_or_investments_not_zero():
    facts = xf.Facts(doc([("RevenueFromOperations", "D2026", 5.0)]))
    got = sv.corporate_bs(sv._Reader(facts, instant=END))
    assert got["CWIP"].value is None and got["Investments"].value is None and got["Borrowings"].value is None
    assert "no balance sheet" in got["CWIP"].note


def test_grasims_nbfc_finance_cost_row_moves_to_interest_like_lts():
    """Grasim Q1FY26 "Finance Cost relating to NBFC/HFC's Business" 2,734.5 Cr: screener's Interest 816.2 + 2,734.5 = 3,550.71,
    Expenses 31,295.82 (owner's Excel, measured 28 Oct 2026)."""
    facts = xf.Facts(doc(ANNUAL + [("DescriptionOfOtherExpenses", "D2026_M1", "Finance Cost relating to NBFC/HFC's Business"),
                                   ("OtherExpenses", "D2026_M1", 25.0)], kind="results", template="INDAS"))
    rows = sv.corporate_pl(sv._Reader(facts, end=END, months=12))
    assert rows["Interest"].value == pytest.approx(45.0) and rows["Expenses"].value == pytest.approx(560.0)


def test_a_loss_on_investments_row_of_other_expenses_moves_to_other_income():
    """M&M Q4FY26 "Loss from investments related to subsidiaries, associates and joint ventures" 410.2 Cr = its Expenses gap."""
    facts = xf.Facts(doc(ANNUAL + [("DescriptionOfOtherExpenses", "D2026_M2",
                                    "Loss from investments related to subsidiaries, associates and joint ventures"),
                                   ("OtherExpenses", "D2026_M2", 11.0)], kind="results", template="INDAS"))
    rows = sv.corporate_pl(sv._Reader(facts, end=END, months=12))
    assert rows["Expenses"].value == pytest.approx(585.0 - 11.0) and rows["Other Income"].value == pytest.approx(15.0 - 11.0)
    assert "loss on investments" in rows["Expenses"].note
