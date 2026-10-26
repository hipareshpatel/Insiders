from bse_intel import nse_speedtest as st

GOOD = b'<?xml version="1.0"?><xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"></xbrli:xbrl>'
CUT = GOOD[:-20]


class FakeFetcher:
    """Answers from a script: status by call number (default 200)."""

    def __init__(self, script=None, body=GOOD, timeouts=()):
        self.script, self.body, self.timeouts, self.calls = script or {}, body, set(timeouts), []

    def get(self, url):
        self.calls.append(url)
        n = len(self.calls)
        if n in self.timeouts:
            return st.Response(seconds=45.0, error="timeout", timeout=True)
        status = self.script.get(n, 200)
        return st.Response(status, self.body if status == 200 else b"", 0.1)


def urls(n):
    return [f"https://{st.ARCHIVE_HOST}/f{i}.xml" for i in range(n)]


def test_round_stops_at_first_429():
    f = FakeFetcher({4: 429})
    r = st.run_round("B", (1.0, 1.0), 1, urls(10), f, sleep=lambda s: None)
    assert len(r.requests) == 4
    assert r.stopped.startswith("HTTP 429")


def test_round_stops_at_three_timeouts():
    f = FakeFetcher(timeouts=(2, 3, 5))
    r = st.run_round("C", (0.3, 0.3), 1, urls(10), f, sleep=lambda s: None)
    assert len(r.requests) == 5 and r.stopped == "3 timeouts"


def test_no_faster_round_after_a_refusal_and_cool_down():
    sleeps = []
    f = FakeFetcher({3: 403})
    rounds = st.run_rounds(urls(400), f, per_round=5, sleep=sleeps.append, cool_down=60.0)
    assert [r.name for r in rounds] == ["A", "B", "C", "D", "E"]
    assert rounds[0].stopped and len(rounds[0].requests) == 3
    assert all(r.not_run and not r.requests for r in rounds[1:])
    assert 60.0 in sleeps
    assert len(f.calls) == 3


def test_each_round_takes_different_files_and_pause_is_applied():
    sleeps = []
    f = FakeFetcher()
    rounds = st.run_rounds(urls(400), f, per_round=4, sleep=sleeps.append)
    seen = [q["url"] for r in rounds for q in r.requests]
    assert len(seen) == len(set(seen)) == 20
    assert all(3.0 <= s <= 5.0 for s in sleeps[:3]) and sleeps[3:6] == [1.0] * 3 and sleeps[6:9] == [0.3] * 3
    assert len(sleeps) == 9   # D and E at 0 s never sleep; one fewer sleep than files in A, B, C


def test_parallel_round_uses_four_workers_and_all_files():
    f = FakeFetcher()
    r = st.run_round("E", (0.0, 0.0), 4, urls(20), f, sleep=lambda s: None)
    assert len(r.requests) == 20 and len(set(f.calls)) == 20


def test_incomplete_xml_is_flagged_and_round_not_safe():
    f = FakeFetcher(body=CUT)
    r = st.run_round("A", (0.0, 0.0), 1, urls(3), f, sleep=lambda s: None)
    assert [q["complete_xml"] for q in r.requests] == [False] * 3
    r.elapsed = 1.0
    assert st._round_summary(r)["safe"] is False


def test_summary_maths_and_fastest_safe_round():
    def rnd(name, files, elapsed, stopped=""):
        r = st.RoundResult(name, (0, 0), 1, files)
        r.requests = [{"url": "u", "status": 200, "bytes": 10, "seconds": 0.2, "error": "", "complete_xml": True,
                       "xbrl_parses": True} for _ in range(files)]
        r.elapsed, r.stopped = elapsed, stopped
        return r

    rounds = [rnd("A", 60, 240.0), rnd("B", 60, 60.0), rnd("C", 30, 10.0, stopped="HTTP 429 on request 30")]
    rounds[2].planned = 60
    listing = {"api_seconds_per_company": 8.0, "api_calls_per_company": 2.0, "all_list_seconds": 120.0}
    s = st.summarise(listing, rounds)
    by = {r["round"]: r for r in s["rounds"]}
    assert by["A"]["files_per_minute"] == 15.0 and by["B"]["files_per_minute"] == 60.0
    assert by["C"]["safe"] is False
    assert s["fastest_safe_round"] == "B"
    p = s["projection"]
    # listing: 1,850 calls at 4 s a call = 7,400 s; files 40,000 at 15/min = 160,000 s and at 60/min = 40,000 s
    assert p["today_hours"] == round((160_000 + 7_400) / 3600, 2)
    assert p["fastest_safe_hours"] == round((40_000 + 7_400) / 3600, 2)
    assert p["fastest_safe_hours_with_all_company_list"] == round((40_000 + 120) / 3600, 2)


def test_pick_symbols_is_seeded():
    pool = [f"S{i}" for i in range(500)]
    assert st.pick_symbols(pool, 100, 26) == st.pick_symbols(pool[::-1], 100, 26)
    assert len(set(st.pick_symbols(pool, 100, 26))) == 100


def test_archive_urls_keep_only_archive_xml_once():
    links = {"A": [f"https://{st.ARCHIVE_HOST}/a.xml", "https://www.nseindia.com/x.xml", f"https://{st.ARCHIVE_HOST}/a.pdf"],
             "B": [f"https://{st.ARCHIVE_HOST}/a.xml", f"https://{st.ARCHIVE_HOST}/b.xml"]}
    assert sorted(st.archive_urls(links, 1)) == [f"https://{st.ARCHIVE_HOST}/a.xml", f"https://{st.ARCHIVE_HOST}/b.xml"]


class FakeNse:
    def __init__(self, refuse_list=False):
        self._calls, self._sleep, self.refuse_list = 0, (lambda s: None), refuse_list

    def financial_results(self, symbol):
        from bse_intel.nse import ResultsFiling, SourceBlockedError
        self._calls += 2
        if self.refuse_list:
            raise SourceBlockedError("HTTP 403")
        return [ResultsFiling("Quarterly", True, "", "2026-01-01", f"https://{st.ARCHIVE_HOST}/{symbol}_{i}.xml", False)
                for i in range(3)]

    def integrated_list(self, kind, page, size):
        return [{"symbol": "AAA", "xbrl": f"https://{st.ARCHIVE_HOST}/AAA_0.xml"}]


def test_run_end_to_end_read_only_with_fakes():
    f = FakeFetcher()
    rep = st.run(FakeNse(), ["AAA", "BBB"], per_round=2, sleep=lambda s: None, fetcher=f)
    assert rep["listing"]["listed"] == 2 and rep["listing"]["api_calls_per_company"] == 2.0
    assert rep["listing"]["all_list_files_found"] == 1
    assert rep["files_available"] == 6 and len(f.calls) == 6   # rounds A-C took two files each; D and E found none left
    assert [r["not_run"] for r in rep["rounds"]][3:] == ["no files left", "no files left"]
    assert "Fastest safe round" in st.render(rep)


def test_listing_refusal_skips_downloads():
    f = FakeFetcher()
    rep = st.run(FakeNse(refuse_list=True), ["AAA"], sleep=lambda s: None, fetcher=f)
    assert rep["listing"]["refused"] and f.calls == [] and rep["rounds"] == []
