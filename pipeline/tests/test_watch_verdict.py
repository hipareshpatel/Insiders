"""F205 (CARD_WATCH_VERDICT, TODO 106): code decides a KPI watch MET / MISSED / NOT_DUE from memory's figure for the watch's one
metric and one period, never from evidence text. The four live cards of the 26 Oct 2026 audit, and every wrong verdict and wrong
cut the four reviews of the earlier text-parsing design found."""

from __future__ import annotations

import pytest

from bse_intel import signals, watch_code as wc
from bse_intel.models import Filing, Pass2Output

N = "nse-1"
WHEN = "2026-10-24T15:00:00+05:30"


def M(metric, period, value, unit="INR_CR", basis="CONSOLIDATED", **extra):
    return {"metric": metric, "period": period, "value": value, "unit": unit, "as_of": WHEN, "source_news_id": N,
            **({"basis": basis} if basis else {}), **extra}


def W(text, target, check_in="Q2FY27 results", **extra):
    return {"id": "w", "kind": "KPI", "text": text, "target": target, "check_in": check_in, "check_by": "2026-09-30",
            "created_on": "2026-07-20T10:00:00+05:30", "status": "OPEN", "status_history": [], **extra}


def V(w, metrics, when=WHEN):
    return wc.watch_code_verdict(w, "evidence is not read", metrics, N, when)


GNPA = [M("gnpa_pct", "Q2FY27", 1.25, "PCT")]


# ---------------------------------------------------------------- the four live cards
def test_mahabank_gnpa_under_a_ceiling_is_met():
    assert V(W("GNPA ratio", "at or below 1.45%"), GNPA) == wc.MET
    assert V(W("GNPA ratio", "at or below 1.45%"), [M("gnpa_pct", "Q2FY27", 1.60, "PCT")]) == wc.MISSED
    assert V(W("GNPA ratio", "at or below 1.45%"), [M("gnpa_pct", "Q2FY27", 1.45, "PCT")]) == wc.MET   # at or below includes it


def test_sakar_fy27_target_on_a_q2_filing_is_not_due():
    w = W("Oncology revenue", "at least Rs 50 Cr for FY27", "FY27")
    assert V(w, [M("revenue", "Q2FY27", 100)]) == wc.NOT_DUE
    assert V(W("Oncology revenue", "at least Rs 50 Cr", "Q2FY27 results and FY27"), [M("revenue", "Q2FY27", 100)]) == wc.NOT_DUE


def test_aplapollo_10_lakh_tonnes_with_9_63_lakh_is_missed_in_either_stored_unit():
    w = W("Sales volume", "at least 10 lakh tonnes")
    assert V(w, [M("sales_volume", "Q2FY27", 9.63, "LAKH_TONNES")]) == wc.MISSED
    assert V(w, [M("sales_volume", "Q2FY27", 963143, "TONNES")]) == wc.MISSED
    assert V(w, [M("sales_volume", "Q2FY27", 10.4, "LAKH_TONNES")]) == wc.MET
    assert V(w, [M("sales_volume", "Q2FY27", 963, "KT")]) is None   # a unit not on the list


def _g(statement="Q1FY27 revenue to surpass Q4FY26 revenue"):
    return {"id": "g", "statement": statement, "metric": "revenue"}


def test_unimech_relative_guidance_is_judged_from_memorys_two_figures_on_one_basis():
    rows = [M("revenue", "Q1FY27", 107.62), M("revenue", "Q4FY26", 81.8)]
    assert wc.relative_guidance_verdict(_g(), rows) == wc.MET
    assert wc.relative_guidance_verdict(_g(), [M("revenue", "Q1FY27", 70), M("revenue", "Q4FY26", 81.8)]) == wc.MISSED
    # two bases: no verdict
    assert wc.relative_guidance_verdict(_g(), [M("revenue", "Q1FY27", 107.62), M("revenue", "Q4FY26", 81.8, basis="STANDALONE")]) is None
    assert wc.relative_guidance_verdict(_g(), [M("revenue", "Q1FY27", 107.62)]) is None
    assert wc.relative_guidance_verdict(_g("Q1FY27 revenue to surpass H2FY26 revenue"), rows) is None   # not one kind
    assert wc.relative_guidance_verdict(_g("Q1FY27 revenue to surpass Q4FY26 revenue by 20%"), rows) is None


# ---------------------------------------------------------------- wrong verdicts of review round 4
def test_another_metrics_figure_is_never_used():
    rev = [M("revenue", "Q2FY27", 80)]
    assert V(W("EBITDA", "at least Rs100 Cr"), rev) is None                       # memory has no EBITDA: not revenue
    assert V(W("EBITDA", "at least Rs100 Cr"), rev + [M("ebitda", "Q2FY27", 120)]) == wc.MET
    assert V(W("EBITDA margin", "at least 18%"), [M("gross_margin", "Q2FY27", 16, "PCT")]) is None
    assert V(W("EBITDA margin", "at least 18%"), [M("gross_margin", "Q2FY27", 16, "PCT"), M("ebitda_margin", "Q2FY27", 17.2, "PCT")]) == wc.MISSED
    assert V(W("Net NPA ratio", "below 0.5%"), [M("gnpa_pct", "Q2FY27", 1.9, "PCT")]) is None
    assert V(W("Store count", "at least 500"), rev) is None


def test_a_prior_year_figure_is_not_the_actual():
    rows = [M("ebitda_margin", "Q2FY26", 13.1, "PCT"), M("ebitda_margin", "Q2FY27", 11.5, "PCT")]
    assert V(W("EBITDA margin", "above 12%"), rows) == wc.MISSED
    assert V(W("EBITDA margin", "above 12%"), rows[:1]) is None   # only last year's figure: no verdict


def test_rate_targets_are_not_judged_by_period_totals():
    vol = [M("sales_volume", "Q2FY27", 8, "LAKH_TONNES"), M("revenue", "Q2FY27", 1200)]
    assert V(W("Sales volume", "at least 3 lakh tons per month"), vol) is None
    assert V(W("Sales volume", "at least 3 lakh tons a month"), vol) is None
    assert V(W("Sales volume", "at least 3 lakh tons/month"), vol) is None
    assert V(W("Revenue", "annual run-rate of at least Rs4,000 Cr"), vol) is None
    assert V(W("Revenue", "at least Rs4,000 Cr annualised"), vol) is None
    assert V(W("Sales volume", "at least 1 MTPA"), vol) is None


def test_another_currency_is_never_read_as_rupees():
    rev = [M("revenue", "Q2FY27", 1000)]
    assert V(W("Revenue", "at least $1.5 bn"), rev) is None
    assert V(W("Revenue", "at least USD 1.5 bn"), rev) is None
    assert V(W("Revenue", "at least 200 million dollars"), rev) is None
    assert V(W("Revenue", "at least Rs 900 Cr"), rev) == wc.MET
    assert V(W("Revenue", "at least ₹15 bn"), rev) == wc.MISSED   # 15 bn = 1,500 Cr


def test_unknown_period_words_and_other_period_kinds_give_no_verdict():
    rev = [M("revenue", "Q2FY27", 100), M("revenue", "H1FY27", 1050)]
    assert V(W("Revenue", "at least Rs500 Cr", "half year ended September 2026"), rev) is None
    assert V(W("Revenue", "at least Rs500 Cr", "nine months ended Dec 2026"), rev) == wc.NOT_DUE   # Dec 2026 is after the filing
    assert V(W("Revenue", "at least Rs500 Cr", "six months ended 30 Sep 2026"), rev) is None
    assert V(W("Revenue", "at least Rs500 Cr", "Q2FY27 or H1FY27"), rev) is None      # two periods
    assert V(W("Revenue", "at least Rs500 Cr", "H1FY27"), rev) == wc.MET              # the exact period, memory's H1 figure
    assert V(W("Revenue", "at least Rs500 Cr", "H1FY27"), [M("revenue", "Q2FY27", 1050)]) is None   # a quarter is not a half


def test_the_period_must_match_exactly_even_when_the_evidence_would_not_say_so():
    q4 = [M("revenue", "Q4FY27", 520), M("revenue", "FY27", 1900)]
    late = "2027-05-10T10:00:00+05:30"
    assert V(W("Revenue", "at least Rs1,000 Cr", "FY27"), q4, late) == wc.MET        # FY27's 1,900, not the quarter's 520
    assert V(W("Revenue", "at least Rs1,000 Cr", "FY26"), [M("revenue", "Q2FY27", 520)]) is None
    assert V(W("Revenue", "at least Rs1,000 Cr", "FY27"), [M("revenue", "Q4FY27", 520)], late) is None   # year not in memory


def test_strict_words_do_not_include_the_figure():
    assert V(W("NNPA ratio", "below 0.40%"), [M("nnpa_pct", "Q2FY27", 0.40, "PCT")]) is None   # equal at its precision: rounding decides
    assert V(W("NNPA ratio", "below 0.40%"), [M("nnpa_pct", "Q2FY27", 0.46, "PCT")]) == wc.MISSED
    assert V(W("NNPA ratio", "under 0.40%"), [M("nnpa_pct", "Q2FY27", 0.39, "PCT")]) == wc.MET
    assert V(W("EBITDA margin", "above 18%"), [M("ebitda_margin", "Q2FY27", 18.0, "PCT")]) is None
    assert V(W("ROA", "over 15%"), [M("roa", "Q2FY27", 14.4, "PCT")]) == wc.MISSED
    assert V(W("Revenue", "more than Rs1,000 Cr"), [M("revenue", "Q2FY27", 1000)]) is None
    assert V(W("Revenue", "more than Rs1,000 Cr"), [M("revenue", "Q2FY27", 990)]) == wc.MISSED
    assert V(W("Revenue", "exceeding Rs1,000 Cr"), [M("revenue", "Q2FY27", 1000.5)]) == wc.MET
    assert V(W("Revenue", "at least Rs1,000 Cr"), [M("revenue", "Q2FY27", 1000)]) == wc.MET
    assert V(W("NNPA ratio", "not exceeding 0.5%"), [M("nnpa_pct", "Q2FY27", 0.5, "PCT")]) == wc.MET
    assert V(W("NNPA ratio", "no more than 0.5%"), [M("nnpa_pct", "Q2FY27", 0.6, "PCT")]) == wc.MISSED
    assert V(W("ROA", "not less than 1.2%"), [M("roa_pct", "Q2FY27", 1.2, "PCT")]) == wc.MET


def test_a_due_period_memory_has_not_reached_is_no_verdict_not_not_due():
    # Q2FY27 ended 30 Sep; the filing is 24 Oct; memory holds only Q1FY27: due, but nothing to judge it by
    assert V(W("Revenue", "at least Rs100 Cr"), [M("revenue", "Q1FY27", 120)]) is None
    # memory's latest period counts, not only this filing's: a Q2FY27 figure from another filing judges it
    assert V(W("Revenue", "at least Rs100 Cr"), [M("revenue", "Q2FY27", 120, source_news_id="nse-earlier")]) == wc.MET


# ---------------------------------------------------------------- shapes that get no verdict
@pytest.mark.parametrize("text,target", [
    ("Revenue", "20% growth"), ("Revenue", "at least Rs100 Cr, up 20%"), ("Revenue", "from Rs80 Cr to Rs100 Cr"),
    ("Revenue", "Rs100-120 Cr"), ("Revenue", "between Rs100 Cr and Rs120 Cr"), ("Revenue", "up to Rs100 Cr"),
    ("EBITDA margin", "12%"), ("Revenue", "at least Rs100 Cr and at most Rs200 Cr"), ("Revenue", "not at least Rs100 Cr"),
    ("Revenue", "at least 100 stores"), ("Revenue", "at least 100 bps"), ("Revenue", "at least Rs100"),
    ("Revenue", "reduce by Rs 100 Cr"), ("Revenue", "at least Rs100 Cr cumulative"), ("Revenue", None),
    ("Oncology revenue", "at least Rs100 Cr"), ("Segment EBITDA", "at least Rs100 Cr"), ("EBITDA per tonne", "at least Rs100 Cr"),
    ("Revenue growth", "at least Rs100 Cr"), ("Revenue and EBITDA", "at least Rs100 Cr"), ("PAT margin", "at least 5%"),
    ("Gross margin", "at least 5%"), ("Net debt", "below Rs100 Cr"),
])
def test_other_shapes_get_no_verdict(text, target):
    rows = [M("revenue", "Q2FY27", 120), M("ebitda", "Q2FY27", 120), M("ebitda_margin", "Q2FY27", 12, "PCT"), M("pat", "Q2FY27", 120)]
    assert V(W(text, target), rows) is None


def test_basis_the_watch_names_must_be_the_memory_figure_basis():
    assert V(W("Standalone revenue", "at least Rs100 Cr"), [M("revenue", "Q2FY27", 120, basis="CONSOLIDATED")]) is None
    assert V(W("Standalone revenue", "at least Rs100 Cr"), [M("revenue", "Q2FY27", 120, basis="STANDALONE")]) == wc.MET
    assert V(W("Consolidated revenue", "at least Rs100 Cr"), [M("revenue", "Q2FY27", 120, basis="STANDALONE")]) is None
    assert V(W("Revenue", "at least Rs100 Cr"), [M("revenue", "Q2FY27", 120, basis=None)]) == wc.MET


def test_a_figure_marked_not_ok_or_in_another_unit_scale_is_not_used():
    assert V(W("Revenue", "at least Rs100 Cr"), [M("revenue", "Q2FY27", 120, lab={"ok": False})]) is None
    assert V(W("Revenue", "at least Rs100 Cr"), [M("revenue", "Q2FY27", 120_000)]) is None    # 1,200x: another unit
    assert V(W("Revenue", "at least Rs100 Cr"), [M("revenue", "Q2FY27", 120, "PCT")]) is None
    assert V(W("Revenue", "at least Rs100 Cr"), [M("revenue", "Q2FY27", 12000, "INR_LAKH")]) == wc.MET   # 120 Cr


def test_the_model_tagged_metric_must_agree_with_the_words():
    assert V(W("GNPA ratio", "at or below 1.45%", metric="gnpa_pct", period="Q2FY27"), GNPA) == wc.MET
    assert V(W("GNPA ratio", "at or below 1.45%", metric="revenue", period="Q2FY27"), GNPA) is None
    assert V(W("GNPA ratio", "at or below 1.45%", metric="gnpa_pct", period="FY27"), GNPA) == wc.NOT_DUE


def test_only_kpi_watches_get_a_verdict():
    assert V({**W("GNPA ratio", "at or below 1.45%"), "kind": "APPROVAL"}, GNPA) is None


# ---------------------------------------------------------------- the sentence cut
def _judged(target, verdict, metric="gnpa", period="Q2FY27", text="x"):
    spec = next(s for s in wc._SPECS if s.key == metric)
    return wc.Judged(verdict, spec, wc.parse_target(target), period, 0.0)


def _cut(sentence, target, verdict, metric="gnpa"):
    return wc._cut(sentence, _judged(target, verdict, metric))[0]


def test_a_claim_against_the_code_verdict_is_cut():
    assert _cut("GNPA at 1.25% did not meet the 1.45% ceiling.", "at most 1.45%", wc.MET) is None
    assert _cut("GNPA at 1.25% fell short of the 1.45% ceiling.", "at most 1.45%", wc.MET) is None
    assert _cut("GNPA at 1.25% missed the 1.45% ceiling.", "at most 1.45%", wc.MET) is None
    assert _cut("GNPA of 1.8% was above the 1.45% ceiling.", "at most 1.45%", wc.MET) is None
    assert _cut("Volume met the 10 lakh tons target.", "at least 10 lakh tons", wc.MISSED, "volume") is None
    assert _cut("Volume beat the 10 lakh tons target.", "at least 10 lakh tons", wc.MISSED, "volume") is None
    assert _cut("Volume exceeded the 10 lakh tons target.", "at least 10 lakh tons", wc.MISSED, "volume") is None
    assert _cut("Volume of 9.63 lakh tons met the 10 lakh tons target.", "at least 10 lakh tons", wc.MISSED, "volume") is None
    assert _cut("GNPA of 1.8% was below the 1.45% ceiling.", "at most 1.45%", wc.MISSED) is None   # below a ceiling is a met claim


def test_a_true_description_is_never_cut():
    # review round 4: these true sentences were cut because "was below / above" counted as a met claim
    assert _cut("GNPA of 1.8% was above the 1.45% ceiling.", "at most 1.45%", wc.MISSED) == "GNPA of 1.8% was above the 1.45% ceiling."
    assert _cut("GNPA of 1.8% stayed above the 1.45% ceiling.", "at most 1.45%", wc.MISSED) == "GNPA of 1.8% stayed above the 1.45% ceiling."
    assert _cut("EBITDA margin of 17.2% was below the 18% target.", "at least 18%", wc.MISSED, "ebitda_margin") == \
        "EBITDA margin of 17.2% was below the 18% target."
    assert _cut("EBITDA margin stayed below the 18% target at 17.2%.", "at least 18%", wc.MISSED, "ebitda_margin") == \
        "EBITDA margin stayed below the 18% target at 17.2%."
    for s in ("Volume of 9.63 lakh tons was within 4% of the 10 lakh tons target.",
              "Volume delivered 9.63 lakh tons versus the 10 lakh tons target.",
              "Volume achieved 9.63 lakh tons against its 10 lakh tons target.",
              "Volume of 9.63 lakh tons fell short of the 10 lakh tons target.",
              "Volume did not meet the 10 lakh tons target.",
              "Volume missed the 10 lakh tons target.",
              "The 10 lakh tons target was not achieved."):
        assert _cut(s, "at least 10 lakh tons", wc.MISSED, "volume") == s, s
    assert _cut("GNPA at 1.25% was below the 1.45% ceiling.", "at most 1.45%", wc.MET) == "GNPA at 1.25% was below the 1.45% ceiling."


def test_a_clause_must_name_the_metric_and_the_target_figure():
    t, v = "at least 10 lakh tons", wc.MISSED
    assert _cut("The 10 lakh tons target is met.", t, v, "volume") == "The 10 lakh tons target is met."   # no metric word
    assert _cut("Revenue met the 10 lakh tons target.", t, v, "volume") == "Revenue met the 10 lakh tons target."
    assert _cut("Volume met the 12 lakh tons target.", t, v, "volume") == "Volume met the 12 lakh tons target."    # another figure
    assert _cut("Volume met the 10% target.", t, v, "volume") == "Volume met the 10% target."                      # another unit


def test_forward_and_other_period_clauses_are_kept():
    t, v = "at least 10 lakh tons", wc.MISSED
    for s in ("Volume will meet the 10 lakh tons target next quarter.",
              "Management expects volume to meet the 10 lakh tons target.",
              "Volume met the 10 lakh tons target in Q2FY26.",
              "Volume met the 10 lakh tons target for FY25.",
              "Volume met the 10 lakh tons target last year.",
              "Volume met the 10 lakh tons target a year ago."):
        assert _cut(s, t, v, "volume") == s, s
    assert _cut("Volume met the 10 lakh tons target in Q2FY27.", t, v, "volume") is None


def test_only_the_contradicting_clause_goes_when_the_rest_stands_alone():
    s = "Revenue grew 12% year on year, and volume met the 10 lakh tons target."
    assert _cut(s, "at least 10 lakh tons", wc.MISSED, "volume") == "Revenue grew 12% year on year."
    assert wc._cut("No clause here names anything.", _judged("at least 10 lakh tons", wc.MISSED, "volume")) == ("No clause here names anything.", None)


def test_drop_contradicting_edits_the_card_and_notes_the_cut():
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "t",
        "card": {"headline": "Mahabank Q2FY27", "impact_level": "MODERATE", "takeaway": "GNPA at 1.25% did not meet the 1.45% ceiling.",
                 "what_happened": ["x"], "why_it_matters": [{"text": "GNPA at 1.25% fell short of the 1.45% ceiling."},
                                                           {"text": "Credit cost stayed low."}]}})
    w = W("GNPA ratio", "at or below 1.45%")
    j = wc.judge(w, GNPA, WHEN)
    notes = wc.drop_contradicting(out.card, {"w": (w, j)})
    assert out.card.takeaway == "" and [i.text for i in out.card.why_it_matters] == ["Credit cost stayed low."]
    assert len(notes) == 2 and all("met" in n for n in notes)
    # nothing contradicted: returned as it was
    out2 = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "t",
        "card": {"headline": "Maha Bank Q2FY27 results", "impact_level": "LOW", "takeaway": "GNPA at 1.25% beat the 1.45% ceiling.", "what_happened": ["x"]}})
    assert wc.drop_contradicting(out2.card, {"w": (w, j)}) == [] and out2.card.takeaway == "GNPA at 1.25% beat the 1.45% ceiling."


# ---------------------------------------------------------------- wiring: the switch, off and on
def _filing():
    return Filing(news_id=N, scrip_code="532", company_name="Maha Bank", headline="h", subject="", filed_at=WHEN,
                  filing_date=WHEN[:10], event_type="RESULTS")


def _out(status, evidence):
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "t",
        "card": {"headline": "Maha Bank Q2FY27 results", "impact_level": "MODERATE", "takeaway": "t", "what_happened": ["x"]},
        "dossier_delta": {"watch_updates": [{"watch_id": "w", "status": status, "evidence": evidence}]}})


def _types(found):
    return [(s.type, s.severity, s.text.split(":")[0]) for s in found]


@pytest.mark.switches_off("CARD_GUIDANCE_DATED")   # the behaviour before the switch; the switch has its own tests
def test_signals_switch_off_keeps_the_models_verdict_and_on_the_code_decides(monkeypatch):
    before = {"watchlist": [W("GNPA ratio", "at or below 1.45%")]}
    after = {**before, "financial_metrics": GNPA}
    out = _out("MISSED", "GNPA ratio 1.25% in Q2FY27, GNPA ratio check.")
    monkeypatch.delenv("CARD_WATCH_VERDICT", raising=False)
    assert _types(signals._promises(before, after, out, _filing())) == [("WATCH_RESOLVED", "WARNING", "KPI check missed")]
    monkeypatch.setenv("CARD_WATCH_VERDICT", "1")
    assert _types(signals._promises(before, after, out, _filing())) == [("WATCH_RESOLVED", "POSITIVE", "KPI check met")]


def test_signals_a_not_due_target_gives_no_signal_with_the_switch_on(monkeypatch):
    before = {"watchlist": [W("Oncology revenue", "at least Rs50 Cr for FY27", "FY27")]}
    after = {**before, "financial_metrics": [M("revenue", "Q2FY27", 100)]}
    out = _out("MISSED", "Oncology revenue Q2FY27 below target.")
    monkeypatch.delenv("CARD_WATCH_VERDICT", raising=False)
    assert len(signals._promises(before, after, out, _filing())) == 1
    monkeypatch.setenv("CARD_WATCH_VERDICT", "1")
    assert signals._promises(before, after, out, _filing()) == []


def test_signals_unknown_shapes_keep_the_old_path_with_the_switch_on(monkeypatch):
    before = {"watchlist": [W("Credit cost", "below 1%")]}
    after = {**before, "financial_metrics": GNPA}
    out = _out("MISSED", "Credit cost 1.2% in Q2FY27.")
    monkeypatch.delenv("CARD_WATCH_VERDICT", raising=False)
    off = _types(signals._promises(before, after, out, _filing()))
    monkeypatch.setenv("CARD_WATCH_VERDICT", "1")
    assert _types(signals._promises(before, after, out, _filing())) == off


def test_the_switch_is_off_by_default_and_read_at_the_call(monkeypatch):
    from bse_intel.settings import card_watch_verdict

    monkeypatch.delenv("CARD_WATCH_VERDICT", raising=False)
    assert card_watch_verdict() is False
    monkeypatch.setenv("CARD_WATCH_VERDICT", "on")
    assert card_watch_verdict() is True


def _merge_watch(monkeypatch, on):
    from bse_intel.dossier import merge, new_dossier

    if on:
        monkeypatch.setenv("CARD_WATCH_VERDICT", "1")
    else:
        monkeypatch.delenv("CARD_WATCH_VERDICT", raising=False)
    kpi = {"kpi": "GNPA ratio", "check_in": "Q2FY27 results", "target": "at or below 1.45%", "metric": "gnpa_pct", "period": "Q2FY27",
           "value": 1.45, "comparison": "<="}
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "t",
        "card": {"headline": "Maha Bank Q1FY27 results filed", "impact_level": "MODERATE", "takeaway": "t", "what_happened": ["x"],
                 "track_next": {"kpis_to_verify": [kpi]}}})
    f = Filing(news_id="n0", scrip_code="532", company_name="Maha Bank", headline="h", subject="", filed_at="2026-07-20T10:00:00+05:30",
               filing_date="2026-07-20", event_type="RESULTS")
    return merge(new_dossier(f), out, f, None, "now")["watchlist"][0]


def test_watch_keeps_the_metric_and_period_only_with_the_switch_on(monkeypatch):
    off = _merge_watch(monkeypatch, False)
    assert "metric" not in off and "period" not in off
    on = _merge_watch(monkeypatch, True)
    assert on["metric"] == "gnpa_pct" and on["period"] == "Q2FY27"
    assert {k: v for k, v in on.items() if k not in ("metric", "period")} == off


# ---------------------------------------------------------------- live review of e5960fc (118 companies)
def _srcs(*rows):
    """A multi-source memory row: (value, basis, by)."""
    sources = [{"news_id": f"n{i}", "as_of": WHEN, "value": v, "unit": "PCT", "basis": b, "lab": {"by": by, "ok": True}}
               for i, (v, b, by) in enumerate(rows)]
    return {"metric": "ebitda_margin", "period": "Q2FY27", "value": rows[-1][0], "unit": "PCT", "as_of": WHEN,
            "source_news_id": "n0", "sources": sources}


def test_b1_a_row_whose_sources_disagree_gives_no_verdict_aequs_and_friends():
    w = W("Consolidated EBITDA margin", "above 5%")
    assert V(w, [_srcs((3.39, "CONSOLIDATED", "calc"), (6.0, "CONSOLIDATED", "ai"))]) is None          # AEQUS
    assert V(W("EBITDA margin", "at least 23%"), [_srcs((21.63, "CONSOLIDATED", "calc"), (23.25, "CONSOLIDATED", "ai"))]) is None  # HFCL
    assert V(W("EBITDA margin", "at least 13%"), [_srcs((13.58, None, "calc"), (18.5, None, "ai"))]) is None   # PERSISTENT
    assert V(W("EBITDA margin", "at least 8%"), [_srcs((8.17, "CONSOLIDATED", "file"), (8.2, "CONSOLIDATED", "ai"))]) == wc.MET   # within 2%


def test_b2_or_above_and_or_below_include_the_figure():
    w = W("EBITDA margin", "21.9% or above")
    assert V(w, [M("ebitda_margin", "Q2FY27", 21.9, "PCT")]) == wc.MET                                   # SUMICHEM wording
    assert V(w, [M("ebitda_margin", "Q2FY27", 20.47, "PCT")]) == wc.MISSED
    assert V(W("GNPA ratio", "1.45% or below"), [M("gnpa", "Q2FY27", 1.45, "PCT")]) == wc.MET
    assert V(W("GNPA ratio", "1.45% or less"), [M("gnpa", "Q2FY27", 1.5, "PCT")]) == wc.MISSED
    assert V(W("Revenue", "Rs 100 Cr or more"), [M("revenue", "Q2FY27", 100)]) == wc.MET


def test_b3_strict_word_on_a_figure_equal_at_its_precision_is_no_verdict():
    w = W("GNPA ratio", "Below 1.45%", "Q1FY27")
    assert V(w, [M("gnpa_pct", "Q1FY27", 1.45, "PCT")]) is None                                           # MAHABANK Q1FY27
    assert V(w, [M("gnpa_pct", "Q1FY27", 1.44, "PCT")]) == wc.MET
    assert V(W("Revenue", "above 107.62 Cr"), [M("revenue", "Q2FY27", 107.62)]) is None


def test_b4_basis_is_read_from_the_sources():
    standalone = {"metric": "ebitda_margin", "period": "Q2FY27", "value": 7.24, "unit": "PCT", "as_of": WHEN, "source_news_id": "n0",
                  "sources": [{"news_id": "n0", "as_of": WHEN, "value": 7.24, "unit": "PCT", "basis": "STANDALONE"},
                              {"news_id": "n1", "as_of": WHEN, "value": 7.24, "unit": "PCT", "basis": "STANDALONE"}]}
    assert V(W("Consolidated EBITDA margin", "above 8%"), [standalone]) is None                             # DEEPA
    assert V(W("Standalone EBITDA margin", "above 8%"), [standalone]) == wc.MISSED
    assert V(W("EBITDA margin", "above 8%"), [standalone]) == wc.MISSED
    mixed = _srcs((7.2, "STANDALONE", "file"), (7.2, "CONSOLIDATED", "file"))
    assert V(W("EBITDA margin", "above 8%"), [mixed]) is None
    assert V(W("Consolidated EBITDA margin", "above 8%"), [mixed]) is None


def test_aplapollo_live_watch_q2fy27_volume_10_lakh_tons_with_memorys_mt_row():
    w = W("Q2FY27 volume", "10 lakh tons", "Q2FY27 results")
    row = M("volumes", "Q2FY27", 963143.0, "MT", lab={"by": "ai", "ok": True})
    assert V(w, [row]) == wc.MISSED
    assert V(w, [M("volumes", "Q2FY27", 1_020_000.0, "MT")]) == wc.MET
    assert V(W("Q2FY27 volume", "10 lakh tons"), [M("volumes", "Q2FY27", 0.96, "MT")]) is None            # million tonnes: 50x rule
    assert V(W("EBITDA margin", "12%"), [M("ebitda_margin", "Q2FY27", 11, "PCT")]) is None                 # a bare ratio could be a ceiling


def test_a_watch_made_by_the_filing_is_not_answered_by_it():
    w = W("GNPA ratio", "at or below 1.45%", created_on=WHEN)
    assert V(w, GNPA) is None


def test_c1_titles_and_company_abbreviations_do_not_split_a_sentence():
    j = _judged("at least Rs 100 Cr", wc.MISSED, "revenue")
    s = "Dr. Rao said revenue beat the Rs 100 Cr target. Margins rose."
    left = [wc._cut(x, j)[0] for x in wc._sentences(s)]
    assert left == [None, "Margins rose."]
    assert wc._sentences("Mr. Shah noted revenue beat the Rs 100 Cr target in the quarter.") == ["Mr. Shah noted revenue beat the Rs 100 Cr target in the quarter."]
    assert wc._sentences("ABC Pvt. Ltd. revenue beat the Rs 100 Cr target. Margins rose.")[0].endswith("target.")


def test_c2_a_clause_hanging_on_the_cut_one_takes_the_sentence_with_it():
    j = _judged("at least Rs 100 Cr", wc.MISSED, "revenue")
    s = "Driven by exports, revenue beat the Rs 100 Cr target, which management called a milestone."
    assert wc._cut(s, j) == (None, s)


def test_a_rough_or_negative_bare_target_gives_no_verdict():
    # review of e23e300: "around Rs 100 Cr" is neither a floor nor a ceiling; "-Rs 50 Cr" is a loss limit
    from bse_intel.watch_code import parse_target
    for target in ("around Rs 100 Cr", "about ₹100 Cr", "approx. ₹100 Cr", "~₹100 Cr", "roughly 10 lakh tons", "-₹50 Cr",
                   "at least -₹5 Cr", "above -Rs 5 Cr", "at least −₹5 Cr"):
        assert parse_target(target) is None, target
    assert parse_target("10 lakh tons") is not None
