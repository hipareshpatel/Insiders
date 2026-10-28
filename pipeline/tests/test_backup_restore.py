"""The undo for data writes (28 Oct 2026): a backup of the stored rows a job changes, saved and read back before the write,
and `restore` putting it back. Run on the local sink (SQLite + a directory standing in for R2)."""

import json
from types import SimpleNamespace

import pytest
from test_card_refresh import FILED, _card, _dossier

from bse_intel import bse_gap_fill as bf
from bse_intel import card_refresh, restore
from bse_intel.backup import BackupError, RunBackup
from bse_intel.cli import cmd_restore
from bse_intel.sinks.local import LocalSink

LATER = "2026-09-11T18:00:00+05:30"


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


def _backups(sink):
    return sorted({k.split("/")[1] for k in sink.list_objects("backup/")})


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


def test_refresh_saves_the_stored_rows_and_memories_before_writing_them(settings):
    sink = _store(settings, Spy)
    before = _cards(sink)
    memory_before = sink.get_dossier("500002")
    report = card_refresh.run(_pipeline(sink))
    assert report["changed"] == 3 and report["memories_with_call_points"] == 1
    (folder,) = _backups(sink)
    assert folder.startswith("card-refresh-") and report["backup"]["prefix"] == f"backup/{folder}/"
    assert report["backup"]["cards"] == 3 and report["backup"]["dossiers"] == 1
    # at the moment of each write the backup of what it replaces was already there
    seen = dict(sink.seen)
    assert f"backup/{folder}/cards/00001.json" in seen["cards_upsert"]
    assert f"backup/{folder}/memory/500002.json" in seen["dossier 500002"]
    saved = json.loads(sink.get_object(f"backup/{folder}/cards/00001.json"))["rows"]
    assert {r["news_id"]: r for r in saved} == before                        # the rows exactly as export_cards gave them
    assert json.loads(sink.get_object(f"backup/{folder}/memory/500002.json")) == memory_before
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


def test_a_restore_dry_run_changes_nothing(settings):
    sink = _store(settings)
    card_refresh.run(_pipeline(sink))
    (folder,) = _backups(sink)
    refreshed, memory = _cards(sink), sink.get_dossier("500002")
    report = restore.plan(sink, f"backup/{folder}/", everything=True)
    text = restore.render(report)
    assert report["to_restore"] == {"memory": 1, "cards": 3}
    assert "card n1 (500001): " in text and "card.signals" in text and "memory 500002: " in text and "call_points" in text
    assert _cards(sink) == refreshed and sink.get_dossier("500002") == memory
    assert _backups(sink) == [folder]                                             # a dry run saves nothing either


def test_restore_apply_puts_the_old_card_and_memory_back_and_keeps_a_backup_of_what_it_replaced(settings):
    sink = _store(settings)
    original = {n: json.loads(r["card_json"]) for n, r in _cards(sink).items()}
    memory_before = sink.get_dossier("500002")
    card_refresh.run(_pipeline(sink))
    (folder,) = _backups(sink)
    refreshed = {n: json.loads(r["card_json"]) for n, r in _cards(sink).items()}
    memory_refreshed = sink.get_dossier("500002")
    assert refreshed != original and memory_refreshed != memory_before

    done = restore.apply(sink, restore.plan(sink, f"backup/{folder}", everything=True))
    assert done["cards"] == 3 and done["memory"] == 1
    assert {n: json.loads(r["card_json"]) for n, r in _cards(sink).items()} == original
    assert sink.get_dossier("500002") == memory_before
    undo = done["undo_backup"]
    assert undo.startswith("backup/restore-")
    # the undo holds what the restore replaced: restoring it brings the refreshed versions back
    restore.apply(sink, restore.plan(sink, undo, everything=True))
    assert {n: json.loads(r["card_json"]) for n, r in _cards(sink).items()} == refreshed
    assert sink.get_dossier("500002") == memory_refreshed


def test_a_restore_whose_backup_does_not_read_back_writes_nothing(settings):
    sink = _store(settings)
    card_refresh.run(_pipeline(sink))
    (folder,) = _backups(sink)
    report = restore.plan(sink, f"backup/{folder}/", everything=True)
    refreshed = _cards(sink)

    class Bad(BadReadback):
        pass

    bad = Bad(settings)
    with pytest.raises(BackupError):
        restore.apply(bad, report)
    assert _cards(sink) == refreshed


def test_the_filters_restrict_what_goes_back(settings):
    sink = _store(settings)
    original = {n: json.loads(r["card_json"]) for n, r in _cards(sink).items()}
    card_refresh.run(_pipeline(sink))
    (folder,) = _backups(sink)
    refreshed = {n: json.loads(r["card_json"]) for n, r in _cards(sink).items()}
    memory_refreshed = sink.get_dossier("500002")
    prefix = f"backup/{folder}/"

    # one card named: that card only, no memory
    done = restore.apply(sink, restore.plan(sink, prefix, news_ids={"n1"}))
    now = {n: json.loads(r["card_json"]) for n, r in _cards(sink).items()}
    assert done["cards"] == 1 and done["memory"] == 0
    assert now["n1"] == original["n1"] and now["n2"] == refreshed["n2"] and now["n3"] == refreshed["n3"]

    # one company named: its cards and its memory, and nothing of the other company
    done = restore.apply(sink, restore.plan(sink, prefix, scrips={"500001"}))
    now = {n: json.loads(r["card_json"]) for n, r in _cards(sink).items()}
    assert done["cards"] == 1 and done["memory"] == 0                           # n1 was back already; n2 goes; 500001's memory was never changed
    assert now["n2"] == original["n2"] and now["n3"] == refreshed["n3"]
    assert sink.get_dossier("500002") == memory_refreshed

    done = restore.apply(sink, restore.plan(sink, prefix, scrips={"500002"}))
    assert done["cards"] == 1 and done["memory"] == 1
    assert sink.get_dossier("500002") != memory_refreshed


def test_no_filter_needs_all_and_the_prefix_must_be_a_backup(settings):
    sink = _store(settings)
    card_refresh.run(_pipeline(sink))
    (folder,) = _backups(sink)
    with pytest.raises(ValueError):
        restore.plan(sink, f"backup/{folder}/")
    with pytest.raises(ValueError):
        restore.plan(sink, "memory/", everything=True)
    args = SimpleNamespace(list=False, backup=f"backup/{folder}/", scrips=None, news_ids=None, all=False, apply=True)
    assert cmd_restore(args, None, sink) == 2
    assert _backups(sink) == [folder]                                             # refused: no restore backup, nothing written


def test_a_dossier_the_job_created_is_deleted_again_by_the_restore(settings):
    sink = LocalSink(settings)
    sink.execute("companies_upsert", [{"scrip_code": "500009", "symbol": "NEW", "company_name": "New Ltd", "updated_at": "x"}])
    backup = RunBackup(sink, "bse-gap-fill")
    entry = {"metric": "revenue", "period": "Q1FY27", "value": 10.0, "unit": "INR_CR", "basis": "STANDALONE",
             "as_of": "2026-10-01", "source_news_id": "x"}
    assert bf._write(sink, "500009", [entry], {**_dossier(), "scrip_code": "500009"}, backup) == 1
    assert sink.get_dossier("500009") is not None
    assert json.loads(sink.get_object(f"{backup.prefix}memory/500009.json")) is None   # it had none before the write
    restore.apply(sink, restore.plan(sink, backup.prefix, scrips={"500009"}))
    assert sink.get_dossier("500009") is None


def test_a_bulk_job_saves_each_dossier_once_before_its_first_write(settings):
    sink = LocalSink(settings)
    backup = RunBackup(sink, "label-memory")
    sink.put_dossier("1", {"scrip_code": "1", "v": 1})
    backup.dossier("1")
    sink.put_dossier("1", {"scrip_code": "1", "v": 2})
    backup.dossier("1")                                                          # the second call keeps the first state
    assert json.loads(sink.get_object(f"{backup.prefix}memory/1.json")) == {"scrip_code": "1", "v": 1}
    assert backup.summary()["dossiers"] == 1


def test_list_shows_each_backup_folder_and_single_file_backups(settings):
    sink = _store(settings)
    card_refresh.run(_pipeline(sink))
    sink.put_object("backup/prune-companies-2026-10-26.json", b"{}")
    listed = {e["backup"]: e for e in restore.list_backups(sink)}
    (folder,) = [k for k in listed if "card-refresh" in k]
    assert listed[folder]["dossiers"] == 1 and listed[folder]["card_parts"] == 1 and listed[folder]["restorable"]
    assert listed["backup/prune-companies-2026-10-26.json"]["restorable"] is False
