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
