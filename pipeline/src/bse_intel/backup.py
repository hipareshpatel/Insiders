"""A backup before a maintenance job rewrites stored data, so one company's or one card's earlier state can be put back.

Memory had only the weekly export to the `backups` git branch and stored cards had no backup at all (owner, 28 Oct 2026:
"an undo for data writes"). A job that rewrites stored data makes a ``RunBackup`` and saves, before each write, the exact
rows it is about to change, to R2 ``backup/<job>-<UTC time>/``, with the state it is about to write beside them:

* ``memory/<scrip>.json``: the company's dossier as stored (JSON ``null`` when it had none);
* ``cards/<part>.json``: ``{"rows": [...]}``, card rows as ``export_cards`` returns them (``card_json`` still a string);
* ``after/memory/<scrip>.json`` and ``after/cards/<part>.json``: the same, as the job wrote them.

A restore (restore.py) puts the "before" back only where the stored value is still the "after": what any other writer
stored since is left alone. Each object is read back and compared before the write goes ahead; a mismatch raises
``BackupError`` and the job writes nothing more (the pattern of prune_companies.apply). Only what the run changes is saved,
a dossier's "before" once per run (its first backup is the state before the run), its "after" at each write.

Runs whose work is done elsewhere (seed-memory for named companies; requeue-failed, whose filings the live run re-reads
later) take a snapshot of the named companies' dossiers and their cards first (``start_scope``) and the "after" at the end
(``save_after``, for the runs that finish before the command ends: seed-memory). requeue-failed --ids has no after-state:
the live run re-reads the filings later, and a seal taken then would count unrelated live writes as the job's, so such a backup
restores only with ``--force``."""

from __future__ import annotations

import json
from datetime import datetime, timezone

PREFIX = "backup/"
META = "meta.json"
AFTER = "after/"
PAGE = 50
SCAN = 100
NO_AFTER = object()   # dossier(): no after-state given (None is one: the job deleted the dossier)


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

    @classmethod
    def attach(cls, sink, prefix: str) -> "RunBackup":
        """The folder of an earlier run, to add its after-state to."""
        backup = cls(sink, prefix.strip("/").split("/", 1)[-1])
        backup.prefix, backup._started = prefix.rstrip("/") + "/", True
        return backup

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

    def cards(self, rows: list[dict], after: list[dict] | None = None) -> None:
        """Save the stored card rows a page is about to change (as read, not as they will be written), and ``after``: the
        rows as they will be written, in the same shape (``card_json`` a string)."""
        if not rows:
            return
        self._parts += 1
        self.save(f"cards/{self._parts:05d}.json", encode({"rows": rows}))
        if after is not None:
            self.save(f"{AFTER}cards/{self._parts:05d}.json", encode({"rows": after}))
        self.card_rows += len(rows)

    def dossier(self, scrip: str, after=NO_AFTER) -> None:
        """Save the company's dossier as stored now (once per run) and, with ``after``, the dossier about to be written
        (every time, the last is kept). Call it right before the job's put_dossier."""
        if scrip not in self.dossiers:
            self.save(f"memory/{scrip}.json", encode(self.sink.get_dossier(scrip)))
            self.dossiers.add(scrip)
        if after is not NO_AFTER:
            self.save(f"{AFTER}memory/{scrip}.json", encode(after))

    def summary(self) -> dict | None:
        return {"prefix": self.prefix, "dossiers": len(self.dossiers), "cards": self.card_rows} if self._started else None


def card_after_row(batch_row: dict) -> dict:
    """A ``cards_upsert`` row (``card`` an object) as an ``export_cards`` row (``card_json`` a string)."""
    row = {k: v for k, v in batch_row.items() if k != "card"}
    row["card_json"] = json.dumps(batch_row["card"], ensure_ascii=False)
    return row


def scan_cards(sink, scrips=(), news_ids=()) -> list[dict]:
    """Stored card rows of the named companies or news ids (export_cards, keyset-paged over every card)."""
    scrips, news_ids = set(scrips), set(news_ids)
    found: list[dict] = []
    if not (scrips or news_ids):
        return found
    after = ["", ""]
    while True:
        rows = sink.query("export_cards", [after[0], after[1], SCAN])
        found += [r for r in rows if r["scrip_code"] in scrips or r["news_id"] in news_ids]
        if len(rows) < SCAN:
            return found
        after = [rows[-1]["filed_at"], rows[-1]["news_id"]]


def start_scope(sink, job: str, scrips=(), news_ids=(), cards_of_scrips: bool = False) -> RunBackup:
    """A run that cannot back up row by row (it changes what it does not know in advance): save, before it starts, the
    dossiers of the named companies and the cards of the named news ids (and of the companies, with ``cards_of_scrips``).
    The companies of named cards are included. Raises BackupError before anything has run if a copy does not read back."""
    backup = RunBackup(sink, job)
    scrips = set(scrips)
    backup.missing_ids = []
    rows = scan_cards(sink, scrips if cards_of_scrips else (), news_ids)
    scrips |= {r["scrip_code"] for r in rows if r["news_id"] in set(news_ids)}
    backup.scrips = sorted(scrips)      # the companies whose dossiers are kept (a requeue by id puts them first: requeue.prioritise)
    backup.missing_ids = sorted(set(news_ids) - {r["news_id"] for r in rows})   # no stored card: its company is not known
    for scrip in sorted(scrips):
        backup.dossier(scrip)
    for at in range(0, len(rows), PAGE):
        backup.cards(rows[at:at + PAGE])
    return backup


def check_prefix(sink, prefix: str) -> str:
    """The backup folder's prefix with its closing slash; ValueError for anything that is not an existing folder
    ``backup/<name>/`` (a restore never reads or writes elsewhere)."""
    name = prefix[len(PREFIX):].strip("/") if prefix.startswith(PREFIX) else ""
    if not name or "/" in name or ".." in name:
        raise ValueError(f"a backup prefix is {PREFIX}<job>-<time>/, not {prefix!r}")
    prefix = f"{PREFIX}{name}/"
    if not sink.list_objects(prefix):
        raise ValueError(f"no backup {prefix} (restore --list shows them)")
    return prefix


def save_after(sink, prefix: str) -> dict:
    """The after-state of a backup made by ``start_scope``, taken by the job that ran in between (seed-memory, at its end):
    the current dossiers and card rows of what it holds. Never for a run the live pipeline finishes later: what it writes
    meanwhile would count as the job's own. Refuses a backup that has an after-state already."""
    prefix = check_prefix(sink, prefix)
    keys = sink.list_objects(prefix)
    if any(k.startswith(prefix + AFTER) for k in keys):
        raise BackupError(f"{prefix} has an after-state already")
    scrips = sorted(k[len(prefix + "memory/"):-len(".json")] for k in keys if k.startswith(prefix + "memory/"))
    ids: list[str] = []
    for k in keys:
        if k.startswith(prefix + "cards/"):
            ids += [r["news_id"] for r in json.loads(sink.get_object(k))["rows"]]
    backup = RunBackup.attach(sink, prefix)
    # pending first, sealed last: a run that stops in between leaves an after-state restore.py knows is incomplete
    backup.save(f"{AFTER}pending.json", encode({"at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))
    for scrip in scrips:
        backup.save(f"{AFTER}memory/{scrip}.json", encode(sink.get_dossier(scrip)))
    rows = scan_cards(sink, news_ids=ids)
    for n, at in enumerate(range(0, len(rows), PAGE), 1):
        backup.save(f"{AFTER}cards/{n:05d}.json", encode({"rows": rows[at:at + PAGE]}))
    backup.save(f"{AFTER}sealed.json", encode({"at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))
    return {"prefix": prefix, "dossiers": len(scrips), "cards": len(rows)}
