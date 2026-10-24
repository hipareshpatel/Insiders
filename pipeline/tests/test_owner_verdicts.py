"""The owner's verdict outlives a re-run (O11): cards_upsert.sql reads card_verdicts, and cards_apply_verdicts.sql
applies standing verdicts to stored cards once. Run over the real migrations and statements (LocalSink)."""

from __future__ import annotations

import argparse
import json

from bse_intel.cli import cmd_apply_verdicts
from bse_intel.sinks.local import LocalSink

OWNER = "Held by the owner (Wrong): "


def _card(news_id: str, headline: str, held: int = 0, review: dict | None = None) -> dict:
    return {"news_id": news_id, "scrip_code": "999001", "symbol": "DEMO", "company_name": "Demo Ltd",
            "filing_date": "2026-10-19", "filed_at": "2026-10-19T10:00:00+05:30", "event_category": "RESULTS", "impact_level": "LOW",
            "headline": headline, "created_at": "2026-10-19T10:05:00Z", "held": held,
            "card": {"headline": headline, "review": review}}


def _verdict(sink: LocalSink, news_id: str, verdict: str, note: str, snapshot_headline: str, held: int = 0) -> None:
    sink._db.execute(
        "INSERT INTO card_verdicts (news_id, scrip_code, event_category, verdict, note, held, card_json_snapshot,"
        " created_at) VALUES (?, '999001', 'RESULTS', ?, ?, ?, ?, '2026-10-20T00:00:00Z')",
        [news_id, verdict, note, held, json.dumps({"headline": snapshot_headline})])
    sink._db.commit()


def _stored(sink: LocalSink, news_id: str) -> tuple[int, dict]:
    row = sink._db.execute("SELECT held, card_json FROM cards WHERE news_id = ?", [news_id]).fetchone()
    return row["held"], json.loads(row["card_json"])


def test_a_wrong_verdict_keeps_every_re_run_held_with_the_owners_note(settings):
    sink = LocalSink(settings)
    _verdict(sink, "a", "WRONG", "revenue is standalone, not consolidated\n", "Old headline")
    sink.execute("cards_upsert", [_card("a", "Old headline")])                      # a first write (insert)
    held, card = _stored(sink, "a")
    assert held == 1 and card["review"] == {"status": "HELD", "held": [OWNER + "revenue is standalone, not consolidated"]}

    # the re-run passes its checks and has its own review block; the owner's line joins the checks' own, once
    rerun = _card("a", "New headline", review={"status": "CORRECTED", "held": ["a figure not on the page"]})
    sink.execute("cards_upsert", [rerun])
    sink.execute("cards_upsert", [rerun])
    held, card = _stored(sink, "a")
    assert held == 1
    assert card["review"] == {"status": "CORRECTED",
                              "held": ["a figure not on the page", OWNER + "revenue is standalone, not consolidated"]}
    assert card["headline"] == "New headline"


def test_a_right_verdict_releases_only_the_card_the_owner_approved(settings):
    sink = LocalSink(settings)
    _verdict(sink, "b", "RIGHT", "", "Approved headline", held=1)
    sink.execute("cards_upsert", [_card("b", "Approved headline", held=1)])
    assert _stored(sink, "b")[0] == 0                                  # same card: the owner's approval stands
    sink.execute("cards_upsert", [_card("b", "A different card", held=1)])
    held, card = _stored(sink, "b")
    assert held == 1 and card["review"] is None                         # a different card: the checks decide
    sink.execute("cards_upsert", [_card("b", "A different card", held=0)])
    assert _stored(sink, "b")[0] == 0


def test_minor_and_no_verdict_leave_held_to_the_checks(settings):
    sink = LocalSink(settings)
    _verdict(sink, "c", "MINOR", "rounding", "H")
    sink.execute("cards_upsert", [_card("c", "H", held=1), _card("d", "H", held=1), _card("e", "H")])
    assert [_stored(sink, i)[0] for i in "cde"] == [1, 1, 0]
    assert _stored(sink, "c")[1]["review"] is None


def test_apply_verdicts_applies_standing_verdicts_once(settings, capsys):
    sink = LocalSink(settings)
    # cards stored before the verdicts acted on them (O11): a WRONG still public, a RIGHT still held, a RIGHT given
    # to an older version, a MINOR, and a card without a verdict
    sink.execute("cards_upsert", [_card("w", "W", review={"status": "UNRESOLVED", "issues": ["x"]}),
                                  _card("r", "R", held=1), _card("s", "Now different", held=1),
                                  _card("m", "M", held=1), _card("n", "N")])
    for news_id, verdict, headline in (("w", "WRONG", "W"), ("r", "RIGHT", "R"), ("s", "RIGHT", "Then"),
                                       ("m", "MINOR", "M")):
        _verdict(sink, news_id, verdict, "says FY25, the filing is FY26" if verdict == "WRONG" else "", headline)

    assert cmd_apply_verdicts(argparse.Namespace(), settings, sink) == 0
    assert json.loads(capsys.readouterr().out) == {"cards_written": 2}
    held, card = _stored(sink, "w")
    assert held == 1
    assert card["review"] == {"status": "UNRESOLVED", "issues": ["x"], "held": [OWNER + "says FY25, the filing is FY26"]}
    assert [_stored(sink, i)[0] for i in "rsmn"] == [0, 1, 1, 0]

    # idempotent: a second run writes nothing; a changed note is written once more
    assert cmd_apply_verdicts(argparse.Namespace(), settings, sink) == 0
    assert json.loads(capsys.readouterr().out) == {"cards_written": 0}
    sink._db.execute("UPDATE card_verdicts SET note = 'wrong year' WHERE news_id = 'w'")
    sink._db.commit()
    assert sink.execute("cards_apply_verdicts", ["WRONG", "RIGHT"]) == 1
    assert _stored(sink, "w")[1]["review"]["held"] == [OWNER + "wrong year"]


def test_a_card_held_by_apply_verdicts_leaves_the_homepage_snapshot_at_once(settings):
    """apply-verdicts (and release-pruned, refresh-card-blocks) changed stored cards without rebuilding the R2 snapshot,
    which a run rebuilt only when it analysed a filing: a card held here stayed on the homepage and Signals page."""
    from datetime import timedelta

    from bse_intel.pipeline import SNAPSHOT_KEY, publish_snapshot
    from bse_intel.timeutil import now_ist

    sink = LocalSink(settings)
    card = _card("s", "Demo Ltd wins a ₹120 Cr order")
    card["filed_at"] = (now_ist() - timedelta(hours=2)).isoformat(timespec="seconds")
    card["filing_date"] = card["filed_at"][:10]
    sink.execute("cards_upsert", [card])
    assert publish_snapshot(sink)
    shown = lambda: [c["news_id"] for c in json.loads(sink.get_object(SNAPSHOT_KEY))["feed"]["cards"]]  # noqa: E731
    assert shown() == ["s"]
    assert not publish_snapshot(sink, force=False)       # same day, nothing forced: left as it is
    _verdict(sink, "s", "WRONG", "the order is the subsidiary's", "Demo Ltd wins a ₹120 Cr order")
    cmd_apply_verdicts(argparse.Namespace(), settings, sink)
    assert shown() == []
