"""F166: memory also saves the excise duty and the profit to minority interests that the XBRL reader parses.

The minority figure is memory-only: not in ``XbrlResult.metrics`` (so no prompt table, card or check reads it) and left
out of the model's memory view; excise duty was already stored."""
from datetime import date

from bse_intel import memory_gaps
from bse_intel import seed as seed_mod
from bse_intel import xbrl
from bse_intel.dossier import view_as_of

from test_xbrl import _fact, results_xml


def _with_tags(minority_q2=20_000_000, owners_q2=130_000_000):
    raw = results_xml().decode().replace("</xbrli:xbrl>", "")
    for ctx, excise, minority, owners in (("OneD", 10_000_000, minority_q2, owners_q2),
                                          ("ThreeD", 5_000_000, 10_000_000, 80_000_000)):
        raw += _fact("ExciseDuty", ctx, excise) + _fact("ProfitOrLossAttributableToNonControllingInterests", ctx, minority) \
            + _fact("ProfitOrLossAttributableToOwnersOfParent", ctx, owners)
    return (raw + "</xbrli:xbrl>").encode()


class _Sink:
    def __init__(self):
        self.d = {}

    def get_dossier(self, key):
        return self.d.get(key)

    def put_dossier(self, key, value):
        self.d[key] = value


def _seed(parsed):
    sink = _Sink()
    seed_mod._write_results(sink, "500001", "X", None, "Q2FY27", "2026-10-20", "http://x/a.xml", parsed, seed_mod.SeedStats())
    return sink.d["500001"]


def _by(dossier):
    return {(m["metric"], m["period"]): m for m in dossier["financial_metrics"]}


def test_memory_gets_excise_duty_and_minority_profit_with_labels_and_basis():
    by = _by(_seed(xbrl.parse(_with_tags())))
    for key, value in ((("excise_duty", "Q2FY27"), 1.0), (("excise_duty", "Q2FY26"), 0.5),
                       (("pat_minority", "Q2FY27"), 2.0), (("pat_minority", "Q2FY26"), 1.0)):
        assert by[key]["value"] == value and by[key]["unit"] == "INR_CR", key
        lab = by[key]["lab"]
        assert (lab["by"], lab["doc"], lab["basis"]) == ("file", "results", "CONSOLIDATED"), key
        assert by[key]["source_news_id"].startswith("xbrl:res:500001:"), key
    assert by[("pat_minority", "Q2FY27")]["yoy_pct"] == 100.0
    assert by[("pat", "Q2FY27")]["lab"]["basis"] == by[("pat_minority", "Q2FY27")]["lab"]["basis"]


def test_the_minority_figure_is_not_in_the_metrics_a_card_reads():
    parsed = xbrl.parse(_with_tags())
    assert "pat_minority" not in {m.metric for m in parsed.metrics}
    assert "pat_minority" in {m.metric for m in parsed.memory_extra}
    assert "pat_minority" not in parsed.table()
    assert xbrl.parse(results_xml()).memory_extra == []


def test_a_minority_share_that_does_not_add_up_is_not_kept():
    # owners 13 + minority 80 is not the profit 15: the owners' tag is dropped and the minority figure is not trusted
    parsed = xbrl.parse(_with_tags(minority_q2=800_000_000))
    assert ("pat_minority", "Q2FY27") not in {(m.metric, m.period) for m in parsed.memory_extra}
    assert ("pat_owners", "Q2FY27") not in {(m.metric, m.period) for m in parsed.metrics}


def test_the_models_memory_view_is_the_same_with_or_without_the_minority_figure():
    parsed = xbrl.parse(_with_tags())
    with_it = _seed(parsed)
    parsed.memory_extra = []
    without = _seed(parsed)
    assert "pat_minority" in {m["metric"] for m in with_it["financial_metrics"]}
    assert "pat_minority" not in {m["metric"] for m in without["financial_metrics"]}
    cutoff = "2026-12-01T00:00:00+05:30"
    assert view_as_of(with_it, cutoff) == view_as_of(without, cutoff)


def test_memory_gaps_do_not_count_the_two_lines_as_required():
    dossier = _seed(xbrl.parse(_with_tags()))
    dossier["financial_metrics"] = [m for m in dossier["financial_metrics"]
                                    if m["metric"] in ("excise_duty", "pat_minority")]
    assert memory_gaps.check(dossier, date(2026, 10, 26))["basis"] is None   # neither is revenue or PAT
