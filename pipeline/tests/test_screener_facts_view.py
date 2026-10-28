"""The complete screener view of the cross-check (28 Oct 2026): memory's figures set against screener's treatment with the parts
the stored XBRL facts show (levies and discounts in Sales, EPS on total shares and on total or continuing profit, lease
liabilities, current maturities, intangibles and right-of-use assets, CWIP's intangibles, netted deferred tax) and the cash
flow of a year end other than March. A part is used only when the facts show it; a gap no part closes is never a definition
(independent review, 28 Oct 2026); a missing section is loud; the top-mcap pick."""

from __future__ import annotations

import csv
import io
import json
from datetime import date

import pytest

from bse_intel import cli, xbrl_facts
from bse_intel import screener_crosscheck as sc
from bse_intel import screener_download as sd
from bse_intel.screener_fill import parse_full

CR = 10_000_000


# --- a small facts document, built by hand ------------------------------------------------------------------------

CONTEXTS = {
    "Q": {"s": "2026-01-01", "e": "2026-03-31", "m": 3, "l": "Q4FY26"},
    "Y": {"s": "2025-04-01", "e": "2026-03-31", "m": 12, "l": "FY26"},
    "I": {"i": "2026-03-31"},
    "I2": {"i": "2026-09-30"},
    "R1": {"s": "2026-01-01", "e": "2026-03-31", "m": 3, "d": {"in-bse-fin:DetailsOfOtherExpensesAxis": "Row1Member"}},
    "R2": {"s": "2026-01-01", "e": "2026-03-31", "m": 3, "d": {"in-bse-fin:DetailsOfOtherExpensesAxis": "Row2Member"}},
    "L1": {"i": "2026-03-31", "d": {"in-bse-fin:DetailsOfOtherCurrentFinancialLiabilitiesAxis": "Row1Member"}},
}
UNITS = {"INR": "MONEY", "INRPerShare": "PER_SHARE", "shares": "SHARES"}


def rows(*facts):
    return [list(f) if len(f) == 5 else [*f, None, None][:5] for f in facts]


def money(name, ctx, crore):
    return [name, ctx, "INR", crore * CR, -5]


def text(name, ctx, value):
    return [name, ctx, None, value, None]


def facts_doc(*facts, contexts=None):
    return {"v": 1, "basis": "CONSOLIDATED", "contexts": contexts or CONTEXTS, "units": UNITS, "facts": [list(f) for f in facts]}


def one_arg(facts):
    """The loader as compare_company hands it on: the period alone (the basis is bound there)."""
    return lambda period: facts(period, "CONSOLIDATED")


def loader(by_period):
    """facts(period, basis) -> Facts or None, as screener_crosscheck.run builds it from the sink."""
    calls = []

    def facts(period, basis):
        calls.append(period)
        doc = by_period.get(period)
        return xbrl_facts.Facts(doc) if doc else None

    facts.calls = calls
    return facts


# --- a company page and a memory ----------------------------------------------------------------------------------

def section(section_id, table, columns, basis="Consolidated"):
    head = "".join(f"<th>{c}</th>" for c in columns)
    body = "".join(f"<tr><td>{label}</td>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>" for label, vals in table.items())
    return (f'<section id="{section_id}"><p>{basis} Figures in Rs. Crores</p><table><thead><tr><th></th>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></section>")


def page_html(sales=182, eps=10.0, columns=("Mar 2026",), eps_row=True, bs=None, bs_columns=("Mar 2025", "Mar 2026", "Sep 2026"),
              cf=None, cf_columns=("Mar 2025", "Mar 2026"), basis="Consolidated"):
    quarter = {"Sales&nbsp;+": [sales] * len(columns), "Net Profit&nbsp;+": [100] * len(columns)}
    if eps_row:
        quarter["EPS in Rs"] = [eps] * len(columns)
    html = section("quarters", quarter, list(columns), basis)
    if bs:
        html += section("balance-sheet", bs, list(bs_columns), basis)
    if cf:
        html += section("cash-flow", cf, list(cf_columns), basis)
    return html


def entry(metric, period, value):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR" if metric != "eps" else "INR",
            "basis": "CONSOLIDATED", "as_of": "2026-11-01", "source_news_id": f"xbrl:res:1:{period}"}


def memory(revenue=200.0, eps=10.0, pat_owners=100.0, extra=(), snaps=(), fy_end=None):
    metrics = [entry("revenue", "Q4FY26", revenue), entry("pat", "Q4FY26", 100.0), entry("eps", "Q4FY26", eps)]
    metrics += [entry("pat_owners", "Q4FY26", pat_owners)]
    metrics += [entry(*e) for e in extra]
    # a statement takes its basis from the results file it came with: that file's figures carry the basis
    metrics += [entry("pat", s["period"], 1.0) for s in snaps if s["period"] != "Q4FY26"]
    d = {"financial_metrics": metrics, "balance_sheet": [dict(s) for s in snaps], "sector": "Demo"}
    if fy_end:
        d["fy_end_month"] = fy_end
    return d


def snap(period, **fields):
    return {"period": period, "as_of": "2026-11-01", "source_news_id": f"xbrl:res:1:{period}", **fields}


def compare(d, html, facts=None):
    return sc.compare_company(d, {"CONSOLIDATED": parse_full(html)}, "1", "DEMO", facts)


def pair(result, metric, period="Q4FY26"):
    return next(p for p in result["pairs"] if p["metric"] == metric and p["period"] == period)


# --- Sales: excise, sales tax / VAT, discounts ------------------------------------------------------------------------

def excise_and_vat_facts():
    # the excise duty is a row of Other expenses (a described breakdown line), the VAT an element of its own
    return {"Q4FY26": facts_doc(text("DescriptionOfOtherExpenses", "R1", "Excise duty"), money("OtherExpenses", "R1", 15.6),
                                text("DescriptionOfOtherExpenses", "R2", "Advertising"), money("OtherExpenses", "R2", 40.0),
                                money("ValueAddedTax", "Q", 5.0), money("RevenueFromOperations", "Q", 200.0))}


def test_sales_less_excise_and_vat_from_the_facts_where_memory_has_no_excise():
    d, html = memory(), page_html(sales=179)           # 200 - 15.6 - 5.0 = 179.4: screener prints 179
    plain = compare(d, html)
    assert pair(plain, "revenue")["class"] == "mismatch"                 # memory alone cannot say why
    got = compare(d, html, loader(excise_and_vat_facts()))
    p = pair(got, "revenue")
    assert p["class"] == "matches_screener_view:excise_taxes" and p["adjustment"] == "excise_taxes (xbrl facts)"
    assert "excise_duty 15.6" in p["note"] and "indirect_taxes 5" in p["note"] and "breakdown row" in p["note"]
    assert "matches_screener_view:excise_taxes" in sc.CLASSES
    # one part alone closes nothing here; the advertising row is not a levy
    only_vat = pair(compare(d, page_html(sales=195), loader(excise_and_vat_facts())), "revenue")
    assert only_vat["class"] == "matches_screener_view:taxes"
    nothing = pair(compare(d, page_html(sales=150), loader(excise_and_vat_facts())), "revenue")
    assert nothing["class"] == "mismatch" and nothing["adjustment"] == ""


def test_sales_less_discounts_and_a_tagged_excise_element():
    facts = {"Q4FY26": facts_doc(money("ExciseDuty", "Q", 10.0), money("TradeDiscounts", "Q", 8.0))}
    p = pair(compare(memory(), page_html(sales=182), loader(facts)), "revenue")
    assert p["class"] == "matches_screener_view:excise_discounts" and "element" in p["note"]


def test_memorys_own_excise_is_never_doubled_by_the_facts():
    d = memory(extra=[("excise_duty", "Q4FY26", 15.6)])
    facts = {"Q4FY26": facts_doc(money("ExciseDuty", "Q", 15.6))}
    extra = sc.facts_extra(one_arg(loader(facts)), sc._figures(d, "CONSOLIDATED")[0], "Q4FY26")
    assert ("excise_duty", "Q4FY26") not in extra                       # memory has it
    p = pair(compare(d, page_html(sales=184), loader(facts)), "revenue")   # 200 - 15.6 = 184.4
    assert p["class"] == "naming" and "revenue less excise_duty" in p["note"]


def test_a_year_is_read_from_its_march_file_and_the_facts_are_fetched_only_for_a_gap():
    facts = loader({"Q4FY26": facts_doc(money("ExciseDuty", "Y", 12.0), money("ExciseDuty", "Q", 99.0))})
    figures = sc._figures(memory(), "CONSOLIDATED")[0]
    got = sc.facts_extra(one_arg(facts), figures, "FY26")
    assert got[("excise_duty", "FY26")]["value"] == 12.0 and facts.calls == ["Q4FY26"]     # the 12-month context, the Q4 file
    # a pair that matches never reads a facts file
    never = loader({})
    compare(memory(revenue=182.0), page_html(sales=182), never)
    assert never.calls == []


# --- EPS: total shares, total or continuing profit ----------------------------------------------------------------------

def test_eps_on_total_shares_where_a_treasury_share_count_is_tagged():
    # profit 100 Cr / EPS 10 = 10 crore shares; 50 lakh treasury shares make 10.5 crore: 100 / 10.5 = 9.52
    d, html = memory(eps=10.0, pat_owners=100.0), page_html(eps=9.52)
    facts = {"Q4FY26": facts_doc(["TreasurySharesHeld", "Q", "shares", 5_000_000, 0])}
    p = pair(compare(d, html, loader(facts)), "eps")
    assert p["class"] == "matches_screener_view:treasury_shares" and p["adjustment"] == "treasury_shares (xbrl facts)"
    assert pair(compare(d, html), "eps")["class"] == "mismatch"                    # no count, no adjustment
    assert pair(compare(d, html, loader({"Q4FY26": facts_doc(money("OtherIncome", "Q", 1.0))})), "eps")["class"] == "mismatch"
    # the arithmetic, apart from the page
    views = sc.screener_views({}, {("eps", "Q4FY26"): {"value": 10.0}, ("pat_owners", "Q4FY26"): {"value": 100.0},
                                    ("treasury_shares", "Q4FY26"): {"value": 5_000_000}}, "Q4FY26")
    assert views["eps"][0][1] == "treasury_shares" and views["eps"][0][0] == pytest.approx(100 / 10.5)


def test_eps_on_total_profit_or_on_continuing_profit_names_which_one_matches():
    eps_facts = {"Q4FY26": facts_doc(["BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", "Q", "INRPerShare", 13.01, "INF"],
                                     ["BasicEarningsLossPerShareFromContinuingOperations", "Q", "INRPerShare", 3.95, "INF"])}
    d = memory(eps=3.95)                       # memory's EPS is the file's first tag
    total = pair(compare(d, page_html(eps=13.01), loader(eps_facts)), "eps")
    assert total["class"] == "naming" and "our eps_total (on total profit)" in total["note"]
    assert total["adjustment"] == "eps_on_total_profit"
    # screener on the continuing profit while memory holds the total
    cont = pair(compare(memory(eps=13.01), page_html(eps=3.95), loader(eps_facts)), "eps")
    assert cont["class"] == "naming" and "our eps_continuing (on continuing profit)" in cont["note"]
    assert cont["adjustment"] == "eps_on_continuing_profit"
    # memory's own two variants (F188) are named too, with no facts
    held = memory(eps=3.95, extra=[("eps_total", "Q4FY26", 13.01), ("eps_continuing", "Q4FY26", 3.95)])
    assert "eps_total" in pair(compare(held, page_html(eps=13.01)), "eps")["note"]


# --- balance sheet --------------------------------------------------------------------------------------------------------

BS = {"Equity Capital": [100, 100, 110], "Reserves": [800, 900, 1000], "Borrowings&nbsp;+": [300, 330, 350],
      "Total Liabilities": [1400, 1580, 1750], "Fixed Assets&nbsp;+": [600, 700, 760], "CWIP": [50, 60, 70],
      "Investments": [250, 280, 300], "Total Assets": [1400, 1580, 1750]}
SNAPS = [snap("Q4FY25", equity_capital_cr=100.0, reserves_cr=800.0, gross_debt_cr=300.0, total_assets_cr=1400.0, fixed_assets_cr=600.0,
              cwip_cr=50.0, investments_cr=250.0, net_worth_cr=900.0),
         snap("Q4FY26", equity_capital_cr=100.0, reserves_cr=900.0, gross_debt_cr=330.0, total_assets_cr=1580.0, fixed_assets_cr=700.0,
              cwip_cr=60.0, investments_cr=280.0, net_worth_cr=1000.0),
         snap("Q2FY27", equity_capital_cr=110.0, reserves_cr=1000.0, gross_debt_cr=350.0, total_assets_cr=1750.0, fixed_assets_cr=760.0,
              cwip_cr=70.0, investments_cr=300.0, net_worth_cr=1110.0)]


def bs_compare(rows_changes, facts=None, lender=False, snaps=SNAPS):
    table = {k: list(v) for k, v in BS.items()}
    for label, vals in rows_changes.items():
        table[label] = vals
    d = memory(snaps=snaps)
    if lender:
        d["industry"] = "Financial Services > Banks"
    return compare(d, page_html(bs=table), facts)


def bs(result, line, period):
    return next(p for p in result["bs_pairs"] if p["metric"] == line and p["period"] == period)


def test_borrowings_plus_lease_liabilities_from_the_facts_closes_the_gap_and_is_named():
    facts = loader({"Q4FY26": facts_doc(money("LeaseLiabilitiesNoncurrent", "I", 40.0),
                                        text("DescriptionOfOtherCurrentFinancialLiabilities", "L1", "Lease liabilities - current"),
                                        money("OtherCurrentFinancialLiabilities", "L1", 10.0))})
    got = bs_compare({"Borrowings&nbsp;+": [300, 380, 350]}, facts)       # 330 + 40 + 10 = 380
    p = bs(got, "borrowings", "Q4FY26")
    assert p["class"] == "matches_screener_view:borrowings_plus_lease_liabilities"
    assert p["adjustment"] == "borrowings_plus_lease_liabilities (xbrl facts)" and p["table"] == "balance_sheet"


def test_a_part_that_does_not_close_the_gap_names_nothing_and_the_note_says_what_the_facts_held():
    facts = loader({"Q4FY26": facts_doc(money("LeaseLiabilitiesNoncurrent", "I", 5.0))})
    p = bs(bs_compare({"Borrowings&nbsp;+": [300, 380, 350]}, facts), "borrowings", "Q4FY26")
    assert p["class"] == "unexplained_larger"
    assert "XBRL facts stored: lease_liabilities found, they do not close the gap" in p["note"]
    none_tagged = loader({"Q4FY26": facts_doc(money("OtherIncome", "Q", 1.0))})
    q = bs(bs_compare({"Borrowings&nbsp;+": [300, 380, 350]}, none_tagged), "borrowings", "Q4FY26")
    assert q["class"] == "unexplained_larger" and "no lease_liabilities/current_maturities tagged" in q["note"]
    absent = bs(bs_compare({"Borrowings&nbsp;+": [300, 380, 350]}, loader({})), "borrowings", "Q4FY26")
    assert absent["class"] == "unexplained_larger" and "no XBRL facts stored for this date" in absent["note"]
    # screener's figure below ours is a plain mismatch whatever the facts hold
    assert bs(bs_compare({"Borrowings&nbsp;+": [300, 250, 350]}, facts), "borrowings", "Q4FY26")["class"] == "mismatch"


def test_current_maturities_count_at_a_year_end_but_never_in_a_half_year():
    facts = loader({"Q4FY26": facts_doc(money("CurrentMaturitiesOfLongtermBorrowings", "I", 20.0)),
                    "Q2FY27": facts_doc(money("CurrentMaturitiesOfLongtermBorrowings", "I2", 20.0))})
    snaps = [dict(s) for s in SNAPS]
    snaps[2]["gross_debt_cr"] = 360.0
    got = bs_compare({"Borrowings&nbsp;+": [300, 350, 380]}, facts, snaps=snaps)   # year end 330 + 20 = 350; Sep 360 + 20 = 380 (not added)
    year = bs(got, "borrowings", "Q4FY26")
    assert year["class"] == "matches_screener_view:borrowings_plus_current_maturities"
    half = bs(got, "borrowings", "Q2FY27")
    assert half["class"] == "unexplained_larger" and "current_maturities found, they do not close" in half["note"]
    # a December year end: Sep is a half year, Dec the year end
    assert sc._half_year("Q2FY27", 3) is True and sc._half_year("Q4FY26", 3) is False and sc._half_year("Q3FY26", 12) is False


def test_fixed_assets_plus_goodwill_intangibles_and_right_of_use_assets_cwip_apart():
    facts = loader({"Q4FY26": facts_doc(money("OtherIntangibleAssets", "I", 60.0), money("RightOfUseAssets", "I", 30.0),
                                        money("Goodwill", "I", 10.0), money("IntangibleAssetsUnderDevelopment", "I", 15.0))})
    got = bs_compare({"Fixed Assets&nbsp;+": [600, 790, 760], "CWIP": [50, 75, 70]}, facts)     # 700 + 60 + 30 = 790; 60 + 15 = 75
    assert bs(got, "fixed_assets", "Q4FY26")["class"] == "matches_screener_view:fixed_assets_plus_intangibles_right_of_use"
    assert bs(got, "cwip", "Q4FY26")["class"] == "matches_screener_view:cwip_plus_intangibles_under_development"
    with_goodwill = bs_compare({"Fixed Assets&nbsp;+": [600, 800, 760]}, facts)                  # 700 + 10 + 60 + 30
    assert bs(with_goodwill, "fixed_assets", "Q4FY26")["class"] == \
        "matches_screener_view:fixed_assets_plus_goodwill_intangibles_right_of_use"
    # no right-of-use line and no intangibles: not named
    bare = bs_compare({"Fixed Assets&nbsp;+": [600, 790, 760]}, loader({"Q4FY26": facts_doc(money("OtherIncome", "Q", 1.0))}))
    assert bs(bare, "fixed_assets", "Q4FY26")["class"] == "unexplained_larger"


def test_investments_parts_are_for_a_company_and_never_a_lender():
    facts = loader({"Q4FY26": facts_doc(money("InvestmentsAccountedForUsingEquityMethod", "I", 25.0))})
    got = bs_compare({"Investments": [250, 305, 300]}, facts)
    assert bs(got, "investments", "Q4FY26")["class"] == "matches_screener_view:investments_plus_equity_method"
    bank = bs_compare({"Investments": [250, 305, 300]}, facts, lender=True)
    assert bs(bank, "investments", "Q4FY26")["class"] == "mismatch"


def test_both_totals_lose_the_deferred_tax_screener_nets():
    facts = loader({"Q4FY26": facts_doc(money("DeferredTaxAssetsNet", "I", 20.0), money("DeferredTaxLiabilitiesNet", "I", 35.0))})
    got = bs_compare({"Total Assets": [1400, 1560, 1750], "Total Liabilities": [1400, 1560, 1750]}, facts)
    assert bs(got, "total_assets", "Q4FY26")["class"] == "matches_screener_view:deferred_tax_net"
    assert bs(got, "total_liabilities", "Q4FY26")["class"] == "matches_screener_view:deferred_tax_net"
    # one side only: nothing is offset
    one = loader({"Q4FY26": facts_doc(money("DeferredTaxLiabilitiesNet", "I", 35.0))})
    assert bs(bs_compare({"Total Assets": [1400, 1560, 1750]}, one), "total_assets", "Q4FY26")["class"] == "mismatch"


def test_the_facts_file_of_a_date_is_read_once_and_only_for_a_gap_a_part_could_close():
    facts = loader({"Q4FY26": facts_doc(money("LeaseLiabilitiesNoncurrent", "I", 50.0))})
    bs_compare({"Borrowings&nbsp;+": [300, 380, 350], "Fixed Assets&nbsp;+": [600, 790, 760]}, facts)
    assert facts.calls.count("Q4FY26") == 1 and "Q4FY25" not in facts.calls and "Q2FY27" not in facts.calls
    never = loader({})
    d = memory(revenue=182.0, snaps=SNAPS)
    compare(d, page_html(sales=182, bs=BS), never)                          # every line agrees: the facts are not asked for
    assert never.calls == []
    bs_compare({}, never)
    assert set(never.calls) <= {"Q4FY26"}                                      # only the revenue gap of the default page


# --- the plugs, the sections, the totals -------------------------------------------------------------------------------

def test_the_plugs_are_marked_informational_in_every_report():
    rows_ = {"Other Liabilities&nbsp;+": [200, 290, 290], "Other Assets&nbsp;+": [500, 540, 620]}
    result = bs_compare(rows_)
    plug = bs(result, "other_liabilities", "Q4FY26")
    assert plug["note"].startswith("informational (plug)")
    out = sc.summarise([result], "2026-10-28")
    assert "other_liabilities (plug: informational)" in sc.render(out) and "other_liabilities (plug: informational)" in sc.to_markdown(out, "2026-10-28")
    assert "borrowings (plug" not in sc.render(out)


def run_summary(html):
    d = memory(snaps=SNAPS)
    return sc.summarise([compare(d, html)], "2026-10-28")


def test_a_missing_section_is_loud_in_the_summary_the_text_and_the_markdown_also_at_zero():
    for html, bs_n, cf_n in ((page_html(), 0, 0), (page_html(bs=BS), 1, 0)):
        out = run_summary(html)
        sec = out["sections"]
        assert sec["pages_read"] == 1 and sec["pages_with_balance_sheet"] == bs_n and sec["pages_with_cash_flow"] == cf_n
        assert sec["compared_pages"] == 1 and sec["compared_with_balance_sheet"] == bs_n
        assert json.loads(sc.to_json(out))["sections"] == sec                                  # in summary.json
        text, md = sc.render(out), sc.to_markdown(out, "2026-10-28")
        for body in (text, md):
            assert f"with id=balance-sheet      {bs_n} of 1" in body and f"with id=cash-flow          {cf_n} of 1" in body
        assert 'WARNING: NO stored page carries id="cash-flow"' in text and 'WARNING: NO stored page carries id="cash-flow"' in md
        assert ('WARNING: NO stored page carries id="balance-sheet"' in text) is (bs_n == 0)
    assert "## Sections found on the stored pages" in md


def test_pages_that_carry_the_sections_but_make_no_pair_are_warned_about_and_nothing_read_is_too():
    # the sections are there, memory holds no statement to set against them
    out = sc.summarise([sc.compare_company(memory(), {"CONSOLIDATED": parse_full(page_html(bs=BS, cf={"Cash from Operating Activity": [1, 2]}))}, "1", "D")])
    assert out["sections"]["pages_with_balance_sheet"] == 1 and out["sections"]["companies_with_balance_sheet_pairs"] == 0
    assert 'WARNING: pages carry id="balance-sheet" but no balance-sheet pair was made' in sc.render(out)
    empty = sc.summarise([])
    assert empty["sections"]["pages_read"] == 0 and "WARNING: no stored page was read" in sc.render(empty)
    assert "with id=balance-sheet      0 of 0" in sc.to_markdown(empty, "2026-10-28")


def test_a_run_counts_the_pages_it_could_not_parse_and_reads_the_facts_from_the_sink():
    class Sink:
        def __init__(self):
            self.objects = {}

        def list_objects(self, prefix):
            return sorted(k for k in self.objects if k.startswith(prefix))

        def get_object(self, key):
            return self.objects.get(key)

        def get_dossier(self, scrip):
            return memory()

        def query(self, name, params):
            return []

        def put_object(self, key, body, content_type="application/json"):
            self.objects[key] = body

    sink = Sink()
    sink.objects["raw/screener/2026-10-28/DEMO_c.html.gz"] = sd.pack(page_html(sales=179))
    sink.objects["raw/screener/2026-10-28/DEMO_s.html.gz"] = sd.pack("<html>no section</html>")
    xbrl_facts.save(sink, "1", "Q4FY26", "CONSOLIDATED", excise_and_vat_facts()["Q4FY26"])
    out = sc.run(sink, [("1", "DEMO")], workers=1, use_referee=False)
    assert out["sections"]["pages_read"] == 1 and out["sections"]["pages_unparsed"] == 1
    rows = list(csv.DictReader(io.StringIO(sc.to_csv(out))))
    revenue = next(r for r in rows if r["metric"] == "revenue")
    assert revenue["class"] == "matches_screener_view:excise_taxes" and revenue["adjustment"] == "excise_taxes (xbrl facts)"
    assert "adjustment" in rows[0]


def test_every_adjustment_applied_is_in_the_csv_also_those_from_memory():
    d = memory(extra=[("other_income", "Q4FY26", 10.0), ("exceptional_items", "Q4FY26", 30.0)])
    html = section("quarters", {"Sales&nbsp;+": [200], "Other Income&nbsp;+": [40], "Net Profit&nbsp;+": [100]}, ["Mar 2026"])
    out = sc.summarise([compare(d, html)], "2026-10-28")
    rows = list(csv.DictReader(io.StringIO(sc.to_csv(out))))
    other = next(r for r in rows if r["metric"] == "other_income")
    assert other["class"] == "matches_screener_view:exceptional_in_other_income" and other["adjustment"] == "exceptional_in_other_income (memory)"


# --- the cash flow of a year end other than March ------------------------------------------------------------------------

CF = {"Cash from Operating Activity&nbsp;+": [150, 180], "Cash from Investing Activity&nbsp;+": [-100, -120],
      "Cash from Financing Activity&nbsp;+": [-30, -40], "Net Cash Flow": [20, 20]}


def june_year_facts(operating=180.0):
    contexts = {"Y": {"s": "2024-07-01", "e": "2025-06-30", "m": 12}}
    return facts_doc(money("CashFlowsFromUsedInOperatingActivities", "Y", operating),
                     money("CashFlowsFromUsedInInvestingActivities", "Y", -120.0),
                     money("CashFlowsFromUsedInFinancingActivities", "Y", -40.0),
                     money("IncreaseDecreaseInCashAndCashEquivalents", "Y", 20.0), contexts=contexts)


def test_a_june_year_end_is_paired_from_the_facts_of_the_file_ending_then():
    page = page_html(cf=CF, cf_columns=("Jun 2024", "Jun 2025"))
    parsed = parse_full(page)
    assert set(parsed["cash_flow"]) == {"YE:2024-06", "YE:2025-06"} and parsed["sections"] == {"balance_sheet": False, "cash_flow": True}
    facts = loader({"Q1FY26": june_year_facts()})              # the quarter ended 30 June 2025 is Q1FY26
    got = compare(memory(fy_end=6), page, facts)
    cash = {(p["period"], p["metric"]): p for p in got["cf_pairs"]}
    assert {p["class"] for p in cash.values()} == {"match"} and len(cash) == 4
    assert cash[("YE:2025-06", "operating")]["memory_source_id"] == "facts:Q1FY26" and "12-month cash flow" in cash[("YE:2025-06", "operating")]["note"]
    assert cash[("YE:2025-06", "operating")]["adjustment"] == "own_year_end (xbrl facts)"
    # the earlier year has no stored facts: counted, with the reason, not dropped
    assert got["cf_skipped"] == [{"period": "YE:2024-06", "reason": "no XBRL facts stored for Q1FY25"}]
    out = sc.summarise([got], "2026-10-28")
    assert out["cf_skipped"] == {"columns": 1, "companies": 1, "by_reason": {"no XBRL facts stored for Q1FY25": 1}}
    assert "cash-flow columns not paired 1 (1 companies)" in sc.render(out) and "no XBRL facts stored for Q1FY25" in sc.to_markdown(out, "d")
    # a wrong figure in the file is a class like any other
    wrong = compare(memory(fy_end=6), page, loader({"Q1FY26": june_year_facts(operating=170.0)}))
    assert {(p["period"], p["metric"]): p for p in wrong["cf_pairs"]}[("YE:2025-06", "operating")]["class"] == "mismatch"


def test_cash_flow_columns_that_cannot_be_paired_are_all_counted():
    page = page_html(cf=CF, cf_columns=("Apr 2024", "Dec 2025"))      # April is no quarter end; December has no facts file here
    got = compare(memory(fy_end=12), page, loader({}))
    reasons = {s["period"]: s["reason"] for s in got["cf_skipped"]}
    assert reasons["YE:2024-04"] == "year ends Apr 2024, not a quarter end" and reasons["YE:2025-12"] == "no XBRL facts stored for Q3FY26"
    assert got["cf_pairs"] == []
    # no loader at all (a caller that has no facts): counted too, never a silent skip
    bare = sc.cash_flow_pairs({}, parse_full(page)["cash_flow"], None, skipped := [])
    assert bare == [] and len(skipped) == 2 and skipped[1]["reason"] == "no XBRL facts available"


def test_a_march_year_end_is_still_read_from_memory_and_is_not_counted_as_skipped():
    cash = [entry("operating_cash_flow", "FY26", 180.0)]
    d = memory(extra=[(e["metric"], e["period"], e["value"]) for e in cash])
    got = compare(d, page_html(cf=CF), None)
    assert {(p["period"], p["metric"]) for p in got["cf_pairs"]} == {("FY26", "operating")} and got["cf_skipped"] == []


# --- top-mcap ---------------------------------------------------------------------------------------------------------------

class CapSink:
    def __init__(self, caps):
        self.caps = caps

    def query(self, name, params):
        assert name == "companies_universe"
        after, limit = params
        rows = [{"scrip_code": s, "market_cap_cr": c} for s, c in sorted(self.caps.items()) if s > after]
        return rows[:limit]


def test_top_mcap_picks_the_n_largest_by_market_cap_with_unpriced_last():
    caps = {"1": 500.0, "2": 90_000.0, "3": 12_000.0, "4": None, "5": 12_000.0, "6": 7.0}
    companies = [(s, f"S{s}") for s in caps]
    assert cli._largest_by_mcap(CapSink(caps), companies, 3) == [("2", "S2"), ("3", "S3"), ("5", "S5")]     # ties by symbol
    assert cli._largest_by_mcap(CapSink(caps), companies, 10)[-1] == ("4", "S4")
    assert cli._largest_by_mcap(CapSink(caps), [("6", "S6"), ("1", "S1")], 1) == [("1", "S1")]          # of the named companies


def test_top_mcap_and_scrips_are_options_of_the_command(monkeypatch, capsys, tmp_path):
    caps = {"1": 500.0, "2": 90_000.0, "3": 12_000.0}

    class Sink(CapSink):
        def __init__(self):
            super().__init__(caps)
            self.objects = {}

        def list_objects(self, prefix):
            return []

    sink = Sink()
    monkeypatch.setattr(cli, "make_sink", lambda settings: sink, raising=False)
    monkeypatch.setattr(cli, "_universe_companies", lambda s, scrips: [("1", "A"), ("2", "B"), ("3", "C")])
    seen = []
    monkeypatch.setattr(sc, "run", lambda s, companies, day, workers, referee: seen.append(companies) or sc.summarise([], None))
    assert cli.main(["screener-crosscheck", "--top-mcap", "2"]) == 0
    assert seen == [[("2", "B"), ("3", "C")]] and "top 2 by market cap: B, C" in capsys.readouterr().out
    assert cli.main(["screener-crosscheck", "--top-mcap", "0"]) == 2
    assert cli.main(["screener-crosscheck", "--scrips", "A,B"]) == 0 and seen[-1] == [("1", "A"), ("2", "B"), ("3", "C")]
