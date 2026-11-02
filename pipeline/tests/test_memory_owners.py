"""memory-owners-drop (lead, 2 Nov 2026): an owners' profit no file backs (every source labelled unknown) that its own period's
file figures contradict is taken out of memory, after a backup; a dry run lists it. ADANIPORTS Q4FY26: memory's 1,238.67 is the
owners' share of other comprehensive income beside the file's whole profit 3,308.30."""

import json

from bse_intel import memory_owners as M
from bse_intel import restore
from bse_intel.sinks.local import LocalSink


def _row(metric, period, value, by, basis="CONSOLIDATED"):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR",
            "sources": [{"news_id": f"nse-{metric}", "value": value, "unit": "INR_CR", "basis": basis, "lab": {"by": by, "basis": basis}}]}


ADANIPORTS = {"scrip_code": "532921", "symbol": "ADANIPORTS", "financial_metrics": [
    _row("pat", "Q4FY26", 3308.30, "file"), _row("pat_owners", "Q4FY26", 1238.67, "unknown"),
    _row("revenue", "Q4FY26", 9126.0, "file"), _row("pat", "Q3FY26", 3040.0, "file"), _row("pat_owners", "Q3FY26", 3014.0, "unknown")]}


def test_adaniports_owners_figure_no_file_backs_is_dropped():
    found = M.suspects(ADANIPORTS)
    assert [(r["period"], r["value"], r["pat"]) for r in found] == [("Q4FY26", 1238.67, 3308.30)]   # Q3's 3,014 is within 2%
    dossier = json.loads(json.dumps(ADANIPORTS))
    M.drop(dossier)
    assert ("pat_owners", "Q4FY26") not in {(m["metric"], m["period"]) for m in dossier["financial_metrics"]}
    assert len(dossier["financial_metrics"]) == 4


def test_a_true_owners_figure_with_its_minority_share_is_kept():
    dossier = {"financial_metrics": [_row("pat", "Q4FY26", 1000.0, "file"), _row("pat_minority", "Q4FY26", 120.0, "file"),
                                     _row("pat_owners", "Q4FY26", 880.0, "unknown")]}
    assert M.suspects(dossier) == []
    # against the minority share it does not add up: dropped
    dossier["financial_metrics"][2] = _row("pat_owners", "Q4FY26", 700.0, "unknown")
    assert [r["value"] for r in M.suspects(dossier)] == [700.0]


def test_only_unknown_rows_on_the_same_basis_with_a_file_profit_are_judged():
    for owners in (_row("pat_owners", "Q4FY26", 1238.67, "file"), _row("pat_owners", "Q4FY26", 1238.67, "ai"),
                   {"metric": "pat_owners", "period": "Q4FY26", "value": 1238.67}):   # no label at all
        assert M.suspects({"financial_metrics": [_row("pat", "Q4FY26", 3308.30, "file"), owners]}) == [], owners
    # a file profit on the other basis, or a model's profit: no judge
    assert M.suspects({"financial_metrics": [_row("pat", "Q4FY26", 3308.30, "file", "STANDALONE"),
                                             _row("pat_owners", "Q4FY26", 1238.67, "unknown")]}) == []
    assert M.suspects({"financial_metrics": [_row("pat", "Q4FY26", 3308.30, "ai"), _row("pat_owners", "Q4FY26", 1238.67, "unknown")]}) == []
    # a zero minority is the template's filler: judged as none
    zero = {"financial_metrics": [_row("pat", "Q4FY26", 3308.30, "file"), _row("pat_minority", "Q4FY26", 0.0, "file"),
                                  _row("pat_owners", "Q4FY26", 1238.67, "unknown")]}
    assert "(0 in the file)" in M.suspects(zero)[0]["why"]


def test_dry_run_lists_and_apply_backs_up_then_restore_puts_it_back(settings):
    sink = LocalSink(settings)
    sink.put_dossier("532921", json.loads(json.dumps(ADANIPORTS)))
    before = sink.get_dossier("532921")
    dry = M.run(sink, ["532921"])
    assert dry["error"] is None and dry["dossiers_written"] == 0 and sink.get_dossier("532921") == before
    assert dry["rows"][0] | {} == {"scrip": "532921", "symbol": "ADANIPORTS", "period": "Q4FY26", "basis": "CONSOLIDATED",
                                   "value": 1238.67, "pat": 3308.30, "minority": None,
                                   "why": "the file's profit 3308.3, no minority share"}
    assert "would drop" in M.render(dry) and "532921 ADANIPORTS Q4FY26 CONSOLIDATED pat_owners 1238.67" in M.render(dry)
    out = M.run(sink, ["532921"], apply=True)
    assert out["dossiers_written"] == 1 and out["backup"]["dossiers"] == 1
    assert ("pat_owners", "Q4FY26") not in {(m["metric"], m["period"]) for m in sink.get_dossier("532921")["financial_metrics"]}
    assert M.run(sink, ["532921"], apply=True)["rows"] == []   # a second run finds nothing
    prefix = out["backup"]["prefix"]
    assert json.loads(sink.get_object(f"{prefix}memory/532921.json")) == before
    restore.apply(sink, restore.plan(sink, prefix, everything=True))
    assert sink.get_dossier("532921") == before
