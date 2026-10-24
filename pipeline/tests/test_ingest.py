from __future__ import annotations

from datetime import date

import httpx
import pymupdf
import pytest

from bse_intel.bse import BseClient, SourceBlockedError, attachment_url, parse_row, parse_scrip
from bse_intel.extract import Document
from bse_intel.models import Filing
from bse_intel.rules import RuleBook, extract_date

ROW = {
    "NEWSID": "a1b2c3d4-0000-4000-8000-000000000001",
    "SCRIP_CD": 999001,
    "XML_NAME": "",
    "NEWSSUB": "Demo Cement Ltd - 999001 - Outcome of Board Meeting",
    "DT_TM": "2026-10-13T17:42:10.153",
    "NEWS_DT": "2026-10-13T17:42:10.153",
    "DissemDT": "2026-10-13T17:43:02",
    "CRITICALNEWS": 0,
    "ATTACHMENTNAME": "f1e2d3c4-1111-2222-3333-444455556666.pdf",
    "HEADLINE": "Unaudited Financial Results for the quarter ended September 30, 2026",
    "CATEGORYNAME": "Result",
    "SUBCATNAME": "Financial Results",
    "PDFFLAG": 0,
    "NSURL": "https://www.bseindia.com/stock-share-price/demo-cement-ltd/democem/999001/",
    "SLONGNAME": "Demo Cement Ltd",
    "Fld_Attachsize": 123456,
}


def test_parse_row():
    f = parse_row(ROW)
    assert f.news_id == ROW["NEWSID"] and f.scrip_code == "999001" and f.symbol == "DEMOCEM"
    assert f.filed_at == "2026-10-13T17:43:02+05:30" and f.filing_date == "2026-10-13"
    assert f.pdf_url == "https://www.bseindia.com/xml-data/corpfiling/AttachLive/f1e2d3c4-1111-2222-3333-444455556666.pdf"
    assert attachment_url("x.pdf", 1).endswith("/AttachHis/x.pdf") and attachment_url("", 0) is None
    assert parse_row({"NEWSID": "", "SCRIP_CD": 1}) is None


def test_parse_scrip_is_defensive():
    row = parse_scrip({"SCRIP_CD": "999001", "Scrip_Name": "DEMO CEMENT", "Issuer_Name": "Demo Cement Ltd",
                       "scrip_id": "democem", "ISIN_NUMBER": "INE000000001", "INDUSTRY": "Cement & Cement Products",
                       "Mktcap": "1,234.50", "GROUP": "xt"})
    assert row == {"scrip_code": "999001", "company_name": "Demo Cement Ltd", "symbol": "DEMOCEM",
                   "isin": "INE000000001", "industry": "Cement & Cement Products", "market_cap_cr": 1234.5,
                   "bse_group": "XT"}


def _transport(pages: list[list[dict]], total: int, seen: list[httpx.Request], status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "www.bseindia.com":
            return httpx.Response(200, text="<html></html>", headers={"set-cookie": "sid=1; Domain=.bseindia.com; Path=/"})
        if status != 200:
            return httpx.Response(status, text="<HTML>Access Denied</HTML>")
        page = int(request.url.params["pageno"])
        rows = pages[page - 1] if page <= len(pages) else []
        return httpx.Response(200, json={"Table": rows, "Table1": [{"ROWCNT": total}]})
    return httpx.MockTransport(handler)


def test_announcements_warm_up_paginate_and_send_browser_headers():
    seen: list[httpx.Request] = []
    rows = [dict(ROW, NEWSID=f"id-{i}") for i in range(3)]
    client = BseClient(page_delay=0, transport=_transport([rows[:2], rows[2:]], 3, seen))
    filings = list(client.announcements(date(2026, 10, 13)))
    assert [f.news_id for f in filings] == ["id-0", "id-1", "id-2"]
    assert seen[0].url == "https://www.bseindia.com/corporates/ann"
    api = seen[1]
    assert api.url.params["strPrevDate"] == "20261013" and api.url.params["strType"] == "C"
    assert api.headers["referer"] == "https://www.bseindia.com/corporates/ann"
    assert api.headers["origin"] == "https://www.bseindia.com" and "Mozilla" in api.headers["user-agent"]
    assert api.headers.get("cookie") == "sid=1"
    assert len([r for r in seen if r.url.host == "api.bseindia.com"]) == 2


def test_403_raises_source_blocked():
    client = BseClient(page_delay=0, transport=_transport([], 0, [], status=403))
    with pytest.raises(SourceBlockedError, match="Indian network"):
        list(client.announcements(date(2026, 10, 13)))


def test_download_falls_back_between_live_and_history():
    def handler(request):
        if "AttachLive" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, content=b"%PDF-1.7 his")
    client = BseClient(transport=httpx.MockTransport(handler), download_delay=(0, 0))
    client._warmed = True
    assert client.download("https://www.bseindia.com/xml-data/corpfiling/AttachLive/x.pdf") == b"%PDF-1.7 his"


@pytest.fixture
def rulebook(settings):
    return RuleBook.from_config(settings.load_toml("taxonomy.toml"))


def _f(headline, category="", subcategory="", subject=""):
    return Filing(news_id="n", scrip_code="1", company_name="X", headline=headline, subject=subject,
                  category=category, subcategory=subcategory, filed_at="2026-10-13T10:00:00+05:30",
                  filing_date="2026-10-13")


@pytest.mark.parametrize("headline,category,subcategory,action,event", [
    ("Intimation of loss of share certificates", "Company Update", "", "DROP", None),
    ("Closure of Trading Window", "Company Update", "Trading Window", "DROP", None),
    ("Certificate under Reg. 74 (5) of SEBI (DP) Regulations", "Company Update", "", "DROP", None),
    ("Copy of Newspaper Publication of financial results", "Result", "", "DROP", None),
    ("Shareholding Pattern for the quarter ended Sep 2026", "", "Shareholding Pattern", "XBRL", "SHAREHOLDING"),
    ("Board Meeting Intimation for considering results on 21/10/2026", "Board Meeting", "", "CALENDAR", "BOARD_MEETING"),
    ("Outcome of Board Meeting - Financial results", "Board Meeting", "", "FAST_TRACK", "RESULTS"),
    ("Unaudited Financial Results for the quarter ended September 30, 2026", "Result", "", "FAST_TRACK", "RESULTS"),
    ("Credit Rating reaffirmed by CRISIL", "Company Update", "Credit Rating", "FAST_TRACK", "DEBT_RATINGS"),
    ("Company bags order worth Rs 450 crore from NHAI", "Company Update", "", "FAST_TRACK", "ORDER_WIN"),
    ("Intimation under Regulation 30 - Receipt of Letter of Acceptance", "Company Update", "", "FAST_TRACK", "ORDER_WIN"),
    ("Receipt of Letter of Intent for wind EPC project", "Company Update", "", "FAST_TRACK", "ORDER_WIN"),
    ("Investor Presentation for Q2 FY27", "Company Update", "", "FAST_TRACK", "CONCALL_PRESENTATION"),
    ("Outcome of Board Meeting held on 13.10.2026 - Dividend", "Board Meeting", "", "FAST_TRACK", None),
    ("Receipt of Warning Letter from USFDA for Unit III", "Company Update", "", "FAST_TRACK", "LITIGATION_REGULATORY"),
    ("Commencement of commercial production at Dahej plant", "Company Update", "", "FAST_TRACK", "CAPEX"),
    ("Clarification sought on USFDA news item", "Company Update", "", "PASS1", None),
    ("Disclosure under Regulation 30 - Update", "Company Update", "", "PASS1", None),
    ("Notice of the 34th Annual General Meeting to be held on 20/11/2026", "AGM/EGM", "", "CALENDAR", "AGM"),
    ("Intimation of Record Date for interim dividend - 30/10/2026", "Corp. Action", "", "CALENDAR", "RECORD_DATE"),
    ("Record date for Rights Issue of equity shares", "Corp. Action", "", "FAST_TRACK", "RIGHTS_ISSUE"),
    ("Outcome of AGM and voting results", "AGM/EGM", "", "TIMELINE", "GOVERNANCE"),
    # Routine events: a dated timeline line, no card (D22)
    ("Jubilant Pharmova recommends final dividend of Rs 5 per share for FY25", "Company Update", "", "TIMELINE", "CORPORATE_ACTION"),
    ("Outcome of Postal Ballot - re-appointment of Mr Rao as Independent Director", "AGM/EGM", "", "TIMELINE", "GOVERNANCE"),
    ("Disclosure under Regulation 31(1) and 31(4) of SEBI SAST - nil encumbrance", "Company Update", "", "TIMELINE", "GOVERNANCE"),
    ("Invocation of pledge on promoter shares under Regulation 31", "Company Update", "", "PASS1", None),
    # The owner's Stage 1 list (seven hard-drop categories) and the conditional ones, with real headlines
    ("Communication to the shareholders w.r.t. TDS on Final Dividend for FY 24-25", "Company Update", "", "DROP", None),
    ("Letter to shareholders whose KYC is not updated", "Company Update", "", "DROP", None),
    ("Intimation to Shareholders related to mandatory furnishing of PAN, KYC and Nomination details", "Company Update", "", "DROP", None),
    ("Intimation under Regulation 30(5) of SEBI (LODR) Reg 2015", "Company Update", "", "DROP", None),
    ("KMP authorised for the purpose of determining materiality of any information", "Company Update", "", "DROP", None),
    ("Clarification on movement in share price", "Company Update", "", "DROP", None),
    ("Reply - Increase in Volume", "Company Update", "", "DROP", None),
    ("Clarification on news item appearing in 'Media/Publication'", "Company Update", "", "PASS1", None),
    ("Grant of Stock Options", "Company Update", "", "DROP", None),
    ("Transfer of Equity Shares from CSB ESOS Trust", "Company Update", "", "DROP", None),
    ("Adoption of eMudhra ESOP/RSU Scheme 2025", "Company Update", "", "PASS1", None),
    ("Allotment of equity shares on preferential basis", "Company Update", "", "PASS1", None),  # not an ESOP drop
    ("Audited financial results for FY25 and recommendation of final dividend", "Result", "", "FAST_TRACK", "RESULTS"),
    # Owner, 2026-10-18: no cards for director / KMP changes or resignations; an auditor's resignation stays with pass 1
    ("Appointment of Mr Yasushi Nishikawa as Managing Director and CEO", "Company Update", "", "DROP", None),
    ("Resignation of Statutory Auditors", "Company Update", "", "PASS1", None),
    # ... except the MD, CEO or CFO leaving (owner, 2026-10-19, D30 amended)
    ("Resignation of Mr X as Chief Financial Officer", "Company Update", "", "FAST_TRACK", "MANAGEMENT_CHANGE"),
    ("Cessation of Mr Y as Managing Director and CEO", "Company Update", "", "FAST_TRACK", "MANAGEMENT_CHANGE"),
    ("XYZ Limited has informed the Exchange about resignation of Mr Z as Chief Executive Officer of the Company",
     "", "Resignation of Director/KMP/SMP", "FAST_TRACK", "MANAGEMENT_CHANGE"),
    ("Mr A steps down as CFO with effect from 31 October 2026", "Company Update", "", "FAST_TRACK", "MANAGEMENT_CHANGE"),
    ("Resignation of Mr A as Independent Director", "Company Update", "Resignation of Director/KMP/SMP", "DROP", None),
    ("Resignation of Company Secretary and Compliance Officer", "Company Update", "", "DROP", None),
    ("Appointment of Mr B as Managing Director, not liable to retire by rotation", "Company Update", "Appointment", "DROP", None),
    # Owner, 2026-10-18: no newspaper publications, of results or anything else
    ("Newspaper publication of extract of Consolidated Unaudited Financial Results for the quarter and half year ended September 30, 2026.",
     "Company Update", "Copy of Newspaper Publication", "DROP", None),
    ("intimation regarding notice to members in newspapers pursuant to Section 201(2) of the Companies Act", "Company Update", "", "DROP", None),
    ("Advertisement in newspapers regarding transfer of equity shares to IEPF", "Company Update", "", "DROP", None),
    # NSE annual-report season wording (25-26 Aug 2026)
    ("Notice of 33rd Annual General Meeting ( AGM ) and Annual Report for the Financial Year 2025-26 including Report on "
     "Business Responsibility and Sustainability Reporting ( BRSR )", "Company Update", "", "FAST_TRACK", "ANNUAL_REPORT"),
    ("Business Responsibility and Sustainability Reporting ( BRSR ) for the Financial Year 2025-26", "Company Update", "", "PASS1", None),
    ("Letter Sent To Shareholders For Annual Report Web-Link And Path", "Company Update", "", "DROP", None),
    ("Annual Report 2025-26 Web Link Letters to Shareholders", "Company Update", "", "DROP", None),
    ("Intimation of Board Meeting notice given in newspaper", "Company Update", "", "DROP", None),
    # ... but a reply to a newspaper report is Reg 30(11) news
    ("Clarification on news item appearing in the Economic Times newspaper", "Company Update", "", "PASS1", None),
    ("Verification of market rumour - article published in Business Standard newspaper on 17 October 2026",
     "Company Update", "", "PASS1", None),
    ("Appointment of M/s ABC & Co as Statutory Auditors for a second term of five years", "Company Update", "", "DROP", None),
    ("Completion of term of Statutory Auditors at the conclusion of the 40th AGM", "Company Update", "", "DROP", None),
    ("Appointment of Statutory Auditors to fill the casual vacancy caused by resignation", "Company Update", "", "PASS1", None),
    ("Intimation of Stop Transfer of share certificates", "Company Update", "", "DROP", None),
    ("Register of duplicate share certificates in Form SH-2", "Company Update", "", "DROP", None),
    ("Payment of Annual Listing Fees for FY 2026-27", "Company Update", "", "DROP", None),
    ("Adoption of amended Code of Practices and Procedures for Fair Disclosure of UPSI", "Company Update", "", "DROP", None),
    ("Annual Secretarial Compliance Report under Regulation 24A", "Company Update", "", "DROP", None),
    ("Certificate under Regulation 57(1) for payment of interest on NCDs", "Company Update", "", "DROP", None),
    ("Statement of Deviation under Regulation 32(1) - NIL", "Company Update", "", "DROP", None),
    ("Completion of dispatch of Annual Report and Notice of AGM", "AGM/EGM", "", "DROP", None),
    ("Audio recording of the Earnings Conference Call for Q2 FY27", "Company Update", "", "DROP", None),
    ("Transcript of the Earnings Conference Call for Q2 FY27", "Company Update", "", "FAST_TRACK", "CONCALL_PRESENTATION"),
    ("Statement of Deviation under Regulation 32(1)", "Company Update", "", "PASS1", None),  # may hold a deviation
    ("Delay in payment of interest on NCDs under Regulation 57(1)", "Company Update", "", "PASS1", None),
    ("Allotment of 1,200 equity shares under ESOP", "Company Update", "", "DROP", None),  # a fraction of a percent of equity
    ("Sale of fractional shares and Outcome of Board Meeting - Bonus issue", "Board Meeting", "", "FAST_TRACK", None),
    # Compound headlines that carry news are not dropped as noise (audit A16)
    ("Board Meeting Intimation for results on 21/10/2026 and Closure of Trading Window", "Board Meeting", "Board Meeting Intimation", "CALENDAR", "BOARD_MEETING"),
    ("Unaudited Financial Results for the quarter ended 30.09.2026 and Newspaper Publication", "Result", "", "FAST_TRACK", "RESULTS"),
    ("Financial Results for the quarter ended September 2026 with Investor Grievances", "Result", "", "FAST_TRACK", "RESULTS"),
    ("Financial Results for the quarter ended September 30, 2026", "Board Meeting", "Outcome of Board Meeting", "FAST_TRACK", "RESULTS"),
    ("Approval of fund raising through QIP", "Board Meeting", "Outcome of Board Meeting", "FAST_TRACK", "FUNDRAISE"),
    ("Transfer of equity shares to Investor Education and Protection Fund", "Company Update", "", "DROP", None),
    ("Schedule of Analyst / Institutional Investor Meet", "Company Update", "", "DROP", None),
    ("Analyst / Institutional Investor Meet - Presentation", "Company Update", "", "FAST_TRACK", "CONCALL_PRESENTATION"),
    # Noise review, 2026-10-21 (owner): monthly volumes, press releases and shareholder letters are read, not judged on page 1
    ("Container Corporation Of India Limited has informed the Exchange about Physical Volumes for September 2026",
     "", "General Updates", "FAST_TRACK", "MONTHLY_BUSINESS_UPDATE"),
    ("Bajaj Finserv Limited has informed the Exchange regarding 'information pertaining to the unlisted insurance subsidiaries of the Company'.",
     "", "Updates", "FAST_TRACK", "MONTHLY_BUSINESS_UPDATE"),
    ("Sales figures for the month of October 2026", "Company Update", "", "FAST_TRACK", "MONTHLY_BUSINESS_UPDATE"),
    ('SRF Limited has informed the Exchange regarding a press release dated October 21, 2026, titled "Press release".',
     "", "Press Release", "FAST_TRACK", None),
    ("Press Release.", "", "Press Release / Media Release", "FAST_TRACK", None),
    ("Eternal Limited has filed with exchange copy of shareholders letter dated October 21, 2026.", "", "General Updates", "FAST_TRACK", None),
])
def test_rules(rulebook, headline, category, subcategory, action, event):
    decision = rulebook.classify(_f(headline, category, subcategory))
    assert decision.action == action, decision
    assert decision.event_type == event


def test_calendar_rule_extracts_meeting_date(rulebook):
    decision = rulebook.classify(_f("Board Meeting Intimation", "Board Meeting",
                                    subject="Meeting to be held on 21st October, 2026 to consider results"))
    assert decision.action == "CALENDAR" and decision.catalyst_date == "2026-10-21"
    assert extract_date("on 05/11/2026", "2026-10-13") == "2026-11-05"
    assert extract_date("for FY 2025 ended 31/03/2025", "2026-10-13") is None


REG34 = "Reg. 34 (1) Annual Report"


@pytest.mark.parametrize("headline,subcategory,action,event", [
    # Filed with its AGM notice, under either subcategory: the "AGM notice" date rule took these (audit of discard paths)
    ("Notice of the 33rd Annual General Meeting and Annual Report for the Financial Year 2024-25", REG34, "FAST_TRACK", "ANNUAL_REPORT"),
    ("Notice of the 33rd Annual General Meeting and Annual Report for the Financial year 2024-25", "AGM", "FAST_TRACK", "ANNUAL_REPORT"),
    ("Please find attached herewith the Notice of 48th Annual General Meeting alongwith the Annual Report for the "
     "Financial Year 2025-26. The 48th AGM of the Company will be held on Wednesday", "AGM", "FAST_TRACK", "ANNUAL_REPORT"),
    ("Annual Report for the Financial year 2024-25", REG34, "FAST_TRACK", "ANNUAL_REPORT"),
    ("46th AR 2024-25", REG34, "FAST_TRACK", "ANNUAL_REPORT"),
    ("The Annual Report for the Financial Year 2024-25 is sent to the shareholders on July 04, 2025", REG34, "FAST_TRACK", "ANNUAL_REPORT"),
    ("Completion of dispatch of Annual Report and Notice of AGM", REG34, "FAST_TRACK", "ANNUAL_REPORT"),
    ("Notice of AGM, Book Closure and Annual Report for FY 2025-26", "AGM", "FAST_TRACK", "ANNUAL_REPORT"),
    # The letters telling shareholders without an e-mail address where to find it (Reg 36(1)(b)) carry nothing
    ("Weblink of annual report to the shareholder whose email id not registered.", "General", "DROP", None),
    ("Letter to Shareholders - Weblink of Integrated Annual Report FY 2025-26.", "General", "DROP", None),
    ("Letter to shareholders - Providing the weblink to access the Notice of the 42nd Annual General Meeting and the "
     "Annual Report for FY 2025-26.", "General", "DROP", None),
    ("Intimation regarding a letter dispatched to the Shareholders  for Annual Report of the Company for FY 2024-25", "General", "DROP", None),
    ("Intimation pursuant to Regulation 36(1)(b) of the SEBI LODR Regulations to non-email shareholders", "General", "DROP", None),
    ("Completion of dispatch of Annual Report and Notice of AGM", "AGM", "DROP", None),
    ("Notice of the 34th Annual General Meeting to be held on 20/11/2026", "AGM", "CALENDAR", "AGM"),
    ("Business Responsibility and Sustainability Report forming part of the Annual Report", "Business Responsibility", "PASS1", None),
])
def test_annual_reports_are_read_and_their_letters_dropped(rulebook, headline, subcategory, action, event):
    decision = rulebook.classify(_f(headline, "Company Update", subcategory, subject=subcategory))
    assert (decision.action, decision.event_type) == (action, event), decision


def _pdf(pages: list[str | None]) -> bytes:
    """Text pages; "" = scanned page (image only); None = blank page."""
    scan = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    scan.clear_with(200)
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(36, 36, 560, 800), text, fontsize=9)
        elif text == "":
            page.insert_image(pymupdf.Rect(36, 36, 560, 800), pixmap=scan)
    return doc.tobytes()


def test_digital_and_scanned_pages_with_ocr_budget():
    calls = []
    def ocr(png: bytes) -> str:
        calls.append(png[:8])
        return "| Revenue | 120 |"
    pdf = _pdf(["Outcome of board meeting. Revenue from operations 120 crore. " * 2, "", "", "Segment results table", None])
    doc = Document(pdf, ocr=ocr, max_ocr_pages=1)
    assert doc.page_count == 5 and not doc.is_scanned(0) and doc.is_scanned(1)
    assert not doc.is_scanned(3) and not doc.is_scanned(4)  # short digital text / blank: no OCR
    assert "Revenue from operations" in doc.first_page_text()
    assert doc.page_text(1) == "| Revenue | 120 |" and calls[0] == b"\x89PNG\r\n\x1a\n"
    assert doc.page_text(2) == ""  # OCR budget spent
    assert doc.ocr_pages_used == 1
    text = doc.select_text(10_000, ["segment"])
    assert "--- Page 1 of 5 ---" in text and "Segment results" in text
    doc.close()


def test_unreadable_attachment_does_not_raise():
    doc = Document(b"PK\x03\x04 not a pdf")
    assert doc.page_count == 0 and doc.error and doc.select_text(1000) == ""
    assert Document(None).error == "no attachment"


@pytest.mark.parametrize("industry,sector", [
    ("Non Banking Financial Company (NBFC)", "nbfc"),
    ("Private Sector Bank", "banks"),
    ("Cement & Cement Products", "cement"),
    ("Edible Oil", "fmcg"),
    ("Refineries & Marketing", "oil_gas"),
    ("Environmental Services", "default"),
    ("Auto Components & Equipments", "auto_components"),
    ("IT Enabled Services", "it"),
    (None, "default"),
    # BSE's classification path is read from its most specific level up
    ("Consumer Discretionary > Automobile and Auto Components > Auto Components > Auto Components & Equipments",
     "auto_components"),
    ("Consumer Discretionary > Automobile and Auto Components > Automobiles > Commercial Vehicles", "auto"),
    ("Healthcare > Healthcare > Pharmaceuticals & Biotechnology > Pharmaceuticals", "pharma"),
    ("Healthcare > Healthcare > Healthcare Services > Hospital", "hospitals"),
    ("Industrials > Capital Goods > Industrial Manufacturing > Industrial Products", "capital_goods"),
    ("Fast Moving Consumer Goods > Food Products > Edible Oil", "fmcg"),
])
def test_sector_lens_matching(settings, industry, sector):
    from bse_intel.prompts.engine import PromptEngine

    assert PromptEngine(settings).sector_for(industry).name == sector


def test_industry_path_from_the_scrip_header():
    from bse_intel.bse import industry_path

    header = {"Industry": "Industrial Products", "Sector": "Industrials", "IndustryNew": "Capital Goods",
              "IGroup": "Industrial Manufacturing", "ISubGroup": "Industrial Products"}
    assert industry_path(header) == "Industrials > Capital Goods > Industrial Manufacturing > Industrial Products"
    assert industry_path({"Sector": "Financial Services", "IndustryNew": "Financial Services", "IGroup": "Banks",
                          "ISubGroup": ""}) == "Financial Services > Banks"
    assert industry_path({"Industry": "Cement & Cement Products"}) == "Cement & Cement Products"
    assert industry_path({}) is None


def test_sync_companies_looks_up_missing_industries_once(settings, monkeypatch):
    """BSE's scrip list now carries INDUSTRY null; each company's industry comes from its quote
    header, once, and a failed lookup never overwrites a stored sector."""
    import argparse

    from bse_intel import bse
    from bse_intel.cli import cmd_sync_companies
    from bse_intel.sinks.local import LocalSink

    headers = {
        "999001": {"Sector": "Commodities", "IndustryNew": "Construction Materials", "IGroup": "Cement & Cement Products",
                   "ISubGroup": "Cement & Cement Products"},
        "999002": {"Sector": "Healthcare", "IndustryNew": "Healthcare", "IGroup": "Pharmaceuticals & Biotechnology",
                   "ISubGroup": "Pharmaceuticals"},
    }
    lookups: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.bseindia.com":
            return httpx.Response(200, text="<html></html>")
        if request.url.path.endswith("/ListofScripData_new/w"):
            return httpx.Response(200, json=[
                {"SCRIP_CD": code, "Issuer_Name": f"Demo {code} Ltd", "scrip_id": f"DEMO{code}", "INDUSTRY": None,
                 "Mktcap": cap} for code, cap in (("999001", "1,234.50"), ("999002", "25000"), ("999003", None))])
        scrip = request.url.params["scripcode"]
        lookups.append(scrip)
        if scrip == "999003":
            return httpx.Response(404)
        return httpx.Response(200, json=headers[scrip])

    real = bse.BseClient
    monkeypatch.setattr(bse, "BseClient", lambda: real(transport=httpx.MockTransport(handler), page_delay=0))
    sink = LocalSink(settings)
    sink.execute("companies_upsert", [{"scrip_code": "999003", "company_name": "Demo 999003 Ltd", "sector": "chemicals"}])
    args = argparse.Namespace(source="bse", max_lookups=10_000, refresh_industry=False)

    assert cmd_sync_companies(args, settings, sink) == 0
    assert sorted(lookups) == ["999001", "999002", "999003"]
    sectors = {s: sink.company(s)["sector"] for s in ("999001", "999002", "999003")}
    assert sectors == {"999001": "cement", "999002": "pharma", "999003": "chemicals"}  # failed lookup kept its sector
    assert sink.company("999002")["industry"].endswith("> Pharmaceuticals")
    # BSE's own market cap gets a size label, so size filters and scoring see the company
    assert [sink.company(s)["size_category"] for s in ("999001", "999002", "999003")] == ["SMALL", "LARGE", None]

    lookups.clear()
    assert cmd_sync_companies(args, settings, sink) == 0
    assert lookups == ["999003"]  # known industries are not fetched again


def test_sql_files_hold_one_statement_with_nothing_after_it():
    """D1 refuses a parameterised call holding more than one statement, and reads anything after
    the final semicolon (even a comment) as another one. Python's sqlite3 does not, so check here."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "db"
    for path in sorted([*root.glob("queries/*.sql"), *root.glob("statements/*.sql")]):
        body = "\n".join(line for line in path.read_text().splitlines() if not line.strip().startswith("--"))
        assert body.count(";") <= 1, path.name
        assert not body[body.rfind(";") + 1:].strip(), f"{path.name}: text after the final semicolon"


def _pages_pdf(pages: list[str]) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_textbox(pymupdf.Rect(36, 36, 560, 800), text, fontsize=9)
    return doc.tobytes()


def test_presentation_chunking_favours_financial_and_capex_slides():
    filler = " lorem ipsum" * 60
    pages = ["Demo Chem Ltd Investor Presentation Q2 FY27", "Agenda and company at a glance" + filler,
             "Safe Harbour Statement. This presentation contains forward-looking statements." + filler,
             "Global economy and macro outlook for chemicals" + filler,
             "CSR and ESG initiatives across our plants" + filler,
             "Financial Highlights Q2 FY27: Revenue 412 Cr, EBITDA 74 Cr" + filler,
             "Capex roadmap: 30,000 MTPA brownfield plant commissioning Q4 FY27" + filler]
    doc = Document(_pages_pdf(pages))
    assert doc.kind() == "PRESENTATION"
    text = doc.select_text(2600)  # the first two pages always, then room for two more
    assert "Financial Highlights" in text and "Capex roadmap" in text
    assert "CSR and ESG" not in text and "Safe Harbour" not in text


def test_transcript_kind_and_chatter_is_stripped():
    pages = ["Demo Chem Ltd Q2 FY27 Earnings Conference Call. Participants: management.",
             "Moderator: Ladies and gentlemen, good day. All participant lines will be in the listen-only mode.\n"
             "Moderator: Thank you. The next question is from the line of A from B. Please go ahead.\n"
             "Management: We expect FY27 revenue growth of 20% with margins at 18%.\nThank you, sir.\n"
             "Moderator: The next question is from the line of C. Please go ahead."]
    doc = Document(_pages_pdf(pages))
    assert doc.kind() == "TRANSCRIPT"
    text = doc.select_text(10_000)
    assert "We expect FY27 revenue growth of 20%" in text
    assert "next question" not in text and "listen-only" not in text and "Thank you, sir" not in text


def test_local_object_keys_are_checked_lexically_and_listed_with_slashes(settings):
    import pytest

    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    sink.put_object("memory/500001.json", b"{}")
    sink.put_object("learning/sector_rules.json", b"{}")
    assert sink.list_objects("memory/") == ["memory/500001.json"]
    for bad in ("../x.json", "memory/../../x", "/etc/x", "memory\\\\x.json", "C:/x", "memory//x"):
        with pytest.raises(ValueError):
            sink.put_object(bad, b"{}")


@pytest.mark.parametrize("headline,subject", [
    ("News Paper Cutting for Q3 Results 31-12-2024 published on 13-02-2025 on FE and Jansatta",
     "Announcement under Regulation 30 (LODR)-Analyst / Investor Meet - Outcome"),
    ("News Paper Cutting on 15-08-2025 Q1 Financial Results FE and Jansatta",
     "Copy Of News Paper Cutting Of Q1 Un-Audited Financial Results For The FY 2025-26"),
    ("Published Financial Results for the FY 2025-26 Audited",
     "Copy Of News Paper Cutting Of Un-Audited Financial Results For Q4 31-03-2026"),
    ("Published News for Q3 Results 31-12-2024 Notice for Board Meeting will be held on 11-02-2025",
     "New Paper Cutting For Un-Audited Financial Results 31-12-2024"),
    ("News Paper Cutting", "Published News Paper Cutting For The FY 2026-27 Q1 Results 30-06-2026"),
])
def test_news_paper_cuttings_are_dropped_whatever_the_spelling(rulebook, headline, subject):
    """Ahluwalia Contracts' clippings ("News Paper Cutting", with a space) reached the model, which invented results
    cards from text with no numbers; two were even fast-tracked as results filings."""
    assert rulebook.classify(_f(headline, "Company Update", "General", subject)).action == "DROP"


def test_page_text_comes_back_in_reading_order():
    """A statement's rows and its column headers are laid out on the page, not in the order a PDF happens
    to store them. Without sorting, Kanoria's FY25 consolidated P&L gave 0% of its figure-carrying lines
    their own row label and put the year headers after every row; with it, 100%. That ordering is where
    the wrong-column and unit-scale errors come from, so the extractor asks for reading order."""
    import pymupdf

    from bse_intel.extract import Document

    doc = pymupdf.open()
    page = doc.new_page()
    # written bottom-up and right-to-left, the way a generator may emit a table
    page.insert_text((320, 190), "430.17", fontsize=9)
    page.insert_text((240, 190), "457.86", fontsize=9)
    page.insert_text((60, 190), "Finance Costs", fontsize=9)
    page.insert_text((320, 150), "14,750.51", fontsize=9)
    page.insert_text((240, 150), "15,367.16", fontsize=9)
    page.insert_text((60, 150), "Revenue from Operations", fontsize=9)
    page.insert_text((60, 110), "(Rs. in million)", fontsize=9)
    pdf = doc.tobytes()
    doc.close()

    text = Document(pdf).page_text(0)
    unit, revenue, finance = text.find("Rs. in million"), text.find("15,367.16"), text.find("457.86")
    assert unit != -1 and revenue != -1 and finance != -1
    assert unit < revenue < finance, "the unit header leads, then the rows in page order"
    line = next(l for l in text.split("\n") if "457.86" in l)
    assert "Finance Costs" in line and "430.17" in line, "a row keeps its label and both columns"


def test_every_announcement_page_is_saved_as_received_and_reads_back_to_the_same_filings(settings):
    """docs/DATA_QUALITY.md: a parsing fix is re-run over what BSE sent, not over a new request."""
    import json
    from dataclasses import replace

    from bse_intel import raw
    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    rows = [dict(ROW, NEWSID=f"id-{i}") for i in range(3)]
    client = BseClient(page_delay=0, transport=_transport([rows[:2], rows[2:]], 3, []))
    raw.attach(client, sink, "bse", settings)
    live = list(client.announcements(date(2026, 10, 13)))
    list(BseClient(page_delay=0, transport=_transport([rows[:2], rows[2:]], 3, [])).announcements(date(2026, 10, 13)))

    keys = sink.list_objects("raw/bse/AnnSubCategoryGetData/")
    assert len(keys) == 2 and client.raw.saved == 2, "one file a page"
    replayed = []
    for key in keys:
        meta, body = raw.decode(sink.get_object(key))
        assert meta["status"] == 200 and meta["params"]["strPrevDate"] == "20261013"
        replayed += [parse_row(r) for r in json.loads(body)["Table"]]
    assert sorted(f.news_id for f in replayed) == sorted(f.news_id for f in live)

    client.raw.save("https://api.bseindia.com/x", {"a": 1}, 200, b"{}")
    client.raw.save("https://api.bseindia.com/x", {"a": 1}, 200, b"{}")
    assert client.raw.saved == 3, "the same answer twice in a run is written once"

    off = BseClient(page_delay=0, transport=_transport([rows], 3, []))
    raw.attach(off, sink, "bse", replace(settings, save_raw=False))
    assert off.raw is None


def test_a_failed_raw_write_never_stops_the_fetch():
    from bse_intel import raw

    class Broken:
        def put_object(self, *a, **k):
            raise OSError("disk full")

    store = raw.RawStore(Broken(), "bse")
    store.save("https://api.bseindia.com/x", {}, 200, b"{}")
    assert store.saved == 0


def test_a_scanned_page_past_the_ocr_cap_is_not_kept_as_read():
    """A page the OCR cap left out was stored as its empty text layer and counted as OCR'd, so no later run
    read it (audit of discard paths, 2026-10-18)."""
    doc = Document(_pdf(["Outcome of board meeting. " * 8, "", ""]), ocr=lambda png: "| Revenue | 120 |", max_ocr_pages=1)
    assert doc.page_text(1) == "| Revenue | 120 |" and doc.page_text(2) == ""
    assert list(doc.to_cache()["ocr"]) == ["1"]


def test_rerun_routes_a_reset_filing_by_todays_rules(settings):
    """scripts/rerun.py: an annual report pass 1 had typed RESULTS is re-run on the ANNUAL_REPORT fast track (F57);
    a filing today's rules would drop keeps its route, since re-reading it measures the reading, not the rule."""
    import importlib.util
    from pathlib import Path

    from bse_intel.sinks.local import LocalSink

    spec = importlib.util.spec_from_file_location("rerun", Path(__file__).parents[1] / "scripts" / "rerun.py")
    rerun = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rerun)
    sink = LocalSink(settings)
    rows = [("n-ar", "Annual Report for the Financial year 2024-25", REG34, "PASS1", "RESULTS"),
            ("n-res", "Unaudited Financial Results for the quarter ended September 30, 2026", "Financial Results",
             "FAST_TRACK", "RESULTS"),
            ("n-tw", "Closure of Trading Window", "Trading Window", "PASS1", "OTHER"),
            ("n-p1", "Disclosure under Regulation 30 - Update", "", "PASS1", "GOVERNANCE")]
    sink.execute("filings_discover", [{
        **_f(headline, "Company Update", subcategory, subject=subcategory).model_copy(update={"news_id": nid}).ledger_row(
            "2026-10-18T00:00:00+05:30"), "status": "ANALYZED", "route": route, "event_type": event}
        for nid, headline, subcategory, route, event in rows])
    sink._db.execute("update filings set route = ?, event_type = ? where news_id = 'n-ar'", ("PASS1", "RESULTS"))

    assert rerun.retriage(sink._db, [r[0] for r in rows]) == 1
    got = {r[0]: (r[1], r[2]) for r in sink._db.execute("select news_id, route, event_type from filings")}
    assert got["n-ar"] == ("FAST_TRACK", "ANNUAL_REPORT")
    assert got["n-res"][1] == "RESULTS" and got["n-tw"] == ("PASS1", "OTHER") and got["n-p1"] == ("PASS1", "GOVERNANCE")


@pytest.mark.parametrize("headline,category,subcategory,subject", [
    # BSE's own wording under the bare "Board Meeting" subcategory; four reached the model (re-run, 2026-10-18)
    ("AHLUWALIA CONTRACTS (INDIA) LTD.has informed BSE that the meeting of the Board of Directors of the Company is "
     "scheduled on 11/02/2025 ,inter alia, to consider and approve Update on board meeting", "Board Meeting", "Board Meeting",
     "Update on board meeting"),
    ("Shivam Autotech Ltdhas informed BSE that the meeting of the Board of Directors of the Company is scheduled on "
     "12/11/2025 ,inter alia, to consider and approve Update on board meeting", "Board Meeting", "Board Meeting",
     "Update on board meeting"),
    ("The meeting of the Board of Directors of the Company is scheduled to be held on Friday, May 09, 2025 to inter alia "
     "consider and approve the Audited Financial Results of the Company for ....", "Insider Trading / SAST",
     "Closure of Trading Window", "Closure of Trading Window"),
])
def test_bse_worded_board_meeting_notices_are_dates(rulebook, headline, category, subcategory, subject):
    decision = rulebook.classify(_f(headline, category, subcategory, subject=subject))
    assert (decision.action, decision.event_type) == ("CALENDAR", "BOARD_MEETING"), decision


def test_top_exit_keeps_a_card_only_for_the_md_ceo_or_cfo_leaving():
    """D30 as amended (owner, 2026-10-19): pass 2's MANAGEMENT_CHANGE ends without a card unless the MD, CEO or CFO is
    leaving; an appointment letter's "not liable to retire by rotation" is not an exit."""
    from bse_intel.pipeline import top_exit

    assert top_exit("We wish to inform that Mr X has resigned from the post of Chief Financial Officer")
    assert top_exit("Cessation of Mr Y as Managing Director on superannuation")
    assert not top_exit("Appointment of Mr B as Managing Director and CEO, not liable to retire by rotation")
    assert not top_exit("Resignation of Ms C as Independent Director due to personal reasons")
    assert not top_exit("Mr D, Director, retires by rotation and offers himself for re-appointment")


def test_every_commands_d1_writes_count_toward_the_day():
    """20 Oct 2026: the day's counter said 93,369 when D1 stopped taking writes at its free 100,000; the maintenance
    commands (card blocks, summaries, requeue, seeds) wrote without adding theirs. Each command's leftover is added."""
    import json as _json

    from bse_intel.sinks.platform import PlatformSink

    kv: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/query/kv_get"):
            key = _json.loads(request.content)["params"][0]
            return httpx.Response(200, json={"rows": [{"value": kv[key]}] if key in kv else []})
        if path.endswith("/exec/kv_set"):
            for row in _json.loads(request.content):
                kv[row["key"]] = row["value"]
            return httpx.Response(200, json={"rows_written": 1})
        if path.endswith("/exec/kv_add"):
            for row in _json.loads(request.content):
                kv[row["key"]] = str(int(kv.get(row["key"], 0)) + int(row["value"]))
            return httpx.Response(200, json={"rows_written": 1})
        return httpx.Response(200, json={"rows_written": 40})

    sink = PlatformSink("https://example.test", "t", transport=httpx.MockTransport(handler))
    sink.execute("cards_upsert", [{"news_id": "n1"}])
    sink.execute("cards_upsert", [{"news_id": "n2"}])
    sink.add_writes("2026-10-20", 40, "now")          # a job that counts its own (the pipeline run)
    sink.add_uncounted_writes("2026-10-20", "now")     # the rest, as the command ends
    assert int(kv["d1_writes:2026-10-20"]) == 81       # 80 card rows and the first counter write


@pytest.mark.parametrize("failure", ["read_timeout", "write_timeout", "bad_gateway"])
def test_a_platform_that_times_out_or_errors_through_every_retry_is_unavailable_not_a_failed_filing(failure, monkeypatch):
    """A ReadTimeout or a 5xx after the retries was raised as itself, reached the pipeline's generic handler and spent one
    of the filing's attempts; it is the site's failure, so it is SinkUnavailable (the filing stays queued)."""
    from bse_intel.sinks import platform
    from bse_intel.sinks.base import SinkUnavailable

    monkeypatch.setattr(platform.time, "sleep", lambda s: None)

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "read_timeout":
            raise httpx.ReadTimeout("read timed out", request=request)
        if failure == "write_timeout":
            raise httpx.WriteTimeout("write timed out", request=request)
        return httpx.Response(502, text="bad gateway")

    sink = platform.PlatformSink("https://example.test", "t", transport=httpx.MockTransport(handler))
    with pytest.raises(SinkUnavailable):
        sink.query("kv_get", ["x"])


def test_jobs_ending_together_both_add_to_the_days_write_counter(settings):
    """The counter was read, added to and written back by each job, so of two jobs ending together the last one won and
    the other's writes were lost; kv_add adds in the database itself (real SQL, the same file D1 runs)."""
    from bse_intel.sinks.local import LocalSink

    first, second = LocalSink(settings), LocalSink(settings)
    first.add_writes("2026-10-24", 100, "t1")
    second.add_writes("2026-10-24", 250, "t2")      # a second job on the same database, not a fresh read of the first
    first.add_writes("2026-10-24", 5, "t3")
    assert first.kv_get("d1_writes:2026-10-24") == "355"
    first.kv_set("other", "7", "t")
    first.execute("kv_add", [{"key": "other", "value": 3, "updated_at": "t"}])
    assert first.kv_get("other") == "10"


def test_batches_are_measured_in_bytes_like_the_workers_cap():
    """The Worker refuses a body over 1,000,000 UTF-8 bytes; batches were measured in characters, so rows of ₹ signs or
    Devanagari (three bytes each) could make a batch the Worker refused."""
    from bse_intel.sinks.base import MAX_PAYLOAD_BYTES, chunk_rows
    from bse_intel.sinks.platform import _encode

    rows = [{"news_id": str(i), "headline": "₹" * 50_000} for i in range(40)]
    batches = chunk_rows(rows, _encode)
    assert sum(len(b) for b in batches) == 40
    assert all(len(_encode(b).encode("utf-8")) <= MAX_PAYLOAD_BYTES for b in batches)
