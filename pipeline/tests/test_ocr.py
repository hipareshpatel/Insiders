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
