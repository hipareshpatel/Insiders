"""Module 42: promoter pledges from NSE's SAST Reg 31 feed (pledges.py). Rows as NSE served them on 2026-10-19."""

from bse_intel.pledges import encumbered, merge, parse_row, signals, summary

VINCOFE_RELEASE = {"attachment": "https://nsearchives.nseindia.com/corporate/VINCOFE_10152026122851.zip",
                   "broadcastdate": "15-Oct-2026 12:28:51", "companyName": "Vintage Coffee And Beverages Limited",
                   "encumbHolding": "4910548", "encumbPerc": "3.35", "eventDate": "06-Oct-2026 - 06-Oct-2026",
                   "eventDetailsEntity": "Punjab National Bank", "eventDetailsFromDate": "06-Oct-2026",
                   "eventDetailsHolding": "4910548", "eventDetailsPerc": "3.35", "eventDetailsToDate": "06-Oct-2026",
                   "eventDetailsType": "Release", "eventDetailsTypeEncumb": "Pledge", "postEventHolding": "0",
                   "postEventHoldingPerc": "     0.00", "preeventHolding": "19769586", "preeventHoldingPerc": "    13.50",
                   "promoterName": "Balakrishna Tati", "reportingDate": "08-Oct-2026", "seqId": "43712", "symbol": "VINCOFE"}
CENTRUM_CREATION = {"broadcastdate": "15-Oct-2026 12:27:21", "encumbHolding": "6450000", "encumbPerc": "1.29",
                    "eventDetailsEntity": "Beacon Trusteeship Limited (for the NCDs issued to Ugro Capital Ltd)",
                    "eventDetailsFromDate": "07-Oct-2026", "eventDetailsHolding": "19500000", "eventDetailsPerc": "3.91",
                    "eventDetailsType": "Creation", "eventDetailsTypeEncumb": "Pledge", "postEventHolding": "25950000",
                    "postEventHoldingPerc": "     5.20", "preeventHoldingPerc": "    13.88",
                    "promoterName": "JBCG Advisory Services Private Limited", "seqId": "43721", "symbol": "CENTRUM"}


def test_a_feed_row_becomes_a_memory_event():
    e = parse_row(VINCOFE_RELEASE)
    assert (e["symbol"], e["event"], e["type"], e["event_on"], e["as_of"]) == (
        "VINCOFE", "RELEASED", "Pledge", "2026-10-06", "2026-10-15T12:28:51+05:30")
    assert (e["pct"], e["before_pct"], e["after_pct"], e["promoter_pct"]) == (3.35, 3.35, 0.0, 13.5)
    assert e["lender"] == "Punjab National Bank" and e["seq_id"] == "43712"
    assert parse_row({"symbol": "X"}) is None                     # no time, no event: not an event
    assert parse_row({**VINCOFE_RELEASE, "eventDetailsPerc": "NA"})["pct"] is None


def test_events_are_kept_once_and_in_order():
    d = {}
    assert merge(d, [parse_row(CENTRUM_CREATION)]) == 1
    assert merge(d, [parse_row(CENTRUM_CREATION)]) == 0           # the same disclosure again
    refiled = {**CENTRUM_CREATION, "seqId": None, "broadcastdate": "16-Oct-2026 10:00:00"}
    assert merge(d, [parse_row(refiled)]) == 1                    # no sequence id: a new row, kept by its facts
    assert merge(d, [parse_row(refiled)]) == 0
    assert [e["as_of"][:10] for e in d["pledges"]["events"]] == ["2026-10-15", "2026-10-16"]
    assert d["pledges"]["summary"] == {"encumbered_pct": 5.2, "promoters": 1, "as_of": "2026-10-16T10:00:00+05:30"}


def test_encumbrance_is_each_promoters_latest_figure_summed():
    a = parse_row(CENTRUM_CREATION)
    b = {**a, "promoter": "Other Promoter", "after_pct": 2.0, "as_of": "2026-10-16T10:00:00+05:30", "seq_id": "9"}
    c = {**a, "after_pct": 1.0, "as_of": "2026-10-17T10:00:00+05:30", "seq_id": "10"}   # the first promoter released some
    assert encumbered([a, b, c]) == {"JBCG ADVISORY SERVICES": 1.0, "OTHER PROMOTER": 2.0}
    s = summary({"pledges": {"events": [a, b, c]}})
    assert s["encumbered_pct"] == 3.0 and s["promoters"] == 2 and s["invoked"] == []
    assert summary({}) is None


def test_signals_for_a_card_invoked_rising_released():
    older = {**parse_row(CENTRUM_CREATION), "event_on": "2026-05-01", "as_of": "2026-05-02T10:00:00+05:30",
             "after_pct": 1.29, "seq_id": "1"}
    rising = {**parse_row(CENTRUM_CREATION), "seq_id": "2"}       # 1.29% -> 5.20% on 7 Oct
    got = signals({"pledges": {"events": [older, rising]}}, "2026-10-19T10:00:00+05:30")
    assert got == [("WARNING", "Promoter shares pledged up from 1.29% to 5.20% of the company in 90 days (1 disclosure).")]

    invoked = {**rising, "event": "INVOKED", "lender": "Axis Bank", "pct": 0.8, "after_pct": 4.4, "seq_id": "3",
               "as_of": "2026-10-18T10:00:00+05:30", "event_on": "2026-10-17"}
    got = signals({"pledges": {"events": [older, rising, invoked]}}, "2026-10-19T10:00:00+05:30")
    assert got[0] == ("WARNING", "Pledge invoked: Axis Bank took 0.80% of the company pledged by "
                                 "JBCG Advisory Services Private Limited (2026-10-17).")

    held = {**parse_row(VINCOFE_RELEASE), "event": "CREATED", "after_pct": 3.35, "event_on": "2026-03-01",
            "as_of": "2026-03-02T10:00:00+05:30", "seq_id": "4"}
    released = parse_row(VINCOFE_RELEASE)
    got = signals({"pledges": {"events": [held, released]}}, "2026-10-19T10:00:00+05:30")
    assert got == [("POSITIVE", "Promoter pledges released in full: 3.35% of the company 90 days ago, none now.")]

    # nothing in the last 90 days: no line; no memory: no line
    assert signals({"pledges": {"events": [held]}}, "2026-10-19T10:00:00+05:30") == []
    assert signals({}, "2026-10-19") == [] and signals(None, "2026-10-19") == []


def test_a_card_sees_only_the_events_known_when_it_was_filed():
    from bse_intel.dossier import dossier_as_of

    d = {"pledges": {"events": [parse_row(CENTRUM_CREATION)]}}
    assert dossier_as_of(d, "2026-10-14T23:00:00+05:30")["pledges"]["events"] == []
    assert len(dossier_as_of(d, "2026-10-15T13:00:00+05:30")["pledges"]["events"]) == 1


def test_sync_files_universe_companies_and_stops_when_refused():
    from types import SimpleNamespace

    from bse_intel import nse as nse_api
    from bse_intel import pledges

    class Sink:
        def __init__(self):
            self.dossiers = {"532000": {"scrip_code": "532000"}}

        def get_dossier(self, scrip):
            return self.dossiers.get(scrip)

        def put_dossier(self, scrip, d):
            self.dossiers[scrip] = d

        def company(self, scrip):
            return {"company_name": "Vintage Coffee"} if scrip == "543000" else None

    class Nse:
        calls = 0

        def encumbrances(self, a, b):
            Nse.calls += 1
            return [CENTRUM_CREATION, VINCOFE_RELEASE, {"symbol": "BROKEN"}]

    sink = Sink()
    universe = SimpleNamespace(built=True, symbols={"CENTRUM": "532000", "VINCOFE": "543000"}, included={"532000", "543000"})
    import bse_intel.pledges as module
    original = module.universe.load_nse
    module.universe.load_nse = lambda s: universe
    try:
        report = pledges.sync(SimpleNamespace(nse=Nse(), sink=sink), deadline=1e12, days=40)
        # the same rows in both windows: counted twice as listed, filed once; Vintage had no memory and gets one
        assert report["filed"] == 2 and report["companies"] == 2 and report["in_universe"] == 4
        assert sink.dossiers["543000"]["pledges"]["events"][0]["event"] == "RELEASED"
        assert report["listed"] == 3 * Nse.calls and len(report["errors"]) == Nse.calls   # the broken row, each month asked
        assert Nse.calls == 2                                     # 40 days asked as two windows of at most 31
        assert len(sink.dossiers["532000"]["pledges"]["events"]) == 1

        class Refused:
            def encumbrances(self, a, b):
                raise nse_api.SourceBlockedError("HTTP 403")

        report = pledges.sync(SimpleNamespace(nse=Refused(), sink=sink), deadline=1e12)
        assert report["stopped"].startswith("NSE refused")
        report = pledges.sync(SimpleNamespace(nse=None, sink=sink), deadline=1e12)
        assert report["stopped"].startswith("NSE not asked")
    finally:
        module.universe.load_nse = original



def test_live_data_edge_cases_names_group_figures_first_events_and_invocations():
    """From the live feed (2026-10-19): one promoter spelt two ways (Hindustan Zinc), group figures on one promoter's
    row (Advent Hotels), a promoter whose first event is in the window (start at its own "before"), and an invocation,
    whose "after" figure is the holding left, not the shares still encumbered."""
    base = parse_row(CENTRUM_CREATION)
    hzl = [{**base, "promoter": "VEDANTA LIMITED", "type": "Others", "promoter_pct": 60.71, "before_pct": 50.0,
            "after_pct": 55.04, "seq_id": "a", "as_of": "2026-06-30T10:00:00+05:30", "event_on": "2026-06-30"},
           {**base, "promoter": "Vedanta Ltd.", "type": "Others", "promoter_pct": 60.71, "before_pct": 55.04,
            "after_pct": 52.6, "seq_id": "b", "as_of": "2026-09-28T10:00:00+05:30", "event_on": "2026-09-28"}]
    assert encumbered(hzl) == {"VEDANTA": 52.6}
    assert summary({"pledges": {"events": hzl}})["encumbered_pct"] == 52.6

    advent = [{**base, "promoter": "Aseela Vinod Goenka", "promoter_pct": 2.99, "before_pct": 67.71, "after_pct": 65.69,
               "event": "RELEASED", "seq_id": "c"}]
    assert summary({"pledges": {"events": advent}})["encumbered_pct"] is None
    assert signals({"pledges": {"events": advent}}, "2026-10-19T10:00:00+05:30") == []

    devx = [{**base, "promoter": "Rushit Shah", "type": "Others", "promoter_pct": 6.55, "before_pct": 0.0, "after_pct": 6.55,
             "seq_id": "d", "event_on": "2026-07-31", "as_of": "2026-08-01T10:00:00+05:30"}]
    assert signals({"pledges": {"events": devx}}, "2026-10-19T10:00:00+05:30") == [
        ("WARNING", "Promoter shares encumbered (pledges and other encumbrances) up from 0.00% to 6.55% of the company "
                    "in 90 days (1 disclosure).")]
    repledged = [{**devx[0], "before_pct": 6.0}]             # already 6% encumbered before its first event in memory
    assert signals({"pledges": {"events": repledged}}, "2026-10-19T10:00:00+05:30") == []

    invoked = {**base, "promoter": "X Holdings", "promoter_pct": 40.0, "before_pct": 30.0, "pct": 5.0,
               "after_pct": 35.0, "event": "INVOKED", "seq_id": "e"}          # after = 40 - 5: the holding left
    assert encumbered([invoked]) == {"X HOLDINGS": 25.0}
