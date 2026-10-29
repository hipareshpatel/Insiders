"""The sub-rows behind each '+' head of the stored screener pages (owner, 29 Oct 2026): one request a head, stored per page,
resumable, capped for a trial, stopping on a refusal."""

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from bse_intel import screener_download as sd
from bse_intel import screener_schedules as ss
from bse_intel.screener_fill import ScreenerClient, ScreenerRefused
from test_screener_download import Sink

DAY = "2026-10-27"
PAGE = ('<div data-company-id="163" data-warehouse-id="6594611">'
        "<button onclick=\"Company.showSchedule('Borrowings', 'balance-sheet', this)\">+</button>"
        "<button onclick=\"Company.showSchedule('Other Income', 'profit-loss', this)\">+</button>"
        "<button onclick=\"Company.showSchedule('Borrowings', 'balance-sheet', this)\">+</button></div>")
ANSWER = {"Lease Liabilities": {"Mar 2026": "813"}}


def store_pages(sink, symbols):
    pages = {}
    for symbol in symbols:
        for basis, letter in sd.BASES:
            key = sd.object_key(DAY, symbol, basis)
            sink.put_object(key, sd.pack(PAGE), "application/gzip")
            pages.setdefault(symbol, {})[basis] = key
    return pages


def client_for(responses, seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        status, body = responses(request)
        return httpx.Response(status, text=body)
    return ScreenerClient(transport=httpx.MockTransport(handler), sleep=lambda s: None, clock=lambda: 0.0, headers=ss.XHR_HEADERS)


def test_heads_are_read_from_the_page_once_each_with_the_company_id():
    assert ss.heads(PAGE) == ("163", [("Borrowings", "balance-sheet"), ("Other Income", "profit-loss")])


def test_each_head_is_one_request_and_a_page_is_stored_with_all_its_answers():
    sink, seen = Sink(), []
    pages = store_pages(sink, ["AAA"])
    with client_for(lambda r: (200, json.dumps(ANSWER)), seen) as client:
        out = ss.run(sink, ["AAA"], pages, client)
    assert out["requests_made"] == 4 and out["pages_stored"] == 2 and not out["more"]
    first = urlparse(str(seen[0].url))
    assert first.path == "/api/company/163/schedules/"
    q = parse_qs(first.query, keep_blank_values=True)
    assert q["parent"] == ["Borrowings"] and q["section"] == ["balance-sheet"] and "consolidated" in q
    assert all("consolidated" not in parse_qs(urlparse(str(r.url)).query, keep_blank_values=True) for r in seen[2:])
    assert seen[0].headers["X-Requested-With"] == "XMLHttpRequest"
    stored = ss.unpack(sink.get_object(f"{ss.PREFIX}{DAY}/AAA_c.json.gz"))
    assert stored == {"balance-sheet|Borrowings": ANSWER, "profit-loss|Other Income": ANSWER}


def test_a_stored_page_is_not_asked_again_and_the_cap_stops_before_a_page():
    sink, seen = Sink(), []
    pages = store_pages(sink, ["AAA", "BBB"])
    with client_for(lambda r: (200, json.dumps(ANSWER)), seen) as client:
        out = ss.run(sink, ["AAA", "BBB"], pages, client, max_requests=3)
        assert out["requests_made"] == 2 and out["more"]          # a page's two heads fit, the next page's do not
        again = ss.run(sink, ["AAA", "BBB"], pages, client)
    assert again["pages_already_stored"] == 1 and again["requests_made"] == 6


def test_an_answer_that_is_not_json_leaves_the_page_to_be_asked_again():
    sink, seen = Sink(), []
    pages = store_pages(sink, ["AAA"])
    with client_for(lambda r: (200, "<html>login</html>"), seen) as client:
        out = ss.run(sink, ["AAA"], pages, client)
    assert out["heads_not_json"] == 4 and out["pages_stored"] == 0


def test_a_refusal_stops_the_run():
    sink, seen = Sink(), []
    pages = store_pages(sink, ["AAA"])
    with client_for(lambda r: (429, ""), seen) as client, pytest.raises(ScreenerRefused):
        ss.run(sink, ["AAA"], pages, client)
