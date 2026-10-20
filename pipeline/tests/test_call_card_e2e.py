"""A call card end to end (scripted model reply, no model called): each takeaway checked on its own, a failed one
never holds the card, and the code block from memory is on the card beside them."""

from __future__ import annotations

import json
from datetime import timedelta

from test_pipeline import _filing, _pdf, build

from bse_intel.timeutil import now_ist

CALL_TEXT = ("Q2FY27 earnings conference call transcript. Good morning everyone and thank you for joining us. "
             "For FY27 we now expect volume growth of 12-14%, supported by the new capacity in the East. "
             "Net debt stood at Rs 1,250 crore at the end of September.")


def test_call_takeaways_are_checked_one_by_one_and_never_hold_the_card(settings):
    now = now_ist() - timedelta(minutes=10)
    f = _filing("n-call", "Transcript of earnings call", now, "Analyst / Investor Meet")
    reply = {
        "is_material": True, "event_type": "CONCALL_PRESENTATION", "timeline_entry": "Q2FY27 call: FY27 volume growth 12-14%",
        "card": {
            "impact_level": "MODERATE", "headline": "Demo Cement guides FY27 volume growth at 12-14% on the Q2 call",
            "what_happened": [{"text": "**FY27 volumes:** growth of 12-14% expected",
                               "quote": "For FY27 we now expect volume growth of 12-14%"}],
            "call_takeaways": [
                {"category": "Guidance", "text": "FY27 volume growth guided at 12-14%",
                 "quote": "For FY27 we now expect volume growth of 12-14%", "memory_refs": [], "versus_prior": None},
                {"category": "Balance sheet & funding", "text": "Net debt down to ₹900 Cr",
                 "quote": "Net debt stood at Rs 1,250 crore at the end of September", "memory_refs": []},
            ],
        },
        "dossier_delta": {"guidance": [{"statement": "Volume growth of 12-14% in FY27", "target": "12-14%", "due": "FY27",
                                        "source_type": "CONCALL"}]},
    }
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(CALL_TEXT)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(reply)] * 3},
                                 env={"NVIDIA_API_KEY": "n", "OPENROUTER_API_KEY": "o"})
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "CONCALL_PRESENTATION"}))
    body = outcome.card["card"]
    assert [(t["text"][:20], t["verified"]) for t in body["call_takeaways"]] == [
        ("FY27 volume growth g", True), ("Net debt down to ₹90", False)]
    assert "900" in body["call_takeaways"][1]["issue"]
    assert body["grounding"]["call_takeaways_unverified"]
    assert not body.get("review")   # a failed takeaway does not hold the card
    # the code block from memory: this call's guidance
    assert any("12-14%" in p["text"] for c in body["call_memory"] for p in c["points"])
