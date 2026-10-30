"""The shadow check of live results cards (pdf_shadow.py, TODO 121): synthetic PDFs, fake store and fetch, no network."""

from __future__ import annotations

import json

import pytest
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
    assert all(r["verdict"] == "mixed_bases" for r in rows)
    rows = ps.check_card([], "Q2FY27", None, [("revenue", 100.0, "Revenue"), ("pat", 12.0, "Net profit")])
    assert all(r["verdict"] == "agrees" for r in rows)


def test_an_unreadable_saved_log_stops_the_run_and_never_overwrites_it():
    # review of 0739dcf: a timeout reading the day's file was taken for "nothing saved" and the run then rewrote the file
    data, _ = pdf()

    class Flaky(Sink):
        def get_object(self, key):
            raise TimeoutError("R2 read timed out")
    sink = Flaky([card("n1", 10.0, 1.0, 1.0)])
    with pytest.raises(TimeoutError):
        ps.run(None, sink, 3, src=Src({"https://x/a.pdf": data}), now=NOW)
    assert sink.puts == 0


def test_a_stored_basis_the_figure_does_not_match_is_a_basis_mismatch_not_a_disagreement(monkeypatch):
    def fake(tables, period, metric, basis):
        return Reading("numfirst", status="ok", value={"CONSOLIDATED": 100.0, "STANDALONE": 80.0}[basis], page=2)
    monkeypatch.setattr(ps, "_read", fake)
    rows = ps.check_card([], "Q2FY27", "STANDALONE", [("revenue", 100.0, "Revenue")])
    assert rows[0]["verdict"] == "basis_mismatch"
    rows = ps.check_card([], "Q2FY27", "STANDALONE", [("revenue", 90.0, "Revenue")])
    assert rows[0]["verdict"] == "disagrees"


def test_a_consolidated_profit_that_differs_is_unclear_not_a_false_alarm(monkeypatch):
    # a card's consolidated profit may be the owners' share; the reader gives the total profit
    monkeypatch.setattr(ps, "_read", lambda tables, period, metric, basis: Reading("numfirst", status="ok", value=50.0, page=2))
    assert ps.check_card([], "Q2FY27", "CONSOLIDATED", [("pat", 45.0, "Net profit")])[0]["verdict"] == "unclear"
    assert ps.check_card([], "Q2FY27", "STANDALONE", [("pat", 45.0, "Net profit")])[0]["verdict"] == "disagrees"


def test_the_summary_separates_held_out_companies_and_counts_the_runner_minutes(tmp_path):
    # the lead's ask (29 Oct): held-out companies' verdicts apart, WRONG counted, and the runner minutes a day
    (tmp_path / "normalpdf").mkdir()
    (tmp_path / "hardpdf").mkdir()
    (tmp_path / "normalpdf" / "key.csv").write_text("symbol,metric\nTUNED,pat\nHELD,pat\n")
    (tmp_path / "hardpdf" / "key.csv").write_text("symbol,metric\n")
    (tmp_path / "heldout.csv").write_text("key,symbol,page_type\nnormal,HELD,x\n")
    tuned = ps.tuned_symbols(tmp_path)
    assert tuned == {"TUNED"}
    rows = [{"card_id": "a", "symbol": "TUNED", "verdict": "agrees", "pdf_seconds": "30"},
            {"card_id": "a", "symbol": "TUNED", "verdict": "disagrees", "pdf_seconds": "30"},
            {"card_id": "b", "symbol": "NEWCO", "verdict": "agrees", "pdf_seconds": "90"},
            {"card_id": "c", "symbol": "HELD", "verdict": "unknown", "pdf_seconds": "60"}]
    got = ps.summary(rows, tuned)
    assert got["tuned"] == {"agrees": 1, "disagrees": 1, "cards": 1}
    assert got["held_out"] == {"agrees": 1, "unknown": 1, "cards": 2}
    assert got["pdf_minutes"] == 3.0


# --- PBT like with like: the card's definition against the PDF's printed line ------------------------------------------------

SHARE = [50.0, 30.0, 20.0, 80.0]              # lakh: the associates' share, printed above the PBT line


def associates_pdf(share_lakh=None):
    """A consolidated statement printing the associates' share above "Profit before tax" (ATUL Q2FY27's layout): the printed
    PBT holds the share. Returns (pdf, printed PBT in crore, the filed PBT before the share in crore, the share in crore)."""
    share = share_lakh or SHARE
    rows, want = pl(exceptional=[-v for v in share])
    rows[9] = (["Share of net profit of associates and joint ventures"], share)
    printed = crore(want["pbt"][0])
    return statement(rows, title="Statement of Consolidated Financial Results"), printed, round(printed - crore(share[0]), 2), crore(share[0])


def memory(filed, share, screener, basis="CONSOLIDATED", family="corporate"):
    rows = {"Profit before tax": screener, "Associates' share": share}
    if screener != filed:
        rows["PBT as filed"] = filed
    return {"statements": [{"period": "Q2FY27", "basis": basis, "table": "quarters", "family": family, "rows": rows}]}


def test_a_card_pbt_with_the_associates_share_agrees_with_a_pdf_printing_pbt_after_the_share():
    data, printed, filed, share = associates_pdf()
    tables = nf.analyse(data)
    assert nf.reading_from_tables(tables, "Q2FY27", "pbt", "CONSOLIDATED").value == pytest.approx(printed)
    screener = round(filed + share, 2)               # screener's PBT: the filed PBT + the share (no other parts)
    mem = memory(filed, share, screener)
    # the card on screener's definition, and today's card on the file's PBT before the share (M&M Q1FY27 7,260.60 / 7,628.09)
    for value in (screener, filed):
        row = ps.check_card(tables, "Q2FY27", "CONSOLIDATED", [("pbt", value, "")], dossier=mem)[0]
        assert row["verdict"] == "agrees", row
        assert row["pdf_value"] == pytest.approx(printed)
    # end to end: the run reads the company's memory from the store by the card's scrip code
    class MemorySink(Sink):
        def get_dossier(self, scrip):
            assert scrip == "500001"
            return mem
    c = card("n1", 10.0, filed, 1.0, basis="CONSOLIDATED")
    c["scrip_code"] = "500001"
    out = ps.run(None, MemorySink([c]), 3, src=Src({"https://x/a.pdf": data}), now=NOW)
    assert {r["verdict"] for r in out["rows"] if r["metric"] == "pbt"} == {"agrees"}


def test_screener_pbt_with_discontinued_profit_agrees_with_the_printed_continuing_pbt():
    # screener has no discontinued line: its PBT adds the discontinued operations' profit after tax (HUL FY26 13,812 + 4,407),
    # which the statement prints below the continuing PBT
    data, printed, filed, share = associates_pdf()
    tables = nf.analyse(data)
    discontinued = 12.34
    screener = round(filed + share + discontinued, 2)
    mem = memory(filed, share, screener)
    row = ps.check_card(tables, "Q2FY27", "CONSOLIDATED", [("pbt", screener, "")], dossier=mem)[0]
    assert row["verdict"] == "agrees" and "screener" in row["reason"], row
    # the same company with no associates: the printed line before any share, screener's PBT = it + the discontinued profit
    plain, want = pdf()
    pbt = crore(want["pbt"][0])
    mem = memory(pbt, 0.0, round(pbt + discontinued, 2), basis="STANDALONE")
    row = ps.check_card(nf.analyse(plain), "Q2FY27", "STANDALONE", [("pbt", round(pbt + discontinued, 2), "")], dossier=mem)[0]
    assert row["verdict"] == "agrees", row


def test_a_pbt_off_the_printed_line_with_no_parts_in_memory_is_unknown():
    data, printed, filed, share = associates_pdf()
    tables = nf.analyse(data)
    for mem in (None, {"statements": []}, memory(filed, share, filed + share, basis="STANDALONE")):   # none, empty, other basis
        row = ps.check_card(tables, "Q2FY27", "CONSOLIDATED", [("pbt", filed, "")], dossier=mem)[0]
        assert row["verdict"] == "unknown" and "the gap is the associates' share printed on p1" in row["reason"], row
    # the printed line itself needs no parts
    assert ps.check_card(tables, "Q2FY27", "CONSOLIDATED", [("pbt", printed, "")])[0]["verdict"] == "agrees"


def test_a_real_pbt_disagreement_still_disagrees():
    data, printed, filed, share = associates_pdf()
    tables = nf.analyse(data)
    mem = memory(filed, share, round(filed + share + 3.0, 2))
    row = ps.check_card(tables, "Q2FY27", "CONSOLIDATED", [("pbt", round(printed + 50.0, 2), "")], dossier=mem)[0]
    assert row["verdict"] == "disagrees" and "none of memory's PBT values" in row["reason"], row
    # a company with no parts to add: a gap is a disagreement, as before
    plain, want = pdf()
    pbt = crore(want["pbt"][0])
    row = ps.check_card(nf.analyse(plain), "Q2FY27", "STANDALONE", [("pbt", pbt + 5, "")], dossier=memory(pbt, 0.0, pbt, basis="STANDALONE"))[0]
    assert row["verdict"] == "disagrees", row
    # revenue and profit are not touched by the PBT parts
    rev = ps.check_card(nf.analyse(plain), "Q2FY27", "STANDALONE", [("revenue", 1.0, "")], dossier=None)[0]
    assert rev["verdict"] == "disagrees"


# blind review of 868980b: no free shifts, memory's own values as the anchor, no blanket "unknown", one memory read a company


def fixed_pdf(values):
    """``_read`` stand-in: the printed PBT by basis."""
    return lambda tables, period, metric, basis: Reading("numfirst", status="ok", value=values[basis], page=2, label="PBT")


def test_with_no_memory_values_a_slip_or_a_flipped_sign_still_disagrees(monkeypatch):
    monkeypatch.setattr(ps, "_read", fixed_pdf({"CONSOLIDATED": 100.0, "STANDALONE": 100.0}))
    # x10, x100, x0.1, a flipped sign, wildly different, and ordinary errors within a quarter of the figure (re-review of ecb6a79)
    for card_value in (1000.0, 10000.0, 10.0, -100.0, 200.0, 90.0, 80.0, 125.0, 75.0, 85.0):
        row = ps.check_card([], "Q2FY27", "CONSOLIDATED", [("pbt", card_value, "")], dossier=None)[0]
        assert row["verdict"] == "disagrees", (card_value, row)


def test_with_no_memory_values_the_other_basis_pbt_is_a_basis_mismatch(monkeypatch):
    monkeypatch.setattr(ps, "_read", fixed_pdf({"CONSOLIDATED": 100.0, "STANDALONE": 90.0}))
    row = ps.check_card([], "Q2FY27", "STANDALONE", [("pbt", 100.0, "")], dossier=None)[0]
    assert row["verdict"] == "basis_mismatch", row


def test_a_sign_error_on_the_share_disagrees(monkeypatch):
    # filed 100, share 30, the PDF prints 100 (before the share): a card of 70 took the share off instead of adding it
    monkeypatch.setattr(ps, "_read", fixed_pdf({"CONSOLIDATED": 100.0, "STANDALONE": 100.0}))
    mem = memory(100.0, 30.0, 130.0)
    row = ps.check_card([], "Q2FY27", "CONSOLIDATED", [("pbt", 70.0, "")], dossier=mem)[0]
    assert row["verdict"] == "disagrees", row
    for good in (130.0, 100.0):                                          # screener's PBT, the filed PBT
        assert ps.check_card([], "Q2FY27", "CONSOLIDATED", [("pbt", good, "")], dossier=mem)[0]["verdict"] == "agrees"


def test_an_associates_loss_counted_twice_disagrees(monkeypatch):
    # share -20, filed 100, the PDF prints 80 (after the share): a card of 60 took the loss twice
    monkeypatch.setattr(ps, "_read", fixed_pdf({"CONSOLIDATED": 80.0, "STANDALONE": 80.0}))
    mem = memory(100.0, -20.0, 80.0)
    assert ps.check_card([], "Q2FY27", "CONSOLIDATED", [("pbt", 60.0, "")], dossier=mem)[0]["verdict"] == "disagrees"
    row = ps.check_card([], "Q2FY27", "CONSOLIDATED", [("pbt", 100.0, "")], dossier=mem)[0]
    assert row["verdict"] == "agrees" and "the filed PBT" in row["reason"], row


def test_a_pdf_line_that_is_none_of_memorys_values_disagrees(monkeypatch):
    # the card is the filed PBT, but the PDF prints a figure memory does not know: no agreement on the card's side alone
    monkeypatch.setattr(ps, "_read", fixed_pdf({"CONSOLIDATED": 115.0, "STANDALONE": 115.0}))
    row = ps.check_card([], "Q2FY27", "CONSOLIDATED", [("pbt", 100.0, "")], dossier=memory(100.0, 30.0, 130.0))[0]
    assert row["verdict"] == "disagrees", row


def test_memory_is_read_only_for_a_pbt_that_needs_it_and_once_a_company(monkeypatch):
    monkeypatch.setattr(ps, "_read", fixed_pdf({"CONSOLIDATED": 130.0, "STANDALONE": 130.0}))

    class Counting(Sink):
        reads = 0

        def get_dossier(self, scrip):
            Counting.reads += 1
            raise RuntimeError("D1 answered 503")                      # a failed read is cached too

    cards = []
    for i, pbt in enumerate((100.0, 100.0, 130.0)):
        c = card(f"n{i}", 10.0, pbt, 1.0, url=f"https://x/{i}.pdf", basis="CONSOLIDATED")
        c["scrip_code"] = "500001"
        cards.append(c)
    sink = Counting(cards)
    ps.run(None, sink, 3, src=Src({f"https://x/{i}.pdf": b"x" for i in range(3)}), analyse=lambda data: [], now=NOW)
    assert Counting.reads == 1
    Counting.reads = 0
    ps.run(None, Counting([cards[2]]), 3, src=Src({"https://x/2.pdf": b"x"}), analyse=lambda data: [],
           now=datetime(2026, 10, 31, 12, 0, tzinfo=IST))
    assert Counting.reads == 0                                          # the PBT agrees plainly: memory is never read


# re-review of ecb6a79: with no memory values, "unknown" only for a gap that is exactly the share the same table prints


def test_no_memory_values_and_no_share_row_a_ten_percent_gap_disagrees():
    plain, want = pdf()
    printed = crore(want["pbt"][0])
    row = ps.check_card(nf.analyse(plain), "Q2FY27", "STANDALONE", [("pbt", round(printed * 0.9, 2), "")], dossier=None)[0]
    assert row["verdict"] == "disagrees", row


def test_no_memory_values_a_gap_that_is_the_printed_share_is_unknown():
    data, printed, filed, share = associates_pdf()
    assert share == pytest.approx(0.5)
    tables = nf.analyse(data)
    row = ps.check_card(tables, "Q2FY27", "CONSOLIDATED", [("pbt", filed, "")], dossier=None)[0]
    assert row["verdict"] == "unknown" and "the gap is the associates' share printed on p1 (0.5 Cr)" in row["reason"], row
    assert ps.printed_share(tables, "Q2FY27", "CONSOLIDATED", 1)[0] == pytest.approx(0.5)


def test_no_memory_values_a_gap_that_is_not_the_printed_share_disagrees():
    # the table prints a share of 0.35 Cr; the card is 0.5 Cr off: the gap is something else
    data, printed, filed, share = associates_pdf([35.0, 21.0, 14.0, 56.0])
    row = ps.check_card(nf.analyse(data), "Q2FY27", "CONSOLIDATED", [("pbt", round(printed - 0.5, 2), "")], dossier=None)[0]
    assert row["verdict"] == "disagrees", row


def test_no_memory_values_a_loss_share_gap_is_unknown_and_its_double_disagrees():
    data, printed, filed, share = associates_pdf([-50.0, -30.0, -20.0, -80.0])
    assert share == pytest.approx(-0.5) and filed > printed
    tables = nf.analyse(data)
    row = ps.check_card(tables, "Q2FY27", "CONSOLIDATED", [("pbt", filed, "")], dossier=None)[0]
    assert row["verdict"] == "unknown" and "-0.5 Cr" in row["reason"], row
    row = ps.check_card(tables, "Q2FY27", "CONSOLIDATED", [("pbt", round(printed - 0.5, 2), "")], dossier=None)[0]
    assert row["verdict"] == "disagrees", row        # the loss counted twice: a gap of the share's size on the wrong side
    row = ps.check_card(tables, "Q2FY27", "CONSOLIDATED", [("pbt", round(printed + 1.0, 2), "")], dossier=None)[0]
    assert row["verdict"] == "disagrees", row
