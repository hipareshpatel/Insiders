from types import SimpleNamespace

from bse_intel.models import CapitalAction
from bse_intel.quality import festive_signals, quality_signals, rating_signals, warrant_deadlines

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
    for i, (q, exc) in enumerate((("Q1FY27", 1.0), ("Q2FY27", 0.0), ("Q3FY27", 2.0))):
        rows += _quarter(q, 100, 50, 10, 10, 30, 12, 10, tax=0.5, exc=exc)
    rows += _quarter("Q4FY27", 100, 58, 10, 10, 22, 8, 7, fin=20, dep=5, tax=0.4, exc=3.0, news=N)
    found = kinds(quality_signals({"financial_metrics": rows, "balance_sheet": []}, N))
    assert "800 bps below" in found["Q4_TRUE_UP"]["text"]
    assert found["LOW_CASH_TAX"]["severity"] == "INFO"
    assert "3 of the last 8" in found["RECURRING_ONE_OFFS"]["text"]
    assert found["DISTRESS"]["text"].startswith("Interest cover 0.8x")


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
