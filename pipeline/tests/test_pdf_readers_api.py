import json

import httpx
import pymupdf
import pytest
import respx

from bse_intel import pdf_readers
from bse_intel.pdf_readers import MistralOcrReader, markdown_tables, mistral_grids


def _pdf(pages: int) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page()
    return doc.tobytes()


ANSWER = {
    "pages": [
        {"index": 0, "markdown": "Statement\n\n[tbl-0.html](tbl-0.html)",
         "tables": [{"id": "tbl-0.html", "content": "<table><tr><td>Revenue from operations</td><td>1,234.50</td></tr>"
                                                     "<tr><td>Profit for the period</td><td>(12.30)</td></tr></table>"}]},
        {"index": 1, "markdown": "| Particulars | Q1 |\n|---|---|\n| Total income | 99.10 |\n\ntext after"},
    ],
    "usage_info": {"pages_processed": 2, "doc_size_bytes": 1000},
}


def test_grids_from_listed_html_tables_and_markdown_pipes():
    grids = mistral_grids(ANSWER)
    assert grids == [(1, [["Revenue from operations", "1,234.50"], ["Profit for the period", "(12.30)"]]),
                     (2, [["Particulars", "Q1"], ["Total income", "99.10"]])]


def test_markdown_tables_drops_the_rule_line_and_splits_tables():
    text = "| a | b |\n|:--|--:|\n| 1 | 2 |\nprose\n| c |\n|---|\n| 3 |"
    assert markdown_tables(text) == [[["a", "b"], ["1", "2"]], [["c"], ["3"]]]


def test_not_available_without_a_key(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    assert not MistralOcrReader().available()
    assert "mistral" in pdf_readers.READERS and pdf_readers.configured_readers("native") == ["native"]


@respx.mock
def test_extract_posts_the_pdf_counts_pages_and_keeps_the_answer(monkeypatch, tmp_path):
    monkeypatch.setenv("MISTRAL_API_KEY", " k ")
    monkeypatch.setenv("MISTRAL_OCR_RAW_DIR", str(tmp_path))
    monkeypatch.setattr(MistralOcrReader, "pages_used", 0)
    route = respx.post("https://api.mistral.ai/v1/ocr").mock(return_value=httpx.Response(200, json=ANSWER))
    grids = MistralOcrReader().extract(_pdf(2))
    sent = json.loads(route.calls[0].request.content)
    assert route.calls[0].request.headers["Authorization"] == "Bearer k"
    assert sent["model"] == "mistral-ocr-latest" and sent["table_format"] == "html"
    assert sent["document"]["document_url"].startswith("data:application/pdf;base64,")
    assert len(grids) == 2 and MistralOcrReader.pages_used == 2
    assert len(list(tmp_path.iterdir())) == 1


@respx.mock
def test_page_cap_stops_before_the_call(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    monkeypatch.setenv("MISTRAL_OCR_PAGE_CAP", "3")
    monkeypatch.setattr(MistralOcrReader, "pages_used", 2)
    route = respx.post("https://api.mistral.ai/v1/ocr").mock(return_value=httpx.Response(200, json=ANSWER))
    with pytest.raises(RuntimeError, match="page cap 3"):
        MistralOcrReader().extract(_pdf(2))
    assert not route.called


# --- nemotron-parse (NVIDIA) ---------------------------------------------------------------------------------------

from bse_intel.pdf_readers import NemotronParseReader, latex_tables, nemotron_grids  # noqa: E402

LATEX = r"\begin{tabular}{lrr}\hline Particulars & Q1 & Q2 \\ \hline Revenue & 1,234.5 & (12.3) \\ \multicolumn{2}{c}{Total} & 9 \\ \end{tabular}"
NEMO = {"choices": [{"message": {"tool_calls": [{"function": {"arguments": json.dumps([[
    {"bbox": {"xmin": 0.1, "ymin": 0.1, "xmax": 0.9, "ymax": 0.2}, "text": "Statement of results", "type": "Section-header"},
    {"bbox": {"xmin": 0.1, "ymin": 0.3, "xmax": 0.9, "ymax": 0.8}, "text": LATEX, "type": "Table"}]])}}]}}]}


def test_latex_tables_rows_cells_rules_and_multicolumn():
    assert latex_tables(LATEX) == [[["Particulars", "Q1", "Q2"], ["Revenue", "1,234.5", "(12.3)"], ["Total", "", "9"]]]


def test_nemotron_grids_takes_only_table_elements_from_a_nested_list():
    assert nemotron_grids(NEMO) == [[["Statement of results"], ["Particulars", "Q1", "Q2"], ["Revenue", "1,234.5", "(12.3)"],
                                     ["Total", "", "9"]]]


@respx.mock
def test_nemotron_extract_sends_one_fitted_png_a_page(monkeypatch, tmp_path):
    monkeypatch.setenv("NVIDIA_API_KEY", "k")
    monkeypatch.setenv("NEMOTRON_PARSE_RAW_DIR", str(tmp_path))
    monkeypatch.setattr(NemotronParseReader, "pages_used", 0)
    route = respx.post("https://integrate.api.nvidia.com/v1/chat/completions").mock(return_value=httpx.Response(200, json=NEMO))
    grids = NemotronParseReader().extract(_pdf(2))
    body = json.loads(route.calls[0].request.content)
    assert route.call_count == 2 and NemotronParseReader.pages_used == 2
    assert body["model"] == "nvidia/nemotron-parse" and body["tools"][0]["function"]["name"] == "markdown_bbox"
    assert body["messages"][0]["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert [g[0] for g in grids] == [1, 2] and len(list(tmp_path.iterdir())) >= 1


def test_nemotron_page_cap(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "k")
    monkeypatch.setenv("NEMOTRON_PARSE_PAGE_CAP", "1")
    monkeypatch.setattr(NemotronParseReader, "pages_used", 1)
    with pytest.raises(RuntimeError, match="page cap 1"):
        NemotronParseReader().extract(_pdf(1))


@respx.mock
def test_nemotron2_has_its_own_model_cap_and_count(monkeypatch):
    from bse_intel.pdf_readers import NemotronParse2Reader
    monkeypatch.setenv("NVIDIA_API_KEY", "k")
    monkeypatch.setattr(NemotronParseReader, "pages_used", 5)
    monkeypatch.setattr(NemotronParse2Reader, "pages_used", 0)
    monkeypatch.setenv("NEMOTRON_PARSE_PAGE_CAP", "5")   # the first model's cap is spent: the second still reads
    route = respx.post("https://integrate.api.nvidia.com/v1/chat/completions").mock(return_value=httpx.Response(200, json=NEMO))
    NemotronParse2Reader().extract(_pdf(1))
    assert json.loads(route.calls[0].request.content)["model"] == "nvidia/nemotron-parse-2.0"
    assert NemotronParse2Reader.pages_used == 1 and NemotronParseReader.pages_used == 5
    assert "nemotron2" in pdf_readers.READERS


@respx.mock
def test_a_refusal_is_kept_with_its_status_and_body(monkeypatch, tmp_path):
    from bse_intel.pdf_readers import NemotronParse35Reader
    monkeypatch.setenv("NVIDIA_API_KEY", "k")
    monkeypatch.setenv("NEMOTRON_PARSE35_RAW_DIR", str(tmp_path))
    monkeypatch.setattr(NemotronParse35Reader, "pages_used", 0)
    route = respx.post("https://integrate.api.nvidia.com/v1/chat/completions").mock(
        return_value=httpx.Response(404, text='{"detail":"Function not found"}'))
    with pytest.raises(RuntimeError, match="nvidia/nemotron-3.5-parse HTTP 404"):
        NemotronParse35Reader().extract(_pdf(1))
    assert json.loads(route.calls[0].request.content)["model"] == "nvidia/nemotron-3.5-parse"
    kept = json.loads((tmp_path / "refused-0.json").read_text())
    assert kept == {"status": 404, "body": '{"detail":"Function not found"}'}


@respx.mock
def test_mistral_refusal_is_kept(monkeypatch, tmp_path):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    monkeypatch.setenv("MISTRAL_OCR_RAW_DIR", str(tmp_path))
    monkeypatch.setattr(MistralOcrReader, "pages_used", 0)
    respx.post("https://api.mistral.ai/v1/ocr").mock(return_value=httpx.Response(403, text="not available in your tier"))
    with pytest.raises(RuntimeError, match="HTTP 403"):
        MistralOcrReader().extract(_pdf(1))
    assert json.loads((tmp_path / "refused-0.json").read_text())["status"] == 403


def _answer(elements):
    return {"choices": [{"message": {"tool_calls": [{"function": {"arguments": json.dumps([elements])}}]}}]}


TABLE = r"\begin{tabular}{lrr} Particulars & Quarter ended 30 June 2023 & Quarter ended 30 June 2022 \\ Profit for the period & 18.370.88 & 14,417.73 \\ \end{tabular}"


def test_nemotron_puts_the_title_and_unit_above_each_table_and_empties_a_two_point_figure(monkeypatch):
    monkeypatch.delenv("NEMOTRON_HEADER", raising=False)
    elements = [{"type": "Section-header", "text": "**Statement of unaudited standalone results**"},
                {"type": "Text", "text": "(All amounts are in Indian Rupees in lakhs)"},
                {"type": "Table", "text": TABLE},
                {"type": "Page-footer", "text": "Place: Chennai"},
                {"type": "Table", "text": TABLE}]
    first, second = nemotron_grids(_answer(elements))
    assert first[:2] == [["Statement of unaudited standalone results"], ["(All amounts are in Indian Rupees in lakhs)"]]
    assert first[-1] == ["Profit for the period", "", "14,417.73"]        # 18.370.88 (read as 18.37) gives no answer
    assert second[0][0].startswith("Particulars")                           # the footer is no header; the title went with the first


def test_nemotron_header_off_and_unit_rule(monkeypatch):
    elements = [{"type": "Table", "text": TABLE}]
    monkeypatch.setenv("NEMOTRON_HEADER", "0")
    assert len(nemotron_grids(_answer(elements))) == 1                       # the unit rule is off by default
    monkeypatch.setenv("NEMOTRON_NEED_UNIT", "1")
    assert nemotron_grids(_answer(elements)) == []                          # on: a table with no unit word anywhere is dropped


@respx.mock
def test_nemotron2_names_its_tool_and_v1_does_not(monkeypatch):
    from bse_intel.pdf_readers import NemotronParse2Reader
    monkeypatch.setenv("NVIDIA_API_KEY", "k")
    monkeypatch.setattr(NemotronParse2Reader, "pages_used", 0)
    monkeypatch.setattr(NemotronParseReader, "pages_used", 0)
    route = respx.post("https://integrate.api.nvidia.com/v1/chat/completions").mock(return_value=httpx.Response(200, json=NEMO))
    NemotronParse2Reader().extract(_pdf(1))
    NemotronParseReader().extract(_pdf(1))
    first, second = (json.loads(c.request.content) for c in route.calls)
    assert first["tool_choice"] == {"type": "function", "function": {"name": "markdown_bbox"}}
    assert "tool_choice" not in second       # v1 answered without it (run 41063175585): left as it was measured


@respx.mock
def test_mistral_retries_a_429(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    monkeypatch.setattr(MistralOcrReader, "pages_used", 0)
    monkeypatch.setattr("time.sleep", lambda s: None)
    route = respx.post("https://api.mistral.ai/v1/ocr").mock(
        side_effect=[httpx.Response(429, text="Rate limit exceeded"), httpx.Response(200, json=ANSWER)])
    assert len(MistralOcrReader().extract(_pdf(2))) == 2 and route.call_count == 2


def test_garbled_figure_spares_dates_and_sees_through_marks():
    from bse_intel.pdf_readers import garbled_figure
    assert all(garbled_figure(x) for x in ["18.370.88", "18.37.88", "1.23.45", "18.370.88*", "1.8.370.88", "−18.370.88", "(18.370.88)", "18.370.88 (1)"])
    assert not any(garbled_figure(x) for x in ["30.06.2023", "1.6.24", "18,370.88", "12.5", "2023.24", ""])


def test_nemotron_header_skips_notes_list_items_and_long_text(monkeypatch):
    monkeypatch.delenv("NEMOTRON_HEADER", raising=False)
    box = lambda y: {"xmin": 0.1, "ymin": y, "xmax": 0.9, "ymax": y + 0.05}
    elements = [{"type": "Section-header", "text": "Statement of standalone results", "bbox": box(0.1)},
                {"type": "List-item", "text": "1 The consolidated figures of the Group", "bbox": box(0.3)},
                {"type": "Text", "text": "Notes: " + "the Group consolidated its figures " * 6, "bbox": box(0.35)},
                {"type": "Table", "text": TABLE, "bbox": box(0.5)}]
    (grid,) = nemotron_grids(_answer(elements))
    assert grid[0] == ["Statement of standalone results"] and grid[1][0] == "Particulars"


def test_nemotron_a_short_line_after_a_table_is_its_footnote(monkeypatch):
    monkeypatch.delenv("NEMOTRON_HEADER", raising=False)
    elements = [{"type": "Section-header", "text": "Statement of standalone results"},
                {"type": "Table", "text": TABLE},
                {"type": "Text", "text": "Figures are consolidated; Rs in lakhs"},
                {"type": "Table", "text": TABLE},
                {"type": "Section-header", "text": "Segment results"},
                {"type": "Text", "text": "(Rs in crore)"},
                {"type": "Table", "text": TABLE}]
    first, second, third = nemotron_grids(_answer(elements))
    assert second[0][0].startswith("Particulars")                        # table A's footnote is not table B's header
    assert third[:2] == [["Segment results"], ["(Rs in crore)"]]           # a new title opens the next block again
