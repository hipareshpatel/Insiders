"""Results XBRL from BSE for the quarters NSE does not list (owner, 29 Oct 2026: "Ensure all test files must gets saved"): every
downloaded file goes through the fill's client into our XBRL store, its facts become the results doc, a stored quarter is never
asked again, and the archive's answer is kept for a week."""

from datetime import date
from pathlib import Path

import pytest

from bse_intel import bse_results_xbrl as br
from bse_intel import xbrl_facts as xf
from bse_intel.bse import XbrlLink
from bse_intel.nse import FileCapReached, SourceBlockedError
from test_screener_download import Sink

TODAY = date(2026, 10, 29)
FIX = Path(__file__).parent / "fixtures"
Q2 = (FIX / "bse_main_ind_as_532811_q2fy25.xml").read_bytes()     # Q2FY25 standalone
Q3 = (FIX / "bse_main_ind_as_532811_q3fy25.xml").read_bytes()     # Q3FY25 standalone
URL = "https://www.bseindia.com/XBRLFILES/FourOneUploadDocument/{}.xml"


class Bse:
    def __init__(self, links, files, cap=None, refuse=False):
        self.links, self.bodies, self.cap, self.refuse = links, files, cap, refuse
        self.keep, self.lists, self.got, self.files = None, 0, [], {"downloaded": 0, "kept": 0, "from_store": 0}

    def results_xbrl(self, scrip):
        if self.refuse:
            raise SourceBlockedError("BSE refused: HTTP 403")
        self.lists += 1
        return self.links

    def download(self, url, max_bytes=30_000_000):
        assert self.keep is not None          # the files go to the store
        if self.cap is not None and len(self.got) >= self.cap:
            raise FileCapReached("cap")
        self.got.append(url)
        return self.bodies[url]


LINKS = [XbrlLink("Q2FY25", "STANDALONE", URL.format("q2old"), "2024-11-01T10:00:00"),
         XbrlLink("Q2FY25", "STANDALONE", URL.format("q2rev"), "2024-11-20T10:00:00"),     # revised: the later one is taken
         XbrlLink("Q3FY25", "STANDALONE", URL.format("q3"), "2025-02-01T10:00:00"),
         XbrlLink("Q4FY25", "STANDALONE", URL.format("q4wrong"), "2025-05-01T10:00:00"),   # the file is another quarter's
         XbrlLink("Q1FY27", "STANDALONE", URL.format("q1fy27"), "2026-08-01T10:00:00")]    # NSE's facts are stored
FILES = {URL.format("q2old"): Q3, URL.format("q2rev"): Q2, URL.format("q3"): Q3, URL.format("q4wrong"): Q3,
         URL.format("q1fy27"): Q3}


def test_the_window_is_the_last_13_quarters_ended():
    w = br.window(TODAY)
    assert w[0] == "Q2FY27" and w[-1] == "Q2FY24" and len(w) == 13


def test_missing_quarters_are_filled_from_bse_and_the_next_run_asks_for_nothing():
    sink = Sink()
    for p in br.window(TODAY):
        if p not in ("Q2FY25", "Q3FY25", "Q4FY25"):
            sink.put_object(xf.key("532811", p, "STANDALONE"), b"x")      # NSE gave every other quarter
    bse = Bse(LINKS, FILES)
    out = br.run(sink, [("532811", "ABC"), ("NSEONLY", "NSEONLY")], bse, today=TODAY)
    assert bse.got == [URL.format("q2rev"), URL.format("q3"), URL.format("q4wrong")]
    assert out["facts_saved"] == 2 and out["period_mismatch"] == 1 and out["not_on_bse"] == 1 and not out["more"]
    doc = xf.loads(sink.get_object(xf.key("532811", "Q2FY25", "STANDALONE")))
    assert doc["exchange"] == "BSE" and doc["period"] == "Q2FY25"
    again = Bse(LINKS, FILES)
    second = br.run(sink, [("532811", "ABC")], again, today=TODAY)
    assert again.lists == 0 and second["lists_reused"] == 1
    assert again.got == [URL.format("q4wrong")]      # only the quarter still missing; its file is read from the store in life


def test_a_company_with_every_quarter_stored_is_not_listed():
    sink = Sink()
    for p in br.window(TODAY):
        sink.put_object(xf.key("532811", p, "CONSOLIDATED"), b"x")
    bse = Bse(LINKS, FILES)
    out = br.run(sink, [("532811", "ABC")], bse, today=TODAY)
    assert bse.lists == 0 and out["complete"] == 1


def test_the_file_cap_ends_the_run_with_more_left_and_a_refusal_stops_it():
    capped = Bse(LINKS, FILES, cap=1)
    out = br.run(Sink(), [("532811", "ABC")], capped, today=TODAY)
    assert out["more"] and len(capped.got) == 1
    with pytest.raises(SourceBlockedError):
        br.run(Sink(), [("532811", "ABC")], Bse(LINKS, FILES, refuse=True), today=TODAY)


def test_a_file_the_store_did_not_keep_stops_the_run():
    bse = Bse(LINKS, FILES)
    bse.files["downloaded"] = 1                      # the client downloaded a file and the store kept none
    out = br.run(Sink(), [("532811", "ABC")], bse, today=TODAY)
    assert out["store_full"] and out["more"] and out["facts_saved"] == 0
