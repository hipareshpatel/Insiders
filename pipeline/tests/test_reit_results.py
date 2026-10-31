"""REIT and InvIT results on the Results page (reit_results.py): the quarter read from NSE's XBRL by screener's rules, comparatives from the
trust's earlier files, the stored copy, the file cap, and the prune guard."""
import json

import pytest

from bse_intel import reit_results as rr
from bse_intel.nse import FileCapReached

NS = ('xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-capmkt="http://www.sebi.gov.in/xbrl/2026-08-31/in-capmkt" '
      'xmlns:xbrldi="http://xbrl.org/2006/xbrldi"')


def xbrl_doc(start="2026-07-01", end="2026-09-30", revenue=13_026_340_000, expenses=10_422_060_000, finance=4_129_690_000,
             depreciation=3_065_400_000, profit=8_310_140_000, basis="Consolidated", isin="INE041025011", symbol="EMBASSY",
             scrip="542602", owners=True) -> bytes:
    """A file shaped like the real ones (Embassy, Sep 2026): one quarter context and the year to date, text facts, amounts in rupees."""
    num = lambda tag, value, ctx="OneD": f'<in-capmkt:{tag} contextRef="{ctx}" unitRef="INR" decimals="-4">{value}</in-capmkt:{tag}>'
    txt = lambda tag, value: f'<in-capmkt:{tag} contextRef="OneD">{value}</in-capmkt:{tag}>'
    body = [txt("ISIN", isin), txt("Symbol", symbol), txt("ScripCode", scrip), txt("NatureOfReportStandaloneConsolidated", basis),
            num("RevenueFromOperations", revenue), num("RevenueFromOperations", revenue * 2, "FourD"), num("Expenses", expenses),
            num("FinanceCosts", finance), num("DepreciationDepletionAndAmortisationExpense", depreciation),
            num("ProfitLossForPeriod", profit), num("NetDistributableCashFlows", 123, "D_Trust_1")]
    if owners:
        body.append(num("ProfitOrLossAttributableToOwnersOfParent", profit))
    return (f'<?xml version="1.0" encoding="UTF-8"?><xbrli:xbrl {NS}>'
            f'<xbrli:context id="OneD"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity><xbrli:period>'
            f'<xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>'
            f'<xbrli:context id="FourD"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity><xbrli:period>'
            f'<xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>'
            f'<xbrli:context id="D_Trust_1"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier><xbrli:segment>'
            f'<xbrldi:explicitMember dimension="in-capmkt:Axis">in-capmkt:Trust</xbrldi:explicitMember></xbrli:segment></xbrli:entity>'
            f'<xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>'
            f'{"".join(body)}</xbrli:xbrl>').encode()


def row(symbol="EMBASSY", name="Embassy Office Parks REIT", basis="Consolidated", related="Second Quarter", ended="30-Sep-2026",
        broadcast="29-Oct-2026 16:40:43", kind="REITs", file="a.xml", typ="Original"):
    return {"symbol": symbol, "companyName": name, "consNoncons": basis, "relatedTo": related, "periodEnded": ended, "broadcast": broadcast,
            "submissionDate": broadcast, "reitsInvits": kind, "typeOfSubmission": typ, "xbrl": f"https://nsearchives.nseindia.com/corporate/xbrl/{file}"}


def test_a_quarter_is_read_by_screeners_rules_in_rupees_crore():
    got = rr.read(xbrl_doc())
    assert (got["period"], got["basis"], got["isin"], got["symbol"], got["scrip"]) == ("Q2FY27", "CONSOLIDATED", "INE041025011", "EMBASSY", "542602")
    # Embassy Sep 2026: screener shows sales 1,303, operating profit 980 (75%), net profit 831
    assert got["rows"] == {"Net Profit": 831.01, "Net Profit (owners)": 831.01, "Sales": 1302.63, "Operating Profit": 979.94, "OPM %": 75.23}


def test_the_year_to_date_and_the_dimension_contexts_are_not_the_quarter():
    got = rr.read(xbrl_doc(start="2026-04-01", end="2026-06-30"))
    assert got["period"] == "Q1FY27" and got["rows"]["Sales"] == 1302.63   # the three-month context, not the six-month one
    assert rr.read(b"<html>blocked</html>") is None
    assert rr.read(xbrl_doc(start="2026-04-01", end="2026-09-30")) is None  # no three-month period: a half year is not a quarter here


def test_a_file_without_a_profit_line_has_no_quarter_and_standalone_is_told_from_consolidated():
    assert rr.read(xbrl_doc(profit="")) is None
    assert rr.read(xbrl_doc(basis="Standalone"))["basis"] == "STANDALONE"
    assert rr.read(xbrl_doc(basis="Non-Consolidated"))["basis"] == "STANDALONE"
    assert "Net Profit (owners)" not in rr.read(xbrl_doc(owners=False))["rows"]


def test_a_revision_beats_its_original_and_the_newest_comes_first():
    rows = [row(file="orig.xml"), row(file="rev.xml", broadcast="30-Oct-2026 10:00:00", typ="Revision"),
            row(symbol="IRBINVIT", name="IRB InvIT Fund", kind="InvITs", file="irb.xml", broadcast="28-Oct-2026 09:00:00"),
            {**row(file="x"), "xbrl": None}]
    got = rr.pick(rows)
    assert [r["xbrl"].rsplit("/", 1)[-1] for r in got] == ["rev.xml", "irb.xml"]


class Client:
    def __init__(self, rows, files, cap=None):
        self.rows, self.files, self.cap, self.downloads = rows, files, cap, []

    def reit_invit_results(self, day_from=None):
        return self.rows

    def download(self, url):
        if self.cap is not None and len(self.downloads) >= self.cap:
            raise FileCapReached("cap")
        self.downloads.append(url)
        return self.files.get(url.rsplit("/", 1)[-1])


def two_years():
    rows = [row(file="now.xml"), row(file="year.xml", ended="30-Sep-2025", related="Second Quarter", broadcast="10-Nov-2025 12:00:00")]
    files = {"now.xml": xbrl_doc(), "year.xml": xbrl_doc(start="2025-07-01", end="2025-09-30", revenue=11_000_000_000,
                                                         expenses=9_000_000_000, finance=3_000_000_000, depreciation=2_000_000_000, profit=4_000_000_000)}
    return rows, files


def test_a_run_puts_the_trust_and_its_quarters_in_with_changes_from_its_earlier_file(settings):
    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    rows, files = two_years()
    out = rr.run(Client(rows, files), sink, "2026-10-30T23:00:00")
    assert (out["trusts"], out["rows"], out["downloaded"], out["stored"], out["capped"]) == (1, 2, 2, 0, False)
    assert out["per_quarter"] == {"Q2FY26": 1, "Q2FY27": 1}
    company = sink._db.execute("SELECT symbol, company_name, isin, industry FROM companies WHERE scrip_code = '542602'").fetchone()
    assert tuple(company) == ("EMBASSY", "Embassy Office Parks REIT", "INE041025011", "Consumer Discretionary > Realty > Real Estate Investment Trusts (REITs)")
    now = sink._db.execute("SELECT kind, basis, revenue, revenue_prev, revenue_yoy, ebitda, pat, pat_yoy, nfo FROM results_kpi WHERE period = 'Q2FY27'").fetchone()
    assert tuple(now) == ("reit", "CONSOLIDATED", 1302.63, 1100.0, 18.4, 979.94, 831.01, 107.8, 0)
    assert json.loads(sink.kv_get(rr.TRUSTS_KEY)) == ["INE041025011"]


def test_the_second_run_reads_the_stored_files_and_downloads_nothing(settings):
    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    rows, files = two_years()
    rr.run(Client(rows, files), sink, "t1")
    again = Client(rows, files)
    out = rr.run(again, sink, "t2")
    assert again.downloads == [] and out["stored"] == 2 and out["downloaded"] == 0 and out["rows"] == 2


def test_the_file_cap_ends_the_run_early_and_keeps_what_was_read(settings):
    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    rows, files = two_years()
    out = rr.run(Client(rows, files, cap=1), sink, "t")
    assert out["capped"] is True and out["downloaded"] == 1 and out["rows"] == 1   # the newest file only: saved, not lost
    assert sink._db.execute("SELECT count(*) FROM results_kpi").fetchone()[0] == 1


def test_a_quarter_with_no_sales_is_left_out_and_its_stored_row_pruned(settings):
    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    rows = [row(symbol="BAGMANE", name="Bagmane Prime Office REIT", file="q1.xml", ended="30-Jun-2026", related="First Quarter"),
            row(symbol="BAGMANE", name="Bagmane Prime Office REIT", file="shell.xml", ended="31-Mar-2026", related="Fourth Quarter",
                basis="Non-Consolidated", broadcast="20-May-2026 10:00:00")]
    q1 = dict(start="2026-04-01", end="2026-06-30", symbol="BAGMANE", scrip="544758", isin="INE0QS725011")
    files = {"q1.xml": xbrl_doc(**q1), "shell.xml": xbrl_doc(**{**q1, "start": "2026-01-01", "end": "2026-03-31"}, basis="Standalone",
                                                           revenue=0, expenses=400_000, finance=0, depreciation=0, profit=-1_100_000)}
    sink.execute(rr.results_table.STATEMENT, rr.results_table.company_rows("544758", {rr.statements.KEY: [
        {"table": "quarters", "period": "Q4FY26", "basis": "STANDALONE", "family": "reit", "lab": {"by": "file"},
         "rows": {"Net Profit": -0.11, "Sales": 0, "Operating Profit": -0.04}, "source_news_id": None}]}, "t0"))
    out = rr.run(Client(rows, files), sink, "t")
    assert (out["no_sales"], out["rows"], out["per_quarter"]) == (1, 1, {"Q1FY27": 1})
    assert [r[0] for r in sink._db.execute("SELECT period FROM results_kpi WHERE scrip_code = '544758'")] == ["Q1FY27"]


def test_an_unreadable_file_is_counted_and_a_trust_without_an_isin_is_left_out(settings):
    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    rows = [row(file="bad.xml"), row(symbol="NOISIN", name="No Isin Trust", file="noisin.xml", broadcast="28-Oct-2026 09:00:00")]
    files = {"bad.xml": b"<html>blocked</html>", "noisin.xml": xbrl_doc(symbol="NOISIN", isin="")}
    out = rr.run(Client(rows, files), sink, "t")
    assert out["no_quarter"] == 1 and out["trusts"] == 0 and out["rows"] == 0


def test_trusts_not_on_bse_are_keyed_by_their_nse_symbol_and_the_shared_000000_rows_go(settings):
    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    # measured 31 Oct 2026: six trusts not on BSE all say ScripCode 000000; keyed by it, each overwrote the others' quarters
    sink.execute(rr.results_table.STATEMENT, rr.results_table.company_rows("000000", {rr.statements.KEY: [
        {"table": "quarters", "period": "Q2FY27", "basis": "CONSOLIDATED", "family": "invit", "lab": {"by": "file"},
         "rows": {"Net Profit": 1.0, "Sales": 2.0}, "source_news_id": None}]}, "t0"))
    rows = [row(symbol="TVSINVIT", name="TVS Infrastructure Trust", file="tvs.xml", kind="InvITs"),
            row(symbol="NDRINVIT", name="NDR InvIT Trust", file="ndr.xml", kind="InvITs"),
            row(symbol="NOCODE", name="No Code Trust", file="nocode.xml", kind="InvITs")]
    files = {"tvs.xml": xbrl_doc(scrip="000000", symbol="TVSINVIT", isin="INE1JNC23012", revenue=1_000_000_000),
             "ndr.xml": xbrl_doc(scrip="000000", symbol="NDRINVIT", isin="INE0Q7Q23015", revenue=3_000_000_000),
             "nocode.xml": xbrl_doc(scrip="", symbol="NOCODE", isin="INE000000001")}
    out = rr.run(Client(rows, files), sink, "t")
    assert (out["trusts"], out["rows"]) == (3, 3)
    got = dict(sink._db.execute("SELECT scrip_code, revenue FROM results_kpi").fetchall())
    assert got == {"NSE:TVSINVIT": 100.0, "NSE:NDRINVIT": 300.0, "NSE:NOCODE": 1302.63}   # each trust its own figures; nothing under 000000
    assert sink._db.execute("SELECT symbol FROM companies WHERE scrip_code = 'NSE:TVSINVIT'").fetchone()[0] == "TVSINVIT"


def test_prune_companies_keeps_a_trust_that_is_not_on_nses_equity_list(settings):
    from bse_intel import prune_companies
    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    rows, files = two_years()
    rr.run(Client(rows, files), sink, "t")
    equities = [type("E", (), {"isin": f"INE{i:09d}", "symbol": f"S{i}"})() for i in range(prune_companies.MIN_NSE_ROWS + 5)]
    sme = [type("E", (), {"isin": f"INF{i:09d}", "symbol": f"M{i}"})() for i in range(prune_companies.MIN_SME_ROWS + 5)]
    plan = prune_companies.plan(sink, equities, sme)
    assert "542602" not in {c["scrip_code"] for c in plan["remove"] + plan["has_cards"]}
    sink.kv_set(rr.TRUSTS_KEY, "[]", "t")
    assert "542602" in {c["scrip_code"] for c in prune_companies.plan(sink, equities, sme)["remove"]}   # without the guard it would be removed
