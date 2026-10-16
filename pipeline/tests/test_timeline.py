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


def test_a_management_change_filed_in_other_words_is_one_card(settings):
    """"Yasushi Nishikawa appointed MD & CEO" and "MD & CEO Junya Yamanishi steps down; Nishikawa takes over": one event."""
    now = now_ist() - timedelta(hours=3)
    a = _filing("n-a", "Appointment of Mr Nishikawa as Managing Director and CEO", now, "Company Update")
    b = _filing("n-b", "Resignation of Mr Yamanishi; Nishikawa takes over as Managing Director and CEO", now + timedelta(hours=1), "Company Update")
    a, b = (x.model_copy(update={"route": "FAST_TRACK", "event_type": "MANAGEMENT_CHANGE"}) for x in (a, b))
    one = json.loads(json.dumps(PASS2))
    one["event_type"] = "MANAGEMENT_CHANGE"
    one["timeline_entry"] = "Yasushi Nishikawa appointed Managing Director and CEO from 17 April 2025, succeeding Junya Yamanishi."
    two = json.loads(json.dumps(one))
    two["timeline_entry"] = "Managing Director and CEO Junya Yamanishi steps down; Yasushi Nishikawa takes over as MD and CEO from 17 April 2025."
    pipeline, sink, fake = build(settings, [a, b], {f.pdf_url: _pdf("Appointment of Managing Director and CEO") for f in (a, b)},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(one), json.dumps(two)]}, env={"NVIDIA_API_KEY": "n"})
    first = pipeline.analyze(a)
    assert first.card is not None
    from bse_intel.dossier import merge, new_dossier
    from bse_intel.models import Pass2Output
    sink.put_dossier("999001", merge(new_dossier(a, {}), Pass2Output.model_validate(one), a, "MODERATE", "now"))
    second = pipeline.analyze(b)
    assert second.update["status"] == "DUPLICATE" and "same event" in second.update["reason"]
