"""nse_selfcheck: NSE's own figures in memory against themselves (TODO row 60), on fake dossiers."""
from bse_intel import nse_selfcheck as sc


def src(nid, value, as_of, later_of=None, by="file", basis="CONSOLIDATED"):
    s = {"news_id": nid, "as_of": as_of, "value": value, "unit": "INR_CR", "basis": basis, "lab": {"by": by, "doc": "results"}}
    if later_of:
        s["restated_from"] = later_of
    return s


def entry(metric, period, *sources, unit="INR_CR"):
    sources = sorted(sources, key=lambda s: s["as_of"])
    e = {"metric": metric, "period": period, "value": sources[-1]["value"], "unit": unit, "as_of": sources[0]["as_of"],
         "source_news_id": sources[0]["news_id"]}
    if len(sources) > 1:
        e.update(sources=list(sources), value_news_id=sources[-1]["news_id"])
    else:
        e.update(basis=sources[0]["basis"], lab=sources[0]["lab"])
    return e


def pair(metric, period, own, later, later_id="xbrl:res:1:Q2FY27"):
    return entry(metric, period, src(f"xbrl:res:1:{period}", own, "2025-10-20"),
                 src(later_id, later, "2026-10-20", later_of="Q2FY27"))


def classes(entries):
    return {(r["metric"], r["period"]): r for r in sc.own_against_later(entries)}


def test_rounding_within_half_a_percent_or_one_crore():
    rows = classes([pair("revenue", "Q2FY26", 1000.0, 1004.0), pair("pat", "Q2FY26", 20.0, 20.9)])
    assert rows[("revenue", "Q2FY26")]["class"] == "rounding"
    assert rows[("pat", "Q2FY26")]["class"] == "rounding"   # 0.9 Cr, under 1 Cr


def test_one_line_restated_and_several_lines_say_merger():
    one = classes([pair("revenue", "Q2FY26", 100.0, 130.0), pair("pat", "Q2FY26", 10.0, 10.0)])
    assert one[("revenue", "Q2FY26")]["class"] == "restated" and one[("revenue", "Q2FY26")]["note"] == ""
    many = classes([pair("revenue", "Q2FY26", 100.0, 130.0), pair("pat", "Q2FY26", 10.0, 14.0), pair("ebitda", "Q2FY26", 20.0, 27.0)])
    assert all(r["class"] == "restated" and "merger" in r["note"] for r in many.values())


def test_single_line_x100_is_scale_suspect_but_not_when_other_lines_differ():
    alone = classes([pair("revenue", "Q2FY26", 12.5, 1250.0), pair("pat", "Q2FY26", 3.0, 3.0)])
    assert alone[("revenue", "Q2FY26")]["class"] == "scale_suspect" and "x100" in alone[("revenue", "Q2FY26")]["note"]
    together = classes([pair("revenue", "Q2FY26", 12.5, 1250.0), pair("pat", "Q2FY26", 3.0, 8.0)])
    assert together[("revenue", "Q2FY26")]["class"] == "restated"


def test_own_figure_equal_to_another_quarter_in_the_later_file_is_wrong_quarter():
    later_id = "xbrl:res:1:Q2FY27"
    q2 = entry("revenue", "Q2FY26", src("xbrl:res:1:Q2FY26", 500.0, "2025-10-20"), src(later_id, 300.0, "2026-10-20", "Q2FY27"))
    q1 = entry("revenue", "Q1FY26", src(later_id, 500.0, "2026-10-20", "Q2FY27"))
    rows = classes([q2, q1])
    assert rows[("revenue", "Q2FY26")]["class"] == "wrong_quarter_suspect" and "Q1FY26" in rows[("revenue", "Q2FY26")]["note"]
    assert ("revenue", "Q1FY26") not in rows   # no own file: nothing to compare


def test_cards_and_other_bases_are_never_compared():
    card = {"news_id": "123", "as_of": "2025-10-20", "value": 50.0, "unit": "INR_CR", "lab": {"by": "ai"}}
    e = entry("revenue", "Q2FY26", card, src("xbrl:res:1:Q2FY27", 90.0, "2026-10-20", "Q2FY27"))
    assert sc.own_against_later([e]) == []
    e = entry("revenue", "Q2FY26", src("xbrl:res:1:a", 50.0, "2025-10-20", basis="STANDALONE"),
              src("xbrl:res:1:b", 90.0, "2026-10-20", "Q2FY27", basis="CONSOLIDATED"))
    assert sc.own_against_later([e]) == []


def test_non_flow_metrics_are_left_out():
    assert sc.own_against_later([pair("total_assets", "Q2FY26", 1.0, 99.0), pair("eps", "Q2FY26", 1.0, 99.0)]) == []


def year(metric, quarters, full, by="file", basis="CONSOLIDATED"):
    out = [entry(metric, f"Q{i}FY26", src(f"xbrl:res:1:Q{i}FY26", v, f"2025-0{i}-01", basis=basis, by=by))
           for i, v in enumerate(quarters, 1)]
    return out + [entry(metric, "FY26", src("xbrl:res:1:FY26", full, "2026-05-01", basis=basis))]


def test_quarters_against_year_rounding_and_gap():
    ok = sc.quarters_against_year(year("revenue", [100.0, 110.0, 120.0, 130.0], 460.4))
    assert ok[0]["class"] == "rounding" and ok[0]["later_value"] == 460.0
    gap = sc.quarters_against_year(year("pat", [10.0, 10.0, 10.0, 10.0], 55.0))
    assert gap[0]["class"] == "quarter_sum_gap" and "gap -15.00" in gap[0]["note"]


def test_year_check_skips_eps_cards_mixed_bases_and_missing_quarters():
    assert sc.quarters_against_year(year("eps", [1.0, 1.0, 1.0, 1.0], 9.0)) == []
    cards = [entry("pat", f"Q{i}FY26", src(f"n{i}", 1.0, f"2025-0{i}-01", by="ai")) for i in (1, 2, 3, 4)]
    assert sc.quarters_against_year(cards + [entry("pat", "FY26", src("xbrl:res:1:FY26", 9.0, "2026-05-01"))]) == []
    mixed = year("pat", [1.0, 1.0, 1.0, 1.0], 9.0)
    mixed[0] = entry("pat", "Q1FY26", src("xbrl:res:1:Q1FY26", 1.0, "2025-01-01", basis="STANDALONE"))
    assert sc.quarters_against_year(mixed) == []
    assert sc.quarters_against_year(year("pat", [1.0, 1.0, 1.0, 1.0], 9.0)[1:]) == []


class FakeSink:
    def __init__(self, dossiers):
        self.d = dossiers

    def get_dossier(self, scrip):
        return self.d.get(scrip)


def test_survey_counts_ranks_and_writes_csv():
    bad = [pair("revenue", "Q2FY26", 100.0, 130.0), pair("pat", "Q2FY26", 10.0, 10.0)]
    clean = [pair("revenue", "Q2FY26", 100.0, 100.0)]
    sink = FakeSink({"1": {"financial_metrics": bad}, "2": {"financial_metrics": clean}, "3": None})
    report = sc.survey(sink, ["1", "2", "3"], {"1": "AAA", "2": "BBB"}, workers=1)
    assert report["by_class"]["restated"] == 1 and report["by_class"]["rounding"] == 2
    assert report["worst_companies"] == [{"scrip": "1", "symbol": "AAA", "differences": 1, "by_class": {"restated": 1}}]
    lines = sc.to_csv(report).splitlines()
    assert lines[0].startswith("scrip,symbol,metric,period,own_value,later_value,class,source_ids")
    assert len(lines) == 4 and "AAA" in lines[1]
    assert "restated" in sc.render(report)
