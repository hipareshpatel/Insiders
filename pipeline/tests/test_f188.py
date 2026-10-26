"""F188 (TODO 89): the whole company's EPS on the card, the continuing-operations EPS beside it (CARD_EPS_WHOLE).

ABB India's Q4FY26 file tags 16.14 (continuing operations) first, so memory's `eps` is that, beside a company profit of
₹1,783.65 Cr (341.91 continuing, 1,441.74 discontinued); screener has 84.17. Memory also keeps the two EPS tags on their
own (`eps_total`, `eps_continuing`), never in what a card or prompt reads."""

import copy

from bse_intel import xbrl
from bse_intel.dossier import MEMORY_ONLY_METRICS, results_snapshot, view_as_of

from test_xbrl import _fact, results_xml


# ---------------------------------------------------------------- the file reader
def _two_tags():
    """results_xml tags the whole-company EPS 4.25 for the quarter; the continuing one is tagged first, as ABB's is."""
    raw = results_xml().decode()
    return raw.replace("<in-bse-fin:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                       _fact("BasicEarningsLossPerShareFromContinuingOperations", "OneD", "1.5", "INRPerShare")
                       + "<in-bse-fin:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", 1).encode()


def test_a_file_with_both_tags_gives_eps_as_before_and_the_two_variants_for_memory():
    parsed = xbrl.parse(_two_tags())
    by = {(m.metric, m.period): m for m in parsed.metrics}
    assert by[("eps", "Q2FY27")].value == 1.5            # the first tag in the file wins, as it always did
    assert not {"eps_total", "eps_continuing"} & {m.metric for m in parsed.metrics}   # nothing a card reads changes
    extra = {(m.metric, m.period): m for m in parsed.memory_extra}
    assert extra[("eps_total", "Q2FY27")].value == 4.25 and extra[("eps_total", "Q2FY27")].unit == "INR"
    assert extra[("eps_continuing", "Q2FY27")].value == 1.5 and extra[("eps_continuing", "Q2FY27")].unit == "INR"


def test_a_variant_the_file_does_not_tag_is_not_recorded():
    parsed = xbrl.parse(results_xml())                   # whole-company tag only
    names = {m.metric for m in parsed.memory_extra}
    assert "eps_total" in names and "eps_continuing" not in names


def test_the_variants_follow_the_filler_and_sign_rules_of_eps():
    values = {("pat", "Q1"): 70.0, ("eps", "Q1"): 0.0, ("eps_total", "Q1"): 0.0, ("eps_continuing", "Q1"): 0.0,
              ("pat", "Q2"): -30.0, ("eps_total", "Q2"): 2.0,
              ("pat", "Q3"): 40.0, ("pat_continuing", "Q3"): -10.0, ("eps_continuing", "Q3"): -1.0, ("eps_total", "Q3"): 3.0}
    assert xbrl.eps_fillers(values) == 2                 # the template's 0 beside a profit of 70 Cr, eps and eps_total
    assert values[("eps_continuing", "Q1")] == 0.0       # no continuing profit to judge it by: left as filed
    assert xbrl.eps_signs(values) == 1
    assert values[("eps_total", "Q2")] == -2.0           # a loss makes the EPS a loss
    assert values[("eps_continuing", "Q3")] == -1.0      # the continuing loss keeps its sign beside a whole profit
    assert values[("eps_total", "Q3")] == 3.0


def test_the_variants_are_memory_only_and_left_out_of_the_models_view():
    assert {"eps_total", "eps_continuing"} <= MEMORY_ONLY_METRICS
    dossier = {"financial_metrics": [
        {"metric": "eps", "period": "Q2FY27", "value": 1.5, "unit": "INR", "source_news_id": "n", "as_of": "2026-10-01"},
        {"metric": "eps_total", "period": "Q2FY27", "value": 4.25, "unit": "INR", "source_news_id": "n", "as_of": "2026-10-01"}]}
    view = view_as_of(dossier, "2026-11-01")
    assert "eps_total" not in str(view)


# ---------------------------------------------------------------- the results table
def _m(metric, period, value, news="n1", unit="INR_CR"):
    return {"metric": metric, "period": period, "value": value, "unit": unit, "source_news_id": news, "as_of": "2026-10-01"}


def _abb(year_ago_discontinued=False):
    """ABB India: Q4FY26 profit 1,783.65 (341.91 continuing, 1,441.74 discontinued); memory's eps is the continuing 16.14."""
    return {"financial_metrics": [
        _m("revenue", "Q4FY26", 3300.0, "n2"), _m("revenue", "Q4FY25", 3000.0), _m("revenue", "Q3FY26", 3100.0),
        _m("ebitda", "Q4FY26", 560.0, "n2"), _m("ebitda", "Q4FY25", 500.0), _m("ebitda", "Q3FY26", 520.0),
        _m("pat", "Q4FY26", 1783.65, "n2"), _m("pat_continuing", "Q4FY26", 341.91, "n2"),
        _m("pat_discontinued", "Q4FY26", 1441.74, "n2"),
        _m("pat", "Q4FY25", 300.0), _m("pat_continuing", "Q4FY25", 220.0 if year_ago_discontinued else 300.0),
        _m("pat", "Q3FY26", 330.0), _m("pat_continuing", "Q3FY26", 330.0),
        _m("eps", "Q4FY26", 16.14, "n2", "INR"), _m("eps", "Q4FY25", 14.2, unit="INR"), _m("eps", "Q3FY26", 15.5, unit="INR"),
        _m("eps_total", "Q4FY26", 84.17, "n2", "INR"), _m("eps_continuing", "Q4FY26", 16.14, "n2", "INR")]}


def test_the_switch_off_leaves_the_table_as_it_is_with_or_without_the_new_figures(monkeypatch):
    monkeypatch.delenv("CARD_EPS_WHOLE", raising=False)
    old = _abb()
    old["financial_metrics"] = [m for m in old["financial_metrics"] if m["metric"] not in ("eps_total", "eps_continuing")]
    assert results_snapshot(_abb(), "n2", with_eps=True) == results_snapshot(old, "n2", with_eps=True)
    assert results_snapshot(_abb(), "n2", with_eps=True)["eps"] == {"value": 16.14, "prev_year": 14.2, "prev_quarter": 15.5,
                                                    "yoy_pct": 13.7, "qoq_pct": 4.1}


def test_the_whole_company_eps_with_the_continuing_one_beside_it(monkeypatch):
    monkeypatch.setenv("CARD_EPS_WHOLE", "1")
    eps = results_snapshot(_abb(), "n2", with_eps=True)["eps"]
    assert eps["value"] == 84.17 and eps["continuing"] == 16.14
    assert eps["prev_year"] == 14.2 and eps["yoy_pct"] == round((84.17 / 14.2 - 1) * 100, 1)   # no discontinued operation then


def test_an_eps_that_is_the_same_on_both_bases_shows_no_continuing(monkeypatch):
    monkeypatch.setenv("CARD_EPS_WHOLE", "1")
    d = _abb()
    for m in d["financial_metrics"]:
        if m["metric"] in ("eps", "eps_total", "eps_continuing") and m["period"] == "Q4FY26":
            m["value"] = 16.14
    d["financial_metrics"] = [m for m in d["financial_metrics"] if m["metric"] != "pat_discontinued"]
    eps = results_snapshot(d, "n2", with_eps=True)["eps"]
    assert eps["value"] == 16.14 and "continuing" not in eps


def test_a_comparison_across_two_bases_is_left_out(monkeypatch):
    monkeypatch.setenv("CARD_EPS_WHOLE", "1")
    eps = results_snapshot(_abb(year_ago_discontinued=True), "n2", with_eps=True)["eps"]
    assert eps["value"] == 84.17
    assert "prev_year" not in eps and "yoy_pct" not in eps       # the year-ago EPS is continuing only: not a base for 84.17
    assert eps["prev_quarter"] == 15.5 and "qoq_pct" in eps       # that quarter had no discontinued operation


def test_a_quarter_without_the_whole_company_figure_is_unchanged(monkeypatch):
    d = _abb()
    d["financial_metrics"] = [m for m in d["financial_metrics"] if m["metric"] not in ("eps_total", "eps_continuing")]
    monkeypatch.delenv("CARD_EPS_WHOLE", raising=False)
    off = results_snapshot(copy.deepcopy(d), "n2", with_eps=True)
    monkeypatch.setenv("CARD_EPS_WHOLE", "1")
    assert results_snapshot(d, "n2", with_eps=True) == off


def test_no_continuing_figure_is_inferred_from_the_older_eps(monkeypatch):
    # a file without the continuing tag: memory's other `eps` is never labelled "continuing" by inference (lead's review)
    monkeypatch.setenv("CARD_EPS_WHOLE", "1")
    d = _abb()
    d["financial_metrics"] = [m for m in d["financial_metrics"] if m["metric"] != "eps_continuing"]
    eps = results_snapshot(d, "n2", with_eps=True)["eps"]
    assert eps["value"] == 84.17 and "continuing" not in eps


def test_the_share_base_and_profit_checks_still_work_on_the_chosen_line(monkeypatch):
    monkeypatch.setenv("CARD_EPS_WHOLE", "1")
    monkeypatch.setenv("CARD_EPS_FOLLOWS_PROFIT", "1")
    d = _abb()
    # profit rose from 330 to 1,783.65 (+440%) and EPS from 15.5 to 84.17 (+443%): carried, kept
    eps = results_snapshot(d, "n2", with_eps=True)["eps"]
    assert eps["value"] == 84.17 and eps["continuing"] == 16.14 and "qoq_pct" in eps
    monkeypatch.setenv("EPS_SHARE_ADJUST", "1")
    d["corporate_actions"] = [{"ex_date": "2026-02-01", "kind": "SPLIT", "factor": 5.0, "subject": "SPLIT 1:5"}]
    for m in d["financial_metrics"]:
        if (m["metric"], m["period"]) == ("eps", "Q4FY25"):
            m["value"] = 71.0   # the year-ago EPS before the 1:5 split
    eps = results_snapshot(d, "n2", with_eps=True)["eps"]
    assert eps["value"] == 84.17 and eps["continuing"] == 16.14 and eps.get("eps_note") \
        and eps["yoy_pct"] == round((84.17 / 14.2 - 1) * 100, 1)   # the share-count note is on the line, the change on one count



def test_a_continuing_eps_without_a_continuing_profit_keeps_its_sign_and_its_zero():
    # review of F188: a loss on continuing operations beside a whole profit from the business sold, no continuing-profit tag
    from bse_intel.xbrl import eps_fillers, eps_signs
    values = {("eps_continuing", "Q4FY26"): -3.0, ("pat", "Q4FY26"): 200.0, ("pat_owners", "Q4FY26"): 200.0}
    assert eps_signs(values) == 0 and values[("eps_continuing", "Q4FY26")] == -3.0
    zero = {("eps_continuing", "Q4FY26"): 0.0, ("pat", "Q4FY26"): 200.0}
    assert eps_fillers(zero) == 0 and zero[("eps_continuing", "Q4FY26")] == 0.0
