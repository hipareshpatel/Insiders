"""F213: a run downloads at most FILE_CAP NSE/BSE files (default 100; 0 = no cap; owner rule, 27 Oct 2026). A file is a
downloaded document (PDF, XBRL/XML, ZIP, attachment); list, search and JSON calls are not files. Every download site
calls ``take()`` once per file, before the request; a file read from the R2 store, the text cache or the XBRL store never
reaches the client, so it is not counted. Past the cap ``take()`` raises FileCapReached, a kind of SourceBlockedError, so
every caller that already stops its run on a refusal stops on the cap the same way, and the rest waits for the next run.
The cap is for the whole run: a sharded job sets FILE_CAP_SHARDS and each shard (its own process) gets FILE_CAP // shards,
at least 1. One dispatch is one budget: a process also writes what it used to GITHUB_ENV (FILE_CAP_USED), so the next process
of the same job holds the cap less that; and when the cap is reached it leaves a marker file in FILE_CAP_MARKER_DIR, which the
maintenance chain reads to not move on to its `then` command ("dispatch again for the rest")."""
from __future__ import annotations

import atexit
import logging
import os
import threading

from . import settings

log = logging.getLogger(__name__)


def shard_cap(cap: int, shards: int) -> int:
    """The cap one shard of a sharded run holds: the run's cap split evenly, at least 1. 0 (no cap) stays 0."""
    if cap <= 0:
        return 0
    return max(1, cap // shards) if shards > 1 else cap


def remaining(cap: int, shards: int, used_before: int) -> int | None:
    """Files this process may still download: its shard's share of the cap less what earlier processes of the dispatch
    used (never below 0); None when there is no cap."""
    share = shard_cap(cap, shards)
    return None if share <= 0 else max(0, share - used_before)


class FileCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.used = 0
        self.reached = False
        self._exit_hook = False

    def reset(self) -> None:
        with self._lock:
            self.used = 0
            self.reached = False

    def cap(self) -> int | None:
        return remaining(settings.file_cap(), settings.file_cap_shards(), settings.file_cap_used())

    def _record_used(self) -> None:
        """At exit: hand the next process of this job what is left (GITHUB_ENV), and say whether the cap was reached."""
        path = os.environ.get("GITHUB_ENV")
        if path and self.used:
            try:
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(f"FILE_CAP_USED={settings.file_cap_used() + self.used}\n")
            except OSError:
                pass

    def _mark_reached(self) -> None:
        folder = os.environ.get("FILE_CAP_MARKER_DIR")
        if folder:
            try:
                os.makedirs(folder, exist_ok=True)
                with open(os.path.join(folder, f"capped-{os.getpid()}"), "w", encoding="utf-8") as fh:
                    fh.write("file cap reached\n")
            except OSError:
                pass

    def take(self, what: str = "") -> None:
        """Count one file about to be downloaded; past the cap raise FileCapReached instead (nothing is counted)."""
        cap = self.cap()
        with self._lock:
            if cap is not None and self.used >= cap:
                first = not self.reached
                self.reached = True
            else:
                self.used += 1
                if not self._exit_hook:
                    self._exit_hook = True
                    atexit.register(self._record_used)
                return
        if first:
            self._mark_reached()
            log.warning("file cap reached: the rest waits for the next run (%d of %d files)", self.used, cap)
        from .nse import FileCapReached   # nse imports this module, so the class is looked up at the call
        raise FileCapReached(f"file cap reached ({self.used} of {cap} files): the rest waits for the next run")

    def summary(self) -> str:
        cap = self.cap()
        text = f"files downloaded {self.used} of cap {cap if cap is not None else 'none'}"
        return text + ("; file cap reached: the rest waits for the next run" if self.reached else "")


files = FileCounter()
