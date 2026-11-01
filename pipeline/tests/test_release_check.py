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
                          "results_statement", "unit_slip_guard", "other_issuer", "adjusted_profit"}
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
