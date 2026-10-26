"""CARD_FOOTER_PLAUSIBLE (F182, TODO 77): a footer KPI that cannot be right is not shown, and the card keeps why.
Real case: GIC Housing Finance (nse-106827848, 26 Oct 2026 audit), NIM 19.63% against FY26 3.41%."""
from __future__ import annotations

import pytest

from bse_intel import footer_plausible as fp
from bse_intel.dossier import latest_fundamentals, results_snapshot

NIM = {"metric": "nim", "label": "NIM", "format": "pct", "aliases": ["nim_pct", "net_interest_margin"]}
MARGIN = {"metric": "ebitda_margin", "label": "EBITDA margin", "format": "pct", "aliases": ["ebitda_margin_pct", "opm"]}
HFC = "Financial Services > Finance > Housing Finance Company"


@pytest.fixture(autouse=True)
def _off(monkeypatch):
    monkeypatch.delenv("CARD_FOOTER_PLAUSIBLE", raising=False)


def m(metric, period, value, news="n1", unit="PCT", as_of="2026-10-01"):
    return {"metric": metric, "period": period, "value": value, "unit": unit, "source_news_id": news, "as_of": as_of}


def gic(nim=19.63):
    """GIC Housing Finance: FY26 NIM 3.41%, and a card-read 19.63% for Q2FY27; profit and revenue so the table builds."""
    rows = [m("nim", "FY26", 3.41), m("nim", "FY25", 3.2), m("nim", "Q2FY27", nim, "n2"),
            m("revenue", "Q2FY27", 300.0, "n2", "INR_CR"), m("revenue", "Q2FY26", 280.0, "n1", "INR_CR"),
            m("revenue", "Q1FY27", 290.0, "n1", "INR_CR"), m("pat", "Q2FY27", 40.0, "n2", "INR_CR"),
            m("pat", "Q2FY26", 38.0, "n1", "INR_CR"), m("pat", "Q1FY27", 39.0, "n1", "INR_CR"),
            m("pbt", "Q2FY27", 50.0, "n2", "INR_CR"), m("pbt", "Q2FY26", 48.0, "n1", "INR_CR")]
    return {"financial_metrics": rows, "industry": HFC}


def test_the_company_type_is_read_from_the_most_specific_level():
    assert fp.company_type(HFC) == "hfc"
    assert fp.company_type("Financial Services > Banks > Private Sector Bank") == "bank"
    assert fp.company_type("Financial Services > Non Banking Financial Company (NBFC)") == "lender"
    assert fp.company_type("Capital Goods > Industrial Machinery") == "other"
    assert fp.company_type(None) == "other"


def test_gic_housings_nim_is_outside_the_range_of_a_home_loan_lender_and_far_above_its_own_year():
    d = gic()
    entry = next(e for e in d["financial_metrics"] if e["period"] == "Q2FY27" and e["metric"] == "nim")
    why = fp.hide_reason(d["financial_metrics"], ("nim", *NIM["aliases"]), entry, "pct", HFC)
    assert why and "19.63% is outside the 1-7%" in why
    # with no industry the company's own history still stops it: more than 3x its last years
    own = fp.hide_reason(d["financial_metrics"], ("nim", *NIM["aliases"]), entry, "pct", None)
    assert own and "more than 3x" in own and "3.41" in own


def test_a_normal_nim_and_a_real_move_are_shown():
    d = gic(nim=3.8)
    entry = next(e for e in d["financial_metrics"] if e["period"] == "Q2FY27" and e["metric"] == "nim")
    assert fp.hide_reason(d["financial_metrics"], ("nim",), entry, "pct", HFC) is None
    assert fp.hide_reason([], ("nim",), entry, "pct", HFC) is None   # no history, in range: shown


def test_a_bank_and_a_factory_have_their_own_ranges():
    nim = m("nim", "Q2FY27", 7.5)
    assert "1.5-6%" in fp.hide_reason([], ("nim",), nim, "pct", "Financial Services > Banks > Private Sector Bank")
    assert fp.hide_reason([], ("nim",), nim, "pct", "Financial Services > Non Banking Financial Company (NBFC)") is None  # microfinance can be 10%
    margin = m("ebitda_margin", "Q2FY27", 75.0)
    assert "-50% to 60%" in fp.hide_reason([], ("ebitda_margin", "opm"), margin, "pct", "Capital Goods > Industrial Machinery")
    assert fp.hide_reason([], ("ebitda_margin",), m("ebitda_margin", "Q2FY27", 55.0), "pct", "Materials > Cement") is None
    assert fp.hide_reason([], ("ebitda_margin",), m("ebitda_margin", "Q2FY27", -40.0), "pct", "Materials > Cement") is None


def test_under_a_third_of_the_last_four_quarters_is_hidden():
    rows = [m("ebitda_margin", f"Q{i}FY26", v) for i, v in enumerate([18.0, 19.0, 17.0, 18.5], 1)]
    low = m("ebitda_margin", "Q1FY27", 4.0)
    why = fp.hide_reason(rows, ("ebitda_margin",), low, "pct", "Materials > Cement")
    assert why and "under a third" in why
    assert fp.hide_reason(rows, ("ebitda_margin",), m("ebitda_margin", "Q1FY27", 9.0), "pct", "Materials > Cement") is None


def test_the_footer_strip_is_unchanged_off_and_hides_the_figure_on(monkeypatch):
    d = gic()
    off = latest_fundamentals(d, [NIM])
    assert off["kpis"] == [{"label": "NIM", "format": "pct", "period": "Q2FY27", "value": 19.63}] and "footer_hidden" not in off
    monkeypatch.setenv("CARD_FOOTER_PLAUSIBLE", "1")
    on = latest_fundamentals(d, [NIM])
    assert "kpis" not in on
    assert on["footer_hidden"][0]["label"] == "NIM" and on["footer_hidden"][0]["value"] == 19.63 and on["footer_hidden"][0]["period"] == "Q2FY27"
    assert latest_fundamentals(gic(nim=3.8), [NIM])["kpis"][0]["value"] == 3.8   # a real figure stays


def test_the_results_table_leaves_the_row_off_and_records_it(monkeypatch):
    d = gic()
    off = results_snapshot(d, "n2", [NIM])
    assert off["kpi:nim"]["value"] == 19.63 and "footer_hidden" not in off
    monkeypatch.setenv("CARD_FOOTER_PLAUSIBLE", "1")
    on = results_snapshot(d, "n2", [NIM])
    assert "kpi:nim" not in on and all(x["key"] != "kpi:nim" for x in on["lines"])
    assert on["footer_hidden"][0]["label"] == "NIM"


def test_the_card_keeps_one_line_a_hidden_figure_for_the_issues_page(monkeypatch):
    monkeypatch.setenv("CARD_FOOTER_PLAUSIBLE", "1")
    d = gic()
    card = {"fundamentals": latest_fundamentals(d, [NIM]), "results": results_snapshot(d, "n2", [NIM])}
    lines = fp.card_notes(card)
    assert len(lines) == 1 and lines[0].startswith("NIM 19.63 (Q2FY27) not shown: 19.63% is outside the 1-7%")


def test_refreshing_a_stored_card_records_the_hidden_footer_figure(monkeypatch):
    from bse_intel.card_refresh import refresh
    from bse_intel.models import Filing
    filing = Filing(news_id="n2", scrip_code="1", company_name="GIC Housing", headline="Results", subject="",
                    filed_at="2026-10-26T10:00:00+05:30", filing_date="2026-10-26")
    stored = {"event_type": "OTHER", "headline": "GIC Housing", "what_happened": [{"text": "NIM 19.63%"}], "impact_level": "LOW", "signals": [],
              "fundamentals": {"kpis": [{"label": "NIM", "format": "pct", "period": "Q2FY27", "value": 19.63}]}}
    same, _ = refresh(stored, gic(), filing, None, [NIM])
    assert "grounding" not in same
    monkeypatch.setenv("CARD_FOOTER_PLAUSIBLE", "1")
    new, changed = refresh(stored, gic(), filing, None, [NIM])
    assert "grounding" in changed and new["grounding"]["footer_hidden"][0].startswith("NIM 19.63")
