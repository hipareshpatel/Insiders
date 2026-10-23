"""Insider trades from NSE's SEBI PIT Regulation 7 filings (insider.py). XBRL files as NSE served them on 22 Oct 2026."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from bse_intel import insider
from bse_intel.insider import merge, parse

FIX = Path(__file__).parent / "fixtures"
KVB = (FIX / "nse_pit_karurvysya_20261022.xml").read_bytes()
DMART = (FIX / "nse_pit_dmart_20261022.xml").read_bytes()
KVB_ROW = {"appId": "4038", "symbol": "KARURVYSYA", "broadcastDateTime": "22-Oct-2026 19:29:01",
           "regulation": "Regulation 7 (2)", "typeOfSubmission": "Original",
           "xmlFileName": "https://nsearchives.nseindia.com/corporate/xbrl/IT_539_WebXMLFile_20261022_192901476.xml"}


def test_each_disclosure_is_a_trade():
    events = parse(KVB, KVB_ROW)
    assert len(events) == 3
    e = events[0]
    assert (e["symbol"], e["person"], e["category"], e["side"], e["qty"]) == (
        "KARURVYSYA", "G Rajasekaran", "Promoter", "SELL", 2000.0)
    assert e["value_cr"] == 0.0769                       # ₹7,69,230
    assert (e["before_qty"], e["before_pct"], e["after_qty"], e["after_pct"]) == (1982319.0, 0.21, 1980319.0, 0.2)
    assert (e["from"], e["to"], e["filed"], e["mode"], e["exchange"]) == (
        "2026-10-21", "2026-10-21", "2026-10-22", "Market Sale", "NSE")
    assert (e["filing_id"], e["regulation"], e["revised"]) == ("4038", "Regulation 7 (2)", False)


def test_a_pledge_invocation_keeps_its_own_type_and_no_exchange():
    e = parse(DMART)[0]
    assert (e["symbol"], e["side"], e["category"], e["exchange"], e["filing_id"]) == (
        "DMART", "PLEDGE INVOKE", "Designated Person", None, None)


def test_trades_are_kept_once_even_when_a_revision_repeats_them():
    d = {}
    assert merge(d, parse(KVB, KVB_ROW), "4038") == 3
    revision = {**KVB_ROW, "appId": "4051", "typeOfSubmission": "Revision"}
    assert merge(d, parse(KVB, revision), "4051") == 0
    assert d["insider_trades"]["filings"] == ["4038", "4051"]


class _Sink:
    def __init__(self):
        self.dossiers = {}

    def get_dossier(self, scrip):
        return self.dossiers.get(scrip)

    def put_dossier(self, scrip, dossier):
        self.dossiers[scrip] = dossier

    def company(self, scrip):
        return {"company_name": "Karur Vysya Bank"}


class _Nse:
    def __init__(self):
        self.fetched = []

    def insider_filings(self, start, stop):
        return [KVB_ROW, {**KVB_ROW, "appId": "9", "symbol": "NOTOURS"}]

    def fetch(self, url, max_bytes=0):
        self.fetched.append(url)
        return KVB


def test_sync_files_universe_trades_and_reads_a_filing_once(monkeypatch):
    nse_map = SimpleNamespace(built=True, symbols={"KARURVYSYA": "590003"}, included={"590003"})
    monkeypatch.setattr(insider.universe, "load_nse", lambda sink: nse_map)
    pipeline = SimpleNamespace(nse=_Nse(), sink=_Sink())
    report = insider.sync(pipeline, deadline=float("inf"), days=3, today=date(2026, 10, 22))
    assert (report["listed"], report["in_universe"], report["read"], report["filed"], report["companies"]) == (2, 1, 1, 3, 1)
    assert len(pipeline.sink.dossiers["590003"]["insider_trades"]["events"]) == 3
    again = insider.sync(pipeline, deadline=float("inf"), days=3, today=date(2026, 10, 22))
    assert (again["read"], again["filed"]) == (0, 0) and len(pipeline.nse.fetched) == 1
