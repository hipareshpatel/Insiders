"""One list of switches for every job (owner, 27 Oct 2026): config/switches.toml, a repository variable over it, a step's
environment variable over both. Before it, the quick run that writes today's cards had none of the switches the main run
turned on, and the card refresh rebuilt stored cards with them off."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from bse_intel import settings

ROOT = Path(__file__).resolve().parents[2]
SWITCHES = ROOT / "pipeline" / "config" / "switches.toml"


def _file(monkeypatch):
    monkeypatch.setenv("BSE_INTEL_SWITCHES", str(SWITCHES))
    monkeypatch.delenv("CARD_WATCH_VERDICT", raising=False)


def test_the_file_turns_a_switch_on_when_nothing_else_is_set(monkeypatch):
    _file(monkeypatch)
    assert settings.card_watch_verdict() is True
    assert settings.card_eps_whole() is False   # not in the file: off


def test_a_repository_variable_wins_over_the_file_and_a_step_variable_over_both(monkeypatch):
    _file(monkeypatch)
    monkeypatch.setenv("REPO_VARS", json.dumps({"CARD_WATCH_VERDICT": "0", "PIPELINE_SCHEDULE": "on"}))
    assert settings.card_watch_verdict() is False
    monkeypatch.setenv("CARD_WATCH_VERDICT", "1")
    assert settings.card_watch_verdict() is True
    monkeypatch.setenv("REPO_VARS", json.dumps({"CARD_TWO_PARTS": "1"}))
    assert settings.card_two_parts() is True


def test_an_unreadable_repo_vars_or_a_missing_file_leaves_the_switch_off(monkeypatch):
    monkeypatch.setenv("BSE_INTEL_SWITCHES", str(ROOT / "no-such-file.toml"))
    monkeypatch.setenv("REPO_VARS", "not json")
    monkeypatch.delenv("CARD_WATCH_VERDICT", raising=False)
    assert settings.card_watch_verdict() is False


def test_no_workflow_sets_a_listed_switch_itself_and_every_python_workflow_passes_repo_vars():
    """The drift this file ends: a switch set in one workflow and not the others."""
    import tomllib

    listed = {k for k, v in tomllib.loads(SWITCHES.read_text(encoding="utf-8"))["on"].items() if v}
    assert len(listed) == 34   # CARD_YEAR_AGO_LABEL of 2 Nov; CARD_VERDICT_NEEDS_FIGURE, CARD_EVENT_REPEAT, DECK_DISCUSSED_PERIOD, METRIC_BUSINESS_LINE, CALL_MEMORY_VISION_CHECK (owner: ON) and DISCONTINUED_NEEDS_FIGURE of 1 Nov; the 13 of 27 Oct, the four card switches, SLIP_CHECK_NUMFIRST, MEMORY_CALL_V2, SLIP_CHECK_READER_OPTIONS, MEMORY_FILE_ONLY, CARD_FACT_SHEET, NUMFIRST_STOP_EARLY and SCREENER_CMLTD of 30 Oct, CARD_FACT_SHEET_LENDERS, ANNUAL_SCALE_FIX and UNIT_SLIP_XBRL_GUARD of 1 Nov
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        for name in listed:
            assert not re.search(rf"^\s*{name}\s*:", text, re.M), f"{wf.name} sets {name}: list it in switches.toml only"
        if "bse_intel" in text:
            assert "REPO_VARS: ${{ toJSON(vars) }}" in text, f"{wf.name} runs the pipeline without REPO_VARS"


def test_a_refresh_applies_one_basis_as_the_live_run_does(monkeypatch):
    """TMCV-type card: a standalone card must not keep a consolidated table; the live run removed it, the refresh did not."""
    from test_card_refresh import FILED, _card, _dossier

    from bse_intel import card_refresh
    from bse_intel.models import Filing

    filing = Filing(news_id="n1", scrip_code="500001", company_name="Demo Rail Ltd", headline="h", subject="",
                    filed_at=FILED, filing_date=FILED[:10])
    dossier = _dossier()
    asof = "2026-08-10T18:00:00+05:30"
    dossier["financial_metrics"].append({"metric": "revenue", "period": "Q2FY27", "value": 25338.0, "unit": "INR_CR",
                                         "as_of": asof, "news_id": "nse-1",
                                         "sources": [{"news_id": "nse-1", "value": 25338.0, "as_of": asof,
                                                      "basis": "CONSOLIDATED"}]})
    card = {**_card(), "basis": "STANDALONE",
            "results": {"period": "Q2FY27", "revenue": {"value": 25338.0}, "lines": [{"key": "revenue"}]}}
    monkeypatch.setenv("CARD_ONE_BASIS", "0")
    new, _ = card_refresh.refresh(copy.deepcopy(card), dossier, filing, None)
    assert new["results"] is not None   # off: as before
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    new, changed = card_refresh.refresh(copy.deepcopy(card), dossier, filing, None)
    assert new["results"] is None and "consolidated" in new["grounding"]["one_basis"][0]
    assert "results" in changed and "grounding" in changed
    assert card["results"] is not None   # the stored card itself is not touched


def test_a_switch_written_as_text_in_the_file_reads_as_written(monkeypatch, tmp_path):
    from bse_intel import settings as st

    path = tmp_path / "switches.toml"
    path.write_text('[on]\nCARD_WATCH_VERDICT = "0"\nCARD_TWO_PARTS = "1"\nCARD_ONE_BASIS = false\n', encoding="utf-8")
    monkeypatch.setenv("BSE_INTEL_SWITCHES", str(path))
    for name in ("CARD_WATCH_VERDICT", "CARD_TWO_PARTS", "CARD_ONE_BASIS"):
        monkeypatch.delenv(name, raising=False)
    assert (st.card_watch_verdict(), st.card_two_parts(), st.card_one_basis()) == (False, True, False)
    assert st.switches_on() == ["CARD_TWO_PARTS"]


def test_a_refresh_drops_a_one_basis_note_that_no_longer_holds(monkeypatch):
    from test_card_refresh import FILED, _card, _dossier

    from bse_intel import card_refresh
    from bse_intel.models import Filing

    filing = Filing(news_id="n1", scrip_code="500001", company_name="Demo Rail Ltd", headline="h", subject="",
                    filed_at=FILED, filing_date=FILED[:10])
    monkeypatch.setenv("CARD_ONE_BASIS", "1")
    card = {**_card(), "grounding": {"one_basis": ["an old note"], "other": 1}}
    new, changed = card_refresh.refresh(copy.deepcopy(card), _dossier(), filing, None)
    assert new["grounding"] == {"other": 1} and "grounding" in changed
    plain = _card()   # no grounding before: none is added
    new, changed = card_refresh.refresh(copy.deepcopy(plain), _dossier(), filing, None)
    assert "grounding" not in new and "grounding" not in changed
