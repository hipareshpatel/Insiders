"""F191 on the live path (30 Oct 2026): the filing's own results XBRL is read from our R2 copy when we hold it, and a fresh
download is kept there. The audit of the live write path found `_xbrl` downloading the period's own file without keeping it."""
from dataclasses import replace

from conftest import FakeProvider

from bse_intel import xbrl_store
from bse_intel.ai.gateway import AIGateway
from bse_intel.models import Filing
from bse_intel.pipeline import Pipeline
from bse_intel.sinks.local import LocalSink


def _pipeline(settings, tmp_path):
    settings = replace(settings, text_cache_dir=None)
    gateway = AIGateway(settings.load_toml("providers.toml"), client_factory=lambda *a: FakeProvider({}), env={})
    return Pipeline(settings, LocalSink(settings), gateway, bse=None, sleep=lambda s: None)


def _filing():
    return Filing(news_id="nse-1", scrip_code="500001", company_name="Demo", category="Result", subcategory="",
                  headline="Results", attachment_url="https://x/a.pdf", xbrl_url="https://x/a.xml",
                  filed_at="2026-10-30T18:00:00+05:30", filing_date="2026-10-30")


def test_a_downloaded_results_file_is_kept_and_our_copy_is_read_first(settings, tmp_path, monkeypatch):
    store, fetched = {}, []
    monkeypatch.setattr(xbrl_store, "put", lambda sink, url, data: store.__setitem__(url, data) or True)
    monkeypatch.setattr(xbrl_store, "get", lambda sink, url: store.get(url))
    p = _pipeline(settings, tmp_path)
    p._attachment = lambda url, cap: fetched.append(url) or b"<xbrl/>"
    p._xbrl(_filing())
    assert store == {"https://x/a.xml": b"<xbrl/>"} and fetched == ["https://x/a.xml"]
    p._xbrl(_filing())
    assert fetched == ["https://x/a.xml"], "the second read is our copy, not the exchange"
