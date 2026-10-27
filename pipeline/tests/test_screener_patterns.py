"""The three patterns of the screener cross-check run 40500186896 (27 Oct 2026): small_gap, the two tax % classes, steady_older,
and screener's rule 16 (profit from associates) as views of our PBT and other income."""

from bse_intel import screener_crosscheck as sc
from bse_intel.periods import quarter_index
from bse_intel.screener_fill import parse_full

from test_screener_six_lines import Q, entry, figs, table

PERIODS = (("Mar", 2024), ("Jun", 2024), ("Sep", 2024), ("Dec", 2024), ("Mar", 2025))
QUARTERS = ("Q4FY24", "Q1FY25", "Q2FY25", "Q3FY25", "Q4FY25")


def run_one(metrics, rows):
    d = {"financial_metrics": [entry(m, v) for m, v in {"revenue": 100.0, **metrics}.items()], "balance_sheet": [], "sector": "Demo"}
    return sc.compare_company(d, {"CONSOLIDATED": parse_full(table(rows))}, "1", "DEMO")


def klass(result, metric, period=Q):
    return next(p for p in result["six_pairs"] if p["metric"] == metric and p["period"] == period)["class"]


def run_many(metric, ours, theirs, label):
    d = {"financial_metrics": [entry(m, v, q) for m, vs in (("revenue", [100.0 * (i + 1) for i in range(5)]), (metric, ours))
                               for i, (q, v) in enumerate(zip(QUARTERS, vs))], "balance_sheet": [], "sector": "Demo"}
    page = parse_full(table([("Sales", [100 * (i + 1) for i in range(5)]), (label, theirs)], periods=PERIODS))
    return sc.compare_company(d, {"CONSOLIDATED": page}, "1", "DEMO")


def classes(result, metric):
    return [p["class"] for p in sorted(result["six_pairs"], key=lambda p: quarter_index(p["period"])) if p["metric"] == metric]


# --- 1. small_gap ------------------------------------------------------------------------------------------------

def test_small_gap_is_its_own_class_at_nine_tenths_of_a_crore_not_at_one_point_two():
    # screener prints whole crore: ours 10.1 against 11 is 0.9 apart, ours 9.8 against 11 is 1.2 apart
    assert klass(run_one({"finance_cost": 10.1}, [("Interest", [11])]), "finance_cost") == "small_gap"
    assert klass(run_one({"finance_cost": 9.8}, [("Interest", [11])]), "finance_cost") == "mismatch"
    assert klass(run_one({"finance_cost": 11.3}, [("Interest", [11])]), "finance_cost") == "match"     # inside rounding stays a match
    # 1% of screener's value also counts: 150 Cr off by 1.4
    assert klass(run_one({"pbt": 1000.0}, [("Profit before tax", [1009])]), "pbt") == "small_gap"
    assert klass(run_one({"pbt": 1000.0}, [("Profit before tax", [1011])]), "pbt") == "mismatch"


def test_a_screener_view_rule_comes_before_small_gap_and_tax_pct_has_no_small_gap():
    page = [("Other Income", [4582])]
    assert klass(run_one({"other_income": 635.78, "exceptional_items": 3945.73}, page), "other_income") == \
        "matches_screener_view:exceptional_in_other_income"
    rows = [("Profit before tax", [100]), ("Tax %", [26])]
    assert klass(run_one({"pbt": 100.0, "tax_expense": 24.0}, rows), "tax_pct") == "mismatch"


# --- 2. tax % ------------------------------------------------------------------------------------------------------

def test_63moons_tax_sign_on_a_loss():
    # Q4FY24: our tax -36.2 over our pbt -32.9 = +110, screener divides by |pbt| and prints -110
    rows = [("Profit before tax", [-33]), ("Tax %", [-110])]
    result = run_one({"pbt": -32.9, "tax_expense": -36.2}, rows)
    assert klass(result, "tax_pct") == "tax_sign_on_loss" and klass(result, "pbt") == "match"
    assert next(p for p in result["six_pairs"] if p["metric"] == "tax_pct")["memory_value"] > 109
    assert klass(run_one({"pbt": -32.9, "tax_expense": -36.2}, [("Profit before tax", [-33]), ("Tax %", [-80])]), "tax_pct") == "mismatch"


def test_a_tax_pct_gap_that_is_the_pbt_gap_carried_over():
    # our tax 25 on our pbt 100 is 25%; screener's pbt is 120 and its tax % 21 = 25 / 120
    rows = [("Profit before tax", [120]), ("Tax %", [21])]
    result = run_one({"pbt": 100.0, "tax_expense": 25.0}, rows)
    assert klass(result, "pbt") == "mismatch" and klass(result, "tax_pct") == "tax_follows_pbt"
    # the PBT matches: the tax % gap is not explained by it
    same = run_one({"pbt": 120.0, "tax_expense": 25.0}, [("Profit before tax", [120]), ("Tax %", [21])])
    assert klass(same, "tax_pct") == "match"
    other = run_one({"pbt": 120.0, "tax_expense": 40.0}, [("Profit before tax", [120]), ("Tax %", [21])])
    assert klass(other, "tax_pct") == "mismatch"
    # current + deferred is used when there is no total; a figure is never back-derived from a percent
    cd = run_one({"pbt": 100.0, "current_tax": 20.0, "deferred_tax": 5.0}, rows)
    assert klass(cd, "tax_pct") == "tax_follows_pbt"
    assert klass(run_one({"pbt": 100.0}, rows), "pbt") == "mismatch"


def test_the_tax_pct_tolerance_widens_to_one_and_a_half_points_under_ten_crore_of_pbt():
    rows = [("Profit before tax", [8]), ("Tax %", [24])]
    # tax 2 / 8 = 25.0 would be close; use pbt 5: 1.2 / 8 = 15 against 16.4 (1.4 apart) passes, 1 point would not
    rows = [("Profit before tax", [8]), ("Tax %", [16])]
    assert klass(run_one({"pbt": 5.0, "tax_expense": 1.3}, rows), "tax_pct") == "tax_follows_pbt"      # 16.25
    assert klass(run_one({"pbt": 5.0, "tax_expense": 1.0}, rows), "tax_pct") == "mismatch"           # 12.5


# --- 3. steady_older -----------------------------------------------------------------------------------------------

def test_a_steady_older_run_with_every_later_quarter_matching():
    result = run_many("ebitda", [100.0] * 5, [90, 90, 90, 100, 100], "Operating Profit")
    assert classes(result, "ebitda") == ["steady_older"] * 3 + ["match"] * 2
    first = next(p for p in result["six_pairs"] if p["period"] == "Q4FY24")
    assert "x0.900" in first["note"] and "3 quarters" in first["note"]


def test_a_run_whose_later_quarter_does_not_match_stays_a_mismatch():
    result = run_many("ebitda", [100.0] * 5, [90, 90, 90, 100, 80], "Operating Profit")
    assert classes(result, "ebitda") == ["mismatch"] * 3 + ["match", "mismatch"]
    # a run that reaches the latest quarter has no later quarter to show it ended: not older
    assert classes(run_many("ebitda", [100.0] * 5, [100, 100, 90, 90, 90], "Operating Profit"), "ebitda") == \
        ["match"] * 2 + ["mismatch"] * 3
    # two quarters are not a run; a ratio off by under 3% from 1 is not a steady gap; ratios spread over 3% are not steady
    assert classes(run_many("ebitda", [100.0] * 5, [90, 90, 100, 100, 100], "Operating Profit"), "ebitda")[:2] == ["mismatch"] * 2
    assert "steady_older" not in classes(run_many("ebitda", [100.0] * 5, [98, 98, 98, 100, 100], "Operating Profit"), "ebitda")
    assert "steady_older" not in classes(run_many("ebitda", [100.0] * 5, [90, 80, 95, 100, 100], "Operating Profit"), "ebitda")


def test_steady_older_also_credits_revenue_and_counts_per_line():
    d = {"financial_metrics": [entry("revenue", 100.0 * (i + 1), q) for i, q in enumerate(QUARTERS)], "balance_sheet": [], "sector": "Demo"}
    page = parse_full(table([("Sales", [110, 220, 330, 400, 500])], periods=PERIODS))
    result = sc.compare_company(d, {"CONSOLIDATED": page}, "1", "DEMO")
    assert [p["class"] for p in result["pairs"] if p["metric"] == "revenue"].count("steady_older") == 3
    out = sc.summarise([run_many("ebitda", [100.0] * 5, [90, 90, 90, 100, 100], "Operating Profit")], "2026-10-27")
    assert out["six_by_class"]["ebitda"]["steady_older"] == 3 and out["six_by_class"]["ebitda"]["match"] == 2
    assert "steady_older 3" in sc.render(out)
    assert "small_gap" in sc.to_markdown(out, "2026-10-27")


# --- 4. rule 16: profit from associates -----------------------------------------------------------------------------

def test_pbt_with_the_associates_share_is_screeners_view():
    # our pbt is the taxonomy's, without the associates' share of 30; screener's holds it
    result = run_one({"pbt": 100.0, "share_associates": 30.0}, [("Profit before tax", [130])])
    pair = next(p for p in result["six_pairs"] if p["metric"] == "pbt")
    assert pair["class"] == "matches_screener_view:associates_in_pbt" and "130" in pair["note"]
    assert klass(run_one({"pbt": 100.0}, [("Profit before tax", [130])]), "pbt") == "mismatch"
    assert klass(run_one({"pbt": 100.0, "share_associates": 0.0}, [("Profit before tax", [130])]), "pbt") == "mismatch"
    assert klass(run_one({"pbt": 100.0, "share_associates": 0.8}, [("Profit before tax", [101])]), "pbt") == "small_gap"
    # a share that is not at least 1 Cr is not credited; a gap inside twice the tolerance is not either
    assert "pbt" not in sc.screener_view({}, figs({"pbt": 100.0, "share_associates": 0.9}), Q)
    assert klass(run_one({"pbt": 100.0, "share_associates": 3.0}, [("Profit before tax", [101])]), "pbt") == "small_gap"


def test_other_income_with_the_associates_share_alone_or_with_the_exceptional_items():
    alone = run_one({"other_income": 10.0, "share_associates": 30.0}, [("Other Income", [40])])
    assert klass(alone, "other_income") == "matches_screener_view:associates_in_other_income"
    both = run_one({"other_income": 10.0, "share_associates": 30.0, "exceptional_items": 20.0}, [("Other Income", [60])])
    pair = next(p for p in both["six_pairs"] if p["metric"] == "other_income")
    assert pair["class"] == "matches_screener_view:associates_in_other_income" and "60" in pair["note"]
    exceptional_only = run_one({"other_income": 10.0, "share_associates": 30.0, "exceptional_items": 20.0}, [("Other Income", [30])])
    assert klass(exceptional_only, "other_income") == "matches_screener_view:exceptional_in_other_income"
    assert klass(run_one({"other_income": 10.0, "share_associates": 30.0}, [("Other Income", [50])]), "other_income") == "mismatch"
    views = sc.screener_views({}, figs({"other_income": 10.0, "share_associates": 30.0, "exceptional_items": 20.0}), Q)
    assert [rule for _, rule in views["other_income"]] == ["exceptional_in_other_income", "associates_in_other_income",
                                                            "associates_in_other_income"]
    assert sc.screener_view({}, figs({"other_income": 10.0, "share_associates": 30.0}), Q)["other_income"][0] == 40.0


def test_steady_older_needs_two_later_matches_and_still_goes_to_the_referee():
    # blind review, 27 Oct 2026: one later quarter is thin evidence; and a steady run can be our error (a wrong basis)
    assert "steady_older" not in classes(run_many("ebitda", [100.0] * 4, [90, 90, 90, 100], "Operating Profit"), "ebitda")
    from bse_intel import screener_xbrl_referee as sx
    assert "steady_older" not in sx.NOT_PAIRS


def test_an_associates_share_under_5_cr_does_not_explain_other_income():
    # shuffle test, run 40505771830: a 1 Cr floor let another company's share close 6.6% as many gaps as the real ones
    small = run_one({"other_income": 10.0, "share_associates": 3.0}, [("Other Income", [13])])
    assert klass(small, "other_income") != "matches_screener_view:associates_in_other_income"
    pbt = run_one({"pbt": 100.0, "share_associates": 3.0}, [("Profit before tax", [103])])
    assert klass(pbt, "pbt") == "matches_screener_view:associates_in_pbt"   # the PBT rule keeps its 1 Cr floor (4.3%)


def test_a_small_associates_share_with_no_exceptional_items_leaves_no_empty_view():
    # run 40512034352 crashed (IndexError in screener_view): a 3 Cr share, no exceptional items, an empty list left behind
    f = figs({"other_income": 10.0, "share_associates": 3.0, "pbt": 100.0})
    assert "other_income" not in sc.screener_views({}, f, Q)
    assert "other_income" not in sc.screener_view({}, f, Q) and "pbt" in sc.screener_view({}, f, Q)
