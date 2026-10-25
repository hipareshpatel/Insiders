"""The off-path BSE client ported from the reference repository (owner, 25 Oct 2026): its request contract (URL,
parameters, headers), pacing, retries, stops and parsing, checked against a fake session. No network."""
from __future__ import annotations

import json
from datetime import date

import pytest
import requests

from bse_intel.adapters import bse

# the reference's headers, as written in Pareshking/NSE-BSE-Insider-Tracker collectors/bse/client.py (d2a929e)
REFERENCE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/153.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.5",
    "Origin": "https://www.bseindia.com", "Referer": "https://www.bseindia.com/", "Connection": "keep-alive",
    "Sec-Fetch-Site": "same-site"}


class Answer:
    def __init__(self, status: int, body: bytes, ctype: str = "application/json"):
        self.status_code, self.content, self.headers = status, body, {"Content-Type": ctype}


class FakeSession:
    def __init__(self, answers):
        self.headers: dict = {}
        self.answers, self.calls = list(answers), []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout, "headers": dict(self.headers)})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def close(self):
        pass


class Raw:
    def __init__(self):
        self.puts = []

    def put(self, source, dataset, body, **meta):
        self.puts.append((source, dataset, body, meta))


def client(*answers, raw=None):
    session, waits = FakeSession(answers), []
    return bse.BSEClient(session=session, sleep=waits.append, raw=raw), session, waits


def test_announcements_request_matches_the_reference_contract_and_is_parsed():
    page = {"Table": [{"NEWSID": "53168f27", "SCRIP_CD": 516038, "ATTACHMENTNAME": "6bcf4467.pdf",
                       "HEADLINE": "Intimation of outcome of Postal ballot"}], "Table1": [{"ROWCNT": 1136}]}
    raw = Raw()
    c, session, waits = client(Answer(200, json.dumps(page).encode()), raw=raw)
    rows, total = c.announcements(date(2026, 10, 12), 3)
    assert rows == page["Table"] and total == 1136
    (call,) = session.calls
    assert call["url"] == "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w" and call["timeout"] == 45
    assert call["params"] == {"pageno": 3, "strCat": "-1", "strPrevDate": "20261012", "strScrip": "", "strSearch": "P",
                              "strToDate": "20261012", "strType": "C", "subcategory": "-1"}
    assert call["headers"] == REFERENCE_HEADERS == bse.HEADERS
    assert raw.puts[0][:2] == ("bse", "announcements") and raw.puts[0][2] == json.dumps(page).encode()
    assert waits == []   # no pause before the first call


def test_every_endpoint_sends_the_reference_parameters():
    a, b = date(2026, 10, 1), date(2026, 10, 10)
    c, session, waits = client(*[Answer(200, b'{"Table": []}')] * 6,
                               Answer(200, b"Security Code,Security Name,Name of Person\n"))
    c.deals("bulk", a, b), c.deals("block", a, b), c.sast(a, b), c.actions(a, b), c.shareholding_filings(6)
    c.board_meetings(a, b)
    c.insider_csv(a, b)
    got = [(call["url"].rsplit("/api/", 1)[1], call["params"]) for call in session.calls]
    assert got == [
        ("BulkDealData_ng/w", {"DealType": "1", "sc_code": "", "FDate": "01/10/2026", "TDate": "10/10/2026"}),
        ("BulkDealData_ng/w", {"DealType": "2", "sc_code": "", "FDate": "01/10/2026", "TDate": "10/10/2026"}),
        ("Corporatesast/w", {"scripcode": "", "ddlregul": "ALL", "fromdate": "20261001", "todate": "20261010"}),
        ("DefaultData/w", {"ddlcategorys": "E", "ddlindustrys": "", "segment": "0", "strSearch": "S",
                           "Fdate": "20261001", "TDate": "20261010", "Purposecode": "", "scripcode": ""}),
        ("Corp_Shareholding_ng/w", {"scripcode": "", "flag": "6", "indtype": ""}),
        ("boardmeeting_fno/w", {"securityName": "", "txtDate": "01/10/2026", "txtTodate": "10/10/2026",
                                "ddlPurpose": "", "ddlindustry": "", "ddlsegment": "C"}),
        ("Corp_Regulation_DownloadCSV_ng/w", {"scripCode": "", "Regulation": "", "fromDT": "20261001",
                                              "ToDate": "20261010", "Isdefault": "2"})]
    assert len(waits) == 6 and all(4.0 <= w <= 6.0 for w in waits)   # 4-6 s between calls


def test_a_refusal_stops_at_once_and_failures_are_retried_then_logged(caplog):
    c, session, _ = client(Answer(403, b"<HTML>Access Denied</HTML>", "text/html"))
    with pytest.raises(bse.Blocked, match="HTTP 403"):
        c.sast(date(2026, 10, 1), date(2026, 10, 2))
    assert len(session.calls) == 1   # no browser fallback, no retry
    c, session, _ = client(requests.ConnectionError("reset"), Answer(503, b""), Answer(200, b'{"Table": [{"x": 1}]}'))
    assert c.sast(date(2026, 10, 1), date(2026, 10, 2)) == [{"x": 1}] and len(session.calls) == 3
    c, session, _ = client(*[Answer(502, b"")] * 4)
    with caplog.at_level("ERROR"):
        assert bse.safely(lambda: c.sast(date(2026, 10, 1), date(2026, 10, 2)), "sast") is None
    assert len(session.calls) == 4 and "Failed" in caplog.text
    c, session, _ = client(Answer(404, b""))
    with pytest.raises(bse.Missing):
        c.shareholding_xbrl("/xml-data/SHP.html")
    assert session.calls[0]["url"] == "https://www.bseindia.com/xml-data/SHP.html"
    c, _, _ = client(Answer(200, b"<html>maintenance</html>"))
    with pytest.raises(bse.Blocked, match="not JSON"):
        c.sast(date(2026, 10, 1), date(2026, 10, 2))


def test_inline_xbrl_facts_are_read_as_the_reference_does():
    text = ('<xbrli:context id="ShareholdingOfPromoterAndPromoterGroupI"></xbrli:context>'
            '<ix:nonFraction name="in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares" '
            'contextRef="ShareholdingOfPromoterAndPromoterGroupI" scale="-2" decimals="2">94.04</ix:nonFraction>'
            '<ix:nonFraction name="in-bse-shp:NumberOfShares" contextRef="ShareholdingOfPromoterAndPromoterGroupI" '
            'sign="-" scale="0">1,20,000</ix:nonFraction>'
            '<ix:nonNumeric name="other:Ignored" contextRef="x">y</ix:nonNumeric>')
    assert bse.ixbrl_facts(text).split("\n") == [
        '<xbrli:context id="ShareholdingOfPromoterAndPromoterGroupI"/>',
        '<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ShareholdingOfPromoterAndPromoterGroupI">'
        '0.9404</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>',
        '<in-bse-shp:NumberOfShares contextRef="ShareholdingOfPromoterAndPromoterGroupI">-120000</in-bse-shp:NumberOfShares>']
