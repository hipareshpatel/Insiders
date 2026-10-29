"""Results cards built by code from the XBRL file (results_card.py; owner's PLAN 18 part 4)."""

from __future__ import annotations

import pytest

from pathlib import Path

from bse_intel import results_card, xbrl
from bse_intel.models import Pass2Output

FIX = Path(__file__).parent / "fixtures"


def _model_card():
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "Q3 revenue rose on lower tax",
        "card": {"impact_level": "MODERATE", "headline": "Ahluwalia Q3 revenue jumps on lower tax and a big order",
                 "takeaway": "Margins held up despite cost pressure.", "core_catalyst": "Lower tax drove profit",
                 "what_happened": ["Revenue rose 12% YoY to ₹952 Cr"],
                 "why_it_matters": [{"text": "One"}, {"text": "Two"}, {"text": "Three"}],
                 "notable_changes": [{"metric": "inventory_change", "previous": "0", "current": "5", "change": "build-up"}],
                 "key_numbers": [{"label": "Revenue", "value": "₹1,952 Cr", "change": "+12% YoY"}]}})


@pytest.mark.switches_off("CARD_EBITDA_PROFIT_V2")   # the behaviour before the switch; the switch has its own tests
def test_code_writes_the_figures_and_the_model_keeps_a_line_or_two():
    tagged = xbrl.parse((FIX / "bse_main_ind_as_532811_q3fy25.xml").read_bytes())
    out = _model_card()
    notes = results_card.build(out, tagged, "Ahluwalia Contracts (India) Limited")
    card = out.card
    assert card.headline == "Ahluwalia Contracts (India) Q3FY25: revenue ₹951.96 Cr, net profit ₹49.39 Cr"
    table = tagged.table()
    assert all(f.quote in table for f in card.what_happened)          # each fact quotes its table line
    assert [k.label for k in card.key_numbers][:3] == ["Revenue from operations", "EBITDA", "Net profit"]
    assert any(k.label == "EBITDA margin" and k.value == "8.9%" for k in card.key_numbers)
    assert card.notable_changes == [] and card.core_catalyst is None and card.quantified_impact == []
    assert [i.text for i in card.why_it_matters] == ["One", "Two"]
    # the takeaway is the file's own figures (no profit bridge in this file); the model's line is left out
    assert card.takeaway == "Q3FY25: revenue ₹951.96 Cr, net profit ₹49.39 Cr." and card.basis == "STANDALONE"
    assert out.timeline_entry.startswith("Q3FY25 results (standalone): revenue ₹951.96 Cr")
    assert notes and "notable changes (1) left out" in notes[0]


def test_a_bank_is_read_on_its_own_lines():
    tagged = xbrl.parse((FIX / "bse_bank_542867_q3fy25.xml").read_bytes())
    out = _model_card()
    results_card.build(out, tagged, "CSB Bank Limited")
    # a bank leads with its profit and its bad loans, not interest earned (owner, 2026-10-19: Punjab & Sind Bank)
    assert out.card.headline.startswith("CSB Bank Q3FY25: net profit ₹151.63 Cr")
    assert out.card.headline.endswith("; net NPA 0.64%, gross 1.58%")
    labels = [k.label for k in out.card.key_numbers]
    assert "Operating profit before provisions" in labels and "Provisions" in labels and "EBITDA margin" not in labels


def test_no_file_no_change():
    out = _model_card()
    assert results_card.build(out, None, "X") == [] and out.card.headline.startswith("Ahluwalia Q3 revenue jumps")


def test_a_loss_is_written_as_a_loss_and_a_turnaround_says_what_it_was():
    """No "net profit ₹-12.5 Cr"; a change against a year-ago loss has no percentage (xbrl._change), so the card says
    what the year before was instead of leaving the profit line bare."""
    from types import SimpleNamespace

    from bse_intel.models import FinancialMetric

    def tagged(now, before):
        return SimpleNamespace(kind="RESULTS", period="Q1FY27", basis="CONSOLIDATED", metrics=[
            FinancialMetric(metric="revenue", period="Q1FY27", value=500.0, yoy_pct=10.0),
            FinancialMetric(metric="pat", period="Q1FY27", value=now, yoy_pct=None),
            FinancialMetric(metric="pat", period="Q1FY26", value=before, yoy_pct=None)])

    out = _model_card()
    results_card.build(out, tagged(-12.5, 8.0), "Loss Co Limited")
    assert out.card.headline == "Loss Co Q1FY27: revenue ₹500 Cr (+10.0% YoY), net loss ₹12.5 Cr (against a profit of ₹8 Cr a year earlier)"
    assert any(k.label == "Net loss" and k.value == "₹12.5 Cr" for k in out.card.key_numbers)
    assert not any("-12.5" in f.text for f in out.card.what_happened)

    out = _model_card()
    results_card.build(out, tagged(20.0, -10.0), "Turn Co Limited")
    assert out.card.headline.endswith("net profit ₹20 Cr (against a loss of ₹10 Cr a year earlier)")


def _history(metric, values, unit="INR_CR"):
    from bse_intel.periods import quarter_from_index, quarter_index
    start = quarter_index("Q1FY25")
    return [{"metric": metric, "period": quarter_from_index(start + i), "value": v, "unit": unit} for i, v in enumerate(values)]


def _tagged(period, pat, pat_year_ago, revenue=None, revenue_year_ago=None, margin=None):
    from bse_intel.models import FinancialMetric
    from bse_intel.periods import prior_year_period
    from bse_intel.xbrl import XbrlResult
    metrics = [FinancialMetric(metric="pat", period=period, value=pat),
               FinancialMetric(metric="pat", period=prior_year_period(period), value=pat_year_ago)]
    if revenue is not None:
        metrics += [FinancialMetric(metric="revenue", period=period, value=revenue),
                    FinancialMetric(metric="revenue", period=prior_year_period(period), value=revenue_year_ago)]
    if margin is not None:
        metrics.append(FinancialMetric(metric="ebitda_margin", period=period, value=margin, unit="PCT"))
    return XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period=period, metrics=metrics)


def test_memory_points_rank_streaks_and_margins_from_memory_alone():
    """Owner (2026-10-19): results with contextual memory. Code states what memory holds, by period, so the model's
    misdated comparisons (Dabur, Protean in round 5) cannot happen."""
    from bse_intel.results_card import memory_points

    # Q1FY25..Q4FY26 in memory (8 quarters), this filing is Q1FY27
    history = _history("pat", [10, 11, 12, 13, 14, 15, 16, 17]) + _history("revenue", [100, 100, 100, 100, 90, 90, 90, 90]) \
        + _history("ebitda_margin", [15, 15, 15, 15, 18.0, 17.5, 18.2, 17.9], "PCT")
    points = [p.text for p in memory_points(_tagged("Q1FY27", 20, 14, revenue=120, revenue_year_ago=90, margin=14.0), history)]
    assert "Q1FY27 is the first year-on-year rise in revenue after 4 quarters of decline in memory." in points
    assert any("net profit of ₹20 Cr is the highest of the 9 quarters in a row memory holds since Q1FY25" in p for p in points)
    assert len(points) == 2 and all(p for p in points)
    # the margin point names each earlier quarter's own figure
    only_margin = memory_points(_tagged("Q1FY27", 15.5, 14, margin=14.0), _history("pat", [10, 11, 12, 13, 14, 15, 16, 17])
                                + _history("ebitda_margin", [15, 15, 15, 15, 18.0, 17.5, 18.2, 17.9], "PCT"))
    assert [p.text for p in only_margin] == [
        "EBITDA margin of 14.0% is below each of the previous four quarters (Q4FY26 17.9%, Q3FY26 18.2%, Q2FY26 17.5%, Q1FY26 18.0%).",
        "Net profit has grown year on year for 5 quarters running, Q1FY27 included."]


def test_memory_points_need_memory_and_the_file_to_agree_on_the_basis():
    """Max Financial (round 5): standalone figures against consolidated memory; nothing is said then."""
    from bse_intel.results_card import memory_points

    history = _history("pat", [10, 11, 12, 13, 14, 15, 16, 17])
    assert memory_points(_tagged("Q1FY27", 20, 1.4), history) == []      # the file's year-ago 1.4 is not memory's 14
    assert memory_points(_tagged("Q1FY27", 20, 14), history[:2]) == []   # too little memory for a rank or a run


def test_the_takeaway_names_what_moved_profit_from_the_file():
    """Texmaco Q1FY27 (round 5): PAT up 71% on "cost control" per the model; the file shows a tax credit while EBITDA
    fell. Ramco: a fall put on "lower other income" when other income rose and EBITDA fell."""
    from bse_intel.models import FinancialMetric
    from bse_intel.results_card import profit_driver
    from bse_intel.xbrl import XbrlResult

    def file(rows):
        return XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period="Q1FY27", metrics=[
            FinancialMetric(metric=m, period=p, value=v) for m, (now, then) in rows.items()
            for p, v in (("Q1FY27", now), ("Q1FY26", then))])

    texmaco = file({"pat": (50.07, 29.33), "ebitda": (56.8, 70.6), "other_income": (30.0, 18.5),
                    "tax_expense": (-7.57, 14.32), "finance_cost": (22.0, 23.0), "depreciation": (12.0, 11.5)})
    assert profit_driver(texmaco) == ("Q1FY27 net profit of ₹50.07 Cr against net profit of ₹29.33 Cr a year earlier; the "
                                      "largest move was a tax credit of ₹7.57 Cr against tax of ₹14.32 Cr a year earlier, "
                                      "while EBITDA fell to ₹56.8 Cr from ₹70.6 Cr.")
    ramco = file({"pat": (31.0, 84.6), "ebitda": (306.5, 397.5), "other_income": (6.74, 5.98), "tax_expense": (10.0, 28.0)})
    assert "the largest move was EBITDA of ₹306.5 Cr against ₹397.5 Cr" in profit_driver(ramco)
    assert profit_driver(file({"pat": (10.2, 10.0), "ebitda": (20, 19)})) is None     # profit barely moved
    bank = file({"pat": (500.0, 300.0), "interest_earned": (6996, 6436), "tax_expense": (100, 150)})
    assert profit_driver(bank) is None        # provisions move a bank's profit; the bridge does not have them


def test_no_driver_when_the_bridge_does_not_account_for_the_profit_change():
    """Like Siemens Q1FY27 (round 4), where total profit jumped on the demerged business's gain, outside every line of the bridge;
    naming the line that happened to move the same way as "the largest move" would be a cause the file does not give."""
    from bse_intel.models import FinancialMetric
    from bse_intel.results_card import profit_driver
    from bse_intel.xbrl import XbrlResult

    # profit +60 Cr, of which +50 Cr is a discontinued business's gain; tax fell 20 Cr, EBITDA fell 5 Cr
    rows = {"pat": (160.0, 100.0), "ebitda": (195.0, 200.0), "other_income": (10.0, 10.0), "depreciation": (30.0, 30.0),
            "finance_cost": (5.0, 5.0), "tax_expense": (40.0, 60.0)}
    siemens = XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period="Q1FY27", metrics=[
        FinancialMetric(metric=m, period=p, value=v) for m, (now, then) in rows.items()
        for p, v in (("Q1FY27", now), ("Q1FY26", then))])
    assert profit_driver(siemens) is None


def test_a_rank_counts_the_files_own_quarters_and_never_jumps_a_gap():
    """Orient Bell (round 6): memory lacked Q4FY26 and the card called Q1FY27 the highest quarter, though the filing's
    own Q4FY26 was higher. Jubilant: "highest of 6" where memory held two quarters in a row."""
    from bse_intel.models import FinancialMetric
    from bse_intel.results_card import history_from_view, memory_points

    tagged = _tagged("Q1FY27", 14, 12)
    tagged.metrics.append(FinancialMetric(metric="pat", period="Q4FY26", value=25))   # the file's previous quarter
    history = _history("pat", [10, 11, 12, 13, 14, 15, 16])                           # Q1FY25..Q3FY26, Q4FY26 missing
    assert not any("highest" in p.text for p in memory_points(tagged, history))
    gap = _history("pat", [10, 11, 12, 13, 14, 15]) + [{"metric": "pat", "period": "Q4FY26", "value": 13, "unit": "INR_CR"}]
    gap = [h for h in gap if h["period"] != "Q3FY26"]                                # a hole one quarter back
    assert not any("highest" in p.text for p in memory_points(_tagged("Q1FY27", 20, 12), gap))
    view = {"metrics": {"pat": ["Q3FY26: 15 INR_CR", "Q4FY26: 13 INR_CR", "FY26: 50 INR_CR"]}}
    assert [(h["period"], h["value"]) for h in history_from_view(view)] == [("Q3FY26", 15.0), ("Q4FY26", 13.0)]


def test_the_models_memory_comparisons_are_left_off_a_results_card():
    """LIC (round 6): "EPS -38% YoY" against a year-ago from before its 1:1 bonus; code makes memory's comparisons."""
    tagged = xbrl.parse((FIX / "bse_main_ind_as_532811_q3fy25.xml").read_bytes())
    out = _model_card()
    out.card.why_it_matters[0].basis = "MEMORY"
    results_card.build(out, tagged, "Ahluwalia Contracts (India) Limited")
    assert [i.text for i in out.card.why_it_matters] == ["Two", "Three"]


def test_a_group_with_minority_interests_is_given_its_shareholders_profit():
    """Bajaj Finserv (round 6): ₹6,296.67 Cr consolidated profit given as the company's; ₹3,132 Cr is its owners'."""
    from bse_intel.models import FinancialMetric
    from bse_intel.xbrl import XbrlResult

    tagged = XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period="Q1FY27", metrics=[
        FinancialMetric(metric="revenue", period="Q1FY27", value=38000.0),
        FinancialMetric(metric="pat", period="Q1FY27", value=6296.67),
        FinancialMetric(metric="pat_owners", period="Q1FY27", value=3132.0)])
    out = _model_card()
    results_card.build(out, tagged, "Bajaj Finserv Limited")
    assert out.card.headline == "Bajaj Finserv Q1FY27: revenue ₹38,000 Cr, net profit to shareholders ₹3,132 Cr"
    # the shareholders' share as a loss is written as a loss, like the group's own profit line
    tagged.metrics[2] = FinancialMetric(metric="pat_owners", period="Q1FY27", value=-120.0)
    out = _model_card()
    results_card.build(out, tagged, "Bajaj Finserv Limited")
    assert out.card.headline == "Bajaj Finserv Q1FY27: revenue ₹38,000 Cr, net loss to shareholders ₹120 Cr"


def test_a_change_against_a_comparative_the_filing_does_not_print_is_left_out():
    """Ambuja (round 6): year-ago profit from the year-ago file (₹969.66 Cr) after the statement restated it to ₹1,041 Cr."""
    from bse_intel.models import FinancialMetric
    from bse_intel.results_card import unconfirmed_changes
    from bse_intel.xbrl import XbrlResult

    tagged = XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period="Q1FY27", metrics=[
        FinancialMetric(metric="pat", period="Q1FY27", value=660.0, yoy_pct=-31.94),       # against 969.66
        FinancialMetric(metric="revenue", period="Q1FY27", value=9500.0, yoy_pct=10.0)])   # against 8636.36
    text = "Net profit 660.00 1,041.12 (restated). Revenue from operations 9,500.00 8,636.36"
    assert unconfirmed_changes(tagged, text) == ["pat YoY"]
    assert tagged.metrics[0].yoy_pct is None and tagged.metrics[1].yoy_pct == 10.0
    # a change is stored to one decimal: the printed comparative it was made from is found, in crore or in lakh
    for printed in ("Net profit 6,296.67 5,604.97", "Net profit 6,29,667 5,60,497 (Rs in lakh)"):
        rounded = XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period="Q1FY27", metrics=[
            FinancialMetric(metric="pat", period="Q1FY27", value=6296.67, yoy_pct=12.3)])   # 6,296.67 / 5,604.97 - 1
        assert unconfirmed_changes(rounded, printed) == [] and rounded.metrics[0].yoy_pct == 12.3


def test_revenue_with_excise_in_it_is_given_net_of_excise():
    """ITC (round 6): revenue "+27.6% YoY" gross of a higher cigarette excise; net of excise it fell about 11%."""
    from bse_intel.models import FinancialMetric
    from bse_intel.xbrl import XbrlResult

    rows = {"revenue": (29523.3, 23130.0), "excise_duty": (10409.0, 1635.0), "pat": (4508.79, 5343.0)}
    tagged = XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period="Q1FY27", metrics=[
        FinancialMetric(metric=m, period=p, value=v) for m, (now, then) in rows.items() for p, v in (("Q1FY27", now), ("Q1FY26", then))])
    out = _model_card()
    results_card.build(out, tagged, "ITC Ltd")
    assert out.card.headline.startswith("ITC Q1FY27: revenue net of excise ₹19,114.3 Cr (-11.1% YoY)")


def test_memory_points_say_when_growth_picks_up_or_slows():
    """Tatva Chintan's Q2 revenue +76% YoY reads differently beside Q1's +43% (owner's example, 2026-10-19): the point
    is made from memory's own quarters, this quarter's YoY against the last one's."""
    history = _history("revenue", [100, 100, 100, 100, 120, 150])   # Q1FY25..Q2FY26
    points = [p.text for p in results_card.memory_points(_tagged("Q3FY26", 10, 9, revenue=200, revenue_year_ago=100), history)]
    assert "Revenue growth picked up to +100% YoY from +50% in Q2FY26." in points, points


def test_a_zero_for_the_owners_share_beside_a_real_profit_is_a_filler():
    """Ahluwalia Q4FY25 (live review 2, 2026-10-20): "net profit to shareholders ₹0 Cr" beside PAT ₹83.33 Cr."""
    from bse_intel.models import FinancialMetric
    from bse_intel.xbrl import XbrlResult

    tagged = XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period="Q4FY25", metrics=[
        FinancialMetric(metric="revenue", period="Q4FY25", value=1215.84),
        FinancialMetric(metric="pat", period="Q4FY25", value=83.33),
        FinancialMetric(metric="pat_owners", period="Q4FY25", value=0.0)])
    out = _model_card()
    results_card.build(out, tagged, "Ahluwalia Contracts (India) Limited")
    assert "shareholders" not in out.card.headline and "₹83.33 Cr" in out.card.headline
    assert not any("₹0 Cr" in f.text for f in out.card.what_happened)


def test_a_change_cut_from_a_pair_keeps_its_brackets():
    """Shivam Autotech Q3FY25 (live review 2, 2026-10-20): "₹11.36 Cr, -7.0% QoQ);" once its YoY was removed."""
    from bse_intel.computed import _strip

    assert _strip("EBITDA Q3FY25: ₹11.36 Cr (+12.3% YoY, -7.0% QoQ); margin 10.1%.", ["+12.3%"]) == \
        "EBITDA Q3FY25: ₹11.36 Cr (-7.0% QoQ); margin 10.1%."
    assert _strip("Revenue ₹90 Cr (+3.7% YoY, +3.2% QoQ).", ["+3.2%"]) == "Revenue ₹90 Cr (+3.7% YoY)."
    assert _strip("EBITDA ₹11.36 Cr (+12.3% YoY); margin 10.1%.", ["+12.3%"]) == "EBITDA ₹11.36 Cr; margin 10.1%."


def test_the_pbt_the_statement_prints_and_the_owners_label():
    """Orient Bell's file tags PBT 11.41 before the associates' share (-0.26), the statement prints 11.15; "net profit
    to shareholders" was set to the group's profit, minorities included (live review 3, 2026-10-20)."""
    from bse_intel.models import FinancialMetric
    from bse_intel.pipeline import _KEY_METRIC
    from bse_intel.xbrl import XbrlResult, settle_pbt

    def result():
        return XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period="Q1FY27", metrics=[
            FinancialMetric(metric="pbt", period="Q1FY27", value=11.41),
            FinancialMetric(metric="share_associates", period="Q1FY27", value=-0.26)])

    r = result()
    assert settle_pbt(r, "Profit before tax 11.15 16.02") and r.metrics[0].value == 11.15
    r = result()
    assert settle_pbt(r, "Profit before tax 11.41 16.02") == [] and r.metrics[0].value == 11.41
    first = lambda label: next(name for name, pattern in _KEY_METRIC if pattern.search(label))
    assert first("Net profit to shareholders") == "pat_owners"
    assert first("Profit attributable to owners of the parent") == "pat_owners"
    assert first("Net profit") == "pat"


def test_eps_takes_its_profit_sign():
    """Shivam Autotech's file tags H1FY24 EPS 2.27 beside a ₹27.77 Cr loss (live review 2, 2026-10-20)."""
    from bse_intel.xbrl import eps_signs

    values = {("pat", "H1FY24"): -27.77, ("eps", "H1FY24"): 2.27, ("pat", "Q2FY25"): 10.0, ("eps", "Q2FY25"): 0.8,
              ("pat", "Q3FY25"): -5.0, ("pat_owners", "Q3FY25"): -4.0, ("eps", "Q3FY25"): -0.4}
    assert eps_signs(values) == 1
    assert values[("eps", "H1FY24")] == -2.27 and values[("eps", "Q2FY25")] == 0.8 and values[("eps", "Q3FY25")] == -0.4


def test_an_owners_profit_its_minority_share_does_not_add_up_to_is_dropped():
    """Adani Ports' Q4FY26 file tags both shares of other comprehensive income as the shares of profit (2026-10-20)."""
    from bse_intel.xbrl import owners_share

    values = {("pat", "Q4FY26"): 3308.30, ("pat_owners", "Q4FY26"): 1238.67, ("pat_minority", "Q4FY26"): 179.14,
              ("pat", "Q4FY25"): 6296.67, ("pat_owners", "Q4FY25"): 3132.0, ("pat_minority", "Q4FY25"): 3164.67,
              ("pat", "FY26"): 100.0, ("pat_owners", "FY26"): 90.0,
              ("pat", "Q1FY27"): -25.27, ("pat_owners", "Q1FY27"): -25.87, ("pat_minority", "Q1FY27"): 0.0,
              ("pat", "Q2FY27"): 9.23, ("pat_owners", "Q2FY27"): 0.0, ("pat_minority", "Q2FY27"): 0.0}
    assert owners_share(values) == 2
    assert values[("pat_owners", "Q1FY27")] == -25.87 and ("pat_owners", "Q2FY27") not in values   # fillers
    assert ("pat_owners", "Q4FY26") not in values   # 3,308.30 - 179.14 is no truer: the statement prints 3,328.96
    assert values[("pat_owners", "Q4FY25")] == 3132.0 and values[("pat_owners", "FY26")] == 90.0   # adds up; no minority
    assert not any(m == "pat_minority" for m, _ in values)


def test_an_owners_profit_above_the_whole_profit_with_no_minority_is_dropped():
    """D.B. Corp Q4FY26 (held-card audit, 22 Oct 2026): ₹63.98 Cr tagged as the owners' profit is its total
    comprehensive income; the profit is ₹62.19 Cr and the file has no minority share. Below the profit it stands."""
    from bse_intel.xbrl import owners_share

    values = {("pat", "Q4FY26"): 62.19, ("pat_owners", "Q4FY26"): 63.98,
              ("pat", "Q3FY26"): 95.51, ("pat_owners", "Q3FY26"): 95.51}
    assert owners_share(values) == 1
    assert ("pat_owners", "Q4FY26") not in values and values[("pat_owners", "Q3FY26")] == 95.51


def test_no_change_against_memory_when_the_filing_restates_its_comparatives():
    """Pitti Engineering Q2FY27 (daily audit, 23 Oct 2026): the amalgamation note says the comparatives "have been
    restated", and the reconciliation prints the first-reported PAT 3,558.25 lakh beside the restated 4,009.42; the
    card's "PAT -4.7% YoY" was against the old figure (restated: -15.5%)."""
    from bse_intel.models import FinancialMetric
    from bse_intel.results_card import unconfirmed_changes
    from bse_intel.xbrl import XbrlResult

    tagged = XbrlResult(kind="RESULTS", basis="STANDALONE", period="Q2FY27", metrics=[
        FinancialMetric(metric="pat", period="Q2FY27", value=33.89, yoy_pct=-4.7, qoq_pct=62.6),
        FinancialMetric(metric="eps", period="Q2FY27", value=9.18, unit="INR", yoy_pct=-4.1)])
    text = ("the comparative financial information for the previous periods presented have been restated to reflect "
            "the impact of the amalgamation. Profit after tax 2,084.15 866.04 2,950.19 3,558.25 451.17 4,009.42")
    assert unconfirmed_changes(tagged, text) == ["pat YoY", "pat QoQ", "eps YoY"]
    assert tagged.metrics[0].yoy_pct is None and tagged.metrics[0].qoq_pct is None


def _rich_model_card():
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "Q3 results",
        "card": {"impact_level": "MODERATE", "headline": "Ahluwalia Q3", "takeaway": "Profit rose.",
                 "core_catalyst": "New orders of ₹1,200 Cr in the quarter",
                 "what_happened": [
                     {"text": "The board declared an interim dividend of ₹2 a share.",
                      "quote": "declared an interim dividend of Rs 2 per share"},
                     {"text": "Revenue ₹951.96 Cr.", "quote": "revenue Q3FY25: 951.96"},   # the table: code's line
                     {"text": "Orders rose", "quote": None}],
                 "why_it_matters": [{"text": "Buyback of ₹296.7 Cr completed", "basis": "MEMORY", "memory_refs": ["E12"]},
                                    {"text": "Margins best in years", "basis": "MEMORY"},   # no memory id
                                    {"text": "Orders from the filing", "basis": "FILING"}],
                 "notable_changes": [{"metric": "employee_cost", "previous": "50", "current": "60", "change": "up"}],
                 "key_numbers": [{"label": "Revenue", "value": "₹1,952 Cr"}]}})


def test_a_rich_card_keeps_computed_lines_and_the_models_quoted_facts():
    from bse_intel import computed
    from bse_intel.facts import Fact
    tagged = xbrl.parse((FIX / "bse_main_ind_as_532811_q3fy25.xml").read_bytes())
    facts = [Fact("", "pct", 38.0, base="revenue"), Fact("", "pct", 40.0, base="revenue"),
             Fact("Cost of materials and goods Q3FY25: 38.0% of revenue against 40.0% in Q3FY24 (down 200 bps)",
                  "bps", 200, -1)]
    out = _rich_model_card()
    notes = results_card.build(out, tagged, "Ahluwalia Contracts (India) Limited", facts=facts, rich=True)
    card = out.card
    texts = [f.text for f in card.what_happened]
    assert card.headline.startswith("Ahluwalia Contracts (India) Q3FY25:")      # still code's
    assert "Cost of materials and goods Q3FY25: 38.0% of revenue against 40.0% in Q3FY24 (down 200 bps)." in texts
    assert "The board declared an interim dividend of ₹2 a share." in texts
    assert "Revenue ₹951.96 Cr." not in texts and "Orders rose" not in texts      # repeats the table / no quote
    assert [w.text for w in card.why_it_matters][-2:] == ["Buyback of ₹296.7 Cr completed", "Orders from the filing"]
    assert card.core_catalyst and card.notable_changes and "(rich)" in notes[0]
    # the computed line survives the computed-figure rule, with a scale block's shares in the pool too
    pool = computed.build_pool("", tagged, scale="- ₹10 Cr = 1.0% of trailing-12-month revenue", facts=facts)
    computed.enforce(out, pool)
    assert any("38.0% of revenue against 40.0%" in f.text and "200 bps" in f.text for f in card.what_happened)


def test_without_rich_the_card_is_as_before():
    tagged = xbrl.parse((FIX / "bse_main_ind_as_532811_q3fy25.xml").read_bytes())
    out = _rich_model_card()
    results_card.build(out, tagged, "Ahluwalia Contracts (India) Limited")
    assert out.card.core_catalyst is None and out.card.notable_changes == []
    assert not any("dividend" in f.text for f in out.card.what_happened)


def test_points_set_against_memory_go_to_our_reading_with_their_id():
    from bse_intel.facts import Fact
    tagged = xbrl.parse((FIX / "bse_main_ind_as_532811_q3fy25.xml").read_bytes())
    out = _rich_model_card()
    facts = [Fact("9MFY25 EBITDA ₹300 Cr is 75% of the FY25 guidance of ₹400 Cr (given 2024-08-01)", "pct", 75,
                  memory_ref="g_1")]
    results_card.build(out, tagged, "Ahluwalia Contracts (India) Limited", facts=facts, rich=True)
    point = next(w for w in out.card.why_it_matters if w.memory_refs == ["g_1"])
    assert point.basis == "MEMORY" and point.text.startswith("9MFY25 EBITDA ₹300 Cr is 75%")
    assert not any("guidance" in f.text for f in out.card.what_happened)


def test_a_rich_card_keeps_no_model_fact_whose_amounts_code_already_shows():
    """Sampling re-run, 24 Oct 2026: "EBITDA ₹111.18 Cr, up 87.8% YoY" and "borrowings ₹938.96 Cr" repeated code's lines
    once a later step had re-pointed their quotes; finance cost and the dividend, in no code line, stay."""
    from bse_intel.facts import Fact as Computed
    tagged = xbrl.parse((FIX / "bse_main_ind_as_532811_q3fy25.xml").read_bytes())
    ebitda = next(m for m in tagged.metrics if m.metric == "ebitda" and m.period == tagged.period)
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "x",
        "card": {"impact_level": "MODERATE", "headline": "Ahluwalia Q3 results card", "what_happened": [
            {"text": f"EBITDA for the quarter stood at ₹{ebitda.value:,.2f} Cr.", "quote": "EBITDA for the quarter stood at"},
            {"text": "Borrowings rose to ₹938.96 Cr.", "quote": "borrowings increased"},
            {"text": "Finance cost rose to ₹18.85 Cr.", "quote": "Finance costs 18.85 14.57"},
            {"text": "Paid a final dividend of ₹12.34 Cr.", "quote": "final dividend of Rs 1 per share"}]}})
    facts = [Computed("Balance sheet Q3FY25: borrowings ₹938.96 Cr")]
    results_card.build(out, tagged, "Ahluwalia Contracts (India) Limited", facts=facts, rich=True)
    texts = [f.text for f in out.card.what_happened]
    assert "Finance cost rose to ₹18.85 Cr." in texts and "Paid a final dividend of ₹12.34 Cr." in texts
    assert not any(t.startswith(("EBITDA for the quarter", "Borrowings rose")) for t in texts)


def test_a_zero_eps_beside_a_profit_is_a_filler():
    """Ahluwalia Contracts Q3FY24: EPS 0 beside a ₹70.24 Cr profit (screener 10.55; referee 26 Oct 2026)."""
    from bse_intel.xbrl import eps_fillers

    values = {("pat", "Q3FY24"): 70.24, ("eps", "Q3FY24"): 0.0, ("pat", "Q4FY24"): 0.4, ("eps", "Q4FY24"): 0.0}
    assert eps_fillers(values) == 1
    assert ("eps", "Q3FY24") not in values and values[("eps", "Q4FY24")] == 0.0   # a profit under ₹1 Cr: a 0 EPS can be real


def test_eps_keeps_its_filed_sign_when_the_two_profits_disagree():
    """Alembic Q4FY26: profit ₹67.13 Cr, owners' share -33.87, filed EPS 2.61 (screener 2.61)."""
    from bse_intel.xbrl import eps_signs

    values = {("pat", "Q4FY26"): 67.13, ("pat_owners", "Q4FY26"): -33.87, ("eps", "Q4FY26"): 2.61}
    assert eps_signs(values) == 0 and values[("eps", "Q4FY26")] == 2.61
