"""F167: restated figures. A later results file restates an earlier quarter in its comparative column; memory keeps the
first-filed figure and the restated one, the company page reads the latest, a card's view names the restatement only with
MEMORY_RESTATED."""
import pytest

from bse_intel import restated_report
from bse_intel import seed as seed_mod
from bse_intel import xbrl
from bse_intel.dossier import first_filed_value, is_comparative, latest_value, view_as_of
from bse_intel.models import FinancialMetric

from test_f166 import _Sink
from test_xbrl import results_xml

CUTOFF = "2026-12-01T00:00:00+05:30"


def _first_file():
    """The Q2FY26 file as filed in October 2025: revenue 80.0 (the Q2FY27 file's comparative column says 90.91)."""
    metrics = [FinancialMetric(metric="revenue", period="Q2FY26", value=80.0, unit="INR_CR", by="file", file_basis="CONSOLIDATED"),
               FinancialMetric(metric="pat", period="Q2FY26", value=9.0, unit="INR_CR", by="file", file_basis="CONSOLIDATED")]
    return xbrl.XbrlResult("RESULTS", "CONSOLIDATED", "Q2FY26", metrics)


def _memory(first=True):
    sink = _Sink()
    stats = seed_mod.SeedStats()
    if first:
        seed_mod._write_results(sink, "500001", "X", None, "Q2FY26", "2025-10-20", "http://x/a.xml", _first_file(), stats)
    seed_mod._write_results(sink, "500001", "X", None, "Q2FY27", "2026-10-20", "http://x/b.xml", xbrl.parse(results_xml()), stats)
    return sink.d["500001"]


def _by(dossier):
    return {(m["metric"], m["period"]): m for m in dossier["financial_metrics"]}


def test_memory_keeps_both_the_first_filed_and_the_restated_figure():
    entry = _by(_memory())[("revenue", "Q2FY26")]
    assert entry["value"] == 90.91 and entry["restated"] is True and entry["first_filed"] == 80.0
    assert entry["restated_in"] == "Q2FY27"
    first, last = entry["sources"][0], entry["sources"][-1]
    assert first["value"] == 80.0 and "restated_from" not in first
    assert last["value"] == 90.91 and last["restated_from"] == "Q2FY27" and last["lab"]["by"] == "file"
    assert first["news_id"] != last["news_id"] and entry["source_news_id"] == first["news_id"]
    assert latest_value(entry) == 90.91 and first_filed_value(entry) == 80.0


def test_a_figure_the_later_file_leaves_unchanged_is_not_flagged_restated():
    entry = _by(_memory())[("pat", "Q2FY26")]
    assert entry["value"] == 9.0 and "restated" not in entry and "first_filed" not in entry
    assert first_filed_value(entry) == latest_value(entry) == 9.0


def test_the_files_own_period_is_not_a_comparative():
    by = _by(_memory())
    assert "restated_from" not in by[("revenue", "Q2FY27")] and "restated_from" not in by[("revenue", "H1FY27")]
    assert is_comparative("Q2FY26", "Q2FY27") and is_comparative("Q1FY27", "Q2FY27") and is_comparative("FY26", "Q2FY27")
    assert not is_comparative("H1FY27", "Q2FY27") and not is_comparative("Q2FY27", "Q2FY27")


def test_a_comparative_alone_is_not_called_first_filed():
    # the Q2FY26 file was never read: the later file's column is all memory has, and nothing is called restated
    entry = _by(_memory(first=False))[("revenue", "Q2FY26")]
    assert entry["value"] == 90.91 and entry["restated_from"] == "Q2FY27" and "restated" not in entry


def test_the_view_is_unchanged_with_the_switch_off_and_names_the_restatement_with_it_on(monkeypatch):
    dossier = _memory()
    monkeypatch.delenv("MEMORY_RESTATED", raising=False)
    off = view_as_of(dossier, CUTOFF)
    line = next(x for x in off["metrics"]["revenue"] if x.startswith("Q2FY26"))
    assert "90.91" in line and "restated 2026-10-20, first reported 80" in line   # the existing note
    monkeypatch.setenv("MEMORY_RESTATED", "1")
    on = view_as_of(dossier, CUTOFF)
    line = next(x for x in on["metrics"]["revenue"] if x.startswith("Q2FY26"))
    assert "90.91" in line and "restated in Q2FY27's filing" in line and "first filed 80" in line
    assert [x for x in off["metrics"]["pat"]] == [x for x in on["metrics"]["pat"]]


def test_a_view_before_the_later_filing_still_shows_the_first_filed_figure():
    view = view_as_of(_memory(), "2026-06-01T00:00:00+05:30")
    assert next(x for x in view["metrics"]["revenue"] if x.startswith("Q2FY26")).startswith("Q2FY26: 80 ")


@pytest.mark.parametrize("first,latest,flag", [(80.0, 90.91, True), (200.0, 200.9, False), (200.0, 202.0, True), (5.0, 5.004, False)])
def test_rounding_is_not_a_restatement(first, latest, flag):
    from bse_intel.dossier import restated_differs
    assert restated_differs(first, latest) is flag


def test_restated_report_counts_by_size_and_the_yoy_base():
    dossier = _memory()
    report = restated_report.survey(type("S", (), {"get_dossier": staticmethod(lambda k: dossier)}), ["500001"], workers=1)
    assert report["restated_figures"] == 1 and report["companies_with_restated"] == 1
    assert report["by_size"]["10-20%".replace("10-20", "5-20")] == 1   # +13.6%
    row = report["rows"][0]
    assert (row["metric"], row["period"], row["first_filed"], row["restated"]) == ("revenue", "Q2FY26", 80.0, 90.91)
    assert "restated figures in memory: 1 of" in restated_report.render(report)
