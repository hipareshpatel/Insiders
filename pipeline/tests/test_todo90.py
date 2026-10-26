"""TODO 90: profits and EPS with the wrong sign in memory, read from NSE's results XBRL (26 Oct 2026).

The cases are the structure of the real files, rebuilt small (the files themselves are not kept):
* Apar Industries Q1FY27: profit +467.45 Cr, owners' -138.56 (minority 0), EPS 116.37 -> the owners' tag is the odd one.
* Alembic Q4FY26 (67.13 / -33.87 / 2.61), DCX India FY26 (-7.71 / +120.16 / -0.69), PVR INOX Q1FY25 (-179.0 / +0.10 /
  -18.21) are the same class; Glenmark Q4FY26 (301.32, owners' -0.10, minority 301.41 adding up, EPS 10.68) too.
* Birla Precision Q4FY24: profit -0.11, owners' +0.11, EPS +0.15: the EPS backs the owners' figure, so it stays.
* Anup Engineering FY25: profit -22.06 Cr beside EPS +59.25 where its Q4 gives 2.0 crore shares and this gives 0.37.
* Centum FY24: profit -2.75, minority -4.62, EPS +1.38: the EPS is on the owners' profit (+1.87), not the whole one.
* Prism Johnson Q1FY26: EPS +0.05 beside a loss of 5.56 Cr and nothing else in the file to say which is right."""

from bse_intel import xbrl
from bse_intel.xbrl import eps_signs, owners_share

from test_xbrl import HEAD, _ctx, _fact


def _file(quarter, year=None):
    """A results file with a quarter (Apr-Jun 2026) and optionally the year (Apr 2025-Mar 2026), by tag name -> Cr or EPS."""
    body = HEAD + _ctx("Q", "2026-04-01", "2026-06-30") + _ctx("Y", "2025-04-01", "2026-03-31")
    body += ('<in-bse-fin:NatureOfReportStandaloneConsolidated contextRef="Q">Consolidated'
             "</in-bse-fin:NatureOfReportStandaloneConsolidated>")
    for ctx, tags in (("Q", quarter), ("Y", year or {})):
        for name, value in tags.items():
            if name.startswith("Basic"):
                body += _fact(name, ctx, value, "INRPerShare")
            else:
                body += _fact(name, ctx, round(value * 1e7), "INR")
    return (body + "</xbrli:xbrl>").encode()


PAT, OWN, NCI = "ProfitLossForPeriod", "ProfitOrLossAttributableToOwnersOfParent", "ProfitOrLossAttributableToNonControllingInterests"
EPS = "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations"
CONT = "ProfitLossForPeriodFromContinuingOperations"


def _by(parsed):
    return {(m.metric, m.period): m.value for m in list(parsed.metrics) + list(parsed.memory_extra)}


# ---------------------------------------------------------------- the owners' profit that opposes the rest
def test_an_owners_profit_against_the_profit_and_the_eps_is_left_out():
    """Apar Industries Q1FY27: owners' -138.56 beside +467.45 and EPS 116.37 (screener +116.36, about 4 crore shares)."""
    got = _by(xbrl.parse(_file({PAT: 467.45, OWN: -138.56, NCI: 0, EPS: "116.37"})))
    assert ("pat_owners", "Q1FY27") not in got
    assert got[("pat", "Q1FY27")] == 467.45 and got[("eps", "Q1FY27")] == 116.37   # not -116.37


def test_the_same_class_in_the_other_files():
    for pat, owners, eps in ((67.13, -33.87, "2.61"), (-7.71, 120.16, "-0.69"), (-179.0, 0.10, "-18.21")):
        got = _by(xbrl.parse(_file({PAT: pat, OWN: owners, NCI: 0, EPS: eps})))
        assert ("pat_owners", "Q1FY27") not in got
        assert got[("pat", "Q1FY27")] == pat and got[("eps", "Q1FY27")] == float(eps)


def test_a_minority_share_that_adds_up_does_not_excuse_an_eps_against_the_owners_profit():
    """Glenmark Q4FY26: owners' -0.10 and minority 301.41 add up to 301.32, but the EPS is +10.68."""
    got = _by(xbrl.parse(_file({PAT: 301.32, OWN: -0.10, NCI: 301.41, EPS: "10.68"})))
    assert ("pat_owners", "Q1FY27") not in got and got[("eps", "Q1FY27")] == 10.68


def test_an_owners_profit_a_real_minority_share_and_the_eps_agree_on_stays():
    """Whole profit +67, minority share +101, owners' -34 and an EPS that is a loss: the file is consistent."""
    got = _by(xbrl.parse(_file({PAT: 67.0, OWN: -34.0, NCI: 101.0, EPS: "-1.3"})))
    assert got[("pat_owners", "Q1FY27")] == -34.0 and got[("eps", "Q1FY27")] == -1.3


def test_an_owners_profit_the_eps_backs_stays_and_the_eps_keeps_its_sign():
    """Birla Precision Q4FY24: profit -0.11, owners' +0.11, EPS +0.15 (screener and tijori +0.15; memory had -0.15)."""
    got = _by(xbrl.parse(_file({PAT: -0.11, OWN: 0.11, NCI: 0, EPS: "0.15"})))
    assert got[("pat_owners", "Q1FY27")] == 0.11 and got[("eps", "Q1FY27")] == 0.15


# ---------------------------------------------------------------- the EPS sign repair
def test_an_eps_beside_a_profit_the_other_periods_contradict_is_left_out_with_its_profit():
    """Anup Engineering FY25: -22.06 Cr beside EPS 59.25; the Q4 of the same file is 31.54 Cr on EPS 15.75 (2.0 crore shares)."""
    got = _by(xbrl.parse(_file({PAT: 31.54, EPS: "15.75"}, {PAT: -22.06, EPS: "59.25"})))
    assert got[("pat", "Q1FY27")] == 31.54 and got[("eps", "Q1FY27")] == 15.75
    assert not [k for k in got if k[1] == "FY26"]   # neither the profit nor the EPS of the odd year


def test_an_unsigned_eps_is_flipped_only_when_the_share_count_agrees_across_the_file():
    values = {("pat", "H1"): -27.77, ("eps", "H1"): 2.27, ("pat", "Q2"): 10.0, ("eps", "Q2"): 0.8}
    assert eps_signs(values) == 1 and values[("eps", "H1")] == -2.27
    alone = {("pat", "Q1FY26"): -5.56, ("pat_owners", "Q1FY26"): 0.0, ("eps", "Q1FY26"): 0.05}
    assert eps_signs(alone) == 1 and ("eps", "Q1FY26") not in alone and alone[("pat", "Q1FY26")] == -5.56   # Prism Johnson
    through = _by(xbrl.parse(_file({PAT: -5.56, OWN: 0, NCI: 0, EPS: "0.05"})))
    assert ("eps", "Q1FY27") not in through and through[("pat", "Q1FY27")] == -5.56


def test_an_eps_on_a_profit_the_file_did_not_give_keeps_its_sign_beside_a_real_minority_share():
    """Centum FY24: whole profit -2.75 Cr, minority share -4.62, filed owners' +4.10 (it does not add up: left out),
    EPS +1.38. The owners' profit is the whole one less the minority share, +1.87; memory had -1.38."""
    got = _by(xbrl.parse(_file({PAT: -6.89, OWN: -4.55, NCI: -1.39, EPS: "-4.18"},
                               {PAT: -2.75, OWN: 4.10, NCI: -4.62, EPS: "1.38"})))
    assert got[("eps", "FY26")] == 1.38
    assert ("pat_owners", "FY26") not in got and got[("pat", "FY26")] == -2.75
    values = {("pat", "FY"): -2.75, ("eps", "FY"): 1.38, ("pat_continuing", "FY"): -2.75, ("eps_continuing", "FY"): 1.38}
    assert eps_signs(values, {"FY"}) == 0 and values[("eps", "FY")] == 1.38 and values[("eps_continuing", "FY")] == 1.38


def test_owners_share_keeps_what_it_did_for_a_zero_minority_and_sums_that_add_up():
    values = {("pat", "A"): -25.27, ("pat_owners", "A"): -25.87, ("pat_minority", "A"): 0.0,
              ("pat", "B"): 100.0, ("pat_owners", "B"): 60.0, ("pat_minority", "B"): 40.0, ("eps", "B"): 3.0}
    assert owners_share(values) == 0 and values[("pat_owners", "A")] == -25.87 and values[("pat_owners", "B")] == 60.0
