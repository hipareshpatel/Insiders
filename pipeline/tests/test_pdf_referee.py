"""The PDF referee (pdf_referee.py): a small results PDF made in the test, a fake NSE client, no network."""

from __future__ import annotations

import pymupdf
import pytest

from bse_intel import pdf_referee as pr
from bse_intel.bse import AttachmentError
from bse_intel.models import Filing
from bse_intel.nse import SourceBlockedError

STANDALONE_PAGE = [
    "Statement of Standalone Unaudited Financial Results for the quarter and half year ended 30 September 2026",
    "(Rs. in crore)",
    "Quarter ended Quarter ended Quarter ended Half year ended Year ended",
    "Particulars 30.09.2026 30.06.2026 30.09.2025 30.09.2026 31.03.2026",
    "1 Revenue from operations 120.50 110.25 100.10 230.75 440.00",
    "2 Other income 1.10 1.00 0.90 2.10 4.00",
    "3 Profit before tax 16.00 13.00 12.00 29.00 53.00",
    "4 Net Profit for the period 12.30 10.10 9.00 22.40 40.00",
    "5 Earnings per share (not annualised)",
    "Basic (in Rs.) 1.23 1.01 0.90 2.24 4.00",
]
CONSOLIDATED_PAGE = [
    "Statement of Consolidated Unaudited Financial Results for the quarter ended 30 September 2026",
    "(Rs. in lakhs)",
    "Quarter ended 30.09.2026 30.06.2026 30.09.2025 Year ended 31.03.2026",
    "Revenue from operations 20,000.00 19,000.00 18,000.00 76,000.00",
    "Net Profit for the period 2,100.00 2,000.00 1,900.00 8,000.00",
]


def make_pdf(*pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page(width=900, height=842)
        for i, line in enumerate(lines):
            page.insert_text((20, 40 + 16 * i), line, fontsize=8)
    return doc.tobytes()


def filing(url="https://nsearchives.nseindia.com/corporate/RES.pdf", subject="Financial Results", headline="Results for the quarter"):
    when = "2026-10-20T10:00:00+05:30"
    return Filing(news_id="nse-9", scrip_code="1", company_name="X", symbol="X", headline=headline, subject=subject,
                  category="", subcategory=subject, filed_at=when, filing_date=when[:10], pdf_url=url)


class FakeNse:
    def __init__(self, filings, pdfs, error=None):
        self.filings, self.pdfs, self.error = filings, pdfs, error
        self.fetches: list[str] = []
        self.lists: list[tuple] = []

    def announcements(self, day_from, day_to=None, symbol=None, scrip_for=None):
        self.lists.append((day_from, day_to, symbol))
        if isinstance(self.error, SourceBlockedError):
            raise self.error
        return self.filings

    def fetch(self, url, max_bytes=0):
        self.fetches.append(url)
        if isinstance(self.error, AttachmentError):
            raise self.error
        return self.pdfs.get(url)


def pair(period="Q2FY27", metric="revenue", basis="STANDALONE", ours=120.5, theirs=125.0, official=125.0,
         verdict="screener_matches_official", symbol="X"):
    return {"scrip": "1", "symbol": symbol, "basis": basis, "period": period, "metric": metric, "class": "mismatch",
            "memory_value": str(ours), "screener_value": str(theirs), "official_value": "" if official is None else str(official),
            "verdict": verdict}


def rows_of(pdf: bytes):
    rows, why = pr.read_document(pdf, ocr=False)
    assert rows, why
    return rows


def test_the_row_figure_is_read_from_the_right_column_and_basis():
    rows = rows_of(make_pdf(STANDALONE_PAGE, CONSOLIDATED_PAGE))
    quarter = pr.figure_for(rows, "Q2FY27", "revenue", "STANDALONE")
    assert [v for v, _, _ in quarter["values"]] == [120.5]
    assert [v for v, _, _ in pr.figure_for(rows, "Q1FY27", "revenue", "STANDALONE")["values"]] == [110.25]
    # the same date is the quarter's and the half year's column: the group words tell them apart; a year is its own column
    assert [v for v, _, _ in pr.figure_for(rows, "FY26", "revenue", "STANDALONE")["values"]] == [440.0]
    assert [v for v, _, _ in pr.figure_for(rows, "Q2FY27", "pat", "STANDALONE")["values"]] == [12.3]
    assert [v for v, _, _ in pr.figure_for(rows, "Q2FY27", "eps", "STANDALONE")["values"]] == [1.23]
    # the consolidated page is in lakh and its group words come one before a run of dates
    assert [v for v, _, _ in pr.figure_for(rows, "Q2FY27", "revenue", "CONSOLIDATED")["values"]] == [200.0]
    assert [v for v, _, _ in pr.figure_for(rows, "FY26", "pat", "CONSOLIDATED")["values"]] == [80.0]
    # profit before tax and other income are not the lines asked for
    assert all(r.label.lower().find("before") < 0 and r.label.lower().find("other") < 0 for r in rows)


def test_verdicts_ours_screener_xbrl_none():
    pdf = make_pdf(STANDALONE_PAGE)
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    src = pr.Sources(FakeNse([filing()], {url: pdf}), ocr=False)
    assert pr.referee_pair(src, pair(ours=120.5, theirs=125.0, official=125.0))["pdf_verdict"] == "pdf_matches_ours"
    got = pr.referee_pair(src, pair(ours=119.0, theirs=121.0, official=130.0))
    assert got["pdf_verdict"] == "pdf_matches_screener" and got["pdf_value"] == 120.5 and got["matches"] == "screener"
    assert pr.referee_pair(src, pair(ours=119.0, theirs=121.0, official=120.5))["pdf_verdict"] == "pdf_matches_xbrl"
    none = pr.referee_pair(src, pair(ours=119.0, theirs=131.0, official=130.0))
    assert none["pdf_verdict"] == "pdf_matches_none" and none["pdf_value"] == 120.5
    # EPS to the hundredth
    assert pr.referee_pair(src, pair(metric="eps", ours=1.23, theirs=1.3, official=1.3))["pdf_verdict"] == "pdf_matches_ours"


def test_a_pdf_is_downloaded_once_for_all_its_pairs():
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    nse = FakeNse([filing()], {url: make_pdf(STANDALONE_PAGE)})
    out = pr.run(nse, [pair(), pair(metric="pat", ours=12.3, theirs=12.0, official=12.0), pair(period="FY26", ours=440.0, theirs=441.0, official=441.0)],
                 ocr=False)
    assert nse.fetches == [url] and len(nse.lists) == 2           # one list a period, one download
    assert out["calls"] == {"announcement_lists": 2, "pdfs": 1}
    assert [r["pdf_verdict"] for r in out["rows"]] == ["pdf_matches_ours"] * 3


def test_a_dropped_nil_cell_is_unsure_not_a_match():
    page = list(STANDALONE_PAGE)
    page[4] = "1 Revenue from operations 120.50 110.25 100.10 440.00"      # a column lost: the figures would slide
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    src = pr.Sources(FakeNse([filing()], {url: make_pdf(page)}), ocr=False)
    got = pr.referee_pair(src, pair(ours=120.5))
    assert got["pdf_verdict"] == "pdf_unsure" and "4 figures" in got["reason"] and got["pdf_value"] is None


def test_unsure_when_the_unit_basis_or_columns_are_not_proven():
    no_unit = [l for l in STANDALONE_PAGE if "crore" not in l]
    ambiguous = [STANDALONE_PAGE[0], STANDALONE_PAGE[1], "Particulars 30.09.2026 30.06.2026 30.09.2025 30.09.2026 31.03.2026"] + STANDALONE_PAGE[4:]
    wrong_basis = ["Statement of Consolidated Unaudited Financial Results"] + STANDALONE_PAGE[1:]
    for lines, word in ((no_unit, "unit"), (ambiguous, "group words"), (wrong_basis, "")):
        url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
        src = pr.Sources(FakeNse([filing()], {url: make_pdf(lines)}), ocr=False)
        got = pr.referee_pair(src, pair(ours=120.5, theirs=131.0, official=130.0))
        if word:
            assert got["pdf_verdict"] == "pdf_unsure" and word in got["reason"], got
        else:   # a consolidated table is not the standalone figure asked for: no row of the right basis, never a match
            assert got["pdf_verdict"] != "pdf_matches_ours" and got["pdf_value"] is None, got


def test_unreadable_reasons():
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    none = pr.referee_pair(pr.Sources(FakeNse([], {}), ocr=False), pair())
    assert none["pdf_verdict"] == "pdf_unreadable" and "no results filing" in none["reason"]
    missing = pr.referee_pair(pr.Sources(FakeNse([filing()], {}), ocr=False), pair())
    assert missing["pdf_verdict"] == "pdf_unreadable" and "404" in missing["reason"]
    junk = pr.referee_pair(pr.Sources(FakeNse([filing()], {url: b"not a pdf"}), ocr=False), pair())
    assert junk["pdf_verdict"] == "pdf_unreadable" and junk["reason"]
    down = pr.referee_pair(pr.Sources(FakeNse([filing()], {}, error=AttachmentError("reset")), ocr=False), pair())
    assert down["pdf_verdict"] == "pdf_unreadable" and "download failed" in down["reason"]
    blank = pr.referee_pair(pr.Sources(FakeNse([filing()], {url: make_pdf(["Notice of a board meeting"])}), ocr=False), pair())
    assert blank["pdf_verdict"] == "pdf_unreadable"


def test_candidate_filings_keep_results_not_intimations():
    keep = filing(subject="Financial Results")
    outcome = filing(url="https://x/o.pdf", subject="Outcome of Board Meeting", headline="Outcome")
    notice = filing(url="https://x/n.pdf", subject="Board Meeting Intimation", headline="Intimation of board meeting to consider results")
    call = filing(url="https://x/c.pdf", subject="Analysts/Institutional Investor Meet/Con. Call Updates", headline="Earnings call transcript")
    nopdf = filing(url=None)
    got = pr.candidate_filings([outcome, notice, call, nopdf, keep], "Q2FY27")
    assert [f.pdf_url for f in got] == [keep.pdf_url, outcome.pdf_url]


def test_only_open_pairs_are_taken_and_limit_and_block_leave_not_run():
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    rows = [pair(verdict="neither", symbol="A"), pair(verdict="no_file", symbol="B"), pair(verdict="ours_matches_official", symbol="C"),
            pair(verdict="both_match", symbol="D"), pair(verdict="not_run", symbol="E"), pair(verdict="screener_matches_official", symbol="F")]
    assert [r["symbol"] for r in pr.open_pairs(rows)] == ["A", "B", "F"]
    out = pr.run(FakeNse([filing()], {url: make_pdf(STANDALONE_PAGE)}), rows, limit=2, ocr=False)
    assert out["verdicts"] == {"pdf_matches_ours": 2, "not_run": 1} and out["left_out"] == 3
    assert [r["reason"] for r in out["rows"] if r["pdf_verdict"] == "not_run"] == ["limit"]
    blocked = pr.run(FakeNse([filing()], {}, error=SourceBlockedError("403")), rows, ocr=False)
    assert blocked["blocked"] and blocked["verdicts"] == {"not_run": 3}
    late = pr.run(FakeNse([filing()], {url: make_pdf(STANDALONE_PAGE)}), rows, time_budget=-1, ocr=False,
                  clock=iter([0, 5, 6, 7, 8, 9, 10]).__next__)
    assert late["out_of_time"] and late["verdicts"] == {"not_run": 3}


def test_csv_markdown_and_input_round_trip():
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    text = ("scrip,symbol,basis,period,metric,class,memory_value,screener_value,official_value,verdict\n"
            "1,X,STANDALONE,Q2FY27,revenue,mismatch,120.5,125,125,screener_matches_official\n"
            "1,X,STANDALONE,Q2FY27,pat,mismatch,12.3,12,12.3,ours_matches_official\n")
    rows = pr.load_csv(text)
    out = pr.run(FakeNse([filing()], {url: make_pdf(STANDALONE_PAGE)}), rows, ocr=False)
    assert out["pairs"] == 1 and out["rows"][0]["pdf_verdict"] == "pdf_matches_ours"
    csv_text = pr.to_csv(out)
    assert csv_text.splitlines()[0].startswith("scrip,symbol,basis") and "pdf_matches_ours" in csv_text and url in csv_text
    md = pr.to_markdown(out, "2026-10-26")
    assert "PDF referee, 2026-10-26" in md and "| screener_matches_official |" in md
    assert "pdf_matches_ours" in pr.render(out)
    assert pr.to_json(out).count("rows") == 0


@pytest.mark.parametrize("period,expect", [("Q2FY27", ("quarter", "2026-09-30")), ("Q4FY26", ("quarter", "2026-03-31")), ("FY26", ("year", "2026-03-31"))])
def test_target_column(period, expect):
    kind, day = pr.target_column(period)
    assert (kind, day.isoformat()) == expect


def test_the_sample_is_seeded_half_revenue_half_profit_and_never_eps():
    rows = [{"symbol": f"S{i}", "period": "Q1FY26", "metric": m, "verdict": v}
            for i in range(30) for m in ("revenue", "pat", "eps") for v in ("ours_matches_official", "neither")]
    one, two = pr.sample_pairs(rows, 10), pr.sample_pairs(rows, 10)
    assert one == two and len(one) == 10
    assert sorted(r["metric"] for r in one) == ["pat"] * 5 + ["revenue"] * 5
    assert all(r["verdict"] == "ours_matches_official" for r in one)
    assert pr.sample_pairs(rows, 10, seed=1) != one


def test_proven_rows_that_disagree_are_unsure_not_a_match():
    # one row agreeing among rows that disagree with each other never confirms the figure (review)
    v, matches, value, label = pr.verdict_of([(120.5, "Revenue", 1), (131.0, "Total income", 1)], 120.5, 125.0, 120.5, "revenue")
    assert v == "pdf_unsure" and value is None and "conflicting rows" in label
    assert pr.verdict_of([(120.5, "Revenue", 1), (120.5, "Revenue", 3)], 120.5, 125.0, 120.5, "revenue")[0] == "pdf_matches_ours"


def test_the_sample_run_catches_a_file_the_pdf_disagrees_with():
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    nse = FakeNse([filing()], {url: make_pdf(STANDALONE_PAGE)})   # the PDF prints 120.5
    rows = [{**pair(ours=119.0, theirs=125.0, official=119.0), "verdict": "ours_matches_official"}]
    out = pr.run(nse, rows, ocr=False, sample=1)
    assert [r["pdf_verdict"] for r in out["rows"]] == ["pdf_matches_none"]
    assert out["sample"] == {"drawn": 1, "pool": 1, "seed": 26}
    assert "upper bound" in pr.to_markdown(out, "2026-10-26")
    with pytest.raises(ValueError):
        pr.sample_pairs(rows, 0)


def test_one_figure_printed_at_two_precisions_is_not_a_conflict():
    assert pr.verdict_of([(120.48, "Revenue", 1), (120.5, "Revenue", 4)], 120.48, 125.0, 120.48, "revenue")[0] == "pdf_matches_ours"
    assert pr.verdict_of([(1.23, "EPS", 1), (1.2, "EPS", 4)], 1.23, 1.5, 1.23, "eps")[0] == "pdf_matches_ours"
    assert pr.verdict_of([(5000.9, "Revenue", 1), (5000.0, "Revenue", 4)], 5000.9, 5100.0, 5000.9, "revenue")[0] == "pdf_matches_ours"
    assert pr.verdict_of([(120.5, "Revenue", 1), (121.0, "Total income", 1)], 120.5, 125.0, 120.5, "revenue")[0] == "pdf_unsure"


# --- lenders' statements, column-order text layers, the column proof (TODO 91, 26 Oct 2026) ----------------------------

Q4_DATES = ["31.03.2024", "31.12.2023", "31.03.2023", "31.03.2024", "31.03.2023"]
Q4_COLUMNS = [430, 500, 570, 640, 710]
LENDER_ROWS = [
    ("Statement of Consolidated Audited Financial Results for the quarter / year ended 31 March 2024", None),
    ("(Rs. in Lakhs except per share data)", None),
    ("Particulars", Q4_DATES),
    ("Quarter ended and Year ended", None),
    ("1 Income from operations", None),
    ("I. Interest Income", ["16,051.28", "15,085.64", "12,845.96", "59,308.18", "38,672.03"]),
    ("iii. Fees and Commission income", ["616.81", "572.40", "524.91", "2,330.29", "1,640.12"]),
    ("Total revenue from Operations", ["18,285.22", "16,876.26", "14,931.25", "66,145.66", "42,390.12"]),
    ("b. Other Income", ["7.11", "-", "0.34", "7.11", "0.34"]),
    ("Total Income", ["18,292.33", "16,876.26", "14,931.59", "66,152.77", "42,390.47"]),
    ("Net Profit for the period", ["5,081.67", "4,200.20", "3,619.95", "17,357.28", "9,381.13"]),
]
WORDS_LINE = "Quarter ended and Year ended"


def make_grid_pdf(rows, columns=Q4_COLUMNS, skip=(), column_order=False, pitch=16, offset=0) -> bytes:
    """Rows of (label, figures or None) with each figure at its column's x. ``skip`` leaves cells blank; ``column_order`` writes
    every label first and then the figures column by column, as some text layers run."""
    doc = pymupdf.open()
    page = doc.new_page(width=900, height=842)
    placed = [(20, 40 + pitch * i, label, figs) for i, (label, figs) in enumerate(rows)]
    cells = [(columns[k], y + (0 if label == "Particulars" else offset), f) for _, y, label, figs in placed if figs for k, f in enumerate(figs)
             if label == "Particulars" or k not in skip]
    for x, y, label, _ in placed:
        page.insert_text((x, y), label, fontsize=8)
    if column_order:
        cells.sort(key=lambda c: (c[0], c[1]))
    for x, y, f in cells:
        page.insert_text((x, y), f, fontsize=8)
    return doc.tobytes()


def revenue_of(pdf, period, basis="CONSOLIDATED", metric="revenue"):
    return [round(v, 4) for v, _, _ in pr.figure_for(rows_of(pdf), period, metric, basis)["values"]]


def test_a_lenders_revenue_is_revenue_from_operations_not_a_sub_line_or_total_income():
    pdf = make_grid_pdf(LENDER_ROWS)
    labels = [r.label for r in rows_of(pdf) if r.metric == "revenue"]
    assert labels == ["Total revenue from Operations"]                    # not "I. Interest Income", not "Total Income"
    assert revenue_of(pdf, "Q4FY24") == [182.8522] and revenue_of(pdf, "FY24") == [661.4566]
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    got = pr.referee_pair(pr.Sources(FakeNse([filing()], {url: pdf}), ocr=False),
                          pair(period="Q4FY24", basis="CONSOLIDATED", ours=182.85, theirs=170.0, official=182.85))
    assert got["pdf_verdict"] == "pdf_matches_ours" and round(got["pdf_value"], 2) == 182.85


def test_a_banks_interest_earned_then_total_income_only_when_nothing_better_is_printed():
    bank = [("Statement of Standalone Audited Financial Results for the quarter and year ended 31 March 2024", None),
            ("(Rs. in Crore)", None), ("Particulars", Q4_DATES), (WORDS_LINE, None),
            ("1. Interest earned (a)+(b)+(c)+(d)", ["1,000.50", "990.00", "900.00", "3,900.00", "3,400.00"]),
            ("2. Other income", ["100.00", "90.00", "80.00", "350.00", "300.00"]),
            ("3. Total income (1+2)", ["1,100.50", "1,080.00", "980.00", "4,250.00", "3,700.00"])]
    assert revenue_of(make_grid_pdf(bank), "Q4FY24", "STANDALONE") == [1000.5]
    only = make_grid_pdf([r for r in bank if not r[0].startswith("1. Interest")])
    assert revenue_of(only, "Q4FY24", "STANDALONE") == [1100.5]
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    # a difference from "Total income" is a definition (it includes other income), never a verdict
    unsure = pr.referee_pair(pr.Sources(FakeNse([filing()], {url: only}), ocr=False),
                             pair(period="Q4FY24", basis="STANDALONE", ours=1000.5, theirs=1000.5, official=1000.5))
    assert unsure["pdf_verdict"] == "pdf_unsure" and "Total income" in unsure["reason"]
    agree = pr.referee_pair(pr.Sources(FakeNse([filing()], {url: only}), ocr=False),
                            pair(period="Q4FY24", basis="STANDALONE", ours=1100.5, theirs=1000.5, official=1100.5))
    assert agree["pdf_verdict"] == "pdf_unsure" and agree["pdf_value"] is None     # even a match: it never settles a pair


def test_a_text_layer_that_runs_column_by_column_is_rebuilt_by_position(monkeypatch):
    pdf = make_grid_pdf(LENDER_ROWS, column_order=True)

    def raw_order(self, index, figures=True):          # the labels, then every figure of one column, then the next column
        with pymupdf.open(stream=pdf, filetype="pdf") as d:
            return d[index].get_text("text")
    raw = raw_order(None, 0)
    assert "Total revenue from Operations\n" in raw and "Total revenue from Operations 18,285.22" not in raw
    assert pr.figure_for(pr.parse_page(raw, 1, True), "Q4FY24", "revenue", "CONSOLIDATED")["values"] == []   # line order cannot
    monkeypatch.setattr(pr.Document, "page_text", raw_order)
    assert revenue_of(pdf, "Q4FY24") == [182.8522]
    assert revenue_of(pdf, "FY24") == [661.4566]
    assert revenue_of(pdf, "Q4FY24", metric="pat") == [50.8167]


def test_a_missing_cell_is_placed_by_its_position_not_by_counting():
    pdf = make_grid_pdf(LENDER_ROWS, skip=(2,))       # no figure under 31.03.2023 (quarter): four figures, five dates
    assert revenue_of(pdf, "Q4FY24") == [182.8522]
    assert revenue_of(pdf, "FY24") == [661.4566]       # the year column lies after the gap: counting would slide it
    [row] = [r for r in rows_of(pdf) if r.metric == "revenue"]
    assert row.aligned == [18285.22, 16876.26, None, 66145.66, 42390.12]
    empty = pr.figure_for(rows_of(pdf), "Q4FY23", "revenue", "CONSOLIDATED")     # the empty cell is no figure
    assert empty["values"] == [] and "nil cell" in empty["unsure"]


def test_the_column_kinds_come_from_the_standard_layout_when_the_header_words_do_not_tell_them():
    # no group words in the header at all (a misread "Quarter Ended"): the five dates fit quarter x3 + year x2 exactly
    bare = [(label, figs) for label, figs in LENDER_ROWS if label != WORDS_LINE]
    assert revenue_of(make_grid_pdf(bare), "Q4FY24") == [182.8522]
    # a half-year statement: quarter x3, half year x2, year
    h1 = ["30.09.2026", "30.06.2026", "30.09.2025", "30.09.2026", "30.09.2025", "31.03.2026"]
    page = [("Statement of Standalone Unaudited Financial Results for the quarter and half year ended 30 September 2026", None),
            ("(Rs. in crore)", None), ("Particulars", h1),
            ("Revenue from operations", ["120.50", "110.25", "100.10", "230.75", "205.00", "440.00"])]
    pdf = make_grid_pdf(page, columns=[360, 420, 480, 540, 600, 660])
    assert revenue_of(pdf, "Q2FY27", "STANDALONE") == [120.5]
    assert revenue_of(pdf, "FY26", "STANDALONE") == [440.0]
    [row] = rows_of(pdf)
    assert [k for k, _ in row.columns] == ["quarter"] * 3 + ["half"] * 2 + ["year"]


def test_dates_that_do_not_fit_the_standard_layout_stay_unsure():
    # the same bare header, but the last two dates are not the quarter's twins: no pattern, no proof
    odd = [(l, ["31.03.2024", "31.12.2023", "31.03.2023", "31.03.2024", "31.03.2022"] if l == "Particulars" else f)
           for l, f in LENDER_ROWS if l != WORDS_LINE]
    got = pr.figure_for(rows_of(make_grid_pdf(odd)), "Q4FY24", "revenue", "CONSOLIDATED")
    assert got["values"] == [] and "group words" in got["unsure"]
    # group words that contradict the layout (a nine-months word over a Q4 header) also stay unsure
    nine = [(l, f) if l != WORDS_LINE else ("Nine months ended", None) for l, f in LENDER_ROWS]
    got = pr.figure_for(rows_of(make_grid_pdf(nine)), "Q4FY24", "revenue", "CONSOLIDATED")
    assert got["values"] == [] and got["unsure"]


def test_the_basis_is_read_through_a_misspelt_title_and_never_guessed_without_one():
    garbled = [("STATEMENT OF CONSOUDATED AUDITED FINANCiAL RESULTS FOR THE QUARTER / YEAR ENDED ON MARCH 31.2024", None)] + LENDER_ROWS[1:]
    assert revenue_of(make_grid_pdf(garbled), "Q4FY24") == [182.8522]
    # two bases named in the title: not told
    both = [("Statement of Standalone and Consolidated Audited Financial Results for the year ended 31 March 2024", None)] + LENDER_ROWS[1:]
    got = pr.figure_for(rows_of(make_grid_pdf(both)), "Q4FY24", "revenue", "CONSOLIDATED")
    assert got["values"] == [] and "basis is not told" in got["unsure"]


def test_a_figure_without_the_decimals_its_row_prints_is_a_garbled_layer_not_a_value():
    rows = [(l, ["5,081,67", "4,200.20", "3,619.95", "17,357.28", "9,381.13"] if l.startswith("Net Profit") else f)
            for l, f in LENDER_ROWS]
    pdf = make_grid_pdf(rows)
    got = pr.figure_for(rows_of(pdf), "Q4FY24", "pat", "CONSOLIDATED")
    assert got["values"] == [] and "decimals" in got["unsure"]
    assert [round(v, 4) for v, _, _ in pr.figure_for(rows_of(pdf), "FY24", "pat", "CONSOLIDATED")["values"]] == [173.5728]


@pytest.mark.parametrize("declared,per_crore", [("(Rs. in Lakhs except per share data)", 100), ("(INR in thousand)", 10_000),
                                                ("(₹ in millions)", 10), ("(Rs. in Mn)", 10), ("(Rs. in Cr.)", 1), ("Rupees in Lacs", 100)])
def test_the_declared_unit_is_converted_to_crore(declared, per_crore):
    page = [LENDER_ROWS[0], (declared, None)] + LENDER_ROWS[2:]
    pdf = make_grid_pdf(page)
    [row] = [r for r in rows_of(pdf) if r.metric == "revenue"]
    assert row.unit == per_crore
    assert revenue_of(pdf, "Q4FY24") == [round(18285.22 / per_crore, 4)]


OCR_PAGE = """ADITYA BIRLA CAPITAL LIMITED
STATEMENT OF CONSOLIDATED AUDITED FINANCIAL RESULTS FOR THE QUARTER AND YEAR ENDED 31* MARCH 2024
crore
Quarter Ended  Year Ended
Particulars  31st March, 2024  31{t Dec, 2023  31st March, 2023  31* March, 2024  31{t March, 2023
1  Revenue from Operations
(a) Interest Income  3,862.73  3,747.60  2,805.03  14,290.58  9,563.16
Total Revenue from Operations  10,939.96  8,800.06  8,024.95  34,505.54  27,415.65
2  Other Income  23.66  14.93  26.87  55.04  2,785.68
3  Total Income (1+2)  10,963.62  8,814.99  8,051.82  34,560.58  30,201.33
"""


def test_a_scanned_page_as_ocr_reads_it_dates_with_noise_and_a_unit_without_its_currency_sign():
    rows = pr.parse_page(OCR_PAGE, 8, True)
    assert [r.label for r in rows] == ["Total Revenue from Operations"]
    assert [(k, d.isoformat()) for k, d in rows[0].columns][:4] == [("quarter", "2024-03-31"), ("quarter", "2023-12-31"),
                                                                     ("quarter", "2023-03-31"), ("year", "2024-03-31")]
    assert rows[0].unit == 1
    assert [v for v, _, _ in pr.figure_for(rows, "Q4FY24", "revenue", "CONSOLIDATED")["values"]] == [10939.96]
    assert [v for v, _, _ in pr.figure_for(rows, "FY24", "revenue", "CONSOLIDATED")["values"]] == [34505.54]
    # no unit anywhere near the header: unsure, never read as crore
    bare = pr.parse_page(OCR_PAGE.replace("\ncrore\n", "\n"), 8, True)
    got = pr.figure_for(bare, "Q4FY24", "revenue", "CONSOLIDATED")
    assert got["values"] == [] and "no unit" in got["unsure"]


STANDARD_HEAD = ["Statement of Standalone Audited Financial Results for the quarter and year ended 31 March 2026", "(Rs. in crore)",
                 ("Particulars", ["31.03.2026", "31.12.2025", "31.03.2025", "31.03.2026", "31.03.2025"]),
                 ("Quarter ended Quarter ended Quarter ended Year ended Year ended", None)]


def lines_grid(body, head=None, **kw):
    head = [(h, None) if isinstance(h, str) else h for h in (head or STANDARD_HEAD)]
    return make_grid_pdf(head + body, **kw)


def referee_revenue(pdf, ours, theirs, official=None):
    url = "https://nsearchives.nseindia.com/corporate/RES.pdf"
    return pr.referee_pair(pr.Sources(FakeNse([filing()], {url: pdf}), ocr=False),
                           pair(period="Q4FY26", basis="STANDALONE", ours=ours, theirs=theirs, official=official))


def test_total_income_never_settles_a_pair_and_a_wrapped_label_is_joined():
    wrapped = [("Revenue from", None), ("operations", ["120.50", "110.25", "100.10", "440.00", "400.00"]),
               ("Total income", ["121.60", "111.25", "101.00", "444.00", "403.00"])]
    pdf = lines_grid(wrapped)
    assert [(r.rank, r.label) for r in rows_of(pdf) if r.metric == "revenue"] == [(0, "Revenue from operations")]
    got = referee_revenue(pdf, ours=120.5, theirs=121.6)
    assert got["pdf_verdict"] == "pdf_matches_ours" and got["pdf_value"] == 120.5       # not Total income's 121.6
    # nothing but Total income printed, and screener equals it: unsure, never matches_screener
    only = lines_grid([("Total income", ["121.60", "111.25", "101.00", "444.00", "403.00"])])
    got = referee_revenue(only, ours=120.5, theirs=121.6)
    assert got["pdf_verdict"] == "pdf_unsure" and got["pdf_value"] is None and "Total income" in got["reason"]
    # a segment line "Total income from operations" is revenue from operations, not total income
    seg = lines_grid([("Total income from operations", ["120.50", "110.25", "100.10", "440.00", "400.00"])])
    assert referee_revenue(seg, ours=120.5, theirs=121.6)["pdf_verdict"] == "pdf_matches_ours"


def test_a_banks_sub_line_of_interest_earned_is_never_the_revenue():
    top = ("1 Interest earned (a)+(b)+(c)+(d)", ["500.00", "480.00", "450.00", "1,900.00", "1,700.00"])
    sub = ("(a) Interest/discount on advances/bills", ["400.00", "390.00", "350.00", "1,500.00", "1,300.00"])
    earned_on = ("(a) Interest earned on advances", ["400.00", "390.00", "350.00", "1,500.00", "1,300.00"])
    assert revenue_of(lines_grid([top, sub, earned_on]), "Q4FY26", "STANDALONE") == [500.0]
    alone = lines_grid([earned_on])
    got = pr.figure_for(rows_of(alone), "Q4FY26", "revenue", "STANDALONE")
    assert got["values"] == [] and "sub-line" in got["unsure"]
    assert referee_revenue(alone, ours=400.0, theirs=400.0)["pdf_verdict"] == "pdf_unsure"
    plain = ("Interest earned on investments", ["50.00", "40.00", "30.00", "150.00", "120.00"])
    assert pr.figure_for(rows_of(lines_grid([plain])), "Q4FY26", "revenue", "STANDALONE")["values"] == []


def test_basis_words_are_not_fuzzy_beyond_small_misspellings_of_the_whole_word():
    for word in ("Consolidating", "Consolidate", "Consolidator", "Deconsolidated", "Reconsolidated", "Consolidation"):
        assert not pr._names(f"Statement of {word} results", "consolidated"), word
    for word in ("CONSOUDATED", "Consolidted", "Consoldated"):
        assert pr._names(f"Statement of {word} results", "consolidated"), word
    assert not pr._names("Statement of Unconsolidated results", "consolidated")
    assert pr._names("Statement of Unconsolidated results", "standalone")
    page = lines_grid([("Revenue from operations", ["120.50", "110.25", "100.10", "440.00", "400.00"])],
                      head=["Statement of Unconsolidated Audited Financial Results for the quarter and year ended 31 March 2026"]
                      + STANDARD_HEAD[1:])
    assert revenue_of(page, "Q4FY26", "STANDALONE") == [120.5]
    assert pr.figure_for(rows_of(page), "Q4FY26", "revenue", "CONSOLIDATED")["values"] == []


def test_a_figure_nearer_the_next_label_than_its_own_makes_the_position_reading_unproven(monkeypatch):
    body = [("Revenue from operations", ["120.50", "110.25", "100.10", "440.00", "400.00"]),
            ("Other income", ["1.10", "1.00", "0.90", "4.00", "3.00"]),
            ("Net Profit for the period", ["12.30", "10.10", "9.00", "40.00", "30.00"])]

    def column_order(pdf):
        def raw(self, index, figures=True):
            with pymupdf.open(stream=pdf, filetype="pdf") as d:
                return d[index].get_text("text")
        monkeypatch.setattr(pr.Document, "page_text", raw)

    # figures 2 pt off their labels' baselines on 10 pt rows: clearly their own row's, so the rebuild reads them
    good = lines_grid(body, column_order=True, pitch=10, offset=2)
    column_order(good)
    assert revenue_of(good, "Q4FY26", "STANDALONE") == [120.5]
    # 4.7 pt off on 10 pt rows (more than 45% of the pitch): they may belong to the next row, so no figure is taken
    bad = lines_grid(body, column_order=True, pitch=10, offset=4.7)
    column_order(bad)
    got = pr.figure_for(rows_of(bad), "Q4FY26", "revenue", "STANDALONE")
    assert got["values"] == [] and "baseline" in got["unsure"]
    # 5 pt off on 8 pt rows: nearer the next label than its own (the review's probe): never the next row's figures
    worse = lines_grid(body, column_order=True, pitch=8, offset=5)
    column_order(worse)
    rows, _why = pr.read_document(worse, ocr=False)
    assert not rows or pr.figure_for(rows, "Q4FY26", "revenue", "STANDALONE")["values"] == []
    assert not rows or pr.figure_for(rows, "Q4FY26", "pat", "STANDALONE")["values"] == []


def test_the_standard_layout_needs_a_march_year_end_on_the_page():
    body = [("Revenue from operations", ["120.50", "110.25", "100.10", "440.00", "400.00"])]
    head = ["Statement of Standalone Audited Financial Results for the quarter ended 31 March 2026", "(Rs. in crore)",
            STANDARD_HEAD[2]]
    got = pr.figure_for(rows_of(lines_grid(body, head=head)), "Q4FY26", "revenue", "STANDALONE")
    assert got["values"] == [] and "group words" in got["unsure"]       # the same dates may be nine-month columns
    assert revenue_of(lines_grid(body, head=[head[0].replace("quarter ended", "quarter and year ended")] + head[1:]),
                      "Q4FY26", "STANDALONE") == [120.5]
