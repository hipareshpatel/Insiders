"""scripts/audit_two_parts.py: the on/off release check for CARD_TWO_PARTS (F152), no AI, no network here."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

TEXT = "Revenue from operations 388.15 225.30. Profit after tax 46.15 30.03."


def _script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "audit_two_parts.py"
    spec = importlib.util.spec_from_file_location("audit_two_parts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_renders_off_and_on_and_writes_the_diff_and_a_blind_sample(tmp_path, monkeypatch):
    script = _script()
    card = {"event_type": "RESULTS", "impact_level": "MODERATE", "headline": "Acme Q2FY27 revenue 388.15 Cr, PAT 46.15 Cr",
            "takeaway": "Margins held.",
            "what_happened": [{"text": "Revenue 388.15", "quote": "Revenue from operations 388.15 225.30"}],
            "why_it_matters": [{"text": "Orders of ₹9,876 Cr would double revenue", "basis": "FILING"},
                               {"text": "Profit was steady", "basis": "FILING"}],
            "key_numbers": [{"label": "PAT", "value": "46.15", "quote": "Profit after tax 46.15 30.03"}]}
    row = {"news_id": "n2", "scrip_code": "1", "symbol": "ACME", "filed_at": "2026-10-20T10:00:00", "pdf_url": "u",
           "headline": "Results", "card_json": json.dumps(card)}
    export = tmp_path / "cards.json"
    export.write_text(json.dumps([row]))
    (tmp_path / "texts").mkdir()
    (tmp_path / "texts" / "n2.txt").write_text(TEXT, encoding="utf-8")
    monkeypatch.setattr(script.v2, "get", lambda url: {"dossier": {"scrip_code": "1"}})
    monkeypatch.setattr(sys, "argv", ["audit_two_parts.py", str(tmp_path / "out"), "--cards", str(export),
                                      "--texts", str(tmp_path / "texts"), "--sample", "5"])
    assert script.main() == 0
    out = tmp_path / "out"
    (rep,) = json.loads((out / "diff.json").read_text(encoding="utf-8"))
    assert rep["lines_off"] == 6 and [h["field"] for h in rep["hidden"]] == ["why_it_matters"]
    assert "9,876" in rep["hidden"][0]["text"]
    assert [x["field"] for x in rep["on"]["part1"] if x["field"] != "block"] == ["headline", "what_happened", "key_numbers"]
    assert "Profit was steady" in [x["text"] for x in rep["on"]["part2"]]
    assert "[why_it_matters]" in (out / "diff.md").read_text(encoding="utf-8")
    (item,) = json.loads((out / "blind_sample.json").read_text(encoding="utf-8"))
    key = json.loads((out / "blind_key.json").read_text(encoding="utf-8"))["c01"]
    texts = {p["n"]: p["text"] for p in item["part2"]}
    assert len(key["hidden"]) == 1 and "9,876" in texts[key["hidden"][0]]       # shown to reviewers, marked only in the key
    assert "hidden" not in json.dumps(item)
