"""Which parts of screener's treatment the facts may supply, and how (screener_parts.py; independent review, 28 Oct 2026): a part is
used only when the filer tagged it and it is at or above a floor; all tagged parts are applied together, as screener's formula
does, never the mix that fits best; each item is counted once (a total or its parts, an element or breakdown rows, never both);
a right-of-use asset is added only when it is demonstrably outside memory's fixed assets."""

from __future__ import annotations

import itertools
import random
from datetime import date

import pytest

from bse_intel import screener_crosscheck as sc
from bse_intel import screener_parts as sp
from bse_intel import xbrl_facts

CR = 10_000_000
YEAR_END = date(2026, 3, 31)
CONTEXTS = {
    "Q": {"s": "2026-01-01", "e": "2026-03-31", "m": 3},
    "I": {"i": "2026-03-31"},
    "R1": {"s": "2026-01-01", "e": "2026-03-31", "m": 3, "d": {"in-bse-fin:DetailsOfOtherExpensesAxis": "Row1Member"}},
    "L1": {"i": "2026-03-31", "d": {"in-bse-fin:DetailsOfOtherCurrentFinancialLiabilitiesAxis": "Row1Member"}},
    "L2": {"i": "2026-03-31", "d": {"in-bse-fin:DetailsOfOtherNoncurrentFinancialLiabilitiesAxis": "Row2Member"}},
}


def money(name, ctx, crore):
    return [name, ctx, "INR", crore * CR, -5]


def text(name, ctx, value):
    return [name, ctx, None, value, None]


def facts(*rows):
    return xbrl_facts.Facts({"contexts": CONTEXTS, "units": {"INR": "MONEY", "shares": "SHARES"}, "facts": [list(r) for r in rows]})


def parts(*rows):
    return {k: v[0] for k, v in sp.balance_parts(facts(*rows), YEAR_END).items()}


# --- the floor and all the parts together ---------------------------------------------------------------------------------

def test_a_part_is_used_only_at_or_above_its_floor():
    assert sp.floor(330.0) == 1.0 and sp.floor(10_000.0) == 20.0           # 1 Cr, or 0.2% of the line
    assert sp.usable({"a": 0.4, "b": 1.0, "c": 25.0}, 330.0) == {"b": 1.0, "c": 25.0}
    assert sp.usable({"a": 15.0, "b": 25.0}, 10_000.0) == {"b": 25.0}
    assert sp.additive_views("borrowings", 330.0, {"lease_liabilities": 0.4}, ("lease_liabilities", "current_maturities")) == []


def fa_views(ours, **found):
    """The fixed-assets views of our figure with parts given as {name: crore} (value and a source label as the facts give them)."""
    return lambda: sc._bs_views({}, "fixed_assets", ours, {k: (v, "e") for k, v in found.items()}, False)


def test_all_the_tagged_parts_are_applied_together_never_the_subset_that_fits():
    order = ("intangibles", "right_of_use")
    assert sp.additive_views("fixed_assets", 700.0, {"intangibles": 60.0, "right_of_use": 30.0}, order) == \
        [(790.0, "fixed_assets_plus_intangibles_right_of_use")]                     # one view: screener's own sum
    cls, _ = sc.classify_balance("fixed_assets", 700.0, 760.0, [], fa_views(700.0, intangibles=60.0, right_of_use=30.0), False)
    assert cls == "unexplained_larger"       # 760 = 700 + the intangibles alone: not a match, the right-of-use asset was tagged too
    cls, _ = sc.classify_balance("fixed_assets", 700.0, 790.0, [], fa_views(700.0, intangibles=60.0, right_of_use=30.0), False)
    assert cls == "matches_screener_view:fixed_assets_plus_intangibles_right_of_use"
    # a part under the floor is left out of the sum, not a reason to refuse the others
    cls, _ = sc.classify_balance("fixed_assets", 700.0, 760.0, [], fa_views(700.0, intangibles=60.0, right_of_use=0.5), False)
    assert cls == "matches_screener_view:fixed_assets_plus_intangibles"


def test_other_companies_parts_do_not_close_gaps_beyond_chance():
    """Shuffle test: each company's gap (screener = ours + its own intangibles and right-of-use assets) set against ANOTHER
    company's parts. The real parts close the gaps; the shuffled ones close only what the tolerance lets by chance, and a fraction
    of what searching the mixes for a fit would (the old way: each alone, and both)."""
    rnd = random.Random(28)
    n = 600
    cos = [(rnd.uniform(500, 5000), rnd.uniform(12, 120), rnd.uniform(12, 120)) for _ in range(n)]
    real = shuffled = searched = 0
    for i, (ours, intangibles, rou) in enumerate(cos):
        theirs = float(round(ours + intangibles + rou))
        real += sc.classify_balance("fixed_assets", ours, theirs, [], fa_views(ours, intangibles=intangibles, right_of_use=rou),
                                    False)[0].startswith(sc.VIEW)
        _, other_intangibles, other_rou = cos[(i + 101) % n]
        cls, _ = sc.classify_balance("fixed_assets", ours, theirs, [], fa_views(ours, intangibles=other_intangibles, right_of_use=other_rou),
                                     False)
        shuffled += cls.startswith(sc.VIEW)
        if cls != "match" and sc._apart(ours, theirs, "money"):
            searched += any(sc.view_close(ours + sum(c), theirs)
                            for size in (1, 2) for c in itertools.combinations((other_intangibles, other_rou), size))
        elif cls.startswith(sc.VIEW) or cls == "match":
            searched += 1
    assert real >= 0.98 * n                                        # screener's own sums are explained (the rest are gaps inside 2 tolerances)
    assert shuffled / n < 0.03
    assert shuffled < searched * 0.6 and searched / n > shuffled / n * 1.5


def test_a_view_closes_a_gap_only_within_a_crore_and_a_half_or_five_hundredths_of_a_percent():
    assert sc.view_close(149_080.40, 149_080.0)                      # BPCL Q2FY27: 157,817.93 - 8,737.53 against 1,49,080
    assert sc.view_close(100.0, 101.4) and not sc.view_close(100.0, 101.6)
    assert sc.view_close(149_080.0, 149_150.0) and not sc.view_close(149_080.0, 149_160.0)        # 0.05% of 1,50,000 is 75 Cr
    assert sc._close(150_000.0, 150_600.0, "money") and not sc.view_close(150_000.0, 150_600.0)   # a plain match keeps 0.5%
    # a part that would close the gap at 0.5% (150,000 + 400 against 150,600) closes nothing as a view
    cls, _ = sc.classify_balance("borrowings", 150_000.0, 150_600.0, [], lambda: [(150_400.0, "borrowings_plus_lease_liabilities")], False)
    assert cls == "match"
    cls, _ = sc.classify_balance("borrowings", 150_000.0, 153_000.0, [], lambda: [(150_400.0, "borrowings_plus_lease_liabilities")], False)
    assert cls == "unexplained_larger"
    assert sc.view_close(9.52, 9.52, "eps") and not sc.view_close(9.50, 9.60, "eps")                # EPS keeps its own tolerance


def test_a_lease_maturity_analysis_is_not_a_balance_but_a_current_maturity_of_a_lease_is():
    analysis = (money("LeaseLiabilitiesMaturityAnalysis", "I", 90.0), money("LeaseLiabilitiesMaturityLessThanOneYear", "I", 20.0),
                money("LeaseLiabilitiesMaturities", "I", 30.0))
    assert "lease_liabilities" not in parts(*analysis)
    got = parts(money("LeaseLiabilitiesNoncurrent", "I", 40.0), money("CurrentMaturitiesOfLeaseLiabilities", "I", 8.0), *analysis)
    assert got["lease_liabilities"] == pytest.approx(48.0)            # the analysis adds nothing, the current maturity stays


# --- each item once ----------------------------------------------------------------------------------------------------------

def test_a_lease_total_is_taken_alone_never_with_its_parts():
    got = parts(money("LeaseLiabilities", "I", 50.0), money("LeaseLiabilitiesNoncurrent", "I", 30.0), money("LeaseLiabilitiesCurrent", "I", 20.0))
    assert got["lease_liabilities"] == pytest.approx(50.0)                    # not 100


def test_current_plus_non_current_when_there_is_no_total():
    got = parts(money("LeaseLiabilitiesNoncurrent", "I", 30.0), money("LeaseLiabilitiesCurrent", "I", 20.0))
    assert got["lease_liabilities"] == pytest.approx(50.0)


def test_an_element_is_never_added_to_breakdown_rows_for_the_same_item():
    rows = (text("DescriptionOfOtherCurrentFinancialLiabilities", "L1", "Lease liabilities - current"),
            money("OtherCurrentFinancialLiabilities", "L1", 10.0))
    both = sp.balance_parts(facts(money("LeaseLiabilitiesNoncurrent", "I", 40.0), *rows), YEAR_END)["lease_liabilities"]
    assert both[0] == pytest.approx(40.0) and both[1].startswith("element:")          # the element only, not 50
    only_rows = sp.balance_parts(facts(*rows, text("DescriptionOfOtherNoncurrentFinancialLiabilities", "L2", "Lease liabilities"),
                                       money("OtherNoncurrentFinancialLiabilities", "L2", 40.0)), YEAR_END)["lease_liabilities"]
    assert only_rows[0] == pytest.approx(50.0) and only_rows[1].startswith("breakdown row")
    # the same for a levy: the element, else the rows
    row = (text("DescriptionOfOtherExpenses", "R1", "Excise duty"), money("OtherExpenses", "R1", 9.0))
    got = sp.flow_parts(facts(money("ExciseDuty", "Q", 12.0), *row), date(2026, 3, 31), 3)["excise"]
    assert got[0] == pytest.approx(12.0) and got[1].startswith("element")
    assert sp.flow_parts(facts(*row), date(2026, 3, 31), 3)["excise"][0] == pytest.approx(9.0)


def test_a_current_maturity_of_a_lease_is_a_lease_and_never_also_a_maturity_of_borrowings():
    got = parts(money("LeaseLiabilitiesNoncurrent", "I", 40.0), money("CurrentMaturitiesOfLeaseLiabilities", "I", 8.0))
    assert got["lease_liabilities"] == pytest.approx(48.0) and "current_maturities" not in got
    # with a total, the maturity of a lease is inside it
    got = parts(money("LeaseLiabilities", "I", 50.0), money("CurrentMaturitiesOfLeaseLiabilities", "I", 8.0))
    assert got["lease_liabilities"] == pytest.approx(50.0) and "current_maturities" not in got
    # a maturity of borrowings beside them is its own part, counted once
    got = parts(money("LeaseLiabilitiesNoncurrent", "I", 40.0), money("CurrentMaturitiesOfLeaseLiabilities", "I", 8.0),
                money("CurrentMaturitiesOfLongtermBorrowings", "I", 20.0))
    assert got["lease_liabilities"] == pytest.approx(48.0) and got["current_maturities"] == pytest.approx(20.0)
    # a breakdown row "current maturities of lease liabilities" is a lease row, not a maturity row
    rows = (text("DescriptionOfOtherCurrentFinancialLiabilities", "L1", "Current maturities of lease liabilities"),
            money("OtherCurrentFinancialLiabilities", "L1", 8.0))
    got = parts(*rows)
    assert got["lease_liabilities"] == pytest.approx(8.0) and "current_maturities" not in got


def test_right_of_use_assets_are_a_row_of_other_non_current_assets_or_a_separate_element_beside_ppe():
    ppe, rou = money("PropertyPlantAndEquipment", "I", 700.0), money("RightOfUseAssets", "I", 30.0)
    assert parts(ppe, rou)["right_of_use"] == pytest.approx(30.0)
    assert "right_of_use" not in parts(rou)                                           # no PPE element: it may sit inside the fixed assets
    # screener's rule B3 (ITC 501.00 Cr): the row "Right-of-use assets" of Other non-current assets, outside PPE by construction
    rows = (text("DescriptionOfOtherNoncurrentAssets", "L2", "Right-of-use assets"), money("OtherNoncurrentAssets", "L2", 501.0))
    assert parts(*rows)["right_of_use"] == pytest.approx(501.0)
    got = sp.balance_parts(facts(*rows), YEAR_END)["right_of_use"]
    assert got[1].startswith("breakdown row")
    # a row of any other line (a breakdown of PPE) may be inside PPE: never added
    inside = (text("DescriptionOfOtherCurrentFinancialLiabilities", "L1", "Right-of-use assets"), money("OtherCurrentFinancialLiabilities", "L1", 30.0))
    assert "right_of_use" not in parts(ppe, *inside)
    # the element form is not added twice beside the row
    assert parts(ppe, rou, *rows)["right_of_use"] == pytest.approx(30.0)
    # and the view adds it
    base = {"intangibles": (60.0, "e")}
    with_rou = {**base, "right_of_use": (30.0, "e")}
    assert sc._bs_views({}, "fixed_assets", 700.0, with_rou)[0][0] == pytest.approx(790.0)
    assert sc._bs_views({}, "fixed_assets", 700.0, base)[0][0] == pytest.approx(760.0)


def test_a_view_is_tried_only_past_twice_its_own_tolerance_on_a_small_line():
    assert sc._view_apart(100.0, 103.2) and not sc._view_apart(100.0, 102.1) and not sc._view_apart(100.0, 103.0)
    # a 1.0 Cr part would "explain" a 2.1 Cr gap on a 100 Cr line (it closes within 1.5): it is not tried
    cls, _ = sc.classify_balance("borrowings", 100.0, 102.1, [], lambda: [(101.0, "borrowings_plus_lease_liabilities")], False)
    assert not cls.startswith(sc.VIEW)
    cls, _ = sc.classify_balance("borrowings", 100.0, 103.2, [], lambda: [(101.9, "borrowings_plus_lease_liabilities")], False)
    assert cls == "matches_screener_view:borrowings_plus_lease_liabilities"          # a 3.2 Cr gap is past the guard
    # the six quarterly lines: a 1.2 Cr gap was explained by any part from 0 to 2.7 Cr
    views = {"other_income": [(11.6, "exceptional_in_other_income")]}                 # ours 10 + a 1.6 Cr part, screener 11.2
    cls, _ = sc.classify_six("other_income", 10.0, 11.2, {}, "Q4FY26", views)
    assert not cls.startswith(sc.VIEW)
    cls, _ = sc.classify_six("other_income", 10.0, 13.5, {}, "Q4FY26", {"other_income": [(13.4, "exceptional_in_other_income")]})
    assert cls == "matches_screener_view:exceptional_in_other_income"                 # a 3.5 Cr gap is past it


def test_shuffled_parts_on_small_lines_explain_far_fewer_gaps_than_the_looser_guard_did():
    """Lines of 50 to 150 Cr, two parts of 0.3 to 2 Cr: another company's parts set against each gap. The guard used to be twice the
    smaller of the plain and the view tolerance (2 Cr here): it let the shuffled parts explain 371 of 600 gaps (62%); past twice the
    view's own tolerance (3 Cr) they explain 83 (14%), and every one of those gaps is a real gap of more than 3 Cr."""
    rnd = random.Random(28)
    n = 600
    cos = [(rnd.uniform(50, 150), rnd.uniform(0.3, 2.0), rnd.uniform(0.3, 2.0)) for _ in range(n)]

    def loose(ours, theirs):
        tol = min(max(1.0, 0.005 * abs(theirs)), max(1.5, 0.0005 * abs(theirs)))
        return abs(ours - theirs) > 2 * tol + 1e-9

    new = old = 0
    for i, (ours, a, b) in enumerate(cos):
        theirs = round(ours + a + b, 1)
        _, other_a, other_b = cos[(i + 101) % n]
        closes = sc.view_close(ours + other_a + other_b, theirs) and not sc._close(ours, theirs, "money")
        new += closes and sc._view_apart(ours, theirs)
        old += closes and loose(ours, theirs)
    assert new / n < 0.20 and new < old / 3
