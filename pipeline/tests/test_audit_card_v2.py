"""scripts/audit_card_v2.py: the on/off release check for CARD_EBITDA_PROFIT_V2 (F151), no AI, no network here."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

from bse_intel.dossier import results_snapshot
from test_card_v2 import RELEASE, _dossier


def _script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "audit_card_v2.py"
    spec = importlib.util.spec_from_file_location("audit_card_v2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_renders_off_and_on_and_writes_the_diff_and_a_blind_sample(tmp_path, monkeypatch):
    script = _script()
    monkeypatch.delenv("CARD_EBITDA_PROFIT_V2", raising=False)
    stored = results_snapshot(_dossier(), "n2")   # the table as stored today (switch off)
    card = {"event_type": "RESULTS", "impact_level": "MODERATE", "headline": "Acme Q2FY27", "results": stored,
            "what_happened": [], "why_it_matters": [], "key_numbers": []}
    row = {"news_id": "n2", "scrip_code": "1", "symbol": "ACME", "filed_at": "2026-10-20T10:00:00", "pdf_url": "u",
           "company_name": "Acme", "card_json": json.dumps(card)}
    other = {**row, "news_id": "n9", "card_json": json.dumps({**card, "event_type": "OTHER"})}
    export = tmp_path / "cards.json"
    export.write_text(json.dumps([row, other]))
    (tmp_path / "texts").mkdir()
    (tmp_path / "texts" / "n2.txt").write_text(RELEASE, encoding="utf-8")
    dossier = _dossier()
    for m in dossier["financial_metrics"]:
        m["as_of"] = "2026-10-19T09:00:00"
    monkeypatch.setattr(script, "get", lambda url: {"dossier": dossier})
    monkeypatch.setattr(sys, "argv", ["audit_card_v2.py", str(tmp_path / "out"), "--cards", str(export),
                                      "--texts", str(tmp_path / "texts"), "--sample", "5"])
    assert script.main() == 0
    assert "CARD_EBITDA_PROFIT_V2" not in os.environ                   # the script puts the switch back
    out = tmp_path / "out"
    report = json.loads((out / "diff.json").read_text(encoding="utf-8"))
    assert len(report) == 1 and report[0]["changed"] and report[0]["printed_ebitda"]
    assert any(x.startswith("TABLE EBITDA (Filing)") for x in report[0]["added"])
    assert any("Operating EBITDA (calculated)" in x and "other income" in x for x in report[0]["added"])
    assert "removed: TABLE EBITDA:" in (out / "diff.md").read_text(encoding="utf-8")
    sample = json.loads((out / "blind_sample.json").read_text(encoding="utf-8"))
    key = json.loads((out / "blind_key.json").read_text(encoding="utf-8"))
    assert sample[0]["id"] == "c01" and set(sample[0]) >= {"X", "Y", "pdf_url"} and key["c01"]["on_is"] in ("X", "Y")
    assert "calculated" in " ".join(sample[0]["X"] + sample[0]["Y"]) and "key" not in sample[0]
