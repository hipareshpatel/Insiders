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


def test_the_table_is_refreshed_and_a_company_that_left_an_index_goes_but_a_skipped_index_keeps_its_rows(settings):
    sink = LocalSink(settings)
    a, b = {"isin": "INE001", "symbol": "AAA", "company_name": "A"}, {"isin": "INE002", "symbol": "BBB", "company_name": "B"}
    im.write(sink, {"NIFTY50": [a, b], "NIFTY100": [a, b]}, "2026-10-25")
    im.write(sink, {"NIFTY50": [a]}, "2026-11-01")   # B left the Nifty 50; the Nifty 100 list was not taken this week
    rows = {tuple(r) for r in sink._db.execute("SELECT index_id, isin, as_of FROM index_members")}
    assert rows == {("NIFTY50", "INE001", "2026-11-01"), ("NIFTY100", "INE001", "2026-10-25"), ("NIFTY100", "INE002", "2026-10-25")}


def test_a_week_with_nothing_taken_changes_nothing(settings):
    sink = LocalSink(settings)
    assert im.write(sink, {}, "2026-11-01") == 0


def test_sync_reports_what_was_written_and_what_was_kept(settings):
    class Client:
        def __init__(self, sizes): self.sizes = sizes
        def _get(self, url):
            name = url.rsplit("/", 1)[-1]
            return type("R", (), {"text": _fetch(self.sizes)(name)})()
    sizes = {name: size for _i, _l, name, size in im.INDEXES}
    sizes["ind_niftymicrocap250_list.csv"] = 0
    report = im.sync(LocalSink(settings), Client(sizes), "2026-11-01")
    assert "MICROCAP250" in report.skipped and report.members["NIFTY50"] == 50 and report.written == sum(report.members.values())
