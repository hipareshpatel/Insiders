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
        assert statement in ("results_kpi_upsert", "results_kpi_prune")
        if statement == "results_kpi_prune":
            self.pruned = getattr(self, "pruned", []) + rows
            return len(rows)
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


def _bank(period, revenue, net, basis="CONSOLIDATED", **extra):
    return _entry(period, {"Revenue": revenue, "Interest": revenue / 2, "Profit before tax": net * 1.3, "Net Profit": net, **extra},
                  basis=basis, family="bank")


def _nbfc(period, revenue, fin_profit, net, margin):
    return _entry(period, {"Revenue": revenue, "Sales": revenue, "Financing Profit": fin_profit, "Financing Margin %": margin,
                           "Net Profit": net}, family="nbfc")


def _row(memory, period="Q2FY27"):
    return next(r for r in rt.company_rows("500010", memory, "t") if r["period"] == period)


def test_a_bank_has_revenue_and_profit_but_no_ebitda_or_margin():
    memory = {"statements": [_bank("Q2FY27", 100.0, 30.0, **{"Net Profit (owners)": 28.0}), _bank("Q2FY26", 80.0, 20.0, **{"Net Profit (owners)": 24.0}),
                             _bank("Q1FY27", 95.0, 27.0, **{"Net Profit (owners)": 25.0})]}
    row = _row(memory)
    assert row["kind"] == "bank" and (row["revenue"], row["revenue_prev"], row["revenue_yoy"], row["revenue_qoq"]) == (100.0, 80.0, 25.0, 5.3)
    assert (row["pat"], row["pat_prev"], row["pat_yoy"], row["pat_qoq"]) == (28.0, 24.0, 16.7, 12.0)
    assert (row["ebitda"], row["ebitda_key"], row["opm"], row["opm_yoy_bps"], row["nfo"]) == (None, None, None, None, 0)


def test_an_nbfc_keeps_its_financing_profit_and_margin_in_the_ebitda_columns():
    memory = {"statements": [_nbfc("Q2FY27", 500.0, 300.0, 120.0, 60.0), _nbfc("Q2FY26", 400.0, 200.0, 100.0, 50.0), _nbfc("Q1FY27", 480.0, 290.0, 110.0, 60.4)]}
    row = _row(memory)
    assert row["kind"] == "nbfc" and (row["revenue"], row["revenue_yoy"]) == (500.0, 25.0)
    assert (row["ebitda"], row["ebitda_prev"], row["ebitda_yoy"], row["ebitda_qoq"]) == (300.0, 200.0, 50.0, 3.4)
    assert (row["opm"], row["opm_yoy_bps"], row["opm_qoq_bps"]) == (60.0, 1000, -40)
    assert row["nfo"] == 0   # never for a lender, whatever the figures


def test_an_insurer_has_profit_only_and_a_quarter_without_a_profit_line_has_no_row():
    memory = {"statements": [_entry("Q2FY27", {"Net Profit": 50.0}, family="insurer"), _entry("Q2FY26", {"Net Profit": 40.0}, family="insurer"),
                             _entry("Q1FY27", {"Revenue": 9.0}, family="bank")]}
    row = _row(memory)
    assert row["kind"] == "insurer" and (row["pat"], row["pat_yoy"]) == (50.0, 25.0)
    assert (row["revenue"], row["ebitda"], row["opm"]) == (None, None, None)
    assert "Q1FY27" not in {r["period"] for r in rt.company_rows("500010", memory, "t")}


def test_a_corporate_row_has_kind_company_prev_amounts_and_both_loss_turns():
    memory = {"statements": [_entry("Q2FY27", _rows(1200.0, 240.0, 200.0, 50.0)), _entry("Q2FY26", _rows(1000.0, 200.0, 160.0, -20.0)),
                             _entry("Q1FY27", _rows(1100.0, 200.0, 150.0, -30.0))]}
    row = _row(memory)
    assert row["kind"] == "company" and (row["revenue_prev"], row["ebitda_prev"], row["pat_prev"]) == (1000.0, 200.0, -20.0)
    assert (row["pat_turn"], row["pat_qoq_turn"], row["pat_yoy"], row["pat_qoq"]) == ("LOSS_TO_PROFIT", "LOSS_TO_PROFIT", None, None)
    assert row["revenue_yoy"] == 20.0 and row["ebitda_yoy"] == 20.0   # revenue never has a turn; ebitda here is a plain per cent


def test_each_family_takes_consolidated_over_standalone():
    memory = {"statements": [_bank("Q2FY27", 100.0, 30.0), _bank("Q2FY27", 90.0, 25.0, basis="STANDALONE")]}
    assert (_row(memory)["basis"], _row(memory)["revenue"]) == ("CONSOLIDATED", 100.0)
    memory = {"statements": [_entry("Q2FY27", {"Net Profit": 5.0}, family="insurer", basis="STANDALONE")]}
    assert _row(memory)["basis"] == "STANDALONE"
    # a consolidated entry with no profit line gives way to the standalone one
    memory = {"statements": [_entry("Q2FY27", {"Revenue": 100.0}, family="bank"), _bank("Q2FY27", 90.0, 25.0, basis="STANDALONE")]}
    assert (_row(memory)["basis"], _row(memory)["pat"]) == ("STANDALONE", 25.0)


def test_profit_not_from_operations_needs_a_company_with_profit_up_and_ebitda_down():
    def row_of(now, before):
        return _row({"statements": [_entry("Q2FY27", now), _entry("Q2FY26", before)]})
    assert row_of(_rows(1200.0, 180.0, 200.0, 150.0), _rows(1000.0, 200.0, 160.0, 120.0))["nfo"] == 1        # profit +25%, EBITDA -10%
    assert row_of(_rows(1200.0, 240.0, 200.0, 150.0), _rows(1000.0, 200.0, 160.0, 120.0))["nfo"] == 0        # EBITDA up
    assert row_of(_rows(1200.0, 180.0, 200.0, 100.0), _rows(1000.0, 200.0, 160.0, 120.0))["nfo"] == 0        # profit down
    assert row_of(_rows(1200.0, 180.0, 200.0, 50.0), _rows(1000.0, 200.0, 160.0, -20.0))["nfo"] == 1         # loss to profit, EBITDA down
    assert row_of(_rows(1200.0, -10.0, 200.0, 50.0), _rows(1000.0, 200.0, 160.0, 40.0))["nfo"] == 1          # EBITDA profit to loss
    assert row_of(_rows(1200.0, 180.0, 200.0, 150.0), _rows(1000.0, 200.0, 160.0, 120.0))["ebitda_turn"] is None


def test_the_source_filing_is_kept_only_when_it_is_an_nse_one_and_is_part_of_the_digest():
    memory = _memory()
    assert _row(memory)["source_news_id"] is None   # the test entries carry "n-..." ids
    memory["statements"][0]["source_news_id"] = "nse-123"
    row = _row(memory)
    assert row["source_news_id"] == "nse-123"
    other = _memory()
    other["statements"][0]["source_news_id"] = "nse-456"
    assert _row(other)["digest"] != row["digest"]


def test_the_row_keys_are_the_tables_columns_and_ten_quarters_are_kept(settings):
    from bse_intel.sinks.local import LocalSink

    row = rt.company_rows("500001", _memory(), "t")[0]
    columns = [c[1] for c in LocalSink(settings)._db.execute("PRAGMA table_info(results_kpi)")]
    assert sorted(row) == sorted(columns) and rt.QUARTERS_KEPT == 10
    memory = {"statements": [_entry(f"Q{q}FY{y}", _rows(100.0 + y, 20.0, 15.0, 10.0)) for y in range(20, 28) for q in range(1, 5)]}
    assert len(rt.company_rows("500001", memory, "t")) == 10


def test_the_upsert_writes_the_table_and_an_unchanged_row_is_not_rewritten(settings):
    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    rows = rt.company_rows("500001", _memory(), "t1")
    assert sink.execute("results_kpi_upsert", rows) == len(rows)
    assert sink.execute("results_kpi_upsert", rt.company_rows("500001", _memory(), "t2")) == 0   # same figures: no D1 row write
    stored = sink._db.execute("SELECT revenue, revenue_yoy, pat_key, updated_at FROM results_kpi WHERE scrip_code = '500001' AND period = 'Q2FY27'").fetchone()
    assert tuple(stored) == (1200.0, 20.0, 25.0, "t1")
    assert sink._db.execute("SELECT kind, revenue_prev, pat_prev, nfo FROM results_kpi WHERE period = 'Q2FY27'").fetchone()[:] == ("company", 1000.0, 118.4, 0)
    changed = _memory()
    changed["statements"][0]["rows"]["Sales"] = 1300.0
    assert sink.execute("results_kpi_upsert", rt.company_rows("500001", changed, "t3")) == 1
    assert sink._db.execute("SELECT revenue, updated_at FROM results_kpi WHERE period = 'Q2FY27'").fetchone()[:] == (1300.0, "t3")


def test_a_quarter_the_statements_no_longer_hold_is_removed_from_the_database(settings):
    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    sink.execute("results_kpi_upsert", rt.company_rows("500001", _memory(), "t1") + rt.company_rows("500002", _memory(), "t1"))
    before = sink._db.execute("SELECT count(*) FROM results_kpi WHERE scrip_code = '500001'").fetchone()[0]
    assert before >= 2
    memory = _memory()
    memory["statements"] = [e for e in memory["statements"] if e["period"] != "Q2FY26"]   # a quarter the statements no longer hold
    now = rt.company_rows("500001", memory, "t2")
    kept = [{"scrip_code": "500001", "periods": [r["period"] for r in now]}]
    sink.execute("results_kpi_prune", kept)
    left = {r[0] for r in sink._db.execute("SELECT period FROM results_kpi WHERE scrip_code = '500001'")}
    assert left == {r["period"] for r in now} and "Q2FY26" not in left
    assert sink._db.execute("SELECT count(*) FROM results_kpi WHERE scrip_code = '500002'").fetchone()[0] == before   # another company untouched


def test_write_prunes_only_companies_that_have_rows_now():
    sink = _Sink({"500001": _memory(), "500002": {"statements": []}})
    assert rt.write(sink, "t", ["500001", "500002"]) == len(sink.sent)
    assert [k["scrip_code"] for k in sink.pruned] == ["500001"]   # an empty read is no proof that old rows are wrong


def test_a_zero_base_going_to_a_loss_is_a_loss_that_appeared_not_a_profit_turned():
    memory = {"statements": [_entry("Q2FY27", _rows(1200.0, -5.0, 200.0, 150.0)), _entry("Q2FY26", _rows(1000.0, 0.0, 160.0, 100.0))]}
    assert rt.company_tables(memory)["Q2FY27"]["ebitda"]["yoy_turn"] == "LOSS_WIDENED"


def test_a_long_run_saves_as_it_goes(monkeypatch):
    monkeypatch.setattr(rt, "SAVE_EVERY", 2)
    names = ["500001", "500002", "500003", "500004", "500005"]
    sink = _Sink({n: _memory() for n in names})
    sink.list_dossiers = lambda: names
    saves = []
    execute = sink.execute
    sink.execute = lambda statement, rows: (saves.append(statement), execute(statement, rows))[1]
    total = rt.write(sink, "t")
    assert total == len(sink.sent) and total == 5 * len(rt.company_rows("500001", _memory(), "t"))
    assert saves.count("results_kpi_upsert") == 3     # after 2, after 4, and the last one
    assert sorted(k["scrip_code"] for k in sink.pruned) == names


def test_a_filler_zero_owners_profit_gives_way_to_the_net_profit():
    # measured 31 Oct 2026: 204 live quarters showed a profit of 0 (PNB Housing Q2FY27 NBFC, Kaynes Q2FY26), the owners' line a filler
    memory = {"statements": [_entry("Q2FY27", _rows(2423.15, 812.59, 700.0, 560.0, owners=0.0), family="nbfc"),
                             _entry("Q2FY26", _rows(2127.86, 773.3, 650.0, 500.0, owners=0.0), family="nbfc")]}
    table = rt.company_tables(memory)["Q2FY27"]
    assert table["pat"]["value"] == 560.0 and table["pat"]["yoy_pct"] == 12.0
    real = {"statements": [_entry("Q2FY27", _rows(1200.0, 240.0, 200.0, 0.0, owners=0.0))]}
    assert rt.company_tables(real)["Q2FY27"]["pat"]["value"] == 0.0   # a true zero (both lines 0) stays
