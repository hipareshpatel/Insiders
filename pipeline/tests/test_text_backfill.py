"""The one-time text backfill (F165): only cards without text, the pipeline's cache bytes, resume, shards, failure reasons."""

import gzip
import io
import json
import zipfile

import pymupdf
import pytest

from bse_intel import pipeline as P
from bse_intel import text_backfill as tb
from bse_intel.bse import AttachmentError, AttachmentTooLarge, SourceBlockedError
from bse_intel.extract import Document

NSE = "https://nsearchives.nseindia.com/corporate/"


def pdf(text="Revenue from operations 1,234.50 crore for the quarter", end=True) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def box(members: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, body in members.items():
            z.writestr(name, body)
    return out.getvalue()


class Sink:
    def __init__(self, cards=(), objects=None, failed=()):
        self.cards, self.objects, self.kv, self.puts = list(cards), dict(objects or {}), {}, []
        self.failed = list(failed)

    def query(self, name, params):
        if name == "filings_failed":
            return self.failed
        assert name == "export_cards"
        rows = [c for c in self.cards if (c["filed_at"], c["news_id"]) > (params[0], params[1])]
        return rows[:params[2]]

    def list_objects(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))

    def put_object(self, key, body, content_type="application/json"):
        assert key.startswith("text/")
        self.objects[key] = body
        self.puts.append(key)

    def kv_get(self, key):
        return self.kv.get(key)

    def kv_set(self, key, value, now):
        self.kv[key] = value


class Client:
    """A fake NseClient: url -> bytes, None (404) or an exception to raise."""

    def __init__(self, files):
        self.files, self.calls = files, []

    def fetch(self, url, max_bytes=30_000_000):
        self.calls.append(url)
        got = self.files[url]
        if isinstance(got, Exception):
            raise got
        return got


def card(n, url=True, filed="2026-10-01T10:00:00+05:30"):
    return {"news_id": f"NSE{n}", "pdf_url": f"{NSE}f{n}.pdf" if url is True else url, "filed_at": filed, "card_json": "{}"}


def test_lists_only_cards_without_text_and_skips_known_no_text():
    sink = Sink([card(1), card(2), card(3), card(4)], objects={P.text_key("NSE1"): b"x"},
                failed=[{"news_id": "NSE3", "last_error": "audio only (a ZIP of a recording): no text"},
                        {"news_id": "NSE4", "last_error": "network error"}])
    rows, counts = tb.cards_lacking_text(sink)
    assert [r["news_id"] for r in rows] == ["NSE2", "NSE4"]
    assert counts == {"cards": 4, "with_text": 1, "known_no_text": 1, "lacking": 3}
    assert [r["news_id"] for r in tb.cards_lacking_text(sink, 1)[0]] == ["NSE2"]


def test_pages_through_more_than_one_page_of_cards():
    cards = [card(n, filed=f"2026-10-01T10:{n // 60:02d}:{n % 60:02d}+05:30") for n in range(230)]
    rows, counts = tb.cards_lacking_text(Sink(cards))
    assert len(rows) == 230 and counts["cards"] == 230


def test_written_object_has_the_pipelines_shape():
    data = pdf()
    sink = Sink()
    out = tb.run(sink, [card(1)], Client({f"{NSE}f1.pdf": data}), ocr=False)
    assert out["written"] == 1 and sink.puts == [P.text_key("NSE1")]
    reference = Document(data, max_ocr_pages=6)
    reference.select_text(10_000_000, [])
    assert sink.objects[P.text_key("NSE1")] == P.text_cache_body(reference)
    entry = json.loads(gzip.decompress(sink.objects[P.text_key("NSE1")]))
    assert {"v", "error", "digital", "has_image", "ocr", "blocks", "sha256"} <= set(entry)
    assert "1,234.50" in Document.from_cache(entry).select_text(10_000, [])


def test_nothing_else_is_written_and_a_zip_is_read():
    sink = Sink()
    zipped = box({"b.xml": b"<x/>", "a.pdf": pdf("Order worth Rs 55 crore")})
    out = tb.run(sink, [card(1)], Client({f"{NSE}f1.pdf": zipped}), ocr=False)
    assert out["written"] == 1 and set(sink.objects) == {P.text_key("NSE1")}


def test_failure_reasons_and_time_figures():
    files = {f"{NSE}f1.pdf": None, f"{NSE}f2.pdf": AttachmentTooLarge("u", 5),
             f"{NSE}f3.pdf": box({"call.mp3": b"abc"}), f"{NSE}f4.pdf": box({"n.xml": b"<x/>"}),
             f"{NSE}f5.pdf": pdf()[:300], f"{NSE}f6.pdf": pdf(), f"{NSE}f7.pdf": b"not a pdf at all"}
    rows = [card(1), card(2), card(3), card(4), card(5), card(6), card(7), card(8, url=""), card(9, url="https://www.bseindia.com/x.pdf")]
    sink = Sink()
    out = tb.run(sink, rows, Client(files), ocr=False)
    assert out["written"] == 1 and out["failed"] == 8
    assert out["reasons"][tb.R_404] == 1 and out["reasons"][tb.R_LARGE] == 1
    assert out["reasons"][tb.R_AUDIO] == 1 and out["reasons"][tb.R_ZIP] == 1
    assert out["reasons"][tb.R_CUT] == 1 and out["reasons"][tb.R_UNREADABLE] == 1
    assert out["reasons"][tb.R_NO_URL] == 1 and out["reasons"][tb.R_NOT_NSE] == 1
    assert out["fetched"] == 7 and out["seconds_per_filing"] is not None
    assert "ZIP audio only" in tb.render(out)


def test_resume_does_not_fetch_written_or_failed_again_and_restart_does():
    files = {f"{NSE}f1.pdf": pdf(), f"{NSE}f2.pdf": None, f"{NSE}f3.pdf": pdf("later")}
    sink = Sink([card(1), card(2), card(3)])
    first = Client(files)
    # a clock that moves with the rows finished (written or failed), not with downloads started: the next download
    # runs in a background thread, so counting client calls raced it (flaky on CI)
    clock = lambda: 15.0 * (len(sink.puts) + len(json.loads(sink.kv.get("textbackfill:failed:0of1", "{}"))))
    out = tb.run(sink, tb.cards_lacking_text(sink)[0], first, time_budget=25, clock=clock, ocr=False)
    assert out["more"] and out["fetched"] == 2 and P.text_key("NSE3") not in sink.objects and json.loads(sink.kv["textbackfill:failed:0of1"]) == {"NSE2": tb.R_404}
    again = Client(files)
    rows, _ = tb.cards_lacking_text(sink)
    assert [r["news_id"] for r in rows] == ["NSE2", "NSE3"]   # NSE1 has its text now
    out = tb.run(sink, rows, again, ocr=False)
    assert not out["more"] and again.calls == [f"{NSE}f3.pdf"] and out["skipped_failed_before"] == 1
    assert out["written"] == 1 and len(sink.puts) == 2
    redo = Client({**files, f"{NSE}f2.pdf": pdf("now served")})
    out = tb.run(sink, rows, redo, restart=True, ocr=False)
    assert redo.calls == [f"{NSE}f2.pdf", f"{NSE}f3.pdf"] and out["written"] == 2
    assert json.loads(sink.kv["textbackfill:failed:0of1"]) == {}


def test_shards_split_the_filings_and_keep_separate_failure_lists():
    files = {f"{NSE}f{n}.pdf": None for n in range(1, 5)}
    rows = [card(n) for n in range(1, 5)]
    sink, a, b = Sink(), Client(files), Client(files)
    tb.run(sink, rows, a, shard=(0, 2), ocr=False)
    tb.run(sink, rows, b, shard=(1, 2), ocr=False)
    assert a.calls == [f"{NSE}f1.pdf", f"{NSE}f3.pdf"] and b.calls == [f"{NSE}f2.pdf", f"{NSE}f4.pdf"]
    assert set(json.loads(sink.kv["textbackfill:failed:0of2"])) == {"NSE1", "NSE3"}


def test_network_failures_are_retried_later_and_three_in_a_row_stop():
    files = {f"{NSE}f{n}.pdf": AttachmentError("down") for n in range(1, 6)}
    sink = Sink()
    out = tb.run(sink, [card(n) for n in range(1, 6)], Client(files), ocr=False)
    assert out["stopped"] and out["fetched"] == 3 and "textbackfill:failed:0of1" not in sink.kv


def test_a_refusal_stops_the_run_and_keeps_earlier_failures():
    files = {f"{NSE}f1.pdf": None, f"{NSE}f2.pdf": SourceBlockedError("403")}
    sink = Sink()
    with pytest.raises(SourceBlockedError):
        tb.run(sink, [card(1), card(2), card(3)], Client(files), ocr=False)
    assert json.loads(sink.kv["textbackfill:failed:0of1"]) == {"NSE1": tb.R_404}


def test_estimate():
    assert tb.estimate(6872, 2, ocr=False)["seconds"] == round(6872 * 6.0 / 2)


BSE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"


class BseDownload:
    """A fake BseClient: url -> bytes, None (404 on both paths) or an exception to raise."""

    def __init__(self, files):
        self.files, self.calls = files, []

    def download(self, url, max_bytes=30_000_000):
        self.calls.append(url)
        got = self.files[url]
        if isinstance(got, Exception):
            raise got
        return got


def test_bse_source_fetches_only_bse_files_with_its_own_failure_list():
    rows = [card(1, url=f"{BSE}a.pdf"), card(2, url=f"{BSE}b.pdf"), card(3)]
    assert tb.bse_rows(rows) == rows[:2]
    client = BseDownload({f"{BSE}a.pdf": pdf(), f"{BSE}b.pdf": None})
    sink = Sink()
    out = tb.run(sink, rows, tb.BseFetcher(client), ocr=False, source="bse")
    assert out["written"] == 1 and client.calls == [f"{BSE}a.pdf", f"{BSE}b.pdf"]
    assert json.loads(sink.kv["textbackfill-bse:failed:0of1"]) == {"NSE2": tb.R_404_BSE, "NSE3": tb.R_NOT_BSE}
    assert "textbackfill:failed:0of1" not in sink.kv


def test_bse_refusal_stops_the_run():
    client = BseDownload({f"{BSE}a.pdf": AttachmentError("BSE refused", refused=True)})
    with pytest.raises(SourceBlockedError):
        tb.run(Sink(), [card(1, url=f"{BSE}a.pdf")], tb.BseFetcher(client), ocr=False, source="bse")


def test_bse_network_failure_is_retried_later():
    client = BseDownload({f"{BSE}a.pdf": AttachmentError("timeout")})
    sink = Sink()
    out = tb.run(sink, [card(1, url=f"{BSE}a.pdf")], tb.BseFetcher(client), ocr=False, source="bse")
    assert out["reasons"] == {tb.R_NETWORK: 1} and "textbackfill-bse:failed:0of1" not in sink.kv


def test_bse_one_refused_file_after_a_good_one_is_kept_and_the_run_goes_on():
    files = {f"{BSE}a.pdf": pdf(), f"{BSE}b.pdf": AttachmentError("BSE refused", refused=True), f"{BSE}c.pdf": pdf()}
    sink = Sink()
    out = tb.run(sink, [card(n, url=f"{BSE}{x}.pdf") for n, x in ((1, "a"), (2, "b"), (3, "c"))],
                 tb.BseFetcher(BseDownload(files)), ocr=False, source="bse")
    assert out["written"] == 2 and json.loads(sink.kv["textbackfill-bse:failed:0of1"]) == {"NSE2": tb.R_REFUSED}


def test_bse_three_refusals_in_a_row_stop_the_run():
    files = {f"{BSE}a.pdf": pdf(), **{f"{BSE}{x}.pdf": AttachmentError("BSE refused", refused=True) for x in "bcd"}}
    rows = [card(n, url=f"{BSE}{x}.pdf") for n, x in enumerate("abcd", 1)]
    with pytest.raises(SourceBlockedError):
        tb.run(Sink(), rows, tb.BseFetcher(BseDownload(files)), ocr=False, source="bse")
