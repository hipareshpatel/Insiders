"""statements-backfill (owner, 30 Oct 2026): every company's past statements by screener's rules from the stored facts into
memory, with a backup first, a limit a run, and two checks against memory."""
import json
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


def test_ai_balance_snapshots_the_file_covers_are_dropped_unless_they_hold_a_figure_the_file_lacks(settings):
    """Owner, 30 Oct 2026: yes. SBI's "Mar-2026" net worth from its results PDF and its call beside the file's Q4FY26."""
    sink = _sink(settings)
    d = sink.get_dossier("522261")
    filed = {"period": "Q4FY26", "net_worth_cr": 614899.15, "deposits_cr": 5.0, "source_news_id": "xbrl:res:522261:Q4FY26",
             "lab": {"by": "file"}}
    d["balance_sheet"] = [
        {"period": "Mar-2026", "net_worth_cr": 472894.5, "source_news_id": "nse-1", "lab": {"by": "unknown"}},
        {"period": "Mar-2026", "net_worth_cr": 543519.0, "source_news_id": "nse-2", "lab": {"by": "ai", "doc": "call"}},
        {"period": "Mar-2026", "net_worth_cr": 1.0, "gold_cr": 2.0, "source_news_id": "nse-3", "lab": {"by": "ai"}},
        {"period": "Sep-2026", "net_worth_cr": 1.0, "source_news_id": "nse-4", "lab": {"by": "ai"}},   # no file snapshot yet
        filed]
    sink.put_dossier("522261", d)
    dry = sb.run(sink, ["500001", "522261"])
    assert (dry["balance_covered"], dry["balance_kept_extra"]) == (2, 1)
    assert len(sink.get_dossier("522261")["balance_sheet"]) == 5
    sb.run(sink, ["500001", "522261"], apply=True)
    assert [e["source_news_id"] for e in sink.get_dossier("522261")["balance_sheet"]] == ["nse-3", "nse-4", filed["source_news_id"]]
    assert sb._balance_end("Q4FY26") == sb._balance_end("Mar-2026") == "2026-03" and sb._balance_end("FY26") is None


def test_rating_snapshots_are_not_empty_and_are_put_back_from_the_backups(settings):
    """Review of PR #256: a rating filing's snapshot holds a rating and no figure; the clean-up of 30 Oct read it as empty.
    The cards read the last rating from memory (card_context.rating_change), so the backups' copies go back."""
    sink = _sink(settings)
    rating = {"period": "Jun-2026", "as_of": "2026-07-01", "credit_rating": "CRISIL AA+", "rating_agency": "CRISIL",
              "source_news_id": "nse-9"}
    d = sink.get_dossier("522261")
    d["balance_sheet"] = [rating, {"period": "Q4FY26", "as_of": "2026-05-01", "net_worth_cr": 1.0, "lab": {"by": "file"}},
                          {"period": "Mar-2026", "as_of": "2026-05-02", "net_worth_cr": 2.0, "rating_outlook": "Stable",
                           "lab": {"by": "ai"}}]
    assert sb.drop_empty_balance(d) == 0
    assert sb.drop_file_covered_balance(d) == (0, 1)   # the reading's outlook is not in the file's snapshot
    # what the clean-up of 30 Oct did: the rating snapshot gone, the dossier backed up first
    from bse_intel.backup import RunBackup
    sink.put_dossier("522261", d)
    RunBackup(sink, "statements-backfill", at="20261030T110000Z").dossier("522261")
    gone = json.loads(json.dumps(d))
    gone["balance_sheet"] = gone["balance_sheet"][1:]
    sink.put_dossier("522261", gone)
    lost = sb.lost_ratings(sink)
    assert lost == {"522261": {"main": [rating]}}
    dry = sb.run(sink, sorted(lost), ratings=lost)
    assert dry["ratings_put_back"] == 1 and len(sink.get_dossier("522261")["balance_sheet"]) == 2
    sb.run(sink, sorted(lost), apply=True, restart=True, ratings=lost)
    back = sink.get_dossier("522261")["balance_sheet"]
    assert [e["period"] for e in back] == ["Q4FY26", "Mar-2026", "Jun-2026"] and back[-1] == rating
    assert sb.run(sink, sorted(lost), apply=True, restart=True, ratings=lost)["ratings_put_back"] == 0
    assert sink.kv_get(sb.RESUME_KEY) != "522261" and sink.kv_get(sb.RATINGS_RESUME_KEY) == "522261"   # the fill's point unmoved
    labelled = dict(rating, lab={"by": "ai"})
    assert sb.put_back({"balance_sheet": [labelled]}, {"main": [rating]}) == 0


def _q(period, rows, by="file", rules="screener_view"):
    return {"period": period, "basis": "CONSOLIDATED", "table": "quarters", "rows": rows, "lab": {"by": by, "rules": rules}}


def test_replace_puts_back_a_file_entry_the_recipes_now_build_differently_and_leaves_the_rest():
    # owner, 31 Oct 2026: a recipe rule is site-wide, so the stored statements the stock page reads are rebuilt (statements-rebuild)
    dossier = {"statements": [_q("Q2FY27", {"Operating Profit": 1940.0}), _q("Q1FY27", {"Operating Profit": 3272.0}, by="card"),
                              _q("Q4FY26", {"Operating Profit": 2640.0})]}
    fresh = [_q("Q2FY27", {"Operating Profit": 2648.0}), _q("Q1FY27", {"Operating Profit": 2137.0}),
             _q("Q4FY26", {"Operating Profit": 2640.0}), _q("Q3FY26", {"Operating Profit": 2883.0})]
    plain = json.loads(json.dumps(dossier))
    assert sb.fill(plain, fresh) == 1   # without replace: only the missing quarter is added, as before
    assert {e["period"]: e["rows"]["Operating Profit"] for e in plain["statements"]}["Q2FY27"] == 1940.0
    assert sb.fill(dossier, fresh, replace=True) == 2   # Q2FY27 replaced, Q3FY26 added
    got = {e["period"]: (e["rows"]["Operating Profit"], e["lab"]["by"]) for e in dossier["statements"]}
    assert got == {"Q2FY27": (2648.0, "file"), "Q1FY27": (3272.0, "card"), "Q4FY26": (2640.0, "file"), "Q3FY26": (2883.0, "file")}


def test_screener_breaks_the_tie_when_memory_doubts_the_files_profit():
    # CGPOWER Q2FY26: memory's AI-read profit 18.24, the file's 284.29, Screener's 284: the file's quarter goes in
    assert sb._confirmed(lambda p, b: 284.0, "Q2FY26", "CONSOLIDATED", 284.29) is True
    assert sb._confirmed(lambda p, b: 18.0, "Q2FY26", "CONSOLIDATED", 284.29) is False     # Screener sides with memory: stays out
    assert sb._confirmed(lambda p, b: None, "Q2FY26", "CONSOLIDATED", 284.29) is False     # no page: the old check stands
    assert sb._confirmed(None, "Q2FY26", "CONSOLIDATED", 284.29) is False
    assert sb._confirmed(lambda p, b: 284.0, "FY26", "CONSOLIDATED", 284.29) is False      # a year: Screener's quarter page has none
