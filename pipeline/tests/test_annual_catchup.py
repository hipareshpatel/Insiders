"""The annual-report catch-up (annual_catchup.py): a report read the day it was filed, before NSE listed its XBRL,
is read again once the year's file appears, and only then."""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from bse_intel import annual_catchup, cli
from bse_intel.nse import SourceBlockedError, parse_annual_report_rows
from bse_intel.timeutil import IST, today_ist

from test_annual_xbrl import ANNUAL_CARD, ANNUAL_TEXT, CONSOLIDATED, LISTING, STANDALONE
from test_pipeline import _filing, _pdf, build, rows

NEMOTRON = "nvidia/nemotron-3-super-120b-a12b"
FILES = {"AR_XBRL_KANORICHEM_22122025122259.xml": CONSOLIDATED, "AR_XBRL_KANORICHEM_22122025122227.xml": STANDALONE}


class FakeNse:
    """NSE's annual-report XBRL list by symbol (LISTING's rows: Kanoria's FY25 files, broadcast 22 Dec 2025)."""

    def __init__(self, listed: dict[str, list[dict]], refuse: set[str] = frozenset()):
        self.listed, self.refuse, self.lists, self.downloads = listed, refuse, [], []

    def annual_reports(self, symbol):
        self.lists.append(symbol)
        if symbol in self.refuse:
            raise SourceBlockedError("NSE refused the request (HTTP 403)")
        return parse_annual_report_rows(self.listed.get(symbol, []))

    def download(self, url, max_bytes=None):
        self.downloads.append(url)
        return FILES.get(url.rsplit("/", 1)[-1])


def _report(news_id, headline, when, scrip, symbol):
    filed = datetime(*when, 15, 46, 49, tzinfo=IST)
    f = _filing(news_id, headline, filed, "AGM/EGM", "Reg. 34 (1) Annual Report", scrip=scrip, name=f"{symbol} Ltd")
    return f.model_copy(update={"symbol": symbol})


REPORTS = [_report("n-fy25", "Annual Report for the Financial year 2024-25", (2025, 9, 2), "999001", "DEMOCEM"),
           _report("n-fy26", "Annual Report for the financial year 2025-26", (2026, 8, 6), "999002", "OTHERCO")]


def _read_the_day_they_were_filed(settings, reports=REPORTS):
    """The daily path: each report read when it was filed, when NSE listed no file for its year yet."""
    pipeline, sink, _ = build(settings, reports, {f.pdf_url: _pdf(ANNUAL_TEXT) for f in reports},
                              {NEMOTRON: [json.dumps(ANNUAL_CARD)]}, env={"NVIDIA_API_KEY": "n"})
    pipeline.nse = FakeNse({})
    for day in sorted({f.filing_date for f in reports}):
        pipeline.discover(date.fromisoformat(day))
    pipeline.process("2000-01-01", "2100-01-01", time.monotonic() + 60, bulk=False)
    cards = {r["news_id"]: json.loads(r["card_json"]) for r in rows(sink, "select news_id, card_json from cards")}
    assert set(cards) == {f.news_id for f in reports}
    # the list was read in full (it had nothing for the year): the card says when
    assert all("annual_xbrl" not in c and c["annual_xbrl_checked"] for c in cards.values())
    for f in reports:   # ... which on the daily path was the day after the filing
        sink._db.execute("update cards set card_json = json_set(card_json, '$.annual_xbrl_checked', ?) where news_id = ?",
                         [f"{f.filing_date}T18:00:00+05:30", f.news_id])
    sink._db.commit()
    sink.close()


def _catch_up(settings, nse, script=None, env=None, reports=REPORTS, **kwargs):
    pipeline, sink, fake = build(settings, reports, {f.pdf_url: _pdf(ANNUAL_TEXT) for f in reports},
                                 script or {NEMOTRON: [json.dumps(ANNUAL_CARD)]}, env=env or {"NVIDIA_API_KEY": "n"})
    pipeline.nse = nse
    kwargs.setdefault("horizon_days", 3650)   # the files are Kanoria's FY25, for a report filed in September 2025
    report = annual_catchup.catch_up(pipeline, time.monotonic() + 60, **kwargs)
    return report, sink, fake


def _cards(sink):
    return {r["news_id"]: {**json.loads(r["card_json"]), "held": r["held"], "created_at": r["created_at"]}
            for r in rows(sink, "select news_id, card_json, held, created_at from cards")}


def test_a_report_is_read_again_once_nse_lists_its_year_and_the_other_is_left(settings):
    _read_the_day_they_were_filed(settings)
    # Kanoria's FY25 files are listed now for both companies: a new file for the FY25 report, none for FY26's year
    nse = FakeNse({"DEMOCEM": LISTING["data"], "OTHERCO": LISTING["data"]})
    report, sink, _ = _catch_up(settings, nse)

    assert report["rerun"] == {"n-fy25": "published with the table"}
    assert report["cards"] == 2 and report["lists_read"] == 2 and nse.lists == ["DEMOCEM", "OTHERCO"]
    cards = _cards(sink)
    assert cards["n-fy25"]["annual_xbrl"]["period"] == "FY25" and cards["n-fy25"]["held"] == 0
    assert "annual_xbrl" not in cards["n-fy26"] and cards["n-fy26"]["annual_xbrl_checked"] == "2026-08-06T18:00:00+05:30"
    statuses = {r["news_id"]: (r["status"], r["attempts"]) for r in rows(sink, "select news_id, status, attempts from filings")}
    assert statuses == {"n-fy25": ("ANALYZED", 0), "n-fy26": ("ANALYZED", 0)}
    # the re-run read the list already fetched, and downloaded the year's two files
    assert len(nse.downloads) == 2
    week = (today_ist() + timedelta(days=7)).isoformat()
    assert json.loads(sink.kv_get(annual_catchup.NEXT_LOOK_KEY)) == {"DEMOCEM": week, "OTHERCO": week}
    sink.close()

    # the next day: no list is read again within the week, and nothing is re-run
    nse = FakeNse({"DEMOCEM": LISTING["data"], "OTHERCO": LISTING["data"]})
    again, sink, _ = _catch_up(settings, nse)
    assert again["cards"] == 1 and again["companies_due"] == 0 and nse.lists == [] and again["rerun"] == {}


def test_the_paid_provider_is_left_out_even_with_its_key_loaded(settings):
    """The step runs every day, so it stays at $0 (D24). Two re-runs: the backfill route's rotation would hand
    the second to DeepSeek."""
    reports = [REPORTS[0], _report("n-third", "Annual Report for the Financial year 2024-25", (2025, 9, 3), "999003", "THIRDCO")]
    _read_the_day_they_were_filed(settings, reports)
    script = {NEMOTRON: [json.dumps(ANNUAL_CARD)], "deepseek-flash": [json.dumps(ANNUAL_CARD)]}
    report, _, fake = _catch_up(settings, FakeNse({"DEMOCEM": LISTING["data"], "THIRDCO": LISTING["data"]}), script,
                                env={"NVIDIA_API_KEY": "n", "DEEPSEEK_API_KEY": "d"}, reports=reports)
    assert report["paid_left_out"] == ["deepseek"] and len(report["rerun"]) == 2
    assert [c["model"] for c in fake.calls] == [NEMOTRON, NEMOTRON]


def test_a_file_counts_as_new_only_when_broadcast_after_the_card_last_read_the_list():
    listing = parse_annual_report_rows(LISTING["data"])   # broadcast 22 Dec 2025
    card = {"headline": "Annual Report for the Financial year 2024-25", "subject": "", "filed_at": "2025-09-02T15:46:49+05:30"}
    assert len(annual_catchup.new_files({**card, "checked": "2025-09-02T18:00:00+05:30"}, listing)) == 2
    # read again after the file was out, and refused (its figures not in the PDF): not tried a third time
    assert annual_catchup.new_files({**card, "checked": "2025-12-23T09:00:00+05:30"}, listing) == []
    # never read in full (NSE off or refused then, or a card from before the stamp): any file of the year
    assert len(annual_catchup.new_files({**card, "checked": None}, listing)) == 2
    assert annual_catchup.new_files({**card, "headline": "Annual Report for the financial year 2025-26"}, listing) == []


def test_nse_refusing_queues_nothing_and_the_companies_stay_due(settings):
    _read_the_day_they_were_filed(settings)
    nse = FakeNse({"DEMOCEM": LISTING["data"]}, refuse={"OTHERCO"})
    report, sink, fake = _catch_up(settings, nse)
    assert report["stopped"].startswith("NSE refused") and report["rerun"] == {} and fake.calls == []
    assert {r["status"] for r in rows(sink, "select status from filings")} == {"ANALYZED"}
    assert json.loads(sink.kv_get(annual_catchup.NEXT_LOOK_KEY)) == {}   # DEMOCEM's file is still to be read


def test_a_rerun_that_ends_without_a_card_takes_the_old_one_out(settings):
    _read_the_day_they_were_filed(settings, REPORTS[:1])
    not_material = {"is_material": False, "event_type": "ANNUAL_REPORT", "reason": "routine annual report"}
    report, sink, _ = _catch_up(settings, FakeNse({"DEMOCEM": LISTING["data"]}), {NEMOTRON: [json.dumps(not_material)]})
    assert report["rerun"]["n-fy25"].startswith("no card now (not_material")
    assert _cards(sink) == {}


def test_a_report_older_than_the_horizon_is_not_looked_at(settings):
    _read_the_day_they_were_filed(settings)
    nse = FakeNse({"DEMOCEM": LISTING["data"], "OTHERCO": LISTING["data"]})
    report, _, _ = _catch_up(settings, nse, horizon_days=(today_ist() - date(2026, 8, 6)).days)
    assert report["cards"] == 1 and nse.lists == ["OTHERCO"] and report["rerun"] == {}


def test_only_the_named_companies_are_looked_at(settings):
    _read_the_day_they_were_filed(settings)
    nse = FakeNse({"DEMOCEM": LISTING["data"], "OTHERCO": LISTING["data"]})
    report, sink, _ = _catch_up(settings, nse, scrips={"999002"})   # DEMOCEM's cards are under review: left alone
    assert report["cards"] == 1 and nse.lists == ["OTHERCO"] and report["rerun"] == {}
    assert {r["status"] for r in rows(sink, "select status from filings")} == {"ANALYZED"}


def test_the_rerun_limit_leaves_the_rest_due(settings):
    _read_the_day_they_were_filed(settings)
    nse = FakeNse({"DEMOCEM": LISTING["data"], "OTHERCO": LISTING["data"]})
    report, sink, _ = _catch_up(settings, nse, max_reruns=0)
    assert report["rerun"] == {} and nse.lists == []
    assert sink.kv_get(annual_catchup.NEXT_LOOK_KEY) == "{}"


def test_another_run_on_the_machine_keeps_the_step_waiting(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    now = time.time()
    for name, age in (("process-20261018-0948.log", 120), ("seed-memory-20261018-0700.log", 3 * 3600),
                      ("annual-xbrl-catchup-20261018-1900.log", 0), ("webdev.log", 0)):   # the dev server's own
        (logs / name).write_text("x")
        os.utime(logs / name, (now - age, now - age))
    processes = lambda: [(os.getpid(), "python -m bse_intel annual-xbrl-catchup"),  # noqa: E731
                         (4242, r"C:\Python312\python.exe -m bse_intel seed-memory --scrips 541153"),
                         (4343, "python -m pytest -q"), (4444, "python scripts/rerun.py --dry-run")]
    busy = annual_catchup.other_runs(logs, processes, now)
    assert [b.split(":")[0] for b in busy] == ["process 4242", "process 4444", "log process-20261018-0948.log written 2 min ago"]
    assert annual_catchup.other_runs(logs, lambda: [], now + 3600) == []

    answers, slept = [["process 4242: seed-memory"], []], []
    assert annual_catchup.wait_for_quiet(logs, 600, sleep=slept.append, check=lambda d: answers.pop(0)) == []
    assert slept == [60]


def test_the_command_skips_while_another_run_is_going(settings, monkeypatch, capsys):
    monkeypatch.setattr(annual_catchup, "other_runs", lambda log_dir: ["process 4242: python -m bse_intel run"])
    args = SimpleNamespace(wait=0, time_budget=60, days=365, every=7, max_companies=150, max_reruns=10, scrips=None)
    assert cli.cmd_annual_xbrl_catchup(args, settings, None) == 3
    assert json.loads(capsys.readouterr().out)["busy"] == ["process 4242: python -m bse_intel run"]


@pytest.fixture(autouse=True)
def _no_real_processes(monkeypatch):
    """No test lists the machine's processes."""
    monkeypatch.setattr(annual_catchup, "_python_processes", lambda: [])


def test_a_card_read_while_nse_refused_has_no_stamp_and_takes_any_file_of_its_year(settings):
    pipeline, sink, _ = build(settings, REPORTS[:1], {REPORTS[0].pdf_url: _pdf(ANNUAL_TEXT)},
                              {NEMOTRON: [json.dumps(ANNUAL_CARD)]}, env={"NVIDIA_API_KEY": "n"})
    pipeline.nse = FakeNse({"DEMOCEM": LISTING["data"]}, refuse={"DEMOCEM"})  # the file was out; NSE said no
    pipeline.discover(date.fromisoformat(REPORTS[0].filing_date))
    pipeline.process("2000-01-01", "2100-01-01", time.monotonic() + 60, bulk=False)
    (card,) = _cards(sink).values()
    assert "annual_xbrl" not in card and "annual_xbrl_checked" not in card
    sink.close()
    report, sink, _ = _catch_up(settings, FakeNse({"DEMOCEM": LISTING["data"]}), reports=REPORTS[:1])
    assert report["rerun"] == {"n-fy25": "published with the table"}
