"""statements-correct (owner, 31 Oct 2026): the profit-line rules over the stored quarters and annual entries, dry run by default,
a backup before every write, only changed dossiers written, saved chunk by chunk, resuming."""
from bse_intel import restore, statements_correct as sc
from bse_intel.sinks.local import LocalSink


def _entry(period, rows, family="corporate", table="quarters", by="file", basis="CONSOLIDATED"):
    return {"period": period, "basis": basis, "table": table, "family": family, "rows": rows, "source_news_id": f"n-{period}", "lab": {"by": by}}


ATUL = {"Net Profit": 182.37, "Net Profit (owners)": 87.95, "Minority share": 3.13, "Profit before tax": 230.1, "Tax": 48.91}
APAR = {"Net Profit": -138.56, "Net Profit (owners)": -138.56, "Minority share": 0.0, "Profit before tax": 625.0, "Tax": 157.55}
PNB = {"Net Profit": 560.0, "Net Profit (owners)": 0.0}
FINE = {"Net Profit": 100.0, "Net Profit (owners)": 96.9, "Minority share": 3.1, "Profit before tax": 130.0, "Tax": 30.0}


def _sink(settings):
    sink = LocalSink(settings)
    sink.put_dossier("500001", {"scrip_code": "500001", "statements": [_entry("Q2FY26", ATUL)]})
    sink.put_dossier("500002", {"scrip_code": "500002", "statements": [_entry("Q1FY27", APAR)]})
    sink.put_dossier("500003", {"scrip_code": "500003", "statements": [_entry("Q2FY27", PNB, family="nbfc")]})
    sink.put_dossier("500004", {"scrip_code": "500004", "statements": [_entry("Q2FY27", FINE), _entry("Q2FY27", ATUL, by="card"),
                                                                       _entry("Q2FY27", ATUL, table="balance")]})
    return sink


def test_a_dry_run_lists_the_changes_and_writes_nothing(settings):
    sink = _sink(settings)
    before = {s: sink.get_dossier(s) for s in sink.list_dossiers()}
    out = sc.run(sink, sink.list_dossiers())
    assert out["error"] is None and out["written"] == 0 and out["backup"] is None and out["changed_dossiers"] == 3
    got = {(c["scrip"], c["row"]): (c["old"], c["new"]) for c in out["changes"]}
    assert got == {("500001", "Net Profit (owners)"): (87.95, 179.24), ("500002", "Net Profit"): (-138.56, 467.45),
                   ("500002", "Net Profit (owners)"): (-138.56, 467.45), ("500003", "Net Profit (owners)"): (0.0, 560.0)}
    assert {s: sink.get_dossier(s) for s in sink.list_dossiers()} == before
    assert "500001,Q2FY26,CONSOLIDATED,quarters,Net Profit (owners),87.95,179.24" in sc.to_csv(out)


def test_apply_rewrites_only_changed_dossiers_after_a_backup_and_restore_undoes_it(settings):
    sink = _sink(settings)
    before = {s: sink.get_dossier(s) for s in sink.list_dossiers()}
    out = sc.run(sink, sink.list_dossiers(), apply=True)
    assert out["error"] is None and out["written"] == 3 and out["backup"]["dossiers"] == 3
    assert sink.get_dossier("500001")["statements"][0]["rows"]["Net Profit (owners)"] == 179.24
    assert sink.get_dossier("500002")["statements"][0]["rows"]["Net Profit"] == 467.45
    assert sink.get_dossier("500003")["statements"][0]["rows"]["Net Profit (owners)"] == 560.0
    assert sink.get_dossier("500004") == before["500004"]   # nothing to change (a card-labelled entry and a balance sheet are left alone): no write
    again = sc.run(sink, sink.list_dossiers(), apply=True, restart=True)
    assert again["changed_dossiers"] == 0 and again["written"] == 0 and again["changes"] == [], "idempotent: nothing is corrected twice"
    restore.apply(sink, restore.plan(sink, out["backup"]["prefix"], everything=True))
    assert {s: sink.get_dossier(s) for s in sink.list_dossiers()} == before


def test_the_backup_is_taken_before_each_write(settings, monkeypatch):
    sink = _sink(settings)
    order = []
    real_put = sink.put_dossier
    monkeypatch.setattr(sink, "put_dossier", lambda s, d: (order.append(("put", s)), real_put(s, d))[1])
    from bse_intel import backup
    real_dossier = backup.RunBackup.dossier
    monkeypatch.setattr(backup.RunBackup, "dossier", lambda self, s, after=backup.NO_AFTER: (order.append(("backup", s)), real_dossier(self, s, after))[1])
    sc.run(sink, ["500001", "500002"], apply=True)
    assert order == [("backup", "500001"), ("put", "500001"), ("backup", "500002"), ("put", "500002")]


def test_chunks_are_saved_and_resumed_and_named_companies_leave_the_resume_point(settings, monkeypatch):
    sink = _sink(settings)
    monkeypatch.setattr(sc, "SAVE_EVERY", 1)
    out = sc.run(sink, sink.list_dossiers(), apply=True, limit=2)
    assert out["companies"] == 2 and out["more"] and sink.kv_get(sc.RESUME_KEY) == "500002"
    rest = sc.run(sink, sink.list_dossiers(), apply=True)
    assert rest["after"] == "500002" and rest["companies"] == 2 and not rest["more"] and sink.kv_get(sc.RESUME_KEY) == ""
    named = sc.run(sink, ["500001"], apply=True, restart=True, named=True)
    assert sink.kv_get(sc.RESUME_KEY) == "" and named["companies"] == 1


def test_a_failed_write_stops_the_run_and_keeps_what_was_done(settings, monkeypatch):
    sink = _sink(settings)
    real_put = sink.put_dossier

    def put(scrip, d):
        if scrip == "500002":
            raise RuntimeError("store down")
        return real_put(scrip, d)
    monkeypatch.setattr(sink, "put_dossier", put)
    out = sc.run(sink, sink.list_dossiers(), apply=True)
    assert "500002, writing" in out["error"] and out["written"] == 1 and sink.get_dossier("500001")["statements"][0]["rows"]["Net Profit (owners)"] == 179.24
    assert sink.get_dossier("500003")["statements"][0]["rows"]["Net Profit (owners)"] == 0.0   # not reached
