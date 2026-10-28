"""A backup before a maintenance job rewrites stored data, so one company's or one card's earlier state can be put back.

Memory had only the weekly export to the `backups` git branch and stored cards had no backup at all (owner, 28 Oct 2026:
"an undo for data writes"). A job that rewrites stored data makes a ``RunBackup`` and saves, before each write, the exact
rows it is about to change, to R2 ``backup/<job>-<UTC time>/``:

* ``memory/<scrip>.json``: the company's dossier as stored (JSON ``null`` when it had none, which a restore deletes);
* ``cards/<part>.json``: ``{"rows": [...]}``, card rows as ``export_cards`` returns them (``card_json`` still a string).

Each object is read back and compared before the write goes ahead; a mismatch raises ``BackupError`` and the job writes
nothing more (the pattern of prune_companies.apply). Only what the run changes is saved, a dossier once per run (its first
backup is the state before the run). ``python -m bse_intel restore`` puts a backup back (restore.py)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

PREFIX = "backup/"
META = "meta.json"


class BackupError(RuntimeError):
    """A backup object did not read back as written: the write it guards must not happen."""


def encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class RunBackup:
    """One job run's backup folder. Nothing is written until the first ``cards`` or ``dossier`` call, so a run that changes
    nothing leaves nothing behind."""

    def __init__(self, sink, job: str, at: str | None = None):
        self.sink, self.job = sink, job
        self.prefix = f"{PREFIX}{job}-{at or stamp()}/"
        self.dossiers: set[str] = set()
        self.card_rows = 0
        self._parts = 0
        self._started = False

    def save(self, name: str, body: bytes) -> str:
        """Write one object under the run's prefix, read it back, and raise when it differs."""
        if not self._started:
            taken, n = self.prefix, 1
            while self.sink.get_object(self.prefix + META) is not None:   # two runs in one second never share a folder
                n += 1
                if n > 50:
                    raise BackupError(f"no free backup folder near {taken}: nothing written")
                self.prefix = f"{taken.rstrip('/')}-{n}/"
            self._put(META, encode({"job": self.job, "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))
            self._started = True
        return self._put(name, body)

    def _put(self, name: str, body: bytes) -> str:
        key = self.prefix + name
        self.sink.put_object(key, body)
        if self.sink.get_object(key) != body:
            raise BackupError(f"backup {key} did not read back as written: nothing more is written")
        return key

    def cards(self, rows: list[dict]) -> None:
        """Save the stored card rows a page is about to change (as read, not as they will be written)."""
        if not rows:
            return
        self._parts += 1
        self.save(f"cards/{self._parts:05d}.json", encode({"rows": rows}))
        self.card_rows += len(rows)

    def dossier(self, scrip: str) -> None:
        """Save the company's dossier as stored now, once per run: call it right before the job's put_dossier."""
        if scrip in self.dossiers:
            return
        self.save(f"memory/{scrip}.json", encode(self.sink.get_dossier(scrip)))
        self.dossiers.add(scrip)

    def summary(self) -> dict | None:
        return {"prefix": self.prefix, "dossiers": len(self.dossiers), "cards": self.card_rows} if self._started else None
