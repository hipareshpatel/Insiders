"""The shadow check of live results cards (pdf_shadow.py, TODO 116): synthetic PDFs, fake store and fetch, no network."""

from __future__ import annotations

import json
from datetime import datetime

from bse_intel import pdf_numbers_first as nf
from bse_intel import pdf_shadow as ps
from bse_intel.pdf_readers import Reading
from bse_intel.timeutil import IST
from test_pdf_numbers_first import crore, pl, statement

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=IST)


class Sink:
    def __init__(self, cards, objects=None):
        self.cards, self.objects, self.puts = cards, dict(objects or {}), 0

    def query(self, name, params):
        assert name == "export_cards"
        after, news, limit = params
        rows = [c for c in sorted(self.cards, key=lambda c: (c["filed_at"], c["news_id"]))
                if c["filed_at"] > after or (c["filed_at"] == after and c["news_id"] > news)]
        return rows[:limit]

    def get_object(self, key):
        return self.objects.get(key)

    def put_object(self, key, body, content_type="application/json"):
        self.puts += 1
        self.objects[key] = body


class Src:
    def __init__(self, pdfs):
        self.pdfs, self.asked = pdfs, []

    def payload(self, url):
        self.asked.append(url)
        data = self.pdfs.get(url)
        return (data, "") if data else (None, "NSE serves no file (404)")

    def release(self):
        pass


def card(news_id, revenue, pbt, pat, url="https://x/a.pdf", basis="STANDALONE", filed="2026-10-29T11:00:00+05:30", label=None):
    results = {"period": "Q2FY27", "revenue": {"value": revenue}, "pbt": {"value": pbt}, "pat": {"value": pat},
               "lines": [{"key": "pat", "label": label or "Net profit"}]}
    return {"news_id": news_id, "symbol": "ABC", "filed_at": filed, "event_category": "RESULTS", "held": 0, "pdf_url": url,
            "card_json": json.dumps({"results": results, "xbrl": {"basis": basis}})}


def pdf():
    rows, want = pl()
    return statement(rows), want


def test_the_verdict_rule():
    ok = Reading("r", status="ok", value=10.0, tol=0.005, page=1)
    assert ps.verdict(10.0, ok)[0] == "agrees"
    assert ps.verdict(10.005, ok)[0] == "agrees"          # inside the reader's half unit
    assert ps.verdict(10.1, ok)[0] == "disagrees"
    assert ps.verdict(10.5, Reading("r", status="ok", value=10.0, tol=0.005))[0] == "disagrees"
    assert ps.verdict(10.4, Reading("r", status="ok", value=10.0, tol=0.5))[0] == "agrees"   # a coarse PDF is allowed its own tolerance
    assert ps.verdict(10.4, Reading("r", status="none", note="no table"))[0] == "unknown"
    assert ps.verdict(10.4, Reading("r", status="conflict", note="tables differ"))[0] == "unknown"
    assert ps.verdict(1000.0, Reading("r", status="ok", value=1000.4, tol=0.005))[0] == "agrees"      # a card showing whole crores is rounded to one
    assert ps.verdict(1000.0, Reading("r", status="ok", value=1000.6, tol=0.005))[0] == "disagrees"


def test_a_card_the_pdf_contradicts_and_one_it_confirms():
    data, want = pdf()
    good, pbt, pat = crore(1000.00), crore(want["pbt"][0]), crore(want["pat"][0])
    sink = Sink([card("n1", good, pbt, pat), card("n2", good * 10, pbt, pat, url="https://x/b.pdf")])
    out = ps.run(None, sink, 3, src=Src({"https://x/a.pdf": data, "https://x/b.pdf": data}), now=NOW)
    by = {(r["card_id"], r["metric"]): r for r in out["rows"]}
    assert {by[("n1", m)]["verdict"] for m in ("revenue", "pbt", "pat")} == {"agrees"}
    assert by[("n2", "revenue")]["verdict"] == "disagrees"           # 10x: the unit slip
    assert by[("n2", "revenue")]["pdf_value"] == good and by[("n2", "pbt")]["verdict"] == "agrees"
    assert float(by[("n1", "revenue")]["pdf_seconds"]) >= 0 and by[("n1", "revenue")]["pdf_page"]
    assert sink.objects["meta/pdf-shadow/2026-10-29.csv"]            # saved to R2


def test_unknown_when_there_is_no_pdf_or_no_table():
    data, want = pdf()
    sink = Sink([card("n1", 10.0, 1.0, 1.0, url="https://x/gone.pdf"), card("n2", 10.0, 1.0, 1.0, url="https://x/c.pdf")])
    out = ps.run(None, sink, 3, src=Src({"https://x/c.pdf": b"%PDF-1.4 not a pdf"}), now=NOW)
    assert {r["verdict"] for r in out["rows"]} == {"unknown"}
    assert any("no PDF" in r["reason"] for r in out["rows"] if r["card_id"] == "n1")


def test_a_named_profit_line_that_differs_is_unknown_not_a_false_alarm():
    data, want = pdf()
    rows = ps.check_card(nf.analyse(data),
                         "Q2FY27", "STANDALONE", [("pat", crore(want["pat"][0]) + 5, "Net profit to shareholders")])
    assert rows[0]["verdict"] == "unknown" and "Net profit to shareholders" in rows[0]["reason"]


def test_continuation_skips_cards_already_done_and_other_cards_are_left_alone():
    data, want = pdf()
    held = card("h1", 10.0, 1.0, 1.0) | {"held": 1}
    other = card("o1", 10.0, 1.0, 1.0) | {"event_category": "ORDER"}
    old = card("old", 10.0, 1.0, 1.0, filed="2026-10-29T01:00:00+05:30")      # before the 3-hour window
    sink = Sink([card("n1", 10.0, 1.0, 1.0), card("n2", 10.0, 1.0, 1.0, url="https://x/b.pdf"), held, other, old])
    src = Src({"https://x/a.pdf": data, "https://x/b.pdf": data})
    first = ps.run(None, sink, 3, limit=1, src=src, now=NOW)
    assert first["cards_read"] == 1 and src.asked == ["https://x/a.pdf"]
    src2 = Src({"https://x/a.pdf": data, "https://x/b.pdf": data})
    second = ps.run(None, sink, 3, src=src2, now=NOW)                         # a later run: n1 is in the saved file
    assert src2.asked == ["https://x/b.pdf"] and second["skipped_done"] == 1
    assert {r["card_id"] for r in second["rows"]} == {"n1", "n2"}
    third = ps.run(None, sink, 3, src=Src({}), now=NOW)
    assert third["cards_read"] == 0 and len(third["rows"]) == len(second["rows"])


def test_a_card_filed_just_before_midnight_is_not_read_again_the_next_day():
    data, _ = pdf()
    sink = Sink([card("n1", 10.0, 1.0, 1.0, filed="2026-10-29T23:50:00+05:30")])
    ps.run(None, sink, 3, src=Src({"https://x/a.pdf": data}), now=datetime(2026, 10, 29, 23, 55, tzinfo=IST))
    again = Src({"https://x/a.pdf": data})
    ps.run(None, sink, 3, src=again, now=datetime(2026, 10, 30, 0, 41, tzinfo=IST))
    assert again.asked == []


def test_a_failed_download_is_not_a_finished_card():
    class Flaky(Src):
        def payload(self, url):
            return None, "download failed (timeout)"
    sink = Sink([card("n1", 10.0, 1.0, 1.0)])
    out = ps.run(None, sink, 3, src=Flaky({}), now=NOW)
    assert out["fetch_failed"] == 1 and out["rows"] == []


def test_figures_of_a_card():
    results = {"period": "Q2FY27", "revenue": {"value": 5.0}, "pbt": {"value": 1.0}, "lines": [{"key": "revenue", "label": "Total income"}]}
    period, basis, figs = ps.figures_of({"results": results})
    assert (period, basis) == ("Q2FY27", None) and [(m, v) for m, v, _ in figs] == [("total_income", 5.0), ("pbt", 1.0)]


def test_a_card_whose_figures_agree_on_different_bases_is_flagged(monkeypatch):
    # with no stored basis each figure may match the basis that fits it; one consolidated and one standalone is a mixed card
    def fake(tables, period, metric, basis):
        value = {"revenue": {"CONSOLIDATED": 100.0, "STANDALONE": 80.0}, "pat": {"CONSOLIDATED": 12.0, "STANDALONE": 9.0}}[metric][basis]
        return Reading("numfirst", status="ok", value=value, page=2)
    monkeypatch.setattr(ps, "_read", fake)
    rows = ps.check_card([], "Q2FY27", None, [("revenue", 100.0, "Revenue"), ("pat", 9.0, "Net profit")])
    assert all(r["verdict"] == "disagrees" and "mixed bases" in r["reason"] for r in rows)
    rows = ps.check_card([], "Q2FY27", None, [("revenue", 100.0, "Revenue"), ("pat", 12.0, "Net profit")])
    assert all(r["verdict"] == "agrees" for r in rows)
