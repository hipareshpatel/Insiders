"""MEMORY_YEAR_CHECK (F177, TODO 64-65): a year's figure that does not match its quarters, and the owners' / minorities' swap,
are held at read time, on fake dossiers built from the real cases of the NSE self-check (26 Oct 2026). Nothing stored changes."""
from __future__ import annotations

import copy
import json
import sys

import pytest

from bse_intel import year_check
from bse_intel.dossier import dossier_as_of, latest_fundamentals, results_snapshot, view_as_of, with_year_hold
from test_release_check import _script

AS_OF = "2026-10-20T10:00:00+05:30"
FILED = "2026-10-26T10:00:00+05:30"


@pytest.fixture(autouse=True)
def _off(monkeypatch):
    monkeypatch.delenv("MEMORY_YEAR_CHECK", raising=False)


def m(metric, period, value, news="nse-1", basis="CONSOLIDATED", as_of=AS_OF):
    src = {"news_id": news, "as_of": as_of, "value": value, "unit": "INR_CR", "basis": basis}
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "as_of": as_of, "source_news_id": news,
            "basis": basis, "sources": [src]}


def quarters(metric, fy, values, **kw):
    return [m(metric, f"Q{i}{fy}", v, **kw) for i, v in enumerate(values, 1)]


def glenmark():
    """FY26: profit 1,361.95 Cr, owners 0.10 and minorities 1,361.85 (swapped); FY25 owners 1,047 and minorities 0.45."""
    return {"financial_metrics": [
        m("pat", "FY26", 1361.95), m("pat_owners", "FY26", 0.10), m("pat_minority", "FY26", 1361.85),
        m("pat", "FY25", 1047.45), m("pat_owners", "FY25", 1047.0), m("pat_minority", "FY25", 0.45),
        *quarters("pat", "FY26", [300.0, 330.0, 350.0, 381.95])]}


def nitco():
    """FY25 the same swap, in a small company; FY24 owners are nearly all of the profit."""
    return {"financial_metrics": [
        m("pat", "FY25", 21.4), m("pat_owners", "FY25", 0.02), m("pat_minority", "FY25", 21.38),
        m("pat", "FY24", 18.0), m("pat_owners", "FY24", 17.9), m("pat_minority", "FY24", 0.1)]}


def held(entries):
    return year_check.held_figures(entries)


# ---------------------------------------------------------------- (B) the swap
def test_a_glenmark_style_swap_holds_owners_and_minorities_with_a_reason():
    got = held(glenmark()["financial_metrics"])
    assert set(got) == {("pat_owners", "FY26"), ("pat_minority", "FY26")}
    why = got[("pat_owners", "FY26")]
    assert "swapped against FY25" in why and "0.10" in why and "1,361.95" in why and "1,047.00" in why
    assert got[("pat_minority", "FY26")] == why


def test_nitco_fy25_is_held_against_fy24():
    got = held(nitco()["financial_metrics"])
    assert set(got) == {("pat_owners", "FY25"), ("pat_minority", "FY25")}
    assert "swapped against FY24" in got[("pat_owners", "FY25")]


def test_owners_low_without_a_normal_year_before_is_not_a_swap():
    rows = [m("pat", "FY26", 100.0), m("pat_owners", "FY26", 2.0), m("pat", "FY25", 90.0), m("pat_owners", "FY25", 40.0)]
    assert held(rows) == {}            # the year before was 44% owners: a real minority-heavy group, not a swap
    assert held(rows[:2]) == {}        # no year before at all: it cannot be judged


def test_a_swapped_quarter_is_held_too():
    rows = [m("pat", "Q2FY27", 80.0), m("pat_owners", "Q2FY27", 1.0), m("pat_minority", "Q2FY27", 79.0),
            m("pat", "Q2FY26", 70.0), m("pat_owners", "Q2FY26", 69.0)]
    assert set(held(rows)) == {("pat_owners", "Q2FY27"), ("pat_minority", "Q2FY27")}


# ---------------------------------------------------------------- (A) the year against its quarters
def test_the_leela_style_year_that_misses_its_quarters_is_held_and_a_normal_year_is_not():
    bad = quarters("pat", "FY26", [90.0, 100.0, 110.0, 103.0]) + [m("pat", "FY26", 33.0)]
    got = held(bad)
    assert list(got) == [("pat", "FY26")] and "Q1-Q4 sum 403.00, FY 33.00" in got[("pat", "FY26")]
    assert held(quarters("pat", "FY26", [90.0, 100.0, 110.0, 103.0]) + [m("pat", "FY26", 403.4)]) == {}   # rounding


def test_h1_and_nine_months_are_checked_against_their_own_quarters():
    rows = quarters("revenue", "FY27", [100.0, 110.0, 120.0]) + [m("revenue", "H1FY27", 150.0), m("revenue", "9MFY27", 330.0)]
    got = held(rows)
    assert list(got) == [("revenue", "H1FY27")] and "Q1-Q2 sum 210.00" in got[("revenue", "H1FY27")]


def test_a_year_with_a_missing_quarter_is_not_held_because_it_cannot_be_checked():
    rows = quarters("pat", "FY26", [90.0, 100.0, 110.0])[:3] + [m("pat", "FY26", 33.0)]
    assert held(rows) == {}
    mixed = quarters("pat", "FY26", [90.0, 100.0, 110.0, 103.0]) + [m("pat", "FY26", 33.0, basis="STANDALONE")]
    assert held(mixed) == {}           # a year on one basis against quarters on another is no sum


def test_a_balance_a_ratio_and_a_cash_flow_are_not_summed():
    rows = [m(name, f"Q{i}FY26", 10.0) for name in ("net_worth", "operating_cash_flow") for i in range(1, 5)]
    rows += [m("net_worth", "FY26", 10.0), m("operating_cash_flow", "FY26", 99.0)]
    assert held(rows) == {}


# ---------------------------------------------------------------- the readers
def test_switch_off_is_the_same_dossier_and_the_stored_one_is_never_changed(monkeypatch):
    d = glenmark()
    before = copy.deepcopy(d)
    assert with_year_hold(d) is d
    monkeypatch.setenv("MEMORY_YEAR_CHECK", "1")
    on = with_year_hold(d)
    assert d == before and on is not d
    assert {(e["metric"], e["period"]) for e in on["financial_metrics"]} \
        == {(e["metric"], e["period"]) for e in d["financial_metrics"]} - {("pat_owners", "FY26"), ("pat_minority", "FY26")}
    assert [h["metric"] for h in on["year_held"]] == ["pat_minority", "pat_owners"] and all(h["reason"] for h in on["year_held"])
    clean = {"financial_metrics": quarters("pat", "FY26", [1.0, 2.0, 3.0, 4.0]) + [m("pat", "FY26", 10.0)]}
    assert with_year_hold(clean) is clean


def _q4_dossier():
    """Q4FY27 reported by nse-1; Q4FY26 was never stored: it is FY26 less 9MFY26, and 9MFY26 does not match Q1-Q3 FY26."""
    rows = [m("revenue", "Q4FY27", 500.0, news="nse-1"), m("revenue", "Q3FY27", 450.0, news="nse-0"),
            *quarters("revenue", "FY26", [100.0, 110.0, 120.0]), m("revenue", "9MFY26", 600.0), m("revenue", "FY26", 1000.0)]
    return {"financial_metrics": rows}


def test_a_derived_q4_is_not_built_from_a_held_year_figure(monkeypatch):
    off = results_snapshot(_q4_dossier(), "nse-1")
    assert off["revenue"]["prev_year"] == 400.0 and off["revenue"]["derived"] == ["prev_year"]   # FY less 9M: what it was
    assert "held" not in off
    monkeypatch.setenv("MEMORY_YEAR_CHECK", "1")
    on = results_snapshot(_q4_dossier(), "nse-1")
    assert "prev_year" not in on["revenue"] and "yoy_pct" not in on["revenue"] and on["revenue"]["value"] == 500.0
    (reason,) = [h for h in on["held"] if h["period"] == "9MFY26"]
    assert reason["metric"] == "revenue" and "nine months does not match its quarters" in reason["reason"]


def test_a_quarter_whose_owners_share_is_swapped_shows_no_owners_line(monkeypatch):
    rows = [m("revenue", "Q2FY27", 900.0), m("pat", "Q2FY27", 80.0), m("pat_owners", "Q2FY27", 1.0),
            m("revenue", "Q2FY26", 800.0), m("pat", "Q2FY26", 70.0), m("pat_owners", "Q2FY26", 69.0)]
    off = latest_fundamentals({"financial_metrics": rows})
    assert off["revenue"]["value"] == 900.0
    monkeypatch.setenv("MEMORY_YEAR_CHECK", "1")
    snap = results_snapshot({"financial_metrics": rows}, "nse-1")
    assert snap["pat"]["value"] == 80.0
    assert {(h["metric"], h["period"]) for h in snap["held"]} == {("pat_owners", "Q2FY27")}


def test_the_prompt_view_leaves_a_held_year_out_and_off_it_is_there(monkeypatch):
    d = {"financial_metrics": quarters("pat", "FY26", [90.0, 100.0, 110.0, 103.0]) + [m("pat", "FY26", 33.0)]}
    text = lambda: json.dumps(view_as_of(d, FILED), default=str)   # noqa: E731
    assert "FY26: 33" in text()
    monkeypatch.setenv("MEMORY_YEAR_CHECK", "1")
    assert "FY26: 33" not in text() and "Q4FY26: 103" in text()


def test_the_year_hold_works_on_memory_as_of_a_filing(monkeypatch):
    monkeypatch.setenv("MEMORY_YEAR_CHECK", "1")
    current = dossier_as_of(glenmark(), FILED)
    assert {h["metric"] for h in with_year_hold(current)["year_held"]} == {"pat_owners", "pat_minority"}


def test_nse_selfcheck_still_reads_the_shared_helpers():
    from bse_intel import nse_selfcheck as sc
    assert sc.close is year_check.close and sc.SUM_METRICS is year_check.SUM_METRICS and sc.ROUND_PCT == 0.5


# ---------------------------------------------------------------- the release check
ROW = {"news_id": "nse-1", "scrip_code": "1", "symbol": "ACME", "company_name": "Acme", "filed_at": FILED,
       "pdf_url": "https://example.test/f.pdf", "headline": "h"}


def _card():
    return {"event_type": "RESULTS", "results": {"period": "Q4FY27", "revenue": {"value": 500.0, "prev_year": 400.0, "yoy_pct": 25.0}}}


def test_the_release_check_replays_the_table_off_and_on_and_lists_the_held_figure():
    rc = _script()
    assert "MEMORY_YEAR_CHECK" in rc.ALL_SWITCHES and ("year_check", "MEMORY_YEAR_CHECK") in rc.CHECKS
    rec = rc.check_year(_card(), _q4_dossier(), ROW, None, "Q4FY27")
    assert any("prev_year 400.0" in x for x in rec["off_lines"]) and not any("prev_year" in x for x in rec["on_lines"])
    assert any(x.startswith("MEMORY held revenue 9MFY26") for x in rec["diff"]["added"])
    assert rc.changed_by_diff(rec["diff"]) and rec["unreplayable"] == [] and rec["info"] == {"cards_with_a_held_figure_in_memory": 1}


def test_the_release_check_lists_a_card_without_memory_and_leaves_a_clean_card_unchanged():
    rc = _script()
    rec = rc.check_year(_card(), None, ROW, None, "Q4FY27")
    assert not rc.changed_by_diff(rec["diff"]) and "memory is not available" in rec["unreplayable"][0]["reason"]
    clean = {"financial_metrics": [m("revenue", "Q4FY27", 500.0), m("revenue", "Q4FY26", 400.0)]}
    same = rc.check_year(_card(), clean, ROW, None, "Q4FY27")
    assert not rc.changed_by_diff(same["diff"]) and same["off_lines"]


def test_the_release_check_run_writes_year_check_and_restores_the_environment(tmp_path, monkeypatch):
    rc = _script()
    (tmp_path / "texts").mkdir()
    (tmp_path / "dossiers").mkdir()
    (tmp_path / "dossiers" / "1.json").write_text(json.dumps(_q4_dossier()))
    (tmp_path / "cards.json").write_text(json.dumps([{**ROW, "card_json": json.dumps(_card())}]))
    import os
    before = dict(os.environ)
    monkeypatch.setattr(sys, "argv", ["release_check.py", str(tmp_path / "out"), "--cards", str(tmp_path / "cards.json"),
                                      "--texts", str(tmp_path / "texts"), "--dossiers", str(tmp_path / "dossiers"),
                                      "--only", "year_check", "--sample", "5"])
    assert rc.main() == 0
    assert dict(os.environ) == before
    total = json.loads((tmp_path / "out" / "release-check.json").read_text(encoding="utf-8"))
    assert total["year_check"]["cards_changed"] == 1 and total["year_check"]["errors"] == 0
    assert (tmp_path / "out" / "year_check.json").exists() and (tmp_path / "out" / "year_check-key.json").exists()


# ---------------------------------------------------------------- item 76 (F181): a held year figure settles no verdict
def _year_prediction_case():
    from bse_intel.dossier import merge, new_dossier
    from bse_intel.models import Pass2Output
    from test_memory import filing, output
    call = filing("call", "2026-07-20T17:00:00+05:30")
    d = merge(new_dossier(call), Pass2Output.model_validate({
        "is_material": True, "event_type": "CONCALL_PRESENTATION",
        "card": {"impact_level": "MODERATE", "headline": "Demo Cement guides a profit above Rs 100 Cr", "what_happened": ["x"],
                 "track_next": {"kpis_to_verify": [{"kpi": "Full-year profit above Rs 100 Cr", "metric": "pat",
                                                    "period": "FY27", "value": 100, "comparison": ">="}]}}}),
        call, "MODERATE", "now")
    # the quarters add up to 100, the year says 250 (The Leela class: a year that misses its quarters)
    metrics = [{"metric": "pat", "period": f"Q{i}FY27", "value": v} for i, v in enumerate([10, 20, 30, 40], 1)] \
        + [{"metric": "pat", "period": "FY27", "value": 250}]
    return d, output(financial_metrics=metrics), filing("q4", "2027-05-20T17:00:00+05:30")


def test_a_held_year_figure_does_not_resolve_a_prediction(monkeypatch):
    from bse_intel.dossier import merge
    d, out, f = _year_prediction_case()
    off = merge(d, out, f, "HIGH", "now")
    assert off["predictions"][0]["status"] == "MET"          # switch off: no change
    monkeypatch.setenv("MEMORY_YEAR_CHECK", "1")
    on = merge(d, out, f, "HIGH", "now")
    assert on["predictions"][0]["status"] == "OPEN" and "actual" not in on["predictions"][0]   # held: no MET / MISSED


def test_a_held_year_figure_triggers_no_signal(monkeypatch):
    from bse_intel.dossier import merge
    from bse_intel.signals import compute
    d, out, f = _year_prediction_case()
    after = merge(d, out, f, "HIGH", "now")                  # stored with the switch off, so the year is in memory
    kinds = ("METRIC_SHIFT", "PREDICTION_RESOLVED")
    off = [s for s in compute(d, after, out, f, {}, every=True) if s["type"] in kinds and ("(FY27)" in s["text"] or s["type"] == "PREDICTION_RESOLVED")]
    assert off
    monkeypatch.setenv("MEMORY_YEAR_CHECK", "1")
    on = [s for s in compute(d, after, out, f, {}, every=True) if s["type"] in kinds and ("(FY27)" in s["text"] or s["type"] == "PREDICTION_RESOLVED")]
    assert not on
