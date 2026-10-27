"""F216: a long release-check run saves as it goes and ends cleanly (time budget, cancel, dead platform)."""

from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

import httpx

from bse_intel.sinks.base import SinkUnavailable
from bse_intel.sinks.platform import PlatformSink
from test_card_v2 import RELEASE

BODY = gzip.compress(json.dumps({"v": 1, "digital": [RELEASE], "has_image": [False]}).encode())


def _script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "release_check.py"
    spec = importlib.util.spec_from_file_location("release_check_f216", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(i: int) -> dict:
    card = {"event_type": "OTHER", "impact_level": "MODERATE", "headline": f"Acme order number {i} announced today",
            "takeaway": "Margins held.", "what_happened": [{"text": "Revenue 388.15", "quote": "Revenue from operations 388.15"}]}
    return {"news_id": f"n{i}", "scrip_code": "1", "symbol": "A", "company_name": "A", "filed_at": "2026-10-20T10:00:00",
            "pdf_url": "u", "held": 0, "card_json": json.dumps(card)}


class _Source:
    def __init__(self, n, on_row=None, text_error=False):
        self.n, self.on_row, self.text_error = n, on_row, text_error

    def rows(self):
        for i in range(self.n):
            if self.on_row:
                self.on_row(i)
            yield _row(i)

    def text_body(self, news_id):
        if self.text_error:
            raise SinkUnavailable("dead")
        return BODY

    def dossier(self, scrip):
        return {}


def _lines(out: Path) -> list[dict]:
    return [json.loads(x) for x in (out / "records.jsonl").read_text(encoding="utf-8").splitlines()]


def test_each_record_is_on_disk_before_the_run_ends(tmp_path):
    rc = _script()
    seen = []

    def at_row(i):
        if i:
            seen.append(len(_lines(tmp_path)))

    result = rc.run(_Source(5, on_row=at_row), ("quote_exact",), tmp_path)
    assert result["cards"] == 5 and result["stopped"] is None
    assert seen == [1, 2, 3, 4]   # when card i is fetched, cards 0..i-1 are already written
    assert [x["check"] for x in _lines(tmp_path)] == ["quote_exact"] * 5


def test_the_time_budget_stops_cleanly_with_what_is_done(tmp_path, monkeypatch):
    rc = _script()
    clock = iter(range(100))
    monkeypatch.setattr(rc.time, "monotonic", lambda: next(clock))
    result = rc.run(_Source(50), ("quote_exact",), tmp_path, deadline=3.5)
    assert result["stopped"] == "time budget reached"
    assert 0 < result["cards"] < 50 and len(_lines(tmp_path)) == result["cards"]


def test_a_dead_platform_ends_the_run_after_a_few_cards(tmp_path):
    rc = _script()
    result = rc.run(_Source(500, text_error=True), ("quote_exact",), tmp_path)
    assert result["cards"] == rc.DEAD_RUN and "did not answer" in result["stopped"]


def test_a_cancel_signal_ends_the_run_and_main_still_writes_the_summary(tmp_path, monkeypatch):
    rc = _script()
    rc._STOP.clear()
    result = rc.run(_Source(5, on_row=lambda i: rc._on_signal(15, None) if i == 2 else None), ("quote_exact",), tmp_path)
    assert result["cards"] == 3 and result["stopped"] == "stopped by SIGTERM"
    rc._STOP.clear()
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps([_row(i) for i in range(4)]))
    monkeypatch.setattr("sys.argv", ["release_check.py", str(tmp_path / "out"), "--cards", str(cards), "--texts", str(tmp_path / "t"),
                                     "--only", "quote_exact", "--time-budget", "0.000001"])
    assert rc.main() == 0
    assert "PARTIAL" in (tmp_path / "out" / "release-check.txt").read_text(encoding="utf-8")


def test_a_platform_request_gives_up_after_the_set_attempts(monkeypatch):
    calls = []

    def dead(request):
        calls.append(1)
        raise httpx.ReadError("Server disconnected without sending a response")

    monkeypatch.setattr("time.sleep", lambda s: None)
    sink = PlatformSink("http://x", "t", timeout=5, transport=httpx.MockTransport(dead), attempts=2)
    try:
        sink.get_object("k")
        raise AssertionError("expected SinkUnavailable")
    except SinkUnavailable:
        pass
    assert len(calls) == 2
    calls.clear()
    try:
        PlatformSink("http://x", "t", transport=httpx.MockTransport(dead)).get_object("k")
    except SinkUnavailable:
        pass
    assert len(calls) == 4   # the default is unchanged


def test_the_precision_audit_stops_on_its_budget_and_says_so(tmp_path):
    import argparse
    path = Path(__file__).resolve().parents[1] / "scripts" / "audit_precision.py"
    spec = importlib.util.spec_from_file_location("audit_precision_f216", path)
    ap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ap)
    rows = (({"news_id": f"n{i}", "card_json": "{}"}, lambda nid: None) for i in range(1000))
    result = ap.audit(rows, argparse.Namespace(time_budget=0.000001, out_dir=str(tmp_path)))
    assert result["summary"]["stopped"] == "time budget reached" and result["summary"]["cards_checked"] == 0
    one = iter([({"news_id": "n1", "card_json": "{}"}, lambda nid: None)])
    full = ap.audit(one, argparse.Namespace(time_budget=0, out_dir=None))
    assert full["summary"]["stopped"] is None and full["summary"]["skipped"] == {"no text": 1}
