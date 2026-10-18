"""The timeline tier (decision D22): routine filings get one dated line and no card."""
import json
from datetime import timedelta

from bse_intel.timeutil import now_ist

from test_pipeline import PASS2, _filing, _pdf, build

PASS1_MODEL = "openai/gpt-oss-20b"
LINE = {"entry": "Board recommends a final dividend of Rs 5 per share for FY25.", "event_type": "CORPORATE_ACTION",
        "needs_card": False, "reason": "dividend recommendation only"}
TEXT = "Pursuant to Regulation 30, the Board has recommended a final dividend of Rs 5 per share for FY25, subject to approval."


def _routine(news_id, when, headline="Board recommends final dividend of Rs 5 per share"):
    f = _filing(news_id, headline, when, "Company Update")
    return f.model_copy(update={"route": "TIMELINE", "event_type": "CORPORATE_ACTION"})


def test_a_routine_filing_gets_a_timeline_line_and_no_card(settings):
    now = now_ist() - timedelta(hours=2)
    f = _routine("n-div", now)
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(TEXT)}, {PASS1_MODEL: [json.dumps(LINE)]}, env={"GROQ_API_KEY": "g"})
    outcome = pipeline.analyze(f)
    assert outcome.card is None and outcome.update["status"] == "NOT_MATERIAL"
    assert outcome.update["reason"].startswith("timeline only: Board recommends a final dividend")
    timeline = sink.get_dossier("999001")["timeline"]
    assert [(t["summary"], t["tier"], t["news_id"]) for t in timeline] == [(LINE["entry"], "TIMELINE", "n-div")]
    assert pipeline.stats.timeline_only == 1 and len(fake.calls) == 1  # one cheap call, no Pass 2


def test_the_same_event_filed_twice_is_one_timeline_line(settings):
    """SML Mahindra's MD and CEO change reached the feed as three cards worded differently."""
    now = now_ist() - timedelta(hours=2)
    first, again = _routine("n-1", now), _routine("n-2", now + timedelta(hours=1), "Intimation of recommendation of final dividend")
    reply = dict(LINE, entry="The Board has recommended a final dividend of Rs 5 per share for FY25")
    pipeline, sink, fake = build(settings, [first, again], {f.pdf_url: _pdf(TEXT) for f in (first, again)},
                                 {PASS1_MODEL: [json.dumps(LINE), json.dumps(reply)]}, env={"GROQ_API_KEY": "g"})
    pipeline.analyze(first)
    second = pipeline.analyze(again)
    assert second.update["status"] == "DUPLICATE" and "n-1" in second.update["reason"]
    assert len(sink.get_dossier("999001")["timeline"]) == 1


def test_a_consequential_filing_goes_back_for_a_full_card(settings):
    now = now_ist() - timedelta(hours=2)
    f = _routine("n-big", now, "Outcome of board meeting - dividend, fund raise and acquisition")
    ask = dict(LINE, needs_card=True, event_type="FUNDRAISE", reason="a fundraise in the same letter")
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(TEXT)},
                                 {PASS1_MODEL: [json.dumps(ask)], "nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]},
                                 env={"GROQ_API_KEY": "g", "NVIDIA_API_KEY": "n"})
    outcome = pipeline.analyze(f)
    assert outcome.card is not None and fake.calls[0]["model"] == PASS1_MODEL and len(fake.calls) >= 2  # the timeline call, then Pass 2
    assert pipeline.stats.timeline_only == 0


def test_a_management_change_gets_no_card_even_when_pass_2_types_it(settings):
    """Owner, 2026-10-18: no cards for director / KMP changes. The rule book drops most of them before any model call;
    one that still reaches pass 2 (an appointment in a board-meeting letter) ends without a card or memory change."""
    now = now_ist() - timedelta(hours=3)
    a = _filing("n-a", "Outcome of board meeting", now, "Company Update")
    a = a.model_copy(update={"route": "FAST_TRACK", "event_type": None})   # the board-outcome rule sets none
    one = json.loads(json.dumps(PASS2))
    one["event_type"] = "MANAGEMENT_CHANGE"
    one["timeline_entry"] = "Yasushi Nishikawa appointed Managing Director and CEO from 17 April 2025, succeeding Junya Yamanishi."
    pipeline, sink, fake = build(settings, [a], {a.pdf_url: _pdf("Appointment of Managing Director and CEO")},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(one)]}, env={"NVIDIA_API_KEY": "n"})
    first = pipeline.analyze(a)
    assert first.card is None and first.update["status"] == "NOT_MATERIAL"
    assert "director / KMP" in first.update["reason"]
    assert not (sink.get_dossier("999001") or {}).get("timeline")
