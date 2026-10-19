"""T5 (laptop, 2026-10-20): memory keeps one basis per figure, and a quarter's P&L is the results filing's."""

from bse_intel.dossier import merge, new_dossier
from bse_intel.models import Filing, Pass2Output


def _filing(news_id: str, when: str, event_type: str = "RESULTS") -> Filing:
    return Filing(news_id=news_id, scrip_code="519552", company_name="Heritage Foods Ltd", headline="h", subject="",
                  filed_at=when, filing_date=when[:10], event_type=event_type)


def _out(value: float, event_type: str = "RESULTS", basis: str | None = "CONSOLIDATED", period: str = "Q4FY25") -> Pass2Output:
    return Pass2Output.model_validate({
        "is_material": True, "event_type": event_type, "timeline_entry": "t",
        "card": {"headline": "Heritage Foods quarterly results filed", "impact_level": "MODERATE", "takeaway": "t",
                 "what_happened": ["The company filed its results."], "basis": basis},
        "dossier_delta": {"financial_metrics": [{"metric": "pat", "period": period, "value": value}]}})


def _pat(d: dict, period: str = "Q4FY25") -> float:
    return next(m["value"] for m in d["financial_metrics"] if m["metric"] == "pat" and m["period"] == period)


def test_a_standalone_xbrl_file_does_not_outrank_consolidated_cards():
    d = new_dossier(_filing("a", "2025-05-20T10:00:00+05:30"))
    d = merge(d, _out(38.17), _filing("card-1", "2025-05-20T10:00:00+05:30"), None, "now")
    seed = Pass2Output(is_material=False, timeline_entry="")
    seed.dossier_delta.financial_metrics = _out(20.51).dossier_delta.financial_metrics
    d = merge(d, seed, _filing("xbrl:res:519552:Q4FY25", "2025-06-12T18:00:00+05:30"), None, "now", basis="STANDALONE")
    assert _pat(d) == 38.17
    # the company's consolidated XBRL still outranks a card on the same basis
    d = merge(d, seed, _filing("xbrl:res:519552:Q4FY25", "2025-06-12T18:00:00+05:30"), None, "now", basis="CONSOLIDATED")
    assert _pat(d) == 20.51


def test_a_non_results_card_fills_a_missing_quarter_but_never_adds_to_a_stated_one():
    d = new_dossier(_filing("a", "2025-05-20T10:00:00+05:30"))
    d = merge(d, _out(38.17), _filing("card-1", "2025-05-20T10:00:00+05:30"), None, "now")
    d = merge(d, _out(20.51, "M_AND_A", None), _filing("ma-1", "2025-06-01T10:00:00+05:30", "M_AND_A"), None, "now")
    assert _pat(d) == 38.17
    entry = next(m for m in d["financial_metrics"] if m["metric"] == "pat")
    assert entry.get("source_news_id") == "card-1" and "sources" not in entry
    # a quarter no results filing has stated yet: the rights-issue card's figure is all there is
    d = merge(d, _out(20.48, "RIGHTS_ISSUE", None, "Q1FY27"), _filing("ri-1", "2026-10-08T10:00:00+05:30", "RIGHTS_ISSUE"),
              None, "now")
    assert _pat(d, "Q1FY27") == 20.48


def _card_out(event_type: str = "RESULTS", kpis=(), guidance=(), updates=(), metrics=()) -> Pass2Output:
    return Pass2Output.model_validate({
        "is_material": True, "event_type": event_type, "timeline_entry": "t",
        "card": {"headline": "Heritage Foods quarterly results filed", "impact_level": "MODERATE", "takeaway": "t",
                 "what_happened": ["The company filed its results."],
                 "track_next": {"kpis_to_verify": list(kpis)}},
        "dossier_delta": {"guidance": list(guidance), "promise_updates": list(updates), "financial_metrics": list(metrics)}})


def test_one_open_target_per_metric_and_period_and_not_reported_once_the_window_passes():
    d = new_dossier(_filing("a", "2026-07-16T10:00:00+05:30"))
    for i, (value, when) in enumerate(((38, "2026-07-16"), (48, "2026-07-20"), (49, "2026-07-21"))):
        kpi = {"kpi": "VAP share", "metric": "vap_share_pct", "period": "Q2FY27", "value": value, "comparison": ">="}
        d = merge(d, _card_out("CONCALL_PRESENTATION", [kpi]), _filing(f"c{i}", f"{when}T10:00:00+05:30", "CONCALL_PRESENTATION"),
                  None, "now")
    (open_,) = [p for p in d["predictions"] if p["status"] == "OPEN"]
    assert open_["value"] == 49 and len(d["predictions"]) == 1
    # Q2FY27 ends 30 Sep; its results and call are in by mid-December: a later filing marks it not reported
    d = merge(d, _card_out("ORDER_WIN"), _filing("o1", "2026-12-20T10:00:00+05:30", "ORDER_WIN"), None, "now")
    assert d["predictions"][0]["status"] == "NOT_REPORTED"


def test_guidance_said_twice_is_one_and_past_its_deadline_is_never_on_track():
    g = {"statement": "Revenue of Rs 6,000 Cr in FY27", "metric": "revenue", "target": "6,000 Cr", "due": "FY27"}
    d = new_dossier(_filing("a", "2025-05-21T10:00:00+05:30"))
    d = merge(d, _card_out(guidance=[g]), _filing("g1", "2025-05-21T10:00:00+05:30"), None, "now")
    again = g | {"statement": "Targets ₹6,000 Cr revenue by FY27"}
    d = merge(d, _card_out(guidance=[again]), _filing("g2", "2026-05-14T10:00:00+05:30"), None, "now")
    (entry,) = d["guidance"]
    assert entry["repeated"][0]["source_news_id"] == "g2"
    milk = {"statement": "2 MLPD milk procurement by FY26", "metric": "milk_procurement", "target": "2 MLPD", "due": "FY26"}
    d = merge(d, _card_out(guidance=[milk]), _filing("g3", "2025-08-01T10:00:00+05:30"), None, "now")
    gid = next(x["id"] for x in d["guidance"] if x["statement"].startswith("2 MLPD"))
    late = {"guidance_id": gid, "status": "ON_TRACK", "evidence": "procurement rising"}
    d = merge(d, _card_out(updates=[late]), _filing("r1", "2026-10-15T10:00:00+05:30"), None, "now")
    assert next(x for x in d["guidance"] if x["id"] == gid)["status_history"] == []
    missed = late | {"status": "MISSED", "evidence": "1.6 MLPD in FY26"}
    d = merge(d, _card_out(updates=[missed]), _filing("r2", "2026-10-16T10:00:00+05:30"), None, "now")
    assert next(x for x in d["guidance"] if x["id"] == gid)["status"] == "MISSED"
