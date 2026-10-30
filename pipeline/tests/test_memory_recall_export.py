"""Memory recall audit export (TODO row 82): read only, one folder a sampled call filing."""
from __future__ import annotations

import gzip
import json
from datetime import date

from bse_intel import memory_recall_export as mre
from bse_intel.cli import main
from bse_intel.pipeline import text_key

TODAY = date(2026, 10, 26)


def _entry(pages, ocr=None, has_image=None):
    return {"v": 1, "digital": pages, "has_image": has_image or [False] * len(pages), "ocr": ocr or {}}


def _body(entry) -> bytes:
    return gzip.compress(json.dumps(entry).encode())


class FakeSink:
    """The sink calls the export makes, and nothing else: any write fails the test."""

    def __init__(self, cards, texts, dossiers, caps):
        self.cards, self.texts, self.dossiers, self.caps = cards, texts, dossiers, caps
        self.calls = []

    def query(self, name, params):
        self.calls.append(name)
        assert name == "export_cards"
        after = (params[0], params[1])
        rows = [c for c in self.cards if (c["filed_at"], c["news_id"]) > after]
        return sorted(rows, key=lambda c: (c["filed_at"], c["news_id"]))[:params[2]]

    def get_object(self, key):
        return self.texts.get(key)

    def get_dossier(self, scrip):
        return self.dossiers.get(scrip)

    def company(self, scrip):
        return {"market_cap_cr": self.caps.get(scrip)}

    def __getattr__(self, name):   # put_object, put_dossier, execute, kv_set ...
        raise AssertionError(f"read-only export called {name}")


def _card(nid, scrip, headline, sector="IT", filed="2026-10-20T10:00:00", event=mre.EVENT, held=0):
    return {"news_id": nid, "scrip_code": scrip, "symbol": f"S{scrip}", "company_name": f"Company {scrip}", "filed_at": filed,
            "sector": sector, "event_category": event, "headline": headline, "pdf_url": f"https://x/{nid}.pdf", "held": held,
            "card_json": json.dumps({"headline": headline, "event_type": event})}


def _world(n=12):
    cards, texts, dossiers, caps = [], {}, {}, {}
    for i in range(n):
        nid, scrip = f"n{i:02d}", str(100 + i)
        deck = i % 2
        cards.append(_card(nid, scrip, "Investor presentation Q2" if deck else "Earnings call transcript Q2",
                           sector=["IT", "Pharma", "Auto"][i % 3]))
        # a transcript has its moderator in the text (an invitation does not: test_a_headline_that_says_call_over_an_invitation)
        texts[text_key(nid)] = _body(_entry([f"page one of {nid}: moderator, moderator, moderator, participant", "page two"]))
        caps[scrip] = [30000, 8000, 900][i % 3]
        dossiers[scrip] = {"guidance": [{"id": "g", "source_news_id": nid, "status": "OPEN", "status_history": []}]}
    return cards, texts, dossiers, caps


def test_attribute_finds_every_section_that_names_the_filing():
    dossier = {
        "financial_metrics": [
            {"metric": "revenue", "period": "Q1FY27", "value": 1, "source_news_id": "other",
             "sources": [{"news_id": "other"}, {"news_id": "F1", "value": 1}]},
            {"metric": "pat", "period": "Q1FY27", "source_news_id": "other"}],
        "guidance": [{"id": "g1", "source_news_id": "other", "status_history": [{"status": "MET", "source_news_id": "F1"}]},
                     {"id": "g2", "source_news_id": "other", "status_history": []}],
        "watchlist": [{"id": "w1", "source_news_id": "F1"}],
        "timeline": [{"id": "t1", "news_id": "F1"}, {"id": "t2", "news_id": "other"}],
        "deals": [{"id": "d1", "source_news_id": "other", "history": [{"source_news_id": "other"}, {"source_news_id": "F1"}]}],
        "predictions": [{"id": "p1", "source_news_id": "other", "resolved_by": "F1"}],
        "call_points": [{"news_id": "F1", "text": "t"}],
        "business_summary": {"text": "s", "source_news_id": "F1"},
        "governance": {"auditor": {"name": "A"}, "auditor_history": [{"name": "A", "source_news_id": "F1"}],
                       "quarters": [{"source": "F1"}]},
        "identity": {"former_names": ["Old Ltd"], "entities": [{"name": "E", "source_news_id": "other"}]},
        "screener_fill": [{"metric": "m", "source": "screener:S:Q1FY27:C"}],
        "segment_mix": [], "updated_at": "2026-10-20",
    }
    got = mre.attribute(dossier, "F1")
    s = got["sections"]
    assert [e["metric"] for e in s["financial_metrics"]] == ["revenue"]
    assert [e["id"] for e in s["guidance"]] == ["g1"]
    assert [e["id"] for e in s["watchlist"]] == ["w1"] and [e["id"] for e in s["timeline"]] == ["t1"]
    assert [e["id"] for e in s["deals"]] == ["d1"] and [e["id"] for e in s["predictions"]] == ["p1"]
    assert s["call_points"] and s["business_summary"][0]["text"] == "s"
    assert s["governance.auditor_history"] and s["governance.quarters"]
    assert "identity.entities" not in s and "segment_mix" not in s
    assert got["entries"] == sum(len(v) for v in s.values())
    # the plain-string list carries no filing id, and the empty list is not a section with entries
    assert "identity.former_names" in got["sections_without_filing_id"]
    assert "segment_mix" not in got["sections_without_filing_id"]
    assert attribute_none() == {"news_id": "F1", "entries": 0, "sections": {}, "sections_without_filing_id": []}


def attribute_none():
    return mre.attribute(None, "F1")


def test_page_markers_and_how_each_page_was_read():
    entry = _entry(["digital page", "x", "garbled ###"], ocr={"1": "text read by OCR"},
                   has_image=[False, True, False])
    text, pages = mre.render_text(entry)
    assert "===== PAGE 1 of 3 [text] =====\ndigital page" in text
    assert "===== PAGE 2 of 3 [ocr] =====\ntext read by OCR" in text
    assert [p["source"] for p in pages] == ["text", "ocr", "text"]


def test_a_scanned_page_nobody_read_is_named_not_hidden():
    text, pages = mre.render_text(_entry(["ok text of the page", ""], has_image=[False, True]))
    assert pages[1]["source"].startswith("text (scanned")
    assert "PAGE 2 of 2 [text (scanned or garbled, not OCR'd)]" in text


def test_kind_of_headline_and_text_fallback():
    assert mre.kind_of("Transcript of earnings call") == "transcript"
    assert mre.kind_of("Investor Presentation Q2") == "deck"
    assert mre.kind_of("Transcript and presentation") == "unknown"
    moderator = _entry(["moderator: welcome. " * 3 + " participant"])
    assert mre.kind_from_text(moderator, "Outcome") == "transcript"
    assert mre.kind_from_text(_entry(["plain slides"]), "Outcome") == "deck"


def test_sample_is_seeded_balanced_and_spread(tmp_path):
    cards, texts, dossiers, caps = _world(12)
    sink = FakeSink(cards, texts, dossiers, caps)
    a = mre.export(sink, tmp_path / "a", limit=6, seed=7, today=TODAY)
    b = mre.export(sink, tmp_path / "b", limit=6, seed=7, today=TODAY)
    c = mre.export(sink, tmp_path / "c", limit=6, seed=8, today=TODAY)
    ids = lambda ix: [s["news_id"] for s in ix["sample"]]
    assert ids(a) == ids(b) and ids(a) != ids(c)
    assert a["by_kind"] == {"transcript": 3, "deck": 3}
    assert a["sectors"] == 3 and {s["size_band"] for s in a["sample"]} == {"large", "mid", "small"}
    assert a["candidates"] == 12 and a["sampled"] == 6


def test_filters_by_event_held_date_and_stored_text(tmp_path):
    cards, texts, dossiers, caps = _world(4)
    cards += [_card("res", "200", "Results", event="RESULTS"),
              _card("held", "201", "Earnings call transcript", held=1),
              _card("old", "202", "Earnings call transcript", filed="2026-08-01T10:00:00"),
              _card("notext", "203", "Earnings call transcript")]
    for nid in ("res", "held", "old"):
        texts[text_key(nid)] = _body(_entry(["text"]))
    index = mre.export(FakeSink(cards, texts, dossiers, caps), tmp_path, limit=20, today=TODAY)
    assert sorted(s["news_id"] for s in index["sample"]) == ["n00", "n01", "n02", "n03"]


def test_a_company_is_sampled_once_while_others_are_left(tmp_path):
    cards, texts, dossiers, caps = _world(4)
    for i in range(3):
        cards.append(_card(f"dup{i}", "100", "Investor presentation"))
        texts[text_key(f"dup{i}")] = _body(_entry(["more"]))
    index = mre.export(FakeSink(cards, texts, dossiers, caps), tmp_path, limit=4, today=TODAY)
    assert len({s["symbol"] for s in index["sample"]}) == 4


def test_folder_files_memory_and_no_writes(tmp_path):
    cards, texts, dossiers, caps = _world(2)
    sink = FakeSink(cards, texts, dossiers, caps)
    index = mre.export(sink, tmp_path, limit=2, today=TODAY)
    assert sink.calls and set(sink.calls) == {"export_cards"}   # FakeSink raises on any write call
    assert (tmp_path / "README.md").read_text(encoding="utf-8").startswith("# Memory recall audit")
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))["sampled"] == 2
    nid = index["sample"][0]["news_id"]
    folder = tmp_path / nid
    assert sorted(p.name for p in folder.iterdir()) == ["card.json", "memory.json", "meta.json", "text.txt"]
    assert f"page one of {nid}" in (folder / "text.txt").read_text(encoding="utf-8")
    memory = json.loads((folder / "memory.json").read_text(encoding="utf-8"))
    assert memory["entries"] == 1 and memory["sections"]["guidance"][0]["source_news_id"] == nid
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["pdf_url"] == f"https://x/{nid}.pdf" and meta["event_type"] == mre.EVENT and meta["pages_text"] == 2
    assert json.loads((folder / "card.json").read_text(encoding="utf-8"))["event_type"] == mre.EVENT
    # the reviewer's text carries nothing of memory
    assert "guidance" not in (folder / "text.txt").read_text(encoding="utf-8")


def test_command_runs_and_exits_1_with_nothing_to_sample(tmp_path, monkeypatch, capsys):
    cards, texts, dossiers, caps = _world(3)
    monkeypatch.setattr("bse_intel.cli.make_sink", lambda settings: FakeSink(cards, texts, dossiers, caps), raising=False)
    monkeypatch.setattr(mre, "today_ist", lambda: TODAY)
    assert main(["memory-recall-export", "--out", str(tmp_path / "ok"), "--limit", "2"]) == 0
    assert "memory recall export: 2 of 3" in capsys.readouterr().out
    monkeypatch.setattr("bse_intel.cli.make_sink", lambda settings: FakeSink([], {}, {}, {}), raising=False)
    assert main(["memory-recall-export", "--out", str(tmp_path / "none")]) == 1


def test_a_headline_that_says_call_over_an_invitation_is_not_sampled_as_a_transcript():
    # Syrma SGS nse-106828335 (26 Oct 2026): "to discuss Q2FY27 results on November 2 earnings call", two pages of dial-in details
    headline = "Syrma SGS: to discuss Q2FY27 results on November 2 earnings call"
    notice = _entry(["Intimation of earnings call. Syrma SGS will hold a call on November 2, 2026 at 4 pm; dial-in 91 22 6280 1000.",
                     "Registration link and the safe harbour statement."])
    assert mre.kind_of(headline) == "transcript"
    assert mre.kind_from_text(notice, headline) == "invitation"
    assert mre.kind_from_text(_entry(["Investor presentation Q2FY27 earnings presentation", "x"]), headline) == "deck"
    real = _entry(["Moderator: welcome. " * 3 + "participant", "x"])   # a call with its moderator is one, however short
    assert mre.kind_from_text(real, headline) == "transcript"
    # a long document with the same headline is a transcript even when no moderator is named in it
    assert mre.kind_from_text(_entry(["words " * 400] * 4), headline) == "transcript"
    # and the sample passes the invitation over for another filing
    cards = [_card("inv", "300", headline), _card("real", "301", "Earnings call transcript Q2")]
    texts = {"inv": notice, "real": real}
    picked = mre.choose(cards, lambda nid: texts[nid], 5, seed=1)
    assert [r["news_id"] for r in picked] == ["real"]


def test_ids_export_exactly_those_filings(tmp_path):
    cards, texts, dossiers, caps = _world(12)
    sink = FakeSink(cards, texts, dossiers, caps)
    want = sorted(c["news_id"] for c in cards)[:3]
    ix = mre.export(sink, tmp_path / "ids", limit=1, today=TODAY, ids=want)
    assert sorted(s["news_id"] for s in ix["sample"]) == want and ix["missing"] == []
    assert mre.export(sink, tmp_path / "gone", today=TODAY, ids=[want[0], "nse-nothere"])["missing"] == ["nse-nothere"]
