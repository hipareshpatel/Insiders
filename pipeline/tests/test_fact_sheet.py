"""CARD_FACT_SHEET (default off; owner, 30 Oct 2026, TODO 131 and 134): a results card whose results figures come from memory's
statements by screener's rules. Off, or with no sheet, the card is what it was."""
import json
from datetime import timedelta

import pytest

from test_pipeline import PASS2, _filing, _pdf, build
from test_xbrl import results_xml

from bse_intel import fact_sheet as fs
from bse_intel.bse import XbrlLink
from bse_intel.models import Pass2Output
from bse_intel.timeutil import now_ist


def _entry(period, rows, basis="CONSOLIDATED", family="corporate", by="file"):
    return {"period": period, "basis": basis, "table": "quarters", "family": family, "rows": rows, "source_news_id": f"n-{period}",
            "lab": {"by": by}}


def _rows(sales, op, pbt, net, owners=None, opm=None):
    out = {"Sales": sales, "Operating Profit": op, "Profit before tax": pbt, "Net Profit": net,
           "OPM %": opm if opm is not None else round(op / sales * 100, 2), "Tax %": 25.0}
    if owners is not None:
        out["Net Profit (owners)"] = owners
    return out


def _memory():
    return {"statements": [
        _entry("Q2FY27", _rows(1200.0, 240.0, 200.0, 150.0, owners=148.0)),
        _entry("Q2FY26", _rows(1000.0, 200.0, 160.0, 120.0, owners=118.4)),
        _entry("Q1FY27", _rows(1100.0, 200.0, 150.0, 100.0, owners=98.67)),
        _entry("Q2FY27", _rows(5.0, 1.0, 1.0, 1.0), basis="STANDALONE"),
    ]}


def test_the_sheet_is_the_files_rows_with_changes_worked_out_by_code():
    sheet = fs.fact_sheet(_memory(), "Q2FY27")
    assert (sheet["period"], sheet["basis"], sheet["prev_year_period"], sheet["prev_quarter_period"]) == \
        ("Q2FY27", "CONSOLIDATED", "Q2FY26", "Q1FY27")
    rev, ebitda, pat = (sheet["lines"][k] for k in ("revenue", "ebitda", "pat"))
    assert (rev["value"], rev["prev_year"], rev["prev_quarter"], rev["yoy_pct"], rev["qoq_pct"]) == (1200.0, 1000.0, 1100.0, 20.0, 9.1)
    assert (ebitda["value"], ebitda["yoy_pct"], ebitda["qoq_pct"]) == (240.0, 20.0, 20.0)
    # PAT is the profit to shareholders, compared with the same line a year and a quarter before; the total beside it
    assert (pat["value"], pat["with_minority"], pat["prev_year"], pat["yoy_pct"], pat["qoq_pct"]) == (148.0, 150.0, 118.4, 25.0, 50.0)
    assert sheet["lines"]["pbt"]["yoy_pct"] == 25.0
    assert sheet["lines"]["ebitda_margin"]["value"] == 20.0 and sheet["lines"]["ebitda_margin"]["yoy_bps"] == 0
    assert "eps" not in json.dumps(sheet).lower()   # owner rule 26 Oct 2026: no EPS on a card


def test_consolidated_when_memory_has_it_else_standalone_and_a_given_basis_is_kept():
    both = _memory()
    assert fs.fact_sheet(both, "Q2FY27")["basis"] == "CONSOLIDATED"
    assert fs.fact_sheet(both, "Q2FY27", "STANDALONE")["lines"]["revenue"]["value"] == 5.0
    alone = {"statements": [e for e in both["statements"] if e["basis"] == "STANDALONE"]}
    assert fs.fact_sheet(alone, "Q2FY27")["basis"] == "STANDALONE"


def test_no_sheet_when_memory_lacks_the_quarter_or_the_rows_are_not_a_corporate_files():
    assert fs.fact_sheet(_memory(), "Q3FY27") is None                         # the exchange file is late
    assert fs.fact_sheet({}, "Q2FY27") is None and fs.fact_sheet(_memory(), None) is None
    pdf_read = {"statements": [_entry("Q2FY27", _rows(1200.0, 240.0, 200.0, 150.0), by="pdf")]}
    assert fs.fact_sheet(pdf_read, "Q2FY27") is None                          # only file-labelled rows count
    bank = {"statements": [_entry("Q2FY27", {"Revenue": 9.0, "Financing Profit": 3.0, "Net Profit": 2.0}, family="bank")]}
    assert fs.fact_sheet(bank, "Q2FY27") is None


def test_a_missing_comparative_gives_no_change_and_a_loss_gives_a_turn_not_a_percent():
    mem = {"statements": [_entry("Q2FY27", _rows(1200.0, 240.0, 200.0, 50.0)),
                          _entry("Q2FY26", _rows(1000.0, 200.0, 160.0, -20.0))]}
    lines = fs.fact_sheet(mem, "Q2FY27")["lines"]
    assert "qoq_pct" not in lines["revenue"] and "prev_quarter" not in lines["revenue"]
    assert lines["pat"]["yoy_turn"] == "LOSS_TO_PROFIT" and "yoy_pct" not in lines["pat"]


def test_the_block_names_the_figures_and_their_changes():
    text = fs.block(fs.fact_sheet(_memory(), "Q2FY27"))
    assert text.startswith("RESULTS FIGURES (from the exchange file; use only these for results lines)")
    assert "Revenue: 1,200.00; year ago 1,000.00; previous quarter 1,100.00; +20.0% YoY; +9.1% QoQ" in text
    assert "Consolidated, ₹ crore, quarter Q2FY27" in text


def test_the_results_table_takes_the_sheets_rows_and_keeps_its_other_lines():
    sheet = fs.fact_sheet(_memory(), "Q2FY27")
    results = {"period": "Q2FY27", "lens": "company", "lines": [{"key": "revenue"}],
               "revenue": {"value": 1199.0, "prev_year": 990.0, "yoy_pct": 21.1, "qoq_pct": 1.0},
               "ebitda": {"value": 250.0}, "kpi:volume": {"value": 3.0}}
    notes = fs.apply_to_results(results, sheet)
    assert results["revenue"] == {"value": 1200.0, "prev_year": 1000.0, "prev_quarter": 1100.0, "yoy_pct": 20.0, "qoq_pct": 9.1}
    assert results["ebitda"]["value"] == 240.0 and results["kpi:volume"] == {"value": 3.0}
    assert {n["line"] for n in notes} == {"revenue", "ebitda"} and notes[0]["was"]["value"] == 1199.0
    # a bank's table, or another quarter's, is left alone
    bank = {"period": "Q2FY27", "lens": "bank", "revenue": {"value": 1.0}}
    assert fs.apply_to_results(bank, sheet) == [] and bank["revenue"] == {"value": 1.0}
    assert fs.apply_to_results({"period": "Q1FY27", "lens": "company", "revenue": {"value": 1.0}}, sheet) == []
    assert fs.apply_to_results(None, sheet) == [] and fs.apply_to_results(results, None) == []


def _card(**fields):
    card = {"impact_level": "HIGH", "headline": "Demo Q2 revenue ₹1,200 Cr", "what_happened": ["Revenue ₹1,200 Cr"], **fields}
    return Pass2Output.model_validate({"is_material": True, "event_type": "RESULTS", "card": card, "timeline_entry": "Q2FY27 results."})


def test_a_figure_the_sheet_contradicts_is_taken_out_and_one_it_agrees_with_stays():
    sheet = fs.fact_sheet(_memory(), "Q2FY27")
    out = _card(
        takeaway="Revenue rose 20.0% YoY to ₹1,200 Cr. EBITDA was ₹300 Cr. PAT grew 40% YoY.",
        what_happened=["Revenue was ₹1,200 Cr against ₹1,000 Cr a year ago", "EBITDA of ₹300.5 Cr", "Net profit ₹150 Cr, up 25% YoY",
                       "Order book at ₹5,000 Cr"],
        key_numbers=[{"label": "Revenue", "value": "₹1,250 Cr", "change": "+25% YoY"}, {"label": "PBT", "value": "₹200 Cr"}],
        why_it_matters=[{"text": "Revenue grew 9.1% QoQ, a sequential gain", "basis": "FILING"},
                        {"text": "Revenue grew 15% QoQ on volumes", "basis": "FILING"}])
    notes = fs.removed(out, sheet)
    card = out.card
    assert card.takeaway == "Revenue rose 20.0% YoY to ₹1,200 Cr."   # the EBITDA and PAT sentences are cut
    assert [f.text for f in card.what_happened] == ["Revenue was ₹1,200 Cr against ₹1,000 Cr a year ago", "Net profit ₹150 Cr, up 25% YoY",
                                                    "Order book at ₹5,000 Cr"]
    assert [k.label for k in card.key_numbers] == ["PBT"]
    assert [i.text for i in card.why_it_matters] == ["Revenue grew 9.1% QoQ, a sequential gain"]
    assert len(notes) == 4 and all("exchange file" in n for n in notes)
    assert fs.removed(out, None) == [] and fs.removed(_card(), sheet) == []


def test_other_periods_segments_and_guidance_are_not_judged():
    sheet = fs.fact_sheet(_memory(), "Q2FY27")
    for sentence in ("FY27 revenue guidance is ₹5,000 Cr", "H1 revenue was ₹2,300 Cr", "Segment revenue was ₹600 Cr",
                     "Revenue and EBITDA were ₹900 Cr and ₹100 Cr", "Capex of ₹300 Cr", "Revenue Q1FY25 was ₹700 Cr and FY26 ₹4,000 Cr"):
        assert fs.disagreements(sentence, sheet) == [], sentence
    assert fs.disagreements("Q2FY27 revenue was ₹900 Cr", sheet)[0][0] == "900"
    # rounding: whole crore or one decimal of the sheet's value is the same figure
    assert fs.disagreements("Revenue was ₹1,200.0 Cr (+20% YoY, +9% QoQ)", sheet) == []


# --- the live path -------------------------------------------------------------------------------------------------------

def _run(settings, switch, monkeypatch):
    monkeypatch.setenv("CARD_FACT_SHEET", switch)
    now = now_ist() - timedelta(minutes=30)
    filing = _filing("n-fs", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    text = ("Statement of unaudited consolidated financial results for the quarter ended 30.09.2026 (Rs. in lakhs). "
            "Revenue from operations 12,000.00 9,091.00. Net profit 1,500.00.")
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf(text), "https://bse.invalid/co.xml": results_xml()},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)]})
    pipeline.bse.archive = {"999001": [XbrlLink("Q2FY27", "CONSOLIDATED", "https://bse.invalid/co.xml", f"{now.date()}T18:05:00")]}
    pipeline.run("live", time_budget_s=60)
    row = sink._db.execute("select card_json from cards where news_id = 'n-fs'").fetchone()
    return json.loads(row[0]), fake


def test_on_the_card_has_the_sheet_in_its_prompt_and_its_table_from_it(settings, monkeypatch):
    card, fake = _run(settings, "1", monkeypatch)
    prompt = fake.calls[0]["messages"][1]["content"]
    assert "RESULTS FIGURES (from the exchange file; use only these for results lines)" in prompt
    assert "Revenue: 120.00" in prompt
    note = card["grounding"]["fact_sheet"]
    assert (note["period"], note["basis"]) == ("Q2FY27", "CONSOLIDATED")
    assert card["results"]["revenue"]["value"] == 120.0


@pytest.mark.parametrize("switch", ["0", ""])
def test_off_nothing_changes(settings, monkeypatch, switch):
    card, fake = _run(settings, switch, monkeypatch)
    assert "RESULTS FIGURES" not in fake.calls[0]["messages"][1]["content"]
    assert "fact_sheet" not in card["grounding"]


# --- the A/B command -----------------------------------------------------------------------------------------------------------

def test_the_ab_makes_each_card_twice_writes_nothing_and_leaves_the_switch_as_it_was(settings, monkeypatch, tmp_path):
    import argparse
    import os

    from bse_intel import call_memory, cli

    monkeypatch.delenv("CARD_FACT_SHEET", raising=False)
    now = now_ist() - timedelta(minutes=30)
    filing = _filing("n-ab", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    filing = filing.model_copy(update={"xbrl_url": "https://bse.invalid/co.xml", "route": "FAST_TRACK", "event_type": "RESULTS"})
    text = ("Statement of unaudited consolidated financial results for the quarter ended 30.09.2026 (Rs. in lakhs). "
            "Revenue from operations 12,000.00 9,091.00. Net profit 1,500.00.")
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf(text), "https://bse.invalid/co.xml": results_xml()},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)]})
    monkeypatch.setattr(call_memory, "find_filing", lambda s, news_id: filing)
    monkeypatch.setattr(cli, "_pipeline", lambda s, quiet: (setattr(pipeline, "sink", quiet), pipeline)[1])
    fakes = pipeline.bse
    monkeypatch.setattr(cli, "_NoExchange", lambda: fakes)   # the fakes stand in for our stored copies here; see the test below
    assert cli.cmd_fact_sheet_ab(argparse.Namespace(ids="n-ab", out=str(tmp_path)), settings, sink) == 0
    both = json.loads((tmp_path / "n-ab.json").read_text(encoding="utf-8"))
    assert both["off_status"] == both["on_status"] == "ANALYZED"
    assert "fact_sheet" not in both["off"]["card"]["grounding"] and both["fact_sheet"]["basis"] == "CONSOLIDATED"
    prompts = [c["messages"][1]["content"] for c in fake.calls]
    assert len(prompts) == 2 and "RESULTS FIGURES" not in prompts[0] and "RESULTS FIGURES" in prompts[1]
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["made"] == 1 and summary["with_fact_sheet"] == 1 and summary["blocked_writes"]
    assert not sink._db.execute("select 1 from cards").fetchall() and sink.get_dossier(filing.scrip_code) is None
    assert "CARD_FACT_SHEET" not in os.environ


def test_the_ab_with_one_named_model_makes_only_the_switch_on_card_and_saves_it(settings, monkeypatch, tmp_path):
    """FACT_SHEET_AB_ON_ONLY (the model grid, 30 Oct 2026): the first grid run lost every card to a KeyError on the missing
    switch-off card, so nothing could be scored."""
    import argparse

    from bse_intel import call_memory, cli

    monkeypatch.setenv("FACT_SHEET_AB_ON_ONLY", "1")
    now = now_ist() - timedelta(minutes=30)
    filing = _filing("n-on", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    filing = filing.model_copy(update={"xbrl_url": "https://bse.invalid/co.xml", "route": "FAST_TRACK", "event_type": "RESULTS"})
    text = ("Statement of unaudited consolidated financial results for the quarter ended 30.09.2026 (Rs. in lakhs). "
            "Revenue from operations 12,000.00 9,091.00. Net profit 1,500.00.")
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf(text), "https://bse.invalid/co.xml": results_xml()},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)]})
    monkeypatch.setattr(call_memory, "find_filing", lambda s, news_id: filing)
    monkeypatch.setattr(cli, "_pipeline", lambda s, quiet: (setattr(pipeline, "sink", quiet), pipeline)[1])
    fakes = pipeline.bse
    monkeypatch.setattr(cli, "_NoExchange", lambda: fakes)
    assert cli.cmd_fact_sheet_ab(argparse.Namespace(ids="n-on", out=str(tmp_path)), settings, sink) == 0
    saved = json.loads((tmp_path / "n-on.json").read_text(encoding="utf-8"))
    assert saved["on_status"] == "ANALYZED" and saved["off"] is None and saved["on"]["card"]
    assert len(fake.calls) == 1


def test_the_ab_sink_reads_our_stored_copies_and_never_downloads_again():
    """Owner rule: never download a file twice. The A/B's read-only sink must still be seen as the platform store, so the
    pipeline reads stored texts (F147) and XBRL files (F191) instead of fetching them from NSE again."""
    from bse_intel import cli, xbrl_store
    from bse_intel.sinks.platform import PlatformSink

    platform = PlatformSink.__new__(PlatformSink)
    wrapped = cli._ReadOnlySink(platform)
    assert xbrl_store.enabled(wrapped) and xbrl_store.enabled(platform)
    wrapped.put_object("k", b"x")
    assert wrapped.blocked == {"put_object": 1}


def test_the_ab_never_calls_an_exchange_and_the_on_card_reads_memory_as_stored(settings, monkeypatch, tmp_path):
    """Blind review: a filing with no stored text failed over to an NSE download, and the on card read the off card's merge."""
    import argparse

    from bse_intel import call_memory, cli

    now = now_ist() - timedelta(minutes=30)
    filing = _filing("n-ab2", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf("Revenue 12,000.00")}, {})
    monkeypatch.setattr(call_memory, "find_filing", lambda s, news_id: filing)
    monkeypatch.setattr(cli, "_pipeline", lambda s, quiet: (setattr(pipeline, "sink", quiet), pipeline)[1])
    pipeline._pending_memory["x"] = [("n-old", {"timeline": []}, {})]
    assert cli.cmd_fact_sheet_ab(argparse.Namespace(ids="n-ab2", out=str(tmp_path)), settings, sink) == 1
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert "no exchange call here" in summary["rows"][0]["error"] and not fake.calls
    assert not pipeline._pending_memory and summary["not_like_for_like"] == 0   # an error, not a warning


def test_the_no_exchange_stub_counts_every_refused_call():
    from bse_intel import cli
    from bse_intel.bse import AttachmentError

    stub = cli._NoExchange()
    with pytest.raises(AttachmentError):
        stub.results_xbrl("500001")
    assert stub.calls == ["results_xbrl"]


def test_the_ab_takes_the_results_file_link_from_the_stored_card():
    from types import SimpleNamespace

    from bse_intel import cli

    card = {"xbrl": {"url": "https://nsearchives.nseindia.com/corporate/xbrl/X.xml"}}
    rows = [{"news_id": "n-0", "card_json": "{}"}, {"news_id": "n-ab", "card_json": json.dumps(card)}]
    sink = SimpleNamespace(query=lambda name, params: rows if name == "export_cards" else [])
    filing = SimpleNamespace(news_id="n-ab", filed_at="2026-10-29T16:21:40+05:30")
    assert cli._stored_card_xbrl(sink, filing) == card["xbrl"]["url"]
    assert cli._stored_card_xbrl(sink, SimpleNamespace(news_id="n-0", filed_at="2026-10-29T16:21:40")) is None


def test_a_comparative_without_the_shareholders_line_gives_no_change_on_another_footing():
    memory = _memory()
    memory["statements"][1]["rows"].pop("Net Profit (owners)")     # the year-ago quarter states only the total
    pat = fs.fact_sheet(memory, "Q2FY27")["lines"]["pat"]
    assert pat["value"] == 148.0 and "prev_year" not in pat and "yoy_pct" not in pat and pat["qoq_pct"] == 50.0


def test_a_card_gets_the_corrected_profit_of_a_quarter_whose_filed_profit_does_not_add_up():
    # the shared profit-line rules (screener_view.corrected_pl) reach the card: ATUL Q2FY26 (owners 87.95 beside 182.37 and a minority of 3.13),
    # APARINDS Q1FY27 (-138.56 beside PBT 625 and tax 157.55), PNB Housing-like filler 0 owners (the card's PAT line reads the owners' row first)
    def entry(period, net, owners, minority=None, pbt=None, tax=None, family="corporate"):
        rows = _rows(1500.0, 300.0, pbt if pbt is not None else net * 1.3, net, owners=owners)
        if minority is not None:
            rows["Minority share"] = minority
        if tax is not None:
            rows["Tax"] = tax
        return _entry(period, rows, family=family)
    atul = {"statements": [entry("Q2FY27", 158.8, 155.67, 3.13), entry("Q2FY26", 182.37, 87.95, 3.13)]}
    pat = fs.fact_sheet(atul, "Q2FY27")["lines"]["pat"]
    assert (pat["prev_year"], pat["yoy_pct"]) == (179.24, -13.1)
    apar = {"statements": [entry("Q1FY27", -138.56, -138.56, 0.0, pbt=625.0, tax=157.55), entry("Q1FY26", 225.0, 225.0, 0.0, pbt=300.0, tax=75.0)]}
    pat = fs.fact_sheet(apar, "Q1FY27")["lines"]["pat"]
    assert (pat["value"], pat["yoy_pct"]) == (467.45, 107.8)
    pnb = {"statements": [entry("Q2FY27", 560.0, 0.0), entry("Q2FY26", 500.0, 0.0)]}
    pat = fs.fact_sheet(pnb, "Q2FY27")["lines"]["pat"]
    assert (pat["value"], pat["yoy_pct"]) == (560.0, 12.0)


def test_the_ab_can_flip_the_lenders_switch_with_the_fact_sheet_kept_on(settings, monkeypatch, tmp_path):
    """FACT_SHEET_AB_SWITCH=CARD_FACT_SHEET_LENDERS (TODO 151): CARD_FACT_SHEET is held on for both cards (a corporate filer's card
    therefore has its sheet both times), only the lenders' switch is flipped, and both switches are as they were afterwards."""
    import argparse
    import os

    from bse_intel import call_memory, cli

    monkeypatch.delenv("CARD_FACT_SHEET", raising=False)
    monkeypatch.delenv("CARD_FACT_SHEET_LENDERS", raising=False)
    monkeypatch.setenv("FACT_SHEET_AB_SWITCH", "CARD_FACT_SHEET_LENDERS")
    now = now_ist() - timedelta(minutes=30)
    filing = _filing("n-len", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    filing = filing.model_copy(update={"xbrl_url": "https://bse.invalid/co.xml", "route": "FAST_TRACK", "event_type": "RESULTS"})
    text = ("Statement of unaudited consolidated financial results for the quarter ended 30.09.2026 (Rs. in lakhs). "
            "Revenue from operations 12,000.00 9,091.00. Net profit 1,500.00.")
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf(text), "https://bse.invalid/co.xml": results_xml()},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)]})
    monkeypatch.setattr(call_memory, "find_filing", lambda s, news_id: filing)
    monkeypatch.setattr(cli, "_pipeline", lambda s, quiet: (setattr(pipeline, "sink", quiet), pipeline)[1])
    fakes = pipeline.bse
    monkeypatch.setattr(cli, "_NoExchange", lambda: fakes)
    assert cli.cmd_fact_sheet_ab(argparse.Namespace(ids="n-len", out=str(tmp_path)), settings, sink) == 0
    prompts = [c["messages"][1]["content"] for c in fake.calls]
    assert len(prompts) == 2 and all("RESULTS FIGURES" in p for p in prompts)      # the fact sheet on for both
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["switch"] == "CARD_FACT_SHEET_LENDERS"
    assert "CARD_FACT_SHEET" not in os.environ and "CARD_FACT_SHEET_LENDERS" not in os.environ
    monkeypatch.setenv("FACT_SHEET_AB_SWITCH", "CRITIC")
    assert cli.cmd_fact_sheet_ab(argparse.Namespace(ids="n-len", out=str(tmp_path)), settings, sink) == 2
