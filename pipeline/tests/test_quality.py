from types import SimpleNamespace

from bse_intel.models import CapitalAction
from bse_intel.quality import asset_turn_signals, festive_signals, quality_signals, rating_signals, warrant_deadlines

N = "n-q"


def _m(metric, period, value, news=N):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "source_news_id": news,
            "as_of": "2026-10-20T10:00:00+05:30"}


def _quarter(period, revenue, rm, emp, other, ebitda, pbt, pat, oi=2.0, fin=3.0, dep=5.0, tax=None, exc=0.0, news="old"):
    rows = [_m("revenue", period, revenue, news), _m("raw_material_cost", period, rm, news), _m("employee_cost", period, emp, news),
            _m("other_expenses", period, other, news), _m("ebitda", period, ebitda, news), _m("pbt", period, pbt, news),
            _m("pat", period, pat, news), _m("other_income", period, oi, news), _m("finance_cost", period, fin, news),
            _m("depreciation", period, dep, news), _m("exceptional_items", period, exc, news)]
    if tax is not None:
        rows.append(_m("current_tax", period, tax, news))
    return rows


def kinds(signals):
    return {s["type"]: s for s in signals}


def test_low_quality_beat_and_margin_mix():
    metrics = _quarter("Q2FY26", 100, 60, 10, 10, 20, 14, 10) + \
        _quarter("Q2FY27", 110, 60, 14, 11, 19, 30, 22, oi=15, news=N)
    signals = quality_signals({"financial_metrics": metrics}, N)
    found = kinds(signals)
    beats = [s["text"] for s in signals if s["type"] == "LOW_QUALITY_BEAT"]
    assert beats[0].startswith("Other income ₹15 Cr is 50% of PBT") and beats[1].startswith("PAT up 120% YoY but core EBITDA -5%")
    # gross margin 40% -> 45.5% (+545 bps); fixed costs 20% -> 22.7% (-273 bps)
    assert "gross margin +545 bps" in found["MARGIN_MIX"]["text"] and "absorption -273 bps" in found["MARGIN_MIX"]["text"]
    assert found["JAWS"]["severity"] == "WARNING"  # employee cost +40% vs revenue +10%, no project under way


def test_jaws_reads_as_prelaunch_when_capex_is_under_way():
    metrics = _quarter("Q2FY26", 100, 60, 10, 10, 20, 14, 10) + _quarter("Q2FY27", 110, 66, 14, 11, 19, 13, 9, news=N)
    found = kinds(quality_signals({"financial_metrics": metrics, "deals": [{"kind": "CAPEX", "stage": "IN_PROGRESS"}]}, N))
    assert found["JAWS"]["severity"] == "INFO" and "ahead of launch" in found["JAWS"]["text"]


def test_q4_true_up_low_tax_one_offs_and_distress():
    rows = []
    for i, (q, exc) in enumerate((("Q1FY27", -1.0), ("Q2FY27", 0.0), ("Q3FY27", -2.0))):
        rows += _quarter(q, 100, 50, 10, 10, 30, 12, 10, tax=0.5, exc=exc)
    rows += _quarter("Q4FY27", 100, 58, 10, 10, 22, 8, 7, fin=20, dep=5, tax=0.4, exc=-3.0, news=N)
    found = kinds(quality_signals({"financial_metrics": rows, "balance_sheet": []}, N))
    assert "800 bps below" in found["Q4_TRUE_UP"]["text"]
    assert found["LOW_CASH_TAX"]["severity"] == "INFO"
    assert "3 of the last 8" in found["RECURRING_ONE_OFFS"]["text"]
    # gains are not a running cost (ITC's remeasurement gain, live review 3): the same quarters as gains raise nothing
    gains = [dict(r, value=-r["value"]) if r["metric"] == "exceptional_items" else r for r in rows]
    assert "RECURRING_ONE_OFFS" not in kinds(quality_signals({"financial_metrics": gains, "balance_sheet": []}, N))
    # below 1x the operating profit covers only part of the interest; "barely covers" is for 1x to 1.5x
    assert found["DISTRESS"]["text"].startswith("EBIT/interest 0.8x")
    assert "covers only part of the interest" in found["DISTRESS"]["text"]


def test_rating_ladder_and_inc():
    before = {"balance_sheet": [{"credit_rating": "CARE BBB+; A2", "rating_outlook": "Stable", "source_news_id": "old"}]}
    after = {"balance_sheet": before["balance_sheet"] + [{"credit_rating": "CARE BBB; A3+", "rating_outlook": "Negative",
                                                          "source_news_id": N}]}
    texts = [s["text"] for s in rating_signals(before, after, N)]
    assert "Short-term rating cut A2 → A3+: near-term liquidity is weaker." in texts and "Rating outlook revised to Negative." in texts
    inc = {"balance_sheet": [{"credit_rating": "ICRA B; ISSUER NOT COOPERATING", "source_news_id": N}]}
    assert "Issuer Not Cooperating" in rating_signals(None, inc, N)[0]["text"]


def test_festive_season_reads_october_and_november_together():
    rows = [_m("sales_volume", p, v, "old") for p, v in (("OCT-2025", 100), ("NOV-2025", 200), ("OCT-2026", 180))]
    rows.append(_m("sales_volume", "NOV-2026", 150, N))
    (s,) = festive_signals({"financial_metrics": rows}, N)
    assert s["text"].startswith("October + November together +10% YoY")


def test_warrant_clock():
    out = SimpleNamespace(dossier_delta=SimpleNamespace(capital_actions=[CapitalAction(instrument="Convertible warrants", amount_cr=75, issue_price=150)]))
    ((deadline, text),) = warrant_deadlines(out, SimpleNamespace(filing_date="2026-10-01"))
    assert deadline == "2028-04-01" and "₹75 Cr at ₹150" in text


def test_asset_turns_against_the_sector_band():
    card = {"deal_value": {"kind": "CAPEX", "amount_cr": 100},
            "quantified_impact": [{"label": "Peak revenue potential", "unit": "INR_CR", "result": 600, "check": "VERIFIED"}]}
    (s,) = asset_turn_signals(card, "chemicals", (0.8, 2.2))
    assert s["severity"] == "WARNING" and "6.0x asset turns, against 0.8-2.2x normal for chemicals" in s["text"]
    card["quantified_impact"][0]["result"] = 180
    assert asset_turn_signals(card, "chemicals", (0.8, 2.2)) == []
    assert asset_turn_signals(card, "banks", None) == []


def test_sector_lens_carries_turns_drivers_and_red_flag(settings):
    from bse_intel.prompts.engine import PromptEngine

    lens = PromptEngine(settings).sector_for("Specialty Chemicals")
    assert lens.asset_turn == (0.8, 2.2)
    text = lens.lens()
    assert "Normal asset turns: 1.4-2.2x specialty" in text and "anti-dumping" in text and "Forensic red flag" in text


def test_volume_strip_lists_recent_months_up_to_the_filing():
    from bse_intel.signals import volume_strip

    rows = [_m("sales_volume", p, v, "old") | {"yoy_pct": y} for p, v, y in
            (("JUN-2026", 900, 5.0), ("JUL-2026", 1000, 12.0), ("AUG-2026", 1100, 18.0))]
    rows.append(_m("sales_volume", "SEP-2026", 1200, N) | {"yoy_pct": 22.0})
    strip = volume_strip({"financial_metrics": rows}, N, months=3)
    assert strip["metric"] == "sales_volume" and [m["period"] for m in strip["months"]] == ["JUL-2026", "AUG-2026", "SEP-2026"]
    assert strip["months"][-1] == {"period": "SEP-2026", "value": 1200, "yoy_pct": 22.0}


def _roiic_dossier(ebitda_now, capital_now, ebitda_then=40.0):
    from bse_intel.quality import roiic  # noqa: F401
    q = {"Q2FY26": ebitda_then, "Q3FY26": 42, "Q4FY26": 45, "Q1FY27": 48, "Q2FY27": ebitda_now}
    return {"financial_metrics": [{"metric": "ebitda", "period": p, "value": v, "unit": "INR_CR"} for p, v in q.items()],
            "balance_sheet": [{"period": "H1FY26", "as_of": "2025-11-10T10:00:00+05:30", "net_worth_cr": 300, "gross_debt_cr": 100, "cash_cr": 20},
                              {"period": "H1FY27", "as_of": "2026-11-10T10:00:00+05:30", "net_worth_cr": capital_now, "gross_debt_cr": 100, "cash_cr": 20}]}


def test_roiic_compounder_and_diluter():
    from bse_intel.quality import roiic
    good = roiic(_roiic_dossier(60, 340))  # +20 Cr a quarter = +80 Cr a year on +40 Cr of capital
    assert good["from"] == "Q2FY26" and good["to"] == "Q2FY27" and good["basis"] == "annualised quarter"
    assert good["ebitda_added_cr"] == 80 and good["capital_added_cr"] == 40 and good["verdict"] == "COMPOUNDER"
    bad = roiic(_roiic_dossier(42, 700))  # +8 Cr a year on +400 Cr
    assert bad["pct"] == 2.0 and bad["verdict"] == "DILUTER"
    flat = roiic(_roiic_dossier(50, 300))
    assert flat["verdict"] == "SELF_FUNDED"


def test_roiic_needs_a_year_and_two_balance_sheets():
    from bse_intel.quality import roiic
    d = _roiic_dossier(60, 420)
    d["financial_metrics"] = [m for m in d["financial_metrics"] if m["period"] != "Q2FY26"]
    assert roiic(d) is None
    d = _roiic_dossier(60, 420)
    d["balance_sheet"] = d["balance_sheet"][:1]
    assert roiic(d) is None


def test_the_defect_digest_groups_cards_by_class_and_finds_repeats():
    """The 100-card audit is the measure of truth but needs ten reviewers, so it cannot run daily. Every card
    already carries what the checks found; the digest reads it back by class, because one class is one change
    in code. Measured on the rebuild, a card the checks flagged was 2.5x as likely to be judged WRONG."""
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "defect_digest", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "defect_digest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def row(news_id, scrip, at, headline, grounding=None, review=None):
        return {"news_id": news_id, "scrip_code": scrip, "filed_at": at, "route": "PASS1", "needs_review": 0,
                "card": {"headline": headline, "timeline_entry": headline, "model": "x/y", "event_type": "RESULTS",
                         "grounding": grounding or {}, "review": review}}

    cards = [
        row("a1", "500", "2026-01-01T10:00:00+05:30", "Q1 revenue up 10%",
            grounding={"ungrounded": ["123.4"], "change_fixes": ["revenue: +1% -> +10%"]},
            review={"status": "UNRESOLVED"}),
        row("b2", "500", "2026-01-03T10:00:00+05:30", "Q1 revenue up 10 percent"),
        row("c3", "600", "2026-02-01T10:00:00+05:30", "Board approves a plant in Gujarat"),
    ]
    found = mod.classes(cards)
    assert len(found["number not found in the filing or memory"]) == 1
    assert len(found["second opinion could not resolve it (a flagged error shipped)"]) == 1
    assert len(found["change recomputed in code"]) == 1
    assert "a1" == found["number not found in the filing or memory"][0]["news_id"]

    pairs = mod.duplicate_pairs(cards)
    assert len(pairs) == 1 and pairs[0]["repeat"] == "b2" and pairs[0]["days"] == 2


def test_a_negative_interest_cover_does_not_read_as_barely_covered():
    """Audit round 1: the one sentence served every cover below 1.5x, so -0.3x and even -0.0x read
    "operating profit barely covers interest", the opposite of the figure printed beside it."""
    # EBITDA 10, depreciation 13, finance 10: EBIT is -3, so interest is not covered at all
    rows = _quarter("Q4FY27", 100, 58, 10, 10, 10, 8, 7, fin=10, dep=13, news=N)
    found = kinds(quality_signals({"financial_metrics": rows, "balance_sheet": []}, N))
    assert found["DISTRESS"]["text"].startswith("EBIT/interest -0.3x")
    assert "does not cover interest at all" in found["DISTRESS"]["text"]

    # EBITDA equal to depreciation: exactly zero cover, and it must not print as "-0.0x"
    rows = _quarter("Q4FY27", 100, 58, 10, 10, 13, 8, 7, fin=10, dep=13, news=N)
    found = kinds(quality_signals({"financial_metrics": rows, "balance_sheet": []}, N))
    assert found["DISTRESS"]["text"].startswith("EBIT/interest +0.00x")
