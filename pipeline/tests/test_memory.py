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


def test_memory_does_not_take_back_its_own_view_as_new_facts():
    """SML Mahindra: notes came back with the view's "2025-05-13: " prefix, entities with the view's
    "(type)" suffix, and one CCI approval was stored in five wordings."""
    d = new_dossier(filing("n1", Q1))
    first = output(event_type="M_AND_A", operating_notes=["Open offer price reflects a 2.4x premium over the SPA price."],
                   entities=[{"name": "SML Isuzu Limited", "type": "Target Company"}])
    first.card.track_next.pending_approvals = ["CCI approval for the open offer and SPAs (triggering control transfer)"]
    d = merge(d, first, filing("n1", Q1), "MODERATE", "now")
    again = output(event_type="M_AND_A",
                   operating_notes=["2026-07-20: Open offer price reflects a 2.4x premium over the SPA price.",
                                    "Public shareholding falls to 15% if the offer is fully accepted."],
                   entities=[{"name": "SML Isuzu Limited (Target Company)", "type": "Target Company"}])
    again.card.track_next.pending_approvals = ["Approval from Competition Commission of India (CCI) for open offer and SPAs",
                                               "Shareholder approval for the related party transactions"]
    d = merge(d, again, filing("n2", Q2), "MODERATE", "now")
    assert [n["text"] for n in d["operating_notes"]] == ["Open offer price reflects a 2.4x premium over the SPA price.",
                                                         "Public shareholding falls to 15% if the offer is fully accepted."]
    assert [e["name"] for e in d["identity"]["entities"]] == ["SML Isuzu Limited"]
    approvals = [w["text"] for w in d["watchlist"] if w["kind"] == "APPROVAL"]
    assert approvals == ["CCI approval for the open offer and SPAs (triggering control transfer)",
                         "Shareholder approval for the related party transactions"]


def test_an_approval_is_met_only_when_the_evidence_says_it_came_through():
    """SML: "Approval met: CCI approval for open offer and SPAs ... CCI approval pending"."""
    d = new_dossier(filing("n1", Q1))
    first = output(event_type="M_AND_A")
    first.card.track_next.pending_approvals = ["CCI approval for the open offer and SPAs"]
    d = merge(d, first, filing("n1", Q1), "MODERATE", "now")
    wid = next(w["id"] for w in d["watchlist"] if w["kind"] == "APPROVAL")
    pending = output(event_type="M_AND_A", watch_updates=[{"watch_id": wid, "status": "MET",
                                                           "evidence": "CCI approval pending for open offer and SPAs."}])
    assert not [s for s in compute(d, d, pending, filing("n2", Q2), {}) if s["type"] == "WATCH_RESOLVED"]
    d2 = merge(d, pending, filing("n2", Q2), "MODERATE", "now")
    assert next(w for w in d2["watchlist"] if w["id"] == wid)["status"] == "OPEN"
    granted = output(event_type="M_AND_A", watch_updates=[{"watch_id": wid, "status": "MET",
                                                           "evidence": "The Competition Commission of India approved the transaction."}])
    assert [s for s in compute(d2, d2, granted, filing("n3", Q2), {}) if s["type"] == "WATCH_RESOLVED"]
    assert next(w for w in merge(d2, granted, filing("n3", Q2), "LOW", "now")["watchlist"] if w["id"] == wid)["status"] == "MET"


def test_a_projected_or_impossible_shareholding_is_not_stored():
    d = new_dossier(filing("n1", Q1))
    projected = output(event_type="M_AND_A", ownership={"period": "May-2026", "promoter_pct": 85, "dii_pct": 40.76})
    assert merge(d, projected, filing("n1", Q1), "LOW", "now")["ownership"] == []
    impossible = output(event_type="RESULTS", ownership={"period": "Q1FY27", "promoter_pct": 85, "fii_pct": 10, "dii_pct": 40})
    assert merge(d, impossible, filing("n1", Q1), "LOW", "now")["ownership"] == []
    real = output(event_type="RESULTS", ownership={"period": "Q1FY27", "promoter_pct": 58.96, "fii_pct": 0.27, "dii_pct": 12.1})
    assert merge(d, real, filing("n1", Q1), "LOW", "now")["ownership"][0]["promoter_pct"] == 58.96


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
    # The value is the later restatement; the figure counts as known since the first filing (bi-temporal).
    assert pat["value"] == 9 and pat["value_news_id"] == "n2"
    assert pat["as_of"] == Q1 and pat["source_news_id"] == "n1" and len(pat["sources"]) == 2


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
    company = {"shares_outstanding": 10_00_00_000, "last_price": 100, "price_date": Q2[:10]}
    (signal,) = compute(d, after, out, filing("n2", Q2), company)
    assert signal["type"] == "DILUTION" and signal["severity"] == "WARNING"
    assert "25.0% more shares (20.0% post-money dilution" in signal["text"] and "20.0% below" in signal["text"]
    # A backfilled card is not compared with today's price.
    (old,) = compute(d, after, out, filing("n2", Q2), {**company, "price_date": "2027-03-01"})
    assert "below" not in old["text"]
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
    assert [f.text for f in out.card.what_happened] == ["Acquisition of 100% stake", "Consideration in cash"]
    assert [f.quote for f in out.card.what_happened] == [None, None]  # a bare string still parses: the checks hold it
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


def test_footer_shows_the_sector_metric_only_in_the_unit_its_label_promises():
    from bse_intel.dossier import latest_fundamentals

    d = new_dossier(filing("n1", Q2))
    d["financial_metrics"] = [
        {"metric": "gnpa", "period": "Q2FY27", "value": 2345.0, "unit": "INR_CR", "as_of": Q2},  # an amount, not a ratio
        {"metric": "gnpa_pct", "period": "Q1FY27", "value": 2.1, "unit": "PCT", "as_of": Q1},
        {"metric": "nim", "period": "Q2FY27", "value": 3.4, "unit": "PCT", "as_of": Q2},
        {"metric": "arpu", "period": "Q2FY27", "value": 211.0, "unit": "INR", "as_of": Q2},
    ]
    bank = ({"metric": "gnpa", "label": "GNPA", "format": "pct", "aliases": ["gnpa_pct"]},
            {"metric": "nim", "label": "NIM", "format": "pct"})
    assert latest_fundamentals(d, bank)["kpis"] == [
        {"label": "GNPA", "format": "pct", "period": "Q1FY27", "value": 2.1},
        {"label": "NIM", "format": "pct", "period": "Q2FY27", "value": 3.4},
    ]
    telecom = ({"metric": "arpu", "label": "ARPU", "format": "inr"},)
    assert latest_fundamentals(d, telecom)["kpis"][0]["value"] == 211.0
    assert "kpis" not in latest_fundamentals(d, ({"metric": "revpar", "label": "RevPAR", "format": "inr"},))


def test_comparatives_do_not_move_known_since_and_backfill_sees_no_future():
    from bse_intel.dossier import dossier_as_of, latest_fundamentals

    d = merge(new_dossier(filing("q1", Q1)), output(financial_metrics=[{"metric": "revenue", "period": "Q1FY27", "value": 100}]),
              filing("q1", Q1), "HIGH", "now")
    d = merge(d, output(financial_metrics=[{"metric": "revenue", "period": "Q2FY27", "value": 130},
                                            {"metric": "revenue", "period": "Q1FY27", "value": 101}]),
              filing("q2", Q2), "HIGH", "now")
    (q1,) = [m for m in d["financial_metrics"] if m["period"] == "Q1FY27"]
    assert q1["as_of"] == Q1 and q1["value"] == 101
    # As of the Q1 filing: Q2 does not exist yet, and Q1 has its original value.
    then = dossier_as_of(d, Q1)
    assert [(m["period"], m["value"]) for m in then["financial_metrics"]] == [("Q1FY27", 100)]
    assert latest_fundamentals(then)["revenue"] == {"period": "Q1FY27", "value": 100}
    # Re-analysing Q2 keeps Q1's first value.
    d = merge(d, output(financial_metrics=[]), filing("q2", Q2), "HIGH", "now")
    assert [(m["period"], m["value"], m["source_news_id"]) for m in d["financial_metrics"]] == [("Q1FY27", 100, "q1")]


def test_a_long_annual_table_does_not_push_out_recent_quarters():
    from bse_intel.dossier import view_as_of

    quarters = [{"metric": "revenue", "period": f"Q{q}FY27", "value": 100 + q} for q in (1, 2)]
    years = [{"metric": "revenue", "period": f"FY{y}", "value": 300 + y} for y in range(10, 27)]
    d = merge(new_dossier(filing("n1", Q1)), output(financial_metrics=quarters), filing("n1", Q1), "HIGH", "now")
    d = merge(d, output(financial_metrics=years), filing("ppt", Q2), "LOW", "now")
    kinds = [m["period"] for m in d["financial_metrics"]]
    assert "Q1FY27" in kinds and "Q2FY27" in kinds and sum(p.startswith("FY") for p in kinds) == 6
    lines = view_as_of(d, "2027-01-01T00:00:00+05:30")["metrics"]["revenue"]
    assert any(line.startswith("Q2FY27") for line in lines)


def test_reanalysing_the_filing_that_set_guidance_keeps_later_status():
    agm = filing("agm", AGM)
    d = merge(new_dossier(agm), output(event_type="CONCALL_PRESENTATION",
              guidance=[{"statement": "Commission Ankleshwar plant", "due": "Q3FY27"}]), agm, "MODERATE", "now")
    gid = d["guidance"][0]["id"]
    d = merge(d, output(promise_updates=[{"guidance_id": gid, "status": "DELIVERED", "evidence": "commissioned"}]),
              filing("n9", Q2), "HIGH", "now")
    d = merge(d, output(event_type="CONCALL_PRESENTATION",
              guidance=[{"statement": "Commission Ankleshwar plant", "due": "Q3FY27"}]), agm, "MODERATE", "now")
    (g,) = d["guidance"]
    assert g["status"] == "DELIVERED" and len(g["status_history"]) == 1


def test_metric_shift_ignores_comparative_columns():
    d = merge(new_dossier(filing("q1", Q1)), output(financial_metrics=[
        {"metric": "pat", "period": "Q1FY26", "value": 10}, {"metric": "pat", "period": "Q1FY27", "value": 25}]),
        filing("q1", Q1), "HIGH", "now")
    out = output(financial_metrics=[{"metric": "pat", "period": "Q2FY27", "value": 26},
                                    {"metric": "pat", "period": "Q2FY26", "value": 24},
                                    {"metric": "pat", "period": "Q1FY27", "value": 25}])
    after = merge(d, out, filing("q2", Q2), "HIGH", "now")
    texts = [s["text"] for s in compute(d, after, out, filing("q2", Q2), {}) if s["type"] == "METRIC_SHIFT"]
    assert not any("Q1FY27" in t for t in texts)


def test_predictions_resolve_against_reported_figures_and_feed_credibility():
    from bse_intel.scoring import credibility

    d = merge(new_dossier(filing("call", Q1)), Pass2Output.model_validate({
        "is_material": True, "event_type": "CONCALL_PRESENTATION",
        "card": {"impact_level": "MODERATE", "headline": "Demo Cement guides lower interest after rights issue", "what_happened": ["x"],
                 "track_next": {"kpis_to_verify": [{"kpi": "Quarterly interest below ₹16 Cr", "metric": "finance_cost",
                                                    "period": "Q2 FY27", "value": 16, "comparison": "below"}]}}}),
        filing("call", Q1), "MODERATE", "now")
    assert d["predictions"][0]["status"] == "OPEN" and d["predictions"][0]["comparison"] == "<="
    out = output(financial_metrics=[{"metric": "finance_cost", "period": "Q2FY27", "value": 14.2}])
    after = merge(d, out, filing("q2", Q2), "HIGH", "now")
    (p,) = after["predictions"]
    assert p["status"] == "MET" and p["actual"] == 14.2
    signals = compute(d, after, out, filing("q2", Q2), {})
    assert any(s["type"] == "PREDICTION_RESOLVED" and s["severity"] == "POSITIVE" for s in signals)
    assert credibility(after)[0] == 100.0
    # re-analysing the results filing reopens it
    again = merge(after, output(financial_metrics=[]), filing("q2", Q2), "HIGH", "now")
    assert again["predictions"][0]["status"] == "OPEN"


def test_monthly_volume_streak_and_quarter_preview():
    months = [("JUL-2025", 800), ("AUG-2025", 750), ("SEP-2025", 812), ("JUL-2026", 1000), ("AUG-2026", 1008)]
    d = merge(new_dossier(filing("m0", Q1)), output(event_type="MONTHLY_BUSINESS_UPDATE",
              financial_metrics=[{"metric": "sales_volume", "period": p, "value": v, "unit": "UNITS"} for p, v in months]),
              filing("m0", Q1), "LOW", "now")
    out = output(event_type="MONTHLY_BUSINESS_UPDATE", financial_metrics=[
        {"metric": "sales_volume", "period": "Sep-2026", "value": 1071, "unit": "UNITS"},
        {"metric": "sales_volume", "period": "Sep-2025", "value": 812, "unit": "UNITS"}])
    after = merge(d, out, filing("sep", Q2), "MODERATE", "now")
    kinds = {s["type"]: s for s in compute(d, after, out, filing("sep", Q2), {})}
    assert "2 months running" in kinds["VOLUME_STREAK"]["text"]  # Aug +34.4%, Sep +31.9% (July is exactly 25%)
    assert "3,079 vs 2,362" in kinds["QUARTER_PREVIEW"]["text"]


def test_auditor_qualification_and_ownership_shift():
    d = merge(new_dossier(filing("s1", Q1)), output(ownership={"period": "Jun-2026", "promoter_pct": 55, "fii_pct": 5, "dii_pct": 4,
                                                               "retail_holders": 40000}), filing("s1", Q1), "LOW", "now")
    out = output(ownership={"period": "Sep-2026", "promoter_pct": 55.5, "fii_pct": 6, "dii_pct": 4.5, "retail_holders": 36000},
                 auditor={"name": "X & Co", "opinion": "qualified", "note": "₹42 Cr receivable"})
    after = merge(d, out, filing("s2", Q2), "HIGH", "now")
    kinds = {s["type"]: s for s in compute(d, after, out, filing("s2", Q2), {})}
    assert kinds["OWNERSHIP_SHIFT"]["severity"] == "POSITIVE" and kinds["AUDIT_FLAG"]["severity"] == "WARNING"


def test_rights_entitlement_ratio_gives_dilution_without_a_share_count():
    out = output(event_type="RIGHTS_ISSUE", capital_actions=[{"instrument": "Rights issue", "ratio": "19:25", "issue_price": 12}])
    d = new_dossier(filing("r0", Q1))
    after = merge(d, out, filing("r1", Q2), "MODERATE", "now")
    (s,) = [s for s in compute(d, after, out, filing("r1", Q2), {}) if s["type"] == "DILUTION"]
    assert "76.0% more shares (43.2% post-money dilution)" in s["text"] and s["severity"] == "WARNING"


def test_period_spellings_land_on_one_dossier_row():
    from bse_intel.periods import due_date

    d = merge(new_dossier(filing("a", Q1)), output(financial_metrics=[{"metric": "revenue", "period": "Q2 FY 2026-27", "value": 1}]),
              filing("a", Q1), "LOW", "now")
    d = merge(d, output(financial_metrics=[{"metric": "revenue", "period": "Q2FY2027", "value": 2}]), filing("b", Q2), "LOW", "now")
    assert [(m["period"], m["value"]) for m in d["financial_metrics"]] == [("Q2FY27", 2)]
    assert str(due_date("FY2026-27")) == "2027-03-31" and str(due_date("November 15, 2026")) == "2026-11-15"
    assert str(due_date("30-09-2026")) == "2026-09-30" and str(due_date("Q2-FY27")) == "2026-09-30"


def test_an_ownership_block_without_a_quarter_end_is_dropped_not_failed():
    assert output(ownership={"period": None, "promoter_pct": None}).dossier_delta.ownership is None
    assert output(ownership={"period": 202609, "promoter_pct": 51}).dossier_delta.ownership.period == "202609"


def test_kpi_verdict_is_checked_in_code():
    """"Cement EBITDA/tonne of ₹701 in Q2FY26 is below the >=700 target for Q3FY26" came back MISSED:
    701 meets ">=700", and a Q2FY26 figure does not settle a Q3FY26 check."""
    from bse_intel.dossier import kpi_verdict

    w = {"kind": "KPI", "text": "Cement EBITDA/tonne", "check_in": "Q3FY26 results", "target": ">=700"}
    assert kpi_verdict(w, "MISSED", "Cement EBITDA/tonne of ₹701 in Q2FY26 is below the >=700 target for Q3FY26.") == "PENDING"
    assert kpi_verdict(w, "MISSED", "Cement EBITDA/tonne of ₹701 in Q3FY26 vs the >=700 target.") == "MET"
    assert kpi_verdict(w, "MET", "Q3FY26 EBITDA/tonne ₹655, short of the ₹700 target") == "MISSED"
    assert kpi_verdict(w, "MET", "EBITDA per tonne improved as guided") == "MET"  # no figure: the model's call stands
    assert kpi_verdict({**w, "target": "Disclosed"}, "MISSED", "Order book not disclosed in Q3FY26") == "MISSED"
    assert kpi_verdict({**w, "kind": "APPROVAL"}, "MET", "anything") == "MET"


def test_watch_verdicts_without_news_or_about_another_item_stay_pending():
    """From the smoke test's follow-ups: "missed ... not disclosed; watchlist item overdue", "met ... no
    update in filing; assumed resolved", and a debt/EBITDA check answered with a director's appointment."""
    from bse_intel.dossier import watch_verdict

    kpi = {"kind": "KPI", "text": "Cement segment EBITDA/tonne recovery", "check_in": "Q1FY26", "target": ">0"}
    assert watch_verdict(kpi, "MISSED", "Cement EBITDA/tonne not disclosed in Q1FY26 results; watchlist item overdue.") == "PENDING"
    gst = {"kind": "KPI", "text": "GST refund status", "check_in": None, "target": None}
    assert watch_verdict(gst, "MET", "No GST refund status update in filing; assumed resolved or not material.") == "PENDING"
    debt = {"kind": "KPI", "text": "Debt/EBITDA ratio", "check_in": None, "target": None}
    assert watch_verdict(debt, "MET", "Dr. Rao's WTD appointment requires AGM approval (July 31, 2025).") == "PENDING"
    de = {"kind": "KPI", "text": "Debt-to-equity ratio", "check_in": "Q2FY26", "target": "<=2"}
    assert watch_verdict(de, "MISSED", "Debt-to-equity ratio of 0.6x in Q2FY26 is lower than the <=2 target.") == "MET"


def test_reduction_targets_compare_downwards_and_off_scale_targets_are_dropped():
    from bse_intel.dossier import _LOWER_IS_BETTER, _plausible_target

    d = {"financial_metrics": [{"metric": "net_worth", "period": "Q3FY25", "value": 1357.5, "as_of": "2025-01-28"}]}
    assert not _plausible_target(d, "net_worth", 128.1)  # a tax refund, not a net-worth target
    assert _plausible_target(d, "net_worth", 1459) and _plausible_target(d, "ebitda", 5)  # no history: kept
    assert _LOWER_IS_BETTER.search("Net debt reduction") and not _LOWER_IS_BETTER.search("Revenue growth")


def test_a_flow_figure_that_breaks_the_cumulative_identity_is_reported():
    """Indian results accumulate over the year, so H1 = Q1 + Q2 and FY = 9M + Q4 for any flow. Audit round 1
    traced every wrong Kanoria YoY to one figure in memory that broke this: Q1FY26 revenue stored as 453.78
    where H1 minus Q2 gives 201.38. The check needs no PDF and no AI, only the arithmetic."""
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "memory_check", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "memory_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def metric(name, period, value, source="xbrl:res:1"):
        return {"metric": name, "period": period, "value": value, "unit": "INR_CR", "source_news_id": source}

    broken = [metric("revenue", "Q1FY26", 453.78, "card-1"), metric("revenue", "Q2FY26", 209.84),
              metric("revenue", "H1FY26", 411.22)]
    found = mod.problems("506525", broken)
    assert len(found) == 1 and found[0]["period"] == "H1FY26"
    assert found[0]["parts_sum"] == 663.62 and found[0]["difference"] == -252.4
    assert "card-1" in found[0]["sources"]

    # the same series with the figure H1 implies, and a balance that must never be summed
    fixed = [metric("revenue", "Q1FY26", 201.38), metric("revenue", "Q2FY26", 209.84),
             metric("revenue", "H1FY26", 411.22),
             metric("paid_up_capital", "Q1FY26", 12.34), metric("paid_up_capital", "Q2FY26", 12.34),
             metric("paid_up_capital", "H1FY26", 12.34)]
    assert mod.problems("506525", fixed) == []
