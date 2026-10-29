"""Annual-report XBRL from BSE for the years NSE does not list (owner, 29 Oct 2026: "ensure to save them so next run required
less 100 files"): each file and the company's list kept in R2, a stored year not asked again, the NSE document kept first."""

import gzip
import json
from datetime import date

import pytest

from bse_intel import bse_annual_xbrl as ba
from bse_intel import xbrl_facts as xf
from bse_intel.adapters.bse import Blocked
from bse_intel.nse import FileCapReached
from test_screener_download import Sink

TODAY = date(2026, 10, 29)


def xml(end_year: int, nature: str, revenue: float) -> bytes:
    ctx = "".join(f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="x">L1</xbrli:identifier></xbrli:entity>'
                  f"<xbrli:period>{per}</xbrli:period></xbrli:context>"
                  for cid, per in (("D", f"<xbrli:startDate>{end_year - 1}-04-01</xbrli:startDate><xbrli:endDate>{end_year}-03-31</xbrli:endDate>"),
                                   ("P", f"<xbrli:startDate>{end_year - 2}-04-01</xbrli:startDate><xbrli:endDate>{end_year - 1}-03-31</xbrli:endDate>")))
    return ('<?xml version="1.0" encoding="UTF-8"?><xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" '
            'xmlns:ind-as="http://www.mca.gov.in/XBRL/2022-12-31/ind-as" xmlns:iso4217="http://www.xbrl.org/2003/iso4217">' + ctx +
            '<xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>'
            f'<ind-as:NatureOfReportStandaloneConsolidated contextRef="D">{nature}</ind-as:NatureOfReportStandaloneConsolidated>'
            f'<ind-as:RevenueFromOperations contextRef="D" unitRef="INR" decimals="-5">{revenue * 1e7:.0f}</ind-as:RevenueFromOperations>'
            f'<ind-as:RevenueFromOperations contextRef="P" unitRef="INR" decimals="-5">{revenue * 0.9e7:.0f}</ind-as:RevenueFromOperations>'
            "</xbrli:xbrl>").encode()


ROWS = [  # the answer repeats joined rows; another company's code is not ours
    {"fld_scripcode": 500279, "fld_filename": "AnnualReport_A24.xml", "enddate": "2024-03-31T00:00:00", "xbrldate": "2024-10-24T11:25:40"},
    {"fld_scripcode": 500279, "fld_filename": "AnnualReport_A24.xml", "enddate": "2024-03-31T00:00:00", "xbrldate": "2024-10-24T11:25:40"},
    {"fld_scripcode": 500279, "fld_filename": "AnnualReport_B24.xml", "enddate": "2024-03-31T00:00:00", "xbrldate": "2024-10-24T11:26:00"},
    {"fld_scripcode": 500279, "fld_filename": "AnnualReport_C25.xml", "enddate": "2025-03-31T00:00:00", "xbrldate": "2025-09-15T20:49:40"},
    {"fld_scripcode": 500279, "fld_filename": "AnnualReport_old.xml", "enddate": "2019-03-31T00:00:00", "xbrldate": "2019-10-01T00:00:00"},
    {"fld_scripcode": 999999, "fld_filename": "AnnualReport_other.xml", "enddate": "2024-03-31T00:00:00", "xbrldate": "2024-10-01T00:00:00"},
]
FILES = {"AnnualReport_A24.xml": xml(2024, "Standalone", 968.04), "AnnualReport_B24.xml": xml(2024, "Consolidated", 970.0),
         "AnnualReport_C25.xml": xml(2025, "Standalone", 746.69)}


class Client:
    def __init__(self, cap: int | None = None, refuse: bool = False):
        self.lists, self.files, self.cap, self.refuse = 0, [], cap, refuse

    def get(self, path, params, dataset, covers=None):
        assert path == ba.LIST and params["Flag"] == "7" and params["scripcode"] == "500279"
        self.lists += 1
        return json.dumps({"Table": ROWS}).encode()

    def fetch_url(self, url, params, dataset, covers=None, file=False):
        if self.refuse:
            raise Blocked("HTTP 403")
        if self.cap is not None and len(self.files) >= self.cap:
            raise FileCapReached("cap")
        name = url.rsplit("/", 1)[1]
        assert url == ba.FILE_URL.format(name=name) and file
        self.files.append(name)
        return FILES[name]


def test_the_companys_own_files_once_each():
    got = ba.own_files(ROWS, "500279")
    assert [f["name"] for f in got] == ["AnnualReport_old.xml", "AnnualReport_A24.xml", "AnnualReport_B24.xml", "AnnualReport_C25.xml"]


def test_only_the_years_without_an_annual_document_are_fetched_kept_raw_and_the_next_run_asks_for_nothing():
    sink = Sink()
    nse_fy25 = xf.parse_annual_facts(xml(2025, "Standalone", 746.0))
    xf.save_annual(sink, "500279", "FY25", "STANDALONE", nse_fy25)            # NSE already gave FY25
    client = Client()
    out = ba.run(sink, [("500279", "ONIDA"), ("BANKA", "BANKA")], client, today=TODAY)
    assert client.files == ["AnnualReport_A24.xml", "AnnualReport_B24.xml"]   # FY24 both bases; FY25 stored; FY19 too old
    assert out["facts_saved"] == 2 and out["not_on_bse"] == 1 and not out["more"]
    assert gzip.decompress(sink.get_object(ba.file_key("500279", "AnnualReport_A24.xml"))) == FILES["AnnualReport_A24.xml"]
    doc = xf.loads(sink.get_object(xf.annual_key("500279", "FY24", "CONSOLIDATED")))
    assert doc["source"] == "bse" and doc["basis"] == "CONSOLIDATED"
    assert xf.Facts(doc).cr("RevenueFromOperations", end=date(2024, 3, 31), months=12) == pytest.approx(970.0)
    again = Client()
    second = ba.run(sink, [("500279", "ONIDA")], again, today=TODAY)
    assert again.lists == 0 and again.files == [] and second["lists_reused"] == 1 and second["files_wanted"] == 0


def test_a_run_stopped_by_the_file_cap_finishes_the_year_next_time():
    sink = Sink()
    first = ba.run(sink, [("500279", "ONIDA")], Client(cap=1), today=TODAY)
    assert first["more"] and first["files_downloaded"] == 1
    client = Client()
    ba.run(sink, [("500279", "ONIDA")], client, today=TODAY)
    assert client.files == ["AnnualReport_B24.xml", "AnnualReport_C25.xml"]   # FY24's other basis, then FY25
    assert ba.file_key("500279", "AnnualReport_A24.xml") in sink.objects


def test_a_refusal_stops_the_run():
    with pytest.raises(Blocked):
        ba.run(Sink(), [("500279", "ONIDA")], Client(refuse=True), today=TODAY)
