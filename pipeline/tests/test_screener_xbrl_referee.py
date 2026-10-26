"""The NSE-XBRL referee of the screener cross-check: verdicts, the period finding, files and lists fetched once, the cap.
No network: a fake NSE client serves fake results lists and fake XBRL."""

from pathlib import Path

import pytest

from bse_intel import screener_xbrl_referee as sx
from bse_intel import xbrl
from bse_intel.models import FinancialMetric
from bse_intel.nse import ResultsFiling, SourceBlockedError

FIXTURES = Path(__file__).parent / "fixtures"
ENDS = {"Q1FY26": "2025-06-30", "Q2FY26": "2025-09-30", "Q3FY26": "2025-12-31", "Q4FY26": "2026-03-31",
        "Q1FY27": "2026-06-30", "Q2FY24": "2023-09-30"}


def listing(period, consolidated=True, filed="2026-01-01", legacy=False):
    return ResultsFiling(period="Quarterly", consolidated=consolidated, audited="Audited", filed_at=filed,
                         xbrl_url=f"https://nsearchives.nseindia.com/x/{period}_{'c' if consolidated else 's'}.xml",
                         is_bank=False, period_end=ENDS[period], legacy=legacy)


def result(values: dict, basis="CONSOLIDATED", template="INDAS"):
    """values: {(metric, period): value}."""
    return xbrl.XbrlResult("RESULTS", basis, None, [FinancialMetric(metric=m, period=p, value=v) for (m, p), v in values.items()],
                           template=template)


class FakeNse:
    def __init__(self, lists, files):
        self.lists, self.files = lists, files     # symbol -> rows; url name -> bytes marker
        self.list_calls, self.download_calls = [], []

    def financial_results(self, symbol):
        self.list_calls.append(symbol)
        rows = self.lists[symbol]
        if isinstance(rows, Exception):
            raise rows
        return rows

    def download(self, url, max_bytes=0):
        name = url.rsplit("/", 1)[-1]
        self.download_calls.append(name)
        body = self.files.get(name)
        if isinstance(body, Exception):
            raise body
        return body


@pytest.fixture
def parsed(monkeypatch):
    """xbrl.parse reads a marker string as a prepared result."""
    table = {}
    monkeypatch.setattr(xbrl, "parse", lambda data: table.get(data))
    return table


def row(period, metric, ours, theirs, cls="mismatch", scrip="1", symbol="DEMO", basis="CONSOLIDATED", shifted=()):
    return {"scrip": scrip, "symbol": symbol, "basis": basis, "period": period, "metric": metric, "class": cls,
            "memory_value": ours, "screener_value": theirs, "shifted": list(shifted), "note": ""}


# --- the file choice and the verdicts -------------------------------------------------------------------------------

def test_file_periods_own_next_and_a_year_on():
    assert sx.file_periods("Q2FY26") == ["Q2FY26", "Q3FY26", "Q2FY27"]
    assert sx.file_periods("Q4FY25") == ["Q4FY25", "Q1FY26", "Q4FY26"]
    assert sx.file_periods("FY26") == ["Q4FY26", "Q4FY27"]


def test_each_verdict(parsed):
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0, ("pat", "Q2FY26"): 100.0, ("eps", "Q2FY26"): 5.0})
    nse = FakeNse({"DEMO": [listing("Q2FY26")]}, {"Q2FY26_c.xml": b"q2"})
    rows = [row("Q2FY26", "revenue", 1000.0, 1100.0),                 # ours is the official figure
            row("Q2FY26", "pat", 90.0, 100.2),                        # screener's rounded figure is the official one
            row("Q2FY26", "eps", 4.0, 6.0),                           # neither
            row("Q2FY26", "revenue", 1000.05, 1000.4, cls="scale")]    # both are within their tolerances
    out = sx.run(nse, rows)
    assert [r["verdict"] for r in out["rows"]] == ["ours_matches_official", "screener_matches_official", "neither", "both_match"]
    assert out["rows"][0]["official_value"] == 1000.0 and out["rows"][0]["official_from"] == "own"
    assert out["rows"][0]["official_file"] == "Q2FY26_c.xml"
    assert out["by_class_metric"]["mismatch/revenue"] == {"ours_matches_official": 1}
    assert out["by_metric"]["revenue"] == {"ours_matches_official": 1, "both_match": 1}


def test_only_disagreeing_pairs_are_refereed(parsed):
    nse = FakeNse({"DEMO": []}, {})
    rows = [row("Q2FY26", "revenue", 1, 1, cls="match"), row("Q2FY26", "revenue", 1, 1, cls="naming"),
            {"scrip": "1", "symbol": "DEMO", "period": "Q1FY26", "metric": "", "class": "screener_only"},
            {"scrip": "1", "symbol": "DEMO", "period": "Q1FY26", "metric": "pat", "class": "memory_period_suspect"}]
    assert sx.run(nse, rows)["pairs"] == 0 and nse.list_calls == []


def test_falls_back_to_the_next_periods_file_and_says_so(parsed):
    parsed[b"q3"] = result({("revenue", "Q3FY26"): 1200.0, ("revenue", "Q2FY26"): 1000.0})   # a comparative column
    nse = FakeNse({"DEMO": [listing("Q3FY26")]}, {"Q3FY26_c.xml": b"q3"})
    out = sx.run(nse, [row("Q2FY26", "revenue", 1000.0, 1100.0)])
    r = out["rows"][0]
    assert r["verdict"] == "ours_matches_official" and r["official_from"] == "next:Q3FY26" and r["official_file"] == "Q3FY26_c.xml"
    assert out["official_from"] == {"next": 1}


def test_a_year_is_read_from_the_march_file(parsed):
    parsed[b"q4"] = result({("pat", "Q4FY26"): 40.0, ("pat", "FY26"): 160.0})
    nse = FakeNse({"DEMO": [listing("Q4FY26")]}, {"Q4FY26_c.xml": b"q4"})
    out = sx.run(nse, [row("FY26", "pat", 160.0, 150.0)])
    assert out["rows"][0]["verdict"] == "ours_matches_official" and out["rows"][0]["official_file"] == "Q4FY26_c.xml"


def test_a_lenders_revenue_is_its_revenue_from_operations_else_interest_earned(parsed):
    # the cross-check's line: revenue from operations (an NBFC), interest earned only where the file has no revenue (a bank)
    parsed[b"q2"] = result({("interest_earned", "Q2FY26"): 21936.39, ("revenue", "Q2FY26"): 24546.37}, template="NBFC")
    nse = FakeNse({"DEMO": [listing("Q2FY26")]}, {"Q2FY26_c.xml": b"q2"})
    out = sx.run(nse, [row("Q2FY26", "revenue", 24546.37, 24000.0, cls="lender_definition")])
    assert out["rows"][0]["verdict"] == "ours_matches_official" and out["rows"][0]["official_value"] == 24546.37
    parsed[b"q2"] = result({("interest_earned", "Q2FY26"): 21936.39}, template="BANKING")   # a bank: no revenue line
    out = sx.run(FakeNse({"DEMO": [listing("Q2FY26")]}, {"Q2FY26_c.xml": b"q2"}),
                 [row("Q2FY26", "revenue", 21936.39, 24000.0, cls="lender_definition")])
    assert out["rows"][0]["official_value"] == 21936.39


def test_the_basis_is_memorys(parsed):
    parsed[b"s"] = result({("revenue", "Q2FY26"): 900.0}, basis="STANDALONE")
    parsed[b"c"] = result({("revenue", "Q2FY26"): 1000.0})
    nse = FakeNse({"DEMO": [listing("Q2FY26", consolidated=False), listing("Q2FY26", consolidated=True)]},
                  {"Q2FY26_s.xml": b"s", "Q2FY26_c.xml": b"c"})
    cons = sx.run(nse, [row("Q2FY26", "revenue", 1000.0, 950.0)])["rows"][0]
    alone = sx.run(nse, [row("Q2FY26", "revenue", 900.0, 950.0, basis="STANDALONE")])["rows"][0]
    assert cons["official_value"] == 1000.0 and alone["official_value"] == 900.0


def test_the_later_filing_of_a_period_wins(parsed):
    parsed[b"old"], parsed[b"new"] = result({("revenue", "Q2FY26"): 1.0}), result({("revenue", "Q2FY26"): 1000.0})
    first = listing("Q2FY26", filed="2025-11-01")
    revised = ResultsFiling(**{**first.__dict__, "filed_at": "2025-12-01", "xbrl_url": "https://x/revised.xml"})
    nse = FakeNse({"DEMO": [first, revised]}, {"Q2FY26_c.xml": b"old", "revised.xml": b"new"})
    assert sx.run(nse, [row("Q2FY26", "revenue", 1000.0, 1100.0)])["rows"][0]["official_value"] == 1000.0


# --- no_file, with the reason ---------------------------------------------------------------------------------------

def test_no_file_says_why(parsed):
    parsed[b"other"] = result({("pat", "Q2FY26"): 5.0})
    nse = FakeNse({"NOLIST": [], "BROKEN": RuntimeError("boom"), "BADFILE": [listing("Q2FY26")],
                   "NOMETRIC": [listing("Q2FY26")], "GONE": [listing("Q2FY26")], "SOLO": [listing("Q2FY26", consolidated=False)]},
                  {"Q2FY26_c.xml": None, "Q2FY26_s.xml": b"x"})
    rows = [row("Q2FY26", "revenue", 1.0, 2.0, symbol="NOLIST", scrip="1"),
            row("Q2FY26", "revenue", 1.0, 2.0, symbol="BROKEN", scrip="2"),
            row("Q2FY26", "revenue", 1.0, 2.0, symbol="GONE", scrip="3"),
            row("Q2FY26", "revenue", 1.0, 2.0, symbol="SOLO", scrip="4")]
    out = sx.run(nse, rows)
    reasons = {r["symbol"]: r["reason"] for r in out["rows"]}
    assert {r["verdict"] for r in out["rows"]} == {"no_file"}
    assert "lists no consolidated results file for Q2FY26" in reasons["NOLIST"]
    assert "results list unavailable (RuntimeError)" in reasons["BROKEN"]
    assert "NSE served no XML" in reasons["GONE"]
    assert "lists no consolidated results file" in reasons["SOLO"]    # only a standalone file is listed
    assert sum(out["no_file_reasons"].values()) == 4


def test_a_file_without_the_metric_is_no_file(parsed):
    parsed[b"q2"] = result({("pat", "Q2FY26"): 5.0})
    nse = FakeNse({"DEMO": [listing("Q2FY26")]}, {"Q2FY26_c.xml": b"q2"})
    r = sx.run(nse, [row("Q2FY26", "revenue", 1.0, 2.0)])["rows"][0]
    assert r["verdict"] == "no_file" and "Q2FY26 revenue not in Q2FY26_c.xml" in r["reason"]


def test_a_file_on_the_other_basis_is_refused(parsed):
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0}, basis="STANDALONE")
    nse = FakeNse({"DEMO": [listing("Q2FY26")]}, {"Q2FY26_c.xml": b"q2"})
    r = sx.run(nse, [row("Q2FY26", "revenue", 1000.0, 900.0)])["rows"][0]
    assert r["verdict"] == "no_file" and "memory's basis is consolidated" in r["reason"]


# --- wrong_quarter ---------------------------------------------------------------------------------------------------

def test_wrong_quarter_with_the_right_period_in_memory(parsed):
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0})
    parsed[b"q3"] = result({("revenue", "Q3FY26"): 1200.0})
    nse = FakeNse({"DEMO": [listing("Q2FY26"), listing("Q3FY26")]}, {"Q2FY26_c.xml": b"q2", "Q3FY26_c.xml": b"q3"})
    r = sx.run(nse, [row("Q2FY26", "revenue", 1000.0, 1200.0, cls="wrong_quarter", shifted=["Q3FY26"])])["rows"][0]
    assert r["verdict"] == "ours_matches_official" and r["period_finding"] == "own_period_right"


def test_wrong_quarter_saved_under_the_wrong_quarter(parsed):
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0})
    parsed[b"q3"] = result({("revenue", "Q3FY26"): 1200.0})
    nse = FakeNse({"DEMO": [listing("Q2FY26"), listing("Q3FY26")]}, {"Q2FY26_c.xml": b"q2", "Q3FY26_c.xml": b"q3"})
    out = sx.run(nse, [row("Q2FY26", "revenue", 1200.0, 1000.0, cls="wrong_quarter", shifted=["Q3FY26"])])
    r = out["rows"][0]
    assert r["verdict"] == "screener_matches_official" and r["period_finding"] == "saved_under_wrong_quarter:Q3FY26"
    assert out["wrong_quarter_findings"] == {"saved_under_wrong_quarter": 1}


def test_wrong_quarter_matching_neither_period_or_unknown(parsed):
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0})
    parsed[b"q3"] = result({("revenue", "Q3FY26"): 1200.0})
    nse = FakeNse({"DEMO": [listing("Q2FY26"), listing("Q3FY26")], "NONE": []},
                  {"Q2FY26_c.xml": b"q2", "Q3FY26_c.xml": b"q3"})
    out = sx.run(nse, [row("Q2FY26", "revenue", 777.0, 1200.0, cls="wrong_quarter", shifted=["Q3FY26"]),
                       row("Q2FY26", "revenue", 777.0, 1200.0, cls="wrong_quarter", shifted=["Q3FY26"], symbol="NONE", scrip="2")])
    assert [r["period_finding"] for r in out["rows"]] == ["neither_period", "unknown"]


# --- once per run, the cap, a refusal --------------------------------------------------------------------------------

def test_each_list_and_file_is_fetched_once_per_company(parsed):
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0, ("pat", "Q2FY26"): 100.0, ("eps", "Q2FY26"): 5.0})
    nse = FakeNse({"DEMO": [listing("Q2FY26")], "TWO": [listing("Q2FY26")]}, {"Q2FY26_c.xml": b"q2"})
    rows = [row("Q2FY26", m, 1.0, 2.0) for m in ("revenue", "pat", "eps")]
    rows += [row("Q2FY26", "revenue", 1.0, 2.0, symbol="TWO", scrip="2")]
    out = sx.run(nse, rows)
    assert nse.list_calls == ["DEMO", "TWO"]
    assert nse.download_calls == ["Q2FY26_c.xml", "Q2FY26_c.xml"]     # one per company, not one per pair
    assert out["calls"] == {"results_lists": 2, "files": 2} and out["companies"] == 2


def test_a_missing_file_is_asked_for_once(parsed):
    nse = FakeNse({"DEMO": [listing("Q2FY26")]}, {"Q2FY26_c.xml": None})
    sx.run(nse, [row("Q2FY26", "revenue", 1.0, 2.0), row("Q2FY26", "pat", 1.0, 2.0)])
    assert nse.download_calls == ["Q2FY26_c.xml"]


def test_limit_finishes_the_company_it_is_in_and_leaves_the_rest_not_run(parsed):
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0})
    lists = {s: [listing("Q2FY26")] for s in ("A", "B", "C")}
    nse = FakeNse(lists, {"Q2FY26_c.xml": b"q2"})
    rows = [row("Q2FY26", "revenue", 1000.0, 1.0, symbol=s, scrip=s) for s in ("A", "B", "C")]
    rows.insert(1, row("Q1FY26", "revenue", 1.0, 2.0, symbol="A", scrip="A"))
    out = sx.run(nse, rows, limit=2)
    assert out["verdicts"].get("not_run") == 2 and nse.list_calls == ["A"]
    assert {r["reason"] for r in out["rows"] if r["verdict"] == "not_run"} == {"limit"}


def test_time_budget_stops_between_companies(parsed):
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0})
    nse = FakeNse({"A": [listing("Q2FY26")], "B": [listing("Q2FY26")]}, {"Q2FY26_c.xml": b"q2"})
    ticks = iter([0, 1, 100, 100, 100])
    out = sx.run(nse, [row("Q2FY26", "revenue", 1000.0, 1.0, symbol=s, scrip=s) for s in "AB"], time_budget=50,
                 clock=lambda: next(ticks))
    assert out["out_of_time"] and nse.list_calls == ["A"] and out["verdicts"]["not_run"] == 1


def test_a_refusal_stops_the_run(parsed):
    nse = FakeNse({"A": SourceBlockedError("NSE refused"), "B": []}, {})
    out = sx.run(nse, [row("Q2FY26", "revenue", 1.0, 2.0, symbol=s, scrip=s) for s in "AB"])
    assert out["blocked"] and out["verdicts"] == {"not_run": 2} and nse.list_calls == ["A"]


# --- a real file, and the outputs ------------------------------------------------------------------------------------

def test_a_real_xbrl_file_through_the_reader():
    data = (FIXTURES / "nse_old_titan_q2fy24.xml").read_bytes()
    nse = FakeNse({"TITAN": [listing("Q2FY24")]}, {"Q2FY24_c.xml": data})
    out = sx.run(nse, [row("Q2FY24", "revenue", 12529.0, 12000.0, symbol="TITAN"), row("Q2FY24", "pat", 915.7, 915.0, symbol="TITAN")])
    assert [r["official_value"] for r in out["rows"]] == [12529.0, 915.7]
    assert [r["verdict"] for r in out["rows"]] == ["ours_matches_official", "both_match"]


def test_csv_and_markdown(parsed):
    parsed[b"q2"] = result({("revenue", "Q2FY26"): 1000.0})
    nse = FakeNse({"DEMO": [listing("Q2FY26")], "NONE": []}, {"Q2FY26_c.xml": b"q2"})
    out = sx.run(nse, [row("Q2FY26", "revenue", 1000.0, 1100.0), row("Q2FY26", "revenue", 1.0, 2.0, cls="scale", symbol="NONE", scrip="2")])
    lines = sx.to_csv(out).splitlines()
    assert lines[0].split(",")[:6] == ["scrip", "symbol", "basis", "period", "metric", "class"]
    assert len(lines) == 3 and "ours_matches_official" in lines[1]
    md = sx.to_markdown(out, "2026-10-26")
    assert "Verdicts per class" in md and "| mismatch |" in md and "| scale |" in md and "Why no file" in md
    assert '"verdicts"' in sx.to_json(out) and "rows" not in sx.to_json(out).split('"verdicts"')[0]
    assert "ours_matches_official" in sx.render(out)
