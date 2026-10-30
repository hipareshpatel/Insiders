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
