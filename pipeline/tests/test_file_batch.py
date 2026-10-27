"""F213: NSE/BSE files are downloaded in batches of FILE_BATCH (100) with a pause between batches; a batch is a size, not a cap."""

from __future__ import annotations

import httpx
import pytest

from bse_intel import seed
from bse_intel import settings as settings_module
from bse_intel.file_batch import files
from bse_intel.nse import NseClient

ARCH = "https://nsearchives.nseindia.com/corporate/a.pdf"
XML = b"<?xml version='1.0'?><xbrl/>"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for name in ("FILE_BATCH", "FILE_BATCH_PAUSE_S"):
        monkeypatch.delenv(name, raising=False)


def nse_client():
    client = NseClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=XML)), sleep=lambda s: None,
                       retries=1, pause=(0, 0))
    client._warmed = True
    return client


def test_defaults():
    assert settings_module.file_batch() == 100 and settings_module.file_batch_pause_s() == 0.0


def test_default_pause_is_zero_so_no_sleep_happens():
    naps = []
    files.sleep = naps.append
    for _ in range(250):
        files.take()
    assert naps == [] and files.pauses == 2 and files.summary() == "files 250 in 3 batches"


def test_the_pause_comes_after_every_100th_file_and_not_before(monkeypatch):
    monkeypatch.setenv("FILE_BATCH_PAUSE_S", "30")
    naps = []
    files.sleep = naps.append
    for _ in range(100):
        files.take()
    assert naps == [] and files.used == 100          # exactly one batch: no pause, nothing waits after the last file
    files.take()                                      # the 101st
    assert naps == [30.0]
    for _ in range(99):
        files.take()
    assert naps == [30.0] and files.used == 200
    files.take()
    assert naps == [30.0, 30.0] and files.used == 201 and files.summary() == "files 201 in 3 batches"


def test_no_delay_below_one_batch_and_the_run_is_never_stopped(monkeypatch):
    monkeypatch.setenv("FILE_BATCH_PAUSE_S", "30")
    naps = []
    files.sleep = naps.append
    for _ in range(40):
        files.take()
    assert naps == [] and files.summary() == "files 40 in 1 batch"
    for _ in range(350):                              # past any number: it keeps going
        files.take()
    assert files.used == 390 and len(naps) == 3


def test_batch_and_pause_settings(monkeypatch):
    naps = []
    files.sleep = naps.append
    monkeypatch.setenv("FILE_BATCH", "2")
    monkeypatch.setenv("FILE_BATCH_PAUSE_S", "5")
    for _ in range(5):
        files.take()
    assert naps == [5.0, 5.0] and files.summary() == "files 5 in 3 batches"
    files.reset()
    files.sleep = naps.append
    monkeypatch.setenv("FILE_BATCH", "0")             # off: no pause at all
    naps.clear()
    for _ in range(300):
        files.take()
    assert naps == []


def test_nse_downloads_are_counted_but_lists_are_not():
    client = nse_client()
    client._get("https://www.nseindia.com/api/x")     # a list / JSON call: not a file
    assert files.used == 0
    assert client.fetch(ARCH) == XML and client.download(ARCH) == XML
    assert files.used == 2


def test_the_nse_client_pauses_at_the_101st_file(monkeypatch):
    monkeypatch.setenv("FILE_BATCH_PAUSE_S", "30")
    naps = []
    files.sleep = naps.append
    client = nse_client()
    for _ in range(101):
        client.download(ARCH)
    assert naps == [30.0]


def test_bse_downloads_are_counted():
    from bse_intel.adapters.bse import BSEClient
    from bse_intel.bse import BseClient
    naps = []
    files.sleep = naps.append
    monkey = BseClient.__new__(BseClient)
    with pytest.raises(AttributeError):               # counted first; the bare object then has no session
        monkey.download("https://www.bseindia.com/xml-data/corpfiling/AttachLive/x.pdf")
    assert files.used == 1
    with pytest.raises(Exception):
        BSEClient.__new__(BSEClient).shareholding_xbrl("/x.xml")
    assert files.used == 2


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
