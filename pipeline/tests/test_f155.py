"""F155: four causes found by the blind review of CARD_EBITDA_PROFIT_V2 (25 Oct 2026), each from its real case."""

from __future__ import annotations

from bse_intel import printed_figures
from bse_intel.dossier import merge, new_dossier, results_snapshot
from bse_intel.models import Filing, Pass2Output
from bse_intel.xbrl import owners_share


def test_a_comprehensive_income_tagged_as_the_owners_profit_is_dropped_beside_a_zero_minority():
    """IREDA's Q2FY26 file tags ProfitOrLossAttributableToOwnersOfParent 614.76 (its total comprehensive income) beside a
    profit of 549.33 and a minority share of 0, the template's filler. The guard that drops an owners' profit above the
    profit trusted a 0 minority as a share and kept it: the card said "net profit to shareholders -10.2% YoY"."""
    values = {("pat", "Q2FY26"): 549.33, ("pat_owners", "Q2FY26"): 614.76, ("pat_minority", "Q2FY26"): 0.0,
              ("pat", "H1FY26"): 796.21, ("pat_owners", "H1FY26"): 880.97, ("pat_minority", "H1FY26"): 0.0}
    assert owners_share(values) == 2
    assert ("pat_owners", "Q2FY26") not in values and values[("pat", "Q2FY26")] == 549.33


def test_an_owners_profit_below_the_profit_beside_a_zero_minority_stays():
    values = {("pat", "Q1FY27"): -25.27, ("pat_owners", "Q1FY27"): -25.87, ("pat_minority", "Q1FY27"): 0.0,
              ("pat", "Q2FY27"): 100.0, ("pat_owners", "Q2FY27"): 99.8, ("pat_minority", "Q2FY27"): 0.0}
    assert owners_share(values) == 0 and ("pat_owners", "Q2FY27") in values


def _filing(news_id: str, when: str) -> Filing:
    return Filing(news_id=news_id, scrip_code="532756", company_name="CIE Automotive India Ltd", headline="h", subject="",
                  filed_at=when, filing_date=when[:10], event_type="RESULTS")


def _ebitda(period: str, value: float) -> Pass2Output:
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "t",
        "card": {"headline": "CIE results", "impact_level": "MODERATE", "takeaway": "t", "what_happened": ["Results."],
                 "basis": "CONSOLIDATED"},
        "dossier_delta": {"financial_metrics": [{"metric": "ebitda", "period": period, "value": value}]}})


def test_a_figure_for_a_quarter_that_had_not_ended_is_not_kept():
    """CIE India's presentation of 27 Jul 2026 called its April-June quarter "Q2" (calendar year): its EBITDA ₹420 Cr was
    stored as Q2FY27, a quarter that ends on 30 Sep 2026, and showed on the September card as "calculated"."""
    d = merge(new_dossier(_filing("a", "2026-07-27T14:56:38+05:30"), {}), _ebitda("Q2FY27", 420.0),
              _filing("nse-106711820", "2026-07-27T14:56:38+05:30"), None, "now")
    assert not [m for m in d["financial_metrics"] if m["period"] == "Q2FY27"]
    d = merge(d, _ebitda("Q1FY27", 389.66), _filing("nse-1", "2026-07-27T14:56:38+05:30"), None, "now")
    assert [m["value"] for m in d["financial_metrics"] if m["period"] == "Q1FY27"] == [389.66]   # an ended quarter is kept


def _m(metric, period, value, *sources):
    srcs = [{"news_id": n, "as_of": a, "value": v, "unit": "INR_CR", "basis": "CONSOLIDATED"} for n, a, v in sources]
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "as_of": srcs[0]["as_of"],
            "source_news_id": srcs[0]["news_id"], "sources": srcs}


def _piramal():
    a, b = "2026-10-19T15:34:13+05:30", "2026-10-19T15:56:03+05:30"
    old = "2026-07-16T18:00:00+05:30"
    return {"financial_metrics": [
        _m("revenue", "Q2FY27", 3253.46, ("nse-106821987", b, 3253.46)),
        _m("revenue", "Q1FY27", 3085.48, ("xbrl:res:544597:Q1FY27", old, 3085.48)),
        _m("pbt", "Q2FY27", 580.0, ("nse-106821933", a, 543.14), ("nse-106821987", b, 580.0)),
        _m("pbt", "Q1FY27", 344.12, ("xbrl:res:544597:Q1FY27", old, 344.12)),
        _m("pat", "Q2FY27", 545.0, ("nse-106821933", a, 545.42), ("nse-106821987", b, 545.0)),
        _m("pat", "Q1FY27", 460.98, ("xbrl:res:544597:Q1FY27", old, 460.98)),
    ]}


def test_pbt_changes_use_one_definition(monkeypatch):
    """Piramal Finance Q2FY27: the release's PBT 580 is after the associates' share, memory's previous quarter 344.12 is
    the file's, before it (the release prints 443 on its own basis): +68.5% compared two definitions."""
    monkeypatch.delenv("CARD_SAME_DEFINITION", raising=False)
    off = results_snapshot(_piramal(), "nse-106821987")
    assert off["pbt"]["value"] == 580.0 and off["pbt"]["qoq_pct"] == 68.5       # off: what it was
    monkeypatch.setenv("CARD_SAME_DEFINITION", "1")
    on = results_snapshot(_piramal(), "nse-106821987")
    assert on["pbt"] == {"value": 580.0}                                        # the figure alone, no change beside it
    assert on["pat"]["qoq_pct"] == 18.2 and on["revenue"]["qoq_pct"] == 5.4      # lines on one definition keep theirs


def test_pbt_changes_stay_when_the_file_agrees_with_the_figure(monkeypatch):
    monkeypatch.setenv("CARD_SAME_DEFINITION", "1")
    d = _piramal()
    d["financial_metrics"][2] = _m("pbt", "Q2FY27", 543.14, ("nse-106821987", "2026-10-19T15:56:03+05:30", 580.0),
                                   ("xbrl:res:544597:Q2FY27", "2026-10-19T18:00:00+05:30", 543.14))
    assert results_snapshot(d, "nse-106821987")["pbt"]["qoq_pct"] == 57.8


CROMPTON_RELEASE = """Crompton Greaves Consumer Electricals Limited
 EBITDA increased 24.1% YoY to Rs. 205 Cr, delivering 9.0% margin, driven by disciplined price increases, cost efficiencies
 PAT increased 65.1% YoY to Rs. 125 Cr"""


def test_the_releases_own_ebitda_change_is_read_from_its_words():
    assert printed_figures.printed_ebitda_yoy(CROMPTON_RELEASE) == 24.1
    assert printed_figures.printed_ebitda_yoy("EBITDA declined 3.5% YoY to Rs. 40 Cr") == -3.5
    assert printed_figures.printed_ebitda_yoy("EBITDA increased 24.1% YoY. Later EBITDA grew 10% YoY") is None
    assert printed_figures.printed_ebitda_yoy("no figure") is None


def _crompton():
    old, now = "2025-11-06T18:00:00+05:30", "2026-10-16T14:27:38+05:30"
    return {"financial_metrics": [
        _m("revenue", "Q2FY27", 2263.0, ("nse-106820175", now, 2263.0)),
        _m("revenue", "Q2FY26", 1915.57, ("xbrl:res:539876:Q2FY26", old, 1915.57)),
        _m("ebitda", "Q2FY27", 205.0, ("nse-106820175", now, 205.0)),
        _m("ebitda", "Q2FY26", 158.37, ("xbrl:res:539876:Q2FY26", old, 158.37)),
        _m("pat", "Q2FY27", 125.0, ("nse-106820175", now, 125.0)),
        _m("pat", "Q2FY26", 75.0, ("xbrl:res:539876:Q2FY26", old, 75.0)),
    ]}


def test_our_year_ago_ebitda_is_left_off_when_the_release_states_another_change(monkeypatch):
    """Crompton Q2FY27: its year-ago finance cost was regrouped (5.16 first filed, 11.63 in this year's column), so the
    year-ago EBITDA is 165 for the company and 158.37 in memory: +29.4% where the release says +24.1%."""
    monkeypatch.setenv("CARD_EBITDA_PROFIT_V2", "1")
    off_text = results_snapshot(_crompton(), "nse-106820175", printed="EBITDA of Rs. 205 Cr for the quarter")
    assert off_text["ebitda"]["yoy_pct"] == 29.4                                  # no stated change: kept as before
    on = results_snapshot(_crompton(), "nse-106820175", printed=CROMPTON_RELEASE)
    assert on["ebitda"] == {"value": 205.0} and "prev_year" not in on["ebitda_margin"]
    assert on["revenue"]["yoy_pct"] == 18.1                                       # other lines keep theirs
    monkeypatch.setenv("CARD_EBITDA_PROFIT_V2", "0")
    assert results_snapshot(_crompton(), "nse-106820175", printed=CROMPTON_RELEASE)["ebitda"]["yoy_pct"] == 29.4
