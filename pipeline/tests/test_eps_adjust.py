"""EPS across splits, bonuses and consolidations (F153, TODO 43, eps_adjust.py)."""

import pytest

from bse_intel import eps_adjust, metrics, results_card
from bse_intel.dossier import view_as_of
from bse_intel.models import FinancialMetric
from bse_intel.xbrl import XbrlResult

X = "xbrl:res:500001:"


def _actions(*specs):
    return {"corporate_actions": [{"ex_date": d, "kind": k, "factor": f, "subject": f"{k} {d}"} for d, k, f in specs]}


BONUS = _actions(("2024-10-28", "BONUS", 2.0))               # 1:1


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("EPS_SHARE_ADJUST", "1")


def test_reliance_bonus_adjusts_the_older_eps_to_todays_shares():
    # profit up 14%, year-ago EPS before the 1:1 bonus (double): -45% as stated, +14% adjusted
    c = eps_adjust.compare(BONUS, "Q2FY26", "Q2FY25", 11.4, 20.0, 15390, 13500)
    assert c.kind == "adjusted" and c.eps_old == 10.0
    assert c.note == "adjusted for bonus 1:1 on 2024-10-28"
    assert round((11.4 / c.eps_old - 1) * 100) == 14


def test_split_one_to_five_and_consolidation():
    split = _actions(("2026-01-10", "SPLIT", 5.0))
    c = eps_adjust.compare(split, "Q4FY26", "Q4FY25", 2.0, 10.0, 100, 100)
    assert c.kind == "adjusted" and c.eps_old == 2.0 and "split 1:5 on 2026-01-10" in c.note
    merged = _actions(("2026-01-10", "CONSOLIDATION", 0.2))       # 5 shares into 1
    c = eps_adjust.compare(merged, "Q4FY26", "Q4FY25", 50.0, 10.0, 100, 100)
    assert c.kind == "adjusted" and round(c.eps_old, 6) == 50.0 and "consolidation 5:1 on 2026-01-10" in c.note


def test_missing_record_with_a_jump_is_blank_and_no_action_is_unchanged():
    c = eps_adjust.compare({}, "Q2FY26", "Q2FY25", 10.0, 20.0, 1000, 1000)
    assert c.kind == "blank" and "EPS not comparable" in c.note
    assert eps_adjust.compare({}, "Q2FY26", "Q2FY25", 10.0, 9.5, 1000, 1000).kind == "same"
    assert eps_adjust.compare({}, "Q2FY26", "Q2FY25", 10.0, 20.0).kind == "same"    # no profit: nothing to judge by


def test_a_file_that_already_restated_is_not_adjusted_twice():
    # the record says bonus 1:1, but the older EPS is already on the new count (implied shares agree)
    assert eps_adjust.compare(BONUS, "Q2FY26", "Q2FY25", 10.0, 9.5, 1000, 1000).kind == "same"
    # a bonus on record plus an issue on top: still adjusted with the record's factor
    assert eps_adjust.compare(BONUS, "Q2FY26", "Q2FY25", 10.0, 40.0, 1000, 1000).kind == "adjusted"


def test_real_dilution_keeps_the_reported_change():
    # a 15% preferential allotment (or rights, QIP, ESOPs, a merger): actual growth, no blank, no adjustment
    assert eps_adjust.compare({}, "Q2FY26", "Q2FY25", 10.0, 11.5, 1000, 1000).kind == "same"
    assert eps_adjust.compare(BONUS, "Q3FY26", "Q3FY25", 10.0, 11.5, 1000, 1000).kind == "same"
    # 1.5x with no record is an exact ratio (a 1:2 bonus), 1.75x is not
    assert eps_adjust.compare({}, "Q2FY26", "Q2FY25", 10.0, 15.0, 1000, 1000).kind == "blank"
    assert eps_adjust.compare({}, "Q2FY26", "Q2FY25", 10.0, 17.5, 1000, 1000).kind == "same"
    assert eps_adjust.compare({}, "Q2FY26", "Q2FY25", 20.0, 10.0, 1000, 1000).kind == "blank"   # 0.5x: a consolidation
    c = eps_adjust.compare({}, "Q2FY26", "Q2FY25", 10.0, 20.0, 1000, 1000)
    assert c.kind == "blank" and "possible bonus or split not on record" in c.note


def _tagged(yoy):
    metrics_ = [FinancialMetric(metric="eps", period="Q2FY26", value=11.4, unit="INR", yoy_pct=yoy),
                FinancialMetric(metric="eps", period="Q2FY25", value=20.0, unit="INR"),
                FinancialMetric(metric="pat", period="Q2FY26", value=15390.0, yoy_pct=14.0),
                FinancialMetric(metric="pat", period="Q2FY25", value=13500.0)]
    return XbrlResult("RESULTS", "CONSOLIDATED", "Q2FY26", metrics_)


def test_results_file_off_is_byte_identical_and_on_adjusts(monkeypatch):
    monkeypatch.delenv("EPS_SHARE_ADJUST", raising=False)
    off, untouched = _tagged(-43.0), _tagged(-43.0)
    assert eps_adjust.adjust_result(off, BONUS) == 0 and off.table() == untouched.table()
    assert results_card._changes(off.metrics[0]) == results_card._changes(untouched.metrics[0])
    monkeypatch.setenv("EPS_SHARE_ADJUST", "1")
    assert eps_adjust.adjust_result(off, BONUS) == 1
    m = off.metrics[0]
    assert m.yoy_pct == 14.0 and m.eps_note == "adjusted for bonus 1:1 on 2024-10-28"
    assert "adjusted for bonus 1:1 on 2024-10-28" in off.table()
    assert "+14.0% YoY" in results_card._changes(m) and results_card._line(m).endswith("(adjusted for bonus 1:1 on 2024-10-28)")
    assert "eps_note" not in m.model_dump()              # never stored in the model's answer


def test_results_file_with_no_record_blanks_the_change(on):
    t = _tagged(-43.0)
    assert eps_adjust.adjust_result(t, {}) == 1
    assert t.metrics[0].yoy_pct is None and "not comparable" in t.metrics[0].eps_note
    t = _tagged(-43.0)
    plain = _tagged(5.0)
    for m in plain.metrics:
        if m.metric == "eps" and m.period == "Q2FY25":
            m.value = 10.9
    assert eps_adjust.adjust_result(plain, {}) == 0 and plain.metrics[0].yoy_pct == 5.0


def _entry(metric, period, value, unit="INR_CR"):
    return {"metric": metric, "period": period, "value": value, "unit": unit, "basis": "CONSOLIDATED",
            "as_of": "2026-01-01", "source_news_id": X + period}


def _dossier(counts, **extra):
    rows = []
    for p, n in counts.items():
        rows += [_entry("revenue", p, 10000.0), _entry("ebitda", p, 2000.0), _entry("pat", p, 1000.0),
                 _entry("eps", p, round(1000 / n, 4), "INR"), _entry("raw_material_cost", p, 3000.0)]
    return {"financial_metrics": rows, "balance_sheet": [], **extra}


def test_metrics_table_adjusts_growth_and_ttm_with_a_record():
    counts = {"Q1FY25": 676, "Q2FY25": 676, "Q3FY25": 1353, "Q4FY25": 1353, "Q1FY26": 1353, "Q2FY26": 1353}
    rows = metrics.table(_dossier(counts, **BONUS), "CONSOLIDATED")
    r = next(r for r in rows if r["period"] == "Q2FY26")
    assert abs(r["eps_yoy"]["value"]) < 0.5 and r["eps_yoy"]["note"] == "adjusted for bonus 1:1 on 2024-10-28"
    assert abs(next(x for x in rows if x["period"] == "Q3FY25")["eps_qoq"]["value"]) < 0.5
    r = next(r for r in rows if r["period"] == "Q1FY26")                  # Q2FY25..Q1FY26 across the bonus
    assert r["ttm_eps"]["value"] == pytest.approx(4 * 1000 / 1353, abs=0.01)
    assert "bonus 1:1" in r["ttm_eps"]["note"]
    bare = metrics.table(_dossier(counts), "CONSOLIDATED")                # no record: still blank
    assert next(r for r in bare if r["period"] == "Q2FY26")["eps_yoy"]["value"] is None


def test_memory_view_shows_the_adjusted_yoy_only_when_on(monkeypatch):
    d = _dossier({"Q2FY25": 676, "Q2FY26": 1353}, **BONUS)
    for e in d["financial_metrics"]:
        e["yoy_pct"] = -50.0 if (e["metric"], e["period"]) == ("eps", "Q2FY26") else None
        e["sources"] = [{"news_id": e["source_news_id"], "as_of": "2026-01-01", "value": e["value"], "unit": e["unit"],
                         "yoy_pct": e["yoy_pct"], "basis": "CONSOLIDATED"}]
    monkeypatch.delenv("EPS_SHARE_ADJUST", raising=False)
    off = str(view_as_of(d, "2027-01-01"))
    assert "YoY -50" in off
    monkeypatch.setenv("EPS_SHARE_ADJUST", "1")
    on_view = str(view_as_of(d, "2027-01-01"))
    assert "YoY -50" not in on_view and "adjusted for bonus 1:1" in on_view


def test_snapshot_row_and_signal_bases(monkeypatch):
    from bse_intel import signals

    periods = {"value": "Q2FY26", "prev_year": "Q2FY25", "prev_quarter": "Q1FY26"}
    row = {"value": 11.4, "prev_year": 20.0, "yoy_pct": -43.0, "prev_quarter": 11.0, "qoq_pct": 3.6}
    monkeypatch.delenv("EPS_SHARE_ADJUST", raising=False)
    assert eps_adjust.snapshot_row(row, BONUS, periods, lambda p: 1000.0) is row
    monkeypatch.setenv("EPS_SHARE_ADJUST", "1")
    out = eps_adjust.snapshot_row(row, BONUS, periods, lambda p: 1000.0 if p != "Q2FY25" else 900.0)
    assert out["yoy_pct"] == 14.0 and out["qoq_pct"] == 3.6 and out["eps_note"] == "adjusted for bonus 1:1 on 2024-10-28"
    out = eps_adjust.snapshot_row({**row, "prev_year": 22.8}, {}, periods, lambda p: 1000.0)
    assert "yoy_pct" not in out and "not comparable" in out["eps_note"]
    cur = {"metric": "eps", "period": "Q2FY26", "value": 11.4}
    old = [{"metric": "eps", "period": "Q2FY25", "value": 20.0}]
    by = {"pat": [{"period": "Q2FY26", "value": 15390.0}, {"period": "Q2FY25", "value": 13500.0}]}
    assert signals._eps_bases(old, cur, BONUS, by)[0]["value"] == 10.0
    assert signals._eps_bases(old, cur, {}, by) == []


# ---------------------------------------------------------------- CARD_EPS_FOLLOWS_PROFIT (F183, TODO 78)
def _wipro(eps_now=3.23, eps_year=2.74, eps_qtr=2.50, actions=None):
    """Wipro's card (nse-106820253, 26 Oct 2026): EPS 3.23 against 2.74 and 2.50 where profit rose 1%."""
    def m(metric, period, value, news="n1", unit="INR_CR"):
        return {"metric": metric, "period": period, "value": value, "unit": unit, "source_news_id": news, "as_of": "2026-10-01"}
    d = {"financial_metrics": [
        m("revenue", "Q2FY27", 23000.0, "n2"), m("revenue", "Q2FY26", 22400.0), m("revenue", "Q1FY27", 22800.0),
        m("ebitda", "Q2FY27", 4400.0, "n2"), m("ebitda", "Q2FY26", 4300.0), m("ebitda", "Q1FY27", 4350.0),
        m("pat", "Q2FY27", 3300.0, "n2"), m("pat", "Q2FY26", 3250.0), m("pat", "Q1FY27", 3267.0),
        m("eps", "Q2FY27", eps_now, "n2", "INR"), m("eps", "Q2FY26", eps_year, unit="INR"), m("eps", "Q1FY27", eps_qtr, unit="INR")]}
    if actions:
        d["corporate_actions"] = actions
    return d


RELEASE_EPS = "Wipro Q2FY27: Revenue 23,000 Cr. EPS up 0.9% QoQ at Rs 3.23. Profit 3,300 Cr."


def test_an_eps_change_the_profit_does_not_carry_is_shown_off_and_left_out_on(monkeypatch):
    from bse_intel.dossier import results_snapshot
    monkeypatch.delenv("CARD_EPS_FOLLOWS_PROFIT", raising=False)
    off = results_snapshot(_wipro(), "n2")
    assert off["eps"]["yoy_pct"] == 17.9 and off["eps"]["prev_quarter"] == 2.5 and "eps_hidden" not in off
    monkeypatch.setenv("CARD_EPS_FOLLOWS_PROFIT", "1")
    on = results_snapshot(_wipro(), "n2")
    assert on["eps"] == {"value": 3.23, "eps_note": on["eps"]["eps_note"]}   # neither change, nor the bases they rest on
    assert "is above profit +1.5% and no share-count event is on record" in on["eps"]["eps_note"]
    assert [h["slot"] for h in on["eps_hidden"]] == ["yoy", "qoq"]


def test_a_change_the_profit_carries_is_kept(monkeypatch):
    from bse_intel.dossier import results_snapshot
    monkeypatch.setenv("CARD_EPS_FOLLOWS_PROFIT", "1")
    on = results_snapshot(_wipro(eps_year=3.17, eps_qtr=3.2), "n2")   # profit +1.5% / +1.0%, EPS +1.9% / +0.9%
    assert on["eps"]["yoy_pct"] == 1.9 and on["eps"]["prev_quarter"] == 3.2 and "eps_hidden" not in on


def test_the_filings_words_never_replace_the_change(monkeypatch):
    # only hidden, never replaced (review: "EPS declined by 5%" was read as +5%)
    from bse_intel.dossier import results_snapshot
    monkeypatch.setenv("CARD_EPS_FOLLOWS_PROFIT", "1")
    on = results_snapshot(_wipro(), "n2", printed=RELEASE_EPS)
    assert on["eps"]["value"] == 3.23 and "yoy_pct" not in on["eps"] and "qoq_pct" not in on["eps"]   # no +0.9% from the words


def test_a_recorded_bonus_leaves_the_change_to_the_share_base_logic(monkeypatch):
    from bse_intel.dossier import results_snapshot
    monkeypatch.setenv("CARD_EPS_FOLLOWS_PROFIT", "1")
    bonus = [{"ex_date": "2026-09-01", "kind": "BONUS", "factor": 2.0, "subject": "BONUS 1:1"}]
    on = results_snapshot(_wipro(eps_qtr=6.4, eps_year=6.3, actions=bonus), "n2")
    assert "eps_hidden" not in on and on["eps"]["prev_quarter"] == 6.4   # a share-count event on record: not this switch's call


def test_follows_allows_dilution_and_noise_but_not_eps_far_above_profit():
    from bse_intel.eps_adjust import follows
    assert follows(1.5, 17.9) is False                       # Wipro: EPS +17.9% on profit +1.5%
    assert follows(10.0, 14.0) and follows(10.0, 4.0)        # within 5 points plus share-count noise
    assert follows(20.0, 9.0) and follows(8.0, -2.0)         # below profit: real dilution (a QIP), shown
    assert follows(0.0, 15.0, base=0.08)                     # a small EPS: its last printed digit is 12.5% of 0.08
    assert follows(0.0, 25.0, base=0.08) is False            # 0.08 to 0.10 is more than rounding
    assert follows(-10.0, 5.0) is False                      # EPS up while profit fell, no buyback on record
