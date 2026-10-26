"""scripts/release_check.py, the checks of F171-F173 (CARD_GROUNDED_FIGURES, CARD_GUIDANCE_DATED, CARD_ONE_BASIS), on fake
stored cards and fake memory: what is replayed is replayed, what cannot be is listed and never faked. No network."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict

import pytest

from bse_intel.event_xbrl import Order
from test_card_grounded_figures import OMAXE_TEXT, _emmvee
from test_release_check import _script

FILED = "2026-10-20T10:00:00+05:30"


@pytest.fixture(autouse=True)
def _off(monkeypatch):
    for n in ("CARD_GROUNDED_FIGURES", "CARD_GUIDANCE_DATED", "CARD_ONE_BASIS"):
        monkeypatch.delenv(n, raising=False)


def _row(news_id="nse-1", scrip="1", **kw):
    return {"news_id": news_id, "scrip_code": scrip, "symbol": "ACME", "company_name": "Acme", "filed_at": FILED,
            "pdf_url": "https://example.test/f.pdf", "headline": "h", **kw}


# ---------------------------------------------------------------- F171
def test_the_footer_kpi_in_megawatts_is_shown_off_and_gone_on():
    rc = _script()
    card = {"event_type": "RESULTS", "results": {"period": "Q2FY27", "lines": [
        {"key": "kpi:order_book", "label": "Order book", "unit": "cr"}],
        "kpi:order_book": {"value": 10404.0, "prev_quarter": 9.9, "qoq_pct": 104990.9}}}
    rec = rc.check_grounded(card, _emmvee(), _row(), None, "Q2FY27", True)
    (change,) = rec["diff"]["changed"]
    assert "qoq_pct 104990.9" in change["before"] and change["after"] == "TABLE Order book: (not shown)"
    assert rec["info"]["footer_kpi_cards_checked"] == 1 and rec["unreplayable"] == []


def test_a_kpi_card_without_memory_is_not_replayable_and_is_listed():
    rc = _script()
    card = {"event_type": "RESULTS", "headline": "H", "results": {"lines": [{"key": "kpi:order_book", "label": "Order book", "unit": "cr"}]}}
    rec = rc.check_grounded(card, None, _row(), None, "Q2FY27", True)
    assert not rc.changed_by_diff(rec["diff"])
    assert len(rec["unreplayable"]) == 1 and "memory" in rec["unreplayable"][0]["reason"]
    assert rec["unreplayable"][0]["pdf_url"] == "https://example.test/f.pdf"


def _cancelled(stage="CANCELLED"):
    return {"event_type": "LITIGATION_REGULATORY", "impact_level": "LOW", "headline": "Omaxe receives RERA approval", "takeaway": "t",
            "what_happened": ["x"],
            "deal_value": {"kind": "OTHER", "amount_cr": None, "stage": stage}}


def test_the_template_withdrawal_row_stops_a_deal_being_cancelled_and_a_real_withdrawal_does_not():
    rc = _script()
    rec = rc.check_grounded(_cancelled(), None, _row(), OMAXE_TEXT, None, False)
    assert rec["diff"]["changed"] == [{"before": "DEAL stage: CANCELLED", "after": "DEAL stage: OTHER"}]
    real = rc.check_grounded(_cancelled(), None, _row(), "The Board has withdrawn the proposed acquisition", None, False)
    assert not rc.changed_by_diff(real["diff"]) and real["info"]["cancelled_deals_checked"] == 1
    # the text read here does not terminate it even off: no change is claimed for the switch
    other = rc.check_grounded(_cancelled(), None, _row(), "Nothing about it", None, False)
    assert not rc.changed_by_diff(other["diff"]) and other["info"]["cancelled_deal_not_reproduced_off"] == 1
    assert rc.check_grounded(_cancelled("COMPLETED"), None, _row(), OMAXE_TEXT, None, False)["info"] == {}


def test_a_cancelled_deal_with_no_stored_text_is_not_replayable():
    rc = _script()
    rec = rc.check_grounded(_cancelled(), None, _row(), None, None, False)
    assert not rc.changed_by_diff(rec["diff"]) and "text" in rec["unreplayable"][0]["reason"]


def _order(amount, who="Rail Vikas"):
    return asdict(Order(amount_cr=amount, counterparty=who, received=True, announcement="New", dated=None, execution_by=None,
                        includes_gst=None, related_party=None, promoter_interest=None, domestic=None))


def test_an_only_order_read_as_rupees_is_found_exactly_but_its_on_value_is_not_replayable():
    rc = _script()
    card = {"event_type": "ORDER_WIN", "headline": "DSSL wins an order", "event_xbrl": {"orders": [_order(0.0)]},
            "deal_value": {"kind": "ORDER", "amount_cr": 0.0}}
    rec = rc.check_grounded(card, None, _row(), None, None, False)
    assert not rc.changed_by_diff(rec["diff"])           # nothing is invented
    assert rec["info"] == {"cards_with_event_xbrl_orders": 1, "order_amount_under_1_lakh": 1}
    (u,) = rec["unreplayable"]
    assert "model's own figure" in u["reason"] and any("amount_cr 0.0" in x for x in u["stored"])


def test_of_two_orders_the_one_under_a_lakh_is_dropped_and_the_other_is_applied_to_the_models_deal():
    rc = _script()
    card = {"event_type": "ORDER_WIN", "headline": "x", "event_xbrl": {"orders": [_order(0.0), _order(12.5)]},
            "deal_value": {"kind": "ORDER", "amount_cr": 99.0, "counterparty": "Someone"}}
    rec = rc.check_grounded(card, None, _row(), None, None, False)
    (change,) = rec["diff"]["changed"]
    assert "amount_cr 99.0" in change["before"] and "amount_cr 12.5" in change["after"] and "Rail Vikas" in change["after"]
    assert rec["unreplayable"] == []
    fine = {**card, "event_xbrl": {"orders": [_order(137.15)]}}
    assert not rc.changed_by_diff(rc.check_grounded(fine, None, _row(), None, None, False)["diff"])


# ---------------------------------------------------------------- F172
def _guided(**kw):
    g = {"id": "g_1", "statement": "EBITDA margin guidance", "metric": "ebitda_margin", "target": "21% to 24%", "due": "Medium term",
         "due_date": None, "given_on": "2026-05-04T17:55:34+05:30", "source_news_id": "nse-old", "status": "MISSED",
         "status_history": [{"status": "MISSED", "evidence": "Q2FY27 margin 15.11%, below the band.", "as_of": FILED,
                             "source_news_id": "nse-1"}], **kw}
    return {"guidance": [g], "watchlist": [],
            "financial_metrics": [{"metric": "ebitda_margin", "period": "Q2FY27", "value": 15.11, "unit": "PCT", "as_of": FILED,
                                   "source_news_id": "nse-1"}]}


def _stored_breach():
    return {"event_type": "RESULTS", "impact_level": "LOW", "headline": "Acme Q2 results", "takeaway": "t",
            "what_happened": ["x"], "signals": [
        {"type": "GUIDANCE_BREACH", "severity": "WARNING", "ref": "g_1", "text": "Missed: guided 2026-05-04"}]}


def test_an_undated_target_missed_off_is_an_info_line_on_and_memory_would_not_record_it():
    rc = _script()
    rec = rc.check_guidance(_stored_breach(), _guided(), _row())
    changed = {c["before"].split(":")[0]: c for c in rec["diff"]["changed"]}
    sig = changed["SIGNAL g_1"]
    assert "GUIDANCE_BREACH WARNING" in sig["before"] and "WATCH_RESOLVED INFO" in sig["after"]
    assert "Management said on 2026-05-04" in sig["after"]
    mem = changed["MEMORY g_1"]   # the recorded MISSED is refused: the target has no date
    assert "status MISSED recorded" in mem["before"] and "not recorded" in mem["after"] and "no date" in mem["after"]
    assert rec["info"] == {"stored_guidance_signals": 1, "stored_signals_reproduced_off": 1} and rec["unreplayable"] == []


def test_a_dated_target_for_this_quarter_and_metric_keeps_its_verdict():
    rc = _script()
    rec = rc.check_guidance(_stored_breach(), _guided(due="Q2FY27", due_date="2026-09-30"), _row())
    assert not rc.changed_by_diff(rec["diff"])


def test_a_stored_signal_that_memory_cannot_reproduce_is_listed_not_replayed():
    rc = _script()
    mem = _guided()
    mem["guidance"][0]["status_history"] = []           # memory rewritten since: nothing records the model's update
    rec = rc.check_guidance(_stored_breach(), mem, _row())
    assert not rc.changed_by_diff(rec["diff"])
    (u,) = rec["unreplayable"]
    assert "not reproduced" in u["reason"] and "g_1" in u["stored"][0]
    none = rc.check_guidance(_stored_breach(), None, _row())
    assert none["unreplayable"] and "memory is not available" in none["unreplayable"][0]["reason"]
    assert rc.check_guidance({"event_type": "RESULTS"}, None, _row())["unreplayable"] == []


# ---------------------------------------------------------------- F173
def _memory_rows(**series):
    return [{"metric": m, "period": p, "value": v, "unit": "INR_CR", "as_of": "2026-10-01T00:00:00+05:30",
             "source_news_id": "xbrl:res:1"} for m, by in series.items() for p, v in by.items()]


def _ltts_card():
    return {"event_type": "RESULTS", "basis": "CONSOLIDATED", "impact_level": "MODERATE", "timeline_entry": "Q2 results",
            "headline": "LTTS Q2FY27: net profit ₹548.7 Cr (+66.7% YoY)", "takeaway": "Net profit ₹548.7 Cr.",
            "what_happened": [{"text": "Net profit Q2FY27: ₹548.7 Cr (+66.7% YoY).", "quote": "pat 548.7"}],
            "key_numbers": [{"label": "Net profit", "value": "₹548.70 Cr", "change": "+66.7% YoY"},
                            {"label": "EPS", "value": "₹35.78 per share", "change": "+15.3% YoY"}],
            "results": {"period": "Q2FY27", "lines": [{"key": "pat", "label": "PAT", "unit": "cr"}],
                        "pat": {"value": 548.7, "prev_year": 329.2, "yoy_pct": 66.7}}}


def test_a_profit_with_a_discontinued_part_is_labelled_and_its_eps_change_removed():
    rc = _script()
    mem = {"financial_metrics": _memory_rows(pat={"Q2FY27": 548.7, "Q2FY26": 329.2}, pat_continuing={"Q2FY27": 380.1, "Q2FY26": 329.2})}
    rec = rc.check_one_basis(_ltts_card(), mem, _row(), "Q2FY27")
    changed = {c["before"].split(" ")[0]: c for c in rec["diff"]["changed"]}
    assert "discontinued operations" in changed["HEADLINE"]["after"] and "380.1" in changed["HEADLINE"]["after"]
    eps = next(c for c in rec["diff"]["changed"] if "EPS" in c["before"])
    assert "+15.3% YoY" in eps["before"] and "+15.3%" not in eps["after"]
    assert rec["extra"] and rec["unreplayable"] == []


def test_a_results_table_on_the_other_basis_is_removed_and_a_card_with_no_issue_is_unchanged():
    rc = _script()
    card = _ltts_card()
    mem = {"financial_metrics": [{"metric": "revenue", "period": "Q2FY27", "value": 3040.4, "unit": "INR_CR", "basis": "STANDALONE",
                                  "as_of": "2026-10-01T00:00:00+05:30", "source_news_id": "xbrl:res:1"}]}
    card["results"]["lines"].append({"key": "revenue", "label": "Revenue", "unit": "cr"})
    card["results"]["revenue"] = {"value": 3040.4}
    rec = rc.check_one_basis(card, mem, _row(), "Q2FY27")
    assert any("standalone" in n for n in rec["extra"])
    assert "TABLE: (none)" in rec["diff"]["added"] and any(x.startswith("TABLE revenue") for x in rec["diff"]["removed"])
    plain = {"event_type": "ORDER_WIN", "impact_level": "LOW", "headline": "Acme wins an order", "takeaway": "t", "what_happened": ["x"]}
    assert not rc.changed_by_diff(rc.check_one_basis(plain, None, _row(), None)["diff"])


# ---------------------------------------------------------------- the run
def test_the_run_writes_the_three_new_reports_and_the_not_replayable_lists(tmp_path, monkeypatch):
    rc = _script()
    cards = [
        _row("nse-1", card_json=json.dumps(_stored_breach())),
        _row("n2", card_json=json.dumps({"event_type": "ORDER_WIN", "impact_level": "LOW", "headline": "DSSL wins an order", "takeaway": "t",
                                         "what_happened": ["x"], "event_xbrl": {"orders": [_order(0.0)]},
                                         "deal_value": {"kind": "ORDER", "amount_cr": 0.0}})),
        _row("n3", scrip="2", card_json=json.dumps(_cancelled())),
    ]
    (tmp_path / "texts").mkdir()
    (tmp_path / "dossiers").mkdir()
    (tmp_path / "dossiers" / "1.json").write_text(json.dumps(_guided()))
    (tmp_path / "cards.json").write_text(json.dumps(cards))
    before = dict(os.environ)
    monkeypatch.setattr(sys, "argv", ["release_check.py", str(tmp_path / "out"), "--cards", str(tmp_path / "cards.json"),
                                      "--texts", str(tmp_path / "texts"), "--dossiers", str(tmp_path / "dossiers"),
                                      "--only", "grounded_figures,guidance_dated,one_basis", "--sample", "5"])
    assert rc.main() == 0
    assert dict(os.environ) == before
    out = tmp_path / "out"
    total = json.loads((out / "release-check.json").read_text(encoding="utf-8"))
    assert total["guidance_dated"]["cards_changed"] == 1 and total["guidance_dated"]["stored_signals_reproduced_off"] == 1
    assert total["grounded_figures"]["cards_changed"] == 0 and total["grounded_figures"]["not_replayable_cards"] == 2
    assert total["one_basis"]["cards_changed"] == 0 and total["one_basis"]["errors"] == 0
    listed = json.loads((out / "grounded_figures-unreplayable.json").read_text(encoding="utf-8"))
    assert {u["news_id"] for u in listed} == {"n2", "n3"}
    md = (out / "grounded_figures-unreplayable.md").read_text(encoding="utf-8")
    assert "https://example.test/f.pdf" in md and "why not replayable" in md
    assert "not replayable 2" in (out / "release-check.txt").read_text(encoding="utf-8")
    for name in total:
        for suffix in (".json", ".txt", "-blind.json", "-blind.md", "-key.json"):
            assert (out / f"{name}{suffix}").exists()
