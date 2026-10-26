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
