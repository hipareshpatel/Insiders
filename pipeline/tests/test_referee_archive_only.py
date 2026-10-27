"""F222: the screener referee's archive-only mode. File names come from memory (lab.file), the URL is rebuilt on the archive
host, the XBRL store is read first, and no results list is ever fetched. Fake NSE client, no network."""

import pytest

from bse_intel import screener_xbrl_referee as sx
from bse_intel import seed, xbrl, xbrl_store
from bse_intel.dossier import label
from bse_intel.models import FinancialMetric

NAME = "INTEGRATED_FILING_INDAS_1664294_06052026105412_WEB.xml"
BASE = "https://nsearchives.nseindia.com/corporate/xbrl/"
URL = BASE + NAME


def result(values, basis="CONSOLIDATED"):
    return xbrl.XbrlResult("RESULTS", basis, None, [FinancialMetric(metric=m, period=p, value=v) for (m, p), v in values.items()],
                           template="INDAS")


class FakeNse:
    def __init__(self, files):
        self.files, self.list_calls, self.downloads = files, [], []

    def financial_results(self, symbol):
        self.list_calls.append(symbol)
        raise AssertionError("archive-only mode must not call the results list")

    def download(self, url, max_bytes=0):
        self.downloads.append(url)
        return self.files.get(url)


def row(period="Q2FY26", metric="revenue", ours=1000.0, theirs=1100.0, basis="CONSOLIDATED"):
    return {"scrip": "1", "symbol": "DEMO", "basis": basis, "period": period, "metric": metric, "class": "mismatch",
            "memory_value": ours, "screener_value": theirs, "shifted": [], "note": ""}


def dossier(file=URL, basis="CONSOLIDATED", sources=False):
    lab = {**label("file", "results", "2026-05-06T18:00:00+05:30", basis=basis, ok=True), **({"file_url": file} if file else {})}
    entry = {"metric": "revenue", "period": "Q2FY26", "value": 1000.0, "source_news_id": "xbrl:res:1:Q2FY26", "basis": basis, "lab": lab}
    if sources:
        entry = {"metric": "revenue", "period": "Q2FY26", "value": 1000.0, "source_news_id": "xbrl:res:1:Q2FY26",
                 "sources": [{"news_id": "xbrl:res:1:Q2FY26", "basis": basis, "lab": lab},
                             {"news_id": "card:9", "basis": basis, "lab": {"by": "ai"}}]}
    return {"financial_metrics": [entry]}


@pytest.fixture
def parsed(monkeypatch):
    table = {}
    monkeypatch.setattr(xbrl, "parse", lambda data: table.get(data))
    return table


def names(d):
    return lambda scrip, basis: sx.file_names(d, scrip, basis or None)


def test_the_url_is_rebuilt_from_memorys_file_name_and_no_list_is_fetched(parsed):
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0})
    nse = FakeNse({URL: b"q2"})
    out = sx.run(nse, [row()], names_for=names(dossier()))
    assert nse.list_calls == [] and nse.downloads == [URL]
    assert out["rows"][0]["verdict"] == "ours_matches_official" and out["rows"][0]["official_file"] == NAME
    assert out["calls"] == {"results_lists": 0, "files": 1, "store_hits": 0} and out["archive_only"] is True
    assert "0 results lists, 1 files downloaded, 0 from the store (archive only)" in sx.render(out)


def test_the_name_is_found_among_several_sources(parsed):
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0})
    nse = FakeNse({URL: b"q2"})
    sx.run(nse, [row()], names_for=names(dossier(sources=True)))
    assert nse.downloads == [URL]


def test_a_store_hit_downloads_nothing(parsed, monkeypatch):
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0})
    monkeypatch.setattr(xbrl_store, "get", lambda sink, url: b"q2" if url == URL else None)
    nse = FakeNse({})
    out = sx.run(nse, [row(), row(metric="revenue", ours=1000.0, theirs=900.0)], names_for=names(dossier()))
    assert nse.downloads == [] and nse.list_calls == []
    assert out["calls"] == {"results_lists": 0, "files": 0, "store_hits": 1}   # one file, read once
    assert {r["verdict"] for r in out["rows"]} == {"ours_matches_official"}


def test_no_file_name_in_memory_is_not_run(parsed):
    nse = FakeNse({URL: b"q2"})
    for d in (None, dossier(file=""), dossier(basis="STANDALONE")):
        out = sx.run(nse, [row()], names_for=names(d))
        r = out["rows"][0]
        assert r["verdict"] == "not_run" and "no file name in memory" in r["reason"]
    assert nse.downloads == [] and nse.list_calls == []


def test_a_file_the_archive_lacks_is_not_run(parsed):
    nse = FakeNse({})   # the archive serves nothing
    out = sx.run(nse, [row()], names_for=names(dossier()))
    r = out["rows"][0]
    assert r["verdict"] == "not_run" and "file not on the archive" in r["reason"]
    assert nse.list_calls == [] and out["verdicts"] == {"not_run": 1}


def test_a_file_without_the_figure_is_still_no_file(parsed):
    parsed[b"q2"] = result({("pat", "Q2FY26"): 5.0})
    nse = FakeNse({URL: b"q2"})
    d = dossier()
    d["financial_metrics"].append({"metric": "pat", "period": "Q3FY26", "value": 1.0, "source_news_id": "xbrl:res:1:Q3FY26",
                                   "basis": "CONSOLIDATED", "lab": {"by": "file", "file_url": BASE + "Q3.xml"}})
    r = sx.run(nse, [row()], names_for=names(d))["rows"][0]
    assert r["verdict"] == "not_run"   # the next quarter's file (named, but not on the archive) was needed too
    d["financial_metrics"].append({"metric": "pat", "period": "Q2FY27", "value": 1.0, "source_news_id": "xbrl:res:1:Q2FY27",
                                   "basis": "CONSOLIDATED", "lab": {"by": "file", "file_url": BASE + "Q2FY27.xml"}})
    files = {URL: b"q2", BASE + "Q3.xml": b"q2", BASE + "Q2FY27.xml": b"q2"}
    r = sx.run(FakeNse(files), [row()], names_for=names(d))["rows"][0]
    assert r["verdict"] == "no_file"


def test_the_default_mode_is_unchanged(parsed):
    from bse_intel.nse import ResultsFiling
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0})

    class Listed(FakeNse):
        def financial_results(self, symbol):
            self.list_calls.append(symbol)
            return [ResultsFiling(period="Quarterly", consolidated=True, audited="Audited", filed_at="2026-01-01", xbrl_url=URL,
                                  is_bank=False, period_end="2025-09-30")]
    nse = Listed({URL: b"q2"})
    out = sx.run(nse, [row()])
    assert nse.list_calls == ["DEMO"] and out["calls"]["results_lists"] == 1 and out["archive_only"] is False


def test_the_seed_stamps_the_file_name_on_its_figures():
    d = {"financial_metrics": [
        {"metric": "revenue", "period": "Q2FY26", "source_news_id": "xbrl:res:1:Q2FY26", "lab": {"by": "file"}},
        {"metric": "pat", "period": "Q2FY26", "source_news_id": "xbrl:res:1:Q2FY26",
         "sources": [{"news_id": "xbrl:res:1:Q2FY26", "lab": {"by": "file"}}, {"news_id": "card:9", "lab": {"by": "ai"}}]},
        {"metric": "pat", "period": "Q1FY26", "source_news_id": "xbrl:res:1:Q1FY26", "lab": {"by": "file"}}]}
    assert seed.stamp_file(d, "xbrl:res:1:Q2FY26", URL) == 2
    assert sx.file_names(d, "1", "CONSOLIDATED") == {"Q2FY26": URL}
    assert "file_url" not in d["financial_metrics"][2]["lab"] and "file_url" not in d["financial_metrics"][1]["sources"][1]["lab"]


class MemSink:
    def __init__(self):
        self.d = {}

    def get_dossier(self, scrip):
        return self.d.get(scrip)

    def put_dossier(self, scrip, dossier):
        self.d[scrip] = dossier


def _seeded(url, from_nse):
    sink = MemSink()
    parsed = result({("revenue", "Q2FY26"): 1000.0})
    seed._write_results(sink, "1", "Demo", None, "Q2FY26", "2026-05-06", url, parsed, seed.SeedStats(), from_nse)
    return sink.d["1"]


def test_only_an_nse_file_is_stamped_and_with_its_full_url():
    odd = "https://nsearchives.nseindia.com/other/folder/X_1.xml"   # not proven to always sit in /corporate/xbrl/
    assert sx.file_names(_seeded(odd, True), "1", "CONSOLIDATED") == {"Q2FY26": odd}
    bse = "https://www.bseindia.com/XBRLFILES/FourOne/x.xml"
    assert sx.file_names(_seeded(bse, False), "1", "CONSOLIDATED") == {}   # a BSE-sourced figure gets no stamp


def test_archive_only_reads_the_stored_url_unchanged_and_its_store_key_matches(parsed, monkeypatch):
    odd = "https://nsearchives.nseindia.com/other/folder/X_1.xml"
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0})
    asked = []
    monkeypatch.setattr(xbrl_store, "get", lambda sink, url: asked.append(xbrl_store.key(url)) or None)
    nse = FakeNse({odd: b"q2"})
    sx.run(nse, [row()], names_for=names(_seeded(odd, True)))
    assert nse.downloads == [odd] and asked == [xbrl_store.key(odd)]


# --- parallel reads (owner 27 Oct 2026: "use multiple downloads at once") ----------------------------------------------

def _many(n=12):
    """n companies, each with one memory file; returns (rows, dossiers by scrip, files by url)."""
    rows, dossiers, files = [], {}, {}
    for i in range(n):
        scrip, name = str(100 + i), f"F{i}.xml"
        rows.append({**row(), "scrip": scrip, "symbol": f"S{i}"})
        d = dossier(file=BASE + name)
        d["financial_metrics"][0]["source_news_id"] = f"xbrl:res:{scrip}:Q2FY26"
        dossiers[scrip] = d
        files[BASE + name] = b"q2" if i % 3 else None   # every third file is not on the archive
    return rows, dossiers, files


def test_parallel_archive_reads_equal_serial_ones(parsed):
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0})
    rows, dossiers, files = _many()

    def pick(scrip, basis):
        return sx.file_names(dossiers[scrip], scrip, basis)
    serial = sx.run(FakeNse(dict(files)), rows, names_for=pick)
    nse = FakeNse(dict(files))
    par = sx.run(nse, rows, names_for=pick, workers=4)
    key = lambda out: [(r["scrip"], r["verdict"], r["reason"]) for r in out["rows"]]  # noqa: E731
    assert key(par) == key(serial)
    assert par["verdicts"] == serial["verdicts"] and par["calls"] == serial["calls"] and par["companies"] == serial["companies"]
    assert nse.list_calls == [] and len(nse.downloads) == 12


def test_a_refusal_stops_the_parallel_run(parsed):
    from bse_intel.nse import SourceBlockedError
    rows, dossiers, files = _many()

    class Refused(FakeNse):
        def download(self, url, max_bytes=0):
            raise SourceBlockedError("refused")
    out = sx.run(Refused({}), rows, names_for=lambda s, b: sx.file_names(dossiers[s], s, b), workers=4)
    assert out["blocked"] is True and {r["verdict"] for r in out["rows"]} == {"not_run"}
    assert any(r["reason"] == "blocked" for r in out["rows"])


def test_the_archive_pace_is_safe_under_threads_and_slows_back_after_a_refusal():
    import httpx
    from concurrent.futures import ThreadPoolExecutor
    from bse_intel.nse import NseClient
    sleeps, state = [], {"n": 0}

    def handler(request):
        state["n"] += 1
        status = 503 if state["n"] == 5 else 200
        return httpx.Response(status, content=b"<?xml version='1.0'?><xbrl/>" if status == 200 else b"")
    client = NseClient(transport=httpx.MockTransport(handler), sleep=sleeps.append, retries=2, archive_pause=(0.0, 0.0))
    client._warmed = True
    with ThreadPoolExecutor(8) as pool:
        got = list(pool.map(lambda _: client.download(URL), range(20)))
    assert all(got)                         # the refused request was retried and served
    assert client._archive_pause is None    # a refusal puts the archive back on the API pace for the rest of the run
    assert sleeps                           # and later requests then wait
