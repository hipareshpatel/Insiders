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
    assert statements.remember(d, _doc("nse_dolphin_q4fy24_cons.xml"), "n1", AS_OF, AT) == 4
    by = {e["table"]: e for e in d["statements"]}
    assert set(by) == {"quarters", "balance", "annual", "cash_flow"}
    assert (by["annual"]["period"], by["cash_flow"]["period"], by["balance"]["period"]) == ("FY24", "FY24", "Q4FY24")
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


def _shifted(doc, months_back):
    """The same file with every date moved back: a December-year company's December file from a March company's March one."""
    import copy
    from datetime import date

    def last(y, m):
        return (date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)).day

    def back(iso):
        y, m, d = (int(x) for x in iso.split("-"))
        ny, nm = (y, m - months_back) if m > months_back else (y - 1, m - months_back + 12)
        return date(ny, nm, last(ny, nm) if d == last(y, m) else d).isoformat()   # a month end stays a month end

    out = copy.deepcopy(doc)
    for c in out["contexts"].values():
        for k in ("s", "e", "i"):
            if c.get(k):
                c[k] = back(c[k])
    return out


def test_a_december_year_end_file_writes_its_year_as_YE_and_a_march_company_s_december_file_none():
    # 1 Nov 2026: the live run wrote a year only from a March file, so VBL's or ABB's December year waited for the rebuild
    dec = _shifted(_doc("nse_dolphin_q4fy24_cons.xml"), 3)
    dec["period"] = dec["file_period"] = "Q3FY24"
    d = {}
    assert statements.remember(d, dec, "n1", AS_OF, AT) == 4
    by = {e["table"]: e["period"] for e in d["statements"]}
    assert by == {"quarters": "Q3FY24", "balance": "Q3FY24", "annual": "YE:2023-12", "cash_flow": "YE:2023-12"}
    # a March company's December file: nine months to December, no twelve, so no year
    nine = _shifted(_doc("nse_dolphin_q4fy24_cons.xml"), 3)
    nine["period"] = "Q3FY24"
    for c in nine["contexts"].values():
        if c.get("m") == 12:
            c["m"], c["s"] = 9, "2023-04-01"
    d = {}
    statements.remember(d, nine, "n1", AS_OF, AT)
    assert not {"annual", "cash_flow"} & {e["table"] for e in d["statements"]}


def test_a_live_ye_year_never_overwrites_the_rebuilt_one():
    dec = _shifted(_doc("nse_dolphin_q4fy24_cons.xml"), 3)
    dec["period"] = "Q3FY24"
    kept = {"period": "YE:2023-12", "basis": "CONSOLIDATED", "table": "annual", "rows": {"Sales": 1.0},
            "lab": {"from": "stored facts"}}
    d = {"statements": [kept]}
    statements.remember(d, dec, "n1", AS_OF, AT)
    assert [e for e in d["statements"] if e["period"] == "YE:2023-12" and e["table"] == "annual"] == [kept]
    fresh: dict = {}   # with no rebuilt year, the live file writes it
    statements.remember(fresh, dec, "n1", AS_OF, AT)
    assert [e["source_news_id"] for e in fresh["statements"] if (e["period"], e["table"]) == ("YE:2023-12", "annual")] == ["n1"]


def test_a_revised_file_replaces_the_same_period_basis_and_table_and_nothing_else():
    d = {"statements": [{"period": "Q3FY24", "basis": "CONSOLIDATED", "table": "quarters", "rows": {"Sales": 1.0}}]}
    statements.remember(d, _doc("nse_dolphin_q4fy24_cons.xml"), "n1", AS_OF, AT)
    statements.remember(d, _doc("nse_dolphin_q4fy24_cons.xml"), "n9", AS_OF, AT)
    keys = [(e["period"], e["table"], e.get("source_news_id")) for e in d["statements"]]
    assert ("Q3FY24", "quarters", None) in keys and len(keys) == 5
    assert {k[2] for k in keys if k[0] in ("Q4FY24", "FY24")} == {"n9"}


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


def test_a_results_file_the_card_sets_aside_still_keeps_its_facts(settings):
    """1 Nov 2026: a file whose figures are not in the PDF text is set aside by the card, and its facts copy was never written (1,414
    raw files with no facts copy, 10 of them Q2FY27); the copy is now kept when the file is downloaded."""
    now = now_ist() - timedelta(minutes=30)
    filing = _filing("n-aside", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    text = "An ECL note for the quarter ended 30.09.2026 with no statement in it. Provision 77.00."
    day = now.date()
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf(text), "https://bse.invalid/co.xml": results_xml()},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)]})
    pipeline.bse.archive = {"999001": [XbrlLink("Q2FY27", "CONSOLIDATED", "https://bse.invalid/co.xml", f"{day}T18:05:00")]}
    pipeline.run("live", time_budget_s=60)
    assert sink.get_object(xbrl_facts.key(filing.scrip_code, "Q2FY27", "CONSOLIDATED")), "the set-aside file's facts are kept"


def test_keep_never_raises_and_skips_a_file_with_no_results():
    assert xbrl_facts.keep(None, b"not xml", "x", "u") is False


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


def test_the_standalone_file_beside_a_consolidated_one_keeps_its_statements_too(settings):
    """Screener's rules hold for both bases (standalone 97.5% of quarter rows exact, 29 Oct): the standalone file read beside
    the consolidated one keeps its rows for the company page's standalone view; the card stays consolidated."""
    now = now_ist() - timedelta(minutes=30)
    filing = _filing("n-both", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    text = ("Statement of unaudited consolidated financial results for the quarter ended 30.09.2026 (Rs. in lakhs). "
            "Revenue from operations 12,000.00 9,091.00. Net profit 1,500.00.")
    day = now.date()
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf(text), "https://bse.invalid/co.xml": results_xml(),
                                                      "https://bse.invalid/sa.xml": results_xml("Standalone")},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)]})
    pipeline.bse.archive = {"999001": [XbrlLink("Q2FY27", "CONSOLIDATED", "https://bse.invalid/co.xml", f"{day}T18:05:00"),
                                       XbrlLink("Q2FY27", "STANDALONE", "https://bse.invalid/sa.xml", f"{day}T18:00:00")]}
    pipeline.run("live", time_budget_s=60)
    bases = {e["basis"] for e in sink.get_dossier(filing.scrip_code).get("statements", []) if e["period"] == "Q2FY27"}
    assert bases == {"CONSOLIDATED", "STANDALONE"}


def test_the_profit_line_rules_are_applied_where_entries_are_written_and_the_backfill_builds_them():
    from bse_intel import screener_view as sv
    rows = {"Net Profit": 182.37, "Net Profit (owners)": 87.95, "Minority share": 3.13, "Profit before tax": 230.1, "Tax": 48.91}
    assert sv.corrected_pl(rows, sv.CORPORATE)["Net Profit (owners)"] == 179.24
    assert sv.corrected_pl(rows, sv.CORPORATE) is not rows and sv.corrected_pl({"Net Profit": 5.0}, sv.CORPORATE) == {"Net Profit": 5.0}
    ok = {"Net Profit": 100.0, "Net Profit (owners)": 96.9, "Minority share": 3.1}
    assert sv.corrected_pl(ok, sv.CORPORATE) is ok                                   # adds up: untouched
    assert sv.corrected_pl({"Net Profit": 560.0, "Net Profit (owners)": 0.0}, sv.NBFC)["Net Profit (owners)"] == 560.0   # filler, no minority row
    assert sv.corrected_pl({"Net Profit": -138.56, "Profit before tax": 625.0, "Tax": 157.55}, sv.CORPORATE)["Net Profit"] == 467.45
    assert sv.corrected_pl({"Net Profit": -138.56, "Profit before tax": 625.0, "Tax": 157.55}, sv.BANK)["Net Profit"] == -138.56   # only corporate PBT is built to hold it
    from bse_intel import statements
    e = {"table": "quarters", "family": "corporate", "rows": rows}
    assert statements.corrected_entry(e)["rows"]["Net Profit (owners)"] == 179.24 and e["rows"]["Net Profit (owners)"] == 87.95
    assert statements.corrected_entry({"table": "balance", "family": "corporate", "rows": rows}) ["rows"] is rows


def test_remember_stores_the_corrected_profit_lines(monkeypatch):
    from bse_intel import screener_view as sv
    raw = {"Net Profit": 182.37, "Net Profit (owners)": 87.95, "Minority share": 3.13}
    monkeypatch.setattr(statements, "rows_of", lambda doc, source="": [("quarters", {k: sv.Row(v, "") for k, v in raw.items()}, "Q2FY26")])
    d: dict = {}
    assert statements.remember(d, {"period": "Q2FY26", "basis": "CONSOLIDATED", "template": "INDAS"}, "n1", "2025-10-17", "t") == 1
    assert d["statements"][0]["rows"]["Net Profit (owners)"] == 179.24


def test_a_ye_year_sorts_with_the_quarter_that_ends_it_and_is_not_dropped_first():
    assert statements._order("YE:2023-12") == statements._order("Q3FY24")
    assert statements._order("YE:2025-06") == statements._order("Q1FY26")
    old = [{"period": "Q1FY20", "table": "quarters"}] + [{"period": "YE:2025-12", "table": "annual"}] \
        + [{"period": f"Q{q}FY{y}", "table": t} for y in range(21, 31) for q in (1, 2, 3, 4) for t in ("quarters", "balance", "x")]
    kept = statements.keep_latest(old)
    assert {"period": "YE:2025-12", "table": "annual"} in kept and {"period": "Q1FY20", "table": "quarters"} not in kept
