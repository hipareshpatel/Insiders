"""The one-time screener.in fill (F161): the page, each rule, the run, the labels and the reader switch."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from bse_intel import memory_gaps as mg
from bse_intel import screener_fill as sf
from bse_intel.dossier import (SCREENER_KEY, dossier_as_of, put_screener, results_snapshot, view_as_of, with_screener)

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 25)
EIGHT = ["Q1FY27", "Q4FY26", "Q3FY26", "Q2FY26", "Q1FY26", "Q4FY25", "Q3FY25", "Q2FY25"]


def page_of(name):
    return sf.parse_page((FIXTURES / f"screener_{name}.html").read_text(encoding="utf-8"))


def fig(metric, period, value, basis="CONSOLIDATED", scrip="1"):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "basis": basis, "as_of": "2026-01-01",
            "source_news_id": f"xbrl:res:{scrip}:{period}"}


def dossier_like(page, basis, gaps, skip_metrics=(), extra=()):
    """Memory holding the exchange file's figures (a few paise off the page's whole crores) for the window, except ``gaps``."""
    rows = []
    for period in EIGHT:
        if period in gaps:
            continue
        for metric, nudge in (("revenue", 0.3), ("pat", 0.2)):
            if metric not in skip_metrics:
                rows.append(fig(metric, period, page["quarters"][period][metric] + nudge, basis))
    return {"financial_metrics": rows + list(extra), "balance_sheet": []}


def decide(dossier, page, symbol="DEMO"):
    return sf.decide(dossier, mg.check(dossier, TODAY), page, symbol)


def reasons(decision):
    return {(s["period"], s["metric"]): s["reason"] for s in decision["skipped"]}


# --- the page -------------------------------------------------------------------------------------------------------

def test_period_names_follow_the_indian_year():
    assert sf.period_of("Sep 2025") == "Q2FY26" and sf.period_of("Mar 2026") == "Q4FY26"
    assert sf.period_of("Jun 2026") == "Q1FY27" and sf.period_of("Dec 2025") == "Q3FY26" and sf.period_of("Mar 2025") == "Q4FY25"
    assert sf.period_of("TTM") is None


def test_parse_page_reads_basis_columns_and_figures():
    jyothy = page_of("jyothylab_standalone")
    assert jyothy["basis"] == "STANDALONE" and len(jyothy["quarters"]) == 13
    assert jyothy["quarters"]["Q1FY27"] == {"revenue": 773.0, "pat": 48.0}
    nmdc = page_of("nmdc_consolidated")
    assert nmdc["basis"] == "CONSOLIDATED" and nmdc["quarters"]["Q4FY25"] == {"revenue": 7005.0, "pat": 1477.0}
    assert sf.parse_page("<html>no results here</html>") is None


# --- the rules ------------------------------------------------------------------------------------------------------

def test_a_proved_page_fills_the_gap_quarters_both_lines():
    page = page_of("jyothylab_standalone")
    d = decide(dossier_like(page, "STANDALONE", {"Q4FY26", "Q3FY26"}), page, "JYOTHYLAB")
    got = {(f["period"], f["metric"]): f for f in d["fills"]}
    assert set(got) == {("Q3FY26", "revenue"), ("Q3FY26", "pat"), ("Q4FY26", "revenue"), ("Q4FY26", "pat")}
    assert got[("Q3FY26", "pat")]["value"] == 81.0 and got[("Q4FY26", "revenue")]["value"] == 717.0
    assert got[("Q4FY26", "pat")]["source"] == "screener:JYOTHYLAB:Q4FY26:STANDALONE"
    assert d["evidence"]["revenue_overlaps"] == 6 and d["evidence"]["pat_overlaps"] == 6 and d["evidence"]["pat_max_diff"] < 0.25


def test_the_page_on_the_other_basis_fills_nothing():
    page = page_of("jyothylab_standalone")   # screener shows the standalone page for a company with no consolidated one
    d = decide(dossier_like(page, "CONSOLIDATED", {"Q4FY26"}), page)
    assert d["fills"] == [] and set(reasons(d).values()) == {"page basis missing"}
    assert decide(dossier_like(page, "STANDALONE", {"Q4FY26"}), None)["fills"] == []


def test_a_lender_is_skipped_whole():
    page = page_of("hdfcbank_consolidated")
    dossier = dossier_like(page, "CONSOLIDATED", {"Q4FY26"}, extra=[fig("interest_earned", "Q1FY27", 1.0)])
    d = decide(dossier, page)
    assert d["fills"] == [] and set(reasons(d).values()) == {"bank"}
    assert set(reasons(decide({**dossier_like(page, "CONSOLIDATED", {"Q4FY26"}), "industry": "Private Sector Bank"}, page)).values()) == {"bank"}


def test_a_small_profit_is_not_filled_but_the_revenue_is():
    page = page_of("jyothylab_standalone")
    page["quarters"]["Q4FY26"]["pat"] = 9.0
    d = decide(dossier_like(page, "STANDALONE", {"Q4FY26"}), page)
    assert reasons(d) == {("Q4FY26", "pat"): "small profit"} and [f["metric"] for f in d["fills"]] == ["revenue"]
    page["quarters"]["Q4FY26"]["pat"] = -12.0   # a loss of ten or more is a profit figure too
    assert {f["metric"] for f in decide(dossier_like(page, "STANDALONE", {"Q4FY26"}), page)["fills"]} == {"revenue", "pat"}


def test_a_revenue_line_that_differs_gives_profit_only():
    page = page_of("jyothylab_standalone")
    dossier = dossier_like(page, "STANDALONE", {"Q4FY26"})
    for row in dossier["financial_metrics"]:
        if row["metric"] == "revenue":
            row["value"] += 25.0   # a steady gap, as RELIANCE, ITC, HINDUNILVR and GAIL show
    d = decide(dossier, page)
    assert reasons(d) == {("Q4FY26", "revenue"): "revenue line differs"} and [f["metric"] for f in d["fills"]] == ["pat"]


def test_too_few_overlaps_or_a_profit_that_disagrees_fills_nothing():
    page = page_of("jyothylab_standalone")
    few = dossier_like(page, "STANDALONE", set(EIGHT[:7]) | {"Q4FY26"})   # one overlap
    assert decide(few, page)["fills"] == []
    dossier = dossier_like(page, "STANDALONE", {"Q4FY26"})
    next(r for r in dossier["financial_metrics"] if r["metric"] == "pat" and r["period"] == "Q2FY26")["value"] += 3.0
    d = decide(dossier, page)
    assert d["fills"] == [] and set(reasons(d).values()) == {"misaligned"}


def test_a_figure_memory_has_is_never_overwritten():
    page = page_of("jyothylab_standalone")
    dossier = dossier_like(page, "STANDALONE", {"Q4FY26"})
    # a card-written revenue for the gap quarter (not an exchange file, so still a gap for memory_gaps)
    dossier["financial_metrics"].append({"metric": "revenue", "period": "Q4FY26", "value": 700.0, "basis": "STANDALONE",
                                         "as_of": "x", "source_news_id": "nse-1"})
    d = decide(dossier, page)
    assert reasons(d) == {("Q4FY26", "revenue"): "has figure"} and [f["metric"] for f in d["fills"]] == ["pat"]
    put_screener(dossier, d["fills"], "JYOTHYLAB", "2026-10-26T10:00:00+05:30")
    assert put_screener(dossier, [{"metric": "pat", "period": "Q4FY26", "value": 1.0, "basis": "STANDALONE"},
                                  {"metric": "revenue", "period": "Q4FY26", "value": 1.0, "basis": "STANDALONE"}],
                        "JYOTHYLAB", "later") == 0
    assert [e["value"] for e in dossier[SCREENER_KEY]] == [68.0]


def test_a_year_that_does_not_add_up_stops_the_quarter_and_one_that_does_lets_it_through():
    """NMDC's Mar 2026 column on screener (11,343 sales, 2,027 profit) against the company's own: the year memory holds
    does not accept it."""
    page = page_of("nmdc_consolidated")
    q = page["quarters"]
    gap = {"Q4FY26"}
    year = lambda metric, last: fig(metric, "FY26", sum(q[p][metric] for p in ("Q1FY26", "Q2FY26", "Q3FY26")) + last)  # noqa: E731
    bad = dossier_like(page, "CONSOLIDATED", gap, extra=[year("pat", 1483.18), year("revenue", 7004.59)])
    d = decide(bad, page, "NMDC")
    assert d["fills"] == [] and set(reasons(d).values()) == {"sum check"}
    page["quarters"]["Q4FY26"] = {"revenue": 7005.0, "pat": 1483.0}   # the quarter as the company reports it
    good = dossier_like(page, "CONSOLIDATED", gap, extra=[year("pat", 1483.18), year("revenue", 7004.59)])
    d = decide(good, page, "NMDC")
    assert {(f["period"], f["metric"], f["sum_checks"]) for f in d["fills"]} == {("Q4FY26", "revenue", 1), ("Q4FY26", "pat", 1)}


def test_a_half_year_total_checks_two_filled_quarters_together():
    page = page_of("jyothylab_standalone")
    q = page["quarters"]
    dossier = dossier_like(page, "STANDALONE", {"Q1FY26", "Q2FY26"},
                           extra=[fig("pat", "H1FY26", q["Q1FY26"]["pat"] + q["Q2FY26"]["pat"] + 0.4, "STANDALONE")])
    assert {(f["period"], f["metric"]) for f in decide(dossier, page)["fills"]} >= {("Q1FY26", "pat"), ("Q2FY26", "pat")}
    dossier["financial_metrics"][-1]["value"] += 30
    d = decide(dossier, page)
    assert {k for k, v in reasons(d).items() if v == "sum check"} == {("Q1FY26", "pat"), ("Q2FY26", "pat")}


# --- the run --------------------------------------------------------------------------------------------------------

class Sink:
    def __init__(self, dossiers, companies=None):
        self.dossiers, self.kv, self.companies = dossiers, {}, companies or {}
        self.puts = 0

    def get_dossier(self, scrip):
        d = self.dossiers.get(scrip)
        return json.loads(json.dumps(d)) if d else None

    def put_dossier(self, scrip, dossier):
        self.dossiers[scrip] = dossier
        self.puts += 1

    def kv_get(self, key):
        return self.kv.get(key)

    def kv_set(self, key, value, now):
        self.kv[key] = value

    def company(self, scrip):
        return self.companies.get(scrip)


def transport(pages, seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("user-agent"), request.headers.get("cookie")))
        status, body = pages.get(str(request.url), (404, ""))
        return httpx.Response(status, text=body)
    return httpx.MockTransport(handler)


def setup_run():
    jy = page_of("jyothylab_standalone")
    body = (FIXTURES / "screener_jyothylab_standalone.html").read_text(encoding="utf-8")
    sink = Sink({"1": dossier_like(jy, "STANDALONE", {"Q4FY26"}, ), "2": dossier_like(jy, "STANDALONE", set()),
                 "3": dossier_like(jy, "STANDALONE", {"Q4FY26"})})
    report = mg.survey(sink, ["1", "2", "3"], TODAY)
    pages = {"https://www.screener.in/company/JYOTHYLAB/": (200, body), "https://www.screener.in/company/OTHER/": (200, body)}
    return sink, report, {"1": "JYOTHYLAB", "2": "NOGAP", "3": "OTHER"}, pages


def test_a_dry_run_asks_gap_companies_only_slowly_and_writes_nothing():
    sink, report, symbols, pages = setup_run()
    seen, naps = [], []
    clock = iter(range(0, 1000, 1))
    with sf.ScreenerClient(transport=transport(pages, seen), sleep=naps.append, clock=lambda: next(clock)) as client:
        out = sf.run(sink, report, symbols, client)
    assert [u for u, _, _ in seen] == ["https://www.screener.in/company/JYOTHYLAB/", "https://www.screener.in/company/OTHER/"]
    assert all("Mozilla/5.0" in ua and cookie is None for _, ua, cookie in seen)
    assert out["requests_made"] == 2 and out["companies_with_gaps"] == 2 and out["companies_with_fills"] == 2
    assert out["fillable"] == {"revenue": 2, "pat": 2} and out["written"] == 0 and sink.puts == 0
    assert all(n >= 0 for n in naps) and len(naps) == 1 and max(naps) <= sf.PAUSE_SECONDS   # paced between the two calls
    assert "screener:JYOTHYLAB:Q4FY26:STANDALONE" in sf.to_csv(out) and sf.CSV_HEADER in sf.to_csv(out)
    assert "dry run" in sf.render(out)


def test_requests_are_at_least_three_seconds_apart():
    seen, naps, now = [], [], [0.0]
    with sf.ScreenerClient(transport=transport({}, seen), sleep=lambda s: (naps.append(s), now.__setitem__(0, now[0] + s)),
                           clock=lambda: now[0]) as client:
        for _ in range(3):
            client.get("https://www.screener.in/company/X/")
    assert sf.PAUSE_SECONDS >= 3 and len(naps) == 2 and all(n >= 3 for n in naps)


def test_apply_writes_labelled_figures_and_a_second_run_skips_the_company():
    sink, report, symbols, pages = setup_run()
    seen = []
    with sf.ScreenerClient(transport=transport(pages, seen), sleep=lambda s: None) as client:
        out = sf.run(sink, report, symbols, client, apply=True)
        again = sf.run(sink, report, symbols, client, apply=True)
    assert out["written"] == 4 and sink.puts == 2 and len(seen) == 2
    stored = sink.dossiers["1"][SCREENER_KEY]
    assert {(e["metric"], e["period"], e["value"]) for e in stored} == {("revenue", "Q4FY26", 717.0), ("pat", "Q4FY26", 68.0)}
    one = stored[0]
    assert one["lab"]["by"] == "screener" and one["lab"]["basis"] == "STANDALONE" and one["source_news_id"].startswith("screener:JYOTHYLAB:Q4FY26")
    assert all(not str(m["source_news_id"]).startswith("screener:") for m in sink.dossiers["1"]["financial_metrics"])
    assert again["companies_skipped_tried"] == 2 and again["requests_made"] == 0 and len(seen) == 2
    with sf.ScreenerClient(transport=transport(pages, seen), sleep=lambda s: None) as client:
        assert sf.run(sink, report, symbols, client, restart=True)["requests_made"] == 2   # a dry run keeps its own list


def test_shards_split_the_gap_companies_and_the_time_budget_stops_the_run():
    sink, report, symbols, pages = setup_run()
    with sf.ScreenerClient(transport=transport(pages, []), sleep=lambda s: None) as client:
        out = sf.run(sink, report, symbols, client, shard=(0, 2))
        assert out["companies_with_gaps"] == 1 and out["requests_made"] == 1
        ticks = iter([0, 0, 99999])
        stopped = sf.run(sink, report, symbols, client, restart=True, time_budget=10, clock=lambda: next(ticks))
    assert stopped["more"] and stopped["requests_made"] == 1


def test_screener_refusing_stops_the_run():
    sink, report, symbols, pages = setup_run()
    refuse = {"https://www.screener.in/company/JYOTHYLAB/": (429, "")}
    with sf.ScreenerClient(transport=transport(refuse, []), sleep=lambda s: None) as client, pytest.raises(sf.ScreenerRefused):
        sf.run(sink, report, symbols, client)
    assert sink.kv_get(sf.DRY_TRIED_KEY) is None   # the refused company is not marked tried


def test_a_missing_page_is_a_page_error_not_a_fill():
    sink, report, symbols, _ = setup_run()
    with sf.ScreenerClient(transport=transport({}, []), sleep=lambda s: None) as client:
        out = sf.run(sink, report, symbols, client)
    assert out["companies_failed"] == 2 and out["rows"] == [] and out["skipped"]["page error"] > 0


def test_shard_option_allows_two_runners_at_most():
    from bse_intel import cli

    for bad in ("0/3", "2/2", "x"):
        assert cli.cmd_screener_fill(SimpleNamespace(shard=bad), None, None) == 2


def test_estimate_counts_gap_companies_with_a_basis():
    sink, report, _, _ = setup_run()
    assert sf.estimate(report) == {"requests": 2, "seconds": 6}
    assert sf.estimate(report, shards=2)["seconds"] == 3


# --- the readers ----------------------------------------------------------------------------------------------------

def filled_memory():
    """Q1FY27 from its results file, the year-ago quarter Q1FY26 only from screener."""
    d = {"financial_metrics": [{**fig("revenue", "Q1FY27", 120.0), "source_news_id": "n2", "as_of": "2026-09-01T00:00:00+05:30"},
                               {**fig("pat", "Q1FY27", 12.0), "source_news_id": "n2", "as_of": "2026-09-01T00:00:00+05:30"}],
         "balance_sheet": []}
    put_screener(d, [{"metric": "revenue", "period": "Q1FY26", "value": 100.0, "basis": "CONSOLIDATED"},
                     {"metric": "pat", "period": "Q1FY26", "value": 10.0, "basis": "CONSOLIDATED"}], "DEMO",
                 "2026-10-01T00:00:00+05:30")
    return d


def test_screener_figures_are_invisible_to_readers_unless_the_switch_is_on(monkeypatch):
    d = filled_memory()
    before = json.dumps(d, sort_keys=True)
    monkeypatch.delenv("MEMORY_SCREENER", raising=False)
    assert with_screener(d) is d
    assert "prev_year" not in results_snapshot(d, "n2")["revenue"]
    assert {m["period"] for m in dossier_as_of(d, "2026-12-01T00:00:00+05:30")["financial_metrics"]} == {"Q1FY27"}
    assert view_as_of(d, "2026-12-01T00:00:00+05:30")["metrics"]["revenue"] == ["Q1FY27: 120 INR_CR"]
    monkeypatch.setenv("MEMORY_SCREENER", "1")
    snap = results_snapshot(d, "n2")
    assert snap["revenue"]["prev_year"] == 100.0 and snap["revenue"]["yoy_pct"] == 20.0 and snap["pat"]["prev_year"] == 10.0
    assert {m["period"] for m in dossier_as_of(d, "2026-12-01T00:00:00+05:30")["financial_metrics"]} == {"Q1FY27", "Q1FY26"}
    assert len(view_as_of(d, "2026-12-01T00:00:00+05:30")["metrics"]["revenue"]) == 2
    # known since the fill: a filing from before it does not see them even with the switch on
    assert {m["period"] for m in dossier_as_of(d, "2026-09-15T00:00:00+05:30")["financial_metrics"]} == {"Q1FY27"}
    assert json.dumps(d, sort_keys=True) == before   # a read never changes the stored memory


def test_the_switch_never_lets_a_screener_figure_replace_a_file_one(monkeypatch):
    d = filled_memory()
    d[SCREENER_KEY].append({**d[SCREENER_KEY][0], "period": "Q1FY27", "value": 999.0})
    monkeypatch.setenv("MEMORY_SCREENER", "1")
    seen = {(m["metric"], m["period"]): m["value"] for m in with_screener(d)["financial_metrics"]}
    assert seen[("revenue", "Q1FY27")] == 120.0


def test_memory_gaps_does_not_count_a_screener_figure_as_an_exchange_file():
    d = filled_memory()
    assert mg.check(d, TODAY)["missing"] != []   # the fill is not the exchange's file: the gap stays a gap


def test_the_labelling_job_knows_the_screener_label():
    from bse_intel import memory_labels

    d = filled_memory()
    changed, new, had = memory_labels.Labeller().run(d)
    assert had["screener_fill"] == {"screener": 2} and "screener" in memory_labels.LABELS
    assert [e["lab"]["by"] for e in d[SCREENER_KEY]] == ["screener", "screener"]
