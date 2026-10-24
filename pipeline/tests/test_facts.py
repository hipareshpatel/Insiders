"""Figures computed in code for a results card (facts.py, owner 24 Oct 2026)."""

from bse_intel import computed
from bse_intel.facts import block, results_facts
from bse_intel.models import BalanceSheet, FinancialMetric
from bse_intel.xbrl import XbrlResult


def _tagged(sheet=None, **rows):
    """rows: metric=(now, year_ago); periods Q2FY27 and Q2FY26, cash flow H1FY27."""
    metrics = []
    for metric, (now, ago) in rows.items():
        if metric in ("operating_cash_flow", "capex", "pat_h1"):
            metrics.append(FinancialMetric(metric="pat" if metric == "pat_h1" else metric, period="H1FY27", value=now))
            continue
        metrics.append(FinancialMetric(metric=metric, period="Q2FY27", value=now,
                                       unit="PCT" if metric == "ebitda_margin" else "INR_CR"))
        if ago is not None:
            metrics.append(FinancialMetric(metric=metric, period="Q2FY26", value=ago,
                                           unit="PCT" if metric == "ebitda_margin" else "INR_CR"))
    return XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period="Q2FY27", metrics=metrics, balance_sheet=sheet)


# The statement as printed: this quarter and the year-ago quarter, ₹ crore
STATEMENT = ("Revenue from operations 1,200.00 1,000.00\nCost of materials consumed 456.00 400.00\n"
             "Employee benefits expense 110.00 95.00\nOther income 20.00 15.00\nProfit before tax 200.00 160.00\n"
             "Tax expense 50.00 38.00\nProfit for the period 150.00 122.00\nInventories 300.00 330.00")


def test_cost_share_and_its_move_in_bps():
    facts = results_facts(_tagged(revenue=(1200, 1000), raw_material_cost=(456, 400)), STATEMENT)
    line = next(f for f in facts if f.text.startswith("Cost of materials"))
    # 38.0% against 40.0%: down 200 bps
    assert "38.0% of revenue against 40.0% in Q2FY26 (down 200 bps)" in line.text
    assert (line.kind, line.value, line.sign) == ("bps", 200, -1)


def test_a_comparative_the_filing_does_not_print_gives_no_move():
    # the year-ago revenue of 900 came from memory, not this statement: a restated or other-basis base
    facts = results_facts(_tagged(revenue=(1200, 900), raw_material_cost=(456, 400)), STATEMENT)
    texts = [f.text for f in facts if f.text]
    assert "Cost of materials and goods Q2FY27: 38.0% of revenue" in texts
    assert not any(f.kind == "bps" for f in facts)


def test_tax_rate_other_income_share_and_profit_margin():
    facts = results_facts(_tagged(revenue=(1200, 1000), pbt=(200, 160), tax_expense=(50, 38), other_income=(20, 15),
                                  pat=(150, 122)), STATEMENT)
    texts = "\n".join(f.text for f in facts)
    assert "Effective tax rate Q2FY27: 25.0% against 23.8% in Q2FY26" in texts
    assert "Other income Q2FY27: 10.0% of profit before tax against 9.4% in Q2FY26" in texts
    assert "Net profit Q2FY27: 12.5% of revenue against 12.2% in Q2FY26 (up 30 bps)" in texts


def test_ebitda_margin_move_needs_printed_inputs():
    tagged = _tagged(revenue=(1200, 1000), pbt=(200, 160), ebitda_margin=(18.4, 17.0))
    assert any("EBITDA margin Q2FY27: 18.4% against 17.0% in Q2FY26 (up 140 bps)" in f.text
               for f in results_facts(tagged, STATEMENT))
    # the year-ago PBT not printed: no move
    assert not any("EBITDA" in f.text for f in results_facts(tagged, STATEMENT.replace("200.00 160.00", "200.00")))


def test_cash_conversion_capex_and_free_cash_flow():
    facts = results_facts(_tagged(revenue=(1200, 1000), operating_cash_flow=(309, None), capex=(-120, None),
                                  pat_h1=(300, None)), STATEMENT)
    line = next(f.text for f in facts if f.text.startswith("Cash flow"))
    assert line == ("Cash flow H1FY27: cash from operations ₹309 Cr, 103% of net profit ₹300 Cr, capex ₹120 Cr, "
                    "free cash flow ₹189 Cr")


def test_balance_sheet_against_the_last_statement_in_memory():
    sheet = BalanceSheet(period="SEP-2026", inventories_cr=300.0, cash_cr=785.0, gross_debt_cr=100.0)
    facts = results_facts(_tagged(sheet, revenue=(1200, 1000)), STATEMENT,
                          [{"period": "MAR-2026", "inventories_cr": 330.0}])
    line = next(f.text for f in facts if f.text.startswith("Balance sheet"))
    assert "inventories ₹300 Cr against ₹330 Cr at MAR-2026 (-9%)" in line
    assert "net cash ₹685 Cr" in line


def test_pool_takes_the_figures_with_their_direction():
    facts = results_facts(_tagged(revenue=(1200, 1000), raw_material_cost=(456, 400)), STATEMENT)
    pool = computed.build_pool("", facts=facts)
    assert pool.has("bps", 200, 0, -1)
    assert not pool.has("bps", 200, 0, +1)   # "rose 200 bps" is not what code worked out
    assert pool.has("pct", 38.0, 1, 0)


def test_block_and_nothing_for_other_files():
    assert block([]) == ""
    assert results_facts(None, STATEMENT) == []
    assert results_facts(XbrlResult(kind="SHAREHOLDING"), STATEMENT) == []
    text = block(results_facts(_tagged(revenue=(1200, 1000), raw_material_cost=(456, 400)), STATEMENT))
    assert text.startswith("Computed by the system") and "- Cost of materials" in text
