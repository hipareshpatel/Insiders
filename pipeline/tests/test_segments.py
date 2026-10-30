"""segments.py (owner, 30 Oct 2026, TODO 137: "Business mix ... on stock pages are wrong or blank"): the quarter's business mix from the
results file's segment note, by code, with the real files."""
from pathlib import Path

from bse_intel import screener_view as sv
from bse_intel import segments, statements, statements_backfill, xbrl_facts

FIXTURES = Path(__file__).parent / "fixtures"
AS_OF, AT = "2026-10-30T18:00:00+05:30", "2026-10-30T18:01:00+05:30"


def _doc(name):
    return xbrl_facts.parse_facts((FIXTURES / name).read_bytes(), "x", "u")


def test_a_multi_segment_file_gives_its_segments_without_the_unallocated_line():
    found = segments.segment_rows(_doc("bse_main_ind_as_532811_q3fy25.xml"))
    assert found["single"] is False
    by = {r["segment"]: r for r in found["rows"]}
    # UNALLOCATED and OTHERS (no revenue in the quarter) are no segment; the amounts are the quarter's, not the nine months'
    assert set(by) == {"CONTRACT WORK", "INVESTMENT PROPERTY"}
    assert (by["CONTRACT WORK"]["revenue_cr"], by["CONTRACT WORK"]["pbit_cr"]) == (950.28, 75.55)
    assert by["INVESTMENT PROPERTY"]["revenue_cr"] == 1.68
    assert round(sum(r["share_pct"] for r in found["rows"]), 0) == 100
    assert found["rows"][0]["segment"] == "CONTRACT WORK"      # largest first


def test_the_capmkt_taxonomy_is_read_too_and_the_unallocated_result_is_not_a_segment():
    found = segments.segment_rows(_doc("nse_hdfcbank_q2fy27_cons.xml"))
    by = {r["segment"]: r for r in found["rows"]}
    assert "Unallocated" not in by and "Retail Banking" in by and "Insurance Business" in by
    assert by["Retail Banking"]["revenue_cr"] == 79112.16
    assert by["Retail Banking"]["pbit_cr"] == 10521.59


def test_a_single_segment_file_gives_the_marker_and_its_description():
    assert segments.segment_rows(_doc("nse_dolphin_q4fy24_cons.xml")) == {"single": True, "description": "Offshore Support Services"}
    assert segments.segment_rows(_doc("nse_bajfin_q2fy27_cons.xml")) == {"single": True, "description": "NBFC"}


def test_remember_labels_the_rows_as_the_files_and_replaces_ai_rows_of_the_period():
    d = {"segment_mix": [{"segment": "Wrong", "period": "Q3FY25", "revenue_cr": 5.0, "as_of": "2025-02-01", "lab": {"by": "ai"}},
                         {"segment": "Old", "period": "Q2FY25", "revenue_cr": 7.0, "as_of": "2024-11-01", "lab": {"by": "ai"}}]}
    assert segments.remember(d, _doc("bse_main_ind_as_532811_q3fy25.xml"), "n1", AS_OF, AT) == 2
    rows = d["segment_mix"]
    assert [r["segment"] for r in rows] == ["Old", "CONTRACT WORK", "INVESTMENT PROPERTY"]
    new = rows[1]
    assert (new["period"], new["basis"], new["lab"]["by"], new["source_news_id"]) == ("Q3FY25", "STANDALONE", "file", "n1")


def test_a_single_segment_marker_replaces_an_ai_ring():
    d = {"segment_mix": [{"segment": "X", "period": "Q4FY24", "revenue_cr": 5.0, "as_of": "a", "lab": {"by": "ai"}}]}
    assert segments.remember(d, _doc("nse_dolphin_q4fy24_cons.xml"), "n1", AS_OF, AT) == 1
    assert d["segment_mix"][0]["segment"] == "Offshore Support Services" and d["segment_mix"][0]["single"] is True


def test_a_standalone_file_never_overwrites_a_consolidated_filers_mix():
    doc = _doc("bse_main_ind_as_532811_q3fy25.xml")      # a standalone file
    d = {"financial_metrics": [{"metric": "revenue", "period": "Q3FY25", "basis": "CONSOLIDATED"}],
         "segment_mix": [{"segment": "AI cut", "period": "Q3FY25", "as_of": "a", "lab": {"by": "ai"}}]}
    assert segments.remember(d, doc, "n1", AS_OF, AT) == 0
    assert d["segment_mix"][0]["segment"] == "AI cut"
    held = {"segment_mix": [{"segment": "Kept", "period": "Q3FY25", "basis": "CONSOLIDATED", "as_of": "a", "lab": {"by": "file"}}]}
    assert segments.remember(held, doc, "n1", AS_OF, AT) == 0 and held["segment_mix"][0]["segment"] == "Kept"
    # and a consolidated file takes a standalone file's place
    d = {}
    segments.remember(d, doc, "n1", AS_OF, AT)
    cons = dict(doc, basis="CONSOLIDATED")
    assert segments.remember(d, cons, "n2", AS_OF, AT) == 2
    assert {r["basis"] for r in d["segment_mix"]} == {"CONSOLIDATED"}


def test_the_live_step_writes_the_mix_beside_the_statements():
    d = {}
    statements.from_file(_Sink(), d, (FIXTURES / "bse_main_ind_as_532811_q3fy25.xml").read_bytes(), "532811", "u", "n1", AS_OF, AT)
    assert [r["segment"] for r in d["segment_mix"]] == ["CONTRACT WORK", "INVESTMENT PROPERTY"]


class _Sink:
    def put_object(self, *args, **kwargs):
        pass


def test_the_backfill_fills_past_quarters_from_stored_facts_and_keeps_what_a_filing_wrote():
    docs = {"q3": _doc("bse_main_ind_as_532811_q3fy25.xml"), "q2": _doc("bse_main_ind_as_532811_q2fy25.xml")}
    store = {xbrl_facts.key("532811", d["period"], d["basis"]): xbrl_facts.dumps(d) for d in docs.values()}
    cf = sv.CompanyFacts(sorted(store), store.__getitem__)
    d = {"segment_mix": [{"segment": "Live", "period": "Q3FY25", "basis": "STANDALONE", "as_of": "a", "lab": {"by": "file"}}]}
    added = statements_backfill.fill_segments(cf, d, AT)
    periods = {r["period"] for r in d["segment_mix"]}
    assert added > 0 and periods == {"Q2FY25", "Q3FY25"}
    assert [r["segment"] for r in d["segment_mix"] if r["period"] == "Q3FY25"] == ["Live"]      # a filing's own rows stay
    assert all(r["lab"]["from"] == "stored facts" for r in d["segment_mix"] if r["period"] == "Q2FY25")
    # stamped with the quarter's own end: the merge keeps the newest rows by stamp, so an old quarter never outranks a live one
    assert {r["as_of"] for r in d["segment_mix"] if r["period"] == "Q2FY25"} == {"2024-09-30"}


def test_a_quarter_memory_holds_as_unit_slipped_gets_no_mix_from_its_file():
    """Jubilant's own Q4FY24 file was tagged at a tenth (F54): memory holds such a quarter in scale_held, and its segment
    amounts would be a tenth too."""
    d = {"scale_held": [{"period": "Q3FY25"}], "segment_mix": []}
    assert segments.remember(d, _doc("bse_main_ind_as_532811_q3fy25.xml"), "n1", AS_OF, AT) == 0 and d["segment_mix"] == []


def test_a_line_is_no_business_only_by_how_it_begins():
    """Blind review: "Power Adjustment Services" is a segment; "Less: Inter-segment revenue" and "Unallocated" are not."""
    for name in ("Unallocated", "Less: Inter-segment revenue", "Eliminations", "Reconciling items", "Adjustments",
                 "Un-allocated expenses"):
        assert segments.NOT_BUSINESS.search(name), name
    for name in ("Power Adjustment Services", "Bank Reconciliation Software", "Retail Banking"):
        assert not segments.NOT_BUSINESS.search(name), name
