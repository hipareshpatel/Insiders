"""F196: two wrong memory figures found by the Tijori referee (26 Oct 2026), both from NSE's own results files."""
from pathlib import Path

from bse_intel import screener_crosscheck as sc
from bse_intel import xbrl
from bse_intel.models import FinancialMetric
from bse_intel.screener_xbrl_referee import CompanyFiles

FIXTURES = Path(__file__).parent / "fixtures"


def _q(period, revenue, pat, eps):
    return [FinancialMetric(metric="revenue", period=period, value=revenue),
            FinancialMetric(metric="pat", period=period, value=pat),
            FinancialMetric(metric="eps", period=period, value=eps, unit="INR")]


def test_dolphin_growth_with_a_split_is_not_a_scale_slip():
    """Dolphin Offshore grew from ~2 to 40 crore a quarter and its share count rose tenfold: its Q4FY24 file (19,478,000
    rupees of revenue, 1.95 crore) passed the slip test against the later quarters and memory held 19.5 crore. Its
    neighbour quarter (Q3FY24, 1.78) shows the file is in the right unit."""
    result = xbrl.parse((FIXTURES / "nse_dolphin_q4fy24_cons.xml").read_bytes())
    assert result.period == "Q4FY24"
    assert {m.metric: m.value for m in result.metrics if m.period == "Q4FY24"}["revenue"] == 1.95
    later = [m for q in (_q("Q1FY25", 8.34, 7.55, 1.89), _q("Q2FY25", 16.73, 12.92, 3.23), _q("Q3FY25", 28.5, 15.56, 3.89),
                         _q("Q4FY25", 20.44, 10.45, 2.61), _q("Q1FY26", 16.44, 11.33, 2.83)) for m in q]
    near = [m for q in (_q("Q2FY24", 2.05, 3.53, 11.17), _q("Q3FY24", 1.78, 0.45, 1.34)) for m in q]
    assert xbrl.scale_slip(result, [*near, *later]) == 0
    assert xbrl.fix_scale(result, [*near, *later], "522261") == 0
    assert {m.metric: m.value for m in result.metrics if m.period == "Q4FY24"}["revenue"] == 1.95


def test_an_isolated_slip_is_still_put_right():
    """A quarter ten times off both neighbours is the Jubilant class, still corrected."""
    slipped = xbrl.XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period="Q4FY24", metrics=_q("Q4FY24", 175.86, -6.18, -3.69))
    others = [*_q("Q1FY24", 1586.9, 60.0, 3.77), *_q("Q2FY24", 1680.3, 62.1, 3.90), *_q("Q3FY24", 1677.1, 66.4, 4.17),
              *_q("Q1FY25", 1731.7, 481.8, 30.25)]
    assert xbrl.scale_slip(slipped, others) == 1


def test_a_lenders_zero_interest_earned_is_not_a_revenue():
    """ICICI Prudential AMC files on the NBFC template: InterestEarned 0, revenue from operations 1,564.22 crore. When memory's
    machine-tagged set has no revenue for the quarter, the check read the interest-earned 0 as its revenue."""
    result = xbrl.parse((FIXTURES / "nse_iciciamc_q1fy27_nbfc.xml").read_bytes())
    now = {m.metric: m.value for m in result.metrics if m.period == "Q1FY27"}
    assert now["revenue"] == 1564.22 and now["interest_earned"] == 0
    zero = {("interest_earned", "Q1FY27"): {"value": 0.0}}
    assert sc._ours(zero, True, "revenue", "Q1FY27") is None, "a 0 never stands in for not found"
    assert sc._ours({**zero, ("revenue", "Q1FY27"): {"value": 1564.22}}, True, "revenue", "Q1FY27")["value"] == 1564.22
    bank = {("interest_earned", "Q1FY27"): {"value": 812.5}}
    assert sc._ours(bank, True, "revenue", "Q1FY27")["value"] == 812.5, "a bank's interest earned is its top line"


def test_the_referee_does_not_take_a_zero_interest_earned_as_official_revenue():
    parsed = xbrl.XbrlResult("RESULTS", "STANDALONE", "Q1FY27",
                             [FinancialMetric(metric="interest_earned", period="Q1FY27", value=0.0)], template="NBFC")
    files = CompanyFiles.__new__(CompanyFiles)
    files.file_for = lambda quarter: (parsed, "f.xml", "")
    assert "value" not in files.official("Q1FY27", "revenue")
    parsed.metrics.append(FinancialMetric(metric="revenue", period="Q1FY27", value=1564.22))
    assert files.official("Q1FY27", "revenue")["value"] == 1564.22
