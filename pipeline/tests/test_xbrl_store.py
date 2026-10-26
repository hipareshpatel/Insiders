"""F191: results XBRL files are kept in R2 (raw/xbrl/) and read before the exchange is asked again."""

from __future__ import annotations

import gzip
import json

import pytest

from bse_intel import seed, xbrl_store
from bse_intel.pipeline import Pipeline
from bse_intel.screener_xbrl_referee import CompanyFiles
from bse_intel.sinks.local import LocalSink
from bse_intel.sinks.platform import PlatformSink

URL = "https://nsearchives.nseindia.com/corporate/xbrl/RESULTS_1.xml"
XML = b"<xbrl>" + b"x" * 500 + b"</xbrl>"


class FakeSink(PlatformSink):
    def __init__(self, fail_put=False, fail_get=False):
        self.objects: dict[str, bytes] = {}
        self.fail_put, self.fail_get = fail_put, fail_get

    def put_object(self, key, body, content_type="application/json"):
        if self.fail_put:
            raise RuntimeError("R2 down")
        self.objects[key] = body

    def get_object(self, key):
        if self.fail_get:
            raise RuntimeError("R2 down")
        return self.objects.get(key)


class Client:
    def __init__(self):
        self.calls = 0

    def download(self, url, max_bytes=0):
        self.calls += 1
        return XML


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.delenv("XBRL_STORE_MAX_MB", raising=False)
    xbrl_store.reset()
    yield
    xbrl_store.reset()


def test_put_then_get_round_trip_with_stable_bytes():
    sink = FakeSink()
    xbrl_store.put(sink, URL, XML)
    key = xbrl_store.key(URL)
    assert key.startswith("raw/xbrl/") and key.endswith(".xml.gz")
    assert sink.objects[key] == gzip.compress(XML, mtime=0)
    assert xbrl_store.get(sink, URL) == XML


def test_nothing_stored_when_not_the_platform_sink(settings):
    sink = LocalSink(settings)
    xbrl_store.put(sink, URL, XML)
    assert xbrl_store.get(sink, URL) is None
    assert xbrl_store.get(None, URL) is None


def test_pipeline_reads_r2_before_the_exchange_and_puts_after_a_download(settings):
    sink = FakeSink()
    p = Pipeline.__new__(Pipeline)
    p.settings, p.sink = settings, sink
    client = Client()
    assert p._xbrl_file(URL, client) == XML and client.calls == 1
    assert gzip.decompress(sink.objects[xbrl_store.key(URL)]) == XML
    # another runner: no local copy, R2 answers, the exchange is not asked
    for f in settings.text_cache_dir.rglob("*.xml.gz"):
        f.unlink()
    assert p._xbrl_file(URL, client) == XML and client.calls == 1


def test_seed_fetch_order_local_then_r2_then_exchange(tmp_path):
    sink = FakeSink()
    client = Client()
    assert seed._fetch(client, URL, tmp_path, sink) == XML and client.calls == 1
    assert seed._fetch(client, URL, tmp_path, sink) == XML and client.calls == 1   # local
    other = tmp_path / "other"
    assert seed._fetch(client, URL, other, sink) == XML and client.calls == 1   # R2
    assert seed._fetch(client, URL, other, None) == XML   # no sink: local copy written from R2 earlier


def test_cap_stops_puts_but_not_gets(monkeypatch):
    sink = FakeSink()
    xbrl_store.put(sink, URL, XML)
    monkeypatch.setenv("XBRL_STORE_MAX_MB", "0.00001")   # 10 bytes
    xbrl_store.put(sink, URL + "2", XML)
    assert xbrl_store.key(URL + "2") not in sink.objects
    assert xbrl_store.get(sink, URL) == XML


def test_total_is_read_once_and_saved_at_exit():
    sink = FakeSink()
    sink.objects[xbrl_store.TOTAL_KEY] = json.dumps({"bytes": 1000}).encode()
    xbrl_store.put(sink, URL, XML)
    xbrl_store.flush()
    size = len(gzip.compress(XML, mtime=0))
    assert json.loads(sink.objects[xbrl_store.TOTAL_KEY])["bytes"] == 1000 + size


def test_a_full_store_on_start_blocks_puts(monkeypatch):
    sink = FakeSink()
    sink.objects[xbrl_store.TOTAL_KEY] = json.dumps({"bytes": 500_000_000}).encode()
    xbrl_store.put(sink, URL, XML)
    assert xbrl_store.key(URL) not in sink.objects


def test_sink_failures_never_break_a_download(tmp_path):
    sink = FakeSink(fail_put=True, fail_get=True)
    client = Client()
    assert seed._fetch(client, URL, tmp_path, sink) == XML
    xbrl_store.put(sink, URL, XML)
    assert xbrl_store.get(sink, URL) is None


def test_referee_files_use_the_store():
    sink = FakeSink()
    xbrl_store.put(sink, URL, XML)

    class Nse(Client):
        pass

    files = CompanyFiles(Nse(), "ABC", None, sink)
    files.rows = {"Q1 FY26": type("R", (), {"xbrl_url": URL})()}
    files.file_for("Q1 FY26")
    assert files.nse.calls == 0 and files.calls["files"] == 0


def test_a_gone_file_is_that_quarter_only_and_a_refusal_still_raises(tmp_path):
    """One dead XBRL file (404/410) is a gap for its quarter, not an error that loses the company's other quarters; any
    other HTTP error (a 403 refusal) still raises so the run stops."""
    import httpx
    from bse_intel import seed

    class Gone:
        def __init__(self, status):
            self.status = status

        def download(self, url, max_bytes=0):
            req = httpx.Request("GET", url)
            raise httpx.HTTPStatusError("x", request=req, response=httpx.Response(self.status, request=req))

    assert seed._fetch(Gone(404), URL, tmp_path, None) is None
    assert seed._fetch(Gone(410), URL, tmp_path, None) is None
    with pytest.raises(httpx.HTTPStatusError):
        seed._fetch(Gone(403), URL, tmp_path, None)
