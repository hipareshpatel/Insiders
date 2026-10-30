"""The Results page's KPI rows from the saved statements only (results_table.py): the company page's source, no card."""
from test_fact_sheet import _entry, _memory, _rows

from bse_intel import results_table as rt


class _Sink:
    def __init__(self, dossiers):
        self.dossiers, self.sent = dossiers, []

    def list_dossiers(self):
        return sorted(self.dossiers)

    def get_dossier(self, scrip):
        return self.dossiers[scrip]

    def execute(self, statement, rows):
        assert statement == "results_kpi_upsert"
        self.sent += rows
        return len(rows)

    def query(self, name, params):
        assert name == "results_cards_recent"   # the query the results catch-up already uses
        return [{"scrip_code": "500001"}, {"scrip_code": "500001"}, {"scrip_code": None}]


def test_a_quarter_table_is_the_statements_rows_with_changes_worked_out_by_code():
    table = rt.company_tables(_memory())["Q2FY27"]
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


def test_consolidated_over_standalone_and_standalone_only_when_there_is_no_consolidated():
    both = rt.company_tables(_memory())["Q2FY27"]
    assert both["basis"] == "CONSOLIDATED" and both["revenue"]["value"] == 1200.0   # not the standalone 5.0
    alone = {"statements": [_entry("Q2FY27", _rows(5.0, 1.0, 1.0, 1.0), basis="STANDALONE")]}
    assert rt.company_tables(alone)["Q2FY27"]["basis"] == "STANDALONE"


def test_a_kpi_row_has_the_growth_figures_and_a_digest_that_changes_with_them():
    row = next(r for r in rt.company_rows("500001", _memory(), "t1") if r["period"] == "Q2FY27")
    assert (row["revenue"], row["revenue_yoy"], row["pat"], row["pat_yoy"]) == (1200.0, 20.0, 148.0, 25.0)
    assert row["opm"] == 20.0 and row["opm_yoy_bps"] == 0 and row["ebitda_yoy"] == 20.0
    assert row["pat_turn"] is None and row["pat_key"] == 25.0
    again = next(r for r in rt.company_rows("500001", _memory(), "t2") if r["period"] == "Q2FY27")
    assert again["digest"] == row["digest"] and again["updated_at"] == "t2"   # the time is not part of the digest
    changed = _memory()
    changed["statements"][0]["rows"]["Sales"] = 1300.0
    assert next(r for r in rt.company_rows("500001", changed, "t3") if r["period"] == "Q2FY27")["digest"] != row["digest"]


def test_a_loss_turned_to_profit_is_a_named_turn_with_a_sort_key_beside_the_per_cents():
    memory = {"statements": [_entry("Q2FY27", _rows(1200.0, 240.0, 200.0, 50.0)), _entry("Q2FY26", _rows(1000.0, 200.0, 160.0, -20.0))]}
    row = rt.company_rows("500009", memory, "t")[0]
    assert row["pat_turn"] == "LOSS_TO_PROFIT" and row["pat_yoy"] is None and row["pat_key"] == rt.TURN_KEY["LOSS_TO_PROFIT"] > 1000


def test_the_full_rebuild_sends_every_company_and_a_bad_one_is_skipped():
    sink = _Sink({"500001": _memory(), "500002": {"statements": []}, "500003": None})
    assert rt.write(sink, "t") == len(sink.sent) > 0
    assert {r["scrip_code"] for r in sink.sent} == {"500001"}


def test_a_run_sends_only_the_live_windows_companies():
    sink = _Sink({"500001": _memory(), "500002": _memory()})
    assert rt.recent_scrips(sink) == ["500001"]
    rt.write(sink, "t", rt.recent_scrips(sink))
    assert {r["scrip_code"] for r in sink.sent} == {"500001"}


def test_nothing_is_sent_when_there_is_nothing():
    sink = _Sink({"500002": {"statements": []}})
    assert rt.write(sink, "t") == 0 and sink.sent == []


def test_the_upsert_writes_the_table_and_an_unchanged_row_is_not_rewritten(settings):
    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    rows = rt.company_rows("500001", _memory(), "t1")
    assert sink.execute("results_kpi_upsert", rows) == len(rows)
    assert sink.execute("results_kpi_upsert", rt.company_rows("500001", _memory(), "t2")) == 0   # same figures: no D1 row write
    stored = sink._db.execute("SELECT revenue, revenue_yoy, pat_key, updated_at FROM results_kpi WHERE scrip_code = '500001' AND period = 'Q2FY27'").fetchone()
    assert tuple(stored) == (1200.0, 20.0, 25.0, "t1")
    changed = _memory()
    changed["statements"][0]["rows"]["Sales"] = 1300.0
    assert sink.execute("results_kpi_upsert", rt.company_rows("500001", changed, "t3")) == 1
    assert sink._db.execute("SELECT revenue, updated_at FROM results_kpi WHERE period = 'Q2FY27'").fetchone()[:] == (1300.0, "t3")
