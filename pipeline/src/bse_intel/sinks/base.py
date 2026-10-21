"""Storage interface: where the pipeline reads state from and writes results to.

Two implementations share the same SQL (db/statements, db/queries):
* PlatformSink -> the deployed Worker's internal API (D1 + R2), production.
* LocalSink    -> a SQLite file plus a directory of dossiers, for development
                  and dry runs without any Cloudflare account.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

# Statements a sink may execute; each takes one bound parameter, a JSON array.
STATEMENTS = (
    "filings_discover",
    "filings_update",
    "cards_upsert",
    "companies_upsert",
    "companies_seen",
    "catalysts_upsert",
    "runs_upsert",
    "usage_add",
    "kv_set",
    "filings_import",
    "cards_reaction",
    "cards_delete",
    "cards_apply_verdicts",
)

QUERIES = (
    "filings_pending",
    "filings_failed",
    "filings_pending_company",
    "filings_recent_company",
    "card_held",
    "annual_cards_without_xbrl",
    "event_cards_without_xbrl",
    "results_cards_recent",
    "filings_remaining",
    "filings_known_day",
    "backfill_companies",
    "usage_for_day",
    "usage_for_month",
    "kv_get",
    "company_get",
    "peer_cards",
    "companies_for_market",
    "companies_outside_universe",
    "companies_universe",
    "companies_for_market_all",
    "export_cards",
    "export_companies",
    "export_catalysts",
    "export_filings",
    "export_kv",
    "snapshot_feed",
    "snapshot_signals",
    "snapshot_count",
    "feedback_examples",
    "cards_awaiting_reaction",
    "reaction_summary",
)

# Statements that add to what is stored: repeating one after an ambiguous failure (a timeout after
# D1 committed) would count twice, so they are retried only when the request never got through.
NOT_IDEMPOTENT = frozenset({"usage_add"})

# Keep each JSON payload comfortably under D1's per-value size limit.
MAX_PAYLOAD_BYTES = 900_000


class SinkRejected(RuntimeError):
    """The database refused a statement's rows (a constraint, a bad value). Not worth retrying."""


class SinkUnavailable(RuntimeError):
    """The platform did not answer at all - the connection was refused or dropped through every retry.

    Not the filing's fault, so it must not count as a failed attempt: on 2026-10-17 the local web server
    had exited and a run marked all twenty filings it touched as failed in thirty seconds. A filing past
    its attempt limit is never retried, so in a backfill that is silent loss rather than a delay."""


class Sink(ABC):
    @abstractmethod
    def execute(self, statement: str, rows: list[dict]) -> int:
        """Run a whitelisted statement over rows; returns D1 rows written."""

    @abstractmethod
    def query(self, name: str, params: list) -> list[dict]:
        """Run a whitelisted read query from db/queries."""

    def pending_filings(self, day_from: str, day_to: str, max_attempts: int, limit: int,
                        after: tuple[str, str] = ("", "")) -> list[dict]:
        """Queued filings in a date window, oldest first, starting after ``after`` (filed_at, news_id)."""
        return self.query("filings_pending", [day_from, day_to, max_attempts, limit, *after])

    def filings_remaining(self, day_from: str, day_to: str, max_attempts: int) -> bool:
        rows = self.query("filings_remaining", [day_from, day_to, max_attempts])
        return bool(rows and rows[0].get("remaining"))

    def known_ids(self, day: str) -> set[str]:
        return set(self.known_sources(day))

    def known_sources(self, day: str) -> dict[str, str | None]:
        """News id -> stored attachment URL for one day's ledger rows."""
        return {r["news_id"]: r.get("pdf_url") for r in self.query("filings_known_day", [day])}

    def pending_for_company(self, scrip_code: str, day_from: str, day_to: str, max_attempts: int, limit: int) -> list[dict]:
        return self.query("filings_pending_company", [scrip_code, day_from, day_to, max_attempts, limit])

    @abstractmethod
    def usage(self, day: str) -> list[dict]: ...

    @abstractmethod
    def usage_month(self, month: str) -> list[dict]: ...

    @abstractmethod
    def kv_get(self, key: str) -> str | None: ...

    @abstractmethod
    def company(self, scrip_code: str) -> dict | None: ...

    @abstractmethod
    def peer_cards(self, sector: str, event_category: str, scrip_code: str, since: str, until: str, limit: int = 5) -> list[dict]: ...

    @abstractmethod
    def get_dossier(self, scrip_code: str) -> dict | None: ...

    @abstractmethod
    def put_dossier(self, scrip_code: str, dossier: dict) -> None: ...

    def list_dossiers(self) -> list[str]:
        return [k.removeprefix("memory/").removesuffix(".json") for k in self.list_objects("memory/")]

    @abstractmethod
    def list_objects(self, prefix: str) -> list[str]: ...

    @abstractmethod
    def put_object(self, key: str, body: bytes, content_type: str = "application/json") -> None: ...

    @abstractmethod
    def get_object(self, key: str) -> bytes | None: ...

    def kv_set(self, key: str, value: str, updated_at: str) -> int:
        return self.execute("kv_set", [{"key": key, "value": value, "updated_at": updated_at}])

    # every row this process wrote through the sink (the platform sink counts what D1 reports), and how many of them a
    # job has already added to the day's counter
    written_total = 0
    _recorded = 0

    def add_writes(self, day: str, rows_written: int, updated_at: str) -> None:
        """Add a job's D1 writes to the day's counter, which gates backfill against the free tier."""
        if rows_written <= 0:
            return
        self._recorded += rows_written
        try:
            current = int(self.kv_get(f"d1_writes:{day}") or 0)
        except ValueError:
            current = 0
        self.kv_set(f"d1_writes:{day}", str(current + rows_written), updated_at)

    def add_uncounted_writes(self, day: str, updated_at: str) -> None:
        """Add what this process wrote that no job counted: the counter said 93,369 on 20 Oct 2026 when D1 stopped
        taking writes at its free 100,000, because refresh-card-blocks, refresh-summaries, requeue and the seeds wrote
        without adding theirs. Called once as every command ends."""
        self.add_writes(day, self.written_total - self._recorded, updated_at)


def chunk_rows(rows: list[dict], encode) -> list[list[dict]]:
    """Split rows into batches whose encoded size stays under MAX_PAYLOAD_BYTES."""
    batches, batch, size = [], [], 2
    for row in rows:
        row_size = len(encode(row)) + 1
        if batch and size + row_size > MAX_PAYLOAD_BYTES:
            batches.append(batch)
            batch, size = [], 2
        batch.append(row)
        size += row_size
    if batch:
        batches.append(batch)
    return batches
