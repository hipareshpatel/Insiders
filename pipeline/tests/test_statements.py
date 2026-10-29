"""statements.py (owner, 30 Oct 2026: "live results should get stored as per screener rules"): a live results file's rows by the
screener recipes, kept in the dossier when the filing is read, and its facts kept in R2."""
import json
from datetime import timedelta
from pathlib import Path

from test_pipeline import PASS2, _filing, _pdf, build
from test_xbrl import results_xml

from bse_intel import statements, xbrl_facts
from bse_intel.bse import XbrlLink
from bse_intel.timeutil import now_ist

FIXTURES = Path(__file__).parent / "fixtures"
AS_OF, AT = "2026-10-30T18:00:00+05:30", "2026-10-30T18:01:00+05:30"


def _doc(name):
    return xbrl_facts.parse_facts((FIXTURES / name).read_bytes(), "x", "u")


def test_a_march_quarter_file_gives_its_pl_balance_sheet_and_years_cash_flow():
    d = {}
    assert statements.remember(d, _doc("nse_dolphin_q4fy24_cons.xml"), "n1", AS_OF, AT) == 3
    by = {e["table"]: e for e in d["statements"]}
    assert set(by) == {"quarters", "balance", "cash_flow"}
    q = by["quarters"]
    assert (q["period"], q["basis"], q["source_news_id"], q["lab"]["by"], q["lab"]["rules"]) == \
        ("Q4FY24", "CONSOLIDATED", "n1", "file", "screener_view")
    assert {"Sales", "Expenses", "Operating Profit", "Net Profit"} <= set(q["rows"])
    assert {"Cash from Operating Activity", "Net Cash Flow"} <= set(by["cash_flow"]["rows"])


def test_a_september_quarter_gives_the_half_years_balance_sheet_and_a_bank_its_own_recipe():
    d = {}
    assert statements.remember(d, _doc("nse_hdfcbank_q2fy27_cons.xml"), "n2", AS_OF, AT) == 2
    by = {e["table"]: e for e in d["statements"]}
    assert set(by) == {"quarters", "balance"} and by["quarters"]["family"] == statements.sv.BANK
    assert "Revenue" in by["quarters"]["rows"] and "Sales" not in by["quarters"]["rows"]


def test_a_revised_file_replaces_the_same_period_basis_and_table_and_nothing_else():
    d = {"statements": [{"period": "Q3FY24", "basis": "CONSOLIDATED", "table": "quarters", "rows": {"Sales": 1.0}}]}
    statements.remember(d, _doc("nse_dolphin_q4fy24_cons.xml"), "n1", AS_OF, AT)
    statements.remember(d, _doc("nse_dolphin_q4fy24_cons.xml"), "n9", AS_OF, AT)
    keys = [(e["period"], e["table"], e.get("source_news_id")) for e in d["statements"]]
    assert ("Q3FY24", "quarters", None) in keys and len(keys) == 4
    assert {k[2] for k in keys if k[0] == "Q4FY24"} == {"n9"}


def test_bad_bytes_never_raise_and_write_nothing():
    d = {}
    assert statements.from_file(None, d, b"not xml", "x", "u", "n1", AS_OF, AT) == 0 and d == {}


def test_the_live_path_keeps_the_rows_and_the_facts(settings):
    now = now_ist() - timedelta(minutes=30)
    filing = _filing("n-st", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    text = ("Statement of unaudited consolidated financial results for the quarter ended 30.09.2026 (Rs. in lakhs). "
            "Revenue from operations 12,000.00 9,091.00. Net profit 1,500.00.")
    day = now.date()
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf(text), "https://bse.invalid/co.xml": results_xml()},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)]})
    pipeline.bse.archive = {"999001": [XbrlLink("Q2FY27", "CONSOLIDATED", "https://bse.invalid/co.xml", f"{day}T18:05:00")]}
    pipeline.run("live", time_budget_s=60)
    rows = [e for e in sink.get_dossier(filing.scrip_code).get("statements", []) if e["period"] == "Q2FY27"]
    assert {e["table"] for e in rows} >= {"quarters"} and all(e["source_news_id"] == "n-st" for e in rows)
    assert sink.get_object(xbrl_facts.key(filing.scrip_code, "Q2FY27", "CONSOLIDATED")), "the file's facts are kept"


def test_a_concurrent_writer_s_statements_are_kept_and_the_newest_periods_win():
    from bse_intel.dossier import keep_concurrent_writes

    def e(period, table="quarters", src="n1"):
        return {"period": period, "basis": "CONSOLIDATED", "table": table, "rows": {"Sales": 1.0}, "source_news_id": src}

    read = {"statements": [e("Q1FY27")]}
    mine = {"statements": [e("Q1FY27"), e("Q2FY27", src="mine")]}
    fresh = {"statements": [e("Q1FY27"), e("Q2FY27", "balance", src="theirs")]}   # the other filing of the run
    keep_concurrent_writes(mine, read, fresh)
    assert {(x["period"], x["table"]) for x in mine["statements"]} == {("Q1FY27", "quarters"), ("Q2FY27", "quarters"),
                                                                      ("Q2FY27", "balance")}
    many = [e(f"Q{q}FY{y}") for y in range(20, 30) for q in range(1, 5)] * 4
    many = [dict(x, table=t) for x, t in zip(many, ["quarters", "balance", "cash_flow", "x"] * 40)]
    kept = statements.keep_latest(many)
    assert len(kept) == statements.MAX_ENTRIES and kept[-1]["period"] == "Q4FY29"
