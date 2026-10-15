"""sync-to-cloud (blueprint §3.2, §15 phase 6): copy the laptop's local database and objects to
Cloudflare once the local backfill is verified.

The source is the local Worker (``wrangler dev`` state under ``data/wrangler``) or a LocalSink; the
destination is the deployed Worker. Everything goes through the same whitelisted statements as the
pipeline, so nothing new can be written remotely.

D1's free tier allows 100,000 rows written per day, and the import counts. Each card costs about
eight (its row, four indexes and the search index), so a large history takes several days: the
sync stops at the daily budget, records where it stopped in ``data/sync_progress.json`` and carries
on from there the next day. Live runs keep working meanwhile. What is copied:

* companies (all), upcoming catalysts, pipeline state (backfill cursor and order, noise counts);
* cards, oldest first;
* the ledger only for recent days and for filings still queued (the historical ledger stays local);
* R2 objects: dossiers, daily card archives, noise files, the universe file (changed ones only).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta
from pathlib import Path

from .sinks.base import Sink
from .timeutil import now_iso, today_ist, utc_day

log = logging.getLogger(__name__)

PAGE = 400
OBJECT_PREFIXES = ("meta/", "memory/", "daily_feed/", "noise/")
RECENT_LEDGER_DAYS = 10


class Sync:
    def __init__(self, source: Sink, dest: Sink, progress_path: Path, write_budget: int):
        self.source, self.dest = source, dest
        self.path = progress_path
        self.progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
        self.budget = write_budget
        self.written = 0
        self.start_writes = int(dest.kv_get(f"d1_writes:{utc_day()}") or 0)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.progress, indent=1))
        tmp.replace(self.path)

    def _room(self) -> bool:
        return self.start_writes + self.written < self.budget

    def _exec(self, statement: str, rows: list[dict]) -> None:
        if rows:
            self.written += self.dest.execute(statement, rows)

    def run(self) -> dict:
        try:
            self._companies()
            self._catalysts()
            self._kv()
            self._filings()
            self._cards()
            self._objects()
        finally:
            self._save()
            self.dest.add_writes(utc_day(), self.written, now_iso())
        done = self._room()
        log.info("sync: %d D1 rows written%s", self.written, "" if done else " (daily budget reached; run again tomorrow)")
        return {"rows_written": self.written, "complete": bool(done and self.progress.get("objects_done")),
                "progress": {k: v for k, v in self.progress.items() if k != "object_hashes"}}

    def _paged(self, name: str, key: str, params, cursor_of, statement: str, transform=lambda r: r) -> None:
        after = self.progress.get(key, "")
        while self._room():
            rows = self.source.query(name, params(after))
            if not rows:
                break
            self._exec(statement, [transform(r) for r in rows])
            after = cursor_of(rows[-1])
            self.progress[key] = after
            self._save()

    def _companies(self) -> None:
        self._paged("export_companies", "companies_after", lambda a: [a, PAGE], lambda r: r["scrip_code"], "companies_upsert")

    def _catalysts(self) -> None:
        today = today_ist().isoformat()
        self._paged("export_catalysts", "catalysts_after", lambda a: [today, a, PAGE], lambda r: r["id"], "catalysts_upsert")

    def _kv(self) -> None:
        rows = [r for r in self.source.query("export_kv", []) if self._room()]
        self._exec("kv_set", rows)

    def _filings(self) -> None:
        since = (today_ist() - timedelta(days=RECENT_LEDGER_DAYS)).isoformat()
        self._paged("export_filings", "filings_after", lambda a: [since, a, PAGE], lambda r: r["news_id"], "filings_import")

    def _cards(self) -> None:
        def params(after):
            filed_at, _, news_id = (after or "|").partition("|")
            return [filed_at, news_id, PAGE // 4]

        def transform(row):
            row = dict(row)
            row["card"] = json.loads(row.pop("card_json"))
            return row

        self._paged("export_cards", "cards_after", params, lambda r: f"{r['filed_at']}|{r['news_id']}", "cards_upsert", transform)

    def _objects(self) -> None:
        """R2 has its own (generous) operation limits; copy objects whose content changed."""
        hashes: dict[str, str] = self.progress.setdefault("object_hashes", {})
        copied = 0
        for prefix in OBJECT_PREFIXES:
            for key in self.source.list_objects(prefix):
                body = self.source.get_object(key)
                if body is None:
                    continue
                digest = hashlib.sha1(body).hexdigest()
                if hashes.get(key) == digest:
                    continue
                self.dest.put_object(key, body)
                hashes[key] = digest
                copied += 1
                if copied % 200 == 0:
                    self._save()
        self.progress["objects_done"] = True
        log.info("sync: %d objects copied", copied)
