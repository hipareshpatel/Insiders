"""statements-backfill (owner, 30 Oct 2026): every company's past statements by screener's rules from the stored facts into
memory, with a backup first, a limit a run, and two checks against memory."""
from pathlib import Path

from bse_intel import restore, statements_backfill as sb, xbrl_facts
from bse_intel.sinks.local import LocalSink

FIX = Path(__file__).parent / "fixtures"


def _sink(settings, revenue=1.95):
    sink = LocalSink(settings)
    doc = xbrl_facts.parse_facts((FIX / "nse_dolphin_q4fy24_cons.xml").read_bytes(), "522261", "u")
    xbrl_facts.save(sink, "522261", doc["period"], doc["basis"], doc)
    sink.put_dossier("522261", {"scrip_code": "522261", "financial_metrics": [
        {"metric": "revenue", "period": "Q4FY24", "value": revenue, "unit": "INR_CR", "basis": "CONSOLIDATED",
         "source_news_id": "xbrl:res:522261:Q4FY24"}]})
    sink.put_dossier("500001", {"scrip_code": "500001", "financial_metrics": []})   # no stored facts
    return sink


def test_a_dry_run_counts_and_writes_nothing(settings):
    sink = _sink(settings)
    before = sink.get_dossier("522261")
    out = sb.run(sink, ["500001", "522261"])
    assert out["error"] is None and out["entries"] == 4 and out["written"] == 0 and out["no_facts"] == 1
    assert set(out["by_table"]) == {"quarters", "balance", "annual", "cash_flow"}
    assert sink.get_dossier("522261") == before


def test_apply_fills_memory_backs_up_resumes_and_restores(settings):
    sink = _sink(settings)
    before = sink.get_dossier("522261")
    out = sb.run(sink, ["500001", "522261"], apply=True)
    tables = {(e["period"], e["table"]) for e in sink.get_dossier("522261")["statements"]}
    assert {("Q4FY24", "quarters"), ("Q4FY24", "balance"), ("FY24", "annual"), ("FY24", "cash_flow")} == tables
    assert out["written"] == 1 and out["backup"]["dossiers"] == 1
    assert sb.run(sink, ["500001", "522261"], apply=True)["companies"] == 0, "resumes after the last company"
    assert sb.run(sink, ["500001", "522261"], apply=True, restart=True)["entries"] == 0, "nothing added twice"
    restore.apply(sink, restore.plan(sink, out["backup"]["prefix"], everything=True))
    assert sink.get_dossier("522261") == before


def test_a_quarter_far_from_memorys_revenue_is_left_out(settings):
    sink = _sink(settings, revenue=194.78)   # memory holds the figure 100x the stored file: a slip memory put right
    out = sb.run(sink, ["522261"])
    assert any("Q4FY24" in x and "Sales" in x for x in out["left_out"])
    assert out["by_table"].get("quarters", 0) == 0
