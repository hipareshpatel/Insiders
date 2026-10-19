-- Fixes from the pre-launch audit (D1 read and write cost, ledger fields).

-- Queued filings keep BSE's subject line (the Pass 1 prompt and the number check read it) and the
-- NSE symbol, which were lost between discovery and analysis.
ALTER TABLE filings ADD COLUMN subject TEXT;
ALTER TABLE filings ADD COLUMN symbol TEXT;

-- The search index is rebuilt only when a name or symbol really changes. "UPDATE OF" fires
-- whenever the columns are assigned, so every price update cost five row writes instead of one.
DROP TRIGGER IF EXISTS companies_au;
CREATE TRIGGER companies_au AFTER UPDATE OF company_name, symbol ON companies
WHEN old.company_name IS NOT new.company_name OR old.symbol IS NOT new.symbol
BEGIN
    INSERT INTO companies_fts (companies_fts, rowid, company_name, symbol, scrip_code)
    VALUES ('delete', old.rowid, old.company_name, old.symbol, old.scrip_code);
    INSERT INTO companies_fts (rowid, company_name, symbol, scrip_code)
    VALUES (new.rowid, new.company_name, new.symbol, new.scrip_code);
END;

-- Peer context (same event type, same sector, last 60 days) seeks straight to its rows. The old
-- (event_category, filed_at) index served nothing else: the feed's optional filters cannot use it.
DROP INDEX IF EXISTS idx_cards_category;
CREATE INDEX IF NOT EXISTS idx_cards_peer ON cards (event_category, sector, filed_at DESC);
