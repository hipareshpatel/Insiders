"""The results page's figures from the saved statements only (results_table.py): the company page's source, no card."""
import json

from test_fact_sheet import _entry, _memory, _rows

from bse_intel import results_table as rt


class _Sink:
    def __init__(self, dossiers):
        self.dossiers, self.objects = dossiers, {}

    def list_dossiers(self):
        return sorted(self.dossiers)

    def get_dossier(self, scrip):
        return self.dossiers[scrip]

    def put_object(self, key, body, content_type="application/json"):
        self.objects[key] = body

    def get_object(self, key):
        return self.objects.get(key)

    def query(self, name, params):
        assert name == "results_cards_recent"   # the query the results catch-up already uses
        return [{"scrip_code": "500001"}, {"scrip_code": "500001"}, {"scrip_code": None}]


def test_a_quarter_table_is_the_statements_rows_with_changes_worked_out_by_code():
    tables = rt.company_tables(_memory())
    table = tables["Q2FY27"]
    assert (table["lens"], table["period"], table["basis"]) == ("company", "Q2FY27", "CONSOLIDATED")
    assert table["revenue"]["value"] == 1200.0 and table["revenue"]["prev_year"] == 1000.0 and table["revenue"]["yoy_pct"] == 20.0
    assert table["pat"]["value"] == 148.0   # the profit to shareholders, as the card's PAT line
    assert table["ebitda_margin"]["yoy_bps"] == 0


def test_a_quarter_the_statements_do_not_hold_has_no_table():
    assert "Q3FY27" not in rt.company_tables(_memory())
    assert rt.company_tables({"statements": []}) == {}
    assert rt.company_tables({}) == {}


def test_a_statement_not_from_the_file_is_not_used():
    memory = {"statements": [_entry("Q2FY27", _rows(1200.0, 240.0, 200.0, 150.0), by="card")]}
    assert rt.company_tables(memory) == {}


def test_only_the_latest_quarters_are_kept():
    memory = {"statements": [_entry(f"Q{q}FY{y}", _rows(100.0 + y, 20.0, 15.0, 10.0)) for y in range(20, 28) for q in range(1, 5)]}
    assert len(rt.company_tables(memory)) == rt.QUARTERS_KEPT


def _file(sink, scrip):
    return json.loads(sink.objects[f"{rt.PREFIX}{scrip}.json"])


def test_the_full_rebuild_is_a_small_file_per_company_and_a_bad_company_is_skipped():
    sink = _Sink({"500001": _memory(), "500002": {"statements": []}, "500003": None})
    count = rt.write(sink, "2026-10-30T20:00:00+05:30")
    assert count == len(_file(sink, "500001")["rows"]) > 0
    assert "Q2FY27" in _file(sink, "500001")["rows"] and _file(sink, "500001")["built_at"].startswith("2026-10-30")
    assert _file(sink, "500002")["rows"] == {}   # a company with no table is marked by an empty file
    assert f"{rt.PREFIX}500003.json" in sink.objects   # no dossier: nothing in it, an empty file


def test_a_run_writes_only_the_live_windows_companies():
    sink = _Sink({"500001": _memory(), "500002": _memory()})
    rt.write(sink, "t1")
    before = sink.objects[f"{rt.PREFIX}500002.json"]
    sink.dossiers["500001"] = {"statements": [_entry("Q2FY27", _rows(2400.0, 480.0, 400.0, 300.0))]}   # a revised file
    sink.dossiers["500002"] = {"statements": []}   # not in the window: not read again
    assert rt.recent_scrips(sink) == ["500001"]
    rt.write(sink, "t2", rt.recent_scrips(sink))
    assert _file(sink, "500001")["rows"]["Q2FY27"]["revenue"]["value"] == 2400.0 and list(_file(sink, "500001")["rows"]) == ["Q2FY27"]
    assert sink.objects[f"{rt.PREFIX}500002.json"] == before


def test_consolidated_over_standalone_and_standalone_only_when_there_is_no_consolidated():
    both = rt.company_tables(_memory())["Q2FY27"]
    assert both["basis"] == "CONSOLIDATED" and both["revenue"]["value"] == 1200.0   # not the standalone 5.0
    alone = {"statements": [_entry("Q2FY27", _rows(5.0, 1.0, 1.0, 1.0), basis="STANDALONE")]}
    assert rt.company_tables(alone)["Q2FY27"]["basis"] == "STANDALONE"
