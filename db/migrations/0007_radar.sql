-- Company memory summary (Inflection Radar, overdue promises, directory columns), the needs-review
-- queue, and search across former names (blueprint §13).
ALTER TABLE companies ADD COLUMN memory_summary_json TEXT;
ALTER TABLE companies ADD COLUMN earliest_open_due TEXT;     -- earliest due date of an open promise
ALTER TABLE companies ADD COLUMN inflection_last_at TEXT;    -- date of the latest inflection trigger
CREATE INDEX IF NOT EXISTS idx_companies_due ON companies (earliest_open_due) WHERE earliest_open_due IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_companies_inflection ON companies (inflection_last_at) WHERE inflection_last_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cards_review ON cards (filed_at DESC) WHERE needs_review = 1;

-- Company search also matches former names (Novartis India finds Evonile Pharma).
DROP TRIGGER IF EXISTS companies_ai;
DROP TRIGGER IF EXISTS companies_au;
DROP TABLE IF EXISTS companies_fts;
CREATE VIRTUAL TABLE companies_fts USING fts5 (
    company_name, symbol, scrip_code, former_names_json,
    content = 'companies', content_rowid = 'rowid', tokenize = 'unicode61'
);
INSERT INTO companies_fts (companies_fts) VALUES ('rebuild');
CREATE TRIGGER companies_ai AFTER INSERT ON companies BEGIN
    INSERT INTO companies_fts (rowid, company_name, symbol, scrip_code, former_names_json)
    VALUES (new.rowid, new.company_name, new.symbol, new.scrip_code, new.former_names_json);
END;
CREATE TRIGGER companies_au AFTER UPDATE OF company_name, symbol, former_names_json ON companies
WHEN old.company_name IS NOT new.company_name OR old.symbol IS NOT new.symbol
  OR old.former_names_json IS NOT new.former_names_json
BEGIN
    INSERT INTO companies_fts (companies_fts, rowid, company_name, symbol, scrip_code, former_names_json)
    VALUES ('delete', old.rowid, old.company_name, old.symbol, old.scrip_code, old.former_names_json);
    INSERT INTO companies_fts (rowid, company_name, symbol, scrip_code, former_names_json)
    VALUES (new.rowid, new.company_name, new.symbol, new.scrip_code, new.former_names_json);
END;
CREATE TRIGGER IF NOT EXISTS companies_ad AFTER DELETE ON companies BEGIN
    INSERT INTO companies_fts (companies_fts, rowid, company_name, symbol, scrip_code, former_names_json)
    VALUES ('delete', old.rowid, old.company_name, old.symbol, old.scrip_code, old.former_names_json);
END;
