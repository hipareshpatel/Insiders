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
    sheet = BalanceSheet(period="SEP-2026", inventories_cr=300.0, cash_cr=13.62, gross_debt_cr=305.6)
    # the latest earlier statement with the line, past an empty snapshot
    facts = results_facts(_tagged(sheet, revenue=(1200, 1000)), STATEMENT,
                          [{"period": "MAR-2026", "inventories_cr": 330.0}, {"period": "JUN-2026"}])
    line = next(f.text for f in facts if f.text.startswith("Balance sheet"))
    assert "inventories ₹300 Cr against ₹330 Cr at MAR-2026 (-9%)" in line
    # cash and cash equivalents leave out bank deposits: no cash or net debt line (Kajaria, net cash ₹635 Cr)
    assert "borrowings ₹305.6 Cr" in line and "cash" not in line and "net debt" not in line


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


def test_the_scale_block_takes_no_net_debt_from_the_results_xbrl():
    from bse_intel.signals import scale_block, stated_net_debt
    xbrl_snap = {"period": "Q2FY27", "gross_debt_cr": 305.6, "cash_cr": 13.62, "net_debt_cr": 291.98,
                 "source_news_id": "xbrl:res:500233:Q2FY27"}
    text = scale_block({"balance_sheet": [xbrl_snap]}, {"market_cap_cr": 20000.0}, "")
    assert "gross debt ₹305.6" in text.replace(",", "") and "net debt" not in text
    # a filing that states its net cash keeps it
    stated = {"period": "Sep-26", "net_debt_cr": -635.0, "source_news_id": "nse-106827741"}
    assert stated_net_debt(stated) == -635.0 and stated_net_debt(xbrl_snap) is None
    assert "net cash" in scale_block({"balance_sheet": [stated]}, {"market_cap_cr": 20000.0}, "")


def test_year_to_date_against_the_years_guidance():
    from bse_intel.facts import guidance_facts
    tagged = XbrlResult(kind="RESULTS", period="Q2FY27", metrics=[
        FinancialMetric(metric="ebitda", period="H1FY27", value=546.99),
        FinancialMetric(metric="ebitda_margin", period="H1FY27", value=19.56, unit="PCT")])
    guidance = [{"id": "g_3937bdcc", "metric": "ebitda", "target": "1000+ INR_CR", "due": "FY27", "given_on": "2026-08-03T17:41"},
                {"id": "g_f9f80c85", "metric": "ebitda_margin", "target": "18-19%", "due": "FY27", "given_on": "2026-08-03"},
                {"id": "g_old", "metric": "ebitda", "target": "800 INR_CR", "due": "FY26"},          # another year
                {"id": "g_vol", "metric": "volume_growth", "target": "double-digit", "due": "FY27"}]  # no figure to set
    facts = guidance_facts(tagged, guidance)
    assert [f.text for f in facts] == [
        "H1FY27 EBITDA ₹546.99 Cr is 55% of the FY27 guidance of ₹1,000 Cr plus (given 2026-08-03)",
        "H1FY27 EBITDA margin 19.56%, above the 18-19% guided for FY27 (given 2026-08-03)"]
    assert [f.memory_ref for f in facts] == ["g_3937bdcc", "g_f9f80c85"]


def test_a_capex_plan_whose_cost_changed():
    from bse_intel.facts import capex_revisions
    deal = {"id": "d_2a5d908f", "kind": "CAPEX", "counterparty": "Srikalahasti Plant", "history": [
        {"amount_cr": 210.0, "as_of": "2026-04-30T14:55:14+05:30"},
        {"amount_cr": 340.0, "as_of": "2026-10-24T19:09:00+05:30"}]}
    facts = capex_revisions([deal], "2026-10-24T19:19:27+05:30")
    assert facts[0].text == "Srikalahasti Plant capex ₹340 Cr against ₹210 Cr first approved (+62%)"
    assert (facts[0].memory_ref, facts[0].sign) == ("d_2a5d908f", 1)
    assert capex_revisions([deal], "2027-06-01T10:00:00+05:30") == []   # the change is old news by then


def test_balance_sheet_against_the_files_own_earlier_date():
    sheet = BalanceSheet(period="Q2FY27", inventories_cr=579.67, gross_debt_cr=305.6)
    tagged = _tagged(sheet, revenue=(1200, 1000))
    tagged.balance_prior = BalanceSheet(period="Q4FY26", inventories_cr=551.46, gross_debt_cr=130.32)
    # memory's year-ago figures are not used where the file carries its own, nor a whole crore a chart axis prints
    facts = results_facts(tagged, "EBITDA chart 50 100 150 200 250", [{"period": "Q2FY26", "gross_debt_cr": 199.51}])
    line = next(f.text for f in facts if f.text.startswith("Balance sheet"))
    assert "inventories ₹579.67 Cr against ₹551.46 Cr at Q4FY26 (+5%)" in line
    assert "borrowings ₹305.6 Cr against ₹130.32 Cr at Q4FY26 (+134%)" in line and "199.51" not in line


def test_ebitda_change_stands_against_a_release_printing_its_own_ebitda():
    tagged = _tagged(revenue=(1468.26, 1186.01), ebitda=(286.61, 213.45))
    for m in tagged.metrics:
        if m.metric == "ebitda" and m.period == "Q2FY27":
            m.yoy_pct = 34.3
    pool = computed.build_pool("EBITDA 286.50 212.90 Total Sales 1,468.26 1,186.56", tagged)
    assert pool.has("pct", 34.3, 1, 1)
    # a line that is not code's own sum keeps the exact test
    tagged2 = _tagged(revenue=(1468.26, 1176.01))
    for m in tagged2.metrics:
        if m.period == "Q2FY27":
            m.yoy_pct = 24.9
    assert not computed.build_pool("Total Sales 1,468.26 1,180.00", tagged2).has("pct", 24.9, 1, 1)
