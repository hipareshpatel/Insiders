"""Owner 26 Oct 2026: scanned call transcripts and decks are read whole; the pages past the usual cap use local OCR only."""
from bse_intel import pipeline as P


def test_pages_past_the_usual_cap_use_local_ocr_only():
    calls = []
    full = lambda png: calls.append("full") or "full"      # noqa: E731
    local = lambda png: calls.append("local") or "local"   # noqa: E731
    read = P._call_ocr(full, local, first=2)
    assert [read(b"") for _ in range(4)] == ["full", "full", "local", "local"]
    assert calls == ["full", "full", "local", "local"]


def test_no_reader_stays_none():
    assert P._call_ocr(None, lambda b: "x", 2) is None
    full = lambda b: "f"   # noqa: E731
    assert P._call_ocr(full, None, 2) is full


def test_the_call_cap_is_above_the_usual_one():
    assert P.CALL_OCR_PAGES >= 60
