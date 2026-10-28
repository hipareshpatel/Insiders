"""The undo for data writes (28 Oct 2026): a backup of the stored rows a job changes (and what it wrote), saved and read back
before the write, and `restore` putting back only what nobody has changed since. Run on the local sink (SQLite + a
directory standing in for R2)."""

import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_card_refresh import FILED, _card, _dossier

from bse_intel import backup as bk
from bse_intel import bse_gap_fill as bf
from bse_intel import card_refresh, restore
from bse_intel.backup import BackupError, RunBackup
from bse_intel.cli import cmd_requeue_failed, cmd_restore
from bse_intel.sinks.local import LocalSink

LATER = "2026-09-11T18:00:00+05:30"
WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _row(news_id, scrip, filed_at, card):
    return {"news_id": news_id, "scrip_code": scrip, "symbol": "DEMO", "company_name": "Demo Rail Ltd", "filing_date": filed_at[:10],
            "filed_at": filed_at, "sector": None, "event_category": "ORDER", "impact_level": "MODERATE", "headline": card["headline"],
            "grounding_score": 1.0, "needs_review": 0, "memory_complete": 1, "card": card, "pdf_url": None, "model": "m",
            "created_at": filed_at, "held": 0}


def _call_card():
    return {**_card(), "event_type": "CONCALL_PRESENTATION", "call_takeaways": [
        {"category": "Guidance", "text": "Deposit growth guided at 11-12% for FY27", "verified": True, "versus_prior": "raised from 9-11%"}]}


def _store(settings, sink_class=LocalSink):
    """Three cards (two of 500001, one call card of 500002) and a memory for each company, as stored before a refresh."""
    sink = sink_class(settings)
    sink.execute("companies_upsert", [{"scrip_code": s, "symbol": "DEMO", "company_name": "Demo Rail Ltd", "updated_at": "x"}
                                      for s in ("500001", "500002")])
    sink.execute("cards_upsert", [_row("n1", "500001", FILED, _card()), _row("n2", "500001", LATER, _card()),
                                  _row("n3", "500002", LATER, _call_card())])
    for scrip in ("500001", "500002"):
        sink.put_dossier(scrip, {**_dossier(), "scrip_code": scrip})
    return sink


def _pipeline(sink):
    return SimpleNamespace(sink=sink, prompts=SimpleNamespace(sector_for=lambda industry: SimpleNamespace(footer=())),
                           _prices=None, _buckets=None)


def _cards(sink):
    return {r["news_id"]: r for r in sink.query("export_cards", ["", "", 100])}


def _parsed(sink):
    return {n: json.loads(r["card_json"]) for n, r in _cards(sink).items()}


def _backups(sink):
    return sorted({k.split("/")[1] for k in sink.list_objects("backup/")})


def _later_write(sink, scrip, change):
    """What the live pipeline does after a job: read the dossier, change it, write it back."""
    d = copy.deepcopy(sink.get_dossier(scrip))
    change(d)
    d["updated_at"] = "2026-10-29T10:00:00+05:30"
    sink.put_dossier(scrip, d)


def _later_card(sink, news_id, **changes):
    row = dict(_cards(sink)[news_id])
    card = json.loads(row.pop("card_json"))
    card.update(changes.pop("card", {}))
    row.update(changes)
    sink.execute("cards_upsert", [{**row, "card": card}])


class Spy(LocalSink):
    """Records which backup objects existed at the moment each write happened."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.seen: list[tuple[str, list[str]]] = []

    def execute(self, statement, rows):
        self.seen.append((statement, self.list_objects("backup/")))
        return super().execute(statement, rows)

    def put_dossier(self, scrip, dossier):
        self.seen.append((f"dossier {scrip}", self.list_objects("backup/")))
        return super().put_dossier(scrip, dossier)


class BadReadback(LocalSink):
    """A store that does not give back what was written to backup/ (the folder's marker aside)."""

    def get_object(self, key):
        body = super().get_object(key)
        return b"garbled" if key.startswith("backup/") and body and not key.endswith("meta.json") else body


def _refreshed(settings):
    sink = _store(settings)
    original = _parsed(sink)
    memory = {s: sink.get_dossier(s) for s in ("500001", "500002")}
    card_refresh.run(_pipeline(sink))
    (folder,) = _backups(sink)
    return sink, f"backup/{folder}/", original, memory


# --- the backup before the write ---------------------------------------------------------------------------------------

def test_refresh_saves_the_stored_rows_and_what_it_wrote_before_writing_them(settings):
    sink = _store(settings, Spy)
    before = _cards(sink)
    memory_before = sink.get_dossier("500002")
    report = card_refresh.run(_pipeline(sink))
    assert report["changed"] == 3 and report["memories_with_call_points"] == 1
    (folder,) = _backups(sink)
    assert folder.startswith("card-refresh-") and report["backup"]["prefix"] == f"backup/{folder}/"
    assert report["backup"]["cards"] == 3 and report["backup"]["dossiers"] == 1
    # at the moment of each write the backup of what it replaces was already there, with the after-state beside it
    seen = dict(sink.seen)
    for name in (f"backup/{folder}/cards/00001.json", f"backup/{folder}/after/cards/00001.json"):
        assert name in seen["cards_upsert"]
    for name in (f"backup/{folder}/memory/500002.json", f"backup/{folder}/after/memory/500002.json"):
        assert name in seen["dossier 500002"]
    saved = json.loads(sink.get_object(f"backup/{folder}/cards/00001.json"))["rows"]
    assert {r["news_id"]: r for r in saved} == before                        # the rows exactly as export_cards gave them
    assert json.loads(sink.get_object(f"backup/{folder}/memory/500002.json")) == memory_before
    after = {r["news_id"]: r for r in json.loads(sink.get_object(f"backup/{folder}/after/cards/00001.json"))["rows"]}
    assert {n: json.loads(r["card_json"]) for n, r in after.items()} == _parsed(sink)   # the rows as the job wrote them
    assert json.loads(sink.get_object(f"backup/{folder}/after/memory/500002.json")) == sink.get_dossier("500002")
    assert _cards(sink)["n1"]["card_json"] != before["n1"]["card_json"]       # and the run did change the stored card


def test_a_backup_that_does_not_read_back_stops_the_refresh_with_nothing_written(settings):
    sink = _store(settings, BadReadback)
    before, memory_before = _cards(sink), {s: sink.get_dossier(s) for s in ("500001", "500002")}
    with pytest.raises(BackupError):
        card_refresh.run(_pipeline(sink))
    assert _cards(sink) == before
    assert {s: sink.get_dossier(s) for s in ("500001", "500002")} == memory_before


def test_a_dry_run_saves_nothing(settings):
    sink = _store(settings)
    assert card_refresh.run(_pipeline(sink), dry_run=True)["backup"] is None
    assert sink.list_objects("backup/") == []


def test_a_run_that_changes_nothing_leaves_no_new_backup_folder(settings):
    sink = _store(settings)
    card_refresh.run(_pipeline(sink), {"500001"})
    (folder,) = _backups(sink)
    assert card_refresh.run(_pipeline(sink), {"500001"})["backup"] is None   # nothing to change the second time
    assert _backups(sink) == [folder]


# --- restore: what goes back, what stays -----------------------------------------------------------------------------

def test_a_restore_dry_run_changes_nothing_and_says_what_it_would_do(settings):
    sink, prefix, _, _ = _refreshed(settings)
    refreshed, memory = _cards(sink), sink.get_dossier("500002")
    report = restore.plan(sink, prefix, everything=True)
    text = restore.render(report)
    assert report["to_restore"] == {"memory": 1, "cards": 3} and report["has_after"]
    assert "card n1 (500001): will restore: " in text and "card_json (card blocks now different: " in text and "memory 500002: will restore: call_points (job added 1, removed 0, changed 0 entries)" in text
    assert _cards(sink) == refreshed and sink.get_dossier("500002") == memory
    assert _backups(sink) == [prefix.split("/")[1]]                              # a dry run saves nothing either
    restore.apply(sink, report)
    again = restore.render(restore.plan(sink, prefix, everything=True))
    assert again.count("already as before") == 4 and "will restore" not in again


def test_restore_apply_puts_the_old_card_and_memory_back_and_the_undo_can_be_undone(settings):
    sink, prefix, original, memory_before = _refreshed(settings)
    refreshed, memory_refreshed = _parsed(sink), sink.get_dossier("500002")
    assert refreshed != original and memory_refreshed != memory_before["500002"]

    done = restore.apply(sink, restore.plan(sink, prefix.rstrip("/"), everything=True))
    assert done["cards"] == 3 and done["memory"] == 1 and done["vanished"] == []
    assert _parsed(sink) == original
    assert sink.get_dossier("500002") == memory_before["500002"]
    undo = done["undo_backup"]
    assert undo.startswith("backup/restore-")
    # the undo holds what the restore replaced and what it wrote: restoring it brings the refreshed versions back
    restore.apply(sink, restore.plan(sink, undo, everything=True))
    assert _parsed(sink) == refreshed
    assert sink.get_dossier("500002") == memory_refreshed


def test_what_was_written_since_the_job_survives_a_restore(settings):
    sink, prefix, original, _ = _refreshed(settings)
    refreshed = _parsed(sink)
    # the live pipeline, hours later: a new figure and a second call point in 500002's memory (the job added the first call
    # point), an owner hold on n1 (a column the refresh did not touch), and a re-run of n2 that changed its headline
    _later_write(sink, "500002", lambda d: (d["financial_metrics"].append(
        {"metric": "pat", "period": "Q2FY27", "value": 5.0, "unit": "INR_CR", "as_of": "2026-10-29"}),
        d["call_points"].append({"news_id": "n9", "date": "2026-10-28", "category": "Risks", "text": "Later call point"})))
    _later_card(sink, "n1", held=1)
    _later_card(sink, "n2", headline="Demo Rail wins a bigger order", card={"headline": "Demo Rail wins a bigger order"})

    report = restore.plan(sink, prefix, everything=True)
    by_id = {c["news_id"]: c for c in report["cards"]}
    assert "card_json" in by_id["n1"]["restored"] and not by_id["n1"]["conflicts"]       # the hold is not the job's: left as it is
    assert by_id["n2"]["conflicts"] == ["card_json"] and not by_id["n2"]["changed"]   # the job never touched the headline column
    assert "conflict (changed since the job, left alone): " in restore.render(report)
    done = restore.apply(sink, report)
    assert done["cards"] == 2 and done["memory"] == 1                                    # n1 and n3; not n2
    now = _cards(sink)
    assert json.loads(now["n1"]["card_json"]) == original["n1"] and now["n1"]["held"] == 1
    assert json.loads(now["n2"]["card_json"])["headline"] == "Demo Rail wins a bigger order"
    assert json.loads(now["n3"]["card_json"]) == original["n3"]
    memory = sink.get_dossier("500002")
    assert [p["news_id"] for p in memory["call_points"]] == ["n9"]                       # the job's call point out, theirs kept
    assert any(m["period"] == "Q2FY27" for m in memory["financial_metrics"])
    assert memory["updated_at"] == "2026-10-29T10:00:00+05:30"

    forced = restore.apply(sink, restore.plan(sink, prefix, everything=True, force=True))
    assert forced["cards"] >= 1 and json.loads(_cards(sink)["n2"]["card_json"]) == original["n2"]   # --force puts n2 back too
    del refreshed


def test_a_dossier_the_job_created_is_deleted_only_if_nothing_changed_it_since(settings):
    sink = LocalSink(settings)
    sink.execute("companies_upsert", [{"scrip_code": "500009", "symbol": "NEW", "company_name": "New Ltd", "updated_at": "x"}])
    entry = {"metric": "revenue", "period": "Q1FY27", "value": 10.0, "unit": "INR_CR", "basis": "STANDALONE",
             "as_of": "2026-10-01", "source_news_id": "x"}
    backup = RunBackup(sink, "bse-gap-fill")
    assert bf._write(sink, "500009", [entry], {**_dossier(), "scrip_code": "500009"}, backup) == 1
    assert json.loads(sink.get_object(f"{backup.prefix}memory/500009.json")) is None      # it had none before the write
    written = sink.get_dossier("500009")
    assert json.loads(sink.get_object(f"{backup.prefix}after/memory/500009.json")) == written

    untouched = restore.plan(sink, backup.prefix, scrips={"500009"})
    assert untouched["memory"][0]["changed"] and untouched["memory"][0]["restored"] == ["(dossier created by the job)"]
    # a later writer put a deal in: only the job's own entries come out, the deal stays
    _later_write(sink, "500009", lambda d: d.__setitem__("deals", [{"id": "d1"}]))
    restore.apply(sink, restore.plan(sink, backup.prefix, scrips={"500009"}))
    left = sink.get_dossier("500009")
    assert left["deals"] == [{"id": "d1"}] and not left.get("financial_metrics") and "company_name" not in left
    # and a dossier nobody touched is deleted
    sink2 = LocalSink(settings.__class__(**{**settings.__dict__, "local_dir": settings.local_dir.parent / "two"}))
    b2 = RunBackup(sink2, "bse-gap-fill")
    bf._write(sink2, "500009", [entry], {**_dossier(), "scrip_code": "500009"}, b2)
    restore.apply(sink2, restore.plan(sink2, b2.prefix, scrips={"500009"}))
    assert sink2.get_dossier("500009") is None


def test_a_backup_with_no_after_state_restores_only_with_force(settings):
    sink = _store(settings)
    before = sink.get_dossier("500002")
    backup = RunBackup(sink, "old-job")
    backup.dossier("500002")                                                      # a backup as the first version made it: no after
    _later_write(sink, "500002", lambda d: d.__setitem__("deals", [{"id": "d1"}]))
    changed = sink.get_dossier("500002")

    report = restore.plan(sink, backup.prefix, scrips={"500002"})
    assert not report["has_after"] and report["memory"][0]["needs_force"]
    assert "no after-state in this backup" in restore.render(report) and "--force needed" in restore.render(report)
    assert restore.apply(sink, report)["memory"] == 0 and sink.get_dossier("500002") == changed
    forced = restore.apply(sink, restore.plan(sink, backup.prefix, scrips={"500002"}, force=True))
    assert forced["memory"] == 1 and sink.get_dossier("500002")["deals"] == before["deals"]


def test_the_filters_restrict_what_goes_back(settings):
    sink, prefix, original, _ = _refreshed(settings)
    refreshed, memory_refreshed = _parsed(sink), sink.get_dossier("500002")

    done = restore.apply(sink, restore.plan(sink, prefix, news_ids={"n1"}))           # one card named: that card, no memory
    now = _parsed(sink)
    assert done["cards"] == 1 and done["memory"] == 0
    assert now["n1"] == original["n1"] and now["n2"] == refreshed["n2"] and now["n3"] == refreshed["n3"]

    done = restore.apply(sink, restore.plan(sink, prefix, scrips={"500001"}))         # one company: its cards, nothing of the other
    now = _parsed(sink)
    assert done["cards"] == 1 and done["memory"] == 0                                 # n1 was back already; n2 goes
    assert now["n2"] == original["n2"] and now["n3"] == refreshed["n3"]
    assert sink.get_dossier("500002") == memory_refreshed

    done = restore.apply(sink, restore.plan(sink, prefix, scrips={"500002"}))
    assert done["cards"] == 1 and done["memory"] == 1
    assert sink.get_dossier("500002") != memory_refreshed


def test_no_filter_needs_all_and_a_name_not_in_the_backup_fails_loudly(settings, capsys):
    sink, prefix, _, _ = _refreshed(settings)
    refreshed = _cards(sink)
    with pytest.raises(ValueError):
        restore.plan(sink, prefix)
    with pytest.raises(ValueError):
        restore.plan(sink, "memory/", everything=True)
    args = SimpleNamespace(list=False, seal=False, backup=prefix, scrips=None, news_ids=None, all=False, apply=True, force=False)
    assert cmd_restore(args, None, sink) == 2
    # a typo among good names: named in the output, non-zero, and nothing written (not even for the good names)
    args = SimpleNamespace(list=False, seal=False, backup=prefix, scrips="500001,999999", news_ids="n1,nope", all=False,
                           apply=True, force=False)
    assert cmd_restore(args, None, sink) == 2
    out = capsys.readouterr()
    assert "NOT IN THE BACKUP: 999999" in out.out and "nope" in out.err and "999999" in out.err
    assert _cards(sink) == refreshed and _backups(sink) == [prefix.split("/")[1]]
    assert restore.plan(sink, prefix, scrips={"999999"})["unknown"] == ["999999"]


def test_a_card_that_vanished_between_the_plan_and_the_apply_is_reported_and_not_counted(settings):
    sink, prefix, original, _ = _refreshed(settings)
    report = restore.plan(sink, prefix, everything=True)
    sink.execute("cards_delete", [{"news_id": "n1"}])
    done = restore.apply(sink, report)
    assert done["vanished"] == ["n1"] and done["cards"] == 2
    assert "n1" not in _cards(sink)


def test_only_the_columns_cards_upsert_can_write_are_compared():
    row = {"news_id": "n", "scrip_code": "1", "filing_date": "d", "filed_at": "t", "headline": "old", "card_json": "{}",
           "post_event_return_json": None, "held": 0}
    changed = {**row, "headline": "new", "post_event_return_json": "{\"r\": 1}", "filing_date": "other"}
    d = restore.decide_card(row, row, changed, force=False)
    assert d["restored"] == [] and d["not_restorable"] == ["filing_date"]            # a column the job did not change is not touched
    after = {**row, "headline": "new", "post_event_return_json": "{\"r\": 1}"}
    d = restore.decide_card(row, after, after, force=False)
    assert d["restored"] == ["headline"] and d["not_restorable"] == ["post_event_return_json"]   # an upsert cannot set it back to NULL
    assert d["new"]["headline"] == "old" and d["new"]["post_event_return_json"] == "{\"r\": 1}"
    assert restore.decide_card(row, None, {**row, "headline": "x"}, force=False)["needs_force"]
    assert restore.decide_card(row, None, {**row, "headline": "x"}, force=True)["restored"] == ["headline"]


def test_the_three_way_merge_goes_down_to_entries_and_fields():
    m = restore.Merge(False)
    before = {"timeline": [{"id": "a", "text": "old"}, {"id": "b", "text": "b"}], "x": 1, "updated_at": "1"}
    after = {"timeline": [{"id": "a", "text": "job"}, {"id": "b", "text": "b"}], "x": 2, "updated_at": "2"}
    current = {"timeline": [{"id": "a", "text": "job"}, {"id": "b", "text": "later"}, {"id": "c", "text": "c"}], "x": 2, "updated_at": "3"}
    d = restore.decide_dossier(before, after, current, True, False)
    assert d["new"]["x"] == 1 and d["new"]["updated_at"] == "3"
    assert d["new"]["timeline"] == [{"id": "a", "text": "old"}, {"id": "b", "text": "later"}, {"id": "c", "text": "c"}]
    assert d["conflicts"] == [] and set(d["restored"]) == {"x", "timeline[a]"}
    # the same field changed by both: a conflict, theirs stays
    current["timeline"][0]["text"] = "theirs"
    d = restore.decide_dossier(before, after, current, True, False)
    assert d["conflicts"] == ["timeline[a].text"] and d["new"]["timeline"][0]["text"] == "theirs"
    assert restore.decide_dossier(before, after, current, True, True)["new"]["timeline"][0]["text"] == "old"
    del m


# --- snapshots for runs that cannot back up row by row -----------------------------------------------------------------

def test_a_snapshot_taken_before_a_rerun_is_sealed_after_it_and_then_restores_three_way(settings):
    sink = _store(settings)
    original = _parsed(sink)
    snapshot = bk.start_scope(sink, "requeue", news_ids=["n1", "nope"])
    assert snapshot.summary()["cards"] == 1 and snapshot.summary()["dossiers"] == 1 and snapshot.missing_ids == ["nope"]
    sink.get_object(f"{snapshot.prefix}memory/500001.json")
    # the live run re-reads n1: new card, new memory; and unrelated writes follow
    _later_card(sink, "n1", headline="Re-read headline", card={"headline": "Re-read headline"})
    _later_write(sink, "500001", lambda d: d.__setitem__("deals", [{"id": "d1"}]))
    plain = restore.plan(sink, snapshot.prefix, everything=True)
    assert not plain["has_after"] and plain["cards"][0]["needs_force"]
    sealed = bk.save_after(sink, snapshot.prefix)
    assert sealed["cards"] == 1 and sealed["dossiers"] == 1
    with pytest.raises(BackupError):
        bk.save_after(sink, snapshot.prefix)                                             # an after-state is never replaced
    _later_write(sink, "500001", lambda d: d.__setitem__("operating_notes", [{"id": "o1"}]))   # after the seal
    restore.apply(sink, restore.plan(sink, snapshot.prefix, everything=True))
    assert json.loads(_cards(sink)["n1"]["card_json"]) == original["n1"]
    memory = sink.get_dossier("500001")
    assert memory["operating_notes"] == [{"id": "o1"}] and memory["deals"] == []        # the seal saw d1: it is the "job's"


def test_a_named_seed_backs_up_the_companies_first_and_seals_the_backup_at_its_end(settings, monkeypatch, capsys):
    from bse_intel import seed, universe
    from bse_intel.cli import cmd_seed_memory

    sink = _store(settings)
    sink.put_object(universe.UNIVERSE_KEY, json.dumps({"source": "nse", "included": ["500001"], "symbols": {"DEMO": "500001"},
                                                       "isins": {}}).encode())
    before = sink.get_dossier("500001")

    def seeded(sink_, bse, scrip, name, since, cache, stats, company, nse=None, symbol=""):
        _later_write(sink_, scrip, lambda d: d["financial_metrics"].append(
            {"metric": "revenue", "period": "Q1FY27", "value": 1.0, "unit": "INR_CR", "as_of": "2026-10-28"}))
    monkeypatch.setattr(seed, "seed_results", seeded)
    args = SimpleNamespace(universe=False, scrips="DEMO", restart=False, shard=None, source="nse", since="2026-01-01",
                           shareholding_only=False, results_only=True)
    assert cmd_seed_memory(args, settings, sink) == 0
    (folder,) = _backups(sink)
    assert folder.startswith("seed-memory-") and f"backup/{folder}/" in capsys.readouterr().out
    assert json.loads(sink.get_object(f"backup/{folder}/memory/500001.json")) == before
    assert json.loads(sink.get_object(f"backup/{folder}/after/memory/500001.json")) == sink.get_dossier("500001")
    restore.apply(sink, restore.plan(sink, f"backup/{folder}/", scrips={"500001"}))
    assert sink.get_dossier("500001")["financial_metrics"] == before["financial_metrics"]
    # a whole-universe run says that it takes no backup
    args = SimpleNamespace(universe=True, scrips=None, restart=False, shard=None, source="nse", since="2026-01-01",
                           shareholding_only=False, results_only=True)
    monkeypatch.setattr(seed, "seed_results", lambda *a, **k: None)
    cmd_seed_memory(args, settings, sink)
    folders = _backups(sink)
    cmd_seed_memory(args, settings, sink)
    assert "no backup taken" in capsys.readouterr().out and _backups(sink) == folders   # and leaves no new folder


def test_requeue_by_id_takes_a_backup_first_and_requeues_nothing_when_it_does_not_read_back(settings, capsys):
    sink = _store(settings, Spy)
    args = SimpleNamespace(ids="n1,n3", dry_run=False, needs_review=False, since=None, days=30, attempts=None)
    assert cmd_requeue_failed(args, SimpleNamespace(max_attempts=3), sink) == 0
    (folder,) = _backups(sink)
    assert folder.startswith("requeue-") and "restore --seal --backup backup/" in capsys.readouterr().out
    assert sink.seen[-1][0] == "filings_update" and f"backup/{folder}/cards/00001.json" in sink.seen[-1][1]
    bad = _store(settings.__class__(**{**settings.__dict__, "local_dir": settings.local_dir.parent / "bad"}), BadReadback)
    bad.seen = []
    bad.execute = lambda statement, rows: bad.seen.append(statement)
    assert cmd_requeue_failed(args, SimpleNamespace(max_attempts=3), bad) == 1
    assert "filings_update" not in bad.seen
    capsys.readouterr()
    cmd_requeue_failed(SimpleNamespace(ids=None, dry_run=False, needs_review=False, since="2026-10-01", days=30, attempts=None),
                       SimpleNamespace(max_attempts=3), sink)
    assert "no backup taken" in capsys.readouterr().out


# --- bookkeeping --------------------------------------------------------------------------------------------------------

def test_a_bulk_job_saves_each_dossiers_first_state_and_its_last_write(settings):
    sink = LocalSink(settings)
    backup = RunBackup(sink, "label-memory")
    sink.put_dossier("1", {"scrip_code": "1", "v": 1})
    backup.dossier("1", {"scrip_code": "1", "v": 2})
    sink.put_dossier("1", {"scrip_code": "1", "v": 2})
    backup.dossier("1", {"scrip_code": "1", "v": 3})                              # a second write: before kept, after replaced
    assert json.loads(sink.get_object(f"{backup.prefix}memory/1.json")) == {"scrip_code": "1", "v": 1}
    assert json.loads(sink.get_object(f"{backup.prefix}after/memory/1.json")) == {"scrip_code": "1", "v": 3}
    assert backup.summary()["dossiers"] == 1


def test_list_shows_each_backup_folder_and_single_file_backups(settings):
    sink = _store(settings)
    card_refresh.run(_pipeline(sink))
    sink.put_object("backup/prune-companies-2026-10-26.json", b"{}")
    listed = {e["backup"]: e for e in restore.list_backups(sink)}
    (folder,) = [k for k in listed if "card-refresh" in k]
    assert listed[folder]["dossiers"] == 1 and listed[folder]["card_parts"] == 1 and listed[folder]["after_state"]
    assert listed["backup/prune-companies-2026-10-26.json"]["restorable"] is False


def test_the_maintenance_restore_step_writes_only_on_an_explicit_mode():
    text = (WORKFLOWS / "maintenance.yml").read_text(encoding="utf-8")
    inputs = re.search(r"      restore_mode:\n(?:        .*\n)+", text).group(0)
    assert "default: preview" in inputs and "options: [preview, apply, apply-force, seal]" in inputs
    step = next(s for s in re.split(r"\n\s+- (?=name:|uses:)", text) if s.startswith("name: Restore from a backup"))
    assert "MODE: ${{ inputs.restore_mode }}" in step and "inputs.dry_run" not in step
    assert 'apply) args+=(--apply) ;;' in step and '"${IDS,,}" = all' in step      # case-insensitive `all`
    assert step.count("--apply") == 2                                                # only the two explicit modes
