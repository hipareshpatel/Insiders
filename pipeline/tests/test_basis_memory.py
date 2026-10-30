"""T5 (laptop, 2026-10-20): memory keeps one basis per figure, and a quarter's P&L is the results filing's."""

import pytest

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
    d = merge(d, _out(38.17), _filing("card-1", "2025-05-20T10:00:00+05:30"), None, "now", by="file")   # set-up: the consolidated figure is the file's
    seed = Pass2Output(is_material=False, timeline_entry="")
    seed.dossier_delta.financial_metrics = _out(20.51).dossier_delta.financial_metrics
    d = merge(d, seed, _filing("xbrl:res:519552:Q4FY25", "2025-06-12T18:00:00+05:30"), None, "now", basis="STANDALONE")
    assert _pat(d) == 38.17
    # the company's consolidated XBRL still outranks a card on the same basis
    d = merge(d, seed, _filing("xbrl:res:519552:Q4FY25", "2025-06-12T18:00:00+05:30"), None, "now", basis="CONSOLIDATED")
    assert _pat(d) == 20.51


@pytest.mark.switches_on("MEMORY_FILE_ONLY")
def test_a_non_results_card_neither_fills_a_missing_quarter_nor_adds_to_a_stated_one():
    d = new_dossier(_filing("a", "2025-05-20T10:00:00+05:30"))
    d = merge(d, _out(38.17), _filing("card-1", "2025-05-20T10:00:00+05:30"), None, "now", by="file")   # set-up: the file's figure
    d = merge(d, _out(20.51, "M_AND_A", None), _filing("ma-1", "2025-06-01T10:00:00+05:30", "M_AND_A"), None, "now")
    assert _pat(d) == 38.17
    entry = next(m for m in d["financial_metrics"] if m["metric"] == "pat")
    assert entry.get("source_news_id") == "card-1" and "sources" not in entry
    # a quarter no results filing has stated yet: the rights-issue card's figure does NOT fill it any more (MEMORY_FILE_ONLY,
    # owner 30 Oct 2026: statement figures enter memory only from the exchange's file); the quarter waits for its file
    d = merge(d, _out(20.48, "RIGHTS_ISSUE", None, "Q1FY27"), _filing("ri-1", "2026-10-08T10:00:00+05:30", "RIGHTS_ISSUE"),
              None, "now")
    assert not [m for m in d["financial_metrics"] if m["period"] == "Q1FY27"]


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


@pytest.mark.switches_off("CARD_GUIDANCE_DATED")   # the behaviour before the switch; the switch has its own tests
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


def test_target_checks_read_the_target_the_way_it_was_given():
    """Live review 2 (2026-10-20): CSB's GNPA 1.81% "missed" against "at or below 1.84%"; a full-year RoA target judged on
    one quarter; SML's "revenue >= 0"."""
    d = new_dossier(_filing("a", "2025-11-13T10:00:00+05:30"))
    kpis = [{"kpi": "GNPA at or below 1.84%", "metric": "gnpa_pct", "period": "Q2FY26", "value": 1.84},
            {"kpi": "RoA of ~1.5% average for the year FY26", "metric": "roa_pct", "period": "Q2FY26", "value": 1.5},
            {"kpi": "Revenue growth", "metric": "revenue", "period": "Q3FY26", "value": 0}]
    d = merge(d, _card_out("CONCALL_PRESENTATION", kpis), _filing("c1", "2025-08-13T10:00:00+05:30", "CONCALL_PRESENTATION"), None, "now")
    preds = {p["metric"]: p for p in d["predictions"]}
    assert preds["gnpa_pct"]["comparison"] == "<=" and preds["roa_pct"]["period"] == "FY26" and "revenue" not in preds
    results = _card_out(metrics=[{"metric": "gnpa_pct", "period": "Q2FY26", "value": 1.81, "unit": "PCT"},
                                 {"metric": "roa_pct", "period": "Q2FY26", "value": 1.33, "unit": "PCT"}])
    d = merge(d, results, _filing("r1", "2025-10-20T10:00:00+05:30"), None, "now")
    preds = {p["metric"]: p for p in d["predictions"]}
    assert preds["gnpa_pct"]["status"] == "MET" and preds["roa_pct"]["status"] == "OPEN"


def test_fundamentals_show_the_latest_periods_balance_sheet_not_the_latest_filed():
    """Kellton (live review 2): an annual report restating FY25, filed after the FY26 figures, put FY25 on the card."""
    from bse_intel.dossier import latest_fundamentals

    d = {"financial_metrics": [], "balance_sheet": [
        {"period": "FY26", "gross_debt_cr": 178.63, "net_worth_cr": 807.26, "as_of": "2026-05-20T10:00:00+05:30"},
        {"period": "FY25", "gross_debt_cr": 156.94, "net_worth_cr": 535.3, "as_of": "2026-08-01T10:00:00+05:30"}]}
    out = latest_fundamentals(d)
    assert out["debt"] == {"period": "FY26", "value": 178.63} and out["net_worth"]["value"] == 807.26


def test_a_presentations_annualised_eps_never_replaces_the_results_quarter():
    """Deep audit F-02: CSB Bank's concall presentation gave Q1FY27 EPS 35.00 (annualised) over the results' 8.65."""
    d = new_dossier(_filing("a", "2026-07-22T10:00:00+05:30"))
    results = _out(150.04, period="Q1FY27")
    results.dossier_delta.financial_metrics[0].metric = "eps"
    results.dossier_delta.financial_metrics[0].value = 8.65
    d = merge(d, results, _filing("r-1", "2026-07-22T12:52:52+05:30"), None, "now", by="file")   # set-up: the results quarter is the file's
    deck = _out(35.0, "CONCALL_PRESENTATION", None, period="Q1FY27")
    deck.dossier_delta.financial_metrics[0].metric = "eps"
    d = merge(d, deck, _filing("p-1", "2026-07-29T20:15:49+05:30", "CONCALL_PRESENTATION"), None, "now")
    assert next(m["value"] for m in d["financial_metrics"] if m["metric"] == "eps") == 8.65
