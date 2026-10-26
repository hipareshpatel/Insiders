"""F156 (CARD_GUIDANCE_DATED): a guidance verdict only from a dated target for this filing's period and metric.
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
    assert "not a plain figure" in found[0].text
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
