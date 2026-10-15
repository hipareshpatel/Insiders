"""SQLite + filesystem sink for development and dry runs (same SQL as D1)."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from ..settings import Settings
from .base import QUERIES, STATEMENTS, Sink, SinkRejected, chunk_rows


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
        self._migrate(settings.db_dir / "migrations")

    def _migrate(self, folder: Path) -> None:
        """Apply each migration once, as wrangler does for D1 (ALTER TABLE cannot run twice)."""
        self._db.execute("CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY)")
        done = {r[0] for r in self._db.execute("SELECT name FROM _migrations")}
        for migration in sorted(folder.glob("*.sql")):
            if migration.name in done:
                continue
            self._db.executescript(migration.read_text())
            self._db.execute("INSERT INTO _migrations (name) VALUES (?)", [migration.name])
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
            try:
                for batch in chunk_rows(rows, _encode):
                    before = self._db.total_changes
                    self._db.execute(sql, [_encode(batch)])
                    written += self._db.total_changes - before
            except sqlite3.IntegrityError as exc:
                self._db.rollback()
                raise SinkRejected(f"{statement}: {exc}") from exc
            self._db.commit()
        return written

    def query(self, name: str, params: list) -> list[dict]:
        if name not in QUERIES:
            raise ValueError(f"query not allowed: {name}")
        with self._lock:
            cur = self._db.execute(self._settings.sql("queries", name), params)
            return [dict(r) for r in cur.fetchall()]

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
        # Checked lexically: resolve() raced with concurrent writes on Windows and rejected good keys.
        parts = key.split("/")
        if not key or "\\" in key or ":" in key or key.startswith("/") or any(p in ("", ".", "..") for p in parts):
            raise ValueError(f"bad object key: {key}")
        return self.objects.joinpath(*parts)

    def get_object(self, key):
        path = self._path(key)
        return path.read_bytes() if path.exists() else None

    def put_object(self, key, body, content_type="application/json"):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f"{path.suffix}.{threading.get_ident()}.tmp")  # one temp file per writer
        tmp.write_bytes(body)
        tmp.replace(path)

    def get_dossier(self, scrip_code):
        body = self.get_object(f"memory/{scrip_code}.json")
        return json.loads(body) if body else None

    def put_dossier(self, scrip_code, dossier):
        self.put_object(f"memory/{scrip_code}.json", _encode(dossier).encode())

    def list_objects(self, prefix):
        keys = (p.relative_to(self.objects).as_posix() for p in self.objects.rglob("*")
                if p.is_file() and not p.name.endswith(".tmp"))
        return sorted(k for k in keys if k.startswith(prefix))
