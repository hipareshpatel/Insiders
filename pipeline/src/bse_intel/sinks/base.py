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
)

QUERIES = (
    "filings_pending",
    "filings_pending_company",
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
    "companies_for_market_all",
    "export_cards",
    "export_companies",
    "export_catalysts",
    "export_filings",
    "export_kv",
)

# Statements that add to what is stored: repeating one after an ambiguous failure (a timeout after
# D1 committed) would count twice, so they are retried only when the request never got through.
NOT_IDEMPOTENT = frozenset({"usage_add"})

# Keep each JSON payload comfortably under D1's per-value size limit.
MAX_PAYLOAD_BYTES = 900_000


class SinkRejected(RuntimeError):
    """The database refused a statement's rows (a constraint, a bad value). Not worth retrying."""


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
        return {r["news_id"] for r in self.query("filings_known_day", [day])}

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

    def add_writes(self, day: str, rows_written: int, updated_at: str) -> None:
        """Add a job's D1 writes to the day's counter, which gates backfill against the free tier."""
        if rows_written <= 0:
            return
        try:
            current = int(self.kv_get(f"d1_writes:{day}") or 0)
        except ValueError:
            current = 0
        self.kv_set(f"d1_writes:{day}", str(current + rows_written), updated_at)


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
