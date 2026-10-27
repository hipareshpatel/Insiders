"""XBRL_FILER_CHECKS (F219, TODO 109): where the filer's own XBRL contradicts itself, two signals must agree."""
from __future__ import annotations

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


def test_owners_plus_minority_replaces_a_whole_profit_the_eps_contradicts_abrel(monkeypatch):
    values = _abrel()
    assert filer_profit(values) == 1
    assert values[("pat", "Q4FY26")] == 5.39 and ("pat_continuing", "Q4FY26") not in values
    values = _abrel()
    owners_share(values)
    assert values[("pat", "Q4FY26")] == -110.31   # the old reading: the sum is not checked, the owners' figure is dropped
    assert ("pat_owners", "Q4FY26") not in values


def test_adani_enterprises_owners_and_minority_are_kept_when_the_share_count_fits_them(monkeypatch):
    values = {("pat", "Q4FY25"): 1382.17, ("pat_owners", "Q4FY25"): 3844.91, ("pat_minority", "Q4FY25"): 169.99,
              ("eps", "Q4FY25"): 32.98, ("pat", "FY25"): 7099.0, ("pat_owners", "FY25"): 7099.0, ("eps", "FY25"): 60.67}
    assert filer_profit(values) == 1 and values[("pat", "Q4FY25")] == 4014.90
    assert owners_share(values) == 0 and values[("pat_owners", "Q4FY25")] == 3844.91   # now adds up
    off = {("pat", "Q4FY25"): 1382.17, ("pat_owners", "Q4FY25"): 3844.91, ("pat_minority", "Q4FY25"): 169.99,
           ("eps", "Q4FY25"): 32.98, ("pat", "FY25"): 7099.0, ("pat_owners", "FY25"): 7099.0, ("eps", "FY25"): 60.67}
    assert owners_share(off) == 1 and ("pat_owners", "Q4FY25") not in off and off[("pat", "Q4FY25")] == 1382.17


def test_neither_fitting_holds_the_whole_profit_and_no_eps_changes_nothing():
    values = {("pat", "Q"): 50.0, ("pat_owners", "Q"): 10.0, ("pat_minority", "Q"): 5.0, ("eps", "Q"): 0.5,
              ("pat", "P"): 50.0, ("eps", "P"): 0.5}   # 100 crore shares there; 50/0.5 is 100, 15/0.5 is 30
    assert filer_profit(values) == 0 and values[("pat", "Q")] == 50.0   # the whole profit fits, the sum does not: stays
    nothing = {("pat", "Q"): 50.0, ("pat_owners", "Q"): 10.0, ("pat_minority", "Q"): 5.0}
    assert filer_profit(nothing) == 0 and nothing[("pat", "Q")] == 50.0
    neither = {("pat", "Q"): 80.0, ("pat_owners", "Q"): 10.0, ("pat_minority", "Q"): 5.0, ("eps", "Q"): 0.5,
               ("pat", "P"): 50.0, ("eps", "P"): 0.5}
    assert filer_profit(neither) == 1 and ("pat", "Q") not in neither


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
    assert on[("pat", "Q4FY26")] == 5.39


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


def _aptus(monkeypatch, on, other_income=0, other_ops=18_780_000):
    body = HEAD.replace("in-bse-fin", "in-bse-fin") + _ctx("OneD", "2026-01-01", "2026-03-31")
    body += _fact("RevenueFromOperations", "OneD", 5_931_200_000) + _fact("Income", "OneD", 5_931_200_000)
    body += _fact("OtherIncome", "OneD", other_income) + _fact("OtherRevenueFromOperations", "OneD", other_ops)
    body += _fact("ProfitLossForPeriod", "OneD", 1_000_000_000)
    return (body + "</xbrli:xbrl>").encode()


def test_a_lenders_revenue_equal_to_its_income_is_held_when_other_revenue_exists(monkeypatch):
    def figures(raw):
        r = xbrl.parse(raw)
        return {m.metric for m in r.metrics}

    raw = _aptus(monkeypatch, True)
    monkeypatch.setattr(xbrl, "LENDER_TEMPLATES", ("INDAS",))   # the fixture has no SEBI namespace: read it as a lender's
    monkeypatch.setattr(xbrl, "taxonomy", lambda data: "INDAS")
    _on(monkeypatch, False)
    assert "revenue" in figures(raw)
    _on(monkeypatch)
    assert "revenue" not in figures(raw) and "total_income" in figures(raw)
    assert not any(m.startswith("_") for m in figures(raw))
    # other income present, or no other revenue from operations: the revenue stays
    assert "revenue" in figures(_aptus(monkeypatch, True, other_income=18_780_000))
    assert "revenue" in figures(_aptus(monkeypatch, True, other_ops=0))


def test_a_commercial_company_keeps_its_revenue_with_the_switch_on(monkeypatch):
    _on(monkeypatch)
    raw = _aptus(monkeypatch, True)
    assert "revenue" in {m.metric for m in xbrl.parse(raw).metrics}
