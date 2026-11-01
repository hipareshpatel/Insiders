"""scripts/release_check.py: the on/off release check of every card switch (F170), no AI, no network here."""

from __future__ import annotations

import gzip
import importlib.util
import json
import os
import sys
from pathlib import Path

from test_card_v2 import RELEASE, _dossier


def _script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "release_check.py"
    spec = importlib.util.spec_from_file_location("release_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_line_diff_pairs_a_changed_line_by_its_label():
    rc = _script()
    off = ["TABLE PAT: value 46.15", "TABLE Revenue: value 388.15", "FACT a", "HEADLINE x"]
    on = ["TABLE PAT: value 48.43", "TABLE Revenue: value 388.15", "TABLE EBITDA (Filing): value 286.61", "HEADLINE x"]
    d = rc.line_diff(off, on)
    assert d["changed"] == [{"before": "TABLE PAT: value 46.15", "after": "TABLE PAT: value 48.43"}]
    assert d["added"] == ["TABLE EBITDA (Filing): value 286.61"] and d["removed"] == ["FACT a"]
    assert not rc.changed_by_diff(rc.line_diff(off, off))


def test_the_sample_is_seeded_independent_of_read_order_and_keeps_the_key_apart():
    rc = _script()
    recs = [{"news_id": f"n{i}", "symbol": "S", "scrip_code": "1", "pdf_url": "u", "off_lines": ["o"], "on_lines": ["n"]}
            for i in range(30)]
    a = rc.draw_sample(recs, 170, 20)
    b = rc.draw_sample(list(reversed(recs)), 170, 20)
    assert [r["news_id"] for r in a] == [r["news_id"] for r in b] and len(a) == 20
    items, key = rc.blind_pairs(a, 170)
    assert items == rc.blind_pairs(b, 170)[0]
    for it in items:
        on = it["X"] if key[it["id"]]["on_is"] == "X" else it["Y"]
        assert on == ["n"]
    assert "on_is" not in json.dumps(items)
    assert len(rc.draw_sample(recs[:3], 170, 20)) == 3


def test_the_switches_are_set_for_the_block_and_restored(monkeypatch):
    rc = _script()
    monkeypatch.setenv("CARD_TWO_PARTS", "1")
    monkeypatch.delenv("QUOTE_EXACT_NUMBERS", raising=False)
    with rc.switches_on("QUOTE_EXACT_NUMBERS"):
        assert os.environ["QUOTE_EXACT_NUMBERS"] == "1" and os.environ["CARD_TWO_PARTS"] == "0"
    assert os.environ["CARD_TWO_PARTS"] == "1" and "QUOTE_EXACT_NUMBERS" not in os.environ


def test_the_run_over_files_writes_a_report_a_sample_and_a_key_per_switch(tmp_path, monkeypatch):
    rc = _script()
    from bse_intel.dossier import results_snapshot
    for n in rc.ALL_SWITCHES:
        monkeypatch.delenv(n, raising=False)
    stored = results_snapshot(_dossier(), "n2")
    card = {"event_type": "RESULTS", "impact_level": "MODERATE", "headline": "Acme Q2FY27 revenue 388.15 Cr", "results": stored,
            "basis": "CONSOLIDATED", "takeaway": "Margins held.",
            "what_happened": [{"text": "Revenue 388.15", "quote": "Revenue from operations 388.15"}],
            "why_it_matters": [{"text": "Orders of ₹9,876 Cr would double revenue", "basis": "FILING"}],
            "key_numbers": [{"label": "Revenue", "value": "388.15", "quote": "Revenue from operations 388.15"}]}
    row = {"news_id": "n2", "scrip_code": "1", "symbol": "ACME", "company_name": "Acme", "filed_at": "2026-10-20T10:00:00",
           "pdf_url": "u", "headline": "Results", "held": 0, "card_json": json.dumps(card)}
    other = {**row, "news_id": "n9", "card_json": json.dumps({**card, "event_type": "OTHER"})}
    (tmp_path / "texts").mkdir()
    cache = {"v": 1, "digital": [RELEASE], "has_image": [False]}
    (tmp_path / "texts" / "n2.json.gz").write_bytes(gzip.compress(json.dumps(cache).encode()))
    (tmp_path / "dossiers").mkdir()
    dossier = _dossier()
    for m in dossier["financial_metrics"]:
        m["as_of"] = "2026-10-19T09:00:00"
    (tmp_path / "dossiers" / "1.json").write_text(json.dumps(dossier))
    (tmp_path / "cards.json").write_text(json.dumps([row, other]))
    before = dict(os.environ)
    monkeypatch.setattr(sys, "argv", ["release_check.py", str(tmp_path / "out"), "--cards", str(tmp_path / "cards.json"),
                                      "--texts", str(tmp_path / "texts"), "--dossiers", str(tmp_path / "dossiers"),
                                      "--sample", "5"])
    assert rc.main() == 0
    assert dict(os.environ) == before   # the switches are put back
    out = tmp_path / "out"
    total = json.loads((out / "release-check.json").read_text(encoding="utf-8"))
    assert set(total) == {"ebitda_v2", "same_definition", "consolidated_only", "two_parts", "quote_exact",
                          "grounded_figures", "guidance_dated", "one_basis", "year_check", "footer_plausible", "eps_follows_profit", "eps_whole", "text_support",
                          "results_statement", "unit_slip_guard", "discontinued_figure", "deck_period", "other_issuer",
                          "adjusted_profit", "words_match_figures",
                          "filer_checks", "figure_matches_file", "guided_not_actual", "event_repeat",
                          "press_release_fold", "unit_fix_scale",
                          "comparative_memory", "year_ago_label",
                          "ratio_columns"}
    assert total["ebitda_v2"]["cards_checked"] == 1 and total["ebitda_v2"]["cards_changed"] == 1   # EBITDA (Filing) row added
    assert total["ebitda_v2"]["printed_ebitda_found"] == 1
    assert total["two_parts"]["cards_checked"] == 1 and total["two_parts"]["part2_lines_hidden"] == 1
    assert total["quote_exact"]["cards_checked"] == 1 and total["quote_exact"]["errors"] == 0
    for name in total:
        for suffix in (".json", ".txt", "-blind.json", "-blind.md", "-key.json"):
            assert (out / f"{name}{suffix}").exists()
    assert "EBITDA (Filing)" in (out / "ebitda_v2.txt").read_text(encoding="utf-8")
    items = json.loads((out / "ebitda_v2-blind.json").read_text(encoding="utf-8"))
    key = json.loads((out / "ebitda_v2-key.json").read_text(encoding="utf-8"))
    assert len(items) == 1 and key["c01"]["on_is"] in ("X", "Y")
    assert "on_is" not in (out / "ebitda_v2-blind.md").read_text(encoding="utf-8")
    assert "9,876" in (out / "two_parts.txt").read_text(encoding="utf-8")


def test_results_statement_check_marks_a_results_card_whose_text_has_no_results():
    rc = _script()
    pad = " The Board reviewed the business. " * 60
    row = {"news_id": "nse-1", "symbol": "TMB", "scrip_code": "543596", "pdf_url": "u"}
    card = {"event_type": "RESULTS", "headline": "TMB provisions ₹304 Cr for ECL"}
    note = rc.check_results_statement(card, row, "A provision of Rs 304.24 crore towards ECL." + pad)
    assert rc.changed_by_diff(note["diff"]) and "TYPE: OTHER (no results statement in the text)" in note["on_lines"]
    real = rc.check_results_statement(card, row, "Statement of unaudited financial results for the quarter ended" + pad)
    assert not rc.changed_by_diff(real["diff"])


def test_other_issuer_check_marks_a_results_card_on_another_companys_statement():
    """CARD_OTHER_ISSUER (HEGAM nse-106837190): HEG Limited's results, filed by HEG Advanced Materials (formerly HEG Limited)."""
    rc = _script()
    row = {"news_id": "nse-106837190", "symbol": "HEGAM", "scrip_code": "509631", "pdf_url": "u",
           "company_name": "HEG Advanced Materials Limited"}
    memory = {"identity": {"former_names": ["HEG Limited", "Hindustan Electro Graphites Limited"]}}
    card = {"event_type": "RESULTS", "headline": "HEG Limited Q2FY27 revenue at ₹740.40 Cr"}
    text = ("HEG LIMITED (Formerly known as HEG Graphite Limited)\nRegd. Office: Mandideep\n"
            "Statement of Unaudited Financial Results for the quarter ended 30th September, 2026")
    note = rc.check_other_issuer(card, row, text, memory)
    assert rc.changed_by_diff(note["diff"]) and any(line.startswith("TYPE: OTHER (HEG LIMITED's") for line in note["on_lines"])
    own = rc.check_other_issuer(card, row, "HEG ADVANCED MATERIALS LIMITED\nStatement of Unaudited Financial Results for the "
                                           "quarter ended 30th September, 2026", memory)
    assert not rc.changed_by_diff(own["diff"])


def test_adjusted_profit_check_labels_a_profit_that_is_not_the_tables():
    """CARD_ADJUSTED_PROFIT_LABEL (TI nse-106837308): the release's adjusted PAT ₹68 Cr beside the table's reported ₹22.27 Cr."""
    rc = _script()
    row = {"news_id": "nse-106837308", "symbol": "TI", "scrip_code": "507205", "pdf_url": "u"}
    card = {"event_type": "RESULTS", "headline": "Tilaknagar Q2FY27 PAT up 30% to ₹68 Cr", "takeaway": "",
            "key_numbers": [{"label": "PAT", "value": "₹68 Cr", "quote": "PAT1 increased by 30% to Rs. 68 crore"}],
            "results": {"period": "Q2FY27", "pat": {"value": 22.27}, "lines": [{"key": "pat", "label": "PAT"}]}}
    note = rc.check_adjusted_profit(card, row)
    assert rc.changed_by_diff(note["diff"]) and "KEY PAT (company-reported; reported PAT ₹22.27 Cr): ₹68 Cr" in note["on_lines"]
    assert card["key_numbers"][0]["label"] == "PAT"   # the stored card is not changed
    same = dict(card, headline="Tilaknagar Q2FY27 PAT ₹22.27 Cr", key_numbers=[{"label": "PAT", "value": "₹22.27 Cr"}])
    assert not rc.changed_by_diff(rc.check_adjusted_profit(same, row)["diff"])


def test_words_figures_check_softens_a_word_the_figures_contradict():
    """CARD_WORDS_MATCH_FIGURES: "PAT doubled" beside a table showing +40% YoY and +5% QoQ."""
    rc = _script()
    row = {"news_id": "nse-1", "symbol": "ACME", "scrip_code": "1", "pdf_url": "u"}
    card = {"event_type": "RESULTS", "headline": "Acme Q2FY27 PAT doubled to ₹50 Cr", "takeaway": "",
            "results": {"period": "Q2FY27", "pat": {"value": 50.0, "yoy_pct": 40.0, "qoq_pct": 5.0}}}
    note = rc.check_words_figures(card, row, None)
    assert rc.changed_by_diff(note["diff"]) and "HEADLINE Acme Q2FY27 PAT rose to ₹50 Cr" in note["on_lines"]
    assert card["headline"] == "Acme Q2FY27 PAT doubled to ₹50 Cr"


def test_year_ago_label_check_puts_a_label_two_years_back_right():
    """CARD_YEAR_AGO_LABEL: HEGAM's "compared to ₹696.85 Cr in Q2FY25" on a Q2FY27 card."""
    rc = _script()
    row = {"news_id": "nse-106837190", "symbol": "HEGAM", "scrip_code": "1", "pdf_url": "u"}
    card = {"event_type": "RESULTS", "headline": "HEG Limited Q2FY27 revenue at ₹740.40 Cr", "takeaway": "",
            "what_happened": [{"text": "Revenue reached **₹740.40 Cr**, compared to **₹696.85 Cr** in Q2FY25."}]}
    note = rc.check_year_ago_label(card, row)
    assert rc.changed_by_diff(note["diff"]) and any("in Q2FY26." in line for line in note["on_lines"])
    assert "Q2FY25" in card["what_happened"][0]["text"]   # the stored card is not changed


def test_filer_checks_reads_the_cards_own_file_off_and_on(monkeypatch):
    """XBRL_FILER_CHECKS (S3, F219): the file read with the switch off and on; a figure the switch holds is a removed line."""
    import os
    from types import SimpleNamespace

    from bse_intel import xbrl

    rc = _script()

    def fake_parse(_data):
        on = os.environ.get("XBRL_FILER_CHECKS") == "1"
        metrics = [SimpleNamespace(metric="revenue", period="Q4FY26", value=593.12 if not on else None),
                   SimpleNamespace(metric="pat", period="Q4FY26", value=120.5)]
        return SimpleNamespace(basis="CONSOLIDATED", metrics=metrics)

    monkeypatch.setattr(xbrl, "parse", fake_parse)
    row = {"news_id": "nse-1", "symbol": "APTUS", "scrip_code": "543335", "pdf_url": "u"}
    note = rc.check_filer_checks({"event_type": "RESULTS"}, b"<xbrl/>", row)
    assert "TABLE revenue Q4FY26 CONSOLIDATED: 593.12" in note["off_lines"]
    assert "TABLE revenue Q4FY26 CONSOLIDATED: 593.12" not in note["on_lines"] and rc.changed_by_diff(note["diff"])
    assert os.environ.get("XBRL_FILER_CHECKS") != "1"   # restored after


def test_event_repeat_check_holds_a_second_card_on_one_order():
    """CARD_EVENT_REPEAT (S2): ARIS's press release of the ₹250 Cr Transcon order already filed as an intimation."""
    rc = _script()
    row = {"news_id": "nse-106830842", "symbol": "ARIS", "scrip_code": "544419", "pdf_url": "u",
           "company_name": "Arisinfra Solutions Limited", "filed_at": "2026-10-27T18:45:34+05:30"}
    card = {"event_type": "ORDER_WIN", "headline": "Arisinfra subsidiary wins ₹250 Cr DaaS mandate for Transcon Ramdev Plaza"}
    memory = {"timeline": [{"event_type": "ORDER_WIN", "date": "2026-10-27T18:40:37+05:30", "news_id": "nse-106830824",
                            "summary": "Arisinfra's subsidiary secured a ₹250 Cr DaaS service order from Transcon Iconica."}]}
    note = rc.check_event_repeat(card, row, memory)
    assert rc.changed_by_diff(note["diff"]) and any(line.startswith("HELD: repeat of nse-106830824") for line in note["on_lines"])
    assert not rc.changed_by_diff(rc.check_event_repeat(card, row, {"timeline": []})["diff"])


def test_press_release_fold_pairs_a_release_with_its_quarters_first_card():
    """RESULTS_PRESS_RELEASE (TODO 135): a later same-quarter card whose file name says "PressRelease" (glued), with no exchange
    file and no statement in its text, would be folded into the quarter's first card."""
    rc = _script()
    first = {"scrip": "1", "period": "Q2FY27", "news_id": "nse-1", "headline": "Acme Q2FY27 revenue ₹100 Cr",
             "filed_at": "2026-10-28T15:00:00+05:30", "symbol": "ACME", "pdf_url": "u1"}
    card = {"event_type": "RESULTS", "headline": "Acme Q2FY27: revenue up 12%"}
    row = {"news_id": "nse-2", "pdf_url": "https://x/corporate/ACME_28102026_PressRelease_Q2.pdf"}
    assert rc.release_candidate(card, row, "Acme reported revenue of Rs 100 crore, up 12%. " * 50)
    assert rc.release_candidate(card, row, "Statement of unaudited financial results for the quarter ended") is None
    assert rc.release_candidate(dict(card, xbrl={"url": "f.xml"}), row, None) is None       # its own file: a statement filing
    assert rc.release_candidate(card, {"news_id": "nse-2", "pdf_url": "https://x/Outcome.pdf"}, "text") is None
    later = dict(first, news_id="nse-2", filed_at="2026-10-28T16:00:00+05:30", why="x")
    pairs = rc.fold_pairs([first, later], [later])
    assert len(pairs) == 1 and pairs[0]["into"] == "nse-1"
    assert rc.fold_pairs([later], [later]) == []      # no earlier card: it stays the quarter's card


def test_unit_fix_scale_keeps_a_figure_at_the_companys_own_scale():
    """UNIT_FIX_SCALE_GUARD (CDSL nse-106838164): the deck's ₹272 Cr standalone revenue was "corrected" to ₹2.72 Cr."""
    rc = _script()
    row = {"news_id": "nse-106838164", "symbol": "CDSL", "scrip_code": "1", "pdf_url": "u"}
    card = {"event_type": "CONCALL_PRESENTATION", "grounding": {"unit_fixes": {"272": "2.72", "45,582": "455.82"}}}
    memory = {"financial_metrics": [{"metric": "revenue", "period": "Q2FY27", "value": 394.48},
                                    {"metric": "pat", "period": "Q2FY27", "value": 173.85}]}
    note = rc.check_unit_fix_scale(card, row, memory)
    assert "UNIT FIX 272 Cr kept (the company's scale)" in note["on_lines"]
    assert "UNIT FIX 45,582 Cr -> 455.82 Cr" in note["on_lines"]   # a correction onto its scale stays
    assert not rc.changed_by_diff(rc.check_unit_fix_scale(card, row, None)["diff"])   # no memory: nothing refused


def test_ratio_columns_check_lists_a_shifted_ratio_comparison():
    """CARD_RATIO_COLUMNS (VIMTALABS nse-106836191): the year-ago margin taken for the previous quarter's."""
    rc = _script()
    row = {"news_id": "nse-106836191", "symbol": "VIMTALABS", "scrip_code": "1", "pdf_url": "u"}
    card = {"headline": "Vimta Labs Q2FY27 revenue ₹112 Cr; EBITDA margin 35.5%",
            "what_happened": [{"text": "EBITDA for Q2FY27 was ₹40.8 Cr.", "quote": "EBIDTA 408 411 -0.8% 369 10.5% 819 723 13.2%"}],
            "why_it_matters": [{"text": "EBITDA margin of 35.5% in Q2FY27 is higher than the 35.3% in Q1FY27.",
                                "quote": "EBIDTA (%) 35.5% 36.4% 35.3% 36.0% 35.5%"}]}
    note = rc.check_ratio_columns(card, row)
    assert rc.changed_by_diff(note["diff"]) and not any("35.3%" in line for line in note["on_lines"])
    assert "35.3%" in card["why_it_matters"][0]["text"]   # the stored card is not changed
