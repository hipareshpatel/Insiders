"""XBRL_FILER_CHECKS (F219, TODO 111): where the filer's own XBRL contradicts itself, two signals must agree."""
from __future__ import annotations

import pytest

from bse_intel import xbrl
from bse_intel.xbrl import eps_signs, filer_profit, owners_share

from test_xbrl import HEAD, _ctx, _fact


def _on(monkeypatch, on=True):
    monkeypatch.setenv("XBRL_FILER_CHECKS", "1" if on else "0")


def _abrel(extra=None):
    # ABREL Q4FY26: whole profit -110.31, owners +10.84, minority -5.45, EPS +0.98; other quarters on 5.5 crore shares
    values = {("pat", "Q4FY26"): -110.31, ("pat_continuing", "Q4FY26"): -104.86, ("pat_owners", "Q4FY26"): 10.84,
              ("pat_minority", "Q4FY26"): -5.45, ("eps_total", "Q4FY26"): 0.98,
              ("pat", "Q3FY26"): 11.0, ("pat_owners", "Q3FY26"): 11.0, ("eps_total", "Q3FY26"): 2.0,
              ("pat", "Q2FY26"): 5.5, ("pat_owners", "Q2FY26"): 5.5, ("eps_total", "Q2FY26"): 1.0}
    values.update(extra or {})
    return values


def test_a_whole_profit_the_eps_contradicts_is_held_abrel(monkeypatch):
    values = _abrel()
    assert filer_profit(values) == 1
    assert ("pat", "Q4FY26") not in values and ("pat_continuing", "Q4FY26") not in values   # held, never the sum
    values = _abrel()
    owners_share(values)
    assert values[("pat", "Q4FY26")] == -110.31   # the old reading: the sum is not checked, the owners' figure is dropped
    assert ("pat_owners", "Q4FY26") not in values


def test_adani_enterprises_wrong_whole_profit_is_held_and_the_owners_figure_kept(monkeypatch):
    values = {("pat", "Q4FY25"): 1382.17, ("pat_owners", "Q4FY25"): 3844.91, ("pat_minority", "Q4FY25"): 169.99,
              ("eps", "Q4FY25"): 32.98, ("pat", "FY25"): 7099.0, ("pat_owners", "FY25"): 7099.0, ("eps", "FY25"): 60.67}
    assert filer_profit(values) == 1 and ("pat", "Q4FY25") not in values
    owners_share(values)
    assert values[("pat_owners", "Q4FY25")] == 3844.91   # the EPS backs it
    off = {("pat", "Q4FY25"): 1382.17, ("pat_owners", "Q4FY25"): 3844.91, ("pat_minority", "Q4FY25"): 169.99,
           ("eps", "Q4FY25"): 32.98, ("pat", "FY25"): 7099.0, ("pat_owners", "FY25"): 7099.0, ("eps", "FY25"): 60.67}
    assert owners_share(off) == 1 and ("pat_owners", "Q4FY25") not in off and off[("pat", "Q4FY25")] == 1382.17


def test_neither_fitting_holds_the_whole_profit_and_no_eps_changes_nothing():
    values = {("pat", "Q"): 50.0, ("pat_owners", "Q"): 10.0, ("pat_minority", "Q"): 5.0, ("eps", "Q"): 0.5,
              ("pat", "P"): 50.0, ("eps", "P"): 0.5}   # 100 crore shares there; 50/0.5 is 100, 15/0.5 is 30
    assert filer_profit(values) == 0 and values[("pat", "Q")] == 50.0   # the whole profit fits, the sum does not: stays
    nothing = {("pat", "Q"): 50.0, ("pat_owners", "Q"): 10.0, ("pat_minority", "Q"): 5.0}
    assert filer_profit(nothing) == 0 and nothing[("pat", "Q")] == 50.0
    # neither the whole profit nor the owners' side fits the share count: nothing backs the owners' side, so the whole profit
    # stays (lead's read of 41345924894: Centum's right -2.75 was removed this way; it was held before)
    neither = {("pat", "Q"): 80.0, ("pat_owners", "Q"): 10.0, ("pat_minority", "Q"): 5.0, ("eps", "Q"): 0.5,
               ("pat", "P"): 50.0, ("eps", "P"): 0.5}
    assert filer_profit(neither) == 0 and neither[("pat", "Q")] == 80.0
    # the share count contradicts the whole profit AND backs the owners' sum: held (ABREL's shape)
    backed = {("pat", "Q"): 80.0, ("pat_owners", "Q"): 45.0, ("pat_minority", "Q"): 5.0, ("eps", "Q"): 0.5,
              ("pat", "P"): 50.0, ("eps", "P"): 0.5}
    assert filer_profit(backed) == 1 and ("pat", "Q") not in backed


def test_adani_ports_guard_still_holds_with_the_switch_on():
    values = {("pat", "Q4FY26"): 3308.30, ("pat_owners", "Q4FY26"): 1238.67, ("pat_minority", "Q4FY26"): 179.14,
              ("eps", "Q4FY26"): 15.3, ("pat", "Q3FY26"): 3000.0, ("pat_owners", "Q3FY26"): 3000.0, ("eps", "Q3FY26"): 13.9}
    assert filer_profit(values) == 0 and values[("pat", "Q4FY26")] == 3308.30   # the whole profit fits the share count
    assert owners_share(values) == 1 and ("pat_owners", "Q4FY26") not in values
    bare = {("pat", "Q4FY26"): 3308.30, ("pat_owners", "Q4FY26"): 1238.67, ("pat_minority", "Q4FY26"): 179.14}
    assert filer_profit(bare) == 0 and owners_share(bare) == 1


def test_parse_uses_the_switch(monkeypatch):
    body = HEAD + _ctx("OneD", "2026-01-01", "2026-03-31") + _ctx("TwoD", "2025-10-01", "2025-12-31") \
        + _ctx("ThreeD", "2025-07-01", "2025-09-30")
    for ctx, pat, owners, minority, eps in (("OneD", -1103.1, 108.4, -54.5, "0.98"), ("TwoD", 110.0, 110.0, 0, "2.0"),
                                            ("ThreeD", 55.0, 55.0, 0, "1.0")):
        body += _fact("ProfitLossForPeriod", ctx, int(pat * 1e6)) + _fact("ProfitOrLossAttributableToOwnersOfParent", ctx, int(owners * 1e6))
        body += _fact("ProfitOrLossAttributableToNonControllingInterests", ctx, int(minority * 1e6))
        body += _fact("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", ctx, eps, "INRPerShare")
    raw = (body + "</xbrli:xbrl>").encode()
    _on(monkeypatch, False)
    off = {(m.metric, m.period): m.value for m in xbrl.parse(raw).metrics}
    assert off[("pat", "Q4FY26")] == -110.31
    _on(monkeypatch)
    on = {(m.metric, m.period): m.value for m in xbrl.parse(raw).metrics}
    assert ("pat", "Q4FY26") not in on


def test_anup_profit_is_held_beside_an_eps_the_other_period_supports():
    # FY25 file with the Q4 only: profit -22.06 beside EPS 59.25; Q4 31.54 / 15.75 = 2.0 crore shares
    def anup():
        return {("pat", "Q4FY25"): 31.54, ("eps", "Q4FY25"): 15.75, ("pat", "FY25"): -22.06, ("pat_continuing", "FY25"): -22.06,
                ("eps", "FY25"): 59.25}
    old = anup()
    assert eps_signs(old) == 1 and ("eps", "FY25") not in old and old[("pat", "FY25")] == -22.06
    new = anup()
    assert eps_signs(new, frozenset(), True) == 1
    assert new[("eps", "FY25")] == 59.25 and ("pat", "FY25") not in new and ("pat_continuing", "FY25") not in new
    assert new[("pat", "Q4FY25")] == 31.54
    # a year that its four quarters confirm keeps the profit and loses the EPS, as before
    ok = {("pat", "Q1FY25"): -5.0, ("pat", "Q2FY25"): -5.0, ("pat", "Q3FY25"): -6.0, ("pat", "Q4FY25"): -6.06,
          ("eps", "Q4FY25"): -3.0, ("pat", "FY25"): -22.06, ("eps", "FY25"): 59.25}
    eps_signs(ok, frozenset(), True)
    assert ("eps", "FY25") not in ok and ok[("pat", "FY25")] == -22.06
    # owners and minority that add up corroborate the profit
    backed = anup()
    backed.update({("pat_owners", "FY25"): -20.0, ("pat_minority", "FY25"): -2.06})
    eps_signs(backed, frozenset(), True)
    assert ("eps", "FY25") not in backed and backed[("pat", "FY25")] == -22.06


def _aptus(monkeypatch, on, other_income=0, other_ops=187_800_000):   # 18.78 Cr, the filed figure
    body = HEAD.replace("in-bse-fin", "in-bse-fin") + _ctx("OneD", "2026-01-01", "2026-03-31")
    body += _fact("RevenueFromOperations", "OneD", 5_931_200_000) + _fact("Income", "OneD", 5_931_200_000)
    body += _fact("OtherIncome", "OneD", other_income) + _fact("OtherRevenueFromOperations", "OneD", other_ops)
    body += _fact("ProfitLossForPeriod", "OneD", 1_000_000_000)
    return (body + "</xbrli:xbrl>").encode()


def test_a_lenders_revenue_equal_to_its_income_is_never_held(monkeypatch):
    """Blind review of release check 41324276371: the Aptus hold removed true revenue on 6 cards (MASTERTR, ARMANFIN, JSWHL,
    BAJAJFINSV, HDBFS, c03), each the filing's printed revenue from operations with other income nil. Removed: kept both ways."""
    def figures(raw):
        r = xbrl.parse(raw)
        return {m.metric for m in r.metrics}

    raw = _aptus(monkeypatch, True)
    monkeypatch.setattr(xbrl, "LENDER_TEMPLATES", ("INDAS",))   # the fixture has no SEBI namespace: read it as a lender's
    monkeypatch.setattr(xbrl, "taxonomy", lambda data: "INDAS")
    for on in (False, True):
        _on(monkeypatch, on)
        assert "revenue" in figures(raw) and "total_income" in figures(raw)
        assert not any(m.startswith("_") for m in figures(raw))


def test_a_commercial_company_keeps_its_revenue_with_the_switch_on(monkeypatch):
    _on(monkeypatch)
    raw = _aptus(monkeypatch, True)
    assert "revenue" in {m.metric for m in xbrl.parse(raw).metrics}


def test_a_right_whole_profit_is_never_replaced_by_a_wrong_sum():
    # blind review, 27 Oct 2026: a minority tagged with the wrong sign (-50 for +50), or owners' and minority shares of
    # other comprehensive income, beside a right profit of 150 on an owners' EPS of 10 (10 crore shares elsewhere)
    for minority in (-50.0, 20.0):
        values = {("pat", "Q"): 150.0, ("pat_owners", "Q"): 100.0, ("pat_minority", "Q"): minority, ("eps", "Q"): 10.0,
                  ("pat", "P"): 100.0, ("eps", "P"): 10.0}
        filer_profit(values)
        assert values.get(("pat", "Q")) not in (50.0, 120.0)


def _file(rows, eps=True) -> bytes:
    """A results file of Q4FY26 (OneD) and FY26 (FourD) with the figures of the stored facts (facts-dump run 41321814793), in Cr:
    (ctx, profit, owners, minority, other comprehensive income, total comprehensive income, EPS)."""
    body = HEAD + _ctx("OneD", "2026-01-01", "2026-03-31") + _ctx("FourD", "2025-04-01", "2026-03-31")
    for ctx, pat, owners, minority, oci, tci, per_share in rows:
        body += _fact("ProfitLossForPeriod", ctx, round(pat * 1e7)) + _fact("ProfitOrLossAttributableToOwnersOfParent", ctx, round(owners * 1e7))
        body += _fact("ProfitOrLossAttributableToNonControllingInterests", ctx, round(minority * 1e7))
        body += _fact("OtherComprehensiveIncomeNetOfTaxes", ctx, round(oci * 1e7)) + _fact("ComprehensiveIncomeForThePeriod", ctx, round(tci * 1e7))
        if eps:
            body += _fact("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", ctx, str(per_share), "INRPerShare")
    return (body + "</xbrli:xbrl>").encode()


# Adani Ports' stored figures; the EPS are not in the dump (its pattern missed the EPS tags): the statement's owners' profit
# (3,328.96 and FY26's) over about 216 crore shares, an assumption that only sets the share count
PORTS = [("OneD", 3308.30, 1238.67, 179.14, 1417.81, 4726.11, 15.41), ("FourD", 12782.03, 914.83, 322.51, 1237.34, 14019.37, 57.68)]
COFORGE = [("OneD", 666.2, 572.2, 60.8, -33.2, 633.0, 18.1), ("FourD", 1744.7, 1565.9, 203.4, 24.6, 1769.3, 46.4)]


def _figures(raw: bytes) -> dict:
    return {(m.metric, m.period): m.value for m in xbrl.parse(raw).metrics}


@pytest.mark.parametrize("rows,profit", [(PORTS, 3308.30), (COFORGE, 666.2)], ids=["ADANIPORTS", "COFORGE"])
def test_owners_and_minority_that_are_comprehensive_income_shares_leave_the_profit_standing(monkeypatch, rows, profit):
    raw = _file(rows)
    _on(monkeypatch)
    on = _figures(raw)
    assert on.get(("pat", "Q4FY26")) == profit                 # main held it and showed the share instead
    assert ("pat_owners", "Q4FY26") not in on and ("pat_owners", "FY26") not in on
    assert not any(k[0].startswith("_") for k in on)
    monkeypatch.setenv("XBRL_FILER_CHECKS", "0")
    assert _figures(raw).get(("pat", "Q4FY26")) == profit      # off: as before


def test_comprehensive_shares_on_the_real_figures():
    ci = lambda tci, oci: {(xbrl._CI_TOTAL, "Q"): tci, (xbrl._CI_OTHER, "Q"): oci}
    # Wabag Q4FY26: 141.2 - 0.1 = 141.1, its total comprehensive income
    wabag = {("pat", "Q"): 128.0, ("pat_owners", "Q"): 141.2, ("pat_minority", "Q"): -0.1}
    assert xbrl.comprehensive_shares(wabag, ci(141.1, 13.1)) == 1 and wabag == {("pat", "Q"): 128.0}
    # ABREL Q4FY26: 10.84 - 5.45 = 5.39, the PDF's profit, neither comprehensive figure: left for filer_profit
    abrel = {("pat", "Q"): -110.31, ("pat_owners", "Q"): 10.84, ("pat_minority", "Q"): -5.45}
    assert xbrl.comprehensive_shares(abrel, ci(-122.44, -12.13)) == 0 and len(abrel) == 3
    # no other comprehensive income: owners + minority are the profit and the total alike, and stay
    plain = {("pat", "Q"): 100.0, ("pat_owners", "Q"): 90.0, ("pat_minority", "Q"): 10.0}
    assert xbrl.comprehensive_shares(plain, ci(100.0, 0.0)) == 0 and len(plain) == 3


def test_a_lender_whose_revenue_is_its_income_with_no_other_income_keeps_it(monkeypatch):
    # BAJAJFINSV-like: revenue equals total income, other income 0, no other revenue from operations
    monkeypatch.setattr(xbrl, "LENDER_TEMPLATES", ("INDAS",))
    monkeypatch.setattr(xbrl, "taxonomy", lambda data: "INDAS")
    _on(monkeypatch)
    body = HEAD + _ctx("OneD", "2026-01-01", "2026-03-31")
    body += _fact("RevenueFromOperations", "OneD", 384_937_900_000) + _fact("Income", "OneD", 384_937_900_000)
    body += _fact("OtherIncome", "OneD", 0) + _fact("ProfitLossForPeriod", "OneD", 52_262_600_000)
    got = {m.metric for m in xbrl.parse((body + "</xbrli:xbrl>").encode()).metrics}
    assert "revenue" in got and "total_income" in got
    assert xbrl._lender_revenue({("revenue", "Q"): 5.0, ("total_income", "Q"): 5.0, ("other_income", "Q"): 0,
                                 (xbrl._OTHER_REVENUE, "Q"): 0}, True) == 0


def _disc_file(rows) -> bytes:
    """Q4FY26 (OneD) and FY26 (FourD) of a company with a discontinued operation, the stored figures in Cr (facts-dump run
    41323023287): (ctx, profit, continuing, discontinued, owners, minority, continuing EPS, whole EPS); the continuing EPS tag
    comes first in the file, as in the real ones, so it is the `eps` kept."""
    body = HEAD + _ctx("OneD", "2026-01-01", "2026-03-31") + _ctx("FourD", "2025-04-01", "2026-03-31")
    for ctx, pat, cont, disc, owners, minority, eps_c, eps_t in rows:
        body += _fact("BasicEarningsLossPerShareFromContinuingOperations", ctx, str(eps_c), "INRPerShare")
        body += _fact("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", ctx, str(eps_t), "INRPerShare")
        for tag, v in (("ProfitLossForPeriod", pat), ("ProfitLossForPeriodFromContinuingOperations", cont),
                       ("ProfitLossFromDiscontinuedOperationsAfterTax", disc), ("ProfitOrLossAttributableToOwnersOfParent", owners),
                       ("ProfitOrLossAttributableToNonControllingInterests", minority)):
            body += _fact(tag, ctx, round(v * 1e7))
    return (body + "</xbrli:xbrl>").encode()


TMPV = [("OneD", 5878.0, 5744.0, 0.0, 5783.0, 95.0, 15.71, 15.71),
        ("FourD", 82645.0, -1823.0, 84022.0, 82390.0, 255.0, -4.43, -0.61)]
CAMLIN = [("OneD", 86.2773, -0.409, 85.3034, 88.2019, -1.9246, 0.35, 4.59),
          ("FourD", 23.5432, -33.1931, 55.0742, 27.6272, -4.084, -1.59, 1.46)]


@pytest.mark.parametrize("rows,profit,continuing", [(TMPV, 82645.0, -1823.0), (CAMLIN, 23.54, -33.19)], ids=["TMPV", "CAMLINFINE"])
def test_a_year_with_a_discontinued_operation_keeps_its_profit(monkeypatch, rows, profit, continuing):
    raw = _disc_file(rows)
    _on(monkeypatch)
    on = _figures(raw)
    assert on.get(("pat", "FY26")) == profit and on.get(("pat_continuing", "FY26")) == continuing   # main held both
    monkeypatch.setenv("XBRL_FILER_CHECKS", "0")
    assert _figures(raw).get(("pat", "FY26")) == profit


def test_corroboration_reads_the_minority_owners_share_kept():
    values = {("pat", "FY26"): 82645.0, ("pat_owners", "FY26"): 82390.0}
    assert not xbrl._profit_corroborated(values, "FY26")
    assert xbrl._profit_corroborated(values, "FY26", {("pat_minority", "FY26"): 255.0})


def test_continuing_eps_only_with_a_discontinued_figure(monkeypatch):
    _on(monkeypatch)
    base = {("eps", "Y"): -4.43, ("eps_continuing", "Y"): -4.43, ("eps_total", "Y"): -0.61, ("pat_continuing", "Y"): -1823.0,
            ("pat", "Y"): 82645.0, ("pat_owners", "Y"): 82390.0}
    assert xbrl._eps_profit({**base, ("pat_discontinued", "Y"): 84022.0}, "eps", "Y") == -1823.0
    assert xbrl._eps_profit({**base, ("pat_discontinued", "Y"): 0.0}, "eps", "Y") == 82390.0   # no discontinued figure
    whole_first = {**base, ("eps", "Y"): -0.61, ("pat_discontinued", "Y"): 84022.0}             # the whole EPS kept first
    assert xbrl._eps_profit(whole_first, "eps", "Y") == 82390.0
    _on(monkeypatch, False)
    assert xbrl._eps_profit({**base, ("pat_discontinued", "Y"): 84022.0}, "eps", "Y") == 82390.0


def test_lender_revenue_is_kept_whatever_its_other_revenue():
    # LTF Q2FY27 (0.07 Cr other revenue) and HDBFS Q2FY27 (345.38 beside 5,005.32, the Aptus shape the review found true)
    for other in (0.07, 345.38):
        values = {("revenue", "Q"): 5005.32, ("total_income", "Q"): 5005.32, ("other_income", "Q"): 0.0, (xbrl._OTHER_REVENUE, "Q"): other}
        assert xbrl._lender_revenue(values, True) == 0 and values[("revenue", "Q")] == 5005.32
        assert (xbrl._OTHER_REVENUE, "Q") not in values


def test_tmpv_keeps_the_total_eps_not_the_continuing_one(monkeypatch):
    """Blind review of 41324276371, TMPV c15: FY26's continuing-only EPS -4.43 stayed on the card; the total EPS is -0.61."""
    raw = _disc_file(TMPV)
    _on(monkeypatch)
    # the total EPS replaces the continuing one; against the positive owners' profit its sign is unproven, so eps_signs leaves
    # it out (less, never a guess; no card shows EPS): -4.43 is gone from the card's figures, memory keeps the continuing variant
    assert ("eps", "FY26") not in _figures(raw)
    assert xbrl.total_tags({("eps", "Y"): -4.43, ("eps_continuing", "Y"): -4.43, ("eps_total", "Y"): -0.61,
                            ("pat_discontinued", "Y"): 84022.0}) == 1
    extra = {(m.metric, m.period): m.value for m in xbrl.parse(raw).memory_extra}
    assert extra[("eps_continuing", "FY26")] == -4.43
    assert _figures(raw).get(("eps", "Q4FY26")) == 15.71   # no discontinued figure in the quarter: as filed
    _on(monkeypatch, False)
    assert ("eps", "FY26") not in _figures(raw)            # off: the sign check leaves -4.43 out against the positive profit, as before


def test_aurum_owners_equal_to_the_continuing_profit_are_left_out(monkeypatch):
    """AURUM c12: owners -10.45 is the continuing profit; the whole profit is +1.90 with the discontinued figure."""
    _on(monkeypatch)
    aurum = {("pat", "Q"): 1.90, ("pat_continuing", "Q"): -10.45, ("pat_discontinued", "Q"): 12.35, ("pat_owners", "Q"): -10.45}
    values = dict(aurum)
    assert xbrl.total_tags(values) == 1 and ("pat_owners", "Q") not in values and values[("pat", "Q")] == 1.90
    # an owners' figure that is the whole profit stays; so does one in a period with no discontinued figure
    right = {**aurum, ("pat_owners", "Q"): 1.90}
    assert xbrl.total_tags(right) == 0 and right[("pat_owners", "Q")] == 1.90
    none = {**aurum, ("pat_discontinued", "Q"): 0.0}
    assert xbrl.total_tags(none) == 0 and ("pat_owners", "Q") in none
    # owners that add up with a real minority to the whole profit stay
    ok = {("pat", "Q"): 100.0, ("pat_continuing", "Q"): 90.0, ("pat_discontinued", "Q"): 10.0, ("pat_owners", "Q"): 90.0,
          ("pat_minority", "Q"): 10.0}
    assert xbrl.total_tags(ok) == 0


def _chain(values: dict) -> dict:
    """The filer-check steps in xbrl.parse's order, the switch on; the minority shares kept beside them."""
    kept: dict = {}
    xbrl.total_tags(values)
    filer_profit(values)
    xbrl.continuing_before_share(values)
    owners_share(values, kept, True)
    return kept


def test_aurum_the_right_whole_profit_stays_and_the_continuing_owners_share_goes(monkeypatch):
    """AURUM nse-106598067 FY26, the file's own figures (facts-dump 41362651030): profit 0.71, continuing -7.75, discontinued 12.34,
    owners -10.45 (their continuing share only: -10.45 - 1.18 + 12.34 = 0.71), minority -1.18. ON removed the right 0.71 and
    kept -10.45 (lead's read of 41345924894)."""
    _on(monkeypatch)
    values = {("pat", "FY26"): 0.71, ("pat_continuing", "FY26"): -7.75, ("pat_discontinued", "FY26"): 12.34,
              ("pat_owners", "FY26"): -10.45, ("pat_minority", "FY26"): -1.18, ("eps", "FY26"): 0.31,
              ("pat", "Q4FY26"): 16.44, ("pat_continuing", "Q4FY26"): 5.24, ("pat_discontinued", "Q4FY26"): 13.05,
              ("pat_owners", "Q4FY26"): 3.59, ("pat_minority", "Q4FY26"): -0.20, ("eps", "Q4FY26"): 2.69}
    _chain(values)
    assert values[("pat", "FY26")] == 0.71 and values[("pat_continuing", "FY26")] == -7.75
    assert ("pat_owners", "FY26") not in values


def test_pgil_a_minority_share_with_the_wrong_sign_keeps_both_profit_lines(monkeypatch):
    """PGIL nse-106623374 (facts-dump 41362651030): owners 83.26 / 277.65 as printed, minority tagged +2.28 / +7.63 for the printed
    losses, whole 80.98 / 270.03 (owners - minority). ON kept the owners' rows and removed both whole profits; both are right."""
    _on(monkeypatch)
    values = {("pat", "Q4FY26"): 80.98, ("pat_continuing", "Q4FY26"): 80.98, ("pat_owners", "Q4FY26"): 83.26,
              ("pat_minority", "Q4FY26"): 2.28, ("eps", "Q4FY26"): 18.05,
              ("pat", "FY26"): 270.03, ("pat_continuing", "FY26"): 270.03, ("pat_owners", "FY26"): 277.65,
              ("pat_minority", "FY26"): 7.63, ("eps", "FY26"): 60.34}
    kept = _chain(values)
    assert values[("pat", "Q4FY26")] == 80.98 and values[("pat_owners", "Q4FY26")] == 83.26
    assert values[("pat", "FY26")] == 270.03 and values[("pat_owners", "FY26")] == 277.65
    assert kept[("pat_minority", "Q4FY26")] == -2.28   # its sign put right for memory
    # off: the owners' rows go (they do not add up as tagged), the whole profit stays
    plain = {("pat", "Q4FY26"): 80.98, ("pat_owners", "Q4FY26"): 83.26, ("pat_minority", "Q4FY26"): 2.28}
    owners_share(plain)
    assert ("pat_owners", "Q4FY26") not in plain and plain[("pat", "Q4FY26")] == 80.98


def test_npst_an_owners_figure_two_signals_contradict_is_left_out(monkeypatch):
    """NPST nse-106645418 (facts-dump 41362651030): whole 12.24 / 40.83, owners 18.37 / 46.94 printed, minority -0.02 / -0.01. The
    owners do not add up with the minority share either way, and the EPS share count (Q2FY26: 9.84 / 5.00, about 1.97 crore
    shares) fits the whole profit (12.24 / 6.17 = 1.98) and not the owners' (2.98): a filer's slip. The whole profit stays."""
    _on(monkeypatch)
    values = {("pat", "Q4FY26"): 12.24, ("pat_owners", "Q4FY26"): 18.37, ("pat_minority", "Q4FY26"): -0.02, ("eps", "Q4FY26"): 6.17,
              ("pat", "FY26"): 40.83, ("pat_owners", "FY26"): 46.94, ("pat_minority", "FY26"): -0.01, ("eps", "FY26"): 20.58,
              ("pat", "Q2FY26"): 9.84, ("pat_owners", "Q2FY26"): 9.84, ("pat_minority", "Q2FY26"): 0.004, ("eps", "Q2FY26"): 5.0}
    _chain(values)
    assert values[("pat", "Q4FY26")] == 12.24 and values[("pat", "FY26")] == 40.83
    assert ("pat_owners", "Q4FY26") not in values and ("pat_owners", "FY26") not in values
