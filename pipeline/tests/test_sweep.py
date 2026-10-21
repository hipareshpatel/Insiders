"""The end-of-day sweep (sweep.py; ai-quality plan change 7): held live-window cards with a writer's error are read
again once, before Gemini's reset; a card held only for its quoting is left alone."""

import json
from datetime import datetime

from bse_intel import sweep
from bse_intel.sinks.local import LocalSink
from bse_intel.timeutil import IST


def _card(sink, news_id, filed_at, grounding, held=1):
    sink._db.execute(
        "INSERT INTO cards (news_id, scrip_code, filing_date, filed_at, event_category, impact_level, headline, card_json, held) "
        "VALUES (?, '500001', ?, ?, 'RESULTS', 'MODERATE', 'h', ?, ?)",
        (news_id, filed_at[:10], filed_at, json.dumps({"grounding": grounding}), held))
    sink._db.execute("INSERT INTO filings (news_id, scrip_code, filed_at, filing_date, status, attempts) "
                     "VALUES (?, '500001', ?, ?, 'ANALYZED', 1)", (news_id, filed_at, filed_at[:10]))


def test_only_writer_errors_are_swept_once_in_the_slot(settings):
    sink = LocalSink(settings)
    _card(sink, "n-invented", "2026-10-21T10:00:00+05:30", {"ungrounded": ["7,993"]})
    _card(sink, "n-maths", "2026-10-20T10:00:00+05:30", {"math_mismatches": [{"x": 1}]})
    _card(sink, "n-quote", "2026-10-21T09:00:00+05:30", {"quotes_paraphrased": ["…"], "change_fixes": ["…"]})
    _card(sink, "n-old", "2026-10-01T10:00:00+05:30", {"ungrounded": ["1"]})              # out of the live window
    _card(sink, "n-published", "2026-10-21T08:00:00+05:30", {"ungrounded": ["1"]}, held=0)
    noon = datetime(2026, 10, 21, 11, 45, tzinfo=IST)
    assert not sweep.due(sink, datetime(2026, 10, 21, 13, 0, tzinfo=IST)) and sweep.due(sink, noon)
    got = sweep.run(sink, 7, 3, now=noon)
    assert got["filings"] == ["n-invented", "n-maths"]
    assert got["classes"] == {"figure not in the filing": 1, "arithmetic": 1}
    rows = {r[0]: r[1:] for r in sink._db.execute("SELECT news_id, status, attempts FROM filings")}
    assert rows["n-invented"] == ("PENDING", 0) and rows["n-quote"] == ("ANALYZED", 1)
    assert not sweep.due(sink, noon)                                                      # once a day
    assert sweep.run(sink, 7, 3, now=noon.replace(day=22))["filings"] == []                # each filing once
