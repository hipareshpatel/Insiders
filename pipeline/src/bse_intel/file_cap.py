"""F213: a run downloads at most FILE_CAP NSE/BSE files (default 100; 0 = no cap; owner rule, 27 Oct 2026). A file is a
downloaded document (PDF, XBRL/XML, ZIP, attachment); list, search and JSON calls are not files. Every download site
calls ``take()`` once per file, before the request; a file read from the R2 store, the text cache or the XBRL store never
reaches the client, so it is not counted. Past the cap ``take()`` raises FileCapReached, a kind of SourceBlockedError, so
every caller that already stops its run on a refusal stops on the cap the same way, and the rest waits for the next run.
The cap is for the whole run: a sharded job sets FILE_CAP_SHARDS and each shard (its own process) gets FILE_CAP // shards,
at least 1."""
from __future__ import annotations

import logging
import threading

from . import settings

log = logging.getLogger(__name__)


def shard_cap(cap: int, shards: int) -> int:
    """The cap one shard of a sharded run holds: the run's cap split evenly, at least 1. 0 (no cap) stays 0."""
    if cap <= 0:
        return 0
    return max(1, cap // shards) if shards > 1 else cap


class FileCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.used = 0
        self.reached = False

    def reset(self) -> None:
        with self._lock:
            self.used = 0
            self.reached = False

    def cap(self) -> int:
        return shard_cap(settings.file_cap(), settings.file_cap_shards())

    def take(self, what: str = "") -> None:
        """Count one file about to be downloaded; past the cap raise FileCapReached instead (nothing is counted)."""
        cap = self.cap()
        with self._lock:
            if cap and self.used >= cap:
                first = not self.reached
                self.reached = True
            else:
                self.used += 1
                return
        if first:
            log.warning("file cap reached: the rest waits for the next run (%d of %d files)", self.used, cap)
        from .nse import FileCapReached   # nse imports this module, so the class is looked up at the call
        raise FileCapReached(f"file cap reached ({self.used} of {cap} files): the rest waits for the next run")

    def summary(self) -> str:
        cap = self.cap()
        text = f"files downloaded {self.used} of cap {cap if cap else 'none'}"
        return text + ("; file cap reached: the rest waits for the next run" if self.reached else "")


files = FileCounter()
