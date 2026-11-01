"""F172 (CARD_GUIDANCE_DATED): a guidance verdict only from a dated target for this filing's period and metric.
The three failing cards of the 26 Oct 2026 audit, each with the switch off (what it was) and on."""

from __future__ import annotations

import pytest

from bse_intel import signals
from bse_intel.models import Filing, Pass2Output

NEWS = "nse-106827552"


def _filing(news_id: str = NEWS, when: str = "2026-10-24T15:38:33+05:30") -> Filing:
    return Filing(news_id=news_id, scrip_code="500870", company_name="Castrol India Limited", headline="h", subject="",
                  filed_at=when, filing_date=when[:10], event_type="RESULTS")


def _out(promises=(), watches=()) -> Pass2Output:
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "t",
        "card": {"headline": "Castrol India Q2FY27 results", "impact_level": "MODERATE", "takeaway": "t", "what_happened": ["x"]},
        "dossier_delta": {"promise_updates": [{"guidance_id": g, "status": s, "evidence": e} for g, s, e in promises],
                          "watch_updates": [{"watch_id": w, "status": s, "evidence": e} for w, s, e in watches]}})


def _metric(metric: str, period: str, value: float, news_id: str = NEWS) -> dict:
    return {"metric": metric, "period": period, "value": value, "unit": "PCT", "as_of": "2026-10-24T15:38:33+05:30",
            "source_news_id": news_id}


def _g(gid, statement, metric, target, due, due_date, given_on, status="OPEN") -> dict:
    return {"id": gid, "statement": statement, "metric": metric, "target": target, "due": due, "due_date": due_date,
            "given_on": given_on, "source_news_id": "nse-old", "status": status, "status_history": []}


def _kinds(found: list) -> list[tuple[str, str]]:
    return [(s.type, s.severity) for s in found]


@pytest.fixture(autouse=True)
def _off(monkeypatch):
    monkeypatch.delenv("CARD_GUIDANCE_DATED", raising=False)
    monkeypatch.delenv("DECK_DISCUSSED_PERIOD", raising=False)


def _castrol():
    before = {"guidance": [
        _g("g_816aa97d", "EBITDA margin guidance", "ebitda_margin", "21% to 24%", "Medium term", None, "2026-05-04T17:55:34+05:30"),
        _g("g_90c97c9a", "Maintain EBITDA margin in the 21% to 24% band through pricing actions", "ebitda_margin", "21-24%",
           "FY26", "2026-03-31", "2026-08-10T15:08:20+05:30"),
    ]}
    after = {**before, "financial_metrics": [_metric("ebitda_margin", "Q2FY27", 15.11)]}
    out = _out(promises=[("g_816aa97d", "MISSED", "Q2FY27 EBITDA margin fell to 15.11%, well below 21% to 24%."),
                         ("g_90c97c9a", "MISSED", "EBITDA margin of 15.11% in Q2FY27 breached the guided 21-24% band.")])
    return before, after, out


def test_castrol_undated_and_wrongly_dated_targets_are_missed_with_the_switch_off():
    before, after, out = _castrol()
    assert _kinds(signals._promises(before, after, out, _filing())) == [("GUIDANCE_BREACH", "WARNING")] * 2


def test_castrol_undated_and_wrongly_dated_targets_get_no_verdict_with_the_switch_on(monkeypatch):
    monkeypatch.setenv("CARD_GUIDANCE_DATED", "1")
    before, after, out = _castrol()
    found = signals._promises(before, after, out, _filing())
    assert _kinds(found) == [("WATCH_RESOLVED", "INFO")] * 2
    assert "Management said on 2026-05-04" in found[0].text and "no date" in found[0].text
    assert "Management said on 2026-08-10" in found[1].text and "before the day it was said" in found[1].text
    assert not any("Missed" in s.text for s in found)


def test_a_dated_target_for_this_period_and_metric_still_gets_its_verdict(monkeypatch):
    monkeypatch.setenv("CARD_GUIDANCE_DATED", "1")
    before, after, out = _castrol()
    before["guidance"].append(_g("g_ok", "EBITDA margin of 21-24% in Q2FY27", "ebitda_margin", "21-24%", "Q2FY27",
                                 "2026-09-30", "2026-05-04T17:55:34+05:30"))
    out = _out(promises=[("g_ok", "MISSED", "EBITDA margin 15.11% in Q2FY27.")])
    found = [s for s in signals._promises(before, after, out, _filing()) if s.ref == "g_ok"]
    assert _kinds(found) == [("GUIDANCE_BREACH", "WARNING")]
    assert found[0].text.startswith("Missed:")


def test_a_year_target_is_not_judged_on_a_quarter(monkeypatch):
    monkeypatch.setenv("CARD_GUIDANCE_DATED", "1")
    before, after, out = _castrol()
    before["guidance"].append(_g("g_fy", "EBITDA margin of 21-24% for FY27", "ebitda_margin", "21-24%", "FY27",
                                 "2027-03-31", "2026-05-04T17:55:34+05:30"))
    out = _out(promises=[("g_fy", "MISSED", "EBITDA margin 15.11% in Q2FY27.")])
    found = [s for s in signals._promises(before, after, out, _filing()) if s.ref == "g_fy"]
    assert _kinds(found) == [("WATCH_RESOLVED", "INFO")] and "not due for the period" in found[0].text


UNION = "nse-106821746"


def _union():
    before = {"guidance": [_g("g_c1e01bb1", "FCNR mobilisation of USD 1.5-2 billion by September", "fcnr_mobilisation",
                              "USD 1.5-2 billion", "Sep-2026", "2026-09-30", "2026-07-21T18:39:11+05:30")],
              "watchlist": [{"id": "w_8002620e", "kind": "KPI", "text": "ECL provision build-up toward ₹6,000 Cr",
                             "check_in": "Q2FY27 results", "target": "progress toward ₹6,000 Cr", "check_by": "2026-09-30",
                             "created_on": "2026-07-21T18:39:11+05:30", "status": "OPEN", "status_history": []}]}
    after = {**before, "financial_metrics": [_metric("revenue", "Q2FY27", 28377.73, UNION),
                                             _metric("provisions", "Q2FY27", 702.19, UNION)]}
    out = _out(watches=[("w_8002620e", "MISSED", "Q2FY27 provisions reported at ₹702.19 Cr.")])
    return before, after, out


def test_union_bank_unmentioned_target_and_cumulative_kpi_are_missed_with_the_switch_off():
    before, after, out = _union()
    found = signals._promises(before, after, out, _filing(UNION, "2026-10-19T12:25:56+05:30"))
    assert _kinds(found) == [("WATCH_RESOLVED", "WARNING"), ("GUIDANCE_BREACH", "WARNING")]
    assert found[0].text.startswith("KPI check missed") and found[1].text.startswith("Deadline passed")


def test_union_bank_gets_dated_said_on_lines_instead_with_the_switch_on(monkeypatch):
    monkeypatch.setenv("CARD_GUIDANCE_DATED", "1")
    before, after, out = _union()
    found = signals._promises(before, after, out, _filing(UNION, "2026-10-19T12:25:56+05:30"))
    assert _kinds(found) == [("WATCH_RESOLVED", "INFO")] * 2
    assert "not a plain figure" in found[0].text   # the honest reason rides DECK_DISCUSSED_PERIOD (off here)
    assert "FCNR mobilisation" in found[1].text and "prints no figure for the target's metric" in found[1].text
    assert not any(s.severity == "WARNING" for s in found)


def test_a_plain_kpi_target_for_this_quarter_keeps_its_verdict(monkeypatch):
    monkeypatch.setenv("CARD_GUIDANCE_DATED", "1")
    before, after, _ = _union()
    before["watchlist"][0].update(text="Provisions", target="< 800")
    out = _out(watches=[("w_8002620e", "MET", "Q2FY27 provisions reported at ₹702.19 Cr.")])
    found = [s for s in signals._promises(before, after, out, _filing(UNION, "2026-10-19T12:25:56+05:30")) if s.ref == "w_8002620e"]
    assert _kinds(found) == [("WATCH_RESOLVED", "POSITIVE")] and found[0].text.startswith("KPI check met")


def test_gic_shaped_filing_with_no_figures_of_its_own_settles_no_target(monkeypatch):
    """GIC Housing's rate notice prints no results figure. Its card's wrong lines (a NIM of 19.63% in the footer, from a
    stored Q4FY26 value, and an AI takeaway) are not guidance verdicts and this rule leaves them alone. What it does
    guarantee is that such a filing can settle no target from memory."""
    before = {"guidance": [_g("g_nim", "NIM above 3.4%", "nim", "above 3.4%", "FY27", "2027-03-31", "2026-05-01T10:00:00+05:30")]}
    after = {**before, "financial_metrics": [_metric("nim", "Q4FY26", 19.63, "nse-106625596")]}
    out = _out(promises=[("g_nim", "DELIVERED", "NIM 19.63%")])
    gic = _filing("nse-106827848", "2026-10-24T16:00:00+05:30")
    assert _kinds(signals._promises(before, after, out, gic)) == [("PROMISE_DELIVERED", "POSITIVE")]   # off: as before
    monkeypatch.setenv("CARD_GUIDANCE_DATED", "1")
    assert _kinds(signals._promises(before, after, out, gic)) == [("WATCH_RESOLVED", "INFO")]


def test_memory_status_is_not_set_by_a_verdict_that_fails_the_rule(monkeypatch):
    """The stored guidance status (read by later cards as MISSED) follows the same rule."""
    from bse_intel.dossier import merge, new_dossier

    def run():
        filing = _filing()
        d = new_dossier(filing, {})
        d["guidance"] = [_g("g_816aa97d", "EBITDA margin guidance", "ebitda_margin", "21% to 24%", "Medium term", None,
                            "2026-05-04T17:55:34+05:30")]
        out = Pass2Output.model_validate({
            "is_material": True, "event_type": "RESULTS", "timeline_entry": "t",
            "card": {"headline": "Castrol India Q2FY27 results", "impact_level": "MODERATE", "takeaway": "t", "what_happened": ["x"]},
            "dossier_delta": {"financial_metrics": [{"metric": "ebitda_margin", "period": "Q2FY27", "value": 15.11}],
                              "promise_updates": [{"guidance_id": "g_816aa97d", "status": "MISSED", "evidence": "15.11%"}]}})
        return merge(d, out, filing, None, "now")["guidance"][0]["status"]

    assert run() == "MISSED"
    monkeypatch.setenv("CARD_GUIDANCE_DATED", "1")
    assert run() == "OPEN"


def _krn_deck(monkeypatch):
    """KRN Heat Exchanger, live audit 1 Nov 2026: the Q2FY27 results (29 Oct) stated the margin; the investor deck (30 Oct)
    prints no table of its own. A target due "Q2FY27 results" is due for the deck that discusses Q2FY27."""
    monkeypatch.setenv("CARD_GUIDANCE_DATED", "1")
    watch = {"id": "w_51343734", "kind": "KPI", "text": "Consolidated EBITDA margin", "check_in": "Q2FY27 results",
             "target": "above 19%", "check_by": "2026-09-30", "created_on": "2026-08-13T22:35:50+05:30",
             "source_news_id": "nse-106743256", "status": "OPEN", "status_history": []}
    before = {"watchlist": [watch]}
    after = {**before, "financial_metrics": [_metric("ebitda_margin", "Q2FY27", 15.27, "nse-106834552"),
                                              _metric("revenue", "Q2FY27", 319.14, "nse-106834552")]}
    out = _out(watches=[("w_51343734", "MISSED", "EBITDA margin at 15.27% in Q2FY27, below the 19% target.")])
    return before, after, out, _filing("nse-106836198", "2026-10-30T13:31:07+05:30")


def test_a_target_due_this_quarters_results_is_judged_by_the_deck_that_discusses_it(monkeypatch):
    before, after, out, deck = _krn_deck(monkeypatch)
    deck = deck.model_copy(update={"event_type": "CONCALL_PRESENTATION"})
    found = signals._promises(before, after, out, deck)   # DECK_DISCUSSED_PERIOD off: as on main
    assert _kinds(found) == [("WATCH_RESOLVED", "INFO")] and "not due for the period" in found[0].text
    monkeypatch.setenv("DECK_DISCUSSED_PERIOD", "1")
    found = signals._promises(before, after, out, deck)
    assert _kinds(found) == [("WATCH_RESOLVED", "WARNING")] and found[0].text.startswith("KPI check missed")


def test_a_non_deck_filing_without_the_figure_still_settles_nothing(monkeypatch):
    before, after, out, deck = _krn_deck(monkeypatch)
    found = signals._promises(before, after, out, deck.model_copy(update={"event_type": "GOVERNANCE"}))
    assert _kinds(found) == [("WATCH_RESOLVED", "INFO")] and "not due for the period" in found[0].text


# ---- 1 Nov 2026 blind grade of release_check deck_period
def _deck_watch(monkeypatch, target, text, status, evidence):
    monkeypatch.setenv("CARD_GUIDANCE_DATED", "1")
    monkeypatch.setenv("DECK_DISCUSSED_PERIOD", "1")
    watch = {"id": "w_1", "kind": "KPI", "text": text, "check_in": "Q2FY27 results", "target": target,
             "check_by": "2026-09-30", "created_on": "2026-07-17T10:00:00+05:30", "status": "OPEN", "status_history": []}
    before = {"watchlist": [watch]}
    after = {**before, "financial_metrics": [_metric("ebitda_margin", "Q2FY27", 20.0, "nse-1"), _metric("revenue", "Q2FY27", 100, "nse-1")]}
    deck = _filing("nse-2", "2026-10-30T13:31:07+05:30").model_copy(update={"event_type": "CONCALL_PRESENTATION"})
    return signals._promises(before, after, _out(watches=[("w_1", status, evidence)]), deck)


def test_hdfcamc_36_bps_against_33_35_is_missed_not_met(monkeypatch):
    found = _deck_watch(monkeypatch, "33-35 bps", "Operating margin as bps of AUM within the stated corridor", "MET",
                        "Operating margin as bps of AUM reported at 36 bps for Q2FY27.")
    assert _kinds(found) == [("WATCH_RESOLVED", "WARNING")]
    assert found[0].text.startswith("KPI check missed") and "36" in found[0].text


def test_a_figure_inside_the_range_or_the_bound_keeps_met(monkeypatch):
    found = _deck_watch(monkeypatch, "33-35 bps", "Operating margin corridor", "MET", "Operating margin reported at 34 bps for Q2FY27.")
    assert found[0].text.startswith("KPI check met")
    found = _deck_watch(monkeypatch, "above 37%", "Consolidated EBITDA margin", "MET", "Consolidated EBITDA margin was 38.2% in Q2FY27, above the 37% target.")
    assert found[0].text.startswith("KPI check met")
    found = _deck_watch(monkeypatch, "above 37%", "Consolidated EBITDA margin", "MET", "Consolidated EBITDA margin was 35.0% in Q2FY27.")
    assert found[0].text.startswith("KPI check missed")


def test_the_range_check_is_only_on_the_deck_path(monkeypatch):
    monkeypatch.setenv("CARD_GUIDANCE_DATED", "1")
    watch = {"id": "w_1", "kind": "KPI", "text": "Operating margin", "check_in": "Q2FY27 results", "target": "33-35 bps",
             "check_by": "2026-09-30", "created_on": "2026-07-17T10:00:00+05:30", "status": "OPEN", "status_history": []}
    after = {"watchlist": [watch], "financial_metrics": [_metric("ebitda_margin", "Q2FY27", 20.0, NEWS)]}
    found = signals._promises({"watchlist": [watch]}, after, _out(watches=[("w_1", "MET", "Operating margin reported at 36 bps for Q2FY27.")]), _filing())
    assert found[0].text.startswith("KPI check met")


def test_numeric_target_reason_text(monkeypatch):
    for target in ("at or below ₹1.95", "target above 83,000 units", "16% or above", "above 11% YoY"):
        found = _deck_watch(monkeypatch, target, "Some metric", "MET", "Some metric was 5 in Q2FY27.")
        assert "prints no figure for the target's metric" in found[0].text, target
        assert "not a plain figure" not in found[0].text
    found = _deck_watch(monkeypatch, "breakeven or positive", "99acres operating PBT", "MET", "99acres operating PBT was positive in Q2FY27.")
    assert "the target is not a plain figure" in found[0].text


def test_tejas_a_smaller_loi_count_is_not_delivery(monkeypatch):
    monkeypatch.setenv("CARD_GUIDANCE_DATED", "1")
    monkeypatch.setenv("DECK_DISCUSSED_PERIOD", "1")
    g = _g("g_1", "BSNL 4G expansion order for additional 26,000 sites expected to be awarded", "order",
           "award of 26,000-site add-on order", "Q2FY27", "2026-09-30", "2026-08-03T10:00:00+05:30")
    after = {"guidance": [g], "financial_metrics": [_metric("order", "Q2FY27", 100, "nse-1"), _metric("revenue", "Q2FY27", 100, "nse-1")]}
    deck = _filing("nse-2", "2026-10-30T13:31:07+05:30").model_copy(update={"event_type": "CONCALL_PRESENTATION"})
    out = _out(promises=[("g_1", "DELIVERED", "Received LOI and began initial shipments for 18,685 BSNL 4G RAN add-on sites.")])
    found = signals._promises({"guidance": [g]}, after, out, deck)
    assert _kinds(found) == [("WATCH_RESOLVED", "INFO")] and "smaller count" in found[0].text
    out = _out(promises=[("g_1", "DELIVERED", "Received a 26,000 site order.")])
    assert _kinds(signals._promises({"guidance": [g]}, after, out, deck)) == [("PROMISE_DELIVERED", "POSITIVE")]


def test_numeric_contradiction_steps_aside_on_signs_and_quoted_targets():
    from bse_intel.guidance_dated import numeric_contradiction, smaller_count
    assert numeric_contradiction("at most -2%", "margin was -5%") is None
    assert numeric_contradiction("above 37%", "Delivered above 37% margin; revenue growth 12%") is None
    assert numeric_contradiction("33-35 bps", "operating margin 36 bps", "Operating margin within the corridor") is not None
    assert smaller_count("reduce receivable days to under 100 days", "92 days") is None
    assert smaller_count("limit slippages under 120 accounts", "80 accounts") is None


def test_beating_a_two_sided_range_on_its_good_side_is_no_miss():
    from bse_intel.guidance_dated import numeric_contradiction
    assert numeric_contradiction("7.0-7.5%", "Q2FY27 EBITDA margin reported at 7.9%", "EBITDA margin") is None   # SKYGOLD
    assert numeric_contradiction("7.0-7.5%", "EBITDA margin 6.4%", "EBITDA margin") is not None
    assert numeric_contradiction("1.0-1.2%", "credit cost 0.8%", "Credit cost") is None   # lower is better: below is a beat
    assert numeric_contradiction("1.0-1.2%", "credit cost 1.5%", "Credit cost") is not None
    assert numeric_contradiction("33-35 bps", "operating margin 36 bps",
                                 "Operating margin as bps of AUM within the stated corridor") is not None   # HDFCAMC
    assert numeric_contradiction("₹100-120 Cr", "cost savings of ₹135 Cr", "Cost savings programme") is None   # more is better
    assert numeric_contradiction("₹100-120 Cr", "cost savings of ₹80 Cr", "Cost savings programme") is not None
    assert numeric_contradiction("60-65", "order book of 90 days", "Order book days") is None   # not a working-capital day count
    assert numeric_contradiction("7.0-7.5%", "margin 7.9%") is None and numeric_contradiction("between 7-8%", "margin 9%") is not None
