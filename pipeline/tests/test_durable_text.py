"""F147: a filing's text is kept in R2 for 6 months as well as in the local (GitHub) cache."""

from __future__ import annotations

import gzip
import json

from bse_intel.extract import Document
from bse_intel.pipeline import Pipeline, text_key
from bse_intel.sinks.local import LocalSink
from bse_intel.sinks.platform import PlatformSink


class FakeSink(PlatformSink):
    def __init__(self, fail_put=False, fail_get=False):
        self.objects: dict[str, bytes] = {}
        self.puts = 0
        self.gets = 0
        self.fail_put, self.fail_get = fail_put, fail_get

    def put_object(self, key, body, content_type="application/json"):
        self.puts += 1
        if self.fail_put:
            raise RuntimeError("R2 down")
        self.objects[key] = body

    def get_object(self, key):
        self.gets += 1
        if self.fail_get:
            raise RuntimeError("R2 down")
        return self.objects.get(key)


def _pipe(settings, sink):
    p = Pipeline.__new__(Pipeline)
    p.settings, p.sink = settings, sink
    return p


def _doc() -> Document:
    d = Document(None)
    d._digital = ["page one text"]
    return d


def test_write_goes_to_r2_and_local_and_is_not_sent_again(settings):
    sink = FakeSink()
    p = _pipe(settings, sink)
    p._cache_text("n1", _doc())
    assert sink.puts == 1 and text_key("n1") == "text/n1.json.gz"
    assert json.loads(gzip.decompress(sink.objects["text/n1.json.gz"]))["digital"] == ["page one text"]
    assert p._cached_text("n1")["digital"] == ["page one text"]
    p._cache_text("n1", _doc())
    assert sink.puts == 1


def test_read_falls_back_to_r2_and_restores_the_local_copy(settings):
    sink = FakeSink()
    _pipe(settings, sink)._cache_text("n2", _doc())
    for f in settings.text_cache_dir.rglob("*.json.gz"):
        f.unlink()
    p = _pipe(settings, sink)
    assert p._cached_text("n2")["digital"] == ["page one text"]
    assert list(settings.text_cache_dir.rglob("n2.json.gz"))
    gets = sink.gets
    assert p._cached_text("n2") is not None and sink.gets == gets   # local first now
    assert p._cached_text("missing") is None


def test_r2_failures_never_fail_the_filing(settings):
    sink = FakeSink(fail_put=True, fail_get=True)
    p = _pipe(settings, sink)
    p._cache_text("n3", _doc())                    # put fails: warning only, local copy kept
    assert p._cached_text("n3") is not None
    assert p._cached_text("absent") is None        # get fails: treated as a miss


def test_local_sink_never_touches_r2(settings):
    p = _pipe(settings, LocalSink(settings))
    p._cache_text("n4", _doc())
    assert p._cached_text("n4") is not None and p._cached_text("zz") is None
