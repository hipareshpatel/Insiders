from __future__ import annotations

from bse_intel.dossier import memory_ids, merge, new_dossier, view_as_of
from bse_intel.grounding import check_card
from bse_intel.models import Card, Filing, Pass2Output
from bse_intel.signals import compute


def filing(news_id: str, filed_at: str, scrip: str = "999001") -> Filing:
    return Filing(news_id=news_id, scrip_code=scrip, company_name="Demo Cement Ltd", headline="h",
                  filed_at=filed_at, filing_date=filed_at[:10])


def output(**delta) -> Pass2Output:
    return Pass2Output.model_validate({
        "is_material": True, "event_type": delta.pop("event_type", "RESULTS"),
        "card": {"impact_level": "HIGH", "headline": "Demo Cement revenue up 32% to ₹120 Cr",
                 "what_happened": ["Revenue ₹120 Cr"]},
        "timeline_entry": delta.pop("timeline", "Q2 results"),
        "dossier_delta": delta,
    })


Q1 = "2026-07-20T17:00:00+05:30"
Q2 = "2026-10-20T17:00:00+05:30"
AGM = "2026-08-25T11:00:00+05:30"


def test_merge_stamps_provenance_and_is_idempotent():
    d0 = new_dossier(filing("n1", Q1))
    out = output(financial_metrics=[{"metric": "Revenue", "period": "Q1 FY27", "value": "₹1,10.5 Cr"}])
    d1 = merge(d0, out, filing("n1", Q1), "HIGH", "now")
    (metric,) = d1["financial_metrics"]
    assert metric == {"metric": "revenue", "period": "Q1FY27", "value": 110.5, "unit": "INR_CR", "yoy_pct": None,
                      "qoq_pct": None, "as_of": Q1, "source_news_id": "n1"}
    assert d1["timeline"][0]["news_id"] == "n1"
    assert d0["financial_metrics"] == []  # input not mutated
    d2 = merge(d1, out, filing("n1", Q1), "HIGH", "now")
    assert d2["financial_metrics"] == d1["financial_metrics"] and len(d2["timeline"]) == 1


def test_older_filing_never_overrides_a_later_restatement():
    d = merge(new_dossier(filing("n2", Q2)), output(financial_metrics=[{"metric": "pat", "period": "Q1FY27", "value": 9}]),
              filing("n2", Q2), "HIGH", "now")
    d = merge(d, output(financial_metrics=[{"metric": "pat", "period": "Q1FY27", "value": 10}]),
              filing("n1", Q1), "HIGH", "now")
    (pat,) = [m for m in d["financial_metrics"] if m["metric"] == "pat"]
    assert pat["value"] == 9 and pat["source_news_id"] == "n2"


def test_guidance_promise_tracking_and_hallucinated_ids():
    d = merge(new_dossier(filing("agm", AGM)),
              output(event_type="CONCALL_PRESENTATION",
                     guidance=[{"statement": "Commission Ankleshwar plant", "due": "Q3FY27", "source_type": "agm"}]),
              filing("agm", AGM), "MODERATE", "now")
    (g,) = d["guidance"]
    assert g["id"].startswith("g_") and g["due_date"] == "2026-12-31" and g["source_news_id"] == "agm"
    before = d
    out = output(promise_updates=[{"guidance_id": g["id"], "status": "delivered", "evidence": "plant commissioned"},
                                  {"guidance_id": "g_deadbeef", "status": "MISSED"}])
    d = merge(d, out, filing("n2", Q2), "HIGH", "now")
    assert d["guidance"][0]["status"] == "DELIVERED"
    signals = compute(before, d, out, filing("n2", Q2), {})
    assert [s["type"] for s in signals] == ["PROMISE_DELIVERED"]


def test_view_as_of_hides_future_facts():
    d = merge(new_dossier(filing("n1", Q1)), output(financial_metrics=[{"metric": "revenue", "period": "Q1FY27", "value": 110}]),
              filing("n1", Q1), "HIGH", "now")
    d = merge(d, output(financial_metrics=[{"metric": "revenue", "period": "Q2FY27", "value": 120}],
                        guidance=[{"statement": "Margins to reach 20%", "due": "FY27"}]),
              filing("n2", Q2), "HIGH", "now")
    early = view_as_of(d, "2026-09-01T00:00:00+05:30")
    assert early["metrics"]["revenue"] == ["Q1FY27: 110 INR_CR"]
    assert "guidance" not in early
    late = view_as_of(d, "2026-12-01T00:00:00+05:30")
    assert late["metrics"]["revenue"] == ["Q1FY27: 110 INR_CR", "Q2FY27: 120 INR_CR"]
    assert memory_ids(late) >= {late["guidance"][0]["id"]}
    assert view_as_of(None, Q1) is None


def test_overdue_guidance_is_flagged():
    d = merge(new_dossier(filing("agm", AGM)), output(guidance=[{"statement": "Start new line", "due": "Sep-2026"}]),
              filing("agm", AGM), "LOW", "now")
    view = view_as_of(d, Q2)
    assert view["guidance"][0]["overdue"] is True
    out = output()
    after = merge(d, out, filing("n2", Q2), "HIGH", "now")
    signals = compute(d, after, out, filing("n2", Q2), {})
    assert signals[0]["type"] == "GUIDANCE_BREACH" and "Deadline passed" in signals[0]["text"]


def test_dilution_signal_is_computed_not_guessed():
    d = new_dossier(filing("n1", Q1))
    d["balance_sheet"] = [{"net_worth_cr": 500, "as_of": "2026-05-01T00:00:00+05:30"}]
    out = output(event_type="RIGHTS_ISSUE",
                 capital_actions=[{"instrument": "Rights issue", "new_shares": "2,50,00,000", "issue_price": "80"}])
    after = merge(d, out, filing("n2", Q2), "HIGH", "now")
    (signal,) = compute(d, after, out, filing("n2", Q2), {"shares_outstanding": 10_00_00_000, "last_price": 100})
    assert signal["type"] == "DILUTION" and signal["severity"] == "WARNING"
    assert "25.0% dilution" in signal["text"] and "20.0% below" in signal["text"]
    assert "1.60x book value" in signal["text"]  # BVPS = 500 Cr / 10 Cr shares = ₹50


def test_working_capital_strain_and_generic_metric_shift():
    d = merge(new_dossier(filing("n0", Q1)), output(financial_metrics=[
        {"metric": "revenue", "period": "H1FY26", "value": 100},
        {"metric": "trade_receivables", "period": "H1FY26", "value": 40},
        {"metric": "gross_debt", "period": "H1FY26", "value": 50},
        {"metric": "ebitda_margin", "period": "H1FY26", "value": 18, "unit": "PCT"},
    ]), filing("n0", "2025-10-20T17:00:00+05:30"), "HIGH", "now")
    out = output(financial_metrics=[
        {"metric": "revenue", "period": "H1FY27", "value": 120},
        {"metric": "trade_receivables", "period": "H1FY27", "value": 64},
        {"metric": "gross_debt", "period": "H1FY27", "value": 90},
        {"metric": "ebitda_margin", "period": "H1FY27", "value": 14.5, "unit": "PCT"},
        {"metric": "revenue", "period": "Q2FY27", "value": 70},  # no comparable quarter: must not be compared to H1
    ])
    after = merge(d, out, filing("n2", Q2), "HIGH", "now")
    signals = compute(d, after, out, filing("n2", Q2), {})
    by_type = {}
    for s in signals:
        by_type.setdefault(s["type"], []).append(s)
    assert "Receivables up 60% YoY vs revenue +20%" in by_type["WORKING_CAPITAL_STRAIN"][0]["text"]
    shifts = " | ".join(s["text"] for s in by_type["METRIC_SHIFT"])
    assert "Gross debt up 80% YoY" in shifts and "EBITDA margin down 350 bps YoY" in shifts
    assert all(s["severity"] == "WARNING" for s in by_type["METRIC_SHIFT"])
    assert "Q2FY27" not in shifts and "Trade receivables" not in shifts


def test_grounding_handles_units_rounding_and_derived_percentages():
    source = "Revenue from operations 12,345.67 (lakhs) against 9,352.78 in the previous year. EBITDA 2,100.50"
    card = Card.model_validate({"impact_level": "HIGH", "headline": "Revenue up 32% YoY to ₹123 Cr",
                                "what_happened": ["Revenue ₹123.46 Cr vs ₹93.5 Cr", "EBITDA ₹21 Cr in Q2FY27"]})
    result = check_card(card, source)
    assert result.ok and result.ungrounded == [], result
    bad = Card.model_validate({"impact_level": "HIGH", "headline": "Revenue up 32% YoY to ₹456 Cr",
                               "what_happened": ["Order book ₹9,999 Cr"]})
    result = check_card(bad, source)
    assert not result.ok and "456" in result.ungrounded and "9,999" in result.ungrounded


def test_lenient_model_parsing():
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "M&A",
        "card": {"impact_level": "high impact", "headline": "Acquires Demo Chem for ₹300 Cr",
                 "what_happened": "Acquisition of 100% stake\n- Consideration in cash",
                 "why_it_matters": ["Adds capacity"], "notable_changes": [{"metric": "net debt", "direction": "adverse"}, "junk"]},
        "dossier_delta": {"financial_metrics": [{"metric": "x"}, {"metric": "revenue", "period": "FY26", "value": "(12.5)"}],
                          "upcoming_events": [{"event_type": "record date", "date": "2026-13-01"},
                                              {"event_type": "record date", "date": "2026-11-05"}]},
    })
    assert out.event_type == "M_AND_A" and out.card.impact_level == "HIGH"
    assert out.card.what_happened == ["Acquisition of 100% stake", "Consideration in cash"]
    assert out.card.why_it_matters[0].basis == "FILING"
    assert out.card.notable_changes[0].direction == "NEGATIVE" and len(out.card.notable_changes) == 1
    assert [m.value for m in out.dossier_delta.financial_metrics] == [-12.5]
    assert [e.event_type for e in out.dossier_delta.upcoming_events] == ["RECORD_DATE"]
    assert out.timeline_entry == "Acquires Demo Chem for ₹300 Cr"


def test_track_next_becomes_watch_items_that_later_filings_resolve():
    capex = Pass2Output.model_validate({
        "is_material": True, "event_type": "CAPEX",
        "card": {"impact_level": "HIGH", "headline": "Demo Chem commissions 12 TPD Triacetin plant",
                 "what_happened": ["Commissioned 12 TPD plant"],
                 "track_next": {"kpis_to_verify": [{"kpi": "Specialty share of revenue", "check_in": "Q3FY27 results",
                                                    "target": "above 40%"}],
                                "pending_approvals": ["Consent to operate from GPCB"],
                                "milestones": [{"what": "First dispatches", "when": "Nov 2026", "date": "not a date"}]}},
        "timeline_entry": "Commissioned plant",
    })
    d = merge(new_dossier(filing("cap", Q1)), capex, filing("cap", Q1), "HIGH", "now")
    kpi, approval = d["watchlist"]
    assert kpi["kind"] == "KPI" and kpi["check_by"] == "2026-12-31" and approval["kind"] == "APPROVAL"
    assert capex.card.track_next.milestones[0].date is None
    view = view_as_of(d, Q2)
    assert {w["id"] for w in view["watchlist"]} == {kpi["id"], approval["id"]}
    assert kpi["id"] in memory_ids(view)

    results = output(watch_updates=[{"watch_id": kpi["id"], "status": "achieved", "evidence": "Specialty at 43%"}])
    after = merge(d, results, filing("q3", "2027-01-25T17:00:00+05:30"), "HIGH", "now")
    assert next(w for w in after["watchlist"] if w["id"] == kpi["id"])["status"] == "MET"
    signals = compute(d, after, results, filing("q3", "2027-01-25T17:00:00+05:30"), {})
    resolved = [s for s in signals if s["type"] == "WATCH_RESOLVED"]
    assert resolved and resolved[0]["severity"] == "POSITIVE" and "Specialty at 43%" in resolved[0]["text"]
    later = view_as_of(after, "2027-02-01T00:00:00+05:30")
    assert [w["id"] for w in later["watchlist"]] == [approval["id"]]


def test_grounding_accepts_bps_and_percentage_point_changes():
    source = "EBITDA margin 14.9% vs 18.6%. Revenue 455.60 vs 380.90"
    card = Card.model_validate({"impact_level": "HIGH", "headline": "Margin down 370 bps to 14.9%",
                                "what_happened": ["EBITDA margin -370 bps YoY", "Margin fell 3.7 percentage points"],
                                "key_numbers": [{"label": "EBITDA margin", "value": "14.9%", "change": "-370 bps"}]})
    result = check_card(card, source)
    assert result.ungrounded == [], result
    assert not check_card(Card.model_validate({"impact_level": "LOW", "headline": "Margin down 900 bps",
                                               "what_happened": ["x"]}), source).ok
