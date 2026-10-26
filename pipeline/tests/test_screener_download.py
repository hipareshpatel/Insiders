"""The one-time screener.in download (F163): both pages, stored gzipped, resumable, skipping stored pages, stopping on a refusal."""

import json

import httpx
import pytest

from bse_intel import screener_download as sd
from bse_intel.screener_fill import ScreenerClient, ScreenerRefused

DAY = "2026-10-27"


class Sink:
    def __init__(self, companies=None):
        self.kv, self.objects, self.puts = {}, {}, 0
        self.rows = companies or {}

    def kv_get(self, key):
        return self.kv.get(key)

    def kv_set(self, key, value, now):
        self.kv[key] = value

    def list_objects(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))

    def put_object(self, key, body, content_type="application/json"):
        self.objects[key] = body
        self.puts += 1

    def get_object(self, key):
        return self.objects.get(key)

    def company(self, scrip):
        return self.rows.get(scrip)


def client_for(responses, seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        status, body = responses(str(request.url))
        return httpx.Response(status, text=body)
    naps = []
    return ScreenerClient(transport=httpx.MockTransport(handler), sleep=naps.append, clock=lambda: 0.0), naps


COMPANIES = [("1", "AAA"), ("2", "BBB"), ("3", "CCC")]


def ok(url):
    return 200, f"<html>{url}</html>"


def test_both_pages_are_stored_gzipped_under_the_dated_key():
    sink, seen = Sink(), []
    client, _ = client_for(ok, seen)
    with client:
        out = sd.run(sink, COMPANIES[:1], client, DAY)
    assert seen == ["https://www.screener.in/company/AAA/consolidated/", "https://www.screener.in/company/AAA/"]
    assert sorted(sink.objects) == [f"raw/screener/{DAY}/AAA_c.html.gz", f"raw/screener/{DAY}/AAA_s.html.gz"]
    assert sd.unpack(sink.objects[f"raw/screener/{DAY}/AAA_c.html.gz"]) == "<html>https://www.screener.in/company/AAA/consolidated/</html>"
    assert out["pages_stored"] == 2 and out["requests_made"] == 2 and not out["more"]


def test_the_pause_is_the_fill_pause_and_the_agent_is_a_browser():
    assert sd.PAUSE_SECONDS == 3.2 and sd.MAX_SHARDS == 2
    client, _ = client_for(ok, [])
    assert client.pause >= 3.0


def test_a_page_already_stored_for_the_day_is_not_fetched_and_a_finished_company_is_not_visited_again():
    sink, seen = Sink(), []
    sink.objects[f"raw/screener/{DAY}/AAA_c.html.gz"] = sd.pack("old")
    client, _ = client_for(ok, seen)
    with client:
        out = sd.run(sink, COMPANIES[:2], client, DAY)
        assert out["pages_already_stored"] == 1 and out["requests_made"] == 3
        assert sd.unpack(sink.objects[f"raw/screener/{DAY}/AAA_c.html.gz"]) == "old"
        again = sd.run(sink, COMPANIES[:2], client, DAY)
    assert again["companies_done_before"] == 2 and again["requests_made"] == 0
    assert json.loads(sink.kv[f"screenerdl:done:{DAY}:0of1"]) == ["AAA", "BBB"]


def test_a_new_day_fetches_again():
    sink, seen = Sink(), []
    client, _ = client_for(ok, seen)
    with client:
        sd.run(sink, COMPANIES[:1], client, DAY)
        sd.run(sink, COMPANIES[:1], client, "2026-10-28")
    assert len(seen) == 4


def test_shards_split_the_companies_and_keep_their_own_lists():
    sink, seen = Sink(), []
    client, _ = client_for(ok, seen)
    with client:
        a = sd.run(sink, COMPANIES, client, DAY, shard=(0, 2))
        b = sd.run(sink, COMPANIES, client, DAY, shard=(1, 2))
    assert a["companies"] == 2 and b["companies"] == 1
    assert f"screenerdl:done:{DAY}:0of2" in sink.kv and f"screenerdl:done:{DAY}:1of2" in sink.kv
    assert len(sink.objects) == 6


def test_a_refusal_stops_the_run_and_keeps_what_is_done():
    sink, seen = Sink(), []

    def answers(url):
        return (429, "") if "/BBB/" in url else ok(url)
    client, _ = client_for(answers, seen)
    with client, pytest.raises(ScreenerRefused):
        sd.run(sink, COMPANIES, client, DAY)
    assert not any("CCC" in u for u in seen)                  # nothing asked after the refusal
    assert json.loads(sink.kv[f"screenerdl:done:{DAY}:0of1"]) == ["AAA"]
    assert f"raw/screener/{DAY}/AAA_s.html.gz" in sink.objects and not any("BBB" in k for k in sink.objects)


@pytest.mark.parametrize("status", [403, 503])
def test_403_and_503_stop_too(status):
    client, _ = client_for(lambda url: (status, ""), [])
    with client, pytest.raises(ScreenerRefused):
        sd.run(Sink(), COMPANIES, client, DAY)


def test_a_failed_page_is_retried_by_the_next_run_and_a_404_is_not():
    sink, seen = Sink(), []
    state = {"fail": True}

    def answers(url):
        if url.endswith("/BBB/consolidated/"):
            return 404, ""
        if url.endswith("/BBB/") and state["fail"]:
            return 500, ""
        return ok(url)
    client, _ = client_for(answers, seen)
    with client:
        first = sd.run(sink, COMPANIES[1:2], client, DAY)
        assert first["pages_not_found"] == 1 and first["pages_failed"] == 1 and first["failed"]
        state["fail"] = False
        second = sd.run(sink, COMPANIES[1:2], client, DAY)
    assert second["pages_stored"] == 1 and second["requests_made"] == 2   # the 404 page is asked again, cheaply
    assert f"raw/screener/{DAY}/BBB_s.html.gz" in sink.objects


def test_time_budget_leaves_companies_and_says_so():
    sink, seen = Sink(), []
    client, _ = client_for(ok, seen)
    ticks = iter([0, 0, 100, 100, 100])
    with client:
        out = sd.run(sink, COMPANIES, client, DAY, time_budget=10, clock=lambda: next(ticks))
    assert out["more"] and out["pages_stored"] == 2


def test_symbols_come_from_the_universe_first_then_the_company_row():
    sink = Sink({"3": {"symbol": "ccc "}, "9": {"symbol": ""}})
    got = sd.symbols_for(sink, ["2", "1", "3", "9"], {"1": "AAA", "2": "bbb"})
    assert got == [("1", "AAA"), ("2", "BBB"), ("3", "CCC")]


def test_estimate_is_two_pages_a_company():
    assert sd.estimate(1900, 2) == {"requests": 3800, "seconds": round(3800 * 3.2 / 2)}
