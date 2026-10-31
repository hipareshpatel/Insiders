"""TODO 148: banks' annual-report PDFs read for the rows their XBRL lacks (bank_pdf.py).

The page texts in fixtures/bank_pdf/ are the real text layers of the three test reports (BSE AttachHis, fetched 31 Oct 2026):
SBI FY23 (22d33d1d-..., pages 149-150, 154, 238, 242), Union Bank FY25 (5e30ef1f-..., pages 220-222, 301-303) and Canara Bank
FY25 (4bfe9370-..., pages 405, 408, 566, 569); sbi_fy23_sch10_16.pdf is SBI's pages 149, 150 and 154 as a PDF. The figures expected
below are the ones printed on those pages. The XBRL facts the checks run against are made up around the printed figures (the file's
OperatingExpenses and FixedAssets equal the report's totals, as the bank's own Q4 file does)."""

import gzip
import json
from datetime import date
from pathlib import Path

import pytest

from bse_intel import bank_pdf as bp
from bse_intel import screener_view as sv
from bse_intel import xbrl_facts as xf
from bse_intel.metrics import CONSOLIDATED, STANDALONE

FIX = Path(__file__).parent / "fixtures" / "bank_pdf"
CR = 10_000_000


def pages(name: str) -> dict:
    data = json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))
    places = sorted(int(p) for p in data["pages"])
    return bp.read_pages([data["pages"][str(p)] for p in places], places)


# --- figures as printed ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("line,expected", [
    ("3297,27,04 ", [32972704.0]),                    # SBI: thousands, a crore group first
    ("1,07,10,161", [10710161.0]),                    # Union: thousands, Indian commas
    (" 837 19 49 ", [8371949.0]),                     # Canara: groups split by spaces
    (" (3203 43 22)", [-32034322.0]),
    ("- 57 49", [-5749.0]),
    ("-14,116", [-14116.0]),
    ("  88", [88.0]),
    (" -   ", [0.0]),
    ("31393,47,30 29069,87,58", [313934730.0, 290698758.0]),
    ("Depreciation on Bank's property", None),
    ("V.", None),
])
def test_figures(line, expected):
    assert bp.figures(line) == expected


def test_units_and_years():
    assert bp.unit_of(["(000s omitted)"]) == 1e-4
    assert bp.unit_of(["(` in 000’)"]) == 1e-4
    assert bp.unit_of(["( ( ` in ‘000)"]) == 1e-4
    assert bp.unit_of(["(₹ in crore)"]) == 1.0
    assert bp.unit_of(["Particulars"]) is None
    assert bp.years_of(["As at 31.03.2023", "As at 31.03.2022"]) == ["FY23", "FY22"]
    assert bp.years_of(["As on ", "31st March 2025", "31st March 2024"]) == ["FY25", "FY24"]
    assert bp.years_of(["March 31, 2025"]) == ["FY25"]


def test_heading_is_the_schedule_not_a_note():
    assert bp.heading("SCHEDULE 16 - OPERATING EXPENSES") == (16, "operating expenses")
    assert bp.heading("SCHEDULE 10 - FIXED ASSETS:") == (10, "fixed assets")
    assert bp.heading(" AcÉsÉ AÉÎxiÉrÉÉÇ / SCHEDULE 10 - FIXED ASSETS") == (10, "fixed assets")
    assert bp.heading("Schedule 16 – Operating Expenses (XII Other expenditure) --") is None   # Union's notes


def test_movement_closing_union_cwip():
    # Union FY25 standalone CWIP: the deductions line prints deduction, closing, deduction, closing (thousands)
    block = [[347034.0, 205438.0], [558797.0, 310576.0], [329475.0, 576356.0, 168980.0, 347034.0]]
    assert bp.movement_closing(block) == (576356.0, 347034.0)
    assert bp.movement_closing(block[:2]) is None
    assert bp.movement_closing([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0, 7.0, 8.0]]) is None      # nothing adds up


def test_page_numbers_are_not_figures():
    # SBI's consolidated Schedule 10 ends "44407,38,10 / 39510,03,05 / 235": the printed page number is not a third figure
    got = pages("sbi_fy23")
    assert got[CONSOLIDATED]["FY23"]["fa_total"] == pytest.approx(44407.381)


# --- the three reports -----------------------------------------------------------------------------------------------

def test_sbi_fy23():
    got = pages("sbi_fy23")
    s, c = got[STANDALONE], got[CONSOLIDATED]
    assert s["FY23"]["depreciation"] == pytest.approx(3297.2704)        # "Depreciation on Bank's property 3297,27,04"
    assert s["FY22"]["depreciation"] == pytest.approx(3248.5859)
    assert s["FY23"]["opex_total"] == pytest.approx(97743.1361) and s["FY23"]["opex_adds_up"]
    assert s["FY23"]["fa_total"] == pytest.approx(42381.8031)
    assert s["FY23"]["cwip"] == pytest.approx(281.0721)                 # "Assets under Construction (Including Premises)"
    assert s["FY22"]["cwip"] == pytest.approx(240.6701)
    assert c["FY23"]["depreciation"] == pytest.approx(3644.7949 + 50.8037)   # a) other than leased + b) leased
    assert c["FY23"]["cwip"] == pytest.approx(317.546 + 66.0204)        # premises under construction + capital work in progress
    assert c["FY23"]["fa_subtotal"] == pytest.approx(44341.3606)
    assert c["FY23"]["cwip_after_subtotal"] == pytest.approx(66.0204)
    assert s["FY23"]["pages"] == {"fixed": 149, "opex": 154} and c["FY23"]["pages"] == {"fixed": 238, "opex": 242}


def test_union_fy25():
    got = pages("union_fy25")
    s, c = got[STANDALONE], got[CONSOLIDATED]
    assert s["FY25"]["depreciation"] == pytest.approx(1071.0161) and s["FY25"]["opex_total"] == pytest.approx(25936.5486)
    assert s["FY25"]["fa_total"] == pytest.approx(9781.8765)
    assert s["FY25"]["cwip"] == pytest.approx(57.6356) and s["FY24"]["cwip"] == pytest.approx(34.7034)   # from the movement
    assert c["FY25"]["depreciation"] == pytest.approx(1083.8813)      # A) 1,08,38,813 + B) leased "-"
    assert c["FY25"]["opex_adds_up"]                                   # the "-" items and Goodwill's -14,116 counted
    assert c["FY25"]["fa_total"] == pytest.approx(9824.0935)
    assert c["FY25"]["cwip"] == pytest.approx(58.7281) and c["FY25"]["fa_subtotal"] == pytest.approx(9765.3654)


def test_canara_fy25_bilingual():
    got = pages("canara_fy25")
    s, c = got[STANDALONE], got[CONSOLIDATED]
    assert s["FY25"]["depreciation"] == pytest.approx(837.1949) and s["FY24"]["depreciation"] == pytest.approx(868.9361)
    assert s["FY25"]["opex_total"] == pytest.approx(28134.4954) and s["FY25"]["opex_adds_up"]
    assert s["FY25"]["fa_total"] == pytest.approx(10215.1494)        # the grand total, not a group's ("2 19 00", "2502 59 00")
    assert s["FY25"]["cwip"] is None                                    # its standalone schedule prints no CWIP line
    assert c["FY25"]["depreciation"] == pytest.approx(869.772)
    assert c["FY25"]["cwip"] is None                                    # CWIP mixed with the subsidiaries' intangibles: not read


def test_read_from_pdf():
    got = bp.read((FIX / "sbi_fy23_sch10_16.pdf").read_bytes())
    assert got[STANDALONE]["FY23"]["depreciation"] == pytest.approx(3297.2704)
    assert got[STANDALONE]["FY23"]["cwip"] == pytest.approx(281.0721)


# --- what the bank's own figures accept ------------------------------------------------------------------------------

def test_pl_figure_needs_the_files_operating_expenses():
    cell = pages("sbi_fy23")[STANDALONE]["FY23"]
    dep, why = bp.pl_figure(cell, 97743.14)
    assert dep == pytest.approx(3297.2704) and "Schedule 16 p.154" in why
    assert bp.pl_figure(cell, 93397.52)[0] is None                       # the previous year's column: not this year
    assert bp.pl_figure({**cell, "opex_adds_up": False}, 97743.14)[0] is None
    assert bp.pl_figure(None, 97743.14)[0] is None


def test_bs_figures_need_the_files_fixed_assets():
    s = pages("sbi_fy23")[STANDALONE]["FY23"]
    (fa, cwip), why = bp.bs_figures(s, 42381.80)
    assert (fa, cwip) == (pytest.approx(42100.731), pytest.approx(281.0721)) and "Schedule 10 p.149" in why
    assert bp.bs_figures(s, 44407.38)[0] is None                          # the consolidated total: another basis
    c = pages("sbi_fy23")[CONSOLIDATED]["FY23"]
    (fa, cwip), _ = bp.bs_figures(c, 44407.38)                           # subtotal 44,341.36 + CWIP after it 66.02 = total
    assert cwip == pytest.approx(383.5664)
    assert bp.bs_figures({**c, "fa_subtotal": 44000.0}, 44407.38)[0] is None
    assert bp.bs_figures(pages("canara_fy25")[STANDALONE]["FY25"], 10215.15)[0] is None    # no CWIP line: nothing


# --- in the bank's statements (screener_view) ------------------------------------------------------------------------

def doc(facts, year=2023):
    contexts = {f"D{year}": {"s": f"{year - 1}-04-01", "e": f"{year}-03-31", "m": 12},
                f"Q{year}": {"s": f"{year}-01-01", "e": f"{year}-03-31", "m": 3},
                f"I{year}": {"i": f"{year}-03-31"}}
    rows = [[el, ctx, "INR", int(round(v * CR)), -5] for el, ctx, v in facts]
    return {"v": 1, "kind": "results", "template": "BANKING", "basis": STANDALONE, "period": f"Q4FY{year % 100}",
            "contexts": contexts, "units": {"INR": "MONEY"}, "facts": rows}


# a direct cash flow: no AdjustmentsForDepreciationAndAmortisationExpense (Bank of Maharashtra's case, F228). SBI FY23's printed
# operating expenses and fixed assets; the other lines made up so that the file's PBT is its own lines' sum
YEAR = [("InterestEarned", "D2023", 332103.0), ("InterestExpended", "D2023", 189980.8), ("OperatingExpenses", "D2023", 97743.14),
        ("ProvisionsOtherThanTaxAndContingencies", "D2023", 16507.2), ("OtherIncome", "D2023", 36615.6),
        ("ProfitLossFromOrdinaryActivitiesBeforeTax", "D2023", 64487.46), ("TaxExpense", "D2023", 13854.4)]
SHEET = [("Capital", "I2023", 892.46), ("ReservesAndSurplus", "I2023", 326608.0), ("Deposits", "I2023", 4408000.0),
         ("Borrowings", "I2023", 493000.0), ("OtherLiabilitiesAndProvisions", "I2023", 238000.0),
         ("CapitalAndLiabilities", "I2023", 5466500.46), ("FixedAssets", "I2023", 42381.80), ("Investments", "I2023", 1570000.0)]


def test_bank_pl_takes_the_reports_depreciation_for_a_year():
    pdf = pages("sbi_fy23")[STANDALONE]["FY23"]
    f = xf.Facts(doc(YEAR))
    without = sv.bank_pl(sv._Reader(f, end=date(2023, 3, 31), months=12))
    assert without["Depreciation"].value is None and without["Expenses"].value is None
    rows = sv.bank_pl(sv._Reader(f, end=date(2023, 3, 31), months=12), pdf=pdf)
    assert rows["Depreciation"].value == pytest.approx(3297.2704)
    assert "annual report Schedule 16" in rows["Depreciation"].note
    assert rows["Expenses"].value == pytest.approx(97743.14 + 16507.2 - 3297.2704)
    fp, oi, pbt = rows["Financing Profit"].value, rows["Other Income"].value, rows["Profit before tax"].value
    assert fp + oi - rows["Depreciation"].value == pytest.approx(pbt, abs=1.0)      # the bank's identity holds
    quarter = sv.bank_pl(sv._Reader(f, end=date(2023, 3, 31), months=3), pdf=pdf)  # a quarter: the report is a year's
    assert quarter["Depreciation"].value is None


def test_bank_pl_leaves_it_empty_when_the_file_disagrees():
    pdf = pages("sbi_fy23")[STANDALONE]["FY23"]
    other = [x if x[0] != "OperatingExpenses" else ("OperatingExpenses", "D2023", 99000.0) for x in YEAR]
    rows = sv.bank_pl(sv._Reader(xf.Facts(doc(other)), end=date(2023, 3, 31), months=12), pdf=pdf)
    assert rows["Depreciation"].value is None and "annual report not used" in rows["Depreciation"].note
    # the file's own lines do not make its PBT: the identity fails, nothing is taken
    broken = [x if x[0] != "ProfitLossFromOrdinaryActivitiesBeforeTax" else (x[0], "D2023", 60000.0) for x in YEAR]
    rows = sv.bank_pl(sv._Reader(xf.Facts(doc(broken)), end=date(2023, 3, 31), months=12), pdf=pdf)
    assert rows["Depreciation"].value is None
    # a file with its own depreciation keeps it
    own = YEAR + [("AdjustmentsForDepreciationAndAmortisationExpense", "D2023", 3300.0)]
    rows = sv.bank_pl(sv._Reader(xf.Facts(doc(own)), end=date(2023, 3, 31), months=12), pdf=pdf)
    assert rows["Depreciation"].value == pytest.approx(3300.0)


def test_bank_bs_splits_cwip_at_march():
    pdf = pages("sbi_fy23")[STANDALONE]["FY23"]
    f = xf.Facts(doc(SHEET))
    plain = sv.bank_bs(sv._Reader(f, instant=date(2023, 3, 31)))
    rows = sv.bank_bs(sv._Reader(f, instant=date(2023, 3, 31)), pdf=pdf)
    assert "CWIP" not in plain and plain["Fixed Assets"].value == pytest.approx(42381.80)
    assert rows["CWIP"].value == pytest.approx(281.0721)
    assert rows["Fixed Assets"].value == pytest.approx(42381.80 - 281.0721)
    assert rows["Other Assets"].value == pytest.approx(plain["Other Assets"].value)      # the split moves nothing else
    wrong = [x if x[0] != "FixedAssets" else ("FixedAssets", "I2023", 40000.0) for x in SHEET]
    rows = sv.bank_bs(sv._Reader(xf.Facts(doc(wrong)), instant=date(2023, 3, 31)), pdf=pdf)
    assert "CWIP" not in rows and rows["Fixed Assets"].value == pytest.approx(40000.0)


# --- the run ---------------------------------------------------------------------------------------------------------

class Sink:
    def __init__(self):
        self.objects = {}

    def put_object(self, key, body, content_type="application/json"):
        self.objects[key] = body

    def get_object(self, key):
        return self.objects.get(key)

    def list_objects(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))


class Client:
    def __init__(self, body=None, error=None):
        self.body, self.error, self.urls = body, error, []

    def fetch_url(self, url, params, dataset, covers=None, file=False):
        assert file and dataset == "annual-pdf"
        self.urls.append(url)
        if self.error:
            raise self.error
        return self.body


# the annual-reports box of a Screener company page, as its HTML lays it out (assumption: the structure of the page,
# "Financial Year 2023 / from bse", not a stored page)
PAGE = """<html><div class="documents annual-reports flex-column"><h3>Annual reports</h3><ul class="list-links">
<li><a href="https://www.bseindia.com/xml-data/corpfiling/AttachHis/22d33d1d-af2a-4d2d-98c0-eff16cd73cb5.pdf" target="_blank">
 Financial Year 2023 <div class="ink-600 smaller">from bse</div></a></li>
<li><a href="https://www.bseindia.com/bseplus/AnnualReport/500112/68583500112.pdf" target="_blank">Financial Year 2022
<div class="ink-600 smaller">from bse</div></a></li>
<li><a href="https://nsearchives.nseindia.com/annual_reports/AR_SBIN_2023.pdf">Financial Year 2023<div>from nse</div></a></li>
</ul></div><div class="documents credit-ratings">x</div></html>"""


def test_screener_links():
    got = bp.screener_links(PAGE)
    assert got == [("FY23", "https://www.bseindia.com/xml-data/corpfiling/AttachHis/22d33d1d-af2a-4d2d-98c0-eff16cd73cb5.pdf"),
                   ("FY22", "https://www.bseindia.com/bseplus/AnnualReport/500112/68583500112.pdf")]
    assert bp.screener_links("<html>no box</html>") == []


def _bank(sink, scrip="500112"):
    sink.put_object(xf.key(scrip, "Q4FY23", STANDALONE), xf.dumps(doc(YEAR + SHEET)))
    from bse_intel import screener_download as sd
    sink.put_object(f"{sd.PREFIX}2026-10-30/SBIN_s.html.gz", sd.pack(PAGE))


def test_run_fetches_keeps_and_reads(monkeypatch):
    sink, pdf = Sink(), (FIX / "sbi_fy23_sch10_16.pdf").read_bytes()
    _bank(sink)
    client = Client(body=pdf)
    out = bp.run(sink, client, [("500112", "SBIN")], years=1)
    assert out["banks"] == 1 and out["downloaded"] == 1 and out["reports_read"] == 1
    assert client.urls == ["https://www.bseindia.com/xml-data/corpfiling/AttachHis/22d33d1d-af2a-4d2d-98c0-eff16cd73cb5.pdf"]
    kept = "raw/annual-pdf/SBIN/22d33d1d-af2a-4d2d-98c0-eff16cd73cb5.pdf.gz"
    assert gzip.decompress(sink.objects[kept]) == pdf                     # every fetched file kept
    reading = json.loads(sink.objects[bp.key("500112", kept)])
    assert reading["years"] == ["FY23", "FY22"] and reading["figures"][STANDALONE]["FY23"]["cwip"] == pytest.approx(281.0721)
    check = [c for c in out["readings"][0]["checks"] if c["fy"] == "FY23"][0]
    assert check["depreciation_ok"] and check["fixed_ok"]
    # read again: nothing fetched, nothing read twice
    again = bp.run(sink, Client(error=AssertionError("no fetch")), [("500112", "SBIN")], years=1)
    assert again["downloaded"] == 0 and again["reports_read"] == 0
    # and the statements take it
    cf = sv.CompanyFacts(sink.list_objects(f"{xf.PREFIX}500112/"), sink.get_object)
    assert bp.attach(cf, sink, "500112") == 2
    rows, _ = sv._ours(cf, sv.BANK, STANDALONE, "annual", "FY23", {})
    assert rows["Depreciation"].value == pytest.approx(3297.2704)
    sheet, _ = sv._ours(cf, sv.BANK, STANDALONE, "balance", "Q4FY23", {})
    assert sheet["CWIP"].value == pytest.approx(281.0721)


def test_run_stops_on_a_refusal_and_at_the_file_cap():
    from bse_intel.adapters.bse import Blocked
    from bse_intel.nse import FileCapReached
    sink = Sink()
    _bank(sink)
    out = bp.run(sink, Client(error=Blocked("HTTP 403")), [("500112", "SBIN")], years=1)
    assert out["blocked"] and out["downloaded"] == 0
    out = bp.run(sink, Client(error=FileCapReached("cap")), [("500112", "SBIN")], years=1)
    assert out["capped"]


def test_run_skips_other_families_and_dry_run_keeps_files_only():
    sink, pdf = Sink(), (FIX / "sbi_fy23_sch10_16.pdf").read_bytes()
    corp = doc(YEAR)
    corp["template"] = "MCA-INDAS"
    sink.put_object(xf.key("500325", "Q4FY23", STANDALONE), xf.dumps(corp))
    out = bp.run(sink, Client(error=AssertionError("no fetch")), [("500325", "RELIANCE")])
    assert out["not_banks"] == 1 and out["banks"] == 0
    _bank(sink)
    out = bp.run(sink, Client(body=pdf), [("500112", "SBIN")], years=1, dry_run=True)
    assert out["downloaded"] == 1 and not sink.list_objects(bp.PREFIX)


def test_merge_prefers_the_years_own_report():
    own = {"years": ["FY23", "FY22"], "figures": {STANDALONE: {"FY23": {"depreciation": 1.0}, "FY22": {"depreciation": 2.0}}}}
    older = {"years": ["FY22", "FY21"], "figures": {STANDALONE: {"FY22": {"depreciation": 3.0}}}}
    got = bp.merge([own, older])
    assert got[("FY22", STANDALONE)]["depreciation"] == 3.0 and got[("FY23", STANDALONE)]["depreciation"] == 1.0
    assert bp.merge([older, own])[("FY22", STANDALONE)]["depreciation"] == 3.0
