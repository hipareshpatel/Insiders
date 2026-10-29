"""NSE's annual-report XBRL (annual_xbrl.py): the parser on real files, and the table in front of an annual report.

Fixtures are the real files for Kanoria Chemicals FY25 (consolidated and standalone) and Shivam Autotech FY25
(standalone), cut down by scripts/trim_xbrl_fixture.py to the facts read here and a few it must ignore.
"""

from __future__ import annotations

import pytest

import json
from datetime import datetime
from pathlib import Path

from bse_intel import annual_xbrl, gate
from bse_intel.nse import AnnualReportFiling, parse_annual_report_rows
from bse_intel.timeutil import IST

from test_pipeline import _filing, _pdf, build

FIXTURES = Path(__file__).parent / "fixtures"
CONSOLIDATED = (FIXTURES / "nse_ar_kanorichem_fy25_consolidated.xml").read_bytes()
STANDALONE = (FIXTURES / "nse_ar_kanorichem_fy25_standalone.xml").read_bytes()
SHIVAM = (FIXTURES / "nse_ar_shivamauto_fy25_standalone.xml").read_bytes()
BASE = "https://nsearchives.nseindia.com/corporate/xbrl/"
# NSE's answer for KANORICHEM on 2026-10-18, as the Annual Reports XBRL page received it
LISTING = {"data": [
    {"companyName": "Kanoria Chemicals & Industries Limited", "fromYr": "2024", "toYr": "2025", "report_type": "IND-AS",
     "submission_type": "Standalone", "broadcast_dttm": "22-DEC-2025 12:22:28", "disseminationDateTime": "22-DEC-2025 12:22:43",
     "timeTaken": "00:00:15", "fileName": BASE + "AR_XBRL_KANORICHEM_22122025122227.xml"},
    {"companyName": "Kanoria Chemicals & Industries Limited", "fromYr": "2024", "toYr": "2025", "report_type": "IND-AS",
     "submission_type": "Consolidated", "broadcast_dttm": "22-DEC-2025 12:22:59", "disseminationDateTime": "22-DEC-2025 12:23:15",
     "timeTaken": "00:00:16", "fileName": BASE + "AR_XBRL_KANORICHEM_22122025122259.xml"}]}


def test_consolidated_statements_are_read_in_crore_with_filler_zeros_left_out():
    report = annual_xbrl.parse(CONSOLIDATED)
    assert report.basis == "CONSOLIDATED" and report.fy == "FY25" and report.rounding == "Millions"
    # the held card's "standalone revenue ₹1,536.71 Cr" is the consolidated figure; the company alone is 678.30
    assert round(report.current["revenue"], 2) == 1536.72 and round(report.prior["revenue"], 2) == 1475.05
    assert round(report.current["pat"], 2) == -108.15 and round(report.current["pat_owners"], 2) == -83.60
    assert report.current["eps"] == -19.13
    assert round(report.current["borrowings_noncurrent"] + report.current["borrowings_current"], 2) == 594.12
    # ContingentLiabilities and ManagerialRemuneration are filed as 0, which is the software's blank: not a nil
    assert "contingent_liabilities" not in report.current and "managerial_remuneration" not in report.current
    assert [(what, round(v, 2)) for what, v in report.contingent][0] == ("Income Tax demands", 5.84)
    # per party: the largest flow and balance, and the group entities that lost money
    party, kind, nature, value = report.related_flows[0]
    assert (party, kind, nature, round(value, 2)) == ("Cosyst Holding AG", "joint control or significant influence",
                                                      "other transactions, contribution received", 67.98)
    assert ("KPL International Limited", "joint control or significant influence", "purchases of goods") in \
        [flow[:3] for flow in report.related_flows]
    assert report.related_balances[0][:3] == ("Cosyst Holding AG", "joint control or significant influence", "payable to")
    assert [(name, round(v, 2)) for name, _, v in report.loss_entities] == [("APAG Holding AG", -27.89),
                                                                           ("Kanoria Africa Textiles PLC", -25.59)]
    assert report.auditors == ["Singhi & Co (firm registration 302049E) signed by RAHUL BOTHRA on 21 May 2025"]
    assert report.qualified_flag is False


def test_standalone_carries_the_boards_report_and_caro():
    report = annual_xbrl.parse(STANDALONE)
    assert report.basis == "STANDALONE" and round(report.current["revenue"], 2) == 678.30
    assert report.kmp_pay[0][:2] == ("Rajya Vardhan Kanoria", "Managing Director") and round(report.kmp_pay[0][2], 2) == 3.15
    assert report.opinion == "unmodified" and not report.report_notes
    clauses = dict(report.caro)
    assert "has not defaulted in repayment of loans" in clauses["defaults in repaying lenders (CARO ix)"]


def test_a_qualified_opinion_on_internal_controls_is_not_the_opinion_on_the_statements():
    """Shivam FY25: the statements' opinion is unmodified, with an emphasis of matter; the report on internal
    financial controls is qualified. Its card said so; a search for "Qualified Opinion" would have said otherwise."""
    report = annual_xbrl.parse(SHIVAM)
    assert report.opinion == "unmodified" and report.rounding == "Lakhs"
    notes = dict(report.report_notes)
    assert notes["emphasis of matter"].startswith("Emphasis of Matter We draw attention to")
    assert "control weaknesses" in notes["qualified opinion"]
    table = annual_xbrl.table([report])
    assert "the auditor's opinion, read from its basis-for-opinion heading: standalone unmodified" in table
    assert "qualified opinion in the standalone auditor's report (outside the opinion on the statements" in table


def test_table_leads_with_the_consolidated_set_and_names_each_basis():
    table = annual_xbrl.table([annual_xbrl.parse(STANDALONE), annual_xbrl.parse(CONSOLIDATED)])
    lines = table.splitlines()
    assert lines[0].startswith("Machine-tagged annual report (XBRL the company filed with NSE, FY25, consolidated, "
                               "₹ crore unless noted") and "prints its statements in millions" in lines[0]
    assert "- consolidated revenue from operations FY25: 1,536.72 Cr (FY24: 1,475.05 Cr, +4.2%)" in lines
    # the year before on the same line: the held card compared with FY24's 506.72, which no line printed
    assert "- consolidated borrowings at 31 March 2025: 594.12 Cr (non-current 343.62 Cr, current 250.50 Cr; " \
           "FY24: 506.72 Cr)" in lines
    assert any(line.startswith("- standalone (the company alone): revenue from operations FY25 678.30 Cr") for line in lines)
    assert any("Rajya Vardhan Kanoria (Managing Director) 3.15 Cr" in line for line in lines)
    # no total is tagged (the filed 0 is a blank), so the classes and what they add to, on one line
    (contingent,) = [line for line in lines if "contingent liabilities" in line]
    assert contingent.startswith("- consolidated contingent liabilities at 31 March 2025, by class: Income Tax demands 5.84 Cr")
    assert contingent.endswith("; all 2 classes add to 6.82 Cr") and not any(": 0.00 Cr" in line for line in lines)
    assert len(table) < 6000


def test_a_tagged_contingent_total_shares_its_line_with_the_classes():
    """Jubilant FY25 tags a total and its classes; its card quoted the by-class line for the total and was held."""
    report = annual_xbrl.parse(CONSOLIDATED)
    report.current["contingent_liabilities"] = 6.82
    (line,) = [l for l in annual_xbrl.table([report]).splitlines() if "contingent liabilities" in l]
    assert line.startswith("- consolidated contingent liabilities at 31 March 2025: 6.82 Cr; by class: Income Tax demands 5.84 Cr")
    assert gate.numbers_in_quote("Contingent liabilities ₹6.82 Cr", line[2:], unit=10) == []


def test_a_card_may_quote_a_table_line_whatever_unit_the_pdf_prints():
    """The held reason the table removes: a crore figure whose quote, from a statement in millions, cannot carry it."""
    table = annual_xbrl.table([annual_xbrl.parse(CONSOLIDATED)])
    quote = next(line[2:] for line in table.splitlines() if line.startswith("- consolidated borrowings"))
    assert gate.quote_found(quote, table)
    assert gate.numbers_in_quote("Consolidated borrowings ₹594.12 Cr", quote, unit=10) == []
    assert gate.numbers_in_quote("Consolidated borrowings ₹5,941.2 Cr", quote, unit=10) != []


def test_nse_listing_and_the_year_a_report_closes():
    listing = parse_annual_report_rows(LISTING["data"])
    assert [(f.to_year, f.basis) for f in listing] == [(2025, "STANDALONE"), (2025, "CONSOLIDATED")]
    assert listing[1].filed_at == "2025-12-22T12:22:59+05:30" and listing[1].xbrl_url.endswith("_22122025122259.xml")
    assert [f.basis for f in annual_xbrl.pick(listing, 2025)] == ["CONSOLIDATED", "STANDALONE"]
    assert annual_xbrl.pick(listing, 2026) == []   # Kanoria's FY26 report, filed before its XBRL: none
    year = annual_xbrl.report_year
    assert year("Annual Report for the Financial year 2024-25", "", "2025-09-02T15:46:49+05:30") == 2025
    assert year("Annual Report for the F.Y.E. 31st March 2026.", "", "2026-08-06T14:30:16+05:30") == 2026
    assert year("Annual Report 2025", "", "2025-09-03T22:00:00+05:30") == 2025
    assert year("Notice of the 34th Annual General Meeting and Annual Report", "", "2026-07-16T13:20:29+05:30") == 2026
    assert year("Annual Report", "", "2026-01-13T10:46:06+05:30") == 2025


def test_confirm_looks_for_the_years_figures_at_any_unit():
    report = annual_xbrl.parse(CONSOLIDATED)
    assert annual_xbrl.confirm(report, "Revenue from operations 15,367.16 14,750.51 (₹ in million)")
    assert not annual_xbrl.confirm(report, "Revenue from operations 9,876.54 8,765.43")
    assert annual_xbrl.confirm(report, "")   # a scan with no text layer: nothing to check against


class FakeNse:
    def __init__(self, files: dict[str, bytes]):
        self.files, self.downloads = files, []

    def annual_reports(self, symbol):
        rows = [r for r in LISTING["data"] if r["fileName"].rsplit("/", 1)[-1] in self.files]
        return parse_annual_report_rows(rows) if symbol == "DEMOCEM" else []

    def download(self, url, max_bytes=None):
        self.downloads.append(url)
        return self.files.get(url.rsplit("/", 1)[-1])


ANNUAL_TEXT = ("Kanoria Chemicals & Industries Limited Annual Report 2024-25 (Rs. in million). Independent Auditor's Report. "
               "Opinion: in our opinion the consolidated financial statements give a true and fair view. "
               "Revenue from operations 15,367.16 14,750.51. Borrowings 3,436.23 2,504.96.")
ANNUAL_CARD = {
    "is_material": True, "event_type": "ANNUAL_REPORT",
    "card": {
        "impact_level": "LOW", "basis": "CONSOLIDATED",
        "headline": "Kanoria FY25 annual report: audit unmodified; consolidated borrowings ₹594.12 Cr",
        "what_happened": [{"text": "The auditor's opinion on the consolidated statements is unmodified",
                           "quote": "in our opinion the consolidated financial statements give a true and fair view"}],
        "key_numbers": [{"label": "Consolidated borrowings", "value": "₹594.12 Cr",
                         "quote": "consolidated borrowings at 31 March 2025: 594.12 Cr (non-current 343.62 Cr, current 250.50 Cr)"}],
        "why_it_matters": [], "missing_disclosures": [],
    },
    "timeline_entry": "FY25 annual report: audit unmodified.",
    "dossier_delta": {},
}


def _annual(settings, files):
    when = datetime(2025, 9, 2, 15, 46, 49, tzinfo=IST)
    f = _filing("n-ar", "Annual Report for the Financial year 2024-25", when, "AGM/EGM", "Reg. 34 (1) Annual Report")
    pipeline, sink, fake = build(settings, [f], {f.pdf_url: _pdf(ANNUAL_TEXT)},
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(ANNUAL_CARD)], "deepseek-ai/deepseek-v4.1-flash": [json.dumps(ANNUAL_CARD)]},
                                 env={"NVIDIA_API_KEY": "n", "OPENROUTER_API_KEY": "o"})
    pipeline.nse = FakeNse(files)
    outcome = pipeline.analyze(f.model_copy(update={"route": "FAST_TRACK", "event_type": "ANNUAL_REPORT"}))
    return outcome, fake, pipeline.nse


def test_annual_report_is_read_with_its_xbrl_table_in_front(settings):
    outcome, fake, nse = _annual(settings, {"AR_XBRL_KANORICHEM_22122025122259.xml": CONSOLIDATED,
                                            "AR_XBRL_KANORICHEM_22122025122227.xml": STANDALONE})
    prompt = fake.calls[0]["messages"][-1]["content"]
    assert "Machine-tagged annual report (XBRL the company filed with NSE, FY25, consolidated" in prompt
    assert prompt.index("Machine-tagged annual report") < prompt.index("Independent Auditor's Report")
    body = outcome.card["card"]
    assert body["annual_xbrl"] == {"bases": ["CONSOLIDATED", "STANDALONE"], "period": "FY25",
                                   "figures": annual_xbrl.parse(CONSOLIDATED).figures() + annual_xbrl.parse(STANDALONE).figures()}
    # the key number quotes the table's line, which is the filing's own figure in crore: nothing to hold
    assert not any("Consolidated borrowings" in issue for issue in (body["review"] or {}).get("issues", []))
    assert outcome.card["held"] == 0 and len(nse.downloads) == 2


@pytest.mark.switches_off("CARD_TWO_PARTS")   # the behaviour before the switch; the switch has its own tests
def test_without_the_file_the_annual_report_is_read_as_before(settings):
    outcome, fake, nse = _annual(settings, {})
    assert "Machine-tagged annual report" not in fake.calls[0]["messages"][-1]["content"]
    body = outcome.card["card"]
    assert "annual_xbrl" not in body and nse.downloads == []
    # the same quote is now not in the filing, as on the cards held in round 3d
    assert any("Consolidated borrowings" in issue for issue in (body["review"] or {}).get("issues", []))


def test_a_file_whose_figures_are_not_in_the_pdf_is_not_used(settings, monkeypatch):
    monkeypatch.setattr("test_annual_xbrl.ANNUAL_TEXT", "Annual Report 2024-25 (Rs. in million). Revenue 9,876.54.")
    outcome, fake, _ = _annual(settings, {"AR_XBRL_KANORICHEM_22122025122259.xml": CONSOLIDATED})
    assert "Machine-tagged annual report" not in fake.calls[0]["messages"][-1]["content"]
    assert "annual_xbrl" not in outcome.card["card"]


def test_listing_rows_for_one_basis_keep_the_latest_file():
    rows = [dict(LISTING["data"][1]), dict(LISTING["data"][1], broadcast_dttm="05-JAN-2026 10:00:00",
                                         fileName=BASE + "AR_XBRL_KANORICHEM_05012026100000.xml")]
    (only,) = parse_annual_report_rows(rows)
    assert isinstance(only, AnnualReportFiling) and only.xbrl_url.endswith("_05012026100000.xml")


def test_the_card_block_names_the_red_flags_from_the_tagged_files():
    """Owner, 22 Oct 2026: an annual report card is read for its red flags. The block is the files' own: opinion, CARO,
    contingent liabilities, related parties, loss-making entities, consolidated first and the standalone filling in."""
    block = annual_xbrl.card_block([annual_xbrl.parse(STANDALONE), annual_xbrl.parse(CONSOLIDATED)])
    assert block["basis"] == "CONSOLIDATED" and block["fy"].startswith("FY")
    assert "opinion" in block or "auditors" in block
    assert block.get("caro_count", 0) >= 1                      # the standalone file carries CARO (test above)
    if "contingent_cr" in block:
        assert block["contingent_cr"] == round(sum(c["cr"] for c in block["contingent_top"]), 2) or len(block["contingent_top"]) == 3
    assert annual_xbrl.card_block([]) is None


def test_only_a_caro_remark_that_something_is_wrong_is_a_flag():
    clean = ["The Company has been regular in depositing undisputed statutory dues.",
             "The Company has not defaulted in repayment of loans or other borrowings.",
             "no fraud by the Company or on the Company has been noticed or reported during the year."]
    adverse = ["The Company has not been regular in depositing undisputed statutory dues, including GST.",
               "The Company has defaulted in repayment of loans to a bank: Rs 12.4 crore overdue for 90 days.",
               "Undisputed dues of Rs 3.2 crore were outstanding for a period of more than six months from the date they became payable."]
    assert not any(annual_xbrl.caro_adverse(t) for t in clean)
    assert all(annual_xbrl.caro_adverse(t) for t in adverse)


def test_the_annual_table_has_no_eps_line_but_the_data_keeps_it():
    from datetime import date
    r = annual_xbrl.AnnualReport(basis="CONSOLIDATED", period_end=date(2026, 3, 31),
                                 current={"revenue": 100.0, "pat": 10.0, "eps": 5.2}, prior={"revenue": 90.0, "pat": 9.0, "eps": 4.8})
    text = annual_xbrl.table([r])
    assert "revenue from operations" in text and "profit for the year" in text and "EPS" not in text and "share" not in text
    assert r.current["eps"] == 5.2
