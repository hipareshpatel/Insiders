"""F213: NSE and BSE files are downloaded in batches of at most FILE_BATCH (default 100), with a pause of FILE_BATCH_PAUSE_S
(default 0 s: none; raise it if wanted) between batches (owner rule, 27 Oct 2026). A batch is a size, not a cap: a run keeps going until its work or
time budget is done, and nothing waits for a later run. A file is a downloaded document (PDF, XBRL/XML, ZIP, attachment);
list, search and JSON calls are not files. Every download site calls ``take()`` once per file, before the request; a file
read from the R2 store, the text cache or the XBRL store never reaches the client, so it is not counted. The pause is taken
before the 101st file (never after the last one), holding the lock so every worker thread waits with it; the pacing and
concurrency inside a batch are each client's own, unchanged. FILE_BATCH=0 turns batching off (no pause)."""
from __future__ import annotations

import logging
import threading
import time

from . import settings

log = logging.getLogger(__name__)


class FileCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.used = 0
        self.pauses = 0
        self.sleep = time.sleep

    def reset(self) -> None:
        with self._lock:
            self.used = self.pauses = 0
            self.sleep = time.sleep

    def take(self, what: str = "") -> None:
        """Count one file about to be downloaded; between batches, pause first."""
        batch = settings.file_batch()
        with self._lock:
            if batch and self.used and self.used % batch == 0:
                pause = settings.file_batch_pause_s()
                self.pauses += 1
                log.info("file batch of %d done (%d files so far); pausing %g s before the next", batch, self.used, pause)
                if pause > 0:
                    self.sleep(pause)
            self.used += 1

    def batches(self) -> int:
        batch = settings.file_batch()
        return -(-self.used // batch) if batch and self.used else (1 if self.used else 0)

    def summary(self) -> str:
        n = self.batches()
        return f"files {self.used} in {n} batch{'es' if n != 1 else ''}"


files = FileCounter()
