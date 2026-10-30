"""TODO 139 (3): every raw results file that the 180-day rule will delete has its facts copy (xbrl_expiry.py), read only."""

from __future__ import annotations

import gzip
from pathlib import Path

from bse_intel import xbrl_expiry, xbrl_facts, xbrl_store
from bse_intel.sinks.platform import PlatformSink

FIXTURES = Path(__file__).parent / "fixtures"
TITAN = (FIXTURES / "nse_old_titan_q2fy24.xml").read_bytes()
SHAREHOLDING = (FIXTURES / "nse_shp_csbbank_q1fy24.xml").read_bytes()
OTHER = TITAN.replace(b">TITAN<", b">OTHERCO<").replace(b">500114<", b">999999<")     # the same statements, another company
URL = "https://nsearchives.nseindia.com/corporate/xbrl/TITAN_Q2FY24.xml"
URL2 = "https://nsearchives.nseindia.com/corporate/xbrl/TITAN_Q1FY24.xml"
URL3 = "https://nsearchives.nseindia.com/corporate/xbrl/SHP.xml"


class FakeSink(PlatformSink):
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.puts = 0

    def put_object(self, key, body, content_type="application/json"):
        self.puts += 1
        self.objects[key] = body

    def get_object(self, key):
        return self.objects.get(key)

    def list_objects(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))


def store(sink, url, data):
    sink.objects[xbrl_store.key(url)] = gzip.compress(data)


def test_covered_missing_and_nothing_to_keep():
    sink = FakeSink()
    sink.objects[xbrl_store.TOTAL_KEY] = b'{"bytes": 1}'
    store(sink, URL, TITAN)            # has its facts copy
    store(sink, URL2, OTHER)           # another company's results, no facts copy: the defect
    store(sink, URL3, SHAREHOLDING)    # no results: nothing to keep
    sink.objects[xbrl_store.PREFIX + "broken.xml.gz"] = b"not gzip"
    doc = xbrl_facts.parse_facts(TITAN, "1", URL)
    xbrl_facts.save(sink, "1", doc["period"], doc["basis"], doc)
    sink.objects[xbrl_facts.listed_key("1")] = b"{}"      # a marker, not a facts document
    puts = sink.puts

    s = xbrl_expiry.check(sink, workers=2)

    assert sink.puts == puts                                # read only
    assert (s["raw_files"], s["facts_docs"], s["covered"]) == (4, 1, 1)
    assert (s["results"], s["annual"], s["nothing_to_keep"], s["unreadable"]) == (1, 0, 1, 1)
    assert s["facts_missing"] == 1 and s["not_verified"] == 1
    missing = {m["key"]: m for m in s["missing"]}
    assert missing[xbrl_store.key(URL2)]["kind"] == "results"
    assert missing[xbrl_store.key(URL2)]["period"] == doc["period"]
    assert "FACTS MISSING for 1" in xbrl_expiry.render(s)
    assert "NOT VERIFIED: 1" in xbrl_expiry.render(s)


def test_an_older_file_of_a_kept_period_is_superseded():
    """Facts are keyed by period and basis: a revised file's facts replace the first file's, whose raw copy is then no loss."""
    sink = FakeSink()
    store(sink, URL, TITAN)
    store(sink, URL2, TITAN)           # the same company, period and basis from another url
    doc = xbrl_facts.parse_facts(TITAN, "1", URL)
    doc["period"] = "memory's label"   # memory's label may differ; the file's own period is what is compared
    xbrl_facts.save(sink, "1", "Q2FY24", doc["basis"], doc)
    s = xbrl_expiry.check(sink)
    assert (s["covered"], s["superseded"], s["results"], s["facts_missing"], s["not_verified"]) == (1, 1, 0, 0, 0)


def test_unreadable_facts_document_is_not_a_pass():
    sink = FakeSink()
    store(sink, URL, TITAN)
    sink.objects[xbrl_facts.key("1", "Q2FY24", "CONSOLIDATED")] = b"damaged"
    s = xbrl_expiry.check(sink)
    assert s["facts_docs_unreadable"] == 1 and s["not_verified"] == 1
    assert "every raw file" not in xbrl_expiry.render(s)


def test_all_covered():
    sink = FakeSink()
    store(sink, URL, TITAN)
    doc = xbrl_facts.parse_facts(TITAN, "1", URL)
    xbrl_facts.save(sink, "1", doc["period"], doc["basis"], doc)
    s = xbrl_expiry.check(sink)
    assert s["facts_missing"] == 0 and s["covered"] == 1
    assert "every raw file that holds results has its facts copy" in xbrl_expiry.render(s)


def test_no_identity_without_a_company_or_a_period():
    facts = [["Symbol", "c", None, "TITAN", None]]
    assert xbrl_expiry.identity({"facts": facts, "file_period": "Q2FY24", "basis": "Consolidated"}) == ("TITAN", "Q2FY24", "CONSOLIDATED")
    assert xbrl_expiry.identity({"facts": facts, "file_period": None, "period": None, "basis": "CONSOLIDATED"}) is None
    assert xbrl_expiry.identity({"facts": [], "file_period": "Q2FY24", "basis": "CONSOLIDATED"}) is None


def test_facts_dump_lists_documents_and_matching_facts():
    sink = FakeSink()
    doc = xbrl_facts.parse_facts(TITAN, "1", URL)
    xbrl_facts.save(sink, "1", doc["period"], doc["basis"], doc)
    sink.objects[xbrl_facts.listed_key("1")] = b"{}"
    text = xbrl_facts.dump(sink, "1", r"^Symbol$")
    assert "kind=results" in text and URL in text and "_listed" not in text
    assert "Symbol @" in text and "TITAN" in text
    assert xbrl_facts.dump(sink, "2", "x") == "no facts stored for 2"
