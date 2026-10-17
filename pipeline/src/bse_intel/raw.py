"""The exact bytes BSE and NSE sent, saved before they are parsed, so a parsing or cleaning fix can be
re-run over what was received instead of asking the exchange again (docs/DATA_QUALITY.md).

Every JSON answer the clients receive (announcement pages, the results archive, the quote header, the
scrip list, NSE's lists) is written to the object store under

    raw/{source}/{endpoint}/{YYYY-MM-DD}/{HHMMSS}-{request}-{content}.bin.gz

the date and time of the fetch in IST, ``request`` a hash of the query and ``content`` a hash of the
body, so the same answer fetched twice in one run is written once. Each file is gzip of one JSON line
of metadata (url, params, status, fetched_at), a newline, then the body exactly as received. PDFs and
XBRL files are not here: the text cache and the XBRL cache keep those.

Saving never fails a run: a write that fails is logged and the fetch carries on.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import threading
from collections.abc import Iterator
from urllib.parse import urlparse

from .timeutil import now_ist

log = logging.getLogger(__name__)

PREFIX = "raw/"


def _hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:10]


def encode(url: str, params: dict | None, status: int, body: bytes, fetched_at: str) -> bytes:
    meta = {"url": url, "params": params or {}, "status": status, "fetched_at": fetched_at}
    return gzip.compress(json.dumps(meta, ensure_ascii=False, sort_keys=True).encode() + b"\n" + body)


def decode(blob: bytes) -> tuple[dict, bytes]:
    """(metadata, the body exactly as received) from a saved file."""
    data = gzip.decompress(blob)
    head, _, body = data.partition(b"\n")
    return json.loads(head), body


class RawStore:
    """Writes each answer once to a sink's object store (R2 in the cloud, a folder on the laptop)."""

    def __init__(self, sink, source: str):
        self._sink = sink
        self._source = source
        self._seen: set[str] = set()
        self._lock = threading.Lock()
        self.saved = 0

    def key(self, url: str, params: dict | None, body: bytes, when) -> str:
        endpoint = urlparse(url).path.rstrip("/").rsplit("/", 2)
        name = "-".join(p for p in endpoint[-2:] if p and p not in ("w", "api")) or "root"
        request = _hash(json.dumps(params or {}, sort_keys=True).encode() + url.encode())
        return (f"{PREFIX}{self._source}/{name}/{when:%Y-%m-%d}/"
                f"{when:%H%M%S}-{request}-{_hash(body)}.bin.gz")

    def save(self, url: str, params: dict | None, status: int, body: bytes) -> None:
        when = now_ist()
        digest = _hash(url.encode() + json.dumps(params or {}, sort_keys=True).encode() + body)
        with self._lock:
            if digest in self._seen:
                return
            self._seen.add(digest)
        try:
            self._sink.put_object(self.key(url, params, body, when),
                                  encode(url, params, status, body, when.isoformat(timespec="seconds")),
                                  content_type="application/gzip")
            with self._lock:
                self.saved += 1
        except Exception as exc:  # the raw copy is a safety net; it never stops a fetch
            log.warning("raw copy not saved for %s: %s", url, exc)


def attach(client, sink, source: str, settings) -> None:
    """Save the client's JSON answers to the sink, unless SAVE_RAW is off or the client takes no store."""
    if settings.save_raw and hasattr(client, "raw"):
        client.raw = RawStore(sink, source)


def saved(sink, source: str, endpoint: str, day: str) -> Iterator[tuple[str, dict, bytes]]:
    """(key, metadata, body) for every answer saved from one endpoint on one IST day, oldest first."""
    for key in sorted(sink.list_objects(f"{PREFIX}{source}/{endpoint}/{day}/")):
        blob = sink.get_object(key)
        if blob:
            meta, body = decode(blob)
            yield key, meta, body
