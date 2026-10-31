"""31 Oct 2026: the restated year-ago figure site-wide. Page layouts rebuilt from the real filings' word positions (HINDUNILVR Q2FY27,
Persistent Q2FY27, Vedanta Q2FY27), the figures the real ones print; no network."""
from __future__ import annotations

import pymupdf
from test_pdf_referee import FakeNse, filing, make_pdf
from test_restated_pdf import Sink, source

from bse_intel import pdf_referee as pr
from bse_intel import restated_pdf as rp
from bse_intel import results_table
from bse_intel.settings import pdf_reader_options

URL = "https://nsearchives.nseindia.com/corporate/RES.pdf"


def pdf_of(words: list[tuple[float, float, str]]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for x, y, text in words:
        page.insert_text((x, y), text, fontsize=5)
    return doc.tobytes()


def hul_page() -> bytes:
    """HUL's consolidated statement: header cells wrap ("ended 30th September" over its year), the label column sits in the middle."""
    w = [(164, 110, "CONSOLIDATED FINANCIAL RESULTS FOR THE QUARTER AND SIX MONTHS ENDED 30TH SEPTEMBER, 2026"), (539, 117, "(Rs in crores)"),
         (49, 128, "Unaudited results for the quarter"), (62, 135, "ended 30th September"),
         (139, 125, "Unaudited results for"), (143, 131, "the quarter ended"), (153, 138, "30th June"),
         (434, 128, "Unaudited results for six months"), (446, 135, "ended 30th September"),
         (525, 125, "Audited results for"), (529, 131, "the year ended"), (534, 138, "31st March"), (295, 134, "Particulars")]
    w += [(59, 145.5, "2026"), (107, 145.5, "2025"), (158, 145.5, "2026"), (443, 145.5, "2026"), (491, 145.5, "2025"), (540, 145.5, "2026")]
    rows = [("Revenue from operations", None), ("Sale of products", ["18,037", "15,715", "17,149", "35,186", "31,267", "63,636"]),
            ("Sale of services", ["34", "27", "35", "69", "54", "127"]),
            ("Other operating revenue", ["155", "177", "157", "312", "355", "705"]),
            ("Other income", ["160", "147", "188", "348", "348", "751"]),
            ("TOTAL INCOME", ["18,386", "16,066", "17,529", "35,915", "32,024", "65,219"]),
            ("PROFIT FOR THE PERIOD / YEAR (C = A+B)", ["2,796", "2,694", "2,680", "5,476", "5,462", "15,059"])]
    xs = [60, 108, 160, 444, 492, 541]
    for k, (label, cells) in enumerate(rows):
        y = 170 + 8 * k
        w.append((300, y, label))
        for x, c in zip(xs, cells or []):
            w.append((x, y, c))
    return pdf_of(w)


def read(payload: bytes):
    with pdf_reader_options():
        return pr.read_document(payload, ocr=False)


def test_a_header_cell_that_wraps_its_date_and_a_label_between_figures_are_read():
    rows, why = read(hul_page())
    assert rows, why
    revenue = next(r for r in rows if r.metric == "revenue")
    assert revenue.label.endswith(pr.DERIVED_LABEL)               # no revenue total printed: the sub-lines' sum, proved against total income
    assert revenue.figures == [18226.0, 15919.0, 17341.0, 35567.0, 31676.0, 64468.0]
    assert [(k, str(d)) for k, d in revenue.columns][:3] == [("quarter", "2026-09-30"), ("quarter", "2025-09-30"), ("quarter", "2026-06-30")]
    assert pr.figure_for(rows, "Q2FY26", "revenue", "CONSOLIDATED")["values"][0][0] == 15919.0
    assert pr.figure_for(rows, "Q2FY26", "pat", "CONSOLIDATED")["values"][0][0] == 2694.0


def test_the_wrapped_header_and_derived_revenue_are_off_without_the_row_fixes():
    rows, _ = pr.read_document(hul_page(), ocr=False)
    assert not rows or not any(r.columns for r in rows)


def test_revenue_is_not_derived_when_the_sub_lines_do_not_add_to_total_income():
    lines = ["Revenue from operations", "Sale of products 100 90 80", "Other operating revenue 10 9 8", "Other income 5 4 3",
             "Total income 130 103 91"]
    assert pr.derive_revenue(lines) == lines
    ok = ["Revenue from operations", "Sale of products 100 90 80", "Other operating revenue 10 9 8", "Other income 5 4 3",
          "Total income 115 103 91"]
    assert pr.derive_revenue(ok)[0].endswith("110 99 88")


def test_dates_on_staggered_baselines_are_one_header():
    w = [(247, 108, "September 30, 2026"), (309, 108, "June 30, 2026"), (349, 102, "September 30, 2025"), (371, 108, "(Restated)"),
         (401, 108, "September 30, 2026"), (450, 102, "September 30, 2025"), (523, 102, "March 31, 2026"),
         (48, 120, "Revenue from operations")]
    words = [(x, y - 5, x + 4, y, t, 0, 0, 0) for x, y, t in [(a, b, c) for a, b, c in w]]
    split = []
    for x, y, t in [(a, b, c) for a, b, c in w]:
        for k, part in enumerate(t.split(" ")):
            split.append((x + 12 * k, y - 5, x + 12 * k + 10, y, part, 0, 0, 0))
    out = pr.align_staggered_dates(split)
    assert len({round(o[1]) for o in out if o[4] in ("2025", "2026")}) == 1 and words


def test_voting_results_are_not_candidates_and_a_miss_is_a_reason_only_when_no_file_was_the_results():
    vote = filing(url="https://x/v.pdf", subject="Shareholders meeting", headline="Voting results and Srutinizers report")
    board = filing(url="https://x/c.pdf", subject="Outcome of Board Meeting", headline="Change in Board")
    assert pr.candidate_filings([vote, board], "Q2FY27") == []
    other = filing(url="https://x/q.pdf", subject="Outcome of Board Meeting", headline="Outcome")
    pdfs = {"https://x/q.pdf": make_pdf(["Notice of a board meeting"])}
    src = pr.Sources(FakeNse([other], pdfs), ocr=False)
    _, _, reasons = rp.read_company(src, "X", {"financial_metrics": [
        {"metric": "revenue", "period": "Q2FY27", "value": 1.0, "unit": "INR_CR", "basis": "CONSOLIDATED", "sources": [source("xbrl:1", 1.0, "2026-10-01")]}]})
    assert reasons and "no page names a quarter" in reasons[0]


def test_a_restatement_beyond_the_band_is_stored_only_when_screener_has_the_same_figure():
    dossier = {"financial_metrics": [
        {"metric": "revenue", "period": "Q2FY26", "value": 39868.0, "unit": "INR_CR", "basis": "CONSOLIDATED",
         "sources": [source("xbrl:res:1:Q2FY26", 39868.0, "2025-10-31")], "source_news_id": "xbrl:res:1:Q2FY26"},
        {"metric": "revenue", "period": "Q2FY27", "value": 18226.0, "unit": "INR_CR", "basis": "CONSOLIDATED",
         "sources": [source("xbrl:res:1:Q2FY27", 18226.0, "2026-10-28")], "source_news_id": "xbrl:res:1:Q2FY27"}]}
    rows, why = read(hul_page())
    with pdf_reader_options():
        none = []
        assert rp.find(dossier, rows, "Q2FY27", "CONSOLIDATED", "nse-1", URL, none, lambda m, p: None) == []
        assert none[0]["reason"].startswith("moves more than") and none[0]["restated"] == 15919.0
        assert rp.find(dossier, rows, "Q2FY27", "CONSOLIDATED", "nse-1", URL, None, lambda m, p: 16000.0) == []
        got = rp.find(dossier, rows, "Q2FY27", "CONSOLIDATED", "nse-1", URL, None, lambda m, p: 15919.4)
    assert [(r["period"], r["restated"], r["confirmed"]) for r in got] == [("Q2FY26", 15919.0, "screener")]
    assert rp.screener_matches(15919.0, 15919.9) and not rp.screener_matches(15919.0, 15935.0) and not rp.screener_matches(1.0, None)


def test_a_unit_the_layer_lost_comes_from_the_filings_own_xbrl_and_dots_for_thousands_need_screener():
    rows, _ = read(pdf_of([(20, 20, "STATEMENT OF UNAUDITED CONSOLIDATED RESULTS FOR THE QUARTER ENDED 30 SEPTEMBER 2026"),
                           (20, 34, "(f in Crnre, except as stated)"),
                           (20, 48, "Quarter ended Half year ended Year ended"),
                           (20, 58, "30.09.2026 30.06.2026 30.09.2025 30.09.2026 30.09.2025 31.03.2026"),
                           (20, 70, "Total revenue from operations 26,356 24.205 16.736 50,561 32.490 78.437"),
                           (20, 82, "Other income 510 542 264 1.052 646 1.550"), (20, 94, "Total income 26,866 24.747 17.000 51.613 33.136 79.987")]))
    assert rows and rows[0].unit is None
    entries = {("revenue", "Q2FY27"): {"metric": "revenue", "period": "Q2FY27", "value": 26356.0, "unit": "INR_CR", "basis": "CONSOLIDATED",
                                       "sources": [source("xbrl:res:1:Q2FY27", 26356.0, "2026-10-28")]}}
    fixed = rp.prepare_rows(rows, "Q2FY27", "CONSOLIDATED", entries)
    assert fixed[0].unit == 1.0 and fixed[0].figures[2] == 16736.0 and fixed[0].label.endswith(rp.DOT)
    d = {"financial_metrics": [{"metric": "revenue", "period": "Q2FY26", "value": 39868.0, "unit": "INR_CR", "basis": "CONSOLIDATED",
                                "sources": [source("xbrl:res:1:Q2FY26", 39868.0, "2025-10-31")]}, *entries.values()]}
    assert rp.find(d, rows, "Q2FY27", "CONSOLIDATED", "n", URL, None, lambda m, p: None) == []
    got = rp.find(d, rows, "Q2FY27", "CONSOLIDATED", "n", URL, None, lambda m, p: 16736.0 if p == "Q2FY26" else None)
    assert got and got[0]["restated"] == 16736.0


RESTATED = {"restated_figures": [
    {"metric": "revenue", "period": "Q2FY26", "basis": "CONSOLIDATED", "unit": "INR_CR", "original": 16241.0, "restated": 15919.0,
     "restated_in": "Q2FY27", "restated_news_id": "nse-1", "restated_url": URL, "read": "pdf_text"},
    {"metric": "pat", "period": "Q2FY26", "basis": "CONSOLIDATED", "unit": "INR_CR", "original": 2700.0, "restated": 2694.0,
     "restated_in": "Q3FY27", "restated_news_id": "nse-2", "restated_url": URL, "read": "pdf_text"}]}


def test_restated_base_follows_the_filing_the_growth_belongs_to():
    assert rp.restated_base(RESTATED, "revenue", "Q2FY26", "CONSOLIDATED", "Q2FY27")["restated"] == 15919.0
    assert rp.restated_base(RESTATED, "revenue", "Q2FY26", "STANDALONE", "Q2FY27") is None
    assert rp.restated_base(RESTATED, "pat", "Q2FY26", "CONSOLIDATED", "Q2FY26") is None       # restated in a later file than the quarter's own
    assert rp.restated_base(RESTATED, "pat", "Q2FY26", "CONSOLIDATED", "Q3FY27")["restated"] == 2694.0


def entry(period, sales, profit):
    return {"table": "quarters", "period": period, "basis": "CONSOLIDATED", "family": "corporate", "lab": {"by": "file"},
            "source_news_id": f"nse-{period}", "rows": {"Sales": sales, "Operating Profit": sales / 5, "OPM %": 20.0, "Net Profit": profit}}


def test_the_results_table_works_growth_against_the_restated_year_ago_figure():
    dossier = {**RESTATED, "statements": [entry("Q2FY26", 16241.0, 2700.0), entry("Q2FY27", 18226.0, 2796.0)]}
    table = results_table.table_of(dossier, "Q2FY27")
    assert table["revenue"]["prev_year"] == 15919.0 and table["revenue"]["yoy_pct"] == round((18226 / 15919 - 1) * 100, 1)
    assert table["pat"]["prev_year"] == 2700.0            # restated in a filing later than this quarter's: its base stays
    plain = results_table.table_of({**dossier, "restated_figures": []}, "Q2FY27")
    assert plain["revenue"]["prev_year"] == 16241.0
    # a base that is not the quantity the restatement was made against is left alone
    other = {**dossier, "statements": [entry("Q2FY26", 16000.0, 2700.0), entry("Q2FY27", 18226.0, 2796.0)]}
    assert results_table.table_of(other, "Q2FY27")["revenue"]["prev_year"] == 16000.0


def test_the_screener_store_reads_the_stored_page_on_the_basis(monkeypatch):
    from bse_intel import screener_download as sd
    from bse_intel import screener_fill

    class FakeSink:
        def list_objects(self, prefix):
            return ["raw/screener/2026-10-28/VEDL_c.html.gz", "raw/screener/2026-10-28/VEDL_s.html.gz"]

        def get_object(self, key):
            return sd.pack("<html>" + key[-14:-8] + "</html>")

    monkeypatch.setattr(screener_fill, "parse_page", lambda body: {"basis": "CONSOLIDATED" if "VEDL_c" in body else "STANDALONE",
                                                                  "quarters": {"Q2FY26": {"revenue": 16736.0, "pat": 1000.0}}})
    store = rp.ScreenerStore(FakeSink())
    assert store.figure("VEDL", "CONSOLIDATED", "revenue", "Q2FY26") == 16736.0
    assert store.figure("VEDL", "CONSOLIDATED", "revenue", "Q1FY26") is None
    assert store.figure("OTHER", "CONSOLIDATED", "revenue", "Q2FY26") is None


def test_the_screener_store_reads_a_years_net_profit_from_the_annual_section(monkeypatch):
    from bse_intel import screener_download as sd
    from bse_intel import screener_view as sv

    class FakeSink:
        def list_objects(self, prefix):
            return ["raw/screener/2026-10-28/ABC_c.html.gz"]

        def get_object(self, key):
            return sd.pack("<html>c</html>")

    monkeypatch.setattr(sv, "parse_page", lambda body: {"basis": "CONSOLIDATED", "tables": {"annual": {"Net Profit": {"FY25": 541.0}}}})
    store = rp.ScreenerStore(FakeSink())
    assert store.figure("ABC", "CONSOLIDATED", "pat", "FY25") == 541.0 and store.figure("ABC", "CONSOLIDATED", "pat", "FY24") is None
