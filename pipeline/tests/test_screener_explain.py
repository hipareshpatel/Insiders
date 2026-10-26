"""screener-explain (screener_explain.py): a bonus or a later file explains a difference, the rest is `unexplained`. No network:
a fake NSE client, a fake sink with dossiers."""

import pytest

from bse_intel import pdf_referee as pr
from bse_intel import screener_explain as se
from bse_intel import xbrl
from bse_intel.models import FinancialMetric
from bse_intel.nse import ResultsFiling, SourceBlockedError

ENDS = {"Q2FY26": "2025-09-30", "Q2FY27": "2026-09-30", "Q4FY26": "2026-03-31", "Q4FY27": "2027-03-31"}


def listing(period):
    return ResultsFiling(period="Quarterly", consolidated=True, audited="Audited", filed_at="2026-10-01",
                         xbrl_url=f"https://nsearchives.nseindia.com/x/{period}.xml", is_bank=False, period_end=ENDS[period],
                         legacy=False)


def result(values):
    return xbrl.XbrlResult("RESULTS", "CONSOLIDATED", None,
                           [FinancialMetric(metric=m, period=p, value=v) for (m, p), v in values.items()], template="INDAS")


class FakeNse:
    def __init__(self, lists, files):
        self.lists, self.files, self.list_calls, self.downloads = lists, files, [], []

    def financial_results(self, symbol):
        self.list_calls.append(symbol)
        rows = self.lists[symbol]
        if isinstance(rows, Exception):
            raise rows
        return rows

    def download(self, url, max_bytes=0):
        name = url.rsplit("/", 1)[-1]
        self.downloads.append(name)
        return self.files.get(name)


class FakeSink:
    def __init__(self, dossiers):
        self.dossiers = dossiers

    def get_dossier(self, scrip):
        return self.dossiers.get(scrip)


@pytest.fixture
def parsed(monkeypatch):
    table = {}
    monkeypatch.setattr(xbrl, "parse", lambda data: table.get(data))
    return table


def row(period, metric, ours, theirs, verdict="ours_matches_official", scrip="1", symbol="DEMO"):
    return {"scrip": scrip, "symbol": symbol, "basis": "CONSOLIDATED", "period": period, "metric": metric, "class": "mismatch",
            "memory_value": ours, "screener_value": theirs, "official_value": ours, "verdict": verdict}


BONUS = {"kind": "BONUS", "factor": 2.0, "ex_date": "2026-01-10", "subject": "Bonus 1:1"}


def run(rows, dossiers=None, nse=None):
    return se.run(nse or FakeNse({"DEMO": []}, {}), FakeSink(dossiers or {}), rows, today="2026-10-26")


def test_a_one_to_one_bonus_explains_a_halved_screener_eps():
    out = run([row("Q2FY26", "eps", 10.0, 5.0)], {"1": {"corporate_actions": [BONUS]}})
    r = out["rows"][0]
    assert r["explain_verdict"] == "share_adjusted" and r["factor"] == 2.0 and "bonus 1:1 on 2026-01-10" in r["detail"]
    assert out["verdicts"] == {"share_adjusted": 1}


def test_an_action_before_the_period_or_after_today_does_not_count():
    early = {"kind": "BONUS", "factor": 2.0, "ex_date": "2025-01-10", "subject": "Bonus 1:1"}
    future = {"kind": "SPLIT", "factor": 5.0, "ex_date": "2026-12-01", "subject": "Split"}
    rupee = {"kind": "DIVIDEND", "ex_date": "2026-01-10", "subject": "Dividend"}
    out = run([row("Q2FY26", "eps", 10.0, 5.0)], {"1": {"corporate_actions": [early, future, rupee]}})
    assert out["rows"][0]["explain_verdict"] == "unexplained" and out["rows"][0]["factor"] is None


def test_a_later_file_that_restated_the_figure_explains_it(parsed):
    parsed[b"later"] = result({("pat", "Q2FY26"): 80.0})
    nse = FakeNse({"DEMO": [listing("Q2FY27")]}, {"Q2FY27.xml": b"later"})
    out = run([row("Q2FY26", "pat", 100.0, 80.2)], nse=nse)
    r = out["rows"][0]
    assert r["explain_verdict"] == "restated_later" and r["later_value"] == 80.0 and r["later_file"] == "Q2FY27.xml"
    assert r["later_from"] == "nse"


def test_a_year_reads_the_next_march_file(parsed):
    parsed[b"later"] = result({("revenue", "FY26"): 900.0})
    nse = FakeNse({"DEMO": [listing("Q4FY27")]}, {"Q4FY27.xml": b"later"})
    assert run([row("FY26", "revenue", 1000.0, 900.0)], nse=nse)["rows"][0]["explain_verdict"] == "restated_later"


def test_memory_holds_the_later_source_so_nse_is_not_asked():
    entry = {"metric": "pat", "period": "Q2FY26", "value": 80.0, "unit": "INR_CR", "sources": [
        {"news_id": "xbrl:a", "as_of": "2025-11-01", "value": 100.0, "basis": "CONSOLIDATED"},
        {"news_id": "xbrl:b", "as_of": "2026-11-01", "value": 80.0, "basis": "CONSOLIDATED", "restated_from": "Q2FY27"}]}
    nse = FakeNse({"DEMO": []}, {})
    out = run([row("Q2FY26", "pat", 100.0, 80.2)], {"1": {"financial_metrics": [entry]}}, nse)
    r = out["rows"][0]
    assert r["explain_verdict"] == "restated_later" and r["later_from"] == "memory" and r["later_file"] == "Q2FY27"
    assert nse.list_calls == [] and nse.downloads == []


def test_a_later_file_equal_to_ours_falls_through(parsed):
    parsed[b"later"] = result({("pat", "Q2FY26"): 100.0})
    nse = FakeNse({"DEMO": [listing("Q2FY27")]}, {"Q2FY27.xml": b"later"})
    r = run([row("Q2FY26", "pat", 100.0, 80.2)], nse=nse)["rows"][0]
    assert r["explain_verdict"] == "unexplained" and "later_same" in r["detail"] and r["later_value"] == 100.0


def test_no_later_file_is_unexplained_with_the_reason():
    r = run([row("Q2FY26", "pat", 100.0, 80.2)], nse=FakeNse({"DEMO": []}, {}))["rows"][0]
    assert r["explain_verdict"] == "unexplained" and "Q2FY27" in r["detail"]


def test_a_refusal_stops_the_run_and_leaves_the_rest_not_run():
    nse = FakeNse({"A": SourceBlockedError("403"), "B": []}, {})
    rows = [row("Q2FY26", "pat", 100.0, 80.0, scrip="1", symbol="A"), row("Q2FY26", "pat", 100.0, 80.0, scrip="2", symbol="B")]
    out = se.run(nse, FakeSink({}), rows, today="2026-10-26")
    assert out["blocked"] and out["verdicts"] == {"not_run": 2}
    assert nse.list_calls == ["A"]


def test_the_time_budget_leaves_later_companies_not_run():
    rows = [row("Q2FY26", "pat", 100.0, 80.0, scrip="1", symbol="A"), row("Q2FY26", "pat", 100.0, 80.0, scrip="2", symbol="B")]
    nse = FakeNse({"A": [], "B": []}, {})
    out = se.run(nse, FakeSink({}), rows, time_budget=1, clock=iter([0, 0, 5]).__next__, today="2026-10-26")
    assert out["out_of_time"] and out["verdicts"] == {"unexplained": 1, "not_run": 1}


def test_other_verdicts_pass_through_unchanged():
    rows = [row("Q2FY26", "pat", 100.0, 80.0, verdict=v) for v in ("neither", "no_file", "screener_matches_official", "both_match")]
    out = run(rows)
    assert [r["explain_verdict"] for r in out["rows"]] == ["not_explained_input"] * 4
    assert [r["verdict"] for r in out["rows"]] == ["neither", "no_file", "screener_matches_official", "both_match"]
    assert out["companies"] == 0


def test_csv_round_trip_and_reports():
    out = run([row("Q2FY26", "eps", 10.0, 5.0), row("Q2FY26", "pat", 1.0, 2.0, verdict="neither")],
              {"1": {"corporate_actions": [BONUS]}})
    text = se.to_csv(out)
    assert text.splitlines()[0].endswith("explain_verdict,factor,later_value,later_file,later_from,detail")
    back = se.load_csv(text)
    assert [r["explain_verdict"] for r in back] == ["share_adjusted", "not_explained_input"]
    assert "share_adjusted: 1" in se.to_markdown(out, "2026-10-26") and "share_adjusted" in se.render(out)
    assert "\"rows\":" not in se.to_json(out)


def metrics(period, **values):
    return [{"metric": m, "period": period, "value": v, "unit": "INR_CR"} for m, v in values.items()]


def test_abb_eps_is_continuing_operations_and_screener_has_the_whole_profit():
    dossier = {"financial_metrics": metrics("Q4FY26", pat=1783.65, pat_continuing=341.91, pat_owners=1783.65)}
    r = run([row("Q4FY26", "eps", 16.14, 84.17)], {"1": dossier})["rows"][0]
    assert r["explain_verdict"] == "eps_continuing_vs_total" and abs(r["factor"] - 1783.65 / 341.91) < 1e-9
    assert "pat_owners" in r["detail"]


def test_abfrl_eps_uses_pat_owners_over_pat_continuing():
    dossier = {"financial_metrics": metrics("Q4FY25", pat=-23.55, pat_continuing=-160.92, pat_owners=-16.87)}   # the 25 Oct backup
    r = run([row("Q4FY25", "eps", -1.34, -0.14)], {"1": dossier})["rows"][0]
    assert r["explain_verdict"] == "eps_continuing_vs_total"


def test_continuing_needs_the_screener_figure_to_agree_and_pat_continuing_to_exist():
    dossier = {"financial_metrics": metrics("Q4FY26", pat=1783.65, pat_continuing=341.91)}
    assert run([row("Q4FY26", "eps", 16.14, 50.0)], {"1": dossier})["rows"][0]["explain_verdict"] == "unexplained"
    assert run([row("Q4FY26", "eps", 16.14, 84.17)], {"1": {"financial_metrics": metrics("Q4FY26", pat=1783.65)}})["rows"][0][
        "explain_verdict"] == "unexplained"


def test_a_rights_issue_is_noted_not_given_a_factor():
    rights = {"kind": "RIGHTS", "factor": None, "ex_date": "2025-11-17", "subject": "Rights 3:25 @ Premium Rs 1799/-"}
    r = run([row("Q2FY26", "eps", 10.0, 9.0)], {"1": {"corporate_actions": [rights]}})["rows"][0]
    assert r["explain_verdict"] == "unexplained" and r["factor"] is None
    assert "rights issue on 2025-11-17 between the period and today" in r["detail"]


def test_pdf_referee_explained_takes_unexplained_and_the_open_verdicts():
    rows = [{**row("Q2FY26", "pat", 1.0, 2.0, symbol=s), "explain_verdict": ev, "verdict": v}
            for s, ev, v in [("A", "unexplained", "ours_matches_official"), ("B", "share_adjusted", "ours_matches_official"),
                             ("C", "restated_later", "ours_matches_official"), ("D", "not_explained_input", "neither"),
                             ("E", "not_run", "ours_matches_official"), ("F", "not_explained_input", "both_match")]]
    assert [r["symbol"] for r in pr.open_pairs(rows, explained=True)] == ["A", "D", "E"]   # a row the explain run cut still goes
    assert [r["symbol"] for r in pr.open_pairs(rows)] == ["D"]    # without the flag the old behaviour


def test_a_standalone_profit_is_never_put_beside_a_consolidated_eps():
    from bse_intel import screener_explain as se
    d = {"financial_metrics": [
        {"metric": "pat_continuing", "period": "Q4FY26", "value": 100.0, "basis": "STANDALONE"},
        {"metric": "pat", "period": "Q4FY26", "value": 500.0, "basis": "STANDALONE"},
        {"metric": "pat_continuing", "period": "Q4FY26", "value": 341.91, "basis": "CONSOLIDATED"},
        {"metric": "pat", "period": "Q4FY26", "value": 1783.65, "basis": "CONSOLIDATED"},
        {"metric": "pat_owners", "period": "Q4FY26", "value": 1783.65, "basis": "CONSOLIDATED"}]}
    ratio, line = se.continuing_ratio(d, "Q4FY26", "CONSOLIDATED")
    assert abs(ratio - 1783.65 / 341.91) < 1e-9 and line == "pat_owners"



def test_an_eps_on_the_whole_profit_where_screener_is_on_the_owners_share_goes_to_the_pdf():
    # AFSL Q2FY25 (25 Oct backup): no discontinued operation (pat = pat_continuing 27.38), owners 25.39; ours 5.46, screener 5.06
    dossier = {"financial_metrics": metrics("Q2FY25", pat=27.38, pat_continuing=27.38, pat_owners=25.39)}
    r = run([row("Q2FY25", "eps", 5.46, 5.06)], {"1": dossier})["rows"][0]
    assert r["explain_verdict"] == "eps_owners_vs_total"
    assert pr.open_pairs([{**r, "verdict": "ours_matches_official"}], explained=True)


def test_a_gap_within_twice_the_tolerance_is_not_explained():
    # UEL Q2FY25 (review) was 0.07 against 0.01 with a factor of 5.04: a gap of exactly twice the 0.03 floor is not apart
    bonus = [{"kind": "BONUS", "factor": 5.04, "ex_date": "2025-01-10", "subject": "Bonus"}]
    r = run([row("Q2FY25", "eps", 0.07, 0.01)], {"1": {"financial_metrics": [], "corporate_actions": bonus}})["rows"][0]
    assert r["explain_verdict"] == "unexplained"


def test_a_ratio_of_zero_or_below_explains_nothing():
    dossier = {"financial_metrics": metrics("Q1FY25", pat=10.0, pat_continuing=3.0, pat_owners=0.0)}
    assert run([row("Q1FY25", "eps", 0.9, 0.04)], {"1": dossier})["rows"][0]["explain_verdict"] == "unexplained"


def test_a_recorded_bonus_explains_a_small_eps_too():
    # EASEMYTRIP Q1FY25 (second review): ours 0.19, screener 0.09, bonus 1:1 after the period
    bonus = [{"kind": "BONUS", "factor": 2.0, "ex_date": "2025-01-10", "subject": "Bonus 1:1"}]
    r = run([row("Q1FY25", "eps", 0.19, 0.09)], {"1": {"financial_metrics": [], "corporate_actions": bonus}})["rows"][0]
    assert r["explain_verdict"] == "share_adjusted"
