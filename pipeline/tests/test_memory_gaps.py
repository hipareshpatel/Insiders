import threading
import time
from datetime import date

import pytest

from bse_intel import memory_gaps as mg
from bse_intel.nse import SourceBlockedError

TODAY = date(2026, 10, 25)   # Q1FY27's deadline (14 Aug) has passed, Q2FY27's (14 Nov) has not


def _fig(metric, period, scrip, basis="CONSOLIDATED", source="xbrl:res:"):
    return {"metric": metric, "period": period, "value": 10.0, "unit": "INR_CR", "basis": basis,
            "as_of": "2026-01-01", "source_news_id": f"{source}{scrip}:{period}"}


def _dossier(scrip, periods, basis="CONSOLIDATED", metrics=("revenue", "pat"), source="xbrl:res:"):
    return {"financial_metrics": [_fig(m, p, scrip, basis, source) for p in periods for m in metrics], "balance_sheet": []}


EIGHT = ["Q1FY27", "Q4FY26", "Q3FY26", "Q2FY26", "Q1FY26", "Q4FY25", "Q3FY25", "Q2FY25"]


class Sink:
    def __init__(self, dossiers):
        self.dossiers, self.kv = dossiers, {}

    def get_dossier(self, scrip):
        return self.dossiers.get(scrip)

    def kv_get(self, key):
        return self.kv.get(key)

    def kv_set(self, key, value, now):
        self.kv[key] = value


def test_deadlines_and_window():
    assert mg.latest_due_quarter(date(2026, 10, 25)) == "Q1FY27"
    assert mg.latest_due_quarter(date(2026, 11, 14)) == "Q1FY27"   # the deadline day itself has not passed
    assert mg.latest_due_quarter(date(2026, 11, 15)) == "Q2FY27"
    assert mg.latest_due_quarter(date(2027, 5, 29)) == "Q3FY27"    # Q4 has 60 days: 30 May
    assert mg.latest_due_quarter(date(2027, 5, 31)) == "Q4FY27"
    assert mg.window(TODAY) == EIGHT


def test_complete_company_has_no_gap():
    r = mg.check(_dossier("1", EIGHT + ["Q4FY24"]), TODAY)
    assert r["basis"] == "CONSOLIDATED" and r["missing"] == [] and not mg.has_gap(r)


def test_missing_latest_quarter_and_year_ago():
    r = mg.check(_dossier("1", EIGHT[1:4]), TODAY)   # Q1FY27 missing, Q1FY26 (year-ago) missing
    assert r["missing_latest"] and r["missing_year_ago"]
    assert r["missing"] == ["Q1FY27", "Q1FY26", "Q4FY25", "Q3FY25", "Q2FY25"]
    only_year_ago_missing = mg.check(_dossier("1", [p for p in EIGHT if p != "Q1FY26"]), TODAY)
    assert not only_year_ago_missing["missing_latest"] and only_year_ago_missing["missing_year_ago"]


def test_year_ago_outside_window_still_checked():
    r = mg.check(_dossier("1", [p for p in EIGHT if p != "Q1FY26"]), TODAY, quarters=2)   # window Q1FY27, Q4FY26; year-ago Q1FY26 is outside
    assert r["missing"] == [] and r["missing_year_ago"] and mg.has_gap(r)


def test_standalone_only_filer_uses_standalone_basis():
    r = mg.check(_dossier("1", EIGHT, basis="STANDALONE"), TODAY)
    assert r["basis"] == "STANDALONE" and r["missing"] == []


def test_consolidated_filer_standalone_figures_do_not_count():
    d = _dossier("1", EIGHT[:2])   # consolidated has two quarters only
    d["financial_metrics"] += _dossier("1", EIGHT[2:], basis="STANDALONE")["financial_metrics"]
    r = mg.check(d, TODAY)
    assert r["basis"] == "CONSOLIDATED" and r["missing"] == EIGHT[2:]


def test_card_written_figures_are_not_xbrl():
    r = mg.check(_dossier("1", EIGHT, source="news:"), TODAY)
    assert r["no_xbrl"] and len(r["missing"]) == 8


def test_partial_quarter_is_not_missing():
    d = _dossier("1", EIGHT[1:])
    d["financial_metrics"].append(_fig("revenue", "Q1FY27", "1"))
    r = mg.check(d, TODAY)
    assert r["missing"] == [] and r["partial"] == ["Q1FY27"]


def test_company_with_nothing_and_summary():
    sink = Sink({"A": _dossier("A", EIGHT), "B": _dossier("B", EIGHT[1:4]), "C": {"financial_metrics": []}})
    report = {"companies": {s: mg.check(sink.get_dossier(s), TODAY) for s in ("A", "B", "C", "D")}}
    s = mg.summarise(report["companies"])   # D has no dossier at all
    assert s == {"companies_checked": 4, "no_xbrl_results": 2, "missing_latest_quarter": 3,
                 "missing_year_ago_quarter": 3, "companies_with_gaps": 3, "missing_company_quarters": 5 + 8 + 8,
                 "partial_company_quarters": 0, "standalone_only_company_quarters": 0}
    assert [g["scrip"] for g in mg.gap_rows(report)] == ["B", "C", "D"]


def test_survey_and_csv():
    sink = Sink({"A": _dossier("A", EIGHT), "B": _dossier("B", EIGHT[1:])})
    report = mg.survey(sink, ["A", "B"], TODAY)
    assert report["summary"]["missing_company_quarters"] == 1
    assert mg.to_csv(report).splitlines() == ["scrip,basis,missing_quarters,missing_year_ago", "B,CONSOLIDATED,Q1FY27,false"]


def test_since_for_goes_back_before_the_oldest_gap():
    r = mg.check(_dossier("1", EIGHT[:7]), TODAY)   # Q2FY25 missing
    assert mg.since_for(r) < "2024-09-30" and mg.since_for(r) >= "2024-06-01"


def _report(sink, scrips):
    return mg.survey(sink, scrips, TODAY)


def test_fill_calls_seed_only_for_gap_companies_and_resumes():
    sink = Sink({"A": _dossier("A", EIGHT), "B": _dossier("B", EIGHT[1:]), "C": {}})
    report = _report(sink, ["A", "B", "C"])
    calls = []
    out = mg.fill(sink, report, lambda scrip, since: calls.append((scrip, since)), 1000)
    assert [c[0] for c in calls] == ["B", "C"] and out["attempted"] == ["B", "C"] and not out["more"]
    calls.clear()   # a second pass skips the companies already tried
    assert mg.fill(sink, report, lambda scrip, since: calls.append(scrip), 1000)["attempted"] == []
    assert calls == []
    mg.fill(sink, report, lambda scrip, since: calls.append(scrip), 1000, restart=True)
    assert calls == ["B", "C"]


def test_fill_failure_is_recorded_and_the_run_goes_on():
    sink = Sink({"B": _dossier("B", EIGHT[1:]), "C": {}})
    report = _report(sink, ["B", "C"])

    def seed(scrip, since):
        if scrip == "B":
            raise ValueError("bad file")

    out = mg.fill(sink, report, seed, 1000)
    assert out["attempted"] == ["B", "C"] and len(out["failed"]) == 1 and "bad file" in out["failed"][0]


def test_fill_stops_on_time_budget_and_on_refusal():
    sink = Sink({"B": _dossier("B", EIGHT[1:]), "C": {}})
    report = _report(sink, ["B", "C"])
    ticks = iter([0, 0, 5000])   # deadline at 1000: the second company starts after it
    out = mg.fill(sink, report, lambda s, since: None, 1000, clock=lambda: next(ticks))
    assert out["attempted"] == ["B"] and out["more"]

    def refuse(scrip, since):
        raise SourceBlockedError("403")

    with pytest.raises(SourceBlockedError):
        mg.fill(Sink({"B": {}}), _report(Sink({"B": {}}), ["B"]), refuse, 1000)


def test_fill_shard_takes_every_nth_gap_company():
    sink = Sink({s: {} for s in "BCDE"})
    report = _report(sink, list("BCDE"))
    calls = []
    mg.fill(sink, report, lambda s, since: calls.append(s), 1000, shard=(1, 2))
    assert calls == ["C", "E"]


class SlowSink(Sink):
    """Reads that take time and finish out of order; counts how many run at once."""

    def __init__(self, dossiers):
        super().__init__(dossiers)
        self.lock, self.running, self.peak = threading.Lock(), 0, 0

    def get_dossier(self, scrip):
        with self.lock:
            self.running += 1
            self.peak = max(self.peak, self.running)
        time.sleep(0.05 if scrip in "ABC" else 0.001)
        with self.lock:
            self.running -= 1
        return self.dossiers.get(scrip)


def test_survey_reads_in_parallel_with_identical_ordered_output():
    dossiers = {s: _dossier(s, EIGHT if s in "ACE" else EIGHT[:3]) for s in "ABCDEFGH"}
    scrips = list("ABCDEFGH")
    serial = mg.survey(Sink(dossiers), scrips, TODAY, workers=1)
    sink = SlowSink(dossiers)
    parallel = mg.survey(sink, scrips, TODAY)
    assert parallel == serial
    assert list(parallel["companies"]) == scrips
    assert mg.to_csv(parallel) == mg.to_csv(serial)
    assert 1 < sink.peak <= mg.READ_WORKERS


def test_survey_read_error_propagates():
    class Broken(Sink):
        def get_dossier(self, scrip):
            raise RuntimeError("sink down")

    with pytest.raises(RuntimeError):
        mg.survey(Broken({}), ["A", "B"], TODAY)


def test_a_company_that_stopped_filing_consolidated_is_checked_on_its_newer_basis():
    """Bharat Wire Ropes (gaps fill, 25 Oct 2026): consolidated FY23-FY24, standalone since. One old consolidated quarter
    kept it on a basis its newer quarters are not on, so all eight read as missing and no fill could close them."""
    d = _dossier("1", ["Q2FY24", "Q3FY24", "Q4FY24"])
    d["financial_metrics"] += _dossier("1", EIGHT, basis="STANDALONE")["financial_metrics"]
    r = mg.check(d, TODAY)
    assert r["basis"] == "STANDALONE" and r["missing"] == [] and not mg.has_gap(r)


def test_both_bases_to_the_same_newest_quarter_are_checked_consolidated():
    d = _dossier("1", EIGHT[:2])
    d["financial_metrics"] += _dossier("1", EIGHT[:2], basis="STANDALONE")["financial_metrics"]
    assert mg.check(d, TODAY)["basis"] == "CONSOLIDATED"


# --- the standalone rule (F162, TODO 49, 26 Oct 2026) ---------------------------------------------------------------

def test_jyothy_like_company_standalone_after_its_last_subsidiary_has_no_gap():
    """Jyothy Labs sold its only subsidiary on 25 Mar 2025: consolidated to Q4FY25, standalone only from Q1FY26. The
    standalone quarters are the company's figures; the older consolidated ones stay filled."""
    d = _dossier("1", EIGHT[:5], basis="STANDALONE")                      # Q1FY27 .. Q1FY26
    d["financial_metrics"] += _dossier("1", EIGHT[5:])["financial_metrics"]   # Q4FY25 .. Q2FY25 consolidated
    d["standalone_only"] = EIGHT[:5][::-1]
    r = mg.check(d, TODAY)
    assert r["basis"] == "STANDALONE" and r["missing"] == [] and not mg.has_gap(r)


def test_abb_like_company_standalone_then_consolidated_counts_the_standalone_quarters_as_filled():
    """ABB India: standalone until its first subsidiary (Q2FY26 on), consolidated after."""
    d = _dossier("1", EIGHT[:3])                                           # Q1FY27, Q4FY26, Q3FY26 consolidated
    d["financial_metrics"] += _dossier("1", EIGHT[3:], basis="STANDALONE")["financial_metrics"]
    r = mg.check(d, TODAY)
    assert r["basis"] == "CONSOLIDATED" and r["missing"] == EIGHT[3:]       # not listed: still a gap (as before)
    d["standalone_only"] = EIGHT[3:]
    r = mg.check(d, TODAY)
    assert r["missing"] == [] and r["standalone_only"] == EIGHT[3:] and not mg.has_gap(r)
    assert mg.summarise({"1": r})["standalone_only_company_quarters"] == 5


def test_a_listed_quarter_needs_its_standalone_figures():
    d = _dossier("1", EIGHT[:3])
    d["standalone_only"] = EIGHT[3:]
    assert mg.check(d, TODAY)["missing"] == EIGHT[3:]
