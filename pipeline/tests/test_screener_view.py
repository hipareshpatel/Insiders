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
        for member in ("M1", "M2", "M3", "M4", "M5", "M6", "M8", "M9"):
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


def test_discounting_charges_leave_sales_and_expenses():
    got = values(sv.corporate_pl(sv._Reader(annual_facts([("DiscountingCharges", "D2026", 7.0)]), end=END, months=12)))
    assert got["Sales"] == 893.0 and got["Expenses"] == 578.0 and got["Operating Profit"] == 315.0


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


def test_a_standalone_year_end_total_is_the_filed_assets_with_no_deferred_tax_offset():
    got = values(sv.corporate_bs(sv._Reader(annual_facts(), instant=END), standalone=True))
    assert got["Total Assets"] == got["Total Liabilities"] == 1000.0         # no min(DTA 8, DTL 3) on a standalone sheet


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
    # PBT as filed: adding back a negative exceptional item fitted HDFC Bank alone and broke 15 rows at 8 banks; none to other income
    assert q["Profit before tax"].value == pytest.approx(27825.48, abs=0.01)
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


def test_quarters_before_fy26_are_listed_but_never_counted():
    page = sv.parse_page(section("quarters", {"Sales&nbsp;+": [100, 90]}, ["Jun 2025", "Mar 2025"]))
    rows = {r["period"]: r for r in sv.compare(page, _store({}), "1", "DEMO")}
    assert rows["Q4FY25"]["status"] == "before_cutoff" and rows["Q1FY26"]["status"] == "no_facts"   # owner: quarters from FY26
    summary = sv.summarise([{"scrip": "1", "symbol": "DEMO", "rows": list(rows.values()), "skipped": None}], "2026-10-29")
    assert summary["by_status"]["before_cutoff"] == 1 and summary["by_row"]["quarters: Sales"]["exact_share"] is None


def test_a_quarter_before_the_first_results_on_either_exchange_is_before_listing():
    page = sv.parse_page(section("quarters", {"Sales&nbsp;+": [100, 90, 80]}, ["Mar 2026", "Dec 2025", "Jun 2025"]))
    q4 = doc([("RevenueFromOperations", "D2026", 1.0)], kind="results", template="INDAS", year=2026)
    def statuses(bse):
        cf = _store({xf.key("1", "Q4FY26", "CONSOLIDATED"): q4})
        cf.bse_periods = bse
        return {r["period"]: r["status"] for r in sv.compare(page, cf, "1", "NEWCO")}
    assert statuses({"Q4FY26"})["Q1FY26"] == "before_listing"               # listed in 2026: screener's quarter is from the prospectus
    assert statuses({"Q4FY26"})["Q3FY26"] == "before_listing"
    assert statuses(None)["Q1FY26"] == "no_facts"                             # BSE not asked yet: it may have the quarter
    assert statuses({"Q4FY26", "Q1FY26"})["Q1FY26"] == "no_facts"           # on BSE's list: a gap to fill, not a pre-listing quarter
    assert statuses({"Q4FY26", "Q4FY24"})["Q1FY26"] == "no_facts"           # BSE has older results: listed long ago, a real gap
    assert statuses(set())["Q1FY26"] == "no_facts"                            # an empty BSE answer decides nothing
    years = sv.parse_page(section("profit-loss", {"Sales&nbsp;+": [9, 8]}, ["Mar 2025", "Mar 2022"]))
    cf = _store({xf.key("1", "Q4FY26", "CONSOLIDATED"): q4})
    cf.bse_periods = {"Q4FY26"}
    got = {r["period"]: r["status"] for r in sv.compare(years, cf, "1", "NEWCO")}
    assert got["FY25"] == "before_listing" and got["FY22"] == "no_facts"    # older than LISTING_FROM: never called pre-listing


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
    assert seen["n"] == 50 and (tmp_path / "r.csv").read_text(encoding="utf-8").startswith("company,sector,industry,basis,period")


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


def test_a_bank_debt_row_of_other_financial_liabilities_is_in_borrowings():
    """Titan standalone "Secured and Unsecured Payable to Banks" 7,043 Cr FY25 / 14,314 Cr FY26 = screener's Borrowings gap."""
    extra = [("DescriptionOfOtherCurrentFinancialLiabilitiesOthers", "D2026_M3", "Secured and Unsecured Payable to Banks"),
             ("OtherCurrentFinancialLiabilitiesOthers", "I2026_M3", 9.0)]
    facts = xf.Facts(doc([r for r in ANNUAL if r[1] not in ("D2026_M3", "I2026_M3")] + extra))
    got = values(sv.corporate_bs(sv._Reader(facts, instant=END)))
    assert got["Borrowings"] == 100 + 50 + 30 + 12 + 9


def test_the_report_groups_rows_by_sector_so_a_sector_practice_shows():
    rows = [{"company": c, "basis": "CONSOLIDATED", "period": "FY26", "table": "annual", "row": "Profit before tax", "screener": 1,
             "ours": 1, "diff": 0, "status": st, "note": ""} for c, st in (("A", "apart"), ("B", "apart"), ("C", "ok"))]
    results = [{"scrip": c, "symbol": c, "skipped": None, "sector": sec, "rows": [r for r in rows if r["company"] == c]}
               for c, sec in (("A", "power"), ("B", "power"), ("C", "it"))]
    summary = sv.summarise(results)
    assert summary["by_sector_row"]["power"]["annual: Profit before tax"] == [0, 2]
    assert summary["by_sector_row"]["it"]["annual: Profit before tax"] == [1, 0]
    md = sv.to_markdown(summary, "2026-10-28")
    assert "| power | 2 | 0% | annual: Profit before tax 2/2 |" in md and "company,sector" in sv.to_csv(summary)


def test_sector_and_industry_come_from_the_companies_table_as_the_site_shows_them():
    class S:
        def company(self, scrip):
            return {"sector": "Chemicals", "industry": "Dyes And Pigments"} if scrip == "1" else None

        def get_dossier(self, scrip):
            return {"sector": "power"} if scrip == "2" else None

    assert sv._sector(S(), "1") == ("Chemicals", "Dyes And Pigments")
    assert sv._sector(S(), "2") == ("power", "") and sv._sector(S(), "3") == ("unknown", "")


def test_a_suppliers_credit_row_is_borrowings_but_a_sale_and_lease_back_payable_is_not():
    """Hindalco FY25 "Supplier's credit" 1,713 Cr is in screener's Borrowings; JSW Steel's "Payable for sale and lease back of an
    under construction asset" 1,286 Cr is not (both exact after, 28 Oct 2026)."""
    extra = [("DescriptionOfOtherCurrentFinancialLiabilitiesOthers", "D2026_M3", "Supplier's credit"),
             ("OtherCurrentFinancialLiabilitiesOthers", "I2026_M3", 5.0),
             ("DescriptionOfOtherNoncurrentAssetsOthers", "D2026_M4", "Right-of-use assets")]
    facts = xf.Facts(doc([r for r in ANNUAL if r[1] not in ("D2026_M3", "I2026_M3")] + extra[:2]))
    assert values(sv.corporate_bs(sv._Reader(facts, instant=END)))["Borrowings"] == 100 + 50 + 30 + 12 + 5
    sale = [("DescriptionOfOtherCurrentFinancialLiabilitiesOthers", "D2026_M3", "Payable for sale and lease back of an under construction asset"),
            ("OtherCurrentFinancialLiabilitiesOthers", "I2026_M3", 5.0)]
    facts = xf.Facts(doc([r for r in ANNUAL if r[1] not in ("D2026_M3", "I2026_M3")] + sale))
    assert values(sv.corporate_bs(sv._Reader(facts, instant=END)))["Borrowings"] == 100 + 50 + 30 + 12


def test_a_misspelt_lease_liabilities_row_is_still_borrowings():
    """Hindustan Unilever FY24-FY26 "Lease Liablities" 365-404 Cr and Coal India FY26 "Lease Liabiiities" 3.30 Cr are in screener's
    Borrowings (exact before the pattern was narrowed to the whole word, 28 Oct 2026)."""
    for words in ("Lease Liablities", "Lease Liabiiities"):
        row = [("DescriptionOfOtherCurrentFinancialLiabilitiesOthers", "D2026_M3", words),
               ("OtherCurrentFinancialLiabilitiesOthers", "I2026_M3", 5.0)]
        facts = xf.Facts(doc([r for r in ANNUAL if r[1] not in ("D2026_M3", "I2026_M3")] + row))
        assert values(sv.corporate_bs(sv._Reader(facts, instant=END)))["Borrowings"] == 100 + 50 + 30 + 12 + 5


def test_a_row_apart_names_the_filed_fact_equal_to_its_gap():
    """A lead for the larger batch: L&T's yearly Interest is apart by its bank charges, a breakdown row of other expenses."""
    facts = xf.Facts(doc([r for r in ANNUAL if r[1] not in ("D2026_M3", "I2026_M3")]
                         + [("DescriptionOfOtherCurrentFinancialLiabilitiesOthers", "D2026_M3", "Bank charges"),
                            ("OtherCurrentFinancialLiabilitiesOthers", "I2026_M3", 7.0)]))
    r = sv._Reader(facts, instant=END)
    assert any("[Bank charges] 7.00" in h for h in sv.gap_hints(r, -7.3))
    assert sv.gap_hints(r, 1.5) == []          # too small a gap to be a lead
    summary = sv.summarise([{"symbol": s, "scrip": "", "skipped": "", "rows": [
        {"company": s, "basis": "CONSOLIDATED", "period": "FY26", "table": "annual", "row": "Interest", "screener": 10.0, "ours": 3.0,
         "diff": -7.0, "status": "apart", "note": "", "hints": "OtherExpensesOthers [Bank charges] 7.00"}]} for s in ("A", "B")])
    assert summary["gap_hints"] == [["annual: Interest", "bank charges", ["A", "B"]]]
    assert "| annual: Interest | bank charges | 2: A, B |" in sv.to_markdown(summary, "2026-10-28")


def test_bank_charges_are_interest_not_expenses():
    """HAL, IndiGo and IOC FY24-FY26, both bases: the yearly Interest gap = the annual report's BankCharges."""
    got = values(sv.corporate_pl(sv._Reader(annual_facts([("BankCharges", "D2026", 4.0)]), end=END, months=12)))
    assert got["Interest"] == 24.0 and got["Expenses"] == 750 - 20 - 40 - 100 - 5 - 4
    assert got["Other Income"] == 30 - 10 - 5                     # the identity: Other Income does not move


def test_discontinued_operations_profit_is_in_pbt():
    """Hindustan Unilever FY26 13,812 + 4,407 = 18,219 (the ice-cream demerger): screener has no discontinued line."""
    got = values(sv.corporate_pl(sv._Reader(annual_facts([(sv.DISCONTINUED, "D2026", 15.0)]), end=END, months=12)))
    assert got["Profit before tax"] == 285.0 and got["PBT as filed"] == 270.0
    assert got["Other Income"] == 30 - 10 - 5 + 15


def test_a_half_year_balance_sheet_puts_intangibles_under_development_in_fixed_assets():
    """HCL Tech, UltraTech, JSW Steel, Hindustan Zinc, Adani Green Q2FY27; a year's column keeps them in CWIP (Reliance FY26)."""
    year = values(sv.corporate_bs(sv._Reader(annual_facts(), instant=END)))
    half = values(sv.corporate_bs(sv._Reader(annual_facts(), instant=END), half_year=True))
    assert (year["CWIP"], half["CWIP"]) == (20.0, 15.0)
    assert half["Fixed Assets"] == year["Fixed Assets"] + 5
    assert (year["Total Assets"], half["Total Assets"]) == (997.0, 1000.0)   # the half year: no min(DTA, DTL) offset


def test_a_banks_net_profit_holds_the_minority_share():
    """HDFC Bank Q3FY24-Q1FY27, ICICI Q3FY24-Q2FY26: the consolidated quarter's gap = ProfitLossOfMinorityInterest."""
    net = "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates"
    facts = xf.Facts(doc([("InterestEarned", "Q2026", 100.0), (net, "Q2026", 30.0), ("ProfitLossOfMinorityInterest", "Q2026", 2.0)],
                         kind="results", template="BANKING"))
    got = values(sv.bank_pl(sv._Reader(facts, end=END, months=3)))
    assert got["Net Profit"] == 32.0 and got["Net Profit (owners)"] == 30.0


def test_a_loss_from_associates_is_an_expense_and_a_profit_is_other_income():
    """43 of 43 quarters with Expenses and Other Income both apart by the share (PBT exact) had a loss (Bajaj Auto Q2FY25, KTM)."""
    base = values(sv.corporate_pl(sv._Reader(annual_facts(), end=END, months=12)))
    loss = values(sv.corporate_pl(sv._Reader(annual_facts([(sv.ASSOCIATES, "D2026", -8.0)]), end=END, months=12)))
    gain = values(sv.corporate_pl(sv._Reader(annual_facts([(sv.ASSOCIATES, "D2026", 8.0)]), end=END, months=12)))
    assert loss["Expenses"] == base["Expenses"] + 8 and loss["Other Income"] == base["Other Income"]
    assert loss["Profit before tax"] == base["Profit before tax"] - 8
    assert gain["Expenses"] == base["Expenses"] and gain["Other Income"] == base["Other Income"] + 8


def test_current_maturities_of_finance_lease_obligations_are_borrowings_once():
    """58 rows of 23 companies (the 500 largest): screener's Borrowings above ours by exactly this element."""
    base = values(sv.corporate_bs(sv._Reader(annual_facts(), instant=END)))["Borrowings"]
    got = values(sv.corporate_bs(sv._Reader(annual_facts([(sv.FINANCE_LEASE_MATURITIES, "I2026", 6.0)]), instant=END)))
    assert got["Borrowings"] == base + 6
    # the same line also described in the breakdown is not counted twice
    facts = xf.Facts(doc([r for r in ANNUAL if r[1] not in ("D2026_M3", "I2026_M3")]
                         + [("DescriptionOfOtherCurrentFinancialLiabilitiesOthers", "D2026_M3", "Current maturities of finance lease obligations"),
                            ("OtherCurrentFinancialLiabilitiesOthers", "I2026_M3", 6.0), (sv.FINANCE_LEASE_MATURITIES, "I2026", 6.0)]))
    assert values(sv.corporate_bs(sv._Reader(facts, instant=END)))["Borrowings"] == 100 + 50 + 30 + 12 + 6


def test_current_maturities_of_long_term_debt_are_borrowings_once(monkeypatch):
    """L&T Q4FY21-FY26, Hyundai, KPR Mill, Dr Reddy's: screener's Borrowings above ours by exactly this element (129 rows).
    Behind SCREENER_CMLTD, off until measured on/off."""
    monkeypatch.setenv("SCREENER_CMLTD", "1")
    base = values(sv.corporate_bs(sv._Reader(annual_facts(), instant=END)))["Borrowings"]
    got = values(sv.corporate_bs(sv._Reader(annual_facts([(sv.LT_DEBT_MATURITIES, "I2026", 9.0)]), instant=END)))
    assert got["Borrowings"] == base + 9
    assert got["Other Liabilities"] == values(sv.corporate_bs(sv._Reader(annual_facts(), instant=END)))["Other Liabilities"] - 9
    # the same line also described in the breakdown is not counted twice
    facts = xf.Facts(doc([r for r in ANNUAL if r[1] not in ("D2026_M3", "I2026_M3")]
                         + [("DescriptionOfOtherCurrentFinancialLiabilitiesOthers", "D2026_M3", "Current maturities of long term debt"),
                            ("OtherCurrentFinancialLiabilitiesOthers", "I2026_M3", 9.0), (sv.LT_DEBT_MATURITIES, "I2026", 9.0)]))
    assert values(sv.corporate_bs(sv._Reader(facts, instant=END)))["Borrowings"] == 100 + 50 + 30 + 12 + 9
    monkeypatch.delenv("SCREENER_CMLTD")            # off by default: today's rule
    assert values(sv.corporate_bs(sv._Reader(annual_facts([(sv.LT_DEBT_MATURITIES, "I2026", 9.0)]), instant=END)))["Borrowings"] == base


def test_tax_percent_is_on_the_size_of_the_pbt():
    """L&T standalone Q2FY26: PBT -2,982 with a tax charge, screener +20.0 (289 quarters of the 500 largest)."""
    assert round(sv._tax_pct(596.4, -2982.0), 1) == 20.0 and sv._tax_pct(1.0, 0.0) is None


def test_an_nbfcs_pbt_holds_the_associates_share():
    """Bajaj Holdings Q2FY24 1,464.08, Jio Financial Q3FY24 66.11: screener's PBT includes the share."""
    facts = xf.Facts(doc([("ProfitBeforeTax", "Q2026", 100.0), ("TaxExpense", "Q2026", 20.0), (sv.ASSOCIATES, "Q2026", 50.0)],
                         kind="results", template="NBFC"))
    got = values(sv.nbfc_pl(sv._Reader(facts, end=END, months=3)))
    assert got["Profit before tax"] == 150.0 and got["PBT as filed"] == 100.0 and round(got["Tax %"], 2) == round(2000 / 150, 2)


def test_lease_rows_under_non_financial_liabilities_and_misspelt_count_once():
    """Ambuja FY25 "CURRENT LEASE LIABILITY" under other current liabilities; Persistent "CurrentbLease Liability";
    MTAR "lease libaility"; a sale-and-lease-back payable is still not debt."""
    for parent, words, counted in (("DescriptionOfOtherCurrentLiabilitiesOthers", "CURRENT LEASE LIABILITY", True),
                                   ("DescriptionOfOtherCurrentFinancialLiabilitiesOthers", "CurrentbLease Liability", True),
                                   ("DescriptionOfOtherCurrentFinancialLiabilitiesOthers", "lease libaility", True),
                                   ("DescriptionOfOtherCurrentFinancialLiabilitiesOthers", "Payable for sale and lease back", False)):
        amount = parent.replace("DescriptionOf", "")
        row = [(parent, "D2026_M3", words), (amount, "I2026_M3", 5.0)]
        if "FinancialLiabilities" not in parent:      # the same line on the parent too: counted once
            row += [("DescriptionOfOtherCurrentLiabilities", "D2026_M4", words), ("OtherCurrentLiabilities", "I2026_M4", 5.0)]
        facts = xf.Facts(doc([r for r in ANNUAL if r[1] not in ("D2026_M3", "I2026_M3", "D2026_M4", "I2026_M4")] + row))
        assert values(sv.corporate_bs(sv._Reader(facts, instant=END)))["Borrowings"] == 100 + 50 + 30 + 12 + (5 if counted else 0), words


def test_a_net_regulatory_expense_is_an_expense_and_a_net_regulatory_income_other_income():
    """NHPC Q4FY26 -559.22 = screener's Expenses gap; a positive movement stays in Other Income (the owner's NHPC sheet)."""
    base = values(sv.corporate_pl(sv._Reader(annual_facts(), end=END, months=12)))
    neg = values(sv.corporate_pl(sv._Reader(annual_facts([(sv.REGULATORY_DEFERRAL, "D2026", -6.0)]), end=END, months=12)))
    pos = values(sv.corporate_pl(sv._Reader(annual_facts([(sv.REGULATORY_DEFERRAL, "D2026", 6.0)]), end=END, months=12)))
    assert neg["Expenses"] == base["Expenses"] + 6 and neg["Other Income"] == base["Other Income"]
    assert pos["Expenses"] == base["Expenses"] and pos["Other Income"] == base["Other Income"] + 6
    assert neg["Profit before tax"] == base["Profit before tax"] - 6


def test_an_impairment_of_investments_stays_in_expenses():
    """Tech Mahindra standalone Q4FY24-Q4FY26: screener keeps "Impairment of investments" in Expenses; a loss moves out."""
    assert not __import__("re").search(sv.INVESTMENT_LOSS, "Impairment of investments", __import__("re").I)
    assert __import__("re").search(sv.INVESTMENT_LOSS, "Loss from investments related to subsidiaries", __import__("re").I)
    # a fair-value change stays in Expenses: measured 29 Oct (run 40874998205), 5 pairs fixed at one company, 10 broken at five
    assert not __import__("re").search(sv.INVESTMENT_LOSS, "Fair value loss on equity investments measured at FVTPL", __import__("re").I)


def test_a_filler_zero_owners_share_is_the_whole_profit():
    """Paradeep Q2FY26-Q1FY27 files 0 for the owners' share and 0 for the minority."""
    facts = annual_facts([("ProfitOrLossAttributableToOwnersOfParent", "D2026", 0.0), ("ProfitOrLossAttributableToNonControllingInterests", "D2026", 0.0)])
    got = values(sv.corporate_pl(sv._Reader(xf.Facts(doc([r for r in ANNUAL if r[0] not in (
        "ProfitOrLossAttributableToOwnersOfParent", "ProfitOrLossAttributableToNonControllingInterests")]
        + [("ProfitOrLossAttributableToOwnersOfParent", "D2026", 0.0), ("ProfitOrLossAttributableToNonControllingInterests", "D2026", 0.0)])),
        end=END, months=12)))
    assert got["Net Profit (owners)"] == 200.0


def test_an_nbfc_has_every_row_of_a_lenders_and_a_holding_companys_page():
    """Screener's identities on 116 NBFCs: Operating Profit = Sales - Expenses, Financing Profit = Revenue - Expenses - Interest."""
    facts = xf.Facts(doc([("RevenueFromOperations", "Q2026", 100.0), ("Expenses", "Q2026", 70.0), ("FinanceCosts", "Q2026", 40.0),
                          ("DepreciationDepletionAndAmortisationExpense", "Q2026", 5.0), ("ProfitBeforeTax", "Q2026", 35.0),
                          ("TaxExpense", "Q2026", 9.0)], kind="results", template="NBFC"))
    got = values(sv.nbfc_pl(sv._Reader(facts, end=END, months=3)))
    assert got["Expenses"] == 25.0 and got["Operating Profit"] == 75.0 and got["Financing Profit"] == 35.0
    assert got["Sales"] == got["Revenue"] == 100.0 and got["Other Income"] == 35 + 5 + 40 - 75


def test_a_row_apart_by_two_filed_lines_names_the_pair_and_exceptional_losses_are_summed():
    extra = [("DescriptionOfOtherExpenses", "D2026_M8", "Freight outward"), ("OtherExpenses", "D2026_M8", 13.0),
             ("DescriptionOfOtherExpenses", "D2026_M9", "Commission to selling agents"), ("OtherExpenses", "D2026_M9", 29.0),
             ("DescriptionOfExceptionalItems", "D2026_M5", "Gain on remeasurement"), ("ExceptionalItems", "D2026_M5", 300.0),
             ("DescriptionOfExceptionalItems", "D2026_M6", "Impairment of goodwill"), ("ExceptionalItems", "D2026_M6", -211.0)]
    r = sv._Reader(annual_facts(extra), end=END, months=12)
    assert any("[Freight outward] + OtherExpenses [Commission to selling agents]" in p or
               "[Commission to selling agents] + OtherExpenses [Freight outward]" in p for p in sv.gap_pairs(r, 42.2))
    assert any(p.startswith("exceptional losses") for p in sv.gap_pairs(r, 211.4))
    assert sv.gap_pairs(r, 1.5) == []


def test_screener_expense_sub_rows_name_the_part_apart_and_the_lines_inside_it():
    assert sv.column_of("annual", "FY26") == "Mar 2026" and sv.column_of("quarters", "Q1FY27") == "Jun 2026"
    assert sv.column_of("quarters", "Q4FY26") == "Mar 2026" and sv.column_of("annual", "YE:Dec2025") is None
    extra = [("CostOfMaterialsConsumed", "D2026", 300.0), ("EmployeeBenefitExpense", "D2026", 100.0),
             ("DescriptionOfOtherExpenses", "D2026_M8", "Freight outward"), ("OtherExpenses", "D2026_M8", 13.0),
             ("DescriptionOfOtherExpenses", "D2026_M9", "Commission to selling agents"), ("OtherExpenses", "D2026_M9", 29.0)]
    r = sv._Reader(annual_facts(extra), end=END, months=12)
    # screener: Sales 1,000; material 30 %, employee 10 %, manufacturing 10 %, other 14.2 %: its rest is 242, ours 200
    answer = {"Material Cost %": {"Mar 2026": "30.00%"}, "Employee Cost %": {"Mar 2026": "10.00%"},
              "Manufacturing Cost %": {"Mar 2026": "10.00%"}, "Other Cost %": {"Mar 2026": "14.20%"}}
    where, found = sv.part_gaps(r, 600.0, answer, "Mar 2026", 1000.0, 42.0)
    assert where == "rest +42"
    assert "Freight outward" in found and "Commission to selling agents" in found


def test_expense_parts_take_the_rest_from_screeners_total_and_round_by_the_places_shown():
    # the quarters' sub-rows: material and employee only; whole percents round to half a percent of Sales
    got, slack = sv.expense_parts({"Material Cost %": {"Mar 2026": "72%"}, "Employee Cost %": {"Mar 2026": "4.90%"}},
                                  "Mar 2026", 1000.0, 870.0)
    assert got == pytest.approx({"material": 720.0, "employee": 49.0, "rest": 101.0})
    assert slack["material"] == pytest.approx(5.0) and slack["employee"] == pytest.approx(0.05)
