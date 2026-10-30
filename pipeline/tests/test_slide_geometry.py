"""TODO 144: a slide's figure tied to its label by the word boxes (slide_geometry.py), on small synthetic pages."""
from __future__ import annotations

from bse_intel import slide_geometry as sg
from bse_intel.models import CallPoint

H = 10.0


def box(text, x, y, w=None):
    """A word box with its left edge at x and its top at y, as wide as its letters."""
    return sg.Word(x, y, x + (w if w is not None else 5.5 * len(text)), y + H, text)


def row(y, x, *texts, gap=8.0):
    out = []
    for t in texts:
        b = box(t, x, y)
        out.append(b)
        x = b.x1 + gap
    return out


def verdict(value, quote, words):
    return sg.figure_label_verdict(value, quote, words).state


def test_row_a_figure_is_tied_to_the_label_on_its_row_not_the_row_above():
    # Welspun-like volume table: the 15 is in the stainless-steel row, the TMT row says 90
    words = (row(100, 20, "Volume", "(KMT)") + row(100, 200, "H1FY26") + row(100, 280, "Q2FY26")
             + row(120, 20, "TMT") + row(120, 200, "90") + row(120, 280, "47")
             + row(140, 20, "Stainless", "Steel") + row(140, 200, "15") + row(140, 280, "8"))
    assert verdict(90, "TMT H1FY26 90", words) == "tied"
    v = sg.figure_label_verdict(15, "TMT H1FY26 15", words)
    assert v.state == "other" and "Stainless" in v.detail


def test_a_row_label_two_lines_tall_counts_as_one_label():
    words = row(120, 20, "DI") + row(132, 20, "pipes") + row(126, 200, "197") + row(160, 20, "Line", "pipes") + row(160, 200, "79")
    assert verdict(197, "DI pipes Q2FY26 197", words) == "tied"
    assert verdict(79, "DI pipes Q2FY26 79", words) == "other"


def test_column_a_kpi_box_takes_its_label_from_above_or_below_in_its_own_column():
    words = (row(50, 20, "Active", "Franchisee") + row(70, 40, "12,911")
             + row(50, 220, "Test", "menu") + row(70, 240, "3,400"))
    assert verdict(12911, "Active Franchisee 12,911", words) == "tied"
    assert verdict(12911, "Test menu 12,911", words) == "other"
    # the caption under the figure
    below = (row(70, 40, "34.3%") + row(86, 30, "Risk", "weighted", "assets") + row(70, 240, "24.1%")
             + row(86, 235, "CRAR"))
    assert verdict(24.1, "CRAR 24.1%", below) == "tied"
    assert verdict(34.3, "CRAR 34.3%", below) == "other"


def test_a_line_of_labels_over_a_line_of_figures_pairs_by_order_when_they_do_not_line_up():
    words = row(50, 20, "Domestic", "Exports", "Services", gap=30) + row(70, 150, "62%", "30%", "8%", gap=60)
    assert verdict(62, "Domestic 62%", words) == "tied"
    assert verdict(30, "Domestic 30%", words) == "other"
    assert verdict(8, "Services 8%", words) == "tied"


def test_pie_with_a_legend_by_colour_cannot_be_proven():
    # the shares sit round the pie, the legend is swatches: nothing in the words ties 41% to "Defence"
    words = (row(40, 100, "Order", "book", "mix") + row(80, 60, "41%") + row(150, 200, "35%") + row(100, 300, "24%")
             + row(60, 400, "Defence") + row(80, 400, "Nuclear") + row(100, 400, "Space"))
    v = sg.figure_label_verdict(41, "Defence 41%", words)
    assert v.state == "unproven"


def test_pie_label_beside_its_share_is_tied():
    words = row(80, 60, "Defence", "41%") + row(150, 200, "Nuclear", "35%")
    assert verdict(41, "Defence 41%", words) == "tied"
    assert verdict(35, "Defence 35%", words) == "other"


def test_a_period_header_is_not_a_label_and_a_missing_figure_or_page_cannot_tell():
    words = row(100, 200, "Q2FY26") + row(120, 20, "Revenue") + row(120, 200, "500")
    assert verdict(500, "Revenue Q2FY26 500", words) == "tied"
    assert verdict(77, "Revenue 77", words) == "unknown"        # the figure is not on the page
    assert verdict(500, "Revenue 500", []) == "unknown"         # no boxes
    assert verdict(500, "Q2FY26 500", words) == "unknown"       # the quote names no label


def test_geometry_issue_only_judges_slide_points_and_returns_a_reason():
    words = row(100, 20, "Stainless", "Steel") + row(100, 200, "15") + row(120, 20, "TMT") + row(120, 200, "90")
    wrong = CallPoint(type="kpi", statement="TMT volume was 15", quote="TMT 15", value=15.0, section="SLIDE", page=7)
    assert sg.geometry_issue(wrong, words).startswith("other:")
    right = CallPoint(type="kpi", statement="TMT volume was 90", quote="TMT 90", value=90.0, section="SLIDE", page=7)
    assert sg.geometry_issue(right, words) is None
    talk = wrong.model_copy(update={"section": "PREPARED"})
    assert sg.geometry_issue(talk, words) is None


def test_ocr_boxes_of_a_line_are_cut_into_words():
    ocr = [([[0, 0], [100, 0], [100, 10], [0, 10]], "Order book 788", 0.9)]
    got = sg.words_from_ocr(ocr)
    assert [w.text for w in got] == ["Order", "book", "788"]
    assert got[0].x1 <= got[1].x0 and got[2].x1 == 100


def test_check_points_drops_a_mispaired_slide_figure_only_with_the_switch_on_and_boxes_given(monkeypatch):
    from bse_intel import call_memory as cm

    monkeypatch.setenv("BSE_INTEL_SWITCHES", "off")
    words = row(100, 20, "Stainless", "Steel") + row(100, 200, "15") + row(120, 20, "TMT") + row(120, 200, "90")
    wrong = CallPoint(type="kpi", statement="TMT volume was 15 KMT", quote="TMT 15", value=15.0, unit="KMT", section="SLIDE",
                      page=7)
    text = "===== PAGE 7 of 9 [text] =====\nStainless Steel   TMT\n15   90 TMT 15\n"
    monkeypatch.delenv("CALL_MEMORY_GEOMETRY", raising=False)
    kept, dropped = cm.check_points([wrong], text, layouts={7: words})
    assert [d["reason"] for d in dropped] != ["label"]        # switch off: geometry is not asked
    monkeypatch.setenv("CALL_MEMORY_GEOMETRY", "1")
    kept, dropped = cm.check_points([wrong], text, layouts={7: words})
    assert any(d["reason"] == "label" and d["detail"].startswith("other:") for d in dropped) and not kept
    kept, dropped = cm.check_points([wrong], text)             # no boxes: nothing to judge by
    assert not any(d["reason"] == "label" for d in dropped)


def test_page_words_reads_a_text_layer_pages_boxes():
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 100), "TMT", fontsize=10)
    page.insert_text((200, 100), "90", fontsize=10)
    page.insert_text((50, 130), "Stainless Steel", fontsize=10)
    page.insert_text((200, 130), "15", fontsize=10)
    words = sg.page_words(doc.tobytes(), 1)
    assert sg.figure_label_verdict(90, "TMT 90", words).state == "tied"
    assert sg.figure_label_verdict(15, "TMT 15", words).state == "other"
