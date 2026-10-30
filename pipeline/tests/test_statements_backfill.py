"""statements-backfill (owner, 30 Oct 2026): every company's past statements by screener's rules from the stored facts into
memory, with a backup first, a limit a run, and two checks against memory."""
from pathlib import Path

from bse_intel import restore, statements_backfill as sb, xbrl_facts
from bse_intel.sinks.local import LocalSink

FIX = Path(__file__).parent / "fixtures"


def _sink(settings, pat=None):
    sink = LocalSink(settings)
    doc = xbrl_facts.parse_facts((FIX / "nse_dolphin_q4fy24_cons.xml").read_bytes(), "522261", "u")
    xbrl_facts.save(sink, "522261", doc["period"], doc["basis"], doc)
    from bse_intel import screener_view as sv
    facts = sv.CompanyFacts([xbrl_facts.key("522261", "Q4FY24", "CONSOLIDATED")], sink.get_object)
    filed = sv._ours(facts, "corporate", "CONSOLIDATED", "quarters", "Q4FY24", {})[0]["Net Profit"].value
    sink.put_dossier("522261", {"scrip_code": "522261", "financial_metrics": [
        {"metric": "pat", "period": "Q4FY24", "value": filed if pat is None else pat, "unit": "INR_CR", "basis": "CONSOLIDATED",
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


def test_named_companies_neither_read_nor_move_the_resume_point(settings):
    sink = _sink(settings)
    sink.kv_set(sb.RESUME_KEY, "540000", "2026-10-30T02:00:00+05:30")
    out = sb.run(sink, ["522261"], apply=True, named=True)
    assert out["written"] == 1 and sink.kv_get(sb.RESUME_KEY) == "540000"


def test_the_live_and_backfill_tables_share_their_columns(settings):
    """A March file's year is one column whichever writer filled it first (blind review: "Q4FY26" and "FY26" both showed
    as Mar 2026)."""
    from bse_intel import statements
    sink = _sink(settings)
    d = sink.get_dossier("522261")
    statements.remember(d, xbrl_facts.loads(sink.get_object(xbrl_facts.key("522261", "Q4FY24", "CONSOLIDATED"))), "n1",
                        "2024-05-20T18:00:00+05:30", "2024-05-20T18:01:00+05:30")
    sink.put_dossier("522261", d)
    assert sb.run(sink, ["522261"], apply=True, named=True)["entries"] == 0


def test_a_quarter_far_from_memorys_revenue_is_left_out(settings):
    probe = _sink(settings)
    pat = probe.get_dossier("522261")["financial_metrics"][0]["value"]
    sink = _sink(settings, pat=pat * 100)   # memory holds the figure 100x the stored file: a slip memory put right
    out = sb.run(sink, ["522261"])
    assert any("Q4FY24" in x and "Net Profit" in x for x in out["left_out"])
    assert out["by_table"].get("quarters", 0) == 0


def test_a_failed_facts_read_stops_the_company_not_a_silent_gap():
    from bse_intel import screener_view as sv

    def loader(key):
        raise RuntimeError("429")

    cf = sv.CompanyFacts(["raw/xbrl-facts/500001/Q1FY27-consolidated.json"], loader)
    import pytest
    with pytest.raises(RuntimeError):
        cf._load("raw/xbrl-facts/500001/Q1FY27-consolidated.json")
    cf2 = sv.CompanyFacts([], lambda key: b"not json")
    assert cf2._load("x") is None


def test_a_failed_write_stops_the_resume_point_before_it_and_later_writes_add_nothing_twice(settings):
    """Writes go 8 at a time: the resume point is the last company of the unbroken run before the first failure."""
    sink = _sink(settings)
    for scrip in ("522262", "522263"):
        doc = xbrl_facts.parse_facts((FIX / "nse_dolphin_q4fy24_cons.xml").read_bytes(), scrip, "u")
        xbrl_facts.save(sink, scrip, doc["period"], doc["basis"], doc)
        sink.put_dossier(scrip, {"scrip_code": scrip, "financial_metrics": []})
    real = sink.put_dossier

    def put(scrip, dossier):
        if scrip == "522262":
            raise RuntimeError("Worker 500")
        return real(scrip, dossier)

    sink.put_dossier = put
    out = sb.run(sink, ["500001", "522261", "522262", "522263"], apply=True)
    assert out["error"].startswith("522262, writing") and out["last"] == "522261"
    assert sink.kv_get(sb.RESUME_KEY) == "522261"
    assert out["written"] == 2 and "statements" in sink.get_dossier("522263")   # written beside the failure
    sink.put_dossier = real
    again = sb.run(sink, ["500001", "522261", "522262", "522263"], apply=True)
    assert again["error"] is None and again["written"] == 1 and sink.kv_get(sb.RESUME_KEY) == "522263"


def test_a_clean_up_with_nothing_added_is_written_and_an_unchanged_company_is_not(settings):
    """30 Oct 2026: the filler-zero ratios xbrl_extras.remember drops were never saved, the run writing only where it added."""
    sink = _sink(settings)
    sb.run(sink, ["500001", "522261"], apply=True)
    d = sink.get_dossier("522261")
    d["fin_ratios"] = [{"period": "Q2FY24", "basis": "CONSOLIDATED", "values": {"CET1Ratio": 0.0}}]
    sink.put_dossier("522261", d)
    out = sb.run(sink, ["500001", "522261"], apply=True, restart=True)
    assert out["written"] == 1 and out["entries"] == 0
    assert not sink.get_dossier("522261").get("fin_ratios")
    assert sb.run(sink, ["500001", "522261"], apply=True, restart=True)["written"] == 0


def test_empty_balance_snapshots_are_dropped_and_counted_in_a_dry_run(settings):
    """Owner, 30 Oct 2026: yes to removing an AI reading's dated stub (SBI "Jun-2026") by code; the dry run gives the count."""
    sink = _sink(settings)
    d = sink.get_dossier("522261")
    d["balance_sheet"] = [{"period": "Q4FY24", "as_of": "2024-05-01", "net_worth_cr": 120.5},
                          {"period": "Jun-2024", "as_of": "2024-08-13", "source_news_id": "nse-1"}]
    d["standalone"] = {"metrics": [], "balance_sheet": [{"period": "Jun-2024", "as_of": "2024-08-13"}]}
    sink.put_dossier("522261", d)
    dry = sb.run(sink, ["500001", "522261"])
    assert dry["balance_stubs"] == 2 and len(sink.get_dossier("522261")["balance_sheet"]) == 2
    sb.run(sink, ["500001", "522261"], apply=True)
    after = sink.get_dossier("522261")
    assert [e["period"] for e in after["balance_sheet"]] == ["Q4FY24"] and after["standalone"]["balance_sheet"] == []
