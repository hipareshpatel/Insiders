"""A results file tagged at a hundredth (or a thousandth) of its value: IMPAL Q1FY27 (28 Oct 2026, xbrl-key disagreements).

India Motor Parts & Accessories' Q1FY27 standalone file tags revenue 23,429,000 rupees (the statement's 234.29 crore typed as
lakh), so memory held revenue ₹2.34 Cr, PAT ₹0.22 Cr and EPS ₹17.38 beside quarters of ₹190-231 Cr, ₹16-33 Cr and ₹13-27. The
slip test needs the revenue and the share count (profit / EPS) to be off by the same power of ten, and it read the share count
as unknown whenever the profit was under ₹0.5 Cr, which a file at a hundredth of its value always is.
"""
from pathlib import Path

from bse_intel import xbrl
from bse_intel.models import BalanceSheet, FinancialMetric

FIXTURES = Path(__file__).parent / "fixtures"

# memory's IMPAL quarters (consolidated set, standalone-only company), 28 Oct 2026: revenue, pat, eps
IMPAL = {"Q1FY25": (197.89, 20.84, 16.70), "Q2FY25": (190.40, 22.60, 18.11), "Q3FY25": (211.67, 16.30, 13.06),
         "Q4FY25": (188.85, 23.93, 19.18), "Q1FY26": (196.69, 20.41, 16.35), "Q2FY26": (198.71, 25.50, 20.44),
         "Q3FY26": (230.99, 17.18, 13.77), "Q4FY26": (210.72, 33.46, 26.81)}
# the statement's Q1FY27 column (crore), and what the file's 23,429,000-rupee-style figures come to
PRINTED = {"revenue": 234.29, "total_income": 243.96, "other_income": 9.67, "total_expenses": 216.52, "pbt": 27.44,
           "tax_expense": 5.74, "pat": 21.70}
RAW = {"revenue": 2.3429, "total_income": 2.4396, "other_income": 0.0967, "total_expenses": 2.1652, "pbt": 0.2744,
       "tax_expense": 0.0574, "pat": 0.2170}


def _history():
    return [m for q, (revenue, pat, eps) in IMPAL.items()
            for m in (FinancialMetric(metric="revenue", period=q, value=revenue),
                      FinancialMetric(metric="pat", period=q, value=pat),
                      FinancialMetric(metric="eps", period=q, value=eps, unit="INR"))]


def _impal(scale=0.01, with_exact=True):
    """The Q1FY27 file as parsed: every crore amount rounded to two decimals at a hundredth of its value."""
    metrics = [FinancialMetric(metric=name, period="Q1FY27", value=round(value * scale, 2)) for name, value in PRINTED.items()]
    metrics.append(FinancialMetric(metric="eps", period="Q1FY27", value=17.38, unit="INR"))
    extra = [FinancialMetric(metric="pat_minority", period="Q1FY27", value=round(0.5 * scale, 2))]
    result = xbrl.XbrlResult(kind="RESULTS", basis="STANDALONE", period="Q1FY27", metrics=metrics, memory_extra=extra,
                             balance_sheet=BalanceSheet(period="Q1FY27", net_worth_cr=round(2308.17 * scale, 2), cash_cr=0.03),
                             balance_prior=BalanceSheet(period="Q4FY26", net_worth_cr=round(2290.0 * scale, 2)))
    if with_exact:
        result.exact_values = {(name, "Q1FY27"): value for name, value in RAW.items()}
        result.exact_values[("pat_minority", "Q1FY27")] = 0.5 * scale
        result.balance_exact = BalanceSheet(period="Q1FY27", net_worth_cr=23.0817, cash_cr=0.0296)
        result.balance_prior_exact = BalanceSheet(period="Q4FY26", net_worth_cr=22.9012)
    return result


def _printed_revenue(result, metric, corrected):
    """What slip_check.PdfCheck answers: the PDF text layer's revenue for the column, to its two decimals."""
    return (abs(corrected - PRINTED["revenue"]) <= 0.0051, f"PDF prints {PRINTED['revenue']}")


def test_impal_a_hundredth_of_its_value_is_a_slip_even_when_its_profit_is_under_half_a_crore():
    result = _impal()
    own = {m.metric: m.value for m in result.metrics}
    assert own["revenue"] == 2.34 and own["pat"] == 0.22 and own["eps"] == 17.38   # as memory held them
    assert xbrl.scale_slip(result, _history()) == 2


def test_impal_is_put_right_to_the_digit_from_the_files_own_unrounded_figures():
    result = _impal()
    asked = []

    def verify(r, metric, corrected):
        asked.append((metric, corrected))
        return _printed_revenue(r, metric, corrected)

    assert xbrl.fix_scale(result, _history(), "590065", verify=verify) == 2
    assert asked == [("revenue", 234.29)], "the PDF is asked for the unrounded figure times 100, not 2.34 x 100 = 234.00"
    figures = {m.metric: m.value for m in result.metrics}
    assert figures == {**PRINTED, "eps": 17.38}, "every amount moved together, the per-share figure did not"
    assert result.memory_extra[0].value == 0.5, "the memory-only minority profit moves with the file"
    assert result.balance_sheet.net_worth_cr == 2308.17 and result.balance_sheet.cash_cr == 2.96
    assert result.balance_prior.net_worth_cr == 2290.12, "the balance sheet's earlier date moves too"
    assert not result.slip_held


def test_without_the_pdfs_proof_the_slip_is_not_corrected_and_the_file_is_held():
    for verify, unsure in ((None, False), (lambda r, m, c: (False, "PDF prints 2.34 Cr"), False),
                           (lambda r, m, c: (None, "no PDF read"), True)):
        result = _impal()
        assert xbrl.fix_scale(result, _history(), "590065", verify=verify) == 0
        assert {m.metric: m.value for m in result.metrics}["revenue"] == 2.34, "nothing multiplied"
        assert result.slip_held.startswith("unit slip 10^2") and result.slip_unsure is unsure


def test_a_slip_by_a_thousand_is_found_and_ten_still_is():
    one_in_a_thousand = xbrl.XbrlResult(kind="RESULTS", basis="STANDALONE", period="Q1FY27", metrics=[
        FinancialMetric(metric="revenue", period="Q1FY27", value=0.23), FinancialMetric(metric="pat", period="Q1FY27", value=0.02),
        FinancialMetric(metric="eps", period="Q1FY27", value=17.38, unit="INR")],
        exact_values={("revenue", "Q1FY27"): 0.23429, ("pat", "Q1FY27"): 0.0217})
    assert xbrl.scale_slip(one_in_a_thousand, _history()) == 3
    assert xbrl.fix_scale(one_in_a_thousand, _history(), "590065", verify=lambda r, m, c: (abs(c - 234.29) < 0.0051, "")) == 3
    assert {m.metric: m.value for m in one_in_a_thousand.metrics} == {"revenue": 234.29, "pat": 21.7, "eps": 17.38}
    ten = xbrl.XbrlResult(kind="RESULTS", basis="STANDALONE", period="Q1FY27", metrics=[
        FinancialMetric(metric="revenue", period="Q1FY27", value=23.43), FinancialMetric(metric="pat", period="Q1FY27", value=2.17),
        FinancialMetric(metric="eps", period="Q1FY27", value=17.38, unit="INR")])
    assert xbrl.scale_slip(ten, _history()) == 1


def test_a_real_fall_with_the_same_shares_is_not_a_slip():
    """Revenue down a hundredfold but profit and EPS still imply the same shares: a demerger, not a unit."""
    shrunk = xbrl.XbrlResult(kind="RESULTS", basis="STANDALONE", period="Q1FY27", metrics=[
        FinancialMetric(metric="revenue", period="Q1FY27", value=2.34), FinancialMetric(metric="pat", period="Q1FY27", value=0.21),
        FinancialMetric(metric="eps", period="Q1FY27", value=0.17, unit="INR")])
    assert xbrl.scale_slip(shrunk, _history()) == 0
    same_shares = xbrl.XbrlResult(kind="RESULTS", basis="STANDALONE", period="Q1FY27", metrics=[
        FinancialMetric(metric="revenue", period="Q1FY27", value=2.34), FinancialMetric(metric="pat", period="Q1FY27", value=21.7),
        FinancialMetric(metric="eps", period="Q1FY27", value=17.38, unit="INR")])
    assert xbrl.scale_slip(same_shares, _history()) == 0, "profit and EPS say the unit is right"


def test_history_quarters_with_a_profit_of_a_few_paise_do_not_move_the_yardstick():
    """History is stored and rounded to 0.01 with no unrounded figure: a profit of 0.04 Cr is 25% rounding noise in the share count
    it implies. The file being checked keeps the 0.001 floor (its figures are unrounded); history needs 0.05."""
    noisy = {"Q1FY25", "Q2FY25", "Q3FY25", "Q4FY25", "Q1FY26"}
    history = [m for m in _history() if m.period not in noisy or m.metric == "revenue"]
    history += [FinancialMetric(metric=name, period=q, value=value, unit=unit)
                for q in noisy for name, value, unit in (("pat", 0.04, "INR_CR"), ("eps", 0.8, "INR"))]
    assert xbrl._shares({"pat": 0.04, "eps": 0.8}) is not None, "under the file's own floor this would count"
    assert xbrl._shares({"pat": 0.04, "eps": 0.8}, xbrl._SHARES_MIN_PAT_STORED) is None
    assert xbrl.scale_slip(_impal(), history) == 2, "the five noisy quarters are left out; the three real ones decide"
    assert xbrl._shares({"pat": 0.06, "eps": 0.8}, xbrl._SHARES_MIN_PAT_STORED) == 0.075


def test_after_a_correction_no_unscaled_copy_is_left_to_read():
    result = _impal()
    assert xbrl.fix_scale(result, _history(), "590065", verify=_printed_revenue) == 2
    assert result.balance_exact is None and result.balance_prior_exact is None
    assert result.exact_values[("revenue", "Q1FY27")] == 234.29, "the unrounded figures moved with the rest"


def test_a_file_in_the_wrong_unit_whose_neighbour_is_in_line_is_left_alone():
    result = _impal()
    neighbour = [FinancialMetric(metric="revenue", period="Q4FY26", value=2.4), FinancialMetric(metric="revenue", period="Q4FY25", value=2.5)]
    history = [m for m in _history() if m.period not in ("Q4FY26", "Q4FY25")] + neighbour
    assert xbrl.scale_slip(result, history) == 0, "the quarter just before it is in the same small unit: not a slip against it"


def test_a_parsed_file_keeps_its_unrounded_figures_for_a_later_correction():
    result = xbrl.parse((FIXTURES / "bse_main_ind_as_532811_q2fy25.xml").read_bytes())
    assert result.exact_values and result.balance_exact is not None
    for m in result.metrics:
        if m.unit == "INR_CR":
            assert abs(result.exact_values[(m.metric, m.period)] - m.value) <= 0.0051
    assert any(abs(v - round(v, 2)) > 1e-9 for v in result.exact_values.values()), "not the rounded figures again"
    assert abs(result.balance_exact.total_assets_cr - result.balance_sheet.total_assets_cr) <= 0.0051


def test_impals_slipped_figures_are_on_the_known_wrong_list_and_the_right_ones_are_not():
    """The stored figures come out with memory-drop-known-wrong, and a seed that cannot read the PDF cannot write them again;
    the printed figures for the same keys are never held back."""
    from bse_intel import known_wrong as kw

    for metric, printed in PRINTED.items():
        wrong = round(printed * 0.01, 2)
        assert kw.listed("590065", metric, "Q1FY27", wrong, "STANDALONE"), metric
        assert not kw.listed("590065", metric, "Q1FY27", printed, "STANDALONE"), f"the printed {metric} is never held back"
        assert not kw.listed("590065", metric, "Q4FY26", wrong, "STANDALONE"), "another quarter is another figure"
    assert not kw.listed("590065", "eps", "Q1FY27", 17.38, "STANDALONE"), "the file's EPS is right"
    entry = kw.listed("590065", "revenue", "Q1FY27", 2.34, "STANDALONE")
    assert entry.right == 234.29 and "page 2" in entry.evidence
