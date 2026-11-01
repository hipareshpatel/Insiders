"""Bulk and block deals from NSE's large-deals snapshot (deals.py). Rows as NSE served them on 22 Oct 2026."""

from bse_intel.deals import merge, parse_row

RAVITA_BULK = {"buySell": "BUY", "clientName": "YASH HITESH PATEL", "date": "22-Oct-2026",
               "name": "Ravita Engineering Ser L", "qty": "529200", "remarks": "-", "symbol": "RAVITA", "watp": "112"}
CAPINVIT_BLOCK = {"buySell": "BUY", "clientName": "LARSEN & TOUBRO LIMITED", "date": "22-Oct-2026",
                  "name": "Capital Infra Trust", "qty": "6644519", "remarks": None, "symbol": "CAPINVIT", "watp": "75.59"}
SHORT_ROW = {"buySell": None, "clientName": None, "date": "21-Oct-2026", "name": "ADITYA BIRLA CAPITAL LIMITED",
             "qty": "400", "remarks": None, "symbol": "ABCAPITAL", "watp": None}


def test_a_snapshot_row_becomes_a_deal():
    e = parse_row(RAVITA_BULK, "BULK")
    assert (e["kind"], e["symbol"], e["date"], e["side"], e["client"]) == (
        "BULK", "RAVITA", "2026-10-22", "BUY", "YASH HITESH PATEL")
    assert (e["qty"], e["price"], e["value_cr"], e["remarks"]) == (529200.0, 112.0, 5.93, None)
    block = parse_row(CAPINVIT_BLOCK, "BLOCK")
    assert block["value_cr"] == 50.23 and block["client"] == "LARSEN & TOUBRO LIMITED"
    assert parse_row(SHORT_ROW, "BULK") is None          # a short-selling row: no side, no price
    assert parse_row({**RAVITA_BULK, "watp": "-"}, "BULK")["value_cr"] is None


def test_deals_are_kept_once_and_in_order():
    d = {}
    assert merge(d, [parse_row(RAVITA_BULK, "BULK")]) == 1
    assert merge(d, [parse_row(RAVITA_BULK, "BULK")]) == 0                  # the morning read and the nightly read
    sell = {**RAVITA_BULK, "buySell": "SELL", "clientName": "SOME FUND", "date": "21-Oct-2026"}
    assert merge(d, [parse_row(sell, "BULK")]) == 1
    assert [(e["date"], e["side"]) for e in d["market_deals"]["events"]] == [("2026-10-21", "SELL"), ("2026-10-22", "BUY")]


def test_sync_files_universe_companies_and_fails_on_a_bot_page(monkeypatch):
    from types import SimpleNamespace

    from bse_intel import deals

    class Sink:
        def __init__(self):
            self.dossiers = {"543000": {"scrip_code": "543000"}}

        def get_dossier(self, scrip):
            return self.dossiers.get(scrip)

        def put_dossier(self, scrip, d):
            self.dossiers[scrip] = d

        def company(self, scrip):
            return None

    class Nse:
        def large_deals(self):
            return {"BULK_DEALS_DATA": [RAVITA_BULK, {"symbol": "BROKEN"}], "BLOCK_DEALS_DATA": [CAPINVIT_BLOCK],
                    "SHORT_DEALS_DATA": [SHORT_ROW]}

    class BotPage:
        def large_deals(self):
            raise ValueError("Expecting value: line 2 column 1")   # NSE's HTML page where JSON was asked for

    universe = SimpleNamespace(built=True, symbols={"RAVITA": "543000"}, included={"543000"})
    monkeypatch.setattr(deals.universe, "load_nse", lambda s: universe)
    sink = Sink()
    report = deals.sync(SimpleNamespace(nse=Nse(), sink=sink), deadline=1e12)
    assert (report["listed"], report["in_universe"], report["filed"], report["companies"]) == (3, 1, 1, 1)
    assert report["sessions"] == ["2026-10-22"] and len(report["errors"]) == 1   # the broken row; short rows not read
    assert sink.dossiers["543000"]["market_deals"]["events"][0]["client"] == "YASH HITESH PATEL"
    again = deals.sync(SimpleNamespace(nse=Nse(), sink=sink), deadline=1e12)
    assert again["filed"] == 0
    failed = deals.sync(SimpleNamespace(nse=BotPage(), sink=sink), deadline=1e12)
    assert failed["stopped"].startswith("snapshot unreadable")


def test_market_deals_leave_the_m_and_a_deals_list_alone():
    """A company's memory already holds "deals", the list of its M&A and order deals: the first deals-sync runs (23 Oct
    2026, market-data and nightly) failed on every company with "'list' object has no attribute 'get'"."""
    d = {"deals": [{"deal_id": "d1", "kind": "ORDER_WIN", "amount_cr": 120.0}]}
    assert merge(d, [parse_row(RAVITA_BULK, "BULK")]) == 1
    assert d["deals"] == [{"deal_id": "d1", "kind": "ORDER_WIN", "amount_cr": 120.0}]
    assert len(d["market_deals"]["events"]) == 1


HISTORY_CSV = ('﻿"Date ","Symbol ","Security Name ","Client Name ","Buy / Sell ","Quantity Traded ",'
               '"Trade Price / Wght. Avg. Price ","Remarks "\n'
               '"21-OCT-2026","ABH","ABH Healthcare Limited","RIKHAV SECURITIES LIMITED","SELL","88,800","42.08","-"\n')


def test_a_history_csv_line_becomes_the_same_deal_as_a_snapshot_row():
    from bse_intel.deals import csv_rows

    rows = csv_rows(HISTORY_CSV)
    e = parse_row(rows[0], "BULK")
    assert (e["symbol"], e["date"], e["client"], e["side"], e["qty"], e["price"], e["value_cr"]) == (
        "ABH", "2026-10-21", "RIKHAV SECURITIES LIMITED", "SELL", 88800.0, 42.08, 0.37)
    snap = {"buySell": "SELL", "clientName": "RIKHAV SECURITIES LIMITED", "date": "21-Oct-2026", "qty": "88800",
            "symbol": "ABH", "watp": "42.08"}
    d = {}
    assert merge(d, [e]) == 1 and merge(d, [parse_row(snap, "BULK")]) == 0   # the backfill and the morning read agree


def test_the_backfill_walks_the_history_a_week_at_a_time(monkeypatch):
    from datetime import date
    from types import SimpleNamespace

    from bse_intel import deals

    asked = []

    class Nse:
        def deals_history(self, kind, start, stop):
            asked.append((kind, start, stop))
            return HISTORY_CSV if kind == "bulk_deals" else '"Date ","Symbol "\n'

    class Sink:
        dossiers = {}

        def get_dossier(self, scrip):
            return self.dossiers.get(scrip)

        def put_dossier(self, scrip, dossier):
            self.dossiers[scrip] = dossier

        def company(self, scrip):
            return {}

    nse_map = SimpleNamespace(built=True, symbols={"ABH": "1"}, included={"1"})
    monkeypatch.setattr(deals.universe, "load_nse", lambda sink: nse_map)
    report = deals.backfill(SimpleNamespace(nse=Nse(), sink=Sink()), float("inf"), days=13, today=date(2026, 10, 22))
    assert report["windows"] == 2 and len(asked) == 4
    assert asked[0][1:] == (date(2026, 10, 9), date(2026, 10, 15)) and asked[2][1:] == (date(2026, 10, 16), date(2026, 10, 22))
    assert report["filed"] == 1 and report["in_universe"] == 2 and not report["errors"]


def test_a_bigger_order_is_no_stage_update_of_an_earlier_one():
    # OSWALPUMPS nse-106836003 (audit of 1 Nov 2026): Rs 235.92 Cr for an additional 10,000 pumps linked to May's Rs 162.06 Cr
    from bse_intel.models import DealValue
    from bse_intel.pipeline import grown_order
    view = {"deals": [{"id": "d_a95fc979", "kind": "ORDER", "amount_cr": 162.06}]}
    assert grown_order(DealValue(kind="ORDER", amount_cr=235.92, updates_deal_id="d_a95fc979"), view)
    assert not grown_order(DealValue(kind="ORDER", amount_cr=162.06, updates_deal_id="d_a95fc979"), view)   # the LOI's work order
    assert not grown_order(DealValue(kind="ORDER", amount_cr=29.0, updates_deal_id="d_a95fc979"), view)     # part of it converted
    assert not grown_order(DealValue(kind="ORDER", amount_cr=235.92), view)
