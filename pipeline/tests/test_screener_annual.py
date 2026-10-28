"""Annual reports in the screener check (28 Oct 2026): the annual-report XBRL (the MCA Ind AS taxonomy, Ind AS files only, never a BRSR
file) is kept by ``xbrl-facts --annual`` as ``annual-<FY>-<basis>``, and screener's annual columns are worked out from it by screener's
own formulas, falling back on the Q4 integrated file's 12-month figures; every pair records which. Numbers: ITC FY26 consolidated,
screener's Data Sheet equals the file to the paisa (Sales 89,913.33 - 11,044.93 = 78,868.40, Power and Fuel 947.71, Employee cost
6,781.50; docs/audit/screener-five-2026-10-28.md and the lead's measurement of 28 Oct)."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from bse_intel import cli, nse as nse_module, xbrl_facts, xbrl_store
from bse_intel import screener_crosscheck as sc
from bse_intel.file_cap import files
from bse_intel.nse import AnnualReportFiling, NseClient, parse_annual_report_rows
from bse_intel.screener_fill import parse_full
from bse_intel.sinks.platform import PlatformSink

CR = 10_000_000

# an annual report's instance on the MCA Ind AS taxonomy (prefix ind-as, cost-audit tags in-ca): the year is a 12-month duration (365
# days here), the previous year beside it, the balance sheet an instant at the year end; the basis is a text fact
ITC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:ind-as="http://www.mca.gov.in/XBRL/2022-12-31/ind-as"
 xmlns:in-ca="http://www.mca.gov.in/XBRL/2022-12-31/in-ca" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:iso4217="http://www.xbrl.org/2003/iso4217">
<xbrli:context id="D"><xbrli:entity><xbrli:identifier scheme="http://www.mca.gov.in/">L16005WB1910PLC001985</xbrli:identifier></xbrli:entity>
 <xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="P"><xbrli:entity><xbrli:identifier scheme="http://www.mca.gov.in/">L16005WB1910PLC001985</xbrli:identifier></xbrli:entity>
 <xbrli:period><xbrli:startDate>2024-04-01</xbrli:startDate><xbrli:endDate>2025-03-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="I"><xbrli:entity><xbrli:identifier scheme="http://www.mca.gov.in/">L16005WB1910PLC001985</xbrli:identifier></xbrli:entity>
 <xbrli:period><xbrli:instant>2026-03-31</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="M1"><xbrli:entity><xbrli:identifier scheme="http://www.mca.gov.in/">L16005WB1910PLC001985</xbrli:identifier></xbrli:entity>
 <xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period>
 <xbrli:scenario><xbrldi:typedMember dimension="ind-as:RelatedPartyAxis"><ind-as:RelatedPartyDomain>Party1</ind-as:RelatedPartyDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
<xbrli:unit id="INRPerShare"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unitNumerator>
 <xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<ind-as:NatureOfReportStandaloneConsolidated contextRef="D">Consolidated</ind-as:NatureOfReportStandaloneConsolidated>
<ind-as:RevenueFromOperations contextRef="D" unitRef="INR" decimals="-5">899133300000.00</ind-as:RevenueFromOperations>
<ind-as:RevenueFromOperations contextRef="P" unitRef="INR" decimals="-5">810000000000.00</ind-as:RevenueFromOperations>
<ind-as:ExciseDuty contextRef="D" unitRef="INR" decimals="-5">110449300000.00</ind-as:ExciseDuty>
<ind-as:PowerAndFuel contextRef="D" unitRef="INR" decimals="-5">9477100000.00</ind-as:PowerAndFuel>
<ind-as:EmployeeBenefitExpense contextRef="D" unitRef="INR" decimals="-5">67815000000.00</ind-as:EmployeeBenefitExpense>
<ind-as:Assets contextRef="I" unitRef="INR" decimals="-5">900000000000.00</ind-as:Assets>
<in-ca:CostOfMaterialsConsumedCostAudit contextRef="D" unitRef="INR" decimals="-5">350983400000.00</in-ca:CostOfMaterialsConsumedCostAudit>
<ind-as:DescriptionOfRelatedParty contextRef="M1">A subsidiary</ind-as:DescriptionOfRelatedParty>
<ind-as:RemunerationToDirectors contextRef="M1" unitRef="INR" decimals="-5">1000000.00</ind-as:RemunerationToDirectors>
</xbrli:xbrl>""".encode()


class FakeSink(PlatformSink):
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_object(self, key, body, content_type="application/json"):
        self.objects[key] = body

    def get_object(self, key):
        return self.objects.get(key)

    def list_objects(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))

    def query(self, name, params):
        return []


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for name in ("FILE_CAP", "FILE_CAP_SHARDS", "FILE_CAP_USED", "FILE_CAP_MARKER_DIR", "GITHUB_ENV", "XBRL_STORE_MAX_MB"):
        monkeypatch.delenv(name, raising=False)
    files.reset()
    xbrl_store.reset()
    yield
    files.reset()
    xbrl_store.reset()


# --- the facts of an annual report ----------------------------------------------------------------------------------------------

def test_an_annual_report_is_kept_with_every_fact_and_found_by_its_year_duration_and_year_end_instant():
    doc = xbrl_facts.parse_annual_facts(ITC_XML, "500875", "https://nsearchives.nseindia.com/corporate/xbrl/AR_XBRL_ITC.xml")
    assert doc["kind"] == "annual" and doc["fy"] == "FY26" and doc["basis"] == "CONSOLIDATED" and doc["year_end"] == "2026-03-31"
    assert doc["n_facts"] == len(doc["facts"]) == 10 and doc["template"] == "MCA-INDAS"
    assert doc["contexts"]["D"] == {"s": "2025-04-01", "e": "2026-03-31", "m": 12} and doc["contexts"]["I"] == {"i": "2026-03-31"}
    assert doc["contexts"]["M1"]["d"] == {"ind-as:RelatedPartyAxis": "Party1"}                          # a typed member, kept
    facts = xbrl_facts.Facts(doc)
    end = date(2026, 3, 31)
    assert facts.kind == "annual" and facts.source == "annual_report_xbrl"
    assert facts.cr("RevenueFromOperations", end=end, months=12) == pytest.approx(89913.33)              # the year, not the previous one
    assert facts.cr("RevenueFromOperations", end=date(2025, 3, 31), months=12) == pytest.approx(81000.0)
    assert facts.cr("Assets", instant=end) == pytest.approx(90000.0)
    # the elements the integrated filing has no tag for are kept (screener's Data Sheet rows)
    assert facts.cr("PowerAndFuel", end=end, months=12) == pytest.approx(947.71)
    assert facts.cr("EmployeeBenefitExpense", end=end, months=12) == pytest.approx(6781.50)
    assert facts.cr("CostOfMaterialsConsumedCostAudit", end=end, months=12) == pytest.approx(35098.34)   # the cost-audit (in-ca) tag
    body = xbrl_facts.dumps(doc)
    assert xbrl_facts.loads(body) == doc and body == xbrl_facts.dumps(xbrl_facts.loads(body))
    assert xbrl_facts.annual_key("500875", "FY26", "CONSOLIDATED") == "raw/xbrl-facts/500875/annual-FY26-consolidated.json.gz"
    sink = FakeSink()
    xbrl_facts.save_annual(sink, "500875", "FY26", "CONSOLIDATED", doc)
    assert xbrl_facts.load_annual(sink, "500875", "FY26", "CONSOLIDATED").doc == doc and xbrl_facts.load_annual(sink, "500875", "FY25", "CONSOLIDATED") is None


def test_the_fiscal_year_labels_and_files_that_are_not_annual_reports():
    assert xbrl_facts.fy_of(date(2026, 3, 31)) == "FY26" and xbrl_facts.fy_of(date(2025, 9, 30)) == "FY26-09"
    assert xbrl_facts.parse_annual_facts(b"not xml") is None
    assert xbrl_facts.parse_annual_facts(b"<xbrli:xbrl xmlns:xbrli='http://www.xbrl.org/2003/instance'/>") is None
    # a file with no revenue, profit or assets (a sustainability report) is no annual report's statements
    brsr = ITC_XML.replace(b"RevenueFromOperations", b"EnergyConsumed").replace(b"Assets", b"WaterUsed")
    assert xbrl_facts.parse_annual_facts(brsr, "1") is None


def test_only_ind_as_files_never_a_brsr_file():
    assert xbrl_facts.is_ind_as("IND-AS") and xbrl_facts.is_ind_as("Ind AS")
    assert not xbrl_facts.is_ind_as("BRSR") and not xbrl_facts.is_ind_as("") and not xbrl_facts.is_ind_as("IND-AS BRSR")
    rows = [{"fromYr": "2025", "toYr": "2026", "report_type": "IND-AS", "submission_type": "Consolidated",
             "broadcast_dttm": "10-JUL-2026 10:00:00", "fileName": "https://nsearchives.nseindia.com/corporate/xbrl/AR_XBRL_ITC_1.xml"},
            # filed later for the same year and basis: it must not displace the Ind AS file
            {"fromYr": "2025", "toYr": "2026", "report_type": "BRSR", "submission_type": "Consolidated",
             "broadcast_dttm": "20-JUL-2026 10:00:00", "fileName": "https://nsearchives.nseindia.com/corporate/xbrl/BRSR_ITC_2.xml"}]
    listing = parse_annual_report_rows(rows)
    assert [(r.report_type, r.basis, r.to_year) for r in listing] == [("IND-AS", "CONSOLIDATED", 2026)]


# --- the command: the list is one request a company, a file only with --download -------------------------------------------------

def row(to_year, basis="CONSOLIDATED", kind="IND-AS", name=None):
    return AnnualReportFiling(from_year=to_year - 1, to_year=to_year, basis=basis, filed_at="2026-07-10T10:00:00+05:30",
                              xbrl_url=f"https://nsearchives.nseindia.com/corporate/xbrl/{name or f'AR_{to_year}_{basis}_{kind}'}.xml",
                              report_type=kind)


class AnnualNse(NseClient):
    """The real client's download path (pacing hooks, file counting) over a mock transport; the annual-report list is a stub."""

    def __init__(self, listing, hits):
        def handler(request):
            hits.append(str(request.url))
            return httpx.Response(200, content=ITC_XML)
        super().__init__(transport=httpx.MockTransport(handler), sleep=lambda s: None, retries=1, pause=(0, 0))
        self._warmed = True
        self.listing, self.lists = listing, []

    def annual_reports(self, symbol):
        self.lists.append(symbol)
        return self.listing


def sink_for():
    sink = FakeSink()
    sink.objects["memory/1.json"] = json.dumps({"financial_metrics": []}).encode()
    return sink


def test_annual_reports_list_one_request_a_company_and_download_only_with_the_flag_under_the_file_cap():
    listing = [row(2026), row(2026, "STANDALONE"), row(2026, kind="BRSR"), row(2025), row(2024), row(2023)]
    sink, hits = sink_for(), []
    nse = AnnualNse(listing, hits)
    out = xbrl_facts.run(sink, [("1", "ITC")], client=nse, annual=True)                       # --annual without --download
    assert nse.lists == ["ITC"] and hits == [] and files.used == 0                             # a list, no file
    assert out["annual_lists"] == 1 and out["annual_missing"] == 4 and out["annual_saved"] == 0 and out["annual_not_ind_as"] == 1
    years = {r["period"] for r in out["missing_rows"]}
    assert years == {"annual-FY26", "annual-FY25", "annual-FY24"}                              # the latest 3 years, Ind AS only
    out = xbrl_facts.run(sink, [("1", "ITC")], client=nse, annual=True, download=True)
    assert len(hits) == 4 and files.used == 4 and out["annual_downloaded"] == 4 and out["annual_saved"] == 4
    assert "raw/xbrl-facts/1/annual-FY26-consolidated.json.gz" in sink.objects and "raw/xbrl-facts/1/annual-FY26-standalone.json.gz" in sink.objects
    assert xbrl_store.key(row(2026).xbrl_url) in sink.objects                                   # the raw file kept too (F191)
    assert "annual reports (Ind AS only)" in xbrl_facts.render(out)
    # run again: the newest year is stored, so the list is not asked for again and nothing is read or fetched
    lists = len(nse.lists)
    again = xbrl_facts.run(sink, [("1", "ITC")], client=nse, annual=True, download=True, today=date(2026, 10, 28))
    assert len(nse.lists) == lists and again["annual_lists"] == 0 and again["annual_list_skipped"] == {"covered": 1, "dry_run": 0}
    assert len(hits) == 4 and again["annual_saved"] == 0
    # --force asks again, and finds every file's facts stored
    forced = xbrl_facts.run(sink, [("1", "ITC")], client=nse, annual=True, download=True, force=True, today=date(2026, 10, 28))
    assert len(nse.lists) == lists + 1 and forced["annual_lists"] == 1 and len(hits) == 4


def facts_key(scrip, fy, basis="consolidated"):
    return f"raw/xbrl-facts/{scrip}/annual-FY{fy}-{basis}.json.gz"


def test_a_company_is_covered_only_when_every_year_kept_is_stored_not_when_the_newest_alone_is():
    assert xbrl_facts.newest_filed_year(date(2026, 10, 28)) == 26 and xbrl_facts.newest_filed_year(date(2026, 5, 20)) == 25
    assert xbrl_facts.newest_filed_year(date(2026, 5, 31)) == 26 and xbrl_facts.newest_filed_year(date(2027, 1, 5)) == 26
    today = date(2026, 10, 28)
    half = {facts_key("1", 26)}                                                       # FY26 stored by a dry run or a FILE_CAP stop
    assert not xbrl_facts.annual_covered("1", half, today)                            # FY25 and FY24 absent: ask for the list again
    assert xbrl_facts.annual_covered("1", half, today, annual_years=1)                # the newest year alone, if that is all that is kept
    full = {facts_key("1", 26), facts_key("1", 25, "standalone"), facts_key("1", 24)}   # one basis each year is enough
    assert xbrl_facts.annual_covered("1", full, today)
    assert not xbrl_facts.annual_covered("1", full - {facts_key("1", 25, "standalone")}, today)       # a hole in the middle
    assert not xbrl_facts.annual_covered("1", {facts_key("1", 25), facts_key("1", 24), facts_key("1", 23)}, today)   # old years only
    assert not xbrl_facts.annual_covered("3", {"raw/xbrl-facts/3/Q2FY27-consolidated.json.gz"}, today)  # quarterly facts only
    assert not xbrl_facts.annual_covered("2", full, today)                            # another company's keys
    assert xbrl_facts.annual_covered("1", {facts_key("1", 25), facts_key("1", 24), facts_key("1", 23)}, date(2026, 5, 20))   # in May FY25 is newest


def test_a_half_filled_company_gets_its_list_asked_again_and_a_complete_one_makes_no_request():
    today = date(2026, 10, 28)
    sink, hits = sink_for(), []
    for scrip in ("2", "3"):
        sink.objects[f"memory/{scrip}.json"] = json.dumps({"financial_metrics": []}).encode()
    for key in (facts_key("1", 26), facts_key("1", 25), facts_key("1", 24, "standalone"),      # company 1: all three years
                facts_key("2", 26)):                                                           # company 2: FY26 only, FY25 and FY24 absent
        sink.objects[key] = b"x"
    nse = AnnualNse([], hits)
    out = xbrl_facts.run(sink, [("1", "A"), ("2", "B"), ("3", "C")], client=nse, annual=True, today=today)
    assert nse.lists == ["B", "C"] and out["annual_lists"] == 2 and out["annual_list_skipped"] == {"covered": 1, "dry_run": 0}
    assert "list requests made 2, skipped 1 (newest year already stored)" in xbrl_facts.render(out)
    # a rerun over the complete company alone: 0 requests
    only = AnnualNse([], hits)
    assert xbrl_facts.run(sink, [("1", "A")], client=only, annual=True, today=today)["annual_lists"] == 0 and only.lists == []


def test_a_dry_run_without_download_asks_for_no_list_force_or_not():
    sink, hits = sink_for(), []
    nse = AnnualNse([row(2026)], hits)
    dry = xbrl_facts.run(sink, [("1", "ITC")], client=nse, annual=True, dry_run=True, today=date(2026, 10, 28))
    assert nse.lists == [] and dry["annual_lists"] == 0 and dry["annual_list_skipped"] == {"covered": 0, "dry_run": 1}
    forced = xbrl_facts.run(sink, [("1", "ITC")], client=nse, annual=True, dry_run=True, force=True, today=date(2026, 10, 28))
    assert nse.lists == [] and forced["annual_lists"] == 0 and forced["annual_list_skipped"]["dry_run"] == 1 and hits == []   # nothing would be fetched
    listed = xbrl_facts.run(sink, [("1", "ITC")], client=nse, annual=True, dry_run=True, download=True, today=date(2026, 10, 28))
    assert nse.lists == ["ITC"] and listed["would_download"] == 1 and hits == []          # with --download the list shows what would be fetched


def test_annual_download_stops_at_the_file_cap_and_a_dry_run_fetches_nothing(monkeypatch):
    listing = [row(2026), row(2025), row(2024)]
    sink, hits = sink_for(), []
    dry = xbrl_facts.run(sink, [("1", "ITC")], client=AnnualNse(listing, hits), annual=True, download=True, dry_run=True)
    assert hits == [] and dry["would_download"] == 3 and dry["annual_saved"] == 0 and not any(k.startswith("raw/xbrl") for k in sink.objects)
    monkeypatch.setenv("FILE_CAP", "2")
    out = xbrl_facts.run(sink, [("1", "ITC")], client=AnnualNse(listing, hits), annual=True, download=True)
    assert len(hits) == 2 and out["capped"] is True and "file cap reached" in out["stopped"] and out["annual_saved"] == 2


def test_annual_without_a_client_is_said_not_silently_skipped():
    out = xbrl_facts.run(sink_for(), [("1", "ITC")], annual=True)
    assert "no NSE client" in out["annual_skipped"] and "annual reports skipped" in xbrl_facts.render(out)


def test_the_cli_annual_flag_builds_a_client_only_when_a_list_will_be_asked_for(monkeypatch, tmp_path):
    sink, hits = sink_for(), []
    monkeypatch.setattr(cli, "make_sink", lambda settings: sink, raising=False)
    monkeypatch.setattr(cli, "_universe_companies", lambda s, scrips: [("1", "ITC")])
    built = []
    monkeypatch.setattr("bse_intel.nse.NseClient", lambda *a, **k: built.append(1) or AnnualNse([row(2026)], hits))
    assert cli.main(["xbrl-facts", "--annual", "--dry-run", "--json", str(tmp_path / "s.json")]) == 0
    assert built == [] and hits == []                                        # a dry run without --download asks for no list
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))["annual_list_skipped"]["dry_run"] == 1
    assert cli.main(["xbrl-facts", "--annual", "--dry-run", "--force", "--json", str(tmp_path / "u.json")]) == 0
    assert built == [] and hits == [] and json.loads((tmp_path / "u.json").read_text(encoding="utf-8"))["annual_lists"] == 0   # --force: still none
    assert cli.main(["xbrl-facts", "--annual", "--dry-run", "--download", "--json", str(tmp_path / "v.json")]) == 0 and built == [1]
    assert json.loads((tmp_path / "v.json").read_text(encoding="utf-8"))["annual_lists"] == 1 and hits == []
    assert cli.main(["xbrl-facts", "--json", str(tmp_path / "t.json")]) == 0 and built == [1]


# --- the cross-check: screener's annual columns --------------------------------------------------------------------------------------

CONTEXTS = {"D": {"s": "2025-04-01", "e": "2026-03-31", "m": 12}, "I": {"i": "2026-03-31"},
            "N1": {"i": "2026-03-31", "d": {"in-capmkt:DetailsOfOtherNoncurrentFinancialLiabilitiesAxis": "Member1"}}}


def money(name, ctx, crore):
    return [name, ctx, "INR", crore * CR, -5]


def text(name, ctx, value):
    return [name, ctx, None, value, None]


def facts_doc(rows, kind="annual"):
    return {"kind": kind, "basis": "CONSOLIDATED", "contexts": CONTEXTS, "units": {"INR": "MONEY"}, "facts": rows}


def loader(annual_rows=None, q4_rows=None):
    def annual(fy, basis):
        return xbrl_facts.Facts(facts_doc(annual_rows)) if annual_rows and fy == "FY26" else None

    def quarter(period, basis):
        return xbrl_facts.Facts(facts_doc(q4_rows, kind="results")) if q4_rows and period == "Q4FY26" else None
    return quarter, annual


def section(section_id, table, columns):
    head = "".join(f"<th>{c}</th>" for c in columns)
    body = "".join(f"<tr><td>{label}</td>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>" for label, vals in table.items())
    return (f'<section id="{section_id}"><p>Consolidated Figures in Rs. Crores</p><table><thead><tr><th></th>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></section>")


def itc_page(extra=""):
    pl = section("profit-loss", {"Sales&nbsp;+": ["78,868"], "Other Income&nbsp;+": ["2,523"], "Profit before tax": ["28,033"],
                                 "Net Profit&nbsp;+": ["21,018"], "Depreciation": ["1,000"]}, ["Mar 2026"])
    return section("quarters", {"Sales&nbsp;+": ["100"], "Net Profit&nbsp;+": ["10"]}, ["Mar 2026"]) + pl + extra


ITC_ROWS = [money("RevenueFromOperations", "D", 89913.33), money("ExciseDuty", "D", 11044.93),
            # screener's Other Income 2,523.09 and PBT 28,033 count the associates' share of 377.08 (ITC: counted, the report's 11.3)
            money("OtherIncome", "D", 2146.01), money("ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod", "D", 377.08),
            money("ProfitBeforeTax", "D", 27655.92), money("ProfitLossForPeriod", "D", 21018.0),
            money("ProfitOrLossAttributableToOwnersOfParent", "D", 20689.47), money("DepreciationDepletionAndAmortisationExpense", "D", 1000.0)]


def memory():
    metrics = [{"metric": m, "period": "Q4FY26", "value": v, "unit": "INR_CR", "basis": "CONSOLIDATED", "as_of": "2026-11-01",
                "source_news_id": "xbrl:res:1:Q4FY26"} for m, v in (("revenue", 100.0), ("pat", 10.0))]
    return {"financial_metrics": metrics, "balance_sheet": [], "sector": "FMCG"}


def run_company(html, quarter=None, annual=None):
    return sc.compare_company(memory(), {"CONSOLIDATED": parse_full(html)}, "1", "ITC", quarter, annual)


def annual(result, line):
    return next(p for p in result["annual_pairs"] if p["metric"] == line and p["period"] == "FY26")


def test_itc_fy26_annual_columns_from_the_annual_report_xbrl_with_the_source_recorded():
    quarter, yearly = loader(annual_rows=ITC_ROWS)
    got = run_company(itc_page(), quarter, yearly)
    sales = annual(got, "revenue")
    assert sales["class"] == "match" and sales["source"] == "annual_report_xbrl" and sales["memory_source_id"] == "annual_report_xbrl:FY26"
    assert sales["memory_value"] == pytest.approx(89913.33 - 11044.93) == pytest.approx(78868.40) and sales["screener_value"] == 78868.0
    # the associates' share is counted by screener for ITC: a named alternative, reported
    other, pbt = annual(got, "other_income"), annual(got, "pbt")
    assert other["class"] == "matches_screener_view:associates_in_other_income" and other["associates"] == "with"
    assert pbt["class"] == "matches_screener_view:associates_in_pbt" and pbt["associates"] == "with"
    assert other["adjustment"] == "associates_in_other_income (xbrl facts)" and other["source"] == "annual_report_xbrl"
    assert annual(got, "pat")["class"] == "match" and annual(got, "depreciation")["class"] == "match"
    assert got["associates"]["with"] >= 2 and got["annual_no_facts"] == []
    out = sc.summarise([got], "2026-10-28")
    assert out["annual_by_source"] == {"annual_report_xbrl": {"pairs": len(got["annual_pairs"]), "match": 3}}
    assert out["annual_by_line"]["revenue"]["match"] == 1 and out["annual_pairs"] == len(got["annual_pairs"])
    assert "from annual_report_xbrl" in sc.render(out) and "## The annual columns against the annual-report XBRL" in sc.to_markdown(out, "d")
    rows = {r["metric"]: r for r in __import__("csv").DictReader(__import__("io").StringIO(sc.to_csv(out))) if r["table"] == "annual_xbrl"}
    assert rows["other_income"]["source"] == "annual_report_xbrl" and "source" in sc.CSV_HEADER


def test_without_an_annual_report_the_year_falls_back_on_the_q4_integrated_files_12_month_figures():
    quarter, yearly = loader(q4_rows=ITC_ROWS)
    got = run_company(itc_page(), quarter, yearly)
    sales = annual(got, "revenue")
    assert sales["class"] == "match" and sales["source"] == "q4_integrated_file" and sales["memory_source_id"] == "q4_integrated_file:FY26"
    # the annual report wins where both are stored
    both = loader(annual_rows=ITC_ROWS, q4_rows=[money("RevenueFromOperations", "D", 1.0)])
    assert annual(run_company(itc_page(), *both), "revenue")["source"] == "annual_report_xbrl"
    # neither: the column is counted, never silently dropped
    none = run_company(itc_page(), *loader())
    assert none["annual_pairs"] == [] and none["annual_no_facts"] == ["FY26"]
    assert sc.summarise([none], "d")["annual_columns_without_facts"] == {"columns": 1, "companies": 1}
    # no facts source at all (a caller without one): no annual pairs, no claim
    assert run_company(itc_page())["annual_pairs"] == []


def test_a_wrong_annual_figure_is_a_mismatch_and_the_owners_share_is_named():
    rows = [r for r in ITC_ROWS if r[0] != "ProfitLossForPeriod"] + [money("ProfitLossForPeriod", "D", 21400.0)]
    quarter, yearly = loader(annual_rows=rows)
    page = itc_page().replace("21,018", "20,689")                      # screener's Excel shows the owners' share
    pat = annual(run_company(page, quarter, yearly), "pat")
    assert pat["class"] == "naming" and "owners' share" in pat["note"]
    assert annual(run_company(itc_page().replace("78,868", "70,000"), quarter, yearly), "revenue")["class"] == "mismatch"


def test_the_balance_sheet_at_march_reads_its_parts_from_the_annual_report_first_and_says_so():
    bs = section("balance-sheet", {"Borrowings&nbsp;+": ["11,283"]}, ["Mar 2026"])
    d = memory()
    d["balance_sheet"] = [{"period": "Q4FY26", "as_of": "2026-11-01", "source_news_id": "xbrl:res:1:Q4FY26", "gross_debt_cr": 9453.0,
                           "total_assets_cr": 182372.0}]
    lease = [text("DescriptionOfOtherNoncurrentFinancialLiabilities", "N1", "Lease liabilities"),
             money("OtherNoncurrentFinancialLiabilities", "N1", 1830.0)]
    for rows_for, source in ((dict(annual_rows=lease), "annual_report_xbrl"), (dict(q4_rows=lease), "q4_integrated_file")):
        quarter, yearly = loader(**rows_for)
        got = sc.compare_company(d, {"CONSOLIDATED": parse_full(itc_page(bs))}, "1", "ITC", quarter, yearly)
        p = next(p for p in got["bs_pairs"] if p["metric"] == "borrowings")
        assert p["class"] == "matches_screener_view:borrowings_plus_lease_liabilities" and p["source"] == source


def test_the_cash_flow_of_a_march_year_is_read_from_the_annual_report_when_memory_keeps_none():
    cf = section("cash-flow", {"Cash from Operating Activity&nbsp;+": ["20,000"],
                               "Cash from Investing Activity&nbsp;+": ["-11,886"]}, ["Mar 2026"])
    rows = [money("CashFlowsFromUsedInOperatingActivities", "D", 20000.0), money("CashFlowsFromUsedInInvestingActivities", "D", -12845.0),
            money("EffectOfExchangeRateChangesOnCashAndCashEquivalents", "D", 959.0)]
    quarter, yearly = loader(annual_rows=rows)
    got = run_company(itc_page(cf), quarter, yearly)
    cash = {p["metric"]: p for p in got["cf_pairs"]}
    assert cash["operating"]["class"] == "match" and cash["operating"]["source"] == "annual_report_xbrl"
    assert cash["investing"]["class"] == "matches_screener_view:investing_plus_exchange_effect"       # -12,845 + 959 = -11,886
    assert cash["investing"]["memory_source_id"] == "annual_report_xbrl:FY26"


# --- review fixes: the view guard on the annual path, and small lines marked ---------------------------------------------------

def test_the_annual_associates_view_is_tried_only_past_twice_its_tolerance():
    # ours 98.4 and a 0.3 share against screener's 100: the share would close the gap (98.7 within 1.5) but the gap is 1.6 Cr
    rows = [money("ProfitBeforeTax", "D", 98.4), money("ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod", "D", 0.3)]
    quarter, yearly = loader(annual_rows=rows)
    page = section("profit-loss", {"Profit before tax": ["100"]}, ["Mar 2026"])
    got = run_company(section("quarters", {"Sales&nbsp;+": ["100"], "Net Profit&nbsp;+": ["10"]}, ["Mar 2026"]) + page, quarter, yearly)
    p = annual(got, "pbt")
    assert p["class"] == "mismatch" and not p["class"].startswith("matches_screener_view")
    # a gap past twice the tolerance that the share does close is still named
    rows = [money("ProfitBeforeTax", "D", 96.0), money("ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod", "D", 4.0)]
    quarter, yearly = loader(annual_rows=rows)
    got = run_company(section("quarters", {"Sales&nbsp;+": ["100"], "Net Profit&nbsp;+": ["10"]}, ["Mar 2026"]) + page, quarter, yearly)
    assert annual(got, "pbt")["class"] == "matches_screener_view:associates_in_pbt"


def test_view_explanations_on_small_lines_are_marked_counted_apart_and_not_called_proof():
    small = run_company(section("quarters", {"Sales&nbsp;+": ["100"], "Net Profit&nbsp;+": ["10"]}, ["Mar 2026"])
                        + section("profit-loss", {"Profit before tax": ["100"]}, ["Mar 2026"]), *loader(annual_rows=[
                            money("ProfitBeforeTax", "D", 96.0),
                            money("ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod", "D", 4.0)]))
    p = annual(small, "pbt")
    assert p["class"] == "matches_screener_view:associates_in_pbt" and p["small_line"] is True
    assert p["note"].endswith(" (chance risk: small line)")
    big = annual(run_company(itc_page(), *loader(annual_rows=ITC_ROWS)), "other_income")          # 2,523 Cr: not a small line
    assert big["class"].startswith("matches_screener_view") and "small_line" not in big and "chance risk" not in big["note"]
    out = sc.summarise([small, run_company(itc_page(), *loader(annual_rows=ITC_ROWS))], "2026-10-28")
    assert out["view_small_line"] == 1 and out["view_large_line"] >= 2
    assert out["views_by_class"]["small_line"] == {"matches_screener_view:associates_in_pbt": 1}
    text, md = sc.render(out), sc.to_markdown(out, "2026-10-28")
    assert "1 on lines under 150 Cr (chance risk: not proof of a match)" in text
    assert "## Explained by a screener view (large and small lines apart)" in md and "the small-line ones are not proof of a match" in md
    assert "| under 150 Cr (chance risk) | 1 |" in md
    # EPS is no crore line: never marked
    eps_pair = {"class": "matches_screener_view:treasury_shares", "metric": "eps", "screener_value": 9.5, "note": ""}
    fake = {"pairs": [eps_pair]}
    sc.mark_small_line_views(fake)
    assert "small_line" not in eps_pair and eps_pair["note"] == ""
