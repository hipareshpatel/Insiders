"""F169: the archive host (nsearchives) has its own pace, lock and counter; a refusal from it puts it back on the API's."""

import logging

import httpx
import pytest

from bse_intel.nse import NseClient, SourceBlockedError, archive_pause_from_env

API = "https://www.nseindia.com/api/x"
ARCH = "https://nsearchives.nseindia.com/corporate/xbrl/a.xml"
XML = b"<?xml version='1.0'?><xbrl/>"


def make(status=200, archive_pause=None, retries=1):
    sleeps = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "nsearchives.nseindia.com":
            return httpx.Response(status, content=XML if status == 200 else b"")
        return httpx.Response(200, json={"data": []})

    client = NseClient(transport=httpx.MockTransport(handler), sleep=sleeps.append, retries=retries,
                       archive_pause=archive_pause)
    client._warmed = True
    return client, sleeps


def test_default_archive_shares_the_api_pace(monkeypatch):
    monkeypatch.delenv("NSE_ARCHIVE_PAUSE_SECONDS", raising=False)
    assert archive_pause_from_env() is None
    client, sleeps = make()
    client._get(API)
    client.download(ARCH)
    client.download(ARCH)
    assert len(sleeps) == 2 and all(3.0 <= s <= 5.0 for s in sleeps)


def test_archive_pause_env_format(monkeypatch):
    monkeypatch.setenv("NSE_ARCHIVE_PAUSE_SECONDS", "0,0")
    assert archive_pause_from_env() == (0.0, 0.0)
    monkeypatch.setenv("NSE_ARCHIVE_PAUSE_SECONDS", "0.3,0.5")
    assert archive_pause_from_env() == (0.3, 0.5)
    for bad in ("2", "fast", "3,1", "-1,0"):
        monkeypatch.setenv("NSE_ARCHIVE_PAUSE_SECONDS", bad)
        assert archive_pause_from_env() is None


def test_archive_and_api_are_paced_independently():
    client, sleeps = make(archive_pause=(0.0, 0.0))
    client._get(API)                      # first API call: no pause
    for _ in range(3):
        client.download(ARCH)             # archive: its own counter, no pause at 0,0
    assert sleeps == []
    client._get(API)                      # second API call keeps the 3-5 s pace
    assert len(sleeps) == 1 and 3.0 <= sleeps[0] <= 5.0
    assert client._lock is not client._archive_lock


def test_archive_pause_range_applies_to_archive_only():
    client, sleeps = make(archive_pause=(0.3, 0.3))
    client.download(ARCH)
    client.download(ARCH)
    assert sleeps == [0.3]


@pytest.mark.parametrize("status", [403, 429, 503])
def test_a_refusal_puts_the_archive_back_on_the_api_pace(status, caplog):
    client, sleeps = make(status=status, archive_pause=(0.0, 0.0))
    with caplog.at_level(logging.WARNING, logger="bse_intel.nse"):
        with pytest.raises((SourceBlockedError, RuntimeError)):
            client.download(ARCH)
    assert client._archive_pause is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and str(status) in r.getMessage()]
    assert len(warnings) == 1
    client._client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=XML)))
    client.download(ARCH)
    client.download(ARCH)
    assert sleeps and all(3.0 <= s <= 5.0 for s in sleeps)


def test_the_warning_is_logged_once(caplog):
    client, _ = make(status=403, archive_pause=(0.0, 0.0))
    with caplog.at_level(logging.WARNING, logger="bse_intel.nse"):
        for _ in range(3):
            with pytest.raises(SourceBlockedError):
                client.download(ARCH)
    assert len([r for r in caplog.records if "archive pace" in r.getMessage()]) == 1


def test_a_404_is_a_missing_file_not_a_refusal():
    client, _ = make(status=404, archive_pause=(0.0, 0.0))
    assert client.fetch(ARCH) is None
    assert client._archive_pause == (0.0, 0.0)
    with pytest.raises(httpx.HTTPStatusError):
        client.download(ARCH)
    assert client._archive_pause == (0.0, 0.0)


def test_an_api_refusal_does_not_touch_the_archive_pace():
    def handler(request):
        return httpx.Response(403)
    client = NseClient(transport=httpx.MockTransport(handler), sleep=lambda s: None, retries=1, archive_pause=(0.0, 0.0))
    client._warmed = True
    with pytest.raises(SourceBlockedError):
        client._get(API)
    assert client._archive_pause == (0.0, 0.0)
