-- Company-by-company backfill and "history first" for live filings read one company's queue.
-- One extra index entry per filing row; backfill no longer stores noise rows, which saves far more.
CREATE INDEX IF NOT EXISTS idx_filings_scrip ON filings (scrip_code, status, filed_at);
