"""NSE as the discovery source (owner, 2026-10-18): the equity list and our company master make the universe, the
day's announcements become filings on our company keys, and the rule book reads NSE's subjects where it read BSE's
subcategories. Rows are shaped like NSE's own answers of 12-18 Oct 2026."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

from conftest import FakeProvider

from bse_intel import universe
from bse_intel.ai.gateway import AIGateway
from bse_intel.nse import Equity, parse_announcement, parse_equity_list
from bse_intel.pipeline import Pipeline
from bse_intel.rules import RuleBook
from bse_intel.sinks.local import LocalSink

EQUITY_CSV = (
    "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
    "RAILTEL,RailTel Corporation of India Limited,EQ,26-FEB-2021,10,1,INE0DD101019,10\n"
    "BALUFORGE,Balu Forge Industries Limited,EQ,14-NOV-2023,10,1,INE011E01029,10\n"
    "TINYCO,Tiny Company Limited,BE,01-JAN-2020,10,1,INE999A01011,10\n"
    "NEWCO,New Listing Limited,EQ,01-OCT-2026,10,1,INE888B01022,10\n"
    "NSEONLY,Only On NSE Limited,EQ,01-JAN-2019,10,1,INE777C01033,10\n"
)

COMPANIES = [
    {"scrip_code": "543265", "symbol": "RAILTEL", "isin": "INE0DD101019", "market_cap_cr": 12000.0, "watchlist": 0},
    # A symbol that changed on one exchange: the ISIN still matches
    {"scrip_code": "531112", "symbol": "BALUFORGEOLD", "isin": "INE011E01029", "market_cap_cr": 5787.0, "watchlist": 0},
    {"scrip_code": "500001", "symbol": "TINYCO", "isin": "INE999A01011", "market_cap_cr": 40.0, "watchlist": 0},
    {"scrip_code": "544999", "symbol": "NEWCO", "isin": "INE888B01022", "market_cap_cr": None, "watchlist": 0},
    {"scrip_code": "500002", "symbol": "BSEONLY", "isin": "INE666D01044", "market_cap_cr": 900.0, "watchlist": 0},
]


def _row(seq, symbol, isin, desc, text, when="17-Oct-2026 13:37:56", attachment="https://nsearchives.nseindia.com/corporate/X.pdf"):
    return {"seq_id": seq, "symbol": symbol, "sm_isin": isin, "sm_name": f"{symbol} Limited", "desc": desc,
            "attchmntText": text, "an_dt": when, "sort_date": "2026-10-17 13:37:56", "attchmntFile": attachment,
            "attFileSize": "324.00 KB", "hasXbrl": True}


def test_equity_list_headers_with_spaces():
    rows = parse_equity_list("﻿" + EQUITY_CSV)
    assert [r.symbol for r in rows] == ["RAILTEL", "BALUFORGE", "TINYCO", "NEWCO", "NSEONLY"]
    assert rows[0] == Equity("RAILTEL", "RailTel Corporation of India Limited", "INE0DD101019", "EQ", "2021-02-26")


def test_universe_joins_by_isin_and_applies_the_floor():
    body = universe.select(parse_equity_list(EQUITY_CSV), COMPANIES, 100)
    assert body["included"] == ["531112", "543265", "544999"]     # the new listing has no market cap yet and stays in
    assert body["excluded"] == ["500001"]                          # ₹40 Cr is below the ₹100 Cr floor
    assert body["nse_only"] == ["NSEONLY"]                         # on NSE, not in our master
    assert body["symbols"]["BALUFORGE"] == "531112"                # matched by ISIN though the stored symbol differs
    assert body["counts"] == {"nse_listed": 5, "matched": 4, "included": 3, "below_floor": 1, "buffered": 0, "returned": 0,
                              "unpriced": 1, "nse_only": 1}
    # The owner's watchlist keeps a small company in
    starred = [dict(c, watchlist=1) if c["scrip_code"] == "500001" else c for c in COMPANIES]
    assert "500001" in universe.select(parse_equity_list(EQUITY_CSV), starred, 100)["included"]


def test_universe_buffer_and_companies_coming_back():
    """Owner, 22 Oct 2026: a company already in leaves only below the exit floor, so one near the floor does not drop
    out and back day to day; one that left is named when it returns, with the day it left, so its set-aside filings
    are read."""
    equities = parse_equity_list(EQUITY_CSV)
    at = lambda cap: [dict(c, market_cap_cr=cap) if c["scrip_code"] == "543265" else c for c in COMPANIES]
    day1 = universe.select(equities, at(12000.0), 500, 400, {}, "2026-10-20")
    assert "543265" in day1["included"] and day1["counts"]["buffered"] == 0
    day2 = universe.select(equities, at(450.0), 500, 400, day1, "2026-10-21")      # below the floor, above the exit
    assert "543265" in day2["included"] and day2["counts"]["buffered"] == 1
    fresh = universe.select(equities, at(450.0), 500, 400, {}, "2026-10-21")       # never in: ₹450 Cr does not join
    assert "543265" in fresh["excluded"]
    day3 = universe.select(equities, at(350.0), 500, 400, day2, "2026-10-22")      # below the exit: out, and when
    assert "543265" in day3["excluded"] and day3["excluded_since"]["543265"] == "2026-10-22"
    day4 = universe.select(equities, at(380.0), 500, 400, day3, "2026-10-23")      # still out: keeps the first day
    assert day4["excluded_since"]["543265"] == "2026-10-22" and not day4["returned"]
    day5 = universe.select(equities, at(520.0), 500, 400, day4, "2026-10-24")      # back above the floor
    assert "543265" in day5["included"] and day5["returned"] == {"543265": "2026-10-22"}
    assert "543265" not in day5["excluded_since"]
    assert universe.select(equities, at(520.0), 500, 400, day5, "2026-10-25")["returned"] == {}   # named once
    # the first build with the field: a company already out has no known day, so all its set-aside history is read
    first = universe.select(equities, at(300.0), 500, 400, {"included": []}, "2026-10-22")
    assert first["excluded_since"]["543265"] == ""
    assert universe.select(equities, at(600.0), 500, 400, first, "2026-10-23")["returned"] == {"543265": ""}


def test_returning_companies_have_their_set_aside_filings_read(settings):
    from bse_intel.pipeline import _still_noise

    class Decision:
        action = "ANALYZE"

    row = ["x", "", "", "", "", "", "", "outside universe (market cap below ₹500 Cr)"]
    assert _still_noise(Decision(), None, row) and not _still_noise(Decision(), None, row, returning=True)
    sink = LocalSink(settings)
    sink.kv_set(universe.RETURNING_KEY, json.dumps({"543265": "2026-05-01", "500002": ""}), "now")
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.sink, pipeline.settings = sink, settings
    pipeline._kv_set = lambda key, value: sink.kv_set(key, value, "now")
    calls = []

    def retriage(scrip, day_from, day_to, returning=False):
        calls.append((scrip, day_from.isoformat(), returning))
        if scrip == "500002":
            raise RuntimeError("NSE refused")
        return ["n1", "n2"]

    pipeline.retriage_company = retriage
    import time as _time
    from datetime import date as _date
    assert pipeline.retriage_returning(_date(2026, 10, 22), _time.monotonic() + 60) == 2
    # the window never starts before the backfill's start; a failed lookup stays listed for the next run
    assert ("500002", settings.backfill_start, True) in calls and ("543265", "2026-05-01", True) in calls
    assert json.loads(sink.kv_get(universe.RETURNING_KEY)) == {"500002": ""}


def test_railtel_order_row_becomes_a_filing_on_our_key():
    nse_map = universe.NseUniverse({"INE0DD101019": "543265"}, {"RAILTEL": "543265"}, {"543265"}, True)
    row = _row("106821056", "RAILTEL", "INE0DD101019", "Bagging/Receiving of orders/contracts",
               "Railtel Corporation Of India Limited has informed the Exchange about Bagging/Receiving of orders/contracts")
    f = parse_announcement(row, nse_map.scrip_for)
    assert (f.news_id, f.scrip_code, f.symbol) == ("nse-106821056", "543265", "RAILTEL")
    assert f.subcategory == f.subject == "Bagging/Receiving of orders/contracts" and f.category == ""
    assert f.filed_at == "2026-10-17T13:37:56+05:30" and f.filing_date == "2026-10-17"
    assert f.pdf_url.startswith("https://nsearchives.nseindia.com/") and f.has_xbrl
    # A company NSE lists that our master does not have keeps its symbol, marked, to be set aside with the reason
    assert parse_announcement(_row("1", "NSEONLY", "INE777C01033", "Updates", "x"), nse_map.scrip_for).scrip_code == "NSE:NSEONLY"
    assert parse_announcement({"seq_id": "", "symbol": "X"}, nse_map.scrip_for) is None


def test_rule_book_reads_nse_subjects(settings):
    rules = RuleBook.from_config(settings.load_toml("taxonomy.toml"))

    def decide(desc, text):
        d = rules.classify(parse_announcement(_row("1", "X", "INE1", desc, text), lambda i, s: "1"))
        return d.action, d.event_type

    co = "Demo Limited has informed the Exchange"
    assert decide("Certificate under SEBI (Depositories and Participants) Regulations, 2018", f"{co} about Certificate")[0] == "DROP"
    assert decide("Analysts/Institutional Investor Meet/Con. Call Updates", f"{co} about Schedule of meet on 2nd November 2026.")[0] == "DROP"
    assert decide("Analysts/Institutional Investor Meet/Con. Call Updates", f"{co} about Transcript") == ("FAST_TRACK", "CONCALL_PRESENTATION")
    assert decide("Spurt in Volume", "Significant increase in volume has been observed in Demo Limited.")[0] == "DROP"
    assert decide("ESOP/ESOS/ESPS", f"{co} regarding Allotment of 84890 Shares.")[0] == "DROP"
    assert decide("Bagging/Receiving of orders/contracts", f"{co} about Bagging/Receiving of orders/contracts") == ("FAST_TRACK", "ORDER_WIN")
    assert decide("Outcome of Board Meeting", "Demo Limited has submitted to the Exchange, the financial results for the period ended "
                  "September 30, 2026.") == ("FAST_TRACK", "RESULTS")
    assert decide("Integrated Filing- Financial", "Outcome and financial results") == ("FAST_TRACK", "RESULTS")
    assert decide("Action(s) taken or orders passed", f"{co} about Action(s) taken") == ("FAST_TRACK", "LITIGATION_REGULATORY")
    assert decide("Copy of Newspaper Publication", f"{co} about Copy of Newspaper Publication")[0] == "DROP"
    assert decide("General Updates", f"{co} about General Updates")[0] == "PASS1"


class FakeNse:
    def __init__(self, rows, pdfs=None):
        self.rows, self.pdfs, self.calls = rows, pdfs or {}, []

    def announcements(self, day_from, day_to=None, symbol=None, scrip_for=lambda i, s: None):
        self.calls.append((day_from, day_to, symbol))
        out = [parse_announcement(r, scrip_for) for r in self.rows if not symbol or r["symbol"] == symbol]
        return [f for f in out if f]

    def fetch(self, url, max_bytes=None):
        return self.pdfs.get(url)


class NoBse:
    raw = None

    def __getattr__(self, name):
        raise AssertionError(f"BSE was called ({name}) with NSE discovery")


def _pipeline(settings, rows):
    settings = replace(settings, discovery_source="nse", universe_min_mcap_cr=100)
    sink = LocalSink(settings)
    body = universe.select(parse_equity_list(EQUITY_CSV), COMPANIES, 100)
    sink.put_object(universe.UNIVERSE_KEY, json.dumps(body).encode())
    gateway = AIGateway(settings.load_toml("providers.toml"), client_factory=lambda *a: FakeProvider({}), env={})
    nse = FakeNse(rows)
    return Pipeline(settings, sink, gateway, bse=NoBse(), nse=nse, sleep=lambda s: None), sink, nse


def test_discovery_from_nse_queues_our_companies_and_sets_the_rest_aside(settings):
    rows = [
        _row("101", "RAILTEL", "INE0DD101019", "Bagging/Receiving of orders/contracts", "RailTel has informed the Exchange about an order"),
        _row("102", "BALUFORGE", "INE011E01029", "Press Release", "Balu Forge has informed the Exchange regarding a press release"),
        _row("103", "TINYCO", "INE999A01011", "Press Release", "Tiny has informed the Exchange regarding a press release"),
        _row("104", "NSEONLY", "INE777C01033", "Press Release", "Only On NSE has informed the Exchange regarding a press release"),
        _row("105", "RAILTEL", "INE0DD101019", "Trading Window", "RailTel has informed the Exchange about Closure of Trading Window"),
    ]
    pipeline, sink, nse = _pipeline(settings, rows)
    assert pipeline.discover(date(2026, 10, 17)) == 5
    queued = {r["news_id"]: (r["scrip_code"], r["route"]) for r in
              sink._db.execute("select news_id, scrip_code, route from filings").fetchall()}
    assert queued == {"nse-101": ("543265", "FAST_TRACK"), "nse-102": ("531112", "FAST_TRACK")}  # a press release is read whole (2026-10-21)
    noise = json.loads(sink.get_object("noise/2026-10-17/000.json"))
    reasons = {r[0]: r[noise["fields"].index("reason")] for r in noise["rows"]}
    assert reasons["nse-103"].startswith("outside universe")
    assert reasons["nse-104"] == "not in the company master (listed on NSE only)"
    assert reasons["nse-105"] == "trading window"
    # A second discovery of the same day records nothing twice
    assert pipeline.discover(date(2026, 10, 17)) == 0


def test_company_discovery_asks_nse_by_symbol(settings):
    rows = [_row("201", "BALUFORGE", "INE011E01029", "Press Release", "Balu Forge press release", when="05-Oct-2026 10:00:00")]
    pipeline, sink, nse = _pipeline(settings, rows)
    assert pipeline.discover_company("531112", date(2026, 10, 1), date(2026, 10, 18)) == 1
    assert nse.calls == [(date(2026, 10, 1), date(2026, 10, 18), "BALUFORGE")]
    assert pipeline.discover_company("500002", date(2026, 10, 1), date(2026, 10, 18)) == 0   # BSE-only: nothing on NSE


def test_nse_discovery_without_a_universe_file_says_how_to_build_it(settings):
    settings = replace(settings, discovery_source="nse")
    sink = LocalSink(settings)
    gateway = AIGateway(settings.load_toml("providers.toml"), client_factory=lambda *a: FakeProvider({}), env={})
    pipeline = Pipeline(settings, sink, gateway, bse=NoBse(), nse=FakeNse([]), sleep=lambda s: None)
    try:
        pipeline.discover(date(2026, 10, 17))
    except RuntimeError as exc:
        assert "sync-universe" in str(exc)
    else:
        raise AssertionError("expected a stop")
