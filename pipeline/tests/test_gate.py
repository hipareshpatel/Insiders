"""The accuracy gate (gate.py). Each test is named after the filing whose card it would have caught."""
import json
from datetime import timedelta

import pytest

from bse_intel import gate
from bse_intel.timeutil import now_ist

from test_pipeline import PASS2, RESULT_TEXT, _filing, _pdf, build


def test_garbled_scan_text_is_flagged_clean_text_is_not():
    """Heritage Foods Q4FY25 and eMudhra's QIP monitoring report: "l0,406.47", "99S.08", "(1,9S7)" in the text layer."""
    clean = " ".join(f"{n:,}.{n % 100:02d}" for n in range(1000, 1400))
    assert not gate.text_is_garbled(clean)
    assert not gate.text_is_garbled(clean + " Q3FY25 30th 2nd 5G INE758C01029 L15209TG1992PLC014332")
    garbled = clean + " l0,406.47 99S.08 (1,9S7) 3l.03.2025 763.S2"
    assert gate.text_is_garbled(garbled)
    assert not gate.text_is_garbled(clean + " l0,406.47 99S.08")  # two stray tokens are not a pattern


def test_a_rupee_amount_written_in_full_cannot_be_crore():
    """Shivam Autotech's 299,99,99,852 (rupees) was written "₹2,99,99,99,852 Cr"."""
    assert gate.impossible_crore_amounts(["Raise ₹2,99,99,99,852 Cr via preference shares"]) == ["2,99,99,99,852"]
    assert gate.impossible_crore_amounts(["Revenue ₹18,137 Cr", "market cap ₹20,00,000 Cr"]) == []


def test_a_deal_size_equal_to_company_revenue_or_net_worth_is_not_a_deal():
    dossier = {"financial_metrics": [{"metric": "revenue", "period": "Q3FY25", "value": 951.96}],
               "balance_sheet": [{"period": "Q2FY25", "net_worth_cr": 1357.5}]}
    assert gate.deal_is_company_figure(951.9, dossier) == "revenue Q3FY25"
    assert gate.deal_is_company_figure(1357.5, dossier) == "net worth Q2FY25"
    assert gate.deal_is_company_figure(396.5, dossier) is None


def test_a_terminated_project_is_not_live():
    """Prism Johnson terminated its 24 MW captive wind project with ReNew."""
    assert gate.is_terminated("Prism Johnson terminates 24 MW captive wind power project with ReNew")
    assert gate.is_terminated("Withdrawal of the open offer")
    assert not gate.is_terminated("Prism Johnson wins ₹128 Cr tax refund")


def test_issue_size_must_follow_from_shares_and_price():
    """SML's open offer: 3,762,628 shares at ₹1,554.60 is ₹584.94 Cr, not ₹5,849 Cr or ₹58 Cr."""
    assert gate.issue_size_mismatch(584.94, 3_762_628, 1554.60) is None
    assert "₹5,849" in gate.issue_size_mismatch(5849.4, 3_762_628, 1554.60)
    assert gate.issue_size_mismatch(58.5, 3_762_628, 1554.60)
    assert gate.issue_size_mismatch(None, 3_762_628, 1554.60) is None  # nothing to compare is not a mismatch


def test_hold_list_parses_and_a_typo_stops_the_run(tmp_path):
    path = tmp_path / "card_holds.txt"
    path.write_text("# holds\n\nn-1 | EBITDA is PBT in the source table\nn-2|wrong column\n", encoding="utf-8")
    assert gate.load_holds(path) == {"n-1": "EBITDA is PBT in the source table", "n-2": "wrong column"}
    assert gate.load_holds(tmp_path / "missing.txt") == {}
    path.write_text("n-3 held without a reason\n", encoding="utf-8")
    with pytest.raises(ValueError, match="card_holds.txt:1"):
        gate.load_holds(path)


def test_a_held_card_is_published_marked_for_review_without_asking_a_second_model(settings):
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-hold", "Unaudited Financial Results for the quarter", now, "Result")
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(RESULT_TEXT)},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]}, env={"NVIDIA_API_KEY": "n"})
    pipeline._holds = {"n-hold": "EBITDA is PBT in the source table"}
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    body = outcome.card["card"]
    assert len(fake.calls) == 1 and outcome.card["needs_review"] == 1
    assert body["review"] == {"status": "HELD", "issues": ["Held after review: EBITDA is PBT in the source table"]}


def test_a_garbled_scan_marks_the_card_for_review(settings):
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-scan", "Unaudited Financial Results for the quarter", now, "Result")
    noisy = RESULT_TEXT + " " + " ".join(f"{n:,}.{n % 100:02d}" for n in range(1000, 1300)) + " l0,406.47 99S.08 (1,9S7) 763.S2"
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(noisy)},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]}, env={"NVIDIA_API_KEY": "n"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "RESULTS"}))
    review = outcome.card["card"]["review"]
    assert outcome.card["needs_review"] == 1 and review["status"] == "HELD" and "garbled" in review["issues"][0]
    assert len(fake.calls) == 1  # a second model cannot repair a scan
