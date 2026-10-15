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
                       "Mktcap": "1,234.50"})
    assert row == {"scrip_code": "999001", "company_name": "Demo Cement Ltd", "symbol": "DEMOCEM",
                   "isin": "INE000000001", "industry": "Cement & Cement Products", "market_cap_cr": 1234.5}


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
    client = BseClient(transport=httpx.MockTransport(handler))
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
    ("Shareholding Pattern for the quarter ended Sep 2026", "", "Shareholding Pattern", "DROP", None),
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
    # Compound headlines that carry news are not dropped as noise (audit A16)
    ("Board Meeting Intimation for results on 21/10/2026 and Closure of Trading Window", "Board Meeting", "Board Meeting Intimation", "CALENDAR", "BOARD_MEETING"),
    ("Unaudited Financial Results for the quarter ended 30.09.2026 and Newspaper Publication", "Result", "", "FAST_TRACK", "RESULTS"),
    ("Financial Results for the quarter ended September 2026 with Investor Grievances", "Result", "", "FAST_TRACK", "RESULTS"),
    ("Financial Results for the quarter ended September 30, 2026", "Board Meeting", "Outcome of Board Meeting", "FAST_TRACK", "RESULTS"),
    ("Approval of fund raising through QIP", "Board Meeting", "Outcome of Board Meeting", "FAST_TRACK", "FUNDRAISE"),
    ("Transfer of equity shares to Investor Education and Protection Fund", "Company Update", "", "DROP", None),
    ("Schedule of Analyst / Institutional Investor Meet", "Company Update", "", "DROP", None),
    ("Analyst / Institutional Investor Meet - Presentation", "Company Update", "", "FAST_TRACK", "CONCALL_PRESENTATION"),
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
])
def test_sector_lens_matching(settings, industry, sector):
    from bse_intel.prompts.engine import PromptEngine

    assert PromptEngine(settings).sector_for(industry).name == sector
