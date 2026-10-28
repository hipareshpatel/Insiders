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


def test_all_the_tagged_parts_are_applied_together_never_the_subset_that_fits():
    order = ("lease_liabilities", "current_maturities")
    assert sp.additive_views("borrowings", 330.0, {"lease_liabilities": 40.0, "current_maturities": 10.0}, order) == \
        [(380.0, "borrowings_plus_lease_liabilities_current_maturities")]          # one view: screener's own sum
    cls, note = sc.classify_balance("borrowings", 330.0, 370.0, [],
                                    lambda: sc._bs_views({}, "borrowings", 330.0, {"lease_liabilities": (40.0, "e"), "current_maturities": (10.0, "e")}),
                                    False)
    assert cls == "unexplained_larger"       # 370 = 330 + the lease alone: not a match, the maturities were tagged too
    cls, _ = sc.classify_balance("borrowings", 330.0, 380.0, [],
                                 lambda: sc._bs_views({}, "borrowings", 330.0, {"lease_liabilities": (40.0, "e"), "current_maturities": (10.0, "e")}),
                                 False)
    assert cls == "matches_screener_view:borrowings_plus_lease_liabilities_current_maturities"
    # a part under the floor is left out of the sum, not a reason to refuse the others
    cls, _ = sc.classify_balance("borrowings", 330.0, 370.0, [],
                                 lambda: sc._bs_views({}, "borrowings", 330.0, {"lease_liabilities": (40.0, "e"), "current_maturities": (0.5, "e")}),
                                 False)
    assert cls == "matches_screener_view:borrowings_plus_lease_liabilities"


def test_other_companies_parts_do_not_close_gaps_beyond_chance():
    """Shuffle test: each company's gap (screener = ours + its own lease and maturities) set against ANOTHER company's parts. The
    real parts close every gap; the shuffled ones close only what the tolerance lets by chance, and about a third of what
    searching the mixes for a fit would (the old way: lease alone, maturities alone, both)."""
    rnd = random.Random(28)
    n = 600
    cos = [(rnd.uniform(500, 5000), rnd.uniform(12, 120), rnd.uniform(12, 120)) for _ in range(n)]
    real = shuffled = searched = 0
    for i, (ours, lease, maturities) in enumerate(cos):
        theirs = float(round(ours + lease + maturities))
        own = {"lease_liabilities": (lease, "e"), "current_maturities": (maturities, "e")}
        real += sc.classify_balance("borrowings", ours, theirs, [], lambda: sc._bs_views({}, "borrowings", ours, own, False), False)[0] \
            .startswith(sc.VIEW)
        _, other_lease, other_maturities = cos[(i + 101) % n]
        other = {"lease_liabilities": (other_lease, "e"), "current_maturities": (other_maturities, "e")}
        cls, _ = sc.classify_balance("borrowings", ours, theirs, [], lambda: sc._bs_views({}, "borrowings", ours, other, False), False)
        shuffled += cls.startswith(sc.VIEW)
        if cls != "match" and sc._apart(ours, theirs, "money"):
            searched += any(sc.view_close(ours + sum(c), theirs)
                            for size in (1, 2) for c in itertools.combinations((other_lease, other_maturities), size))
        elif cls.startswith(sc.VIEW) or cls == "match":
            searched += 1
    # the view tolerance (1.5 Cr or 0.05% of screener's figure) leaves little room for chance: measured on this seed, the real parts
    # close 596 of 600 gaps, the shuffled parts 10 (1.7%), and searching the mixes for a fit would have closed 29 (4.8%)
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


def test_right_of_use_assets_only_when_a_separate_element_stands_beside_ppe_tagged_apart():
    ppe, rou = money("PropertyPlantAndEquipment", "I", 700.0), money("RightOfUseAssets", "I", 30.0)
    assert parts(ppe, rou)["right_of_use"] == pytest.approx(30.0)
    assert "right_of_use" not in parts(rou)                                           # no PPE element: it may sit inside the fixed assets
    rows = (text("DescriptionOfOtherNoncurrentAssets", "L2", "Right-of-use assets"), money("OtherNoncurrentAssets", "L2", 30.0))
    assert "right_of_use" not in parts(ppe, *rows)                                    # a row of a breakdown is never added
    # and the view adds it only then
    base = {"intangibles": (60.0, "e")}
    with_rou = {**base, "right_of_use": (30.0, "e")}
    assert sc._bs_views({}, "fixed_assets", 700.0, with_rou)[0][0] == pytest.approx(790.0)
    assert sc._bs_views({}, "fixed_assets", 700.0, base)[0][0] == pytest.approx(760.0)
