"""F202 (TODO 104): a restated comparative kept beside the original, read from the later filing's PDF text layer.

The figures are the real ones of the hard-PDF set (360ONE's consolidated Q3FY24 revenue 647.68 in its own file, 629.79 printed
in the next one); the PDFs themselves are rebuilt here, because the real ones' text layers are garbled and only OCR reads them."""
from __future__ import annotations

from test_pdf_referee import FakeNse, filing, make_pdf

from bse_intel import pdf_referee as pr
from bse_intel import restated_pdf as rp
from bse_intel.models import FinancialMetric
from bse_intel.settings import card_yoy_restated
from bse_intel.xbrl import XbrlResult

CONSOLIDATED_Q4 = [
    "Statement of Consolidated Audited Financial Results for the quarter and year ended 31 March 2024",
    "(Rs. in crore)",
    "Quarter ended Quarter ended Quarter ended Year ended Year ended",
    "Particulars 31.03.2024 31.12.2023 31.03.2023 31.03.2024 31.03.2023",
    "1 Revenue from operations 791.74 629.79 479.91 2,507.03 1,974.66",
    "2 Other income 1.10 1.00 0.90 2.10 4.00",
    "3 Profit before tax 300.00 250.00 200.00 1,000.00 800.00",
    "4 Net Profit for the period 242.61 192.11 155.41 804.21 657.89",
]
STANDALONE_Q4 = [
    "Statement of Standalone Audited Financial Results for the quarter and year ended 31 March 2024",
    "(Rs. in crore)",
    "Quarter ended Quarter ended Quarter ended Year ended Year ended",
    "Particulars 31.03.2024 31.12.2023 31.03.2023 31.03.2024 31.03.2023",
    "1 Revenue from operations 100.00 90.00 80.00 400.00 300.00",
    "4 Net Profit for the period 50.00 40.00 30.00 150.00 120.00",
]


def source(news_id, value, as_of, restated_from=None, basis="CONSOLIDATED"):
    return {"news_id": news_id, "as_of": as_of, "value": value, "unit": "INR_CR", "basis": basis,
            **({"restated_from": restated_from} if restated_from else {})}


def dossier():
    return {"financial_metrics": [
        {"metric": "revenue", "period": "Q3FY24", "value": 647.68, "unit": "INR_CR", "basis": "CONSOLIDATED",
         "sources": [source("xbrl:res:1:Q3FY24", 647.68, "2024-01-30")], "source_news_id": "xbrl:res:1:Q3FY24"},
        {"metric": "pat", "period": "Q3FY24", "value": 192.11, "unit": "INR_CR", "basis": "CONSOLIDATED",
         "sources": [source("xbrl:res:1:Q3FY24", 192.11, "2024-01-30")], "source_news_id": "xbrl:res:1:Q3FY24"},
        {"metric": "revenue", "period": "Q4FY24", "value": 791.74, "unit": "INR_CR", "basis": "CONSOLIDATED",
         "sources": [source("xbrl:res:1:Q4FY24", 791.74, "2024-04-23")], "source_news_id": "xbrl:res:1:Q4FY24"},
    ]}


def rows():
    got, why = pr.read_document(make_pdf(CONSOLIDATED_Q4, STANDALONE_Q4), ocr=False)
    assert got, why
    return got


def test_a_difference_is_beyond_half_a_unit_of_the_printed_decimals():
    assert rp.decimals_of(647.68) == 2 and rp.decimals_of(1259.0) == 0
    assert rp.differs(647.68, 629.79)
    assert not rp.differs(647.68, 647.68)
    assert not rp.differs(647.68, 647.7)      # a figure printed to one decimal is rounding of the other
    assert not rp.differs(1259.4, 1259.0)     # to the whole crore
    assert rp.differs(1259.0, 1260.0)


def test_the_restated_figure_is_found_next_to_the_original_on_the_same_basis():
    found = rp.find(dossier(), rows(), "Q4FY24", "CONSOLIDATED", "nse-77", "https://x/RES.pdf")
    assert [(r["metric"], r["period"]) for r in found] == [("revenue", "Q3FY24")]   # profit 192.11 is printed as filed
    r = found[0]
    assert (r["original"], r["restated"], r["restated_in"]) == (647.68, 629.79, "Q4FY24")
    assert r["original_news_id"] == "xbrl:res:1:Q3FY24" and r["restated_news_id"] == "nse-77" and r["read"] == "pdf_text"
    assert r["basis"] == "CONSOLIDATED"
    # the standalone page's 90.00 never stands for the consolidated quarter
    standalone = rp.comparatives(rows(), "Q4FY24", "STANDALONE")
    assert {c["value"] for c in standalone if c["period"] == "Q3FY24"} == {90.0, 40.0}


def test_no_original_in_memory_no_restatement():
    d = dossier()
    d["financial_metrics"][0]["sources"] = [source("nse-5", 647.68, "2024-01-30", restated_from="Q4FY24")]
    assert rp.find(d, rows(), "Q4FY24", "CONSOLIDATED") == []       # memory holds only a comparative, not the period's own file


def test_the_history_keeps_the_original_and_the_store_the_latest_reading():
    d = dossier()
    before = [dict(e) for e in d["financial_metrics"]]
    rec = rp.find(d, rows(), "Q4FY24", "CONSOLIDATED", "nse-77")
    assert rp.merge(d, rec) == 1
    assert d["financial_metrics"] == before and d["financial_metrics"][0]["value"] == 647.68
    assert d["restated_figures"][0]["restated"] == 629.79
    assert rp.merge(d, rec) == 0                                    # again: nothing changes
    newer = [{**rec[0], "restated": 630.0, "restated_in": "Q1FY25"}]
    rp.merge(d, newer)
    assert d["restated_figures"][0]["restated"] == 630.0
    rp.merge(d, rec)                                                # an older filing never overrides a newer reading
    assert d["restated_figures"][0]["restated_in"] == "Q1FY25"
    rp.merge(d, [], [("revenue", "Q3FY24", "CONSOLIDATED", "Q2FY25")])   # a later file prints it unchanged: no longer restated
    assert "restated_figures" not in d


def result(period="Q3FY25", basis="CONSOLIDATED", revenue=700.0, yoy=8.1, profit=-5.0):
    return XbrlResult(kind="RESULTS", basis=basis, period=period, metrics=[
        FinancialMetric(metric="revenue", period=period, value=revenue, yoy_pct=yoy),
        FinancialMetric(metric="pat", period=period, value=profit, yoy_pct=-120.0)])


def stored(d):
    rp.merge(d, rp.find(d, rows(), "Q4FY24", "CONSOLIDATED", "nse-77"))
    return d


def test_the_card_yoy_uses_the_restated_base_and_says_so():
    d = stored(dossier())
    tagged = result()
    assert rp.apply_to_result(tagged, d) == 1
    rev = tagged.metrics[0]
    assert rev.yoy_pct == round((700.0 / 629.79 - 1) * 100, 1) == 11.1
    assert rev.yoy_note == "vs restated"
    assert "YoY +11.1% vs restated" in tagged.table()
    assert tagged.metrics[1].yoy_note is None                       # a loss has no percentage and is left alone


def test_other_basis_later_file_or_no_base_leaves_the_yoy_alone():
    d = stored(dossier())
    for tagged in (result(basis="STANDALONE"), result(period="Q3FY23"), result(revenue=-1.0)):
        assert rp.apply_to_result(tagged, d) == 0 and tagged.metrics[0].yoy_note is None
    assert rp.apply_to_result(result(), dossier()) == 0             # nothing restated stored
    # a restatement printed by a file later than this one is not this file's base
    d["restated_figures"][0]["restated_in"] = "Q1FY26"
    assert rp.apply_to_result(result(), d) == 0


def test_the_card_lines_carry_vs_restated():
    from bse_intel import results_card as rc
    d = stored(dossier())
    tagged = result()
    rp.apply_to_result(tagged, d)
    rev = tagged.metrics[0]
    assert rc._line(rev) == "- revenue Q3FY25: 700 Cr, YoY +11.1% vs restated"
    assert rc._line(rev) in tagged.table()                          # the quote still finds its table line
    assert rc._changes(rev) == "+11.1% YoY vs restated"


def test_the_switch_is_off_by_default(monkeypatch):
    monkeypatch.delenv("CARD_YOY_RESTATED", raising=False)
    assert card_yoy_restated() is False
    monkeypatch.setenv("CARD_YOY_RESTATED", "1")
    assert card_yoy_restated() is True


class Sink:
    def __init__(self, d):
        self.d, self.puts = d, 0

    def get_dossier(self, scrip):
        return self.d

    def put_dossier(self, scrip, d):
        self.d, self.puts = d, self.puts + 1


def test_the_maintenance_pass_reads_the_text_layer_and_stores_what_it_proves():
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    nse = FakeNse([filing(url=url)], {url: make_pdf(CONSOLIDATED_Q4)})
    sink = Sink(dossier())
    stats = rp.run(nse, sink, {"1": "X"}, quarters=1)
    assert (stats["companies"], stats["restated"], stats["stored"]) == (1, 1, 1)
    assert sink.d["restated_figures"][0]["restated"] == 629.79 and sink.d["financial_metrics"][0]["value"] == 647.68
    assert stats["reasons"] == {}
    assert rp.run(nse, sink, {"1": "X"}, quarters=1)["stored"] == 0   # nothing new: no write


def test_a_comparative_memory_holds_no_original_for_never_clears_a_restatement():
    """Review of #168: only a figure compared with memory's original and found the same clears an older restatement."""
    d = stored(dossier())
    d["financial_metrics"][0]["sources"] = [source("nse-5", 647.68, "2024-01-30", restated_from="Q4FY24")]
    _, cleared, _ = rp.read_company(_Src(rows()), "X", d, quarters=1)
    assert ("revenue", "Q3FY24", "CONSOLIDATED", "Q4FY24") not in cleared
    assert d["restated_figures"][0]["restated"] == 629.79


def test_the_pass_keeps_what_another_writer_stored_while_the_pdfs_were_read():
    """Review of #168: the PDFs take minutes; a card or deals write in that gap is not overwritten."""
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    nse = FakeNse([filing(url=url)], {url: make_pdf(CONSOLIDATED_Q4)})
    sink = Sink(dossier())
    real = sink.get_dossier
    calls = []

    def get(scrip):
        calls.append(scrip)
        got = real(scrip)
        if len(calls) == 2:          # the re-read just before the write: a deal arrived meanwhile
            got = {**got, "deals": [{"id": "d1"}]}
        return got
    sink.get_dossier = get
    rp.run(nse, sink, {"1": "X"}, quarters=1)
    assert sink.d["deals"] == [{"id": "d1"}] and sink.d["restated_figures"][0]["restated"] == 629.79


class _Src:
    def __init__(self, got):
        self.got = got

    def filings(self, symbol, period):
        return [filing(url="u")]

    def rows(self, url):
        return self.got, ""


def test_a_dry_run_lists_what_it_found_and_writes_nothing():
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    nse = FakeNse([filing(url=url)], {url: make_pdf(CONSOLIDATED_Q4)})
    sink = Sink(dossier())
    stats = rp.run(nse, sink, {"1": "X"}, quarters=1, dry_run=True)
    assert sink.puts == 0 and "restated_figures" not in sink.d and stats["stored"] == 0
    assert [(f["symbol"], f["metric"], f["original"], f["restated"]) for f in stats["found"]] == [("X", "revenue", 647.68, 629.79)]


TITAN_Q3 = [   # Titan's real Q3FY26 layout: revenue split into sub-lines with no total; "Total income" includes other income
    "Statement of Consolidated Unaudited Financial Results for the quarter and nine months ended 31 December 2025",
    "(Rs. in crore)",
    "Particulars 3 months ended 3 months ended 3 months ended 9 months ended 9 months ended Year ended",
    "31-12-2025 30-09-2025 31-12-2024 31-12-2025 31-12-2024 31-03-2025",
    "I. Revenue from operations",
    "- Sale of products/ services 24,915 16,461 17,550 56,190 43,246 57,143",
    "- Other operating revenues 501 2,264 190 4,474 2,294 3,313",
    "II. Other income 151 112 128 368 370 486",
    "III. Total income (I +II) 25,567 18,837 17,868 61,032 45,910 60,942",
]


def test_total_income_is_never_read_as_a_restated_revenue():
    """Restated-pdf trial, 27 Oct 2026: Titan's four 'restatements' were its Total income (17,868) against revenue (17,740)."""
    got, why = pr.read_document(make_pdf(TITAN_Q3), ocr=False)
    assert got, why
    d = {"financial_metrics": [
        {"metric": "revenue", "period": "Q3FY25", "value": 17740.0, "unit": "INR_CR", "basis": "CONSOLIDATED",
         "sources": [source("xbrl:res:1:Q3FY25", 17740.0, "2025-02-04")], "source_news_id": "xbrl:res:1:Q3FY25"}]}
    assert rp.find(d, got, "Q3FY26", "CONSOLIDATED") == []
    assert all(c["metric"] != "revenue" for c in rp.comparatives(got, "Q3FY26", "CONSOLIDATED"))
