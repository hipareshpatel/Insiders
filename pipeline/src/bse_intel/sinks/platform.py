"""Sink backed by the deployed Worker's internal API (D1 + R2 bindings).

The pipeline never holds Cloudflare credentials: it authenticates to the
Worker with one bearer token (INGEST_TOKEN), and the Worker runs only
whitelisted SQL files and touches only whitelisted R2 prefixes.
"""

from __future__ import annotations

import json
import logging
import time
from urllib.parse import quote

import httpx

from .base import NOT_IDEMPOTENT, QUERIES, STATEMENTS, Sink, SinkRejected, SinkUnavailable, chunk_rows

log = logging.getLogger(__name__)


def _encode(row) -> str:
    return json.dumps(row, ensure_ascii=False, separators=(",", ":"))


class PlatformSink(Sink):
    def __init__(self, base_url: str, token: str, timeout: float = 60.0, transport: httpx.BaseTransport | None = None):
        if not base_url or not token:
            raise ValueError("PLATFORM_API_URL and INGEST_TOKEN are required for the platform sink")
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/api/internal",
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, url: str, idempotent: bool = True, **kwargs) -> httpx.Response:
        for attempt in range(4):
            try:
                resp = self._http.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                # A connect failure never reached the Worker; anything later may have been applied.
                if attempt == 3 or not (idempotent or isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))):
                    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError,
                                        httpx.ReadError)):
                        raise SinkUnavailable(f"the platform API at {self._http.base_url} did not answer "
                                              f"({type(exc).__name__}: {exc})") from exc
                    raise
                log.warning("platform API %s %s failed (%s); retrying", method, url, exc)
                time.sleep(2 ** (attempt + 1))
                continue
            # 429 and 503 mean the request was not processed; other 5xx may have been applied.
            if resp.status_code in (429, 503) or (resp.status_code >= 500 and idempotent):
                if attempt == 3:
                    resp.raise_for_status()
                time.sleep(2 ** (attempt + 1))
                continue
            return resp
        raise RuntimeError("unreachable")

    def execute(self, statement, rows):
        if statement not in STATEMENTS:
            raise ValueError(f"statement not allowed: {statement}")
        written = 0
        for batch in chunk_rows(rows, _encode):
            resp = self._request("POST", f"/exec/{statement}", idempotent=statement not in NOT_IDEMPOTENT,
                                 content=_encode(batch).encode(), headers={"Content-Type": "application/json"})
            if resp.status_code == 400:
                raise SinkRejected(f"{statement}: {resp.text[:300]}")
            resp.raise_for_status()
            written += int(resp.json().get("rows_written", 0))
        return written

    def query(self, name: str, params: list) -> list[dict]:
        if name not in QUERIES:
            raise ValueError(f"query not allowed: {name}")
        resp = self._request("POST", f"/query/{name}", json={"params": params})
        resp.raise_for_status()
        return resp.json().get("rows", [])

    def usage(self, day):
        return self.query("usage_for_day", [day])

    def usage_month(self, month):
        return self.query("usage_for_month", [month])

    def kv_get(self, key):
        rows = self.query("kv_get", [key])
        return rows[0]["value"] if rows else None

    def company(self, scrip_code):
        rows = self.query("company_get", [scrip_code])
        return rows[0] if rows else None

    def peer_cards(self, sector, event_category, scrip_code, since, until, limit=5):
        return self.query("peer_cards", [sector, event_category, scrip_code, since, until, limit])

    def get_object(self, key):
        resp = self._request("GET", f"/objects/{quote(key)}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content

    def put_object(self, key, body, content_type="application/json"):
        resp = self._request("PUT", f"/objects/{quote(key)}", content=body, headers={"Content-Type": content_type})
        resp.raise_for_status()

    def get_dossier(self, scrip_code):
        body = self.get_object(f"memory/{scrip_code}.json")
        return json.loads(body) if body else None

    def put_dossier(self, scrip_code, dossier):
        self.put_object(f"memory/{scrip_code}.json", _encode(dossier).encode())

    def list_objects(self, prefix):
        keys, cursor = [], None
        while True:
            params = {"prefix": prefix}
            if cursor:
                params["cursor"] = cursor
            resp = self._request("GET", "/objects", params=params)
            resp.raise_for_status()
            data = resp.json()
            keys += data.get("keys", [])
            cursor = data.get("cursor")
            if not cursor:
                return keys
