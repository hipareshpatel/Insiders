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
    assert sb._confirmed(lambda p, b: 284.0, "FY26", "CONSOLIDATED", 284.29) is True       # a year: the page's annual Net Profit


def test_a_quarter_a_hundred_times_off_the_companys_other_quarters_is_left_out_and_taken_off_a_rebuild(monkeypatch):
    """Audit #303 item D: IMPAL Q1FY27 Sales 2.3429, Net Profit 0.217 against its other quarters' ~200 and ~25 (the file tagged in the
    wrong unit); the backfill from stored facts wrote it, so the Results page showed -98.8% and a 9,363% rise the next quarter."""
    from types import SimpleNamespace

    from bse_intel import screener_view as sv

    figures = {"Q1FY26": (196.69, 20.41), "Q2FY26": (198.71, 25.5), "Q3FY26": (230.99, 17.18), "Q4FY26": (210.72, 33.46),
               "Q1FY27": (2.3429, 0.217), "Q2FY27": (221.7, 27.67)}
    row = lambda v: SimpleNamespace(value=v)
    monkeypatch.setattr(sv, "_ours", lambda cf, fam, basis, table, period, memo: (
        ({"Sales": row(figures[period][0]), "Net Profit": row(figures[period][1])}, "") if table == "quarters" else (None, "")))
    cf = SimpleNamespace(results={(p, "STANDALONE"): f"k{p}" for p in figures}, annual={}, family=lambda b: "corporate")
    entries, left = sb.company_entries(cf, {}, "t")
    assert {e["period"] for e in entries if e["table"] == "quarters"} == set(figures) - {"Q1FY27"}
    assert left == [f"STANDALONE quarters Q1FY27: {sb.UNIT_SLIP_NOTE}"]
    # the slipped entry the earlier backfill wrote is taken out on a rebuild; an entry a card wrote is left alone
    stored = {"statements": [{"period": "Q1FY27", "basis": "STANDALONE", "table": "quarters", "rows": {"Sales": 2.3429},
                              "lab": {"by": "file", "rules": "screener_view"}},
                             {"period": "Q1FY27", "basis": "CONSOLIDATED", "table": "quarters", "rows": {"Sales": 9.0}, "lab": {"by": "card"}}]}
    assert sb.fill(stored, entries, replace=True, slipped=sb.slipped_keys(left)) == len(entries) + 1
    assert [(e["period"], e["basis"]) for e in stored["statements"] if e["period"] == "Q1FY27"] == [("Q1FY27", "CONSOLIDATED")]


def test_a_seasonal_quarter_as_large_as_a_year_earlier_is_no_unit_slip(monkeypatch):
    """Dry run 41225623600: Maharashtra Scooters' Jul-Sep quarter (its dividends) is ~40x its other quarters every year."""
    from types import SimpleNamespace

    from bse_intel import screener_view as sv

    figures = {"Q1FY26": (29.27, 35.36), "Q2FY26": (271.02, 267.07), "Q3FY26": (6.44, 4.12), "Q4FY26": (6.03, 4.01),
               "Q1FY27": (5.41, 3.32), "Q2FY27": (297.36, 293.27)}
    row = lambda v: SimpleNamespace(value=v)
    monkeypatch.setattr(sv, "_ours", lambda cf, fam, basis, table, period, memo: (
        ({"Sales": row(figures[period][0]), "Net Profit": row(figures[period][1])}, "")
        if table == "quarters" and period in figures else (None, "")))
    cf = SimpleNamespace(results={(p, "STANDALONE"): f"k{p}" for p in figures}, annual={}, family=lambda b: "corporate")
    entries, left = sb.company_entries(cf, {}, "t")
    assert left == [] and {e["period"] for e in entries} >= {"Q2FY26", "Q2FY27"}


def test_a_december_year_company_gets_its_year_and_its_december_balance_sheet(monkeypatch):
    """Stored-statements check, 31 Oct 2026: Schaeffler, Rain and Hexaware's FY25 years (Dec 2024) and Dec balance sheets were never
    built, as only Q4 years and Q2/Q4 balance sheets were. The newest, unfinished year stays out."""
    from types import SimpleNamespace

    from bse_intel import screener_view as sv

    quarters = ["Q4FY24", "Q1FY25", "Q2FY25", "Q3FY25", "Q4FY25", "Q1FY26"]
    row = lambda v: SimpleNamespace(value=v)

    def ours(cf, fam, basis, table, period, memo):
        if table == "quarters" and period in quarters:
            return {"Sales": row(100.0), "Net Profit": row(10.0)}, ""
        if table == "balance" and period in ("Q1FY25", "Q3FY25"):          # its June half-year and December year-end sheets
            return {"Total Assets": row(500.0)}, ""
        if table in ("annual", "cash_flow"):
            return ({"Sales": row(400.0), "Net Profit": row(40.0)} if table == "annual" else {"Cash from Operating Activity": row(50.0)}), ""
        return None, ""

    monkeypatch.setattr(sv, "_ours", ours)
    cf = SimpleNamespace(results={(p, "CONSOLIDATED"): f"k{p}" for p in quarters}, annual={}, family=lambda b: "corporate")
    entries, _ = sb.company_entries(cf, {}, "t")
    got = {(e["table"], e["period"]) for e in entries}
    assert {("balance", "Q1FY25"), ("balance", "Q3FY25"), ("annual", "FY25"), ("cash_flow", "FY25")} <= got
    assert ("annual", "FY26") not in got and ("balance", "Q2FY25") not in got   # FY26 unfinished; no sheet in that file


def test_a_year_held_only_as_an_annual_reports_comparative_is_built_with_its_march_sheet(monkeypatch):
    """Every-company check after the 1 Nov 2026 rebuild: Meesho, Anthem and others had FY25 only as the FY26 report's comparative."""
    from types import SimpleNamespace

    from bse_intel import screener_view as sv

    row = lambda v: SimpleNamespace(value=v)
    built = []

    def ours(cf, fam, basis, table, period, memo):
        built.append((table, period))
        if table == "quarters" and period in ("Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"):
            return {"Sales": row(100.0), "Net Profit": row(10.0)}, ""
        if table == "annual" and period in ("FY25", "FY26"):
            return {"Sales": row(400.0), "Net Profit": row(40.0)}, ""
        if table == "balance" and period in ("Q4FY25", "Q4FY26"):
            return {"Total Assets": row(500.0)}, ""
        return None, ""

    monkeypatch.setattr(sv, "_ours", ours)
    cf = SimpleNamespace(results={(p, "CONSOLIDATED"): p for p in ("Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26")},
                         annual={("FY26", "CONSOLIDATED"): "ar26"}, family=lambda b: "corporate")
    entries, _ = sb.company_entries(cf, {}, "t")
    got = {(e["table"], e["period"]) for e in entries}
    assert {("annual", "FY25"), ("balance", "Q4FY25"), ("annual", "FY26"), ("balance", "Q4FY26")} <= got


def test_a_december_year_is_stored_from_the_files_that_hold_its_twelve_months(monkeypatch):
    """Owner, 1 Nov 2026: VBL, ABB, Siemens: a "YE:2025-12" year goes in where a report or the Dec-quarter file holds its twelve months."""
    from types import SimpleNamespace

    from bse_intel import screener_view as sv

    row = lambda v: SimpleNamespace(value=v)

    def ours(cf, fam, basis, table, period, memo):
        if table == "quarters":
            return {"Sales": row(100.0), "Net Profit": row(10.0)}, ""
        if period == "YE:2025-12" and table in ("annual", "cash_flow"):
            return ({"Sales": row(400.0), "Net Profit": row(40.0)} if table == "annual" else {"Net Cash Flow": row(5.0)}), ""
        return None, ""

    monkeypatch.setattr(sv, "_ours", ours)
    quarters = ("Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26")
    cf = SimpleNamespace(results={(p, "CONSOLIDATED"): p for p in quarters}, annual={}, family=lambda b: "corporate")
    entries, _ = sb.company_entries(cf, {}, "t")
    got = {(e["table"], e["period"]) for e in entries}
    assert {("annual", "YE:2025-12"), ("cash_flow", "YE:2025-12")} <= got
    assert not {p for t, p in got if p.startswith("YE:") and p != "YE:2025-12"}   # Jun / Sep quarters held no twelve months


def test_a_december_year_before_the_stored_quarters_comes_from_the_annual_reports(monkeypatch):
    """Every-company check 1 Nov 2026 (run 41254893012): ELANTAS has quarters from Q1FY26 only, so only YE:2025-12 was built, while
    its reports hold 2023 and 2024 (screener 680 and 749). A March company asks for no earlier December year."""
    from types import SimpleNamespace

    from bse_intel import screener_view as sv

    row = lambda v: SimpleNamespace(value=v)
    years = ("YE:2023-12", "YE:2024-12", "YE:2025-12")
    asked = []

    def ours(cf, fam, basis, table, period, memo):
        asked.append(period)
        if table == "quarters":
            return {"Sales": row(100.0), "Net Profit": row(10.0)}, ""
        if period in years and table in ("annual", "cash_flow") and cf.december:
            return ({"Sales": row(400.0), "Net Profit": row(40.0)} if table == "annual" else {"Net Cash Flow": row(5.0)}), ""
        return None, ""

    monkeypatch.setattr(sv, "_ours", ours)
    quarters = ("Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26", "Q1FY27")
    for december in (True, False):
        asked.clear()
        cf = SimpleNamespace(results={(p, "STANDALONE"): p for p in quarters}, december=december,
                             annual={("FY25", "STANDALONE"): "ar25", ("FY26", "STANDALONE"): "ar26"}, family=lambda b: "corporate")
        entries, _ = sb.company_entries(cf, {}, "t")
        got = {(e["table"], e["period"]) for e in entries if e["period"].startswith("YE:")}
        if december:
            assert got == {(t, y) for t in ("annual", "cash_flow") for y in years}
        else:
            assert not got and "YE:2023-12" not in asked


def test_a_june_year_whose_quarters_start_in_september_keeps_that_june(monkeypatch):
    """Review of #310: quarters from Q2FY26 give YE:2025-09 as the first quarter end; YE:2025-06 (twelve months to June) is wanted."""
    from types import SimpleNamespace

    from bse_intel import screener_view as sv

    row = lambda v: SimpleNamespace(value=v)
    years = ("YE:2024-06", "YE:2025-06", "YE:2026-06")

    def ours(cf, fam, basis, table, period, memo):
        if table == "quarters":
            return {"Sales": row(100.0), "Net Profit": row(10.0)}, ""
        if period in years and table == "annual":
            return {"Sales": row(400.0), "Net Profit": row(40.0)}, ""
        return None, ""

    monkeypatch.setattr(sv, "_ours", ours)
    quarters = ("Q2FY26", "Q3FY26", "Q4FY26", "Q1FY27")
    cf = SimpleNamespace(results={(p, "STANDALONE"): p for p in quarters}, annual={("FY26", "STANDALONE"): "ar26"},
                         family=lambda b: "corporate")
    entries, _ = sb.company_entries(cf, {}, "t")
    assert {e["period"] for e in entries if e["table"] == "annual" and e["period"].startswith("YE:")} == set(years)


def test_a_re_read_results_file_keeps_the_rebuilds_sheet_and_years():
    """1 Nov 2026: the live run re-read RITES's and VINATIORGA's May results files and put the results file's FY26 cash flow and
    March sheet over the rebuild's, which reads the annual report first (RITES cash from operations 165.97 over 327.48, screener 327).
    A stored-facts entry of the balance sheet, the year or its cash flow stays; the quarter is the file's own and is rewritten."""
    from pathlib import Path

    from bse_intel import statements
    from bse_intel import xbrl_facts as xf

    name = "nse_hdfcbank_q2fy27_cons.xml"
    doc = xf.parse_facts((Path(__file__).parent / "fixtures" / name).read_bytes(), "500180", f"https://nsearchives.nseindia.com/{name}")
    d: dict = {}
    assert statements.remember(d, doc, "nse-1", "2026-10-20", "2026-10-20T10:00:00Z") == 2   # the quarter and the half-year sheet
    sheet = next(e for e in d[statements.KEY] if e["table"] == "balance")
    sheet["rows"] = {"Total Assets": 1.0}
    sheet["lab"] = {**sheet["lab"], "from": "stored facts"}
    assert statements.remember(d, doc, "nse-2", "2026-10-21", "2026-10-21T10:00:00Z") == 1
    got = {e["table"]: e for e in d[statements.KEY]}
    assert got["balance"]["rows"] == {"Total Assets": 1.0} and got["quarters"]["source_news_id"] == "nse-2"
