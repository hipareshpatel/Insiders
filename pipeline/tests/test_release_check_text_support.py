"""scripts/release_check.py, the text_support check (CARD_TEXT_SUPPORT, TODO 142): lists what the switch would drop from a
stored card, leaves the in-sample cards out, and keeps the blind sample free of hints. Offline, a made-up card, text, memory."""

from __future__ import annotations

import gzip
import json
import os
import sys

from test_release_check import _script

FILED = "2026-10-20T10:00:00+05:30"
TEXT = ("Board meeting outcome. The company reported revenue growth for the quarter. "
        "The Board approved a capital expenditure plan for the Pune plant. Nothing else.")


def _card():
    return {"event_type": "OTHER", "impact_level": "LOW", "headline": "Acme plans capex", "takeaway": "t",
            "what_happened": [{"text": "Board approved capex for the Pune plant", "quote": "approved a capital expenditure plan"}],
            "track_next": {"risks": ["Dalmia Bharat and Merino wool demand could pressure the Pune plant"]},
            "core_catalyst": "Capex for the Pune plant"}


def _row(news_id, card):
    return {"news_id": news_id, "scrip_code": "1", "symbol": "ACME", "company_name": "Acme", "filed_at": FILED,
            "pdf_url": "https://example.test/f.pdf", "headline": "Acme plans capex", "held": 0, "card_json": json.dumps(card)}


def test_a_risk_naming_things_no_source_prints_is_listed_with_its_note_and_the_filing_window():
    rc = _script()
    rec = rc.check_text_support(_card(), {}, _row("nse-1", _card()), TEXT)
    (drop,) = rec["drops"]
    assert drop["field"] == "track_next" and "Merino" in drop["item"] and "Dalmia" in "; ".join(drop["note"])
    assert drop["company"] == "ACME" and "Pune plant" in drop["filing_window"]
    assert rec["diff"]["removed"] == ["track_next: " + drop["item"]] and rec["info"]["items_dropped"] == 1


def test_the_run_leaves_the_in_sample_cards_out_and_counts_them(tmp_path, monkeypatch):
    rc = _script()
    in_sample = rc.IN_SAMPLE_MARKS[0][0]
    (tmp_path / "texts").mkdir()
    cache = {"v": 1, "digital": [TEXT], "has_image": [False]}
    for nid in (in_sample, "nse-1", "nse-2"):
        (tmp_path / "texts" / f"{nid}.json.gz").write_bytes(gzip.compress(json.dumps(cache).encode()))
    (tmp_path / "cards.json").write_text(json.dumps([_row(n, _card()) for n in (in_sample, "nse-1", "nse-2")]))
    before = dict(os.environ)
    monkeypatch.setattr(sys, "argv", ["release_check.py", str(tmp_path / "out"), "--cards", str(tmp_path / "cards.json"),
                                      "--texts", str(tmp_path / "texts"), "--only", "text_support"])
    assert rc.main() == 0
    assert dict(os.environ) == before
    out = tmp_path / "out"
    total = json.loads((out / "release-check.json").read_text(encoding="utf-8"))["text_support"]
    assert total["cards_checked"] == 2 and total["in_sample_cards_excluded"] == 1 and total["cards_changed"] == 2
    full = json.loads((out / "text_support.json").read_text(encoding="utf-8"))
    assert {d["news_id"] for d in full["dropped"]} == {"nse-1", "nse-2"}
    assert "## track_next (2)" in (out / "text_support.md").read_text(encoding="utf-8")
    blind = json.loads((out / "text_support-blind.json").read_text(encoding="utf-8"))
    assert len(blind) == 2 and all(set(b) == {"id", "news_id", "company", "headline", "pdf_url", "item"} for b in blind)
    md = (out / "text_support-blind.md").read_text(encoding="utf-8")
    assert "not supported" not in md and "Dalmia" in md   # the item, no note
    key = json.loads((out / "text_support-key.json").read_text(encoding="utf-8"))
    assert key["t01"]["field"] == "track_next"
    for b in blind:   # the judges read each sampled card's filing text and memory, not the exchange
        assert (out / "text_support-sources" / f"{b['news_id']}.filing.txt").read_text(encoding="utf-8")
        assert (out / "text_support-sources" / f"{b['news_id']}.memory.json").exists()
