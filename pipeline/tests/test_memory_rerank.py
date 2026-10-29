"""memory-rerank (TODO 118 B, 29 Oct 2026): stored figures the new ranking changes are rebuilt from their own sources, with a
backup first, at most ``limit`` a run; a figure some other rule set is left alone. Run on the local sink."""

import json

from bse_intel import memory_rerank, restore
from bse_intel.sinks.local import LocalSink


def _src(news_id, value, as_of, by):
    return {"news_id": news_id, "value": value, "as_of": as_of, "unit": "INR_CR", "basis": "CONSOLIDATED",
            "lab": {"by": by, "doc": "results" if by != "ai" else "release"}}


def _old_entry(metric, period, sources, value):
    """A figure as the old rule stored it: the newest source wins."""
    last = sorted(sources, key=lambda s: s["as_of"])[-1]
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "as_of": sources[0]["as_of"],
            "source_news_id": sources[0]["news_id"], "sources": sources, "value_news_id": last["news_id"]}


def _sink(settings, n_companies=1):
    sink = LocalSink(settings)
    for i in range(n_companies):
        file_, release = _src("nse-1", 1274.17, "2026-10-28T18:55:00+05:30", "file"), _src("nse-2", 1270.0, "2026-10-28T18:59:00+05:30", "ai")
        other = [_src("nse-3", 50.0, "2026-10-28T18:55:00+05:30", "file"), _src("nse-4", 49.0, "2026-10-28T18:59:00+05:30", "ai")]
        sink.put_dossier(f"5000{i:02d}", {"scrip_code": f"5000{i:02d}", "financial_metrics": [
            _old_entry("pat", "H1FY27", [file_, release], 1270.0),
            _old_entry("revenue", "H1FY27", other, 51.0),   # stored by some other rule: not the old rule's value, left alone
            {"metric": "ebitda", "period": "H1FY27", "value": 9.0, "unit": "INR_CR", "as_of": "2026-10-28T18:55:00+05:30",
             "source_news_id": "nse-1"}]})
    return sink


def test_a_dry_run_reports_and_writes_nothing(settings):
    sink = _sink(settings)
    before = sink.get_dossier("500000")
    out = memory_rerank.run(sink, ["500000"])
    assert out["error"] is None and out["figures"] == 1 and out["dossiers_written"] == 0
    assert out["rows"][0] | {} == {"scrip": "500000", "metric": "pat", "period": "H1FY27", "old": 1270.0, "new": 1274.17,
                                   "from": "nse-1", "was_from": "nse-2"}
    assert sink.get_dossier("500000") == before
    assert "would correct" in memory_rerank.render(out)


def test_apply_corrects_only_the_rule_s_figures_backs_up_and_restores(settings):
    sink = _sink(settings)
    before = sink.get_dossier("500000")
    out = memory_rerank.run(sink, ["500000"], apply=True)
    assert out["dossiers_written"] == 1 and out["backup"]["dossiers"] == 1
    got = {(e["metric"], e["period"]): e["value"] for e in sink.get_dossier("500000")["financial_metrics"]}
    assert got == {("pat", "H1FY27"): 1274.17, ("revenue", "H1FY27"): 51.0, ("ebitda", "H1FY27"): 9.0}
    assert memory_rerank.run(sink, ["500000"], apply=True)["figures"] == 0   # a second run finds nothing
    prefix = out["backup"]["prefix"]
    assert json.loads(sink.get_object(f"{prefix}memory/500000.json")) == before
    restore.apply(sink, restore.plan(sink, prefix, everything=True))
    assert sink.get_dossier("500000") == before


def test_the_limit_keeps_whole_companies_for_the_next_run(settings):
    sink = _sink(settings, 3)
    out = memory_rerank.run(sink, ["500000", "500001", "500002"], apply=True, limit=2)
    assert out["figures"] == 2 and out["dossiers_written"] == 2 and out["waiting"] == ["500002"]
    assert memory_rerank.run(sink, ["500000", "500001", "500002"], apply=True, limit=2)["figures"] == 1
