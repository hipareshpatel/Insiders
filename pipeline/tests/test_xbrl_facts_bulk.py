"""``xbrl-facts --from-nse`` (owner, 28 Oct 2026: download now every results XBRL and annual-report XBRL of the universe): NSE's own list
per company, the seed's latest quarters in both bases, each file not stored fetched through the seed's fetch and its facts saved at
once, no memory write; shards, a time budget, refusals that stop a shard and other failures that are counted by reason. The client
is the real ``NseClient`` over a mock transport, so its download path, its refusals and the file cap are the ones a run uses."""

from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path

import httpx
import pytest
from test_xbrl_facts import SHAREHOLDING, TITAN, FakeSink

from bse_intel import cli, xbrl_facts, xbrl_store
from bse_intel.file_cap import files
from bse_intel.nse import ResultsFiling, NseClient

BASE = "https://nsearchives.nseindia.com/corporate/xbrl/"
XML_STAMP = "17102023091927"


def furl(n: str, stamp: str = XML_STAMP) -> str:
    return f"{BASE}INTEGRATED_FILING_INDAS_{n}_{stamp}_WEB.xml"


def irow(n: str, qe: str, consolidated: bool, **more) -> dict:
    """A row of NSE's integrated list, with timestamp fields of its own (and one the client's parser never reads)."""
    row = {"xbrl": furl(n), "qe_Date": qe, "consolidated": "Consolidated" if consolidated else "Non-Consolidated",
           "type_Sub": "Original", "broadcast_Date": "17-Oct-2023 21:19:12", "creation_Date": "17-Oct-2023 21:10:00",
           "revised_Date": None, "submission_Time": "17-Oct-2023 21:12:00", "symbol": "X"}
    row.update(more)
    return row


class Site:
    """NSE in memory: the two result lists by symbol and the files by url (status, body); every request is kept."""

    def __init__(self, integrated: dict[str, list[dict]], served: dict[str, tuple[int, bytes]] | None = None, older=None,
                 default=(200, TITAN), delay: float = 0.0, annual: dict[str, list[dict]] | None = None):
        self.integrated, self.older, self.served, self.default, self.delay = integrated, older or {}, served or {}, default, delay
        self.annual = annual or {}
        self.home = (200, b"<html>NSE</html>")
        self.requests: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        if request.url.path == "/":          # the client's warm-up visit to the home page
            return httpx.Response(self.home[0], content=self.home[1])
        symbol = request.url.params.get("symbol", "")
        if request.url.path.endswith("/integrated-filing-results"):
            return httpx.Response(200, json={"data": self.integrated.get(symbol, [])})
        if request.url.path.endswith("/corporates-financial-results"):
            return httpx.Response(200, json=self.older.get(symbol, []))
        if request.url.path.endswith("/annual-reports-xbrl"):
            return httpx.Response(200, json={"data": self.annual.get(symbol, [])})
        if self.delay:
            time.sleep(self.delay)
        status, body = self.served.get(url, self.default)
        return httpx.Response(status, content=body)

    @property
    def lists(self) -> list[str]:
        return [u for u in self.requests if "nsearchives" not in u]

    @property
    def file_requests(self) -> list[str]:
        return [u for u in self.requests if "nsearchives" in u]

    def client(self, retries: int = 1, warmed: bool = True) -> NseClient:
        nse = NseClient(transport=httpx.MockTransport(self.handler), sleep=lambda s: None, retries=retries, pause=(0, 0))
        nse._warmed = warmed
        return nse


class SpySink(FakeSink):
    """The R2 side of FakeSink, and memory off limits: a from-NSE run must write no dossier and not even read one."""

    def get_dossier(self, scrip_code):
        raise AssertionError("xbrl-facts --from-nse must not read memory")

    def put_dossier(self, scrip_code, dossier):
        raise AssertionError("xbrl-facts --from-nse must not write memory")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for name in ("FILE_CAP", "FILE_CAP_SHARDS", "FILE_CAP_USED", "FILE_CAP_MARKER_DIR", "GITHUB_ENV", "XBRL_STORE_MAX_MB"):
        monkeypatch.delenv(name, raising=False)
    files.reset()
    xbrl_store.reset()
    yield
    files.reset()
    xbrl_store.reset()


COMPANIES = [("1", "AAA"), ("2", "BBB")]
Q2 = "30-SEP-2023"
Q1 = "30-JUN-2023"


def two_companies() -> Site:
    return Site({"AAA": [irow("a1", Q2, True), irow("a2", Q2, False)], "BBB": [irow("b1", Q2, True), irow("b2", Q2, False)]})


def run(site: Site, sink=None, companies=COMPANIES, retries: int = 1, warmed: bool = True, **kw):
    sink = sink if sink is not None else SpySink()
    kw.setdefault("download", True)
    return sink, xbrl_facts.run(sink, companies, client=site.client(retries, warmed), from_nse=True, **kw)


# --- the selection and the shard -----------------------------------------------------------------------------------------

def test_shard_slice_is_deterministic_and_covers_everyone_once():
    companies = [(str(i), f"S{i}") for i in range(1, 30)]
    slices = [xbrl_facts.shard_slice(companies, i, 16) for i in range(16)]
    assert sorted(sum(slices, [])) == sorted(companies)                       # everyone, once
    assert sum(len(s) for s in slices) == len(companies)
    assert slices == [xbrl_facts.shard_slice(list(reversed(companies)), i, 16) for i in range(16)]   # whatever the input order
    assert xbrl_facts.shard_slice(companies, 0, 1) == sorted(companies)
    for bad in ((0, 17), (16, 16), (-1, 4), (0, 0)):
        with pytest.raises(ValueError):
            xbrl_facts.shard_slice(companies, *bad)


def test_select_files_is_the_seeds_selection_with_both_bases():
    rows = []
    for i in range(16):                                   # 16 quarters back from Dec 2025, both bases
        year, month = divmod(2025 * 12 + 11 - 3 * i, 12)
        end = f"{year}-{month + 1:02d}-{[31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month]:02d}"
        for consolidated in (True, False):
            rows.append(ResultsFiling("Quarterly", consolidated, "", "2026-01-01", f"https://x/{end}-{consolidated}.xml", False,
                                      period_end=end))
    chosen = xbrl_facts.select_files(rows)
    ends = {r.period_end for _, _, r in chosen}
    assert len(ends) == 13 and "2022-03-31" in ends                      # the 12 latest quarters, and the March quarter before them
    assert sum(1 for _, b, _ in chosen if b == "CONSOLIDATED") == sum(1 for _, b, _ in chosen if b == "STANDALONE") == len(ends)
    assert max(ends) == "2025-12-31" and ("Q3FY26", "CONSOLIDATED") in {(p, b) for p, b, _ in chosen}
    assert "2022-12-31" not in ends and "2022-09-30" not in ends         # older than the 12 latest quarters and not a March quarter


# --- a run, a dry run, the skips -----------------------------------------------------------------------------------------

def test_a_run_lists_each_company_once_fetches_both_bases_saves_facts_and_the_raw_file_and_writes_no_memory():
    site = two_companies()
    sink, out = run(site)
    assert len(site.lists) == 4 and out["lists"] == 2                     # two requests a company (integrated and older list), one list
    assert len(site.file_requests) == 4 and files.used == 4 and out["downloaded"] == 4 and out["facts_saved"] == 4
    for scrip, period in (("1", "Q2FY24"), ("2", "Q2FY24")):
        assert xbrl_facts.key(scrip, period, "CONSOLIDATED") in sink.objects
        assert xbrl_facts.key(scrip, period, "STANDALONE") in sink.objects
    assert xbrl_store.key(furl("a1")) in sink.objects                      # each file kept raw too (F191)
    assert not [k for k in sink.objects if k.startswith("memory/")]        # no memory, no dossier (SpySink raises on any)
    assert out["stopped"] == "" and out["refusal"] is None and out["failed_reasons"] == {}


def test_a_dry_run_without_download_asks_nse_for_nothing():
    site = two_companies()
    sink, out = run(site, dry_run=True, download=False)
    assert site.requests == [] and files.used == 0 and out["lists"] == 0 and out["lists_skipped"]["dry_run"] == 2
    assert sink.objects == {}


def test_a_dry_run_with_download_lists_and_fetches_no_file_and_writes_nothing():
    site = two_companies()
    sink, out = run(site, dry_run=True)
    assert len(site.lists) == 4 and site.file_requests == [] and files.used == 0
    assert out["would_download"] == 4 and out["downloaded"] == 0 and sink.objects == {}


def test_a_from_nse_run_that_would_download_needs_a_client_and_the_flag():
    with pytest.raises(ValueError):
        xbrl_facts.run(SpySink(), COMPANIES, from_nse=True)
    with pytest.raises(ValueError):
        xbrl_facts.run(SpySink(), COMPANIES, from_nse=True, client=two_companies().client())      # no download=True


def test_a_rerun_skips_stored_files_and_the_list_of_a_company_whose_every_period_is_stored():
    site = two_companies()
    sink, first = run(site)
    assert first["downloaded"] == 4
    before = len(site.requests)
    sink, second = run(site, sink=sink)
    assert len(site.requests) == before                                    # no list, no file: the markers say everything is stored
    assert second["lists"] == 0 and second["lists_skipped"]["stored"] == 2 and second["downloaded"] == 0 and files.used == 4


def test_without_a_marker_the_list_is_asked_for_but_no_stored_file_is_fetched_again():
    site = two_companies()
    sink, _ = run(site)
    for scrip in ("1", "2"):
        del sink.objects[xbrl_facts.listed_key(scrip)]
    before = len(site.file_requests)
    sink, out = run(site, sink=sink)
    assert out["lists"] == 2 and len(site.file_requests) == before and out["skipped_stored"] == 4 and out["downloaded"] == 0


def test_a_stale_marker_asks_for_the_list_again_and_a_missing_period_is_fetched():
    site = Site({"AAA": [irow("a1", Q2, True)]})
    sink, _ = run(site, companies=[("1", "AAA")])
    marker = json.loads(sink.objects[xbrl_facts.listed_key("1")])
    assert marker["files"] == [["Q2FY24", "CONSOLIDATED"]] and marker["gone"] == []
    marker["listed_on"] = "2000-01-01"
    sink.objects[xbrl_facts.listed_key("1")] = json.dumps(marker).encode()
    site.integrated["AAA"].append(irow("a3", Q1, True))                   # a new filing since the last list
    sink, out = run(site, sink=sink, companies=[("1", "AAA")])
    assert out["lists"] == 1 and out["downloaded"] == 1 and out["skipped_stored"] == 1
    assert xbrl_facts.key("1", "Q1FY24", "CONSOLIDATED") in sink.objects


def test_a_fresh_marker_with_a_period_whose_facts_are_gone_asks_for_the_list_again():
    site = Site({"AAA": [irow("a1", Q2, True)]})
    sink, _ = run(site, companies=[("1", "AAA")])
    del sink.objects[xbrl_facts.key("1", "Q2FY24", "CONSOLIDATED")]
    sink, out = run(site, sink=sink, companies=[("1", "AAA")])
    assert out["lists"] == 1 and xbrl_facts.key("1", "Q2FY24", "CONSOLIDATED") in sink.objects


def test_a_stored_raw_file_gives_its_facts_without_a_request():
    site = Site({"AAA": [irow("a1", Q2, True)]})
    sink = SpySink()
    xbrl_store.put(sink, furl("a1"), TITAN)
    sink, out = run(site, sink=sink, companies=[("1", "AAA")])
    assert site.file_requests == [] and out["from_store"] == 1 and out["downloaded"] == 0 and out["facts_saved"] == 1


def test_force_reads_the_stored_facts_again_from_the_stored_raw_file():
    site = Site({"AAA": [irow("a1", Q2, True)]})
    sink, _ = run(site, companies=[("1", "AAA")])
    before = len(site.file_requests)
    sink, out = run(site, sink=sink, companies=[("1", "AAA")], force=True)
    assert len(site.file_requests) == before and out["from_store"] == 1 and out["facts_saved"] == 1


# --- failures: refusals stop the shard, the rest are counted ---------------------------------------------------------------

@pytest.mark.parametrize("status, body, retries", [
    (403, b"<html><body>Access Denied</body></html>", 1),
    (429, b"Too Many Requests", 1),
    (503, b"<html>Service Unavailable - Reference #18.1234</html>", 3),
    (200, b"<!DOCTYPE html><html><title>Just a moment...</title>cloudflare challenge</html>", 1),
])
def test_a_refusal_stops_the_shard_at_once_with_its_status_and_body_and_keeps_what_was_saved(status, body, retries, caplog):
    site = two_companies()
    site.served[furl("a2")] = (status, body)                   # the second file of the first company is refused
    with caplog.at_level("ERROR"):
        sink, out = run(site, retries=retries)
    assert "refused" in out["stopped"] and out["capped"] is False and out["out_of_time"] is False
    assert out["refusal"]["status"] == status and body[:40].decode() in out["refusal"]["body_head"]
    assert not any("BBB" in u for u in site.requests)                  # the second company is never asked for
    assert out["downloaded"] == 1 and xbrl_facts.key("1", "Q2FY24", "CONSOLIDATED") in sink.objects   # the first file was saved
    assert xbrl_store.key(furl("a1")) in sink.objects
    assert xbrl_facts.listed_key("1") not in sink.objects              # the company was not finished: no marker
    assert any(f"HTTP {status}" in r.getMessage() and body[:20].decode() in r.getMessage() for r in caplog.records)
    assert len([u for u in site.requests if u == furl("a2")]) == retries    # the client's own retries, then the stop


def test_a_refusal_on_a_company_list_stops_the_shard_too():
    class Refusing(Site):
        def handler(self, request):
            if "integrated" in str(request.url) and request.url.params.get("symbol") == "BBB":
                self.requests.append(str(request.url))
                return httpx.Response(403, content=b"Access Denied")
            return super().handler(request)

    site = Refusing({"AAA": [irow("a1", Q2, True)], "BBB": [irow("b1", Q2, True)]})
    sink, out = run(site)
    assert "refused" in out["stopped"] and out["refusal"]["status"] == 403 and out["downloaded"] == 1


def test_failures_that_are_not_refusals_are_counted_by_reason_and_the_run_goes_on(monkeypatch, caplog):
    monkeypatch.setattr("bse_intel.nse.ANNUAL_REPORT_MAX_BYTES", 100_000)
    site = Site({"AAA": [irow("a1", Q2, True), irow("a2", Q2, False), irow("a3", Q1, True), irow("a4", Q1, False)],
                 "BBB": [irow("b1", Q2, True)]},
                served={furl("a1"): (404, b"not found"),
                        furl("a2"): (200, b"<html><body>hello, no xml here</body></html>"),
                        furl("a3"): (200, b"<?xml version='1.0'?><x>" + b"a" * 120_000 + b"</x>"),
                        furl("a4"): (500, b"oops")})
    with caplog.at_level("WARNING"):
        sink, out = run(site)
    assert out["failed_reasons"] == {"http_404": 1, "not_xml": 1, "too_large": 1, "http_500": 1}
    assert out["download_failed"] == 4 and out["stopped"] == "" and out["refusal"] is None
    assert out["downloaded"] == 1 and xbrl_facts.key("2", "Q2FY24", "CONSOLIDATED") in sink.objects   # the next company was done
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "nothing kept (http_404): HTTP 404, 9 bytes, body looked like XML: False" in text
    assert "nothing kept (too_large): HTTP 200, 120" in text and "nothing kept (not_xml): HTTP 200" in text
    # the 404 is remembered for the company's marker, the others are not (they may be a passing fault): its list is asked again later
    marker = json.loads(sink.objects[xbrl_facts.listed_key("1")])
    assert {tuple(g) for g in marker["gone"]} == {("Q2FY24", "CONSOLIDATED", "http_404"), ("Q1FY24", "CONSOLIDATED", "too_large")}


def test_a_results_file_over_the_seeds_8_mb_is_fetched_with_the_annual_report_limit():
    big = TITAN + b"<!--" + b"x" * 9_000_000 + b"-->"           # ADANIPORTS standalone Q4FY26 is over the client's 8 MB default
    site = Site({"AAA": [irow("a1", Q2, True)]}, served={furl("a1"): (200, big)})
    sink, out = run(site, companies=[("1", "AAA")])
    assert out["downloaded"] == 1 and out["facts_saved"] == 1 and out["failed_reasons"] == {}


def test_the_file_cap_is_still_a_planned_stop_and_a_list_does_not_count(monkeypatch):
    monkeypatch.setenv("FILE_CAP", "3")
    site = two_companies()
    sink, out = run(site)
    assert out["capped"] is True and "file cap reached" in out["stopped"] and out["refusal"] is None
    assert len(site.file_requests) == 3 and out["downloaded"] == 3 and files.used == 3
    assert out["lists"] == 2                                              # lists of both companies were asked for, uncounted


def test_a_company_that_fails_for_a_reason_of_its_own_does_not_stop_the_others_until_five_in_a_row():
    class Broken(SpySink):
        def put_object(self, key, body, content_type="application/json"):
            if key.startswith("raw/xbrl-facts/1/"):
                raise OSError("R2 hiccup")
            super().put_object(key, body, content_type)

    site = two_companies()
    sink, out = run(site, sink=Broken())
    assert out["company_errors"] == 1 and out["failed_reasons"] == {"company_error:OSError": 1}
    assert xbrl_facts.key("2", "Q2FY24", "CONSOLIDATED") in sink.objects and out["stopped"] == ""


def test_an_integrated_list_that_fails_leaves_the_older_list_and_no_marker_and_a_503_in_it_stops_the_shard():
    class Flaky(Site):
        def handler(self, request):
            if "integrated" in str(request.url) and request.url.params.get("symbol") == "AAA":
                self.requests.append(str(request.url))
                return httpx.Response(500, content=b"oops")
            return super().handler(request)

    site = Flaky({"AAA": [], "BBB": [irow("b1", Q2, True)]}, older={"AAA": [{"xbrl": f"{BASE}OLD_Q2.xml", "toDate": Q2,
                                                                          "consolidated": "Consolidated", "period": "Quarterly"}]})
    sink, out = run(site)
    assert out["partial_lists"] == 1 and out["downloaded"] == 2                 # the older list's file and the other company's
    assert xbrl_facts.listed_key("1") not in sink.objects and xbrl_facts.listed_key("2") in sink.objects

    class Refusing(Flaky):
        def handler(self, request):
            if "integrated" in str(request.url) and request.url.params.get("symbol") == "AAA":
                self.requests.append(str(request.url))
                return httpx.Response(503, content=b"Service Unavailable")
            return Site.handler(self, request)

    sink, out = run(Refusing({"AAA": [], "BBB": [irow("b1", Q2, True)]}))
    assert "refused" in out["stopped"] and out["refusal"]["status"] == 503 and out["downloaded"] == 0   # the older list answered; the 503 still stops


def annual_row(year: int, basis: str, name: str) -> dict:
    return {"fromYr": year - 1, "toYr": year, "submission_type": basis, "fileName": f"{BASE}{name}.xml", "report_type": "Ind AS",
            "broadcast_dttm": "01-JUL-2025 10:00:00"}


def test_the_annual_report_xbrl_goes_through_the_same_guard():
    ar = (Path(__file__).parent / "fixtures" / "nse_ar_kanorichem_fy25_consolidated.xml").read_bytes()
    site = Site({"AAA": [irow("a1", Q2, True)]}, annual={"AAA": [annual_row(2025, "CONSOLIDATED", "AR25C"), annual_row(2025, "STANDALONE", "AR25S")]},
                served={f"{BASE}AR25C.xml": (200, ar), f"{BASE}AR25S.xml": (404, b"gone")})
    sink, out = run(site, companies=[("1", "AAA")], annual=True)
    assert out["annual_lists"] == 1 and out["annual_downloaded"] == 1 and out["annual_saved"] == 1
    assert out["failed_reasons"] == {"http_404": 1} and out["stopped"] == "" and out["downloaded"] == 1
    assert xbrl_facts.annual_key("1", "FY25", "CONSOLIDATED") in sink.objects
    site = Site({"AAA": [irow("a1", Q2, True)]}, annual={"AAA": [annual_row(2025, "CONSOLIDATED", "AR25C")]},
                served={f"{BASE}AR25C.xml": (403, b"Access Denied")})
    sink, out = run(site, companies=[("1", "AAA")], annual=True)
    assert "refused" in out["stopped"] and out["refusal"]["status"] == 403 and out["downloaded"] == 0


# --- the time budget ---------------------------------------------------------------------------------------------------

class Ticker:
    """A clock that moves one second a look."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        self.now += 1.0
        return self.now


def test_the_time_budget_stops_between_two_files_saves_everything_and_writes_the_summary():
    site = Site({s: [irow(f"{s}1", Q2, True), irow(f"{s}2", Q2, False)] for s in ("AAA", "BBB", "CCC")})
    seen: list[dict] = []
    rows: list[dict] = []
    # the clock is looked at: the deadline (1), the progress timer (2), a company (3), its list (4), its first file (5), its second (6)
    sink, out = run(site, companies=[("1", "AAA"), ("2", "BBB"), ("3", "CCC")], time_budget=4.5, clock=Ticker(),
                    progress=lambda s: seen.append(dict(s)), row_sink=rows.append)
    assert out["out_of_time"] is True and "time budget reached" in out["stopped"] and out["capped"] is False and out["refusal"] is None
    assert out["downloaded"] == 1 and out["not_reached"] == 1                    # the first file was kept, the second not reached
    assert xbrl_facts.key("1", "Q2FY24", "CONSOLIDATED") in sink.objects and xbrl_store.key(furl("AAA1")) in sink.objects
    assert not any("BBB" in u for u in site.requests)
    assert [r["status"] for r in rows] == ["fetched", "not_reached"]
    assert seen and seen[-1]["out_of_time"] is True                              # the summary was handed on at the end
    assert xbrl_facts.listed_key("1") not in sink.objects                        # the company was not finished: its list is asked again


def test_the_cli_writes_the_summary_and_the_csv_when_the_time_budget_ends_the_run(monkeypatch, tmp_path, capsys):
    site = Site({"AAA": [irow("a1", Q2, True), irow("a2", Q2, False)], "BBB": [irow("b1", Q2, True)]}, delay=1.2)
    sink = SpySink()
    monkeypatch.setattr(cli, "make_sink", lambda settings: sink, raising=False)
    monkeypatch.setattr(cli, "_universe_companies", lambda s, scrips: COMPANIES)
    monkeypatch.setattr("bse_intel.nse.NseClient", lambda *a, **k: site.client())
    code = cli.main(["xbrl-facts", "--from-nse", "--download", "--time-budget", "1", "--json", str(tmp_path / "s.json"),
                     "--csv", str(tmp_path / "l.csv")])
    assert code == 124                                                              # a planned stop: the workflow turns it into "dispatch again"
    summary = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert summary["out_of_time"] is True and summary["downloaded"] == 1 and "missing_rows" not in summary
    lines = list(csv.DictReader((tmp_path / "l.csv").open(encoding="utf-8")))
    assert [r["status"] for r in lines] == ["fetched", "not_reached"]
    assert "time budget reached" in capsys.readouterr().out
    assert xbrl_facts.key("1", "Q2FY24", "CONSOLIDATED") in sink.objects


# --- the CSV: every timestamp of NSE's row ---------------------------------------------------------------------------------------

def test_the_csv_has_a_line_a_listed_file_with_every_timestamp_nse_carries(tmp_path):
    old = {"xbrl": f"{BASE}OLD_RESULT_Q1.xml", "toDate": "30-JUN-2023", "consolidated": "Consolidated", "period": "Quarterly",
           "filingDate": "21-JUL-2023", "broadCastDate": "21-JUL-2023 16:05:11", "exchdisstime": "21-JUL-2023 16:04:59"}
    site = Site({"AAA": [irow("a1", Q2, True, revised_Date="20-OCT-2023 10:00:00"), irow("a2", Q2, False)]}, older={"AAA": [old]})
    path = tmp_path / "listing.csv"
    csv_out = xbrl_facts.ListingCsv(path)
    try:
        run(site, companies=[("1", "AAA")], row_sink=csv_out)
    finally:
        csv_out.close()
    rows = {(r["period"], r["basis"]): r for r in csv.DictReader(path.open(encoding="utf-8"))}
    assert list(csv.reader(path.open(encoding="utf-8")))[0] == xbrl_facts.LISTING_HEADER
    new = rows[("Q2FY24", "CONSOLIDATED")]
    assert new["status"] == "fetched" and new["list"] == "integrated" and new["url"] == furl("a1")
    assert new["broadcast_Date"] == "17-Oct-2023 21:19:12" and new["creation_Date"] == "17-Oct-2023 21:10:00"
    assert new["revised_Date"] == "20-OCT-2023 10:00:00" and new["qe_Date"] == Q2
    assert new["name_stamp_raw"] == XML_STAMP and new["name_stamp_iso"] == "2023-10-17T09:19:27"
    times = json.loads(new["times"])
    assert times["submission_Time"] == "17-Oct-2023 21:12:00" and times["broadcast_Date"] == "17-Oct-2023 21:19:12"   # a field the parser never reads
    assert "symbol" not in times and "xbrl" not in times and "submission_Time" in new["raw_keys"].split("|")
    standalone = rows[("Q2FY24", "STANDALONE")]
    assert standalone["revised_Date"] == "" and standalone["status"] == "fetched"
    older = rows[("Q1FY24", "CONSOLIDATED")]
    assert older["list"] == "older" and older["filingDate"] == "21-JUL-2023" and older["broadCastDate"] == "21-JUL-2023 16:05:11"
    assert older["exchdisstime"] == "21-JUL-2023 16:04:59" and older["toDate"] == "30-JUN-2023" and older["name_stamp_raw"] == ""


def test_file_name_stamp():
    assert xbrl_facts.file_name_stamp(furl("1")) == (XML_STAMP, "2023-10-17T09:19:27")
    assert xbrl_facts.file_name_stamp(f"{BASE}X_99999999999999_WEB.xml") == ("99999999999999", "")
    assert xbrl_facts.file_name_stamp(f"{BASE}old.xml") == ("", "")


# --- the command and the workflow ------------------------------------------------------------------------------------------------

def test_the_cli_refuses_from_nse_without_download_and_a_bad_shard(monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_sink", lambda settings: SpySink(), raising=False)
    monkeypatch.setattr(cli, "_universe_companies", lambda s, scrips: COMPANIES)
    monkeypatch.setattr("bse_intel.nse.NseClient", lambda *a, **k: pytest.fail("no client for these"))
    assert cli.main(["xbrl-facts", "--from-nse"]) == 2
    for bad in ("0/17", "16/16", "x", "1"):
        assert cli.main(["xbrl-facts", "--from-nse", "--dry-run", "--shard", bad]) == 2
    assert "--shard takes I/N" in capsys.readouterr().out


def test_the_cli_runs_one_shards_slice_and_a_dry_run_without_download_makes_no_client(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "make_sink", lambda settings: SpySink(), raising=False)
    monkeypatch.setattr(cli, "_universe_companies", lambda s, scrips: [(str(i), f"S{i}") for i in range(1, 17)])
    monkeypatch.setattr("bse_intel.nse.NseClient", lambda *a, **k: pytest.fail("a dry run without --download asks NSE for nothing"))
    assert cli.main(["xbrl-facts", "--from-nse", "--dry-run", "--shard", "3/8", "--json", str(tmp_path / "s.json")]) == 0
    summary = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert summary["companies"] == 2 and summary["shard"] == "3/8" and summary["lists_skipped"]["dry_run"] == 2
    assert "shard 3/8: 2 companies" in capsys.readouterr().out


def test_the_cli_exits_75_on_a_refusal_and_still_writes_the_summary(monkeypatch, tmp_path):
    site = two_companies()
    site.served[furl("a1")] = (403, b"Access Denied")
    monkeypatch.setattr(cli, "make_sink", lambda settings: SpySink(), raising=False)
    monkeypatch.setattr(cli, "_universe_companies", lambda s, scrips: COMPANIES)
    monkeypatch.setattr("bse_intel.nse.NseClient", lambda *a, **k: site.client())
    assert cli.main(["xbrl-facts", "--from-nse", "--download", "--json", str(tmp_path / "s.json"), "--csv", str(tmp_path / "l.csv")]) == 75
    summary = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert summary["refusal"]["status"] == 403 and summary["refusal"]["body_head"] == "Access Denied"
    statuses = [r["status"] for r in csv.DictReader((tmp_path / "l.csv").open(encoding="utf-8"))]
    assert statuses == ["not_reached", "not_reached"]


def workflow():
    import yaml

    text = (Path(__file__).parents[2] / ".github" / "workflows" / "maintenance.yml").read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def test_workflow_runs_xbrl_facts_as_a_matrix_of_at_most_sixteen_shards_and_always_uploads():
    text, doc = workflow()
    inputs = (doc.get("on") or doc.get(True))["workflow_dispatch"]["inputs"]
    assert inputs["shards"]["default"] == "1" and inputs["from_nse"]["default"] is False and len(inputs) <= 25
    plan, job = doc["jobs"]["xbrl-facts-plan"], doc["jobs"]["xbrl-facts"]
    plan_step = next(st for st in plan["steps"] if st.get("id") == "plan")
    assert "[1-9]|1[0-6])" in plan_step["run"] and "exit 1" in plan_step["run"]      # 17 or 0 or text: the run is refused
    assert job["needs"] == "xbrl-facts-plan" and job["strategy"]["fail-fast"] is False
    assert job["strategy"]["matrix"]["shard"] == "${{ fromJSON(needs.xbrl-facts-plan.outputs.shards) }}"
    assert job["env"]["FILE_CAP_SHARDS"] == "${{ inputs.shards || '1' }}"
    assert "inputs.command != 'xbrl-facts'" in doc["jobs"]["run"]["if"]
    assert not any("xbrl-facts" in json.dumps(st) for st in doc["jobs"]["run"]["steps"])      # nothing of it is left in the generic job
    uploads = [st for st in job["steps"] if st.get("uses", "").startswith("actions/upload-artifact")]
    assert uploads and all(st["if"] == "always()" for st in uploads)                       # the summary and the CSV go up whatever happened
    assert {st["with"]["name"] for st in uploads} == {"xbrl-facts-${{ matrix.shard }}", "xbrl-facts-more-${{ matrix.shard }}",
                                                      "xbrl-facts-capped-${{ matrix.shard }}"}
    step = next(st for st in job["steps"] if st.get("name", "").startswith("Keep every fact"))
    assert "--time-budget 19200" in step["run"] and "--shard $SHARD/$SHARDS" in step["run"] and "--from-nse" in step["run"]
    assert step["timeout-minutes"] == 335 and job["timeout-minutes"] <= 360 and 19200 / 60 + 15 <= step["timeout-minutes"]
    assert 'if [ "$code" -eq 124 ]' in step["run"]                                           # the time budget is no failure
    assert "xbrl-facts-plan" in doc["jobs"]["chain"]["needs"] and "xbrl-facts" in doc["jobs"]["chain"]["needs"]


# --- the review's findings ----------------------------------------------------------------------------------------------------

def test_a_403_on_the_home_page_warm_up_is_no_refusal():
    """NseClient.warm_up() tolerates a 403 on the home page on purpose; the API answers all the same."""
    site = two_companies()
    site.home = (403, b"Access Denied")
    sink, out = run(site, warmed=False)
    assert out["refusal"] is None and out["stopped"] == "" and out["downloaded"] == 4 and out["lists"] == 2
    assert site.requests[0] == "https://www.nseindia.com/"          # the warm-up did happen (before the first guarded call)


def test_the_tap_ignores_a_home_page_answer_even_when_it_comes_later():
    site = two_companies()
    site.home = (403, b"Access Denied")
    client = site.client()
    guard = xbrl_facts.Guard(client)
    client._client.get("https://www.nseindia.com/")
    assert guard.tap.refusal is None and guard.tap.last is None


def test_three_block_like_pages_in_a_row_across_companies_stop_the_shard_but_one_does_not():
    page = (200, b"<html><body>Please wait while we check your browser</body></html>")      # no keyword the list knows
    companies = [(str(i), f"S{i}") for i in range(1, 6)]
    rows = {f"S{i}": [irow(f"s{i}", Q2, True)] for i in range(1, 6)}
    site = Site(rows, served={furl(f"s{i}"): page for i in range(1, 6)})
    sink, out = run(site, companies=companies)
    assert "refused" in out["stopped"] and out["refusal"]["status"] == 200 and "Please wait" in out["refusal"]["body_head"]
    assert out["failed_reasons"] == {"not_xml": 2} and len(site.file_requests) == 3          # two counted, the third stops the shard
    # an odd answer between good ones is only a counted failure: the run of them is broken by anything else
    site = Site(rows, served={furl("s1"): page, furl("s2"): page, furl("s4"): page})
    sink, out = run(site, companies=companies)
    assert out["stopped"] == "" and out["failed_reasons"] == {"not_xml": 3} and out["downloaded"] == 2


def utf16(body: bytes) -> bytes:
    """A fixture re-encoded the way some of NSE's files come (UTF-16 with its byte-order mark, CIPLA's FY26 annual report)."""
    return body.decode("utf-8").replace('encoding="UTF-8"', 'encoding="utf-16"').replace("encoding='UTF-8'", "encoding='utf-16'").encode("utf-16")


def commented(body: bytes) -> bytes:
    """A fixture with a generator's comment and no XML declaration first (NETWORK18's annual report, BeyondWallsXBRL)."""
    text = body.decode("utf-8")
    if text.startswith("<?xml"):
        text = text.split("?>", 1)[1]
    return b"<!-- XML Generated using BeyondWallsXBRL Solution - Copyright of BeyondSquare Solutions Private Limited -->\n" + text.lstrip().encode("utf-8")


@pytest.mark.parametrize("encode", [utf16, commented])
def test_utf16_and_comment_first_files_are_xml_kept_and_never_a_block_page(encode):
    """Measured 28 Oct 2026, maintenance run 40679795489: six of sixteen shards stopped on three such files in a row ("3 block-like
    file pages"), and about 160 more were counted not_xml; both are real XBRL instances that parse."""
    from bse_intel.nse import looks_like_xml

    body = encode(TITAN)
    assert looks_like_xml(body) and looks_like_xml(body[:2000]) and xbrl_facts.parse_facts(body) is not None
    companies = [(str(i), f"S{i}") for i in range(1, 6)]
    rows = {f"S{i}": [irow(f"s{i}", Q2, True)] for i in range(1, 6)}
    site = Site(rows, served={furl(f"s{i}"): (200, body) for i in range(1, 6)})
    sink, out = run(site, companies=companies)
    assert out["stopped"] == "" and out["refusal"] is None and out["failed_reasons"] == {} and out["downloaded"] == 5
    assert out["facts_saved"] == 5


def test_a_block_page_is_still_no_xml_after_the_wider_test():
    from bse_intel.nse import looks_like_xml

    for page in (b"<html><body>Please wait</body></html>", b"<!DOCTYPE html><html>", b"<!-- a comment --><html>", b"Access Denied",
                 b"", b"<!-- a comment that never closes", "<html>blocked</html>".encode("utf-16")):
        assert not looks_like_xml(page), page


def test_html_for_both_lists_of_three_companies_in_a_row_stops_the_shard():
    class Html(Site):
        def handler(self, request):
            if request.url.path.endswith(("/integrated-filing-results", "/corporates-financial-results")):
                self.requests.append(str(request.url))
                return httpx.Response(200, content=b"<html><body>One moment please</body></html>")
            return super().handler(request)

    companies = [(str(i), f"S{i}") for i in range(1, 6)]
    site = Html({})
    sink, out = run(site, companies=companies)
    assert "refused" in out["stopped"] and out["lists"] == 2 and out["list_failed"] == 2      # the third list is the one that stops
    assert out["failed_reasons"] == {"list:not_xml": 2} and out["refusal"]["status"] == 200


def test_the_cli_takes_the_file_cap_share_count_from_shard_when_the_workflow_did_not_set_it(monkeypatch):
    monkeypatch.setenv("FILE_CAP_SHARDS", "")                    # unset as far as the cli is concerned; restored after the test
    monkeypatch.setenv("FILE_CAP", "20")
    monkeypatch.setattr(cli, "make_sink", lambda settings: SpySink(), raising=False)
    monkeypatch.setattr(cli, "_universe_companies", lambda s, scrips: COMPANIES)
    monkeypatch.setattr("bse_intel.nse.NseClient", lambda *a, **k: pytest.fail("a dry run asks NSE for nothing"))
    assert cli.main(["xbrl-facts", "--from-nse", "--dry-run", "--shard", "0/8"]) == 0
    assert files.cap() == 2                                      # 20 // 8
    monkeypatch.setenv("FILE_CAP", "5")
    assert files.cap() == 1                                      # a cap below the shards gives every shard 1
    monkeypatch.setenv("FILE_CAP_SHARDS", "4")                   # what the workflow sets stays
    assert cli.main(["xbrl-facts", "--from-nse", "--dry-run", "--shard", "0/8"]) == 0
    assert files.cap() == 1 and os.environ["FILE_CAP_SHARDS"] == "4"


def test_a_file_that_holds_no_results_or_is_over_the_limit_goes_in_the_marker_so_the_list_is_skipped(monkeypatch):
    monkeypatch.setattr("bse_intel.nse.ANNUAL_REPORT_MAX_BYTES", 400_000)
    site = Site({"AAA": [irow("a1", Q2, True), irow("a2", Q2, False)]},
                served={furl("a1"): (200, SHAREHOLDING), furl("a2"): (200, b"<?xml version='1.0'?><x>" + b"a" * 450_000 + b"</x>")})
    sink, out = run(site, companies=[("1", "AAA")])
    assert out["not_results"] == 1 and out["failed_reasons"] == {"too_large": 1} and out["downloaded"] == 1
    marker = json.loads(sink.objects[xbrl_facts.listed_key("1")])
    assert {tuple(g) for g in marker["gone"]} == {("Q2FY24", "CONSOLIDATED", "not_results"), ("Q2FY24", "STANDALONE", "too_large")}
    before = len(site.requests)
    sink, again = run(site, sink=sink, companies=[("1", "AAA")])
    assert len(site.requests) == before and again["lists"] == 0 and again["lists_skipped"]["stored"] == 1


def test_an_exception_in_the_annual_part_is_that_companys_gap_and_the_run_goes_on():
    ar = (Path(__file__).parent / "fixtures" / "nse_ar_kanorichem_fy25_consolidated.xml").read_bytes()

    class Broken(SpySink):
        def put_object(self, key, body, content_type="application/json"):
            if key.startswith("raw/xbrl-facts/1/annual-"):
                raise OSError("R2 hiccup")
            super().put_object(key, body, content_type)

    site = Site({"AAA": [irow("a1", Q2, True)], "BBB": [irow("b1", Q2, True)]},
                annual={"AAA": [annual_row(2025, "CONSOLIDATED", "AR1")], "BBB": [annual_row(2025, "CONSOLIDATED", "AR2")]},
                served={f"{BASE}AR1.xml": (200, ar), f"{BASE}AR2.xml": (200, ar)})
    sink, out = run(site, sink=Broken(), annual=True)
    assert out["failed_reasons"] == {"company_error:OSError": 1} and out["stopped"] == "" and out["refusal"] is None
    assert xbrl_facts.annual_key("2", "FY25", "CONSOLIDATED") in sink.objects
    assert xbrl_facts.key("2", "Q2FY24", "CONSOLIDATED") in sink.objects


def test_five_companies_in_a_row_failing_is_an_infrastructure_stop_with_its_own_exit_code(monkeypatch, tmp_path, caplog):
    class Down(SpySink):
        def put_object(self, key, body, content_type="application/json"):
            if key.startswith("raw/xbrl-facts/"):
                raise OSError("R2 down")
            super().put_object(key, body, content_type)

    companies = [(str(i), f"S{i}") for i in range(1, 9)]
    site = Site({f"S{i}": [irow(f"s{i}", Q2, True)] for i in range(1, 9)})
    with caplog.at_level("ERROR"):
        sink, out = run(site, sink=Down(), companies=companies)
    assert out["infra_stop"] is True and "infrastructure, not an NSE refusal" in out["stopped"] and out["refusal"] is None
    assert out["company_errors"] == 5 and not any("S6" in u for u in site.requests)
    assert any("infrastructure stop" in r.getMessage() for r in caplog.records)
    monkeypatch.setattr(cli, "make_sink", lambda settings: Down(), raising=False)
    monkeypatch.setattr(cli, "_universe_companies", lambda s, scrips: companies)
    monkeypatch.setattr("bse_intel.nse.NseClient", lambda *a, **k: site.client())
    code = cli.main(["xbrl-facts", "--from-nse", "--download", "--json", str(tmp_path / "s.json")])
    assert code == cli.INFRA_STOP == 70 and code != cli.REFUSED
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))["infra_stop"] is True


def test_workflow_archive_pause_is_optional_and_empty_by_default_and_the_chain_waits_for_a_shard_with_files_left():
    text, doc = workflow()
    inputs = (doc.get("on") or doc.get(True))["workflow_dispatch"]["inputs"]
    assert inputs["archive_pause"]["default"] == "" and inputs["archive_pause"]["type"] == "string" and len(inputs) <= 25
    job = doc["jobs"]["xbrl-facts"]
    assert "NSE_ARCHIVE_PAUSE_SECONDS" not in job["env"]                       # not set unless the input is
    step = next(st for st in job["steps"] if st.get("name", "").startswith("Keep every fact"))
    assert step["env"]["ARCHIVE_PAUSE"] == "${{ inputs.archive_pause }}"
    assert 'if [ -n "$ARCHIVE_PAUSE" ]; then export NSE_ARCHIVE_PAUSE_SECONDS="$ARCHIVE_PAUSE"; fi' in step["run"]
    chain = next(st for st in doc["jobs"]["chain"]["steps"] if st.get("name") == "Start the next command")
    assert "xbrl-facts)" in chain["run"]
    block = chain["run"].split("xbrl-facts)")[1].split(";;")[0]
    assert '[ -n "$left" ]' in block and "exit 0" in block and "dispatch again" in block
    assert "a `file_cap` below `shards` gives every shard 1 file" in text


# --- annual reports: newest year first, across companies too ------------------------------------------------------------------

def annual_site(symbols: list[str]) -> Site:
    ar = (Path(__file__).parent / "fixtures" / "nse_ar_kanorichem_fy25_consolidated.xml").read_bytes()
    listing = {s: [annual_row(y, "CONSOLIDATED", f"{s}{y}") for y in (2024, 2026, 2025)] for s in symbols}     # NSE's order is not trusted
    return Site({}, annual=listing, default=(200, ar))


def fetched_years(site: Site) -> list[str]:
    return [u.rsplit("/", 1)[-1].removesuffix(".xml") for u in site.file_requests]


def test_annual_files_are_fetched_newest_year_first_for_each_company(monkeypatch):
    monkeypatch.setenv("FILE_CAP", "2")
    site = annual_site(["AAA"])
    sink, out = run(site, companies=[("1", "AAA")], annual=True)
    assert fetched_years(site) == ["AAA2026", "AAA2025"] and out["capped"] is True


def test_a_capped_run_does_every_companys_newest_year_before_any_older_year(monkeypatch):
    monkeypatch.setenv("FILE_CAP", "4")
    names = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    companies = [(str(i), s) for i, s in enumerate(names, 1)]
    site = annual_site(names)
    sink, out = run(site, companies=companies, annual=True)
    assert fetched_years(site) == ["AAA2026", "BBB2026", "CCC2026", "DDD2026"]      # not AAA2026, AAA2025, AAA2024, BBB2026
    # without a cap the second pass follows: all of FY26, then the older years, company by company
    files.reset()
    monkeypatch.delenv("FILE_CAP")
    site = annual_site(["AAA", "BBB"])
    sink, out = run(site, companies=companies[:2], annual=True)
    assert fetched_years(site) == ["AAA2026", "BBB2026", "AAA2025", "AAA2024", "BBB2025", "BBB2024"]
    assert out["annual_saved"] == 6 and out["annual_lists"] == 2 and out["stopped"] == ""


def test_the_annual_path_without_from_nse_is_newest_first_too(monkeypatch):
    monkeypatch.setenv("FILE_CAP", "2")
    site = annual_site(["AAA", "BBB"])
    out = xbrl_facts.run(FakeSink(), [("1", "AAA"), ("2", "BBB")], download=True, client=site.client(), annual=True)
    assert fetched_years(site) == ["AAA2026", "BBB2026"] and out["capped"] is True
