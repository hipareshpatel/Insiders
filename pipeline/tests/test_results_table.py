"""The Results page's KPI rows from the saved statements only (results_table.py): the company page's source, no card."""
from test_fact_sheet import _entry, _memory, _rows

from bse_intel import results_table as rt


class _Sink:
    def __init__(self, dossiers, industries=None):
        self.dossiers, self.sent, self.industries = dossiers, [], industries or {}

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
        if name == "export_companies":   # the companies table, paged by scrip code (company_master.stored_companies)
            return [{"scrip_code": k, "industry": v} for k, v in sorted(self.industries.items()) if k > params[0]][:params[1]]
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
    # the profit before exceptional items is in a row only for a quarter that has one (its absence keeps the digest)
    # and the whole profit only where it differs from the owners' (this memory has a minority share)
    assert sorted(row) == sorted(set(columns) - {"pat_pre", "pat_pre_prev", "pat_pre_yoy", "pat_pre_turn"}) and rt.QUARTERS_KEPT == 10
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


def test_a_margin_change_is_not_given_when_a_margin_is_past_100_per_cent_or_the_base_ebitda_is_negative():
    # live, 31 Oct 2026: SADHNANIQ Q2FY27 17.92% against -628.89% gave +64,681 bp
    memory = {"statements": [_entry("Q2FY27", _rows(100.0, 17.92, 20.0, 15.0)), _entry("Q2FY26", _rows(10.0, -62.889, -70.0, -70.0, opm=-628.89)),
                             _entry("Q1FY27", _rows(90.0, 16.0, 18.0, 13.0)), ]}
    row = _row(memory)
    assert (row["opm"], row["opm_yoy_bps"]) == (17.92, None)   # the base margin is out of range and its EBITDA negative
    assert row["opm_qoq_bps"] == round((17.92 - 17.78) * 100)   # last quarter's margin is fine
    # a negative base EBITDA with an in-range margin is no base either
    memory = {"statements": [_entry("Q2FY27", _rows(100.0, 10.0, 12.0, 9.0)), _entry("Q2FY26", _rows(100.0, -5.0, -6.0, -6.0, opm=-5.0))]}
    assert _row(memory)["opm_yoy_bps"] is None


# --- the profit before exceptional items (illustrative figures shaped like two live quarters of 31 Oct 2026) ---

def _with_exceptional(period, rows, exc, at, **kw):
    return _entry(period, {**rows, "Exceptional items": exc, **({} if at is None else {"Exceptional items AT": at})}, **kw)


def test_a_big_exceptional_gain_gives_the_profit_before_it_and_its_growth_on_the_same_row_rule():
    # CGPOWER-like: PAT 412.0 against 18.24 (+2,159%); an exceptional gain of 300 after tax leaves 112.0, and the year-ago quarter had none filed
    memory = {"statements": [_with_exceptional("Q2FY27", _rows(2900.0, 400.0, 560.0, 412.0, owners=412.0), 400.0, 300.0),
                             _entry("Q2FY26", _rows(2500.0, 300.0, 24.0, 18.24, owners=18.24))]}
    row = _row(memory)
    assert (row["pat"], row["pat_yoy"]) == (412.0, 2158.8)
    assert (row["pat_pre"], row["pat_pre_prev"], row["pat_pre_yoy"], row["pat_pre_turn"]) == (112.0, 18.24, 514.0, None)


def test_the_base_is_the_year_ago_profit_less_its_own_exceptional_item_and_a_turn_across_a_loss_is_named():
    # ABREL-like: PAT 858.5 on revenue 825.0 (profit above revenue); a 700 gain after tax leaves 158.5; a year ago a 50 loss after tax hid a profit of 20
    memory = {"statements": [_with_exceptional("Q2FY27", _rows(825.0, 200.0, 900.0, 858.5, owners=858.5), 800.0, 700.0),
                             _with_exceptional("Q2FY26", _rows(700.0, 150.0, -40.0, -30.0, owners=-30.0), -60.0, -50.0)]}
    row = _row(memory)
    assert row["pat_turn"] == "LOSS_TO_PROFIT"
    assert (row["pat_pre"], row["pat_pre_prev"]) == (158.5, 20.0) and row["pat_pre_yoy"] == 692.5 and row["pat_pre_turn"] is None
    loss = {"statements": [_with_exceptional("Q2FY27", _rows(825.0, 200.0, 900.0, 858.5, owners=858.5), 800.0, 700.0),
                           _with_exceptional("Q2FY26", _rows(700.0, 150.0, -40.0, -90.0, owners=-90.0), -60.0, -50.0)]}
    assert _row(loss)["pat_pre_turn"] == "LOSS_TO_PROFIT" and _row(loss)["pat_pre_yoy"] is None   # -40 a year ago: a turn, not a per cent


def test_no_profit_before_exceptional_items_without_a_non_zero_exceptional_item_after_tax():
    plain = {"statements": [_entry("Q2FY27", _rows(1200.0, 240.0, 200.0, 150.0, owners=148.0)), _entry("Q2FY26", _rows(1000.0, 200.0, 160.0, 120.0, owners=118.4))]}
    zero = {"statements": [_with_exceptional("Q2FY27", _rows(1200.0, 240.0, 200.0, 150.0, owners=148.0), 0.0, 0.0), plain["statements"][1]]}
    untaxed = {"statements": [_with_exceptional("Q2FY27", _rows(1200.0, 240.0, 200.0, 150.0, owners=148.0), 40.0, None), plain["statements"][1]]}
    for memory in (plain, zero, untaxed):
        row = _row(memory)
        assert not any(k in ("pat_pre", "pat_pre_prev", "pat_pre_yoy", "pat_pre_turn") for k in row)   # the key is left out, so the row's digest is what it was before the columns


def test_a_row_without_one_offs_keeps_its_old_digest_and_a_bank_or_nbfc_gets_the_line_too():
    base = next(r for r in rt.company_rows("500001", _memory(), "t") if r["period"] == "Q2FY27")
    assert "pat_pre" not in base
    bank = {"statements": [_bank("Q2FY27", 100.0, 30.0, **{"Net Profit (owners)": 28.0, "Exceptional items AT": 8.0, "Exceptional items": 10.0}),
                           _bank("Q2FY26", 80.0, 20.0, **{"Net Profit (owners)": 24.0})]}
    row = _row(bank)
    assert (row["pat_pre"], row["pat_pre_prev"], row["pat_pre_yoy"]) == (20.0, 24.0, -16.7)


def test_the_database_statement_and_migration_hold_the_new_columns(settings):
    from bse_intel.sinks.local import LocalSink
    memory = {"statements": [_with_exceptional("Q2FY27", _rows(2900.0, 400.0, 560.0, 412.0, owners=412.0), 400.0, 300.0),
                             _entry("Q2FY26", _rows(2500.0, 300.0, 24.0, 18.24, owners=18.24))]}
    rows = rt.company_rows("500001", memory, "t")
    sink = LocalSink(settings)
    sink.execute(rt.STATEMENT, rows)
    got = sink._db.execute("SELECT pat_pre, pat_pre_prev, pat_pre_yoy FROM results_kpi WHERE period='Q2FY27'").fetchone()
    assert tuple(got) == (112.0, 18.24, 514.0)
    assert sink.execute(rt.STATEMENT, rows) == 0   # unchanged: nothing rewritten
def _holding(period, sales, op, net, margin):
    return _entry(period, {"Revenue": sales, "Sales": sales, "Financing Profit": sales * 0.1, "Financing Margin %": 10.0, "Operating Profit": op, "OPM %": margin,
                           "Net Profit": net}, family="nbfc")


def _nbfc_template():
    return {"statements": [_holding("Q2FY27", 700.0, 70.0, 20.0, 10.0), _holding("Q2FY26", 600.0, 48.0, 10.0, 8.0), _holding("Q1FY27", 650.0, 65.0, 15.0, 10.0)]}


def test_an_nbfc_template_filer_in_a_non_financial_industry_gets_the_corporate_layout_and_kind_company():
    for industry in ("Consumer Services > Restaurants", "Capital Goods > Industrial Products", "Services > Commercial Services & Supplies"):
        row = next(r for r in rt.company_rows("500020", _nbfc_template(), "t", industry) if r["period"] == "Q2FY27")
        assert row["kind"] == "company" and (row["revenue"], row["revenue_yoy"]) == (700.0, 16.7)
        assert (row["ebitda"], row["ebitda_prev"], row["ebitda_yoy"], row["opm"], row["opm_yoy_bps"]) == (70.0, 48.0, 45.8, 10.0, 200)   # operating profit, not financing profit


def test_real_lenders_and_a_company_with_no_industry_stay_as_they_are():
    for industry in ("Financial Services > Finance > Non Banking Financial Company (NBFC)", "Financial Services", "Finance", " finance ", None, ""):
        row = next(r for r in rt.company_rows("500020", _nbfc_template(), "t", industry) if r["period"] == "Q2FY27")
        assert row["kind"] == "nbfc" and row["ebitda"] == 70.0 and row["ebitda_prev"] == 60.0 and row["opm"] == 10.0   # financing profit and margin, as before
    assert rt.non_lender("Consumer Services > Restaurants") and not rt.non_lender("Finance") and not rt.non_lender(None)


def test_the_run_passes_each_companys_industry_from_the_companies_table():
    sink = _Sink({"500020": _nbfc_template(), "500021": _nbfc_template(), "500022": _nbfc_template()},
                 {"500020": "Consumer Services > Restaurants", "500021": "Financial Services > Finance > Housing Finance Company"})
    rt.write(sink, "t")
    kinds = {r["scrip_code"]: r["kind"] for r in sink.sent}
    assert kinds == {"500020": "company", "500021": "nbfc", "500022": "nbfc"}   # 500022 has no industry stored: as today


def test_a_failed_industry_read_builds_the_table_as_before_and_does_not_stop_the_run():
    sink = _Sink({"500020": _nbfc_template()}, {"500020": "Consumer Services > Restaurants"})
    sink.query = lambda name, params: (_ for _ in ()).throw(RuntimeError("D1 timeout")) if name == "export_companies" else []
    rt.write(sink, "t")
    assert sink.sent and {r["kind"] for r in sink.sent} == {"nbfc"}   # every quarter as before: the NBFC layout


def test_an_owners_row_beside_a_year_ago_filler_zero_still_finds_its_base():
    # measured 31 Oct 2026, live: KAYNES Q1FY27 PAT 56.43 against Q1FY26 74.61 (owners' line a filler 0) had no YoY
    memory = {"statements": [_entry("Q1FY27", _rows(1000.0, 150.0, 80.0, 57.0, owners=56.43)), _entry("Q1FY26", _rows(900.0, 130.0, 100.0, 74.61, owners=0.0))]}
    pat = rt.company_tables(memory)["Q1FY27"]["pat"]
    assert (pat["value"], pat["prev_year"], pat["yoy_pct"]) == (56.43, 74.61, -24.4)


def test_an_nbfc_template_filer_in_insurance_gets_the_insurer_layout():
    for industry in ("Financial Services > Insurance > Life Insurance", "Financial Services > Insurance > General Insurance"):
        row = next(r for r in rt.company_rows("500020", _nbfc_template(), "t", industry) if r["period"] == "Q2FY27")
        assert row["kind"] == "insurer" and (row["pat"], row["revenue"], row["ebitda"], row["opm"]) == (20.0, None, None, None)
    row = next(r for r in rt.company_rows("500020", _nbfc_template(), "t", "Financial Services > Finance > NBFC") if r["period"] == "Q2FY27")
    assert row["kind"] == "nbfc"


def _slip(period, pbt, tax, net, owners=None, minority=None):
    rows = _rows(6591.0, 757.57, pbt, net, owners=owners)
    rows["Tax"] = tax
    if minority is not None:
        rows["Minority share"] = minority
    return _entry(period, rows)


def test_a_profit_on_the_wrong_side_of_pbt_less_tax_is_a_slip_and_a_genuine_loss_stays():
    # measured 31 Oct 2026, live: APARINDS Q1FY27 PAT -138.56 beside PBT about 600
    memory = {"statements": [_slip("Q1FY27", 625.0, 157.55, -138.56, owners=-138.56, minority=0.0), _slip("Q1FY26", 300.0, 75.0, 225.0, owners=225.0, minority=0.0)]}
    pat = rt.company_tables(memory)["Q1FY27"]["pat"]
    assert (pat["value"], pat["yoy_pct"]) == (467.45, 107.8)
    # the same slip in the year-ago quarter: the base is PBT - tax
    memory = {"statements": [_slip("Q1FY27", 400.0, 100.0, 300.0, owners=300.0, minority=0.0), _slip("Q1FY26", 625.0, 157.55, -138.56, owners=-138.56, minority=0.0)]}
    assert rt.company_tables(memory)["Q1FY27"]["pat"]["prev_year"] == 467.45
    # a real loss: PBT - tax is negative too, so nothing changes
    loss = {"statements": [_slip("Q1FY27", -150.0, -20.0, -130.0, owners=-130.0, minority=0.0)]}
    assert rt.company_tables(loss)["Q1FY27"]["pat"]["value"] == -130.0
    # a minority share that turns the owners' profit negative is not a slip
    minority = {"statements": [_slip("Q1FY27", 30.0, 10.0, 20.0, owners=-8.0, minority=28.0)]}
    assert rt.company_tables(minority)["Q1FY27"]["pat"]["value"] == -8.0


def test_primesecu_like_nbfc_quarters_find_their_bases_beside_filler_owners_rows():
    # measured 31 Oct 2026, live: PRIMESECU Q1FY27 3.49 vs Q1FY26 10.48 and Q4FY26 -10.93 vs Q4FY25 0.80 had no change at all: the
    # current quarters carry a real owners' row, the older ones a filler 0 that used to be dropped
    memory = {"statements": [_entry("Q4FY26", _rows(30.2, 5.0, -12.0, -10.93, owners=-10.93), family="nbfc"),
                             _entry("Q4FY25", _rows(12.33, 2.0, 1.0, 0.8, owners=0.0), family="nbfc"),
                             _entry("Q3FY26", _rows(30.18, 6.0, 3.0, 2.1, owners=0.0), family="nbfc")]}
    pat = rt.company_tables(memory)["Q4FY26"]["pat"]
    assert (pat["prev_year"], pat["yoy_turn"], pat["prev_quarter"], pat["qoq_turn"]) == (0.8, "PROFIT_TO_LOSS", 2.1, "PROFIT_TO_LOSS")


def test_an_owners_profit_that_does_not_add_up_with_the_minoritys_to_the_whole_is_the_whole_less_the_minority():
    # measured 31 Oct 2026, NSE's ATUL Q2FY26 file: profit 182.37, owners 87.95, minority 3.13 (Tijori 179.24); the page showed +77.1% for Q2FY27
    def atul(period, net, owners, minority):
        rows = _rows(1500.0, 300.0, 230.1, net, owners=owners)
        rows["Minority share"] = minority
        return _entry(period, rows)
    memory = {"statements": [atul("Q2FY27", 158.8, 155.67, 3.13), atul("Q2FY26", 182.37, 87.95, 3.13)]}
    pat = rt.company_tables(memory)["Q2FY27"]["pat"]
    assert (pat["prev_year"], pat["yoy_pct"]) == (179.24, -13.1)
    # rows that add up (within 0.5%) are left alone, and with no minority row the owners' row stays
    assert rt.company_tables({"statements": [atul("Q2FY27", 158.8, 155.67, 3.13), atul("Q2FY26", 100.0, 96.9, 3.1)]})["Q2FY27"]["pat"]["prev_year"] == 96.9
    bare = {"statements": [_entry("Q2FY27", _rows(1500.0, 300.0, 230.1, 182.37, owners=87.95))]}
    assert rt.company_tables(bare)["Q2FY27"]["pat"]["value"] == 87.95


def test_a_bank_takes_screeners_financing_profit_and_margin_in_the_ebitda_slots():
    # owner, 31 Oct 2026: match Screener, banks get a figure (screener_view.bank_pl: Revenue - Interest - Expenses, provisions inside Expenses)
    def bank(period, revenue, fp, margin, net):
        return _bank(period, revenue, net, **{"Financing Profit": fp, "Financing Margin %": margin})
    memory = {"statements": [bank("Q2FY27", 1000.0, 400.0, 40.0, 250.0), bank("Q2FY26", 900.0, 300.0, 33.33, 200.0), bank("Q1FY27", 950.0, 380.0, 40.0, 240.0)]}
    row = _row(memory)
    assert row["kind"] == "bank" and (row["ebitda"], row["ebitda_prev"], row["ebitda_yoy"], row["ebitda_qoq"]) == (400.0, 300.0, 33.3, 5.3)
    assert (row["opm"], row["opm_yoy_bps"]) == (40.0, 667) and row["nfo"] == 0   # never "profit up, EBITDA down" for a lender


def test_the_whole_profit_sits_beside_the_owners_profit_only_when_they_differ():
    """Owner, 31 Oct 2026: "Both, owners' first" (Phoenix Mills Q2FY27: owners 325.71, +7.1%; whole 427.00, +11.2%, as the news quoted)."""
    memory = {"statements": [_bank("Q2FY27", 100.0, 30.0, **{"Net Profit (owners)": 28.0}), _bank("Q2FY26", 80.0, 20.0, **{"Net Profit (owners)": 24.0}),
                             _bank("Q1FY27", 95.0, 27.0, **{"Net Profit (owners)": 25.0})]}
    row = _row(memory)
    assert (row["pat"], row["pat_yoy"]) == (28.0, 16.7)
    assert (row["pat_total"], row["pat_total_prev"], row["pat_total_yoy"], row["pat_total_turn"]) == (30.0, 20.0, 50.0, None)
    same = {"statements": [_bank("Q2FY27", 100.0, 30.0, **{"Net Profit (owners)": 30.0}), _bank("Q2FY26", 80.0, 20.0, **{"Net Profit (owners)": 20.0})]}
    assert "pat_total" not in _row(same)            # no minority share: the PAT is already the whole profit (the digest is kept)
