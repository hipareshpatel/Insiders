"""Local OCR (RapidOCR): its boxes put back into lines, and the order it is tried in against the vision route."""

import pytest

from bse_intel import ocr


def box(x, y, w=60, h=12):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def test_boxes_become_rows_with_the_label_before_its_figures():
    # As RapidOCR returns them: not in reading order, and a figure a pixel or two off its label's line.
    result = [
        (box(400, 101), "1,234.56", 0.99),
        (box(40, 100, w=200), "Revenue from operations", 0.98),
        (box(520, 99), "(98.10)", 0.97),
        (box(40, 130, w=120), "Other income", 0.99),
        (box(400, 131), "45.20", 0.99),
        (box(40, 60, w=180), "(Rs. in lakhs)", 0.95),
    ]
    assert ocr.lines_from_boxes(result) == (
        "(Rs. in lakhs)\n"
        "Revenue from operations  1,234.56  (98.10)\n"
        "Other income  45.20"
    )
    assert ocr.lines_from_boxes(None) == ""


def test_local_ocr_first_and_the_vision_route_when_it_reads_nothing(monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: True)
    asked = []
    vision = lambda png: asked.append(png) or "VISION TEXT"

    monkeypatch.setattr(ocr, "recognise", lambda png: "Revenue from operations  1,234.56")
    assert ocr.page_reader(vision)(b"png") == "Revenue from operations  1,234.56" and not asked

    monkeypatch.setattr(ocr, "recognise", lambda png: "  ")
    assert ocr.page_reader(vision)(b"png") == "VISION TEXT"

    def broken(png):
        raise RuntimeError("onnxruntime missing a library")

    monkeypatch.setattr(ocr, "recognise", broken)
    assert ocr.page_reader(vision)(b"png") == "VISION TEXT"
    with pytest.raises(RuntimeError):
        ocr.page_reader(None)(b"png")


def test_without_rapidocr_installed_the_vision_route_is_used_as_before(monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: False)
    vision = lambda png: "VISION TEXT"
    assert ocr.page_reader(vision) is vision
    assert ocr.page_reader(None) is None


@pytest.mark.skipif(not ocr.available(), reason="RapidOCR is an optional install")
def test_rapidocr_reads_a_rendered_statement_row():
    import pymupdf

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 100), "Revenue from operations", fontsize=14)
    page.insert_text((380, 100), "1,234.56", fontsize=14)
    png = page.get_pixmap(dpi=ocr.DPI).tobytes("png")
    text = ocr.recognise(png)
    assert "1,234.56" in text and "Revenue" in text.splitlines()[0]


def test_twenty_pages_a_document_with_rapidocr_and_six_on_the_vision_route(monkeypatch):
    from bse_intel.settings import Settings

    monkeypatch.delenv("MAX_OCR_PAGES", raising=False)
    monkeypatch.setattr(ocr, "available", lambda: True)
    assert Settings().max_ocr_pages == 20
    monkeypatch.setattr(ocr, "available", lambda: False)
    assert Settings().max_ocr_pages == 6
    monkeypatch.setenv("MAX_OCR_PAGES", "9")
    assert Settings().max_ocr_pages == 9


def test_a_sideways_page_is_turned_until_its_text_lies_flat(monkeypatch):
    """A landscape table on a portrait page reads with high confidence - each run of text is recognised -
    but its boxes stand on end, and putting them into lines by height turns its columns into rows. The
    benchmark's rotated Form AOC-1 came back as 17 transposed rows. A page whose boxes mostly stand on end
    is read again turned each way, and the reading whose boxes lie flat is kept."""
    np = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")

    def tall(x, y):
        return [[x, y], [x + 12, y], [x + 12, y + 90], [x, y + 90]]

    sideways = [(tall(40 * i, 50), f"col {i}", 0.98) for i in range(10)]
    flat = [(box(40, 100 + 20 * i, w=200), f"Subsidiary {i}  {i * 100:,}", 0.99) for i in range(10)]
    reads = []

    class Engine:
        def __call__(self, image):
            reads.append(image)
            if len(reads) == 1:                      # the page as rendered
                return sideways, None
            return (flat, None) if len(reads) == 2 else (sideways, None)   # turned clockwise: lies flat

    png = cv2.imencode(".png", np.zeros((40, 30, 3), np.uint8))[1].tobytes()
    monkeypatch.setattr(ocr, "_engine", Engine())
    text = ocr.recognise(png)
    assert len(reads) == 3, "read once as rendered, then a quarter turn each way"
    assert text.splitlines()[0] == "Subsidiary 0  0" and len(text.splitlines()) == 10
    assert ocr.lying_flat(sideways) == 0.0 and ocr.lying_flat(flat) == 1.0

    reads.clear()
    monkeypatch.setattr(ocr, "_engine", lambda image: reads.append(image) or (flat, None))
    assert ocr.recognise(png).startswith("Subsidiary 0") and len(reads) == 1, "an upright page is read once"


def test_the_text_layer_puts_back_the_nils_ocr_drops_and_nothing_else():
    """OCR loses thin cells, and every later figure in the row slides a column left: Novartis's
    "(2.0) 0.4 - (1.7) 1.7" came back "(2.0) 0.4 (1.7) 1.7" (benchmark, 2026-10-17). Where an OCR row's
    figures are exactly a text-layer row's, in order, the text layer's values - nils in place - are used."""
    layer = ("Particulars 30.09.2025 30.06.2025 30.09.2024\n"
             "(f) Impairment Loss on Receivables (2.0) 0.4 - (1.7) 1.7\n"
             "Income tax relating to these items (3.3) – (4.1) (3.3) (4.1)\n"
             "Other income 12.4 11.0 9.8 23.4 20.1\n"
             "Exceptional items Nil 5.0 Nil 5.0 Nil")
    ocr_text = ("Particulars  30.09.2025  30.06.2025  30.09.2024\n"
                "(f) Impairment Loss on Receivables  (2.0)  0.4  (1.7)  1.7\n"
                "Income tax relating to these items  (3.3)  (4.1)  (3.3)  (4.1)\n"
                "Other income  12.4  11.0  9.8  23.4  20.1\n"
                "Exceptional items  5.0  5.0\n"
                "Finance costs  (2.0)  0.4  (1.7)  1.8")
    # Novartis's statement is a scan: its text layer is an invisible OCR of its own, not the PDF's text
    merged = ocr.merge_with_text_layer(ocr_text, layer, layer_exact=False).splitlines()
    assert merged[1] == "(f) Impairment Loss on Receivables  (2.0) 0.4 - (1.7) 1.7"
    assert merged[2] == "Income tax relating to these items  (3.3) – (4.1) (3.3) (4.1)"
    assert merged[4] == "Exceptional items  Nil 5.0 Nil 5.0 Nil"
    assert merged[0] == "Particulars  30.09.2025  30.06.2025  30.09.2024", "a header row is OCR's"
    assert merged[3] == "Other income  12.4  11.0  9.8  23.4  20.1", "no nil to give back: OCR's row"
    assert merged[5] == "Finance costs  (2.0)  0.4  (1.7)  1.8", "one figure differs: not the same row"
    assert ocr.merge_with_text_layer(ocr_text, "") == ocr_text
    twice = layer + "\nDeferred tax 5.0 - - 5.0 -"
    assert ocr.merge_with_text_layer(ocr_text, twice, layer_exact=False).splitlines()[4] == \
        "Exceptional items  Nil 5.0 Nil 5.0 Nil", "two text-layer rows carry these figures: the one under the same label"
    unlabelled = ocr_text.replace("Exceptional items", "Excptnl itms")
    assert ocr.merge_with_text_layer(unlabelled, twice, layer_exact=False).splitlines()[4] == "Excptnl itms  5.0  5.0", \
        "two rows, nils in different places, neither under OCR's label: which one is unknown"
    # The PDF's own text: a line with exactly the row's figures is the row, every cell and character as printed.
    exact = ocr.merge_with_text_layer(ocr_text, layer).splitlines()
    assert exact[1] == "(f) Impairment Loss on Receivables (2.0) 0.4 - (1.7) 1.7"
    assert exact[5] == "Finance costs  (2.0)  0.4  (1.7)  1.8"
    aoc = "1 Jubilant Clinsys Limited September 21, 2004 INR 20 20 40 - - 2 2 1 1 Nil 100.00%"
    assert ocr.merge_with_text_layer("1  Jubilant Clinsys Limited  September 21, 2004  INR  20  20  40  2  2  1  1  i!n  "
                                     "100.00%", aoc) == aoc, "OCR read the Nil as 'i!n': the PDF's own line is the row"


def test_a_figure_ocr_misread_is_taken_from_a_clean_text_layer():
    """Jubilant's 978 came back from OCR as "8L6" and (70) as "(0L)" (benchmark page G, 2026-10-17); a
    scan's own OCR layer read Kanoria's (2,164) as "(Z,l64}". A garbled figure is taken from the other reader
    when its is clean. Two clean figures that differ: the PDF's own text is exact, a scan's OCR layer is not."""
    layer = "Total tax expense 547 298 81 1,443 978\n(ii) Items reclassified (58) 637 (70) 845 497"
    ocr_text = "Total tax expense  547  298  81  1,448  8L6\n(ii) Items reclassified  (58)  637  (0L)  845  497"
    assert ocr.merge_with_text_layer(ocr_text, layer).splitlines() == [
        "Total tax expense  547 298 81 1,443 978", "(ii) Items reclassified  (58) 637 (70) 845 497"]
    assert ocr.merge_with_text_layer(ocr_text, layer, layer_exact=False).splitlines()[0] == \
        "Total tax expense  547 298 81 1,448 978", "a scan's OCR layer fills a gap but does not overrule"
    scan_layer = "Total Comprehensive Income far the Period (Z,l64} (1,533) (1,482) (5,842)"
    assert ocr.merge_with_text_layer("Total Comprehensive Income for the Period  (2,164}  ('35'3)  (1,482)  (5,842)",
                                     scan_layer, layer_exact=False) == \
        "Total Comprehensive Income for the Period  (2,164) (1,533) (1,482) (5,842)", \
        "each reader's clean figure, a brace read as the bracket it is"


def _figure_pdf() -> bytes:
    import pymupdf

    pdf = pymupdf.open()
    pdf.new_page().insert_textbox(pymupdf.Rect(36, 36, 560, 800), "Statement of profit and loss\n" + "\n".join(
        f"Line {chr(65 + i)} {1000 + i:,}.50 - {900 + i:,}.25 {4000 + i:,}.75" for i in range(8)), fontsize=9)
    pdf.new_page().insert_textbox(pymupdf.Rect(36, 36, 560, 800),
                                  "The Board approved the results for the quarter ended 30 September 2025. " * 4, fontsize=9)
    return pdf.tobytes()


def test_a_sideways_table_s_text_layer_is_read_in_rows():
    """Form AOC-1 set landscape on a portrait page: PyMuPDF's reading order made its columns into lines and
    kept none of its 16 rows (benchmark page B). Its words, turned upright, give every row back, nils included."""
    import pymupdf

    from bse_intel.extract import Document

    pdf = pymupdf.open()
    page = pdf.new_page()
    rows = [f"Subsidiary {chr(65 + i)} INR {100 + i:,}.50 - {2000 + i:,}.25 Nil {(i + 1) * 1111:,}.75" for i in range(8)]
    for i, row in enumerate(rows):
        x = 80 + 24 * i
        for cell, y in zip(row.split(), (700, 640, 600, 520, 480, 400, 360, 280)):
            page.insert_text((x, y), cell.replace("Subsidiary", "Sub"), fontsize=9, rotate=90)   # text runs up the page
    text = Document(pdf.tobytes())._digital[0]
    assert text.splitlines()[0].split() == "Sub A INR 100.50 - 2,000.25 Nil 1,111.75".split()
    assert len(text.splitlines()) == 8


def test_a_page_of_figures_is_read_by_ocr_first_and_a_prose_page_by_its_text_layer():
    from bse_intel.extract import Document, amounts, cache_needs_ocr, figure_page

    assert figure_page("Revenue 1,234.56 (98.10) " * 8) and not figure_page("On 30 September 2025, 12 directors met.")
    assert amounts("1,234.56 (98.10) 12.5% 2025 30.09.2025 1,23,456") == 4, "years and dates are not amounts"
    reads = []

    def read(png):
        reads.append(png)
        return "\n".join(f"Line {chr(65 + i)}  {1000 + i:,}.50  {900 + i:,}.25  {4000 + i:,}.75" for i in range(8))

    doc = Document(_figure_pdf(), figure_reader=read)
    assert doc.page_text(0).splitlines()[0] == "Line A 1,000.50 - 900.25 4,000.75", "the PDF's own row, its nil kept"
    assert doc.page_text(1).startswith("The Board approved") and len(reads) == 1, "a prose page is not OCR'd"
    doc.page_text(0)
    assert len(reads) == 1 and doc.figure_pages_used == 1 and doc.ocr_pages_used == 0, "read once, own budget"
    assert doc.page_text(0, figures=False).startswith("Statement of profit"), "the duplicate check's text layer"
    cached = doc.to_cache()
    assert cached["local_ocr"] == 1 and not cache_needs_ocr(cached, local_ocr=True)
    assert Document.from_cache(cached).page_text(0).startswith("Line A 1,000.50 - 900.25")

    before = {k: v for k, v in cached.items() if k not in ("local_ocr", "ocr")}
    assert cache_needs_ocr(before, local_ocr=True), "an entry from before: read the PDF again, once"
    assert not cache_needs_ocr(before, local_ocr=False), "nothing to gain without local OCR"
    stale = Document(_figure_pdf(), figure_reader=read)
    stale.keep_ocr({**before, "ocr": {"1": "OLD OCR"}})
    assert stale.page_text(1).startswith("The Board"), "pages OCR'd by the older line-building are read again"

    assert Document(_figure_pdf()).page_text(0).startswith("Statement of profit"), "no local OCR: the text layer"
    assert Document(_figure_pdf(), figure_reader=lambda png: "Line A 1,000.50").page_text(0).startswith(
        "Statement of profit"), "OCR read too few of the page's amounts: the text layer"

    def broken(png):
        raise RuntimeError("onnxruntime missing a library")

    # A scan whose own OCR text is drawn under the page image (Heritage Foods): its line is not the PDF's text,
    # so it does not replace RapidOCR's row - the label stays readable - though its nil still goes back.
    import pymupdf

    scan = pymupdf.open()
    page = scan.new_page()
    page.insert_textbox(pymupdf.Rect(36, 36, 560, 800), "\n".join(
        f"Total e.-.:pcnscs {chr(65 + i)} {1000 + i:,}.50 - {900 + i:,}.25 {4000 + i:,}.75" for i in range(8)), fontsize=9)
    image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    image.clear_with(200)
    page.insert_image(page.rect, pixmap=image, keep_proportion=False)  # a scan fills its page (PyMuPDF 2.0 keeps the square)
    beneath = Document(scan.tobytes(), figure_reader=lambda png: "\n".join(
        f"Total expenses {chr(65 + i)}  {1000 + i:,}.50  {900 + i:,}.25  {4000 + i:,}.75" for i in range(8)))
    assert beneath.page_text(0).splitlines()[0] == "Total expenses A  1,000.50 - 900.25 4,000.75"

    failed = Document(_figure_pdf(), figure_reader=broken)
    assert failed.page_text(0).startswith("Statement of profit") and failed.ocr_error is None
    assert "0" not in failed.to_cache()["ocr"], "not cached as read, so a later run tries again"
    capped = Document(_figure_pdf(), figure_reader=read, max_figure_pages=0)
    assert capped.page_text(0).startswith("Statement of profit") and not capped.figure_pages_used


def test_a_half_lost_bracket_is_put_back_and_close_rows_stay_apart():
    """The older OCR merged two close rows and interleaved their figures - "Employee Benefits Expense
    Finance Costs 31.7 1.2 48.1 3.6" - a wrong column on every figure. Rows two box-heights apart stay two
    lines, and a negative whose closing bracket the OCR lost stays negative."""
    result = [
        (box(40, 100, w=200), "(c) Employee Benefits Expense", 0.99),
        (box(400, 100), "31.7", 0.99), (box(480, 100), "48.1", 0.99),
        (box(40, 112, w=120), "(d) Finance Costs", 0.99),
        (box(400, 112), "1.2", 0.99), (box(480, 112), "3.6", 0.99),
        (box(40, 124, w=120), "Impairment loss", 0.99), (box(400, 124), "(2.0", 0.98),
    ]
    assert ocr.lines_from_boxes(result) == (
        "(c) Employee Benefits Expense  31.7  48.1\n"
        "(d) Finance Costs  1.2  3.6\n"
        "Impairment loss  (2.0)"
    )


def test_the_bench_cache_gives_the_fresh_reading_back_and_loads_no_engine_on_a_hit(tmp_path):
    import numpy as np

    calls = []

    class Fake:
        def __call__(self, image):
            calls.append(image.shape)
            return ([(np.array([[1.5, 2.0], [9.0, 2.0], [9.0, 4.0], [1.5, 4.0]], dtype=np.float32), "Revenue 1,245.60", np.float32(0.97))], 0.1)

    built = []

    def factory():
        built.append(1)
        return Fake()

    page = np.zeros((4, 5, 3), np.uint8)
    first = ocr.CachedEngine(factory, str(tmp_path))
    fresh = first(page)
    again = ocr.CachedEngine(factory, str(tmp_path))      # a new run: same folder
    cached = again(page)
    assert cached == fresh and ocr._boxes(cached) == ocr._boxes(fresh)
    assert ocr.positioned_lines(cached) == ocr.positioned_lines(fresh)
    assert (first.misses, again.hits, again.misses, len(built), len(calls)) == (1, 1, 0, 1, 1)
    other = page.copy(); other[0, 0, 0] = 1                # one pixel differs: another page
    again(other)
    assert again.misses == 1 and len(built) == 2


def test_the_engine_is_cached_only_when_the_bench_names_a_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("PDF_OCR_CACHE_DIR", str(tmp_path))
    assert isinstance(ocr._new_engine(), ocr.CachedEngine)
