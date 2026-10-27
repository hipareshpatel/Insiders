"""F213: a run downloads at most FILE_CAP (100) NSE/BSE files; past it FileCapReached stops the run and the rest waits."""

from __future__ import annotations

import json
import time
from datetime import timedelta

import httpx
import pytest

from bse_intel import memory_gaps as mg
from bse_intel import restated_pdf as rp
from bse_intel import seed
from bse_intel import settings as settings_module
from bse_intel import text_backfill as tb
from bse_intel.bse import SourceBlockedError
from bse_intel.file_cap import files, shard_cap
from bse_intel.nse import FileCapReached, NseClient
from bse_intel.timeutil import now_ist

ARCH = "https://nsearchives.nseindia.com/corporate/a.pdf"
XML = b"<?xml version='1.0'?><xbrl/>"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for name in ("FILE_CAP", "FILE_CAP_SHARDS"):
        monkeypatch.delenv(name, raising=False)


def nse_client(hits=None):
    def handler(request):
        if hits is not None:
            hits.append(str(request.url))
        return httpx.Response(200, content=XML)
    client = NseClient(transport=httpx.MockTransport(handler), sleep=lambda s: None, retries=1, pause=(0, 0))
    client._warmed = True
    return client


def test_defaults_and_the_shard_split():
    assert settings_module.file_cap() == 100 and settings_module.file_cap_shards() == 1
    assert shard_cap(100, 1) == 100 and shard_cap(100, 12) == 8 and shard_cap(100, 4) == 25 and shard_cap(100, 6) == 16
    assert shard_cap(5, 12) == 1          # never below one file
    assert shard_cap(0, 12) == 0          # no cap stays no cap


def test_the_shard_count_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("FILE_CAP_SHARDS", "4")
    assert files.cap() == 25
    monkeypatch.setenv("FILE_CAP", "10")
    assert files.cap() == 2
    monkeypatch.setenv("FILE_CAP_SHARDS", "0")        # a bad value is one shard
    assert files.cap() == 10
    monkeypatch.setenv("FILE_CAP", "0")
    assert files.cap() == 0


def test_the_cap_stops_at_the_101st_file_and_counts_nothing_past_it(caplog):
    for _ in range(100):
        files.take()
    assert files.used == 100 and not files.reached
    with caplog.at_level("INFO"):
        with pytest.raises(FileCapReached):
            files.take()
        with pytest.raises(FileCapReached):
            files.take()
    assert files.used == 100 and files.reached
    assert caplog.text.count("file cap reached: the rest waits for the next run") == 1   # logged once
    assert files.summary() == "files downloaded 100 of cap 100; file cap reached: the rest waits for the next run"
    files.reset()
    files.take()
    assert files.summary() == "files downloaded 1 of cap 100"


def test_it_is_a_blocked_source_error_but_not_a_refusal():
    from bse_intel.nse import stop_reason
    exc = FileCapReached("x")
    assert isinstance(exc, SourceBlockedError)
    assert stop_reason(exc) == "file cap reached: the rest waits for the next run"
    assert stop_reason(SourceBlockedError("403")).startswith("NSE refused")


def test_no_cap_when_it_is_zero(monkeypatch):
    monkeypatch.setenv("FILE_CAP", "0")
    for _ in range(300):
        files.take()
    assert files.used == 300 and files.summary() == "files downloaded 300 of cap none"


def test_the_nse_client_counts_files_not_lists_and_stops_before_the_request(monkeypatch):
    monkeypatch.setenv("FILE_CAP", "2")
    hits: list[str] = []
    client = nse_client(hits)
    client._get("https://www.nseindia.com/api/x")     # a list / JSON call: not a file
    assert files.used == 0
    assert client.fetch(ARCH) == XML and client.download(ARCH) == XML
    assert files.used == 2
    sent = len(hits)
    with pytest.raises(FileCapReached):
        client.fetch(ARCH)
    with pytest.raises(FileCapReached):
        client.download(ARCH)
    assert len(hits) == sent                           # nothing was asked of NSE past the cap


def test_bse_downloads_are_counted(monkeypatch):
    from bse_intel.adapters.bse import BSEClient
    from bse_intel.bse import BseClient
    monkey = BseClient.__new__(BseClient)
    with pytest.raises(AttributeError):               # counted first; the bare object then has no session
        monkey.download("https://www.bseindia.com/xml-data/corpfiling/AttachLive/x.pdf")
    assert files.used == 1
    with pytest.raises(Exception):
        BSEClient.__new__(BSEClient).fetch_url("https://www.bseindia.com/x.xml", {}, "x", file=True)
    assert files.used == 2
    with pytest.raises(Exception):                    # a list call is not a file
        BSEClient.__new__(BSEClient).fetch_url("https://api.bseindia.com/x", {}, "x")
    assert files.used == 2
    monkeypatch.setenv("FILE_CAP", "2")
    with pytest.raises(FileCapReached):
        BseClient.__new__(BseClient).download("https://www.bseindia.com/xml-data/corpfiling/AttachLive/y.pdf")


def test_seed_fetch_lets_the_cap_through_and_does_not_hide_it_as_a_dead_file(monkeypatch, tmp_path):
    monkeypatch.setenv("FILE_CAP", "1")
    client = nse_client()
    url = "https://nsearchives.nseindia.com/corporate/xbrl/one.xml"
    assert seed._fetch(client, url, tmp_path, None) == XML
    with pytest.raises(FileCapReached):
        seed._fetch(client, "https://nsearchives.nseindia.com/corporate/xbrl/two.xml", tmp_path, None)
    assert seed._fetch(client, url, tmp_path, None) == XML   # the stored copy still serves, uncounted


def test_a_pipeline_filing_over_the_cap_stays_queued_with_its_attempts_unchanged(settings, monkeypatch):
    """The live run stops, the filing is PENDING (not FAILED), no attempt is spent, and nothing was marked failed."""
    from test_pipeline import _filing as make, build

    now = now_ist() - timedelta(hours=2)
    filings = [make(f"n{i}", "Disclosure under Regulation 30", now + timedelta(minutes=i), "Company Update") for i in range(3)]
    pipeline, sink, fake = build(settings, filings, {}, {})
    monkeypatch.setenv("FILE_CAP", "1")
    files.used = 1                                    # this run has already downloaded its file

    def download(url, max_bytes=None):
        files.take(url)
        return b"%PDF-1.4"

    pipeline.bse.download = download
    out = pipeline._process_one(filings[0], bulk=False, memory_complete=True)
    assert out.update["status"] == "PENDING" and "attempts" not in out.update
    assert out.update["last_error"] == "deferred: file cap reached"
    assert isinstance(pipeline._blocked, FileCapReached)
    assert pipeline.stats.failed == 0
    assert pipeline.stats.stopped_reason == "file cap reached: the rest waits for the next run"
    # the rest of the group is not even started
    assert pipeline._process_group(filings[1:], deadline=10 ** 12, bulk=False, memory_complete=True) == []


def test_memory_gaps_fill_resumes_and_does_not_mark_the_unfinished_company_tried(monkeypatch):
    from test_memory_gaps import EIGHT, Sink, _dossier, _report
    monkeypatch.setenv("FILE_CAP", "2")
    sink = Sink({s: _dossier(s, EIGHT[1:]) for s in "BCD"})
    report = _report(sink, list("BCD"))
    seeded: list[str] = []

    def seed_one(scrip, since):
        files.take(scrip)                             # one file a company
        seeded.append(scrip)

    out = mg.fill(sink, report, seed_one, 1000)
    assert out["attempted"] == ["B", "C"] and out["capped"] and out["more"] and out["failed"] == []
    assert set(json.loads(sink.kv[mg.TRIED_KEY])) == {"B", "C"}      # D is neither tried nor failed
    assert mg.TRIED_KEY + ":failed" not in sink.kv or "D" not in json.loads(sink.kv[mg.TRIED_KEY + ":failed"])
    files.reset()                                     # the next run
    out = mg.fill(sink, report, seed_one, 1000)
    assert out["attempted"] == ["D"] and not out["capped"] and not out["more"]
    assert seeded == ["B", "C", "D"]


class Client:
    def __init__(self, got=None):
        self.calls, self.got = [], got

    def fetch(self, url, max_bytes=30_000_000):
        files.take(url)
        self.calls.append(url)
        return self.got


def _card(n):
    return {"news_id": f"NSE{n}", "pdf_url": f"https://nsearchives.nseindia.com/c/f{n}.pdf", "filed_at": "2026-10-01T10:00:00+05:30"}


def test_text_backfill_stops_at_the_cap_keeps_the_rest_unmarked_and_resumes(monkeypatch):
    from test_text_backfill import Sink
    monkeypatch.setenv("FILE_CAP", "2")
    sink = Sink()
    rows = [_card(n) for n in range(1, 5)]
    out = tb.run(sink, rows, Client(), ocr=False)      # every file is a 404: kept as failed, so a resume skips it
    assert out["capped"] and out["more"] and out["fetched"] == 2 and out["failed"] == 2
    assert set(json.loads(sink.kv["textbackfill:failed:0of1"])) == {"NSE1", "NSE2"}   # 3 and 4 are not marked
    assert "file cap reached: the rest waits for the next run" in tb.render(out)
    time.sleep(0.3)                                   # the run's read-ahead thread has finished its (refused) take
    files.reset()
    second = Client()
    out = tb.run(sink, rows, second, ocr=False)
    assert [c.rsplit("/", 1)[-1] for c in second.calls] == ["f3.pdf", "f4.pdf"] and not out["capped"]


def test_restated_pdf_stops_at_the_cap_and_resumes_after_the_last_company(monkeypatch):
    from test_pdf_referee import FakeNse, filing, make_pdf
    from test_restated_pdf import CONSOLIDATED_Q4, Sink, dossier
    monkeypatch.setenv("FILE_CAP", "1")
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"

    class Capped(FakeNse):
        def fetch(self, u, max_bytes=0):
            files.take(u)
            return super().fetch(u, max_bytes)

    nse = Capped([filing(url=url)], {url: make_pdf(CONSOLIDATED_Q4)})
    stats = rp.run(nse, Sink(dossier()), {"1": "X", "2": "Y", "3": "Z"}, quarters=1)
    assert stats["capped"] and stats["stopped_at"] == "2" and stats["last_done"] == "1" and stats["companies"] == 1
    files.reset()
    stats = rp.run(nse, Sink(dossier()), {"1": "X", "2": "Y", "3": "Z"}, quarters=1, resume_after=stats["last_done"])
    assert stats["capped"] and stats["last_done"] == "2" and stats["stopped_at"] == "3"


def test_the_pdf_referee_leaves_the_pairs_after_the_cap_not_run(monkeypatch):
    from test_pdf_referee import STANDALONE_PAGE, FakeNse, filing, make_pdf, pair
    from bse_intel import pdf_referee as pr
    monkeypatch.setenv("FILE_CAP", "1")
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"

    class Capped(FakeNse):
        def fetch(self, u, max_bytes=0):
            files.take(u)
            return super().fetch(u, max_bytes)

    rows = [pair(verdict="neither", symbol="A"), pair(verdict="neither", symbol="B"), pair(verdict="neither", symbol="C")]
    out = pr.run(Capped([filing()], {url: make_pdf(STANDALONE_PAGE)}), rows, ocr=False)
    assert out["file_cap_reached"] and not out["blocked"]
    assert out["verdicts"] == {"pdf_matches_ours": 1, "not_run": 2}
    assert {r["reason"] for r in out["rows"] if r["pdf_verdict"] == "not_run"} == {"file cap"}
    assert "file cap reached: the rest waits for the next run" in pr.render(out)


def test_a_capped_call_seed_does_not_start_another_run():
    from bse_intel import call_seed
    assert call_seed.next_run({"stopped": True, "companies": 3}, 17)
    assert not call_seed.next_run({"stopped": True, "capped": True, "companies": 3}, 17)


def test_the_speed_test_stops_its_rounds_at_the_cap(monkeypatch):
    from bse_intel import nse_speedtest as st
    monkeypatch.setenv("FILE_CAP", "3")
    client = nse_client()
    fetcher = st.HttpFetcher(client)
    result = st.run_round("a", (0, 0), 1, [ARCH] * 6, fetcher, sleep=lambda s: None)
    assert len(result.requests) == 3 and result.stopped == "file cap reached"


def test_a_stored_file_is_not_counted(tmp_path):
    """The local cache is read before the client is asked, so it never reaches the counter."""
    class XbrlClient:
        def download(self, url, max_bytes=None):
            files.take(url)
            return XML

    url = "https://nsearchives.nseindia.com/corporate/xbrl/one.xml"
    assert seed._fetch(XbrlClient(), url, tmp_path, None) == XML
    assert files.used == 1
    assert seed._fetch(XbrlClient(), url, tmp_path, None) == XML
    assert files.used == 1
