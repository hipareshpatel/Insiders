"""SQLite + filesystem sink for development and dry runs (same SQL as D1)."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from ..settings import Settings
from .base import QUERIES, STATEMENTS, Sink, chunk_rows


def _encode(row) -> str:
    return json.dumps(row, ensure_ascii=False, separators=(",", ":"))


class LocalSink(Sink):
    def __init__(self, settings: Settings, root: Path | None = None):
        self._settings = settings
        self.root = Path(root or settings.local_dir)
        self.objects = self.root / "r2"
        self.objects.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.root / "d1.sqlite3", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        for migration in sorted((settings.db_dir / "migrations").glob("*.sql")):
            self._db.executescript(migration.read_text())
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def execute(self, statement: str, rows: list[dict]) -> int:
        if statement not in STATEMENTS:
            raise ValueError(f"statement not allowed: {statement}")
        if not rows:
            return 0
        sql = self._settings.sql("statements", statement)
        written = 0
        with self._lock:
            for batch in chunk_rows(rows, _encode):
                before = self._db.total_changes
                self._db.execute(sql, [_encode(batch)])
                written += self._db.total_changes - before
            self._db.commit()
        return written

    def query(self, name: str, params: list) -> list[dict]:
        if name not in QUERIES:
            raise ValueError(f"query not allowed: {name}")
        with self._lock:
            cur = self._db.execute(self._settings.sql("queries", name), params)
            return [dict(r) for r in cur.fetchall()]

    def pending_filings(self, day_from, day_to, max_attempts, limit):
        return self.query("filings_pending", [day_from, day_to, max_attempts, limit])

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

    def _path(self, key: str) -> Path:
        path = (self.objects / key).resolve()
        if self.objects.resolve() not in path.parents:
            raise ValueError(f"bad object key: {key}")
        return path

    def get_object(self, key):
        path = self._path(key)
        return path.read_bytes() if path.exists() else None

    def put_object(self, key, body, content_type="application/json"):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(body)
        tmp.replace(path)

    def get_dossier(self, scrip_code):
        body = self.get_object(f"memory/{scrip_code}.json")
        return json.loads(body) if body else None

    def put_dossier(self, scrip_code, dossier):
        self.put_object(f"memory/{scrip_code}.json", _encode(dossier).encode())

    def list_dossiers(self):
        return sorted(p.stem for p in (self.objects / "memory").glob("*.json"))
