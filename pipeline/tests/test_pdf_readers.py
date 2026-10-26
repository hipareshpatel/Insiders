"""The PDF readers ensemble (pdf_readers.py): fake readers, small PDFs made in the test, no heavy package, no network."""

from __future__ import annotations

import pymupdf
import pytest
from test_pdf_referee import STANDALONE_PAGE, FakeNse, filing, make_pdf, pair

from bse_intel import pdf_readers as prd
from bse_intel import pdf_referee as pr

URL = "https://nsearchives.nseindia.com/corporate/RES.pdf"


def reading(reader, family, value=120.5, verbatim=True, layer=True, status="ok"):
    return prd.Reading(reader, family, status, value if status == "ok" else None, verbatim, layer,
                       "textlayer" if verbatim else "ocr", "Revenue from operations", 1)


# --- the settlement rule -----------------------------------------------------------------------------------------------

def test_two_families_agreeing_settle():
    v = prd.settle([reading("native", "textlayer-native"), reading("camelot", "camelot")])
    assert v.status == "settled" and v.value == 120.5 and v.agreed == ["native", "camelot"] and v.disagreed == []


def test_one_reader_alone_is_not_settled():
    assert prd.settle([reading("native", "textlayer-native")]).status == "unsure"
    one = prd.settle([reading("native", "textlayer-native"), reading("docling", "docling", status="unavailable")])
    assert one.status == "unsure" and one.abstained == ["docling(unavailable)"]


def test_unavailable_readers_leave_the_rest_to_decide():
    v = prd.settle([reading("mineru", "mineru", status="unavailable"), reading("native", "textlayer-native"),
                    reading("paddle", "paddle")])
    assert v.status == "settled" and v.abstained == ["mineru(unavailable)"]


def test_a_different_value_from_any_reader_keeps_it_open():
    v = prd.settle([reading("native", "textlayer-native"), reading("docling", "docling"),
                    reading("surya", "surya", value=125.0)])
    assert v.status == "disagree" and v.disagreed == ["surya"] and set(v.agreed) == {"native", "docling"}


def test_readings_within_the_referees_precision_agree():
    v = prd.settle([reading("native", "textlayer-native", 120.5), reading("camelot", "camelot", 120.504)])
    assert v.status == "settled"
    assert prd.settle([reading("a", "x", 120.5), reading("b", "y", 120.9)]).status == "disagree"


def test_marker_and_surya_share_a_family():
    assert prd.READERS["marker"].family == prd.READERS["surya"].family == "surya"
    alone = prd.settle([reading("marker", "surya"), reading("surya", "surya")])
    assert alone.status == "unsure" and "one family" in alone.reason
    assert prd.settle([reading("marker", "surya"), reading("docling", "docling")]).status == "settled"
    blocked = prd.settle([reading("marker", "surya"), reading("docling", "docling"), reading("surya", "surya", 99.0)])
    assert blocked.status == "disagree"


def test_native_ocr_and_paddle_share_a_family_native_text_layer_does_not():
    native, paddle = prd.READERS["native"], prd.READERS["paddle"]
    assert prd.family_of(native, "ocr", False) == prd.family_of(paddle, "ocr", False) == "paddle"
    assert prd.family_of(native, "textlayer", True) == "textlayer-native" != prd.family_of(paddle, "textlayer", True)
    scan = prd.settle([reading("native", "paddle", verbatim=False, layer=False),
                       reading("paddle", "paddle", verbatim=False, layer=False)])
    assert scan.status == "unsure"
    assert prd.settle([reading("native", "textlayer-native"), reading("paddle", "paddle")]).status == "settled"


def test_text_layer_digits_are_required():
    v = prd.settle([reading("native", "textlayer-native", verbatim=False), reading("camelot", "camelot", verbatim=False)])
    assert v.status == "unsure" and "text layer" in v.reason
    mixed = prd.settle([reading("native", "textlayer-native"), reading("camelot", "camelot", verbatim=False)])
    assert mixed.status == "unsure"          # only one family has the digits in the layer


def test_scanned_page_agreement_is_a_lead_not_a_verdict():
    v = prd.settle([reading("native", "paddle", verbatim=False, layer=False),
                    reading("tatr", "tesseract", verbatim=False, layer=False)])
    assert v.status == "scanned_lead" and v.value == 120.5


# --- tables to rows, units, the page layer -----------------------------------------------------------------------------

def grid(unit="(Rs. in crore)", title=None, revenue=("120.50", "110.25", "100.10", "230.75", "440.00")):
    return ([[title]] if title else []) + [[unit], ["", "Quarter ended", "Quarter ended", "Quarter ended", "Half year ended", "Year ended"],
            ["Particulars", "30.09.2026", "30.06.2026", "30.09.2025", "30.09.2026", "31.03.2026"],
            ["Revenue from operations", *revenue]]


class FakeReader(prd.Reader):
    worker = False

    def __init__(self, name, family, cells, ocr_family=""):
        self.name, self.family, self.ocr_family, self.cells = name, family, ocr_family, cells

    def available(self):
        return self.cells is not None

    def extract(self, sub_pdf):
        return [(1, self.cells)]


def install(monkeypatch, *readers, native=False):
    table = {r.name: r for r in readers}
    if native:
        table["native"] = prd.READERS["native"]
    monkeypatch.setattr(prd, "READERS", table)
    monkeypatch.setenv("PDF_READERS", ",".join(table))


def run_pair(pdf, **kw):
    nse = FakeNse([filing()], {URL: pdf})
    return pr.run(nse, [pair(**kw)], ocr=False)["rows"][0]


def test_unit_conversion_lakh_and_crore_agree(monkeypatch):
    lakh = grid("(Rs. in lakhs)", revenue=("12,050.00", "11,025.00", "10,010.00", "23,075.00", "44,000.00"))
    layers = {1: prd.page_layer("x" * 60)}
    crore_rows = prd.tables_to_rows([prd.Table("a", 1, grid())], layers)
    lakh_rows = prd.tables_to_rows([prd.Table("b", 1, lakh)], layers)
    a = pr.figure_for(crore_rows, "Q2FY27", "revenue", "STANDALONE")["values"][0][0]
    b = pr.figure_for(lakh_rows, "Q2FY27", "revenue", "STANDALONE")["values"][0][0]
    assert a == pytest.approx(120.5) and b == pytest.approx(120.5)
    # a filing printed in lakh: both readers' figures are in its text layer and convert to the crore figure
    page = [line.replace("(Rs. in crore)", "(Rs. in lakhs)").replace("120.50", "12,050.00") for line in STANDALONE_PAGE]
    install(monkeypatch, FakeReader("a", "fa", lakh), FakeReader("b", "fb", lakh))
    row = run_pair(make_pdf(page))
    assert row["pdf_verdict"] == "pdf_matches_ours" and row["pdf_value"] == pytest.approx(120.5)
    assert row["readers"] == "agreed=a+b;disagreed="


def test_two_readers_from_two_families_settle_with_native(monkeypatch):
    install(monkeypatch, FakeReader("camelot", "camelot", grid()), native=True)
    row = run_pair(make_pdf(STANDALONE_PAGE))
    assert row["pdf_verdict"] == "pdf_matches_ours"
    assert set(row["readers"].split(";")[0][len("agreed="):].split("+")) == {"native", "camelot"}


def test_a_disagreeing_reader_leaves_the_pair_open(monkeypatch):
    install(monkeypatch, FakeReader("a", "fa", grid()), FakeReader("b", "fb", grid()),
            FakeReader("c", "fc", grid(revenue=("125.00", "1.00", "2.00", "3.00", "4.00"))))
    row = run_pair(make_pdf(STANDALONE_PAGE))
    assert row["pdf_verdict"] == "pdf_disagree" and row["readers"] == "agreed=a+b;disagreed=c"


def test_one_reader_with_the_rest_unavailable_is_unsure(monkeypatch):
    install(monkeypatch, FakeReader("a", "fa", grid()), FakeReader("b", "fb", None))
    row = run_pair(make_pdf(STANDALONE_PAGE))
    assert row["pdf_verdict"] == "pdf_unsure" and "abstained=b(unavailable)" in row["readers"]


def test_digits_missing_from_the_text_layer_never_settle(monkeypatch):
    wrong = grid(revenue=("120.51", "110.25", "100.10", "230.75", "440.00"))
    install(monkeypatch, FakeReader("a", "fa", wrong), FakeReader("b", "fb", wrong))
    row = run_pair(make_pdf(STANDALONE_PAGE), ours=120.51, theirs=125.0)
    assert row["pdf_verdict"] == "pdf_unsure" and "text layer" in row["reason"]


def test_a_page_without_a_text_layer_gives_a_scanned_lead(monkeypatch):
    doc = pymupdf.open()
    doc.new_page(width=900, height=842)
    titled = grid(title="Statement of Standalone Unaudited Financial Results")
    install(monkeypatch, FakeReader("a", "fa", titled, ocr_family="ocr1"), FakeReader("b", "fb", titled, ocr_family="ocr2"))
    row = run_pair(doc.tobytes())
    assert row["pdf_verdict"] == "pdf_scanned_lead" and row["pdf_value"] == pytest.approx(120.5)
    summary = pr.summarise([row], {"lists": 1, "pdfs": 1}, 1)
    assert "pdf_scanned_lead" in pr.render(summary) and "readers" in pr.to_csv(summary).splitlines()[0]


def test_the_default_path_is_unchanged(monkeypatch):
    monkeypatch.delenv("PDF_READERS", raising=False)
    nse = FakeNse([filing()], {URL: make_pdf(STANDALONE_PAGE)})
    src = pr.Sources(nse, ocr=False)
    assert src.ensemble is None and prd.configured_readers() == ["native"]
    summary = pr.run(nse, [pair()], ocr=False)
    row = summary["rows"][0]
    assert row["pdf_verdict"] == "pdf_matches_ours" and "readers" not in row
    assert pr.to_csv(summary).splitlines()[0] == ",".join(pr.CSV_HEADER)
    assert "pdf_disagree" not in pr.render(summary)
    monkeypatch.setenv("PDF_READERS", "native")
    assert pr.Sources(nse, ocr=False).ensemble is None


def test_unknown_reader_name_is_refused():
    with pytest.raises(ValueError):
        prd.configured_readers("native,nosuch")


# --- parts: statement pages, HTML tables, Table Transformer cells ----------------------------------------------------

def test_statement_pages_are_the_results_pages_at_most_four():
    pages = [["Notes to accounts", "nothing here"]] + [STANDALONE_PAGE] * 6
    layers = prd.page_layers(make_pdf(*pages))
    assert prd.statement_pages(layers) == [2, 3, 4, 5]


def test_the_page_layer_gives_no_unit_when_two_are_declared():
    layer = prd.page_layer("Statement of Results (Rs. in crore)\n(Rs. in lakhs)\n" + "x" * 50)
    assert layer.context == ""
    assert "crore" in prd.page_layer("Statement of Standalone Results\n(Rs. in crore)\n" + "x" * 50).context


def test_html_tables_with_spans():
    html = ("<table><tr><th rowspan=2>Particulars</th><th colspan=2>Quarter ended</th></tr>"
            "<tr><td>30.09.2026</td><td>30.06.2026</td></tr><tr><td>Revenue</td><td>1.0</td><td>2.0</td></tr></table>")
    assert prd.html_tables(html) == [[["Particulars", "Quarter ended", "Quarter ended"], ["", "30.09.2026", "30.06.2026"],
                                      ["Revenue", "1.0", "2.0"]]]


def test_table_transformer_cells_from_mocked_structure():
    rows = [(0, 0, 100, 10), (0, 10, 100, 20)]
    cols = [(60, 0, 100, 20), (0, 0, 60, 20)]                  # unsorted on purpose
    words = [(2, 2, 30, 8, "Revenue"), (62, 2, 90, 8, "120.50"), (2, 12, 30, 18, "Profit"), (62, 12, 90, 18, "12.30")]
    cells = prd.cells_from_structure(rows, cols, lambda box, ci: prd.words_in(words, box))
    assert cells == [["Revenue", "120.50"], ["Profit", "12.30"]]
    assert prd.TatrReader.DETECTION == "microsoft/table-transformer-detection"
    assert prd.READERS["tatr"].ocr_family == "tesseract" and prd.READERS["tatr"].family == "tatr"


def test_readers_missing_a_package_report_unavailable(monkeypatch):
    monkeypatch.delenv("PDF_READER_PYTHON_DOCLING", raising=False)
    monkeypatch.setattr(prd, "_has", lambda module: False)
    assert not prd.READERS["docling"].available() and prd.READERS["native"].available()
    monkeypatch.setenv("PDF_READER_PYTHON_DOCLING", "/venv/bin/python")
    assert prd.READERS["docling"].available()      # runs as a worker in its own environment


# --- one reader a process: the readings files and the matrix jobs -----------------------------------------------------

def test_read_all_writes_one_readers_tables_and_the_ensemble_settles_from_the_files(monkeypatch, tmp_path):
    import json
    pdf_dir, tables_dir = tmp_path / "pdfs", tmp_path / "tables"
    pdf_dir.mkdir()
    tables_dir.mkdir()
    pdf = make_pdf(STANDALONE_PAGE)
    key = prd.pdf_key(URL)
    (pdf_dir / f"{key}.pdf").write_bytes(pdf)
    (pdf_dir / "manifest.json").write_text(json.dumps({key: URL}))
    fake = FakeReader("camelot", "camelot", grid())
    monkeypatch.setattr(prd, "READERS", {"camelot": fake, "native": prd.READERS["native"]})
    assert prd.read_all("camelot", str(pdf_dir), str(tables_dir / "camelot.json")) == 0
    stored = json.loads((tables_dir / "camelot.json").read_text())
    assert stored["reader"] == "camelot" and stored["pdfs"][key]["pages"] == [1] and stored["pdfs"][key]["tables"][0]["page"] == 1
    # the final job: PDFs from the cache folder (no NSE download), the other readers' readings from their files
    monkeypatch.setattr(prd, "READERS", {"camelot": fake, "native": prd.READERS["native"], "docling": FakeReader("docling", "docling", None)})
    monkeypatch.setenv("PDF_READERS", "native,camelot,docling")
    monkeypatch.setenv("PDF_READER_TABLES_DIR", str(tables_dir))
    monkeypatch.setenv("PDF_CACHE_DIR", str(pdf_dir))
    nse = FakeNse([filing()], {})                                   # fetch would return None: the cache must serve it
    row = pr.run(nse, [pair()], ocr=False)["rows"][0]
    assert nse.fetches == [] and row["pdf_verdict"] == "pdf_matches_ours"
    assert "abstained=docling(unavailable)" in row["readers"]


def test_a_reader_missing_its_package_writes_unavailable_for_every_pdf(monkeypatch, tmp_path):
    import json
    (tmp_path / "manifest.json").write_text(json.dumps({"k1": "u1"}))
    monkeypatch.setattr(prd, "READERS", {"docling": FakeReader("docling", "docling", None)})
    prd.read_all("docling", str(tmp_path), str(tmp_path / "o.json"))
    assert json.loads((tmp_path / "o.json").read_text())["pdfs"]["k1"]["error"] == "unavailable"


# --- independent review fixes: basis, vetoes, cell-level proof, exact tolerance -----------------------------------------

CONSOLIDATED_PAGE = [
    "Statement of Consolidated Unaudited Financial Results for the quarter ended 30 September 2026",
    *STANDALONE_PAGE[1:3],
    "Particulars 30.09.2026 30.06.2026 30.09.2025 30.09.2026 31.03.2026",
    "1 Revenue from operations 999.50 110.25 100.10 230.75 440.00",
    "2 Other income 1.10 1.00 0.90 2.10 4.00",
    "Note: the standalone results are available on the company website.",
]
TITLED = "Statement of Standalone Unaudited Financial Results"


def test_untitled_grids_never_default_to_standalone_on_a_consolidated_document(monkeypatch):
    g = grid(revenue=("999.50", "110.25", "100.10", "230.75", "440.00"))
    install(monkeypatch, FakeReader("a", "fa", g), FakeReader("b", "fb", g), native=True)
    row = run_pair(make_pdf(CONSOLIDATED_PAGE), ours=999.5, theirs=120.5)
    assert row["pdf_verdict"] != "pdf_matches_ours"
    assert row["pdf_verdict"] == "pdf_disagree"                      # native sees the figure only on the other basis
    assert "disagreed=native" in row["readers"] and "abstained=a(none)+b(none)" in row["readers"]


def test_a_reader_with_the_figure_on_the_other_basis_vetoes():
    other = prd.Reading("native", "textlayer-native", "otherbasis", note="CONSOLIDATED only")
    v = prd.settle([reading("a", "fa"), reading("b", "fb"), other])
    assert v.status == "disagree" and v.disagreed == ["native"]
    assert prd.settle([other]).status == "disagree"


def test_a_readers_conflicting_rows_veto_while_an_unproven_column_only_abstains():
    conflict = prd.Reading("tabula", "tabula", "conflict", note="rows differ: 1, 2")
    v = prd.settle([reading("a", "fa"), reading("b", "fb"), conflict])
    assert v.status == "unsure" and "tabula" in v.reason
    none = prd.Reading("tabula", "tabula", "none")
    assert prd.settle([reading("a", "fa"), reading("b", "fb"), none]).status == "settled"


def test_agreement_is_exact_at_the_printed_precision_and_transitive():
    assert prd.settle([reading("a", "fa", 12345.67), reading("b", "fb", 12349.00)]).status == "disagree"   # not 0.05%
    assert prd.settle([reading("a", "fa", 100.00), reading("b", "fb", 100.004)]).status == "settled"
    chain = prd.settle([reading("a", "fa", 100.000), reading("b", "fb", 100.004), reading("c", "fc", 100.008)])
    assert chain.status == "disagree"                                # a-c differ by more than half a unit
    coarse = [prd.Reading("a", "fa", "ok", 120.5, True, True, "textlayer", "Revenue", 1, tol=0.05),
              prd.Reading("b", "fb", "ok", 120.52, True, True, "textlayer", "Revenue", 1, tol=0.005)]
    assert prd.settle(coarse).status == "settled"                    # one reader prints one decimal: the coarser one rules


def test_the_settled_value_comes_from_a_text_layer_reader():
    docling = prd.Reading("docling", "paddle", "ok", 5000.004, False, True, "ocr", "Revenue", 1)
    v = prd.settle([docling, reading("native", "textlayer-native", 5000.0), reading("camelot", "camelot", 5000.0)])
    assert v.status == "settled" and v.value == 5000.0 and v.agreed == ["native", "camelot"]


TWO_BASES = [
    "Statement of Consolidated Unaudited Financial Results", "(Rs. in crore)",
    "Quarter ended Quarter ended Quarter ended Half year ended Year ended",
    "Particulars 30.09.2026 30.06.2026 30.09.2025 30.09.2026 31.03.2026",
    "Revenue from operations 999.50 110.25 100.10 230.75 440.00",
    "Other income 777.00 1.00 0.90 2.10 4.00",
    "Statement of Standalone Unaudited Financial Results", "(Rs. in crore)",
    "Quarter ended Quarter ended Quarter ended Half year ended Year ended",
    "Particulars 30.09.2026 30.06.2026 30.09.2025 30.09.2026 31.03.2026",
    "Revenue from operations 120.50 111.00 100.10 230.75 440.00",
]


def test_the_digits_must_be_on_the_same_row_column_and_basis_in_the_layer(monkeypatch):
    def attempt(revenue):
        g = grid(title=TITLED, revenue=revenue)
        install(monkeypatch, FakeReader("a", "fa", g), FakeReader("b", "fb", g))
        return run_pair(make_pdf(TWO_BASES), ours=revenue[0].replace(",", ""), theirs=1.0)

    good = attempt(("120.50", "111.00", "100.10", "230.75", "440.00"))
    assert good["pdf_verdict"] == "pdf_matches_ours"
    # 999.50 is in the layer, on the consolidated revenue row: the wrong basis for a standalone pair
    assert attempt(("999.50", "111.00", "100.10", "230.75", "440.00"))["pdf_verdict"] == "pdf_unsure"
    # 777.00 is in the layer on the "Other income" row, not the revenue row
    assert attempt(("777.00", "111.00", "100.10", "230.75", "440.00"))["pdf_verdict"] == "pdf_unsure"
    # 111.00 is on the revenue row but in the second column, not the period's
    assert attempt(("111.00", "111.00", "100.10", "230.75", "440.00"))["pdf_verdict"] == "pdf_unsure"


def test_rapidtable_is_the_paddle_family():
    """rapid-table runs the PP-StructureV3 table models: with PP-StructureV3 it is one family, so the two never settle alone."""
    from bse_intel.pdf_readers import READERS, Reading, settle
    def rd(n):
        return Reading(n, READERS[n].family, "ok", 10.0, True, True, "textlayer", "x", 1)
    assert READERS["rapidtable"].family == READERS["paddle"].family == "paddle"
    assert settle([rd("paddle"), rd("rapidtable")]).status != "settled"


def test_title_ending_in_its_date_sets_the_basis():
    """A basis title ending in its date ("... September 30, 2025") switches the basis: the standalone row under it is not
    proven on the consolidated basis."""
    from bse_intel.pdf_readers import cell_in_layer, page_layer
    from bse_intel.pdf_referee import CONSOLIDATED, STANDALONE
    text = ("Consolidated Results\nRevenue from operations 200.00 190.00 180.00\n"
            "Standalone Financial Results for the quarter ended September 30, 2025\n"
            "Revenue from operations 100.00 90.00 80.00\n")
    layer = page_layer(text + "x" * 200)
    layer.text = text
    assert [b.basis for b in layer.bands() if b.nums and b.label.startswith("Revenue")] == [CONSOLIDATED, STANDALONE]
    assert cell_in_layer(layer, "Revenue from operations", CONSOLIDATED, 100.0, 0, 3, True) == ""
    assert cell_in_layer(layer, "Revenue from operations", STANDALONE, 100.0, 0, 3, True) == "100.00"


def test_a_data_row_ending_in_a_year_keeps_the_basis():
    """Only a results title ending in its date switches the basis; a data row that names a basis and ends in a year does not."""
    from bse_intel.pdf_readers import page_layer
    from bse_intel.pdf_referee import STANDALONE
    text = ("Statement of Standalone Financial Results for the quarter ended 30th September, 2025\n"
            "Profit attributable to owners (consolidated) 2025\nRevenue from operations 50.00 40.00\n")
    layer = page_layer(text + "x" * 200)
    layer.text = text
    assert [b.basis for b in layer.bands() if b.label.startswith("Revenue")] == [STANDALONE]
# --- adapters: what the first GitHub trial (run 40388046768, 26 Oct 2026) showed -----------------------------------------

import json
import pathlib
import sys
import types

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "pdf_readers"


def words_pdf(*pages: list[list[str]]) -> bytes:
    """A PDF whose every token sits at its own x on its row's baseline (the raw text then has one token a line, as a table's
    cells do in many results PDFs); a page is a list of rows, a row a list of tokens."""
    doc = pymupdf.open()
    for rows in pages:
        page = doc.new_page(width=900, height=842)
        for i, row in enumerate(rows):
            for j, token in enumerate(row):
                page.insert_text((20 + 110 * j, 40 + 16 * i), token, fontsize=8)
    return doc.tobytes()


def test_camelot_output_of_a_ruled_results_table_gets_its_columns_proven():
    """The real camelot table of RBL Bank's standalone page: the header spans columns ("Quarter ended" once over three dates)."""
    rows = json.loads((FIXTURES / "camelot_rbl.json").read_text())["rows"]
    layers = {1: prd.page_layer("UNAUDITED STANDALONE FINANCIAL RESULTS FOR THE QUARTER AND HALF YEAR ENDED\n(in lakh) " + "x" * 60)}
    parsed = prd.tables_to_rows([prd.Table("camelot", 1, rows)], layers)
    got = pr.figure_for(parsed, "Q2FY25", "revenue", pr.STANDALONE)
    assert [round(v, 2) for v, _, _ in got["values"]] == [3530.93]    # 353,093 lakh
    got = pr.figure_for(parsed, "FY24", "revenue", pr.STANDALONE)
    assert [round(v, 2) for v, _, _ in got["values"]] == [12394.30]       # the year column, after two quarter and two half columns


def test_merged_multiline_cells_are_split_into_their_rows():
    """pdfplumber's real output for J&K Bank: one cell holds the five printed rows of "Interest earned (a)-(d)" and the next
    holds their five figures (the line breaks were collapsed into spaces before, so the row was one long label)."""
    rows = json.loads((FIXTURES / "pdfplumber_jk_merged.json").read_text())["rows"]
    lines = prd.table_text(rows).splitlines()
    assert any(ln.startswith("b) Income on Investments") and "564.87" in ln and "558,84" in ln for ln in lines)
    assert not any("Income on Investments" in ln and "Advances" in ln for ln in lines)        # no longer one line
    # a label of 2 lines over figures of 3 is not guessed apart: joined
    assert prd.table_text([["a\nb", "1\n2\n3"]]) == "a b  1 2 3"
    assert prd.table_text([["Revenue\nOther income", "10.0\n2.0", "9.0\n1.0"]]) == "Revenue  10.0  9.0\nOther income  2.0  1.0"


def test_a_lone_basis_cell_above_the_columns_is_a_title():
    """Docling's real grid of an Indian results table starts with a cell that only says STANDALONE: not a title the referee
    reads, so it is written as "STANDALONE financial results"; a cell deeper in the table is left alone."""
    cells = [["", "STANDALONE", "", ""], ["Particulars", "Quarter Ended", "Quarter Ended", "Year Ended"],
             ["", "30/06/2024", "31/03/2024", "31/03/2024"], ["Revenue from Operations", "91,934.83", "116,366.01", "385,529.77"]]
    text = prd.table_text(cells)
    assert text.splitlines()[0] == "STANDALONE financial results"
    layers = {1: prd.page_layer("(Rs. in lakhs) " + "x" * 60)}
    parsed = prd.tables_to_rows([prd.Table("docling", 1, cells)], layers)
    assert parsed and parsed[0].basis == pr.STANDALONE
    deep = prd.table_text([["a", "1"], ["b", "2"], ["c", "3"], ["d", "4"], ["CONSOLIDATED", ""]])
    assert deep.splitlines()[-1] == "CONSOLIDATED"


def test_a_header_spanning_cell_is_repeated_over_its_columns():
    """PP-StructureV3 (and MinerU, Marker, Surya) give the header as HTML with colspan: "Quarter Ended" over three columns
    names the kind of each of the three dates below it, so the text is repeated over the span; figures and labels are not."""
    html = ('<html><body><table><thead><tr><td rowspan="3">Particulars</td><td colspan="3">Quarter Ended</td>'
            '<td colspan="2">Nine Months Ended</td><td>Year Ended</td></tr><tr><td>31.12.2024</td><td>30.09.2024</td>'
            '<td>31.12.2023</td><td>31.12.2024</td><td>31.12.2023</td><td>31.03.2024</td></tr></thead><tbody>'
            '<tr><td>Revenue from Operations</td><td>1,926.65</td><td>2,022.88</td><td>1,754.24</td><td>5,637.39</td>'
            '<td>5,200.89</td><td>7,100.46</td></tr><tr><td colspan="2">Total 12.50</td><td>1.0</td></tr></tbody></table></body></html>')
    grid_ = prd.html_tables(html)[0]
    assert grid_[0] == ["Particulars", "Quarter Ended", "Quarter Ended", "Quarter Ended", "Nine Months Ended", "Nine Months Ended",
                        "Year Ended"]
    assert grid_[-1] == ["Total 12.50", "", "1.0"]
    layers = {1: prd.page_layer("Standalone Financial Results\n(Rs. in crore) " + "x" * 60)}
    parsed = prd.tables_to_rows([prd.Table("paddle", 1, grid_)], layers)
    assert parsed[0].columns is not None
    assert [k for k, _ in parsed[0].columns] == ["quarter", "quarter", "quarter", "nine", "nine", "year"]
    assert prd.is_group_header("Quarter Ended") and not prd.is_group_header("Total 12.50")
    assert not prd.is_group_header("Revenue from operations") and not prd.is_group_header("30.09.2024 Quarter ended")


def test_a_table_without_its_header_takes_the_pages_header():
    """Camelot, Tabula and MinerU often start the table below the dates; the page's own header (read from its words) goes above."""
    pdf = words_pdf([["Statement of Standalone Financial Results for the quarter ended 30.09.2026"], ["(Rs. in crore)"],
                     ["Quarter ended", "Quarter ended", "Quarter ended", "Half year ended", "Year ended"],
                     ["30.09.2026", "30.06.2026", "30.09.2025", "30.09.2026", "31.03.2026"],
                     ["Revenue from operations", "120.50", "110.25", "100.10", "230.75", "440.00"]])
    layers = prd.page_layers(pdf)
    assert "30.09.2026" in layers[1].header_block() and "Quarter ended" in layers[1].header_block()
    cells = [["Revenue from operations", "120.50", "110.25", "100.10", "230.75", "440.00"]]
    parsed = prd.tables_to_rows([prd.Table("tabula", 1, cells)], layers)
    got = pr.figure_for(parsed, "Q2FY27", "revenue", pr.STANDALONE)
    assert [round(v, 2) for v, _, _ in got["values"]] == [120.5]
    # a table that has its own header is not given another
    own = prd.tables_to_rows([prd.Table("a", 1, grid())], layers)
    assert own[0].dates == parsed[0].dates
    # two different headers on the page: none is guessed
    two = words_pdf([["Statement of Standalone Financial Results"], ["30.09.2026", "30.06.2026"], ["31.03.2026", "31.03.2025"]])
    assert prd.page_layers(two)[1].header_block() == ""


def test_statement_pages_read_the_words_not_the_raw_text_lines():
    """The raw text of many results PDFs has one cell a line, so no line shows two dates and no page was ever chosen (18 of 47
    PDFs of the trial had no page); the rows of words show them. A page with revenue, profit and EPS rows ranks above one that
    only repeats the heading."""
    head = ["Statement of Standalone Financial Results for the quarter ended 30.09.2026"]
    dates = [["Quarter ended", "Quarter ended"], ["30.09.2026", "30.06.2026"]]
    pdf = words_pdf(
        [head, *dates, ["Segment revenue", "10.00", "9.00"]],
        [head, *dates, ["Revenue from operations", "120.50", "110.25"], ["Net profit for the period", "20.10", "18.00"],
         ["Basic earnings per share", "2.01", "1.80"]],
    )
    layers = prd.page_layers(pdf)
    assert not any(len(pr._dates_in(line)) >= 2 for line in layers[2].text.splitlines())     # the raw lines never show two
    assert prd.statement_pages(layers) == [1, 2]
    assert prd.statement_pages(layers, max_pages=1) == [2]


def test_page_context_names_the_basis_by_its_titles_when_both_words_appear():
    text = "Statement of Standalone Financial Results\nNote 3: the consolidated figures are on page 9\n(Rs. in crore)\n" + "x" * 50
    assert "Standalone Financial Results" in prd.page_layer(text).context
    two = "Statement of Standalone Financial Results\nStatement of Consolidated Financial Results\n(Rs. in crore)\n" + "x" * 50
    assert "Standalone" not in prd.page_layer(two).context       # two statements on a page: no basis is given to a table


# --- the heavy readers' own failures (mended; the model packages are replaced by fakes here) ---------------------------------

def test_tatr_structure_model_loads_when_its_config_has_a_null_dilation(monkeypatch, tmp_path):
    """transformers 5 builds its configs as strict dataclasses; the structure model's published config has "dilation": null
    ("Field 'dilation' expected bool, got NoneType", every tatr read of run 40388046768, reproduced with transformers 5.21.0)."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"dilation": None, "d_model": 256}))
    seen = {}

    class Config:
        @classmethod
        def from_dict(cls, data):
            seen["config"] = data
            return cls()

    class Model:
        @classmethod
        def from_pretrained(cls, name, config=None):
            if config is None:
                raise ValueError("StrictDataclassFieldValidationError: Validation error for field 'dilation'")
            return "model"

    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(hf_hub_download=lambda name, fname: str(cfg)))
    monkeypatch.setitem(sys.modules, "transformers", types.SimpleNamespace(TableTransformerConfig=Config))
    assert prd.TatrReader._structure_model(Model) == "model"
    assert seen["config"] == {"dilation": False, "d_model": 256}

    class Broken:
        @classmethod
        def from_pretrained(cls, name, config=None):
            raise OSError("offline")

    with pytest.raises(OSError):
        prd.TatrReader._structure_model(Broken)         # only the null field is mended


def test_tatr_structure_image_is_resized_by_its_longest_side():
    """The structure processor's size is {"longest_edge": 800} only, which transformers 5 refuses at resize time."""
    Image = pytest.importorskip("PIL.Image")   # Pillow comes with the reader extras; CI installs [dev] only
    image = Image.new("RGB", (1600, 400), "white")
    only_longest = types.SimpleNamespace(size=types.SimpleNamespace(longest_edge=800, shortest_edge=None))
    resized, kwargs = prd.TatrReader._longest_side(only_longest, image)
    assert resized.size == (800, 200) and kwargs == {"do_resize": False}
    both = types.SimpleNamespace(size={"shortest_edge": 800, "longest_edge": 1333})
    assert prd.TatrReader._longest_side(both, image) == (image, {})
    assert prd.TatrReader._longest_side(types.SimpleNamespace(), image) == (image, {})


def test_paddle_runs_without_onednn(monkeypatch):
    """With oneDNN on (the default) paddlepaddle 3.3.1 stops on every page: "ConvertPirAttribute2RuntimeAttribute not support"."""
    made = {}

    class FakePipeline:
        def __init__(self, **kwargs):
            made.update(kwargs)

        def predict(self, input):
            return []

    monkeypatch.setitem(sys.modules, "paddleocr", types.SimpleNamespace(PPStructureV3=FakePipeline))
    assert prd.PaddleReader().extract(make_pdf(STANDALONE_PAGE)) == []
    assert made["enable_mkldnn"] is False and made["use_table_recognition"] is True


def test_a_failed_download_is_tried_again_but_a_missing_file_is_not(monkeypatch):
    """The trial collected 47 PDFs and four more were never downloaded, so every reader read "unavailable" for their pairs."""
    monkeypatch.setattr("time.sleep", lambda s: None)

    class Src:
        def __init__(self, answers):
            self.answers, self.calls, self._payload = list(answers), 0, None

        def payload(self, url):
            self.calls += 1
            return self.answers.pop(0)

    flaky = Src([(None, "download failed (ReadTimeout)"), (None, "download failed (ReadTimeout)"), (b"%PDF", "")])
    assert prd.fetch_with_retry(flaky, "u") == (b"%PDF", "") and flaky.calls == 3
    gone = Src([(None, "NSE serves no file (404)")])
    assert prd.fetch_with_retry(gone, "u") == (None, "NSE serves no file (404)") and gone.calls == 1


def test_rapidtable_crops_the_page_to_its_results_table():
    """rapid-table's SLANet reads one table; given a whole page its rows ran into each other (0 of 98 figures right on the hard
    set, 25 right after the crop). The region runs from three rows above the dates to the last row of figures."""
    rows = [["Company Limited registered office address"], ["Statement of Standalone Financial Results"], ["(Rs. in crore)"],
            ["Particulars", "Quarter ended", "Quarter ended"], ["30.09.2026", "30.06.2026"],
            ["Revenue from operations", "120.50", "110.25"], ["Net profit", "20.10", "18.00"]]
    rows += [["Notes: the above results were approved by the board"]] * 7 + [["Footer 12.00 13.00"]]
    doc = pymupdf.open(stream=words_pdf(rows), filetype="pdf")
    words = doc[0].get_text("words")
    x0, y0, x1, y1 = prd.table_region(words)

    def top_of(text):
        return next(w[1] for w in words if w[4] == text)

    assert y0 <= top_of("(Rs.") and y0 > top_of("Company")                    # the title above the unit line is left out
    assert y1 >= top_of("Net") and y1 < top_of("Footer")                      # the notes and the footer are not in it
    assert prd.table_region([w for w in words if w[4] not in ("30.09.2026", "30.06.2026")]) is None      # no row of dates
