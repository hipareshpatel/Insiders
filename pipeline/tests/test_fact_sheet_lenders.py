"""TODO 151: the fact sheet for banks, NBFCs and insurers (fact_sheet.FAMILY_LINES, behind CARD_FACT_SHEET_LENDERS).

The quarters come from the real exchange files in fixtures/ (HDFC Bank, Bajaj Finance and HDFC Life Q2FY27 consolidated), turned into
statements by the live path's own step (statements.remember). The year-ago quarters are those entries with their rows scaled (made
up), so the changes can be checked."""

import copy
from pathlib import Path

import pytest

from bse_intel import fact_sheet as fs
from bse_intel import screener_view as sv
from bse_intel import statements
from bse_intel import xbrl_facts as xf
from bse_intel.metrics import CONSOLIDATED

FIX = Path(__file__).parent / "fixtures"


def dossier_of(name: str, scrip: str, year_ago_scale: float | None = 0.8, industry: str | None = None) -> tuple[dict, str]:
    doc = xf.parse_facts((FIX / name).read_bytes(), scrip, f"https://nsearchives.nseindia.com/{name}")
    d: dict = {"industry": industry} if industry else {}
    statements.remember(d, doc, "nse-1", "2026-10-20", "2026-10-20T10:00:00Z")
    if year_ago_scale is not None:
        q = next(e for e in d[statements.KEY] if e["table"] == "quarters")
        old = copy.deepcopy(q)
        old["period"], old["source_news_id"] = "Q2FY26", "nse-0"
        old["rows"] = {k: v * year_ago_scale for k, v in old["rows"].items()}
        d[statements.KEY].append(old)
    return d, doc["period"]


def test_off_keeps_lenders_out():
    d, period = dossier_of("nse_hdfcbank_q2fy27_cons.xml", "500180")
    assert fs.fact_sheet(d, period, lenders=False) is None


def test_bank_sheet():
    d, period = dossier_of("nse_hdfcbank_q2fy27_cons.xml", "500180")
    sheet = fs.fact_sheet(d, period, lenders=True)
    assert sheet["family"] == sv.BANK and sheet["basis"] == CONSOLIDATED
    lines = sheet["lines"]
    assert lines["revenue"]["label"] == "Interest earned" and lines["revenue"]["value"] == pytest.approx(95131.63)
    assert lines["nii"]["value"] == pytest.approx(95131.63 - 50667.43)          # Revenue - Interest
    assert lines["pbt"]["value"] == pytest.approx(27825.48)
    assert lines["pat"]["value"] == pytest.approx(20700.03) and lines["pat"]["label"] == "Net profit"
    assert lines["nii"]["prev_year"] == pytest.approx((95131.63 - 50667.43) * 0.8)
    assert lines["nii"]["yoy_pct"] == 25.0
    # a quarter has no depreciation for a bank (the cash flow is half-yearly): no financing profit, so no line, never a made-up one
    assert "financing_profit" not in lines
    block = fs.block(sheet)
    assert "Net interest income: 44,464.20" in block and "Interest earned: 95,131.63" in block


def test_nbfc_sheet():
    d, period = dossier_of("nse_bajfin_q2fy27_cons.xml", "500034")
    sheet = fs.fact_sheet(d, period, lenders=True)
    assert sheet["family"] == sv.NBFC
    lines = sheet["lines"]
    assert lines["revenue"]["value"] == pytest.approx(24546.37)
    assert lines["financing_profit"]["value"] == pytest.approx(8825.09)
    assert lines["financing_margin"]["value"] == pytest.approx(35.95) and "yoy_bps" in lines["financing_margin"]
    assert lines["pat"]["value"] == pytest.approx(6266.2) and lines["pat"]["with_minority"] == pytest.approx(6366.57)
    assert "ebitda" not in lines
    assert "Financing margin: 35.95%" in fs.block(sheet)


def test_nbfc_template_outside_finance_is_a_company():
    # results_table's rule: an NBFC-template filer in a known industry that is not financial services takes the corporate rows
    d, period = dossier_of("nse_bajfin_q2fy27_cons.xml", "500034", industry="Consumer Services > Restaurants")
    sheet = fs.fact_sheet(d, period, lenders=True)
    assert sheet["family"] == sv.CORPORATE and sheet["lines"]["ebitda"]["value"] == pytest.approx(17426.82)
    d, period = dossier_of("nse_bajfin_q2fy27_cons.xml", "500034", industry="Financial Services > Insurance > Life Insurance")
    assert set(fs.fact_sheet(d, period, lenders=True)["lines"]) == {"pat"}


def test_insurer_sheet_is_profit_only():
    d, period = dossier_of("nse_hdfclife_q2fy27_cons.xml", "540777")
    sheet = fs.fact_sheet(d, period, lenders=True)
    assert sheet["family"] == sv.INSURER and set(sheet["lines"]) == {"pat"}
    assert sheet["lines"]["pat"]["value"] == pytest.approx(521.6) and sheet["lines"]["pat"]["yoy_pct"] == 25.0


# --- the card's table ------------------------------------------------------------------------------------------------

def test_bank_sheet_into_a_bank_table():
    d, period = dossier_of("nse_hdfcbank_q2fy27_cons.xml", "500180")
    sheet = fs.fact_sheet(d, period, lenders=True)
    table = {"lens": "bank", "period": "Q2FY27", "interest_earned": {"value": 95000.0}, "nii": {"value": 44000.0},
             "ppop": {"value": 30000.0}, "gnpa_pct": {"value": 1.24}, "pbt": {"value": 27825.48}, "pat": {"value": 20000.0}}
    notes = fs.apply_to_results(table, sheet)
    assert table["interest_earned"]["value"] == pytest.approx(95131.63) and table["nii"]["value"] == pytest.approx(44464.2)
    assert table["pat"]["value"] == pytest.approx(20700.03)
    assert table["ppop"] == {"value": 30000.0} and table["gnpa_pct"] == {"value": 1.24}     # rows the sheet does not hold stay
    assert {n["line"] for n in notes} == {"interest_earned", "nii", "pbt", "pat"}     # the table's own row names; PBT gains its year-ago


def test_a_sheet_goes_only_into_its_own_kind_of_table():
    d, period = dossier_of("nse_hdfcbank_q2fy27_cons.xml", "500180")
    bank = fs.fact_sheet(d, period, lenders=True)
    company = {"lens": "company", "period": "Q2FY27", "revenue": {"value": 1.0}, "pat": {"value": 2.0}}
    assert fs.apply_to_results(company, bank) == [] and company["revenue"] == {"value": 1.0}
    d, period = dossier_of("nse_bajfin_q2fy27_cons.xml", "500034")
    nbfc = fs.fact_sheet(d, period, lenders=True)
    lines = [{"key": "revenue", "label": "Revenue", "unit": "cr"}, {"key": "ebitda", "label": "Operating EBITDA (calculated)", "unit": "cr"},
             {"key": "ebitda_filing", "label": "EBITDA (Filing)", "unit": "cr"},
             {"key": "ebitda_margin", "label": "EBITDA margin", "unit": "pct"}, {"key": "pat", "label": "PAT", "unit": "cr"}]
    table = {"lens": "company", "period": "Q2FY27", "revenue": {"value": 1.0}, "ebitda": {"value": 9.0}, "ebitda_filing": {"value": 8.0},
             "ebitda_margin": {"value": 50.0}, "pat": {"value": 2.0}, "lines": lines}
    notes = fs.apply_to_results(table, nbfc)
    assert table["revenue"]["value"] == pytest.approx(24546.37) and table["pat"]["value"] == pytest.approx(6266.2)
    # owner, 31 Oct 2026: an NBFC card shows its financing profit and margin where a company shows EBITDA
    assert [x["key"] for x in table["lines"]] == ["revenue", "financing_profit", "financing_margin", "pat"]
    assert [x["label"] for x in table["lines"]][1:3] == ["Financing profit", "Financing margin"]
    assert table["financing_profit"]["value"] == pytest.approx(8825.09) and table["financing_margin"]["value"] == pytest.approx(35.95)
    assert not {"ebitda", "ebitda_margin", "ebitda_filing"} & set(table)
    assert {n["line"] for n in notes} >= {"ebitda", "ebitda_filing", "ebitda_margin", "financing_profit"}
    # a table with no lines list (an old card) still gets the rows, and a company sheet never swaps anything
    bare = {"lens": "company", "period": "Q2FY27", "revenue": {"value": 1.0}, "ebitda": {"value": 9.0}, "pat": {"value": 2.0}}
    fs.apply_to_results(bare, nbfc)
    assert "ebitda" not in bare and bare["financing_profit"]["value"] == pytest.approx(8825.09)
    d2, period2 = dossier_of("nse_bajfin_q2fy27_cons.xml", "500034", industry="Consumer Services > Restaurants")
    as_company = fs.fact_sheet(d2, period2, lenders=True)
    kept = {"lens": "company", "period": "Q2FY27", "revenue": {"value": 1.0}, "ebitda": {"value": 9.0}, "pat": {"value": 2.0}}
    fs.apply_to_results(kept, as_company)
    assert kept["ebitda"]["value"] == pytest.approx(17426.82) and "financing_profit" not in kept
    d, period = dossier_of("nse_hdfclife_q2fy27_cons.xml", "540777")
    insurer = fs.fact_sheet(d, period, lenders=True)
    table = {"lens": "insurer", "period": "Q2FY27", "gross_premium": {"value": 9000.0}, "pat": {"value": 500.0}}
    fs.apply_to_results(table, insurer)
    assert table["pat"]["value"] == pytest.approx(521.6) and table["gross_premium"] == {"value": 9000.0}


# --- the card text -----------------------------------------------------------------------------------------------------

def test_bank_words_in_the_text_check():
    d, period = dossier_of("nse_hdfcbank_q2fy27_cons.xml", "500180")
    sheet = fs.fact_sheet(d, period, lenders=True)
    assert fs.disagreements("Net interest income rose 25% YoY to ₹44,464 Cr.", sheet) == []
    assert fs.disagreements("NII grew to ₹44,464.20 Cr.", sheet) == []
    assert fs.disagreements("Net interest income rose 31% YoY to ₹44,464 Cr.", sheet)        # the change is 25.0%
    assert fs.disagreements("Interest earned was ₹91,000 Cr.", sheet)                         # interest earned is 95,131.63
    assert fs.disagreements("Interest income on advances rose to ₹71,000 Cr.", sheet) == []   # one part of it: not judged
    # a bank's operating profit (pre-provision) and total income (with other income) are not the sheet's lines: not judged
    assert fs.disagreements("Operating profit was ₹31,000 Cr.", sheet) == []
    assert fs.disagreements("Total income was ₹129,358 Cr.", sheet) == []
    assert fs.disagreements("Net profit was ₹20,700 Cr.", sheet) == []
    assert fs.disagreements("Net profit was ₹19,000 Cr.", sheet)


def test_insurer_text_check_judges_profit_only():
    d, period = dossier_of("nse_hdfclife_q2fy27_cons.xml", "540777")
    sheet = fs.fact_sheet(d, period, lenders=True)
    assert fs.disagreements("Net premium income was ₹9,999 Cr.", sheet) == []
    assert fs.disagreements("PAT was ₹600 Cr.", sheet)
    assert fs.disagreements("PAT was ₹521.6 Cr.", sheet) == []


def test_switch_reads_the_setting(monkeypatch):
    d, period = dossier_of("nse_hdfcbank_q2fy27_cons.xml", "500180")
    monkeypatch.setenv("CARD_FACT_SHEET_LENDERS", "1")
    assert fs.fact_sheet(d, period)["family"] == sv.BANK
    monkeypatch.setenv("CARD_FACT_SHEET_LENDERS", "0")
    assert fs.fact_sheet(d, period) is None


def test_live_path_keeps_the_industry(monkeypatch):
    # for_filing reads memory with the filing's own file put in: the company's industry must come along, or an NBFC-template
    # restaurant is built as an NBFC (independent review of #300)
    monkeypatch.setenv("CARD_FACT_SHEET_LENDERS", "1")
    raw = (FIX / "nse_bajfin_q2fy27_cons.xml").read_bytes()
    plain = fs.for_filing({"industry": "Consumer Services > Restaurants"}, raw, "500034", "https://x/a.xml", "nse-1",
                          "2026-10-20", "2026-10-20T10:00:00Z")
    life = fs.for_filing({"industry": "Financial Services > Insurance > Life Insurance"}, raw, "500034", "https://x/a.xml",
                         "nse-1", "2026-10-20", "2026-10-20T10:00:00Z")
    assert plain["family"] == sv.CORPORATE and life["family"] == sv.INSURER


def test_nbfc_sheet_into_a_bank_table_fills_pbt_and_profit_only():
    # most NBFC cards carry the bank table (live feed, 31 Oct 2026)
    d, period = dossier_of("nse_bajfin_q2fy27_cons.xml", "500034")
    nbfc = fs.fact_sheet(d, period, lenders=True)
    table = {"lens": "bank", "period": "Q2FY27", "interest_earned": {"value": 20000.0}, "nii": {"value": 11000.0},
             "pbt": {"value": 8000.0}, "pat": {"value": 6000.0}, "lines": [{"key": "interest_earned"}, {"key": "nii"}, {"key": "pat"}]}
    fs.apply_to_results(table, nbfc)
    assert table["interest_earned"] == {"value": 20000.0} and table["nii"] == {"value": 11000.0}
    assert table["pbt"]["value"] == pytest.approx(8537.2) and table["pat"]["value"] == pytest.approx(6266.2)
    assert "financing_profit" not in table and table["lines"] == [{"key": "interest_earned"}, {"key": "nii"}, {"key": "pat"}]
