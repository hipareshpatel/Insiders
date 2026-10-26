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
    assert prd.html_tables(html) == [[["Particulars", "Quarter ended", ""], ["", "30.09.2026", "30.06.2026"],
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
