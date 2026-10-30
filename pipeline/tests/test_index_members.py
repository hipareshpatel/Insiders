"""NSE's broad index constituents, refreshed every Sunday (index_members.py)."""
import pytest

from bse_intel import index_members as im
from bse_intel.nse import SourceBlockedError
from bse_intel.sinks.local import LocalSink

HEAD = "Company Name,Industry,Symbol,Series,ISIN Code\n"


def _csv(*rows):
    return HEAD + "".join(f"{n},Financial Services,{s},EQ,{i}\n" for n, s, i in rows)


def test_a_list_gives_isin_symbol_and_name_and_leaves_out_placeholders_blanks_and_repeats():
    text = "﻿" + _csv(("HDFC Bank Ltd.", "hdfcbank", "inE040A01034"), ("Demerger stand-in", "DUMMYHEG", "INE000000001"),
                       ("No ISIN Ltd.", "NOISIN", ""), ("HDFC Bank Ltd.", "HDFCBANK", "INE040A01034"))
    assert im.parse_members(text) == [{"isin": "INE040A01034", "symbol": "HDFCBANK", "company_name": "HDFC Bank Ltd."}]
    assert im.parse_members("") == [] and im.parse_members(None) == []


def test_a_list_is_the_whole_index_only_when_its_size_is_near():
    assert im.plausible(50, 50) and im.plausible(47, 50) and im.plausible(500, 500)
    assert not im.plausible(0, 50) and not im.plausible(12, 50) and not im.plausible(80, 50)


def _fetch(sizes: dict[str, int], fail=()):
    def fetch(name):
        if name in fail:
            raise RuntimeError("HTTP 500")
        return _csv(*[(f"Co {i}", f"S{i}", f"INE{name[4:9]}{i:05d}") for i in range(sizes.get(name, 0))])
    return fetch


def test_every_index_with_a_whole_list_is_taken_and_a_cut_or_failed_one_is_kept_out_with_its_reason():
    sizes = {name: size for _i, _l, name, size in im.INDEXES}
    sizes["ind_nifty100list.csv"] = 12   # a cut download
    taken, skipped = im.read_all(_fetch(sizes, fail={"ind_nifty200list.csv"}))
    assert "NIFTY100" not in taken and "12 members" in skipped["NIFTY100"]
    assert "NIFTY200" not in taken and "HTTP 500" in skipped["NIFTY200"]
    assert len(taken["NIFTY50"]) == 50 and len(taken["NIFTY500"]) == 500 and len(taken) == len(im.INDEXES) - 2


def test_a_source_block_stops_the_run_it_is_not_one_index_missing():
    def fetch(name):
        raise SourceBlockedError("403")
    with pytest.raises(SourceBlockedError):
        im.read_all(fetch)


A = {"isin": "INE001", "symbol": "AAA", "company_name": "A"}
B = {"isin": "INE002", "symbol": "BBB", "company_name": "B"}
C = {"isin": "INE003", "symbol": "CCC", "company_name": "C"}


def _stretches(sink, index_id="NIFTY50"):
    return sorted(tuple(r) for r in sink._db.execute(
        "SELECT isin, valid_from, valid_to FROM index_members WHERE index_id = ?", (index_id,)))


def _members_on(sink, day, index_id="NIFTY50"):
    return sorted(r[0] for r in sink._db.execute(
        "SELECT isin FROM index_members WHERE index_id = ? AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)",
        (index_id, day, day)))


def test_the_first_read_of_an_index_starts_its_members_at_the_sentinel_and_sets_tracking_since_once(settings):
    sink = LocalSink(settings)
    report = im.write(sink, {"NIFTY50": [A, B]}, "2026-11-01")
    assert _stretches(sink) == [("INE001", "1900-01-01", None), ("INE002", "1900-01-01", None)]
    assert (report.adds, report.closes, report.written, report.members) == (2, 0, 2, {"NIFTY50": 2})
    assert sink.kv_get(im.TRACKING_KEY) == "2026-11-01"
    im.write(sink, {"NIFTY50": [A, B]}, "2026-11-08")
    assert sink.kv_get(im.TRACKING_KEY) == "2026-11-01"   # set once


def test_a_second_identical_read_writes_nothing(settings):
    sink = LocalSink(settings)
    im.write(sink, {"NIFTY50": [A, B]}, "2026-11-01")
    report = im.write(sink, {"NIFTY50": [A, B]}, "2026-11-08")
    assert (report.adds, report.closes, report.written, report.added, report.closed) == (0, 0, 0, {}, {})
    assert len(_stretches(sink)) == 2


def test_a_company_that_leaves_gets_valid_to_and_stays_in_history_and_one_that_joins_starts_that_day(settings):
    sink = LocalSink(settings)
    im.write(sink, {"NIFTY50": [A, B]}, "2026-11-01")
    report = im.write(sink, {"NIFTY50": [A, C]}, "2026-11-08")
    assert _stretches(sink) == [("INE001", "1900-01-01", None), ("INE002", "1900-01-01", "2026-11-08"), ("INE003", "2026-11-08", None)]
    assert report.added == {"NIFTY50": ["CCC"]} and report.closed == {"NIFTY50": ["BBB"]}


def test_a_company_that_returns_gets_a_new_row_and_the_members_on_a_day_follow_the_history(settings):
    sink = LocalSink(settings)
    im.write(sink, {"NIFTY50": [A, B]}, "2026-11-01")
    im.write(sink, {"NIFTY50": [A]}, "2026-11-08")
    im.write(sink, {"NIFTY50": [A, B]}, "2026-11-22")
    assert _stretches(sink) == [("INE001", "1900-01-01", None), ("INE002", "1900-01-01", "2026-11-08"), ("INE002", "2026-11-22", None)]
    assert _members_on(sink, "2026-10-01") == ["INE001", "INE002"]   # before tracking: the first list stands in
    assert _members_on(sink, "2026-11-07") == ["INE001", "INE002"]
    assert _members_on(sink, "2026-11-08") == ["INE001"]             # valid_to is the first day out
    assert _members_on(sink, "2026-11-21") == ["INE001"]
    assert _members_on(sink, "2026-11-22") == ["INE001", "INE002"]


def test_a_skipped_index_changes_nothing_and_each_index_is_read_alone(settings):
    sink = LocalSink(settings)
    im.write(sink, {"NIFTY50": [A, B], "NIFTY100": [A, B]}, "2026-11-01")
    report = im.write(sink, {"NIFTY50": [A]}, "2026-11-08")   # the Nifty 100 list was not taken this week
    assert _stretches(sink, "NIFTY100") == [("INE001", "1900-01-01", None), ("INE002", "1900-01-01", None)]
    assert _stretches(sink)[1] == ("INE002", "1900-01-01", "2026-11-08")
    assert "NIFTY100" not in report.members


def test_a_week_with_nothing_taken_changes_nothing(settings):
    sink = LocalSink(settings)
    assert im.write(sink, {}, "2026-11-01").written == 0
    assert sink.kv_get(im.TRACKING_KEY) is None


def test_sync_reports_what_was_written_and_what_was_kept(settings):
    class Client:
        def __init__(self, sizes): self.sizes = sizes
        def _get(self, url):
            name = url.rsplit("/", 1)[-1]
            return type("R", (), {"text": _fetch(self.sizes)(name)})()
    sizes = {name: size for _i, _l, name, size in im.INDEXES}
    sizes["ind_niftymicrocap250_list.csv"] = 0
    report = im.sync(LocalSink(settings), Client(sizes), "2026-11-01")
    assert "MICROCAP250" in report.skipped and report.members["NIFTY50"] == 50 and report.written == sum(report.members.values()) and report.adds == report.written
    assert report.as_dict()["skipped"] == report.skipped


def test_a_first_run_that_died_halfway_does_not_start_the_rest_at_today(settings):
    sink = LocalSink(settings)
    # an earlier first run stored A and then failed before the tracking day was saved
    sink.execute("index_members_add", [{"index_id": "NIFTY50", "isin": "INE001", "symbol": "AAA", "company_name": "A", "valid_from": im.FIRST_READ}])
    assert sink.kv_get(im.TRACKING_KEY) is None
    report = im.write(sink, {"NIFTY50": [A, B]}, "2026-11-08")
    assert _stretches(sink) == [("INE001", "1900-01-01", None), ("INE002", "1900-01-01", None)]   # B is a first-read member too, not a joiner of 2026-11-08
    assert report.added == {} and sink.kv_get(im.TRACKING_KEY) == "2026-11-08"


def test_an_index_added_later_is_a_first_read_of_its_own(settings):
    sink = LocalSink(settings)
    im.write(sink, {"NIFTY50": [A, B]}, "2026-11-01")
    report = im.write(sink, {"NIFTY50": [A, B], "NIFTY100": [A, C]}, "2026-11-08")
    assert _stretches(sink, "NIFTY100") == [("INE001", "1900-01-01", None), ("INE003", "1900-01-01", None)]   # earlier members unknown, not "joined today"
    assert report.added == {} and sink.kv_get(im.TRACKING_KEY) == "2026-11-01"
