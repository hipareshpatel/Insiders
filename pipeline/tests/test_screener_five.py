"""The screener view as screener's own formulas, reproduced to the paisa from the XBRL elements for TCS, Sun Pharma, L&T, Tata Steel
and ITC (docs/audit/screener-five-2026-10-28.md, sections 4 and 11.2), with that report's real numbers: Sales less the excise row
(ITC Q1FY27 19,114.37), Interest with the finance-cost row (L&T Q1FY26 2,487.96), Operating Profit, Net Profit whole against the
owners' share, borrowings with the lease rows, the totals less netted deferred tax in a March column only, Net Block, CWIP,
Investments, Cash from Investing with the exchange-rate effect, and the associates' share reported as a named alternative."""

from __future__ import annotations

import pytest

from bse_intel import screener_crosscheck as sc
from bse_intel import xbrl_facts
from bse_intel.screener_fill import parse_full

CR = 10_000_000
CONTEXTS = {
    # Q1FY27 (ITC) and Q1FY26 (L&T): the quarter, and a breakdown row of Other expenses on the axis the integrated filing uses
    "ITC_Q": {"s": "2026-04-01", "e": "2026-06-30", "m": 3},
    "ITC_X": {"s": "2026-04-01", "e": "2026-06-30", "m": 3, "d": {"in-capmkt:DetailsOfOtherExpensesAxis": "OtherExpenses1Member"}},
    "LT_Q": {"s": "2025-04-01", "e": "2025-06-30", "m": 3},
    "LT_X": {"s": "2025-04-01", "e": "2025-06-30", "m": 3, "d": {"in-capmkt:DetailsOfOtherExpensesAxis": "OtherExpenses3Member"}},
    "Y": {"s": "2025-04-01", "e": "2026-03-31", "m": 12},
    "I": {"i": "2026-03-31"},
    "I2": {"i": "2026-09-30"},
    "N1": {"i": "2026-03-31", "d": {"in-capmkt:DetailsOfOtherNoncurrentFinancialLiabilitiesAxis": "Member1"}},
    "N2": {"i": "2026-03-31", "d": {"in-capmkt:DetailsOfOtherCurrentFinancialLiabilitiesAxis": "Member2"}},
    "A1": {"i": "2026-03-31", "d": {"in-capmkt:DetailsOfOtherNoncurrentAssetsAxis": "Member3"}},
}


def money(name, ctx, crore):
    return [name, ctx, "INR", crore * CR, -5]


def text(name, ctx, value):
    return [name, ctx, None, value, None]


def facts_by(**docs):
    def facts(period, basis):
        rows = docs.get(period)
        return xbrl_facts.Facts({"contexts": CONTEXTS, "units": {"INR": "MONEY"}, "facts": rows, "basis": "CONSOLIDATED"}) if rows else None
    return facts


def section(section_id, table, columns):
    head = "".join(f"<th>{c}</th>" for c in columns)
    body = "".join(f"<tr><td>{label}</td>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>" for label, vals in table.items())
    return (f'<section id="{section_id}"><p>Consolidated Figures in Rs. Crores</p><table><thead><tr><th></th>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></section>")


def entry(metric, period, value):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "basis": "CONSOLIDATED", "as_of": "2026-11-01",
            "source_news_id": f"xbrl:res:1:{period}"}


def memory(period, figures, snaps=()):
    metrics = [entry(m, period, v) for m, v in figures.items()]
    metrics += [entry("pat", s["period"], 1.0) for s in snaps if s["period"] != period]
    return {"financial_metrics": metrics, "balance_sheet": [dict(s) for s in snaps], "sector": "Demo"}


def compare(d, html, facts=None):
    return sc.compare_company(d, {"CONSOLIDATED": parse_full(html)}, "1", "CO", facts)


def pair(result, key, metric, period):
    return next(p for p in result[key] if p["metric"] == metric and p["period"] == period)


# --- ITC: Sales less the Excise Duty row ------------------------------------------------------------------------------------

def test_itc_q1fy27_sales_is_revenue_less_the_excise_duty_row():
    d = memory("Q1FY27", {"revenue": 29523.30, "pat": 5000.0})
    html = section("quarters", {"Sales&nbsp;+": ["19,114.37"], "Net Profit&nbsp;+": ["5,000"]}, ["Jun 2026"])
    facts = facts_by(Q1FY27=[text("DescriptionOfOtherExpenses", "ITC_X", "Excise Duty"), money("OtherExpenses", "ITC_X", 10408.93),
                             money("OtherExpenses", "ITC_Q", 12221.11)])
    p = pair(compare(d, html, facts), "pairs", "revenue", "Q1FY27")
    assert p["class"] == "matches_screener_view:excise" and p["adjustment"] == "excise (xbrl facts)"
    assert 29523.30 - 10408.93 == pytest.approx(19114.37)


# --- L&T: the finance cost of the financial-services business is Interest, not Expenses ----------------------------------------

def lt_page(interest="2,488", operating="8,024"):
    return section("quarters", {"Sales&nbsp;+": ["63,679"], "Operating Profit": [operating], "Interest": [interest],
                                "Net Profit&nbsp;+": ["4,318"]}, ["Jun 2025"])


LT_FACTS = facts_by(Q1FY26=[text("DescriptionOfOtherExpenses", "LT_X", "Finance cost of financial services business - Interest"),
                            money("OtherExpenses", "LT_X", 1706.35), money("FinanceCosts", "LT_Q", 781.61)])


def lt_memory():
    return memory("Q1FY26", {"revenue": 63678.9, "pat": 4318.2, "finance_cost": 781.61, "ebitda": 6317.7})


def test_lt_q1fy26_interest_is_finance_costs_plus_the_finance_cost_row():
    got = compare(lt_memory(), lt_page(), LT_FACTS)
    p = pair(got, "six_pairs", "finance_cost", "Q1FY26")
    assert p["class"] == "matches_screener_view:financial_services_finance_cost"
    assert p["adjustment"] == "financial_services_finance_cost (xbrl facts)" and "finance_services_cost 1706.35" in p["note"]
    assert 781.61 + 1706.35 == pytest.approx(2487.96)                   # the Data Sheet's figure
    # without the facts the gap is unexplained
    assert pair(compare(lt_memory(), lt_page()), "six_pairs", "finance_cost", "Q1FY26")["class"] == "mismatch"


def test_lt_q1fy26_operating_profit_is_ours_plus_the_same_row_and_the_excise_cancels():
    got = compare(lt_memory(), lt_page(), LT_FACTS)
    p = pair(got, "six_pairs", "ebitda", "Q1FY26")
    assert p["class"] == "matches_screener_view:financial_services_finance_cost" and p["screener_value"] == 8024.0
    assert 6317.7 + 1706.35 == pytest.approx(8024.05)
    # a company with no such row (Sun Pharma) is left as it is
    assert pair(compare(lt_memory(), lt_page(), facts_by(Q1FY26=[money("FinanceCosts", "LT_Q", 781.61)])), "six_pairs", "ebitda",
                "Q1FY26")["class"] == "mismatch"


# --- Net Profit: the web page shows the whole profit, the Excel the owners' share -----------------------------------------------

@pytest.mark.parametrize("whole, owners", [(49454.0, 49210.0), (11509.0, 11479.42), (18954.0, 16083.99), (10886.0, 10793.87), (21018.0, 20689.47)])
def test_net_profit_of_the_page_is_the_whole_profit_and_the_owners_share_is_a_named_view(whole, owners):
    d = memory("Q4FY26", {"revenue": 100000.0, "pat": whole, "pat_owners": owners})
    page = lambda value: section("quarters", {"Sales&nbsp;+": ["100,000"], "Net Profit&nbsp;+": [f"{value:,.2f}"]}, ["Mar 2026"])
    assert pair(compare(d, page(whole)), "pairs", "pat", "Q4FY26")["class"] == "match"            # screener's web page
    named = pair(compare(d, page(owners)), "pairs", "pat", "Q4FY26")                               # screener's Excel
    if abs(whole - owners) <= 0.005 * whole:
        # a minority under 0.5% of the profit (TCS, Sun) is inside the plain tolerance: both are a match, nothing to name
        assert named["class"] == "match"
    else:
        assert named["class"] == "naming" and "pat_owners" in named["note"]


# --- the associates' share: reported, not fitted ----------------------------------------------------------------------------------

def associates_result(symbol, other_income, share, screener_other, pbt=5000.0, screener_pbt=None):
    d = memory("Q4FY26", {"revenue": 10000.0, "pat": 100.0, "other_income": other_income, "share_associates": share, "pbt": pbt})
    html = section("quarters", {"Sales&nbsp;+": ["10,000"], "Other Income&nbsp;+": [f"{screener_other:,.2f}"],
                                "Profit before tax": [f"{screener_pbt or pbt:,.2f}"], "Net Profit&nbsp;+": ["100"]}, ["Mar 2026"])
    return sc.compare_company(d, {"CONSOLIDATED": parse_full(html)}, "1", symbol)


def test_the_associates_share_is_reported_per_company_which_way_it_matches():
    itc = associates_result("ITC", 2000.0, 139.57, 2139.57, screener_pbt=5139.57)       # screener counts the share
    lt = associates_result("LT", 1441.0, -184.47, 1441.0)                                # screener leaves it out
    assert itc["associates"] == {"with": 2, "without": 0, "neither": 0} and lt["associates"] == {"with": 0, "without": 2, "neither": 0}
    assert pair(itc, "six_pairs", "other_income", "Q4FY26")["associates"] == "with"
    assert pair(lt, "six_pairs", "pbt", "Q4FY26")["associates"] == "without"
    out = sc.summarise([itc, lt], "2026-10-28")
    assert out["associates"]["counted"] == ["ITC"] and out["associates"]["not counted"] == ["LT"]
    text = sc.render(out)
    assert "associates' share in Other Income and PBT (a named alternative, reported, never fitted" in text
    assert "counted in 2 quarters, not counted in 0" in text and "LT" in text
    assert "## The associates' share (Other Income and PBT)" in sc.to_markdown(out, "2026-10-28")
    # a share too small to tell the two ways apart says nothing
    assert associates_result("X", 2000.0, 1.0, 2000.0)["associates"] == {"with": 0, "without": 0, "neither": 0}
    # a company that neither way fits is reported so
    assert associates_result("Y", 2000.0, 140.0, 2500.0, screener_pbt=5300.0)["associates"]["neither"] == 2


# --- balance sheet --------------------------------------------------------------------------------------------------------------

def snap(period, **fields):
    return {"period": period, "as_of": "2026-11-01", "source_news_id": f"xbrl:res:1:{period}", **fields}


def bs_html(table, columns=("Mar 2026",)):
    return section("quarters", {"Sales&nbsp;+": ["100"], "Net Profit&nbsp;+": ["10"]}, ["Mar 2026"]) + section("balance-sheet", table, list(columns))


def bs_pair(d, table, facts, line, period="Q4FY26", columns=("Mar 2026",)):
    return pair(compare(d, bs_html(table, columns), facts), "bs_pairs", line, period)


def test_tcs_borrowings_are_borrowings_plus_the_lease_liability_rows():
    d = memory("Q4FY26", {"revenue": 100.0, "pat": 10.0}, [snap("Q4FY26", gross_debt_cr=9453.0, total_assets_cr=182372.0)])
    facts = facts_by(Q4FY26=[text("DescriptionOfOtherNoncurrentFinancialLiabilities", "N1", "Lease liabilities"),
                             money("OtherNoncurrentFinancialLiabilities", "N1", 1230.0),
                             text("DescriptionOfOtherCurrentFinancialLiabilities", "N2", "Lease liabilities"),
                             money("OtherCurrentFinancialLiabilities", "N2", 600.0)])
    p = bs_pair(d, {"Borrowings&nbsp;+": ["11,283"]}, facts, "borrowings")                     # 9,453 + 1,830 = 11,283
    assert p["class"] == "matches_screener_view:borrowings_plus_lease_liabilities" and "breakdown row" in p["note"]


def test_tcs_total_is_assets_less_the_smaller_deferred_tax_in_march_and_not_in_september():
    d = memory("Q4FY26", {"revenue": 100.0, "pat": 10.0},
               [snap("Q4FY26", total_assets_cr=182372.0), snap("Q2FY27", total_assets_cr=190782.0)])
    march = [money("DeferredTaxAssetsNet", "I", 1205.0), money("DeferredTaxLiabilitiesNet", "I", 6000.0)]
    sep = [money("DeferredTaxAssetsNet", "I2", 1205.0), money("DeferredTaxLiabilitiesNet", "I2", 6000.0)]
    facts = facts_by(Q4FY26=march, Q2FY27=sep)
    table = {"Total Assets": ["181,167", "190,782"], "Total Liabilities": ["181,167", "190,782"]}
    html = bs_html(table, ("Mar 2026", "Sep 2026"))
    got = compare(d, html, facts)
    assert pair(got, "bs_pairs", "total_assets", "Q4FY26")["class"] == "matches_screener_view:deferred_tax_net"       # 182,372 - 1,205
    assert pair(got, "bs_pairs", "total_assets", "Q2FY27")["class"] == "match"                                          # Sep: equals Assets
    wrongly_netted = bs_html({"Total Assets": ["181,167", "189,577"]}, ("Mar 2026", "Sep 2026"))
    assert pair(compare(d, wrongly_netted, facts), "bs_pairs", "total_assets", "Q2FY27")["class"] != "matches_screener_view:deferred_tax_net"


def test_itc_net_block_is_ppe_investment_property_goodwill_intangibles_and_the_right_of_use_row():
    d = memory("Q4FY26", {"revenue": 100.0, "pat": 10.0}, [snap("Q4FY26", fixed_assets_cr=30000.0, total_assets_cr=90000.0)])
    facts = facts_by(Q4FY26=[money("InvestmentProperty", "I", 100.0), money("Goodwill", "I", 200.0), money("OtherIntangibleAssets", "I", 300.0),
                             text("DescriptionOfOtherNoncurrentAssets", "A1", "Right-of-use assets"),
                             money("OtherNoncurrentAssets", "A1", 501.00)])
    p = bs_pair(d, {"Fixed Assets&nbsp;+": ["31,101"]}, facts, "fixed_assets")                  # 30,000 + 100 + 200 + 300 + 501
    assert p["class"] == "matches_screener_view:fixed_assets_plus_investment_property_goodwill_intangibles_right_of_use"


def test_cwip_with_intangibles_under_development_and_investments_with_the_equity_method():
    d = memory("Q4FY26", {"revenue": 100.0, "pat": 10.0},
               [snap("Q4FY26", cwip_cr=5000.0, investments_cr=40000.0, total_assets_cr=90000.0)])
    facts = facts_by(Q4FY26=[money("IntangibleAssetsUnderDevelopment", "I", 750.0), money("InvestmentsAccountedForUsingEquityMethod", "I", 1200.0),
                             money("InvestmentProperty", "I", 90.0)])
    got = compare(d, bs_html({"CWIP": ["5,750"], "Investments": ["41,200"]}), facts)
    assert pair(got, "bs_pairs", "cwip", "Q4FY26")["class"] == "matches_screener_view:cwip_plus_intangibles_under_development"
    # the investment property is in the Net Block, never in Investments
    assert pair(got, "bs_pairs", "investments", "Q4FY26")["class"] == "matches_screener_view:investments_plus_equity_method"


# --- cash flow ----------------------------------------------------------------------------------------------------------------------

def test_tcs_cash_from_investing_adds_the_exchange_rate_effect_on_cash():
    d = memory("FY26", {"investing_cash_flow": -12845.0, "operating_cash_flow": 50000.0}) | {"sector": "IT"}
    d["financial_metrics"] += [entry("revenue", "Q4FY26", 100.0), entry("pat", "Q4FY26", 10.0)]
    html = (section("quarters", {"Sales&nbsp;+": ["100"], "Net Profit&nbsp;+": ["10"]}, ["Mar 2026"])
            + section("cash-flow", {"Cash from Investing Activity&nbsp;+": ["-11,886"], "Cash from Operating Activity&nbsp;+": ["50,000"]},
                      ["Mar 2026"]))
    facts = facts_by(Q4FY26=[money("EffectOfExchangeRateChangesOnCashAndCashEquivalents", "Y", 959.0)])
    got = compare(d, html, facts)
    p = pair(got, "cf_pairs", "investing", "FY26")
    assert p["class"] == "matches_screener_view:investing_plus_exchange_effect" and p["adjustment"] == "investing_plus_exchange_effect (xbrl facts)"
    assert pair(got, "cf_pairs", "operating", "FY26")["class"] == "match"
    assert -12845 + 959 == -11886
    # no effect tagged (ITC): nothing to add
    assert pair(compare(d, html, facts_by(Q4FY26=[money("OtherIncome", "Y", 1.0)])), "cf_pairs", "investing", "FY26")["class"] in ("mismatch", "wrong_period")
    assert "matches_screener_view:investing_plus_exchange_effect" in sc.CF_CLASSES
