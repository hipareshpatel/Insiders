-- BSE Corporate Intelligence: D1 schema (SQLite).
-- Shared by the Cloudflare Worker (wrangler migrations) and the Python
-- pipeline's LocalSink, so the two never drift.
--
-- Write-budget note: D1 counts every index entry touched as a row written
-- (free tier: 100k/day). Each table below carries only the indexes its read
-- paths actually need.

-- Every company we have seen in a filing, enriched by the market-data job.
CREATE TABLE IF NOT EXISTS companies (
    scrip_code         TEXT PRIMARY KEY,
    symbol             TEXT,
    company_name       TEXT NOT NULL,
    isin               TEXT,
    industry           TEXT,             -- BSE industry string (covers all BSE scrips)
    sector             TEXT,             -- prompt-module sector resolved from industry
    market_cap_cr      REAL,
    size_category      TEXT,             -- LARGE | MID | SMALL | MICRO
    shares_outstanding REAL,
    shares_updated_at  TEXT,
    last_price         REAL,
    price_date         TEXT,
    ret_1w             REAL,             -- percent
    ret_1m             REAL,
    ret_1y             REAL,
    card_count         INTEGER NOT NULL DEFAULT 0,
    last_card_at       TEXT,
    updated_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_companies_name ON companies (company_name COLLATE NOCASE);

-- Ledger of every filing discovered on BSE, material or not. This is the
-- pipeline's work queue (status machine), its idempotency guard, and the
-- source for the frontend's "noise audit" view.
--   status: PENDING | DROPPED_RULE | NOT_MATERIAL | ANALYZED | FAILED
--   route:  FAST_TRACK (skip Pass 1) | PASS1 | NONE
CREATE TABLE IF NOT EXISTS filings (
    news_id      TEXT PRIMARY KEY,
    scrip_code   TEXT NOT NULL,
    company_name TEXT,
    headline     TEXT,
    category     TEXT,
    subcategory  TEXT,
    filed_at     TEXT NOT NULL,          -- ISO-8601 with +05:30 offset
    filing_date  TEXT NOT NULL,          -- YYYY-MM-DD (IST)
    pdf_url      TEXT,
    status       TEXT NOT NULL,
    route        TEXT NOT NULL DEFAULT 'NONE',
    event_type   TEXT,
    reason       TEXT,
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT,
    updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_filings_queue ON filings (status, filed_at);
CREATE INDEX IF NOT EXISTS idx_filings_date ON filings (filing_date, status);

-- One "super-card" per material filing.
CREATE TABLE IF NOT EXISTS cards (
    news_id         TEXT PRIMARY KEY,
    scrip_code      TEXT NOT NULL,
    symbol          TEXT,
    company_name    TEXT,
    filing_date     TEXT NOT NULL,
    filed_at        TEXT NOT NULL,
    sector          TEXT,
    event_category  TEXT NOT NULL,
    impact_level    TEXT NOT NULL,       -- HIGH | MODERATE | LOW
    headline        TEXT NOT NULL,
    grounding_score REAL,                -- share of card numbers found in the source
    needs_review    INTEGER NOT NULL DEFAULT 0,
    memory_complete INTEGER NOT NULL DEFAULT 1,  -- 0 when backfill had not reached this filing's date
    card_json       TEXT NOT NULL,
    pdf_url         TEXT,
    model           TEXT,
    created_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_cards_feed ON cards (filed_at DESC);
CREATE INDEX IF NOT EXISTS idx_cards_impact ON cards (impact_level, filed_at DESC);
CREATE INDEX IF NOT EXISTS idx_cards_category ON cards (event_category, filed_at DESC);
CREATE INDEX IF NOT EXISTS idx_cards_scrip ON cards (scrip_code, filed_at DESC);

-- Full-text search for the Ctrl+K palette. External-content tables keep the
-- text in one place; triggers keep the index in sync.
CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5 (
    headline, company_name, symbol,
    content = 'cards', content_rowid = 'rowid', tokenize = 'unicode61'
);
CREATE TRIGGER IF NOT EXISTS cards_ai AFTER INSERT ON cards BEGIN
    INSERT INTO cards_fts (rowid, headline, company_name, symbol)
    VALUES (new.rowid, new.headline, new.company_name, new.symbol);
    UPDATE companies
       SET card_count = card_count + 1,
           last_card_at = max(coalesce(last_card_at, ''), new.filed_at)
     WHERE scrip_code = new.scrip_code;
END;
CREATE TRIGGER IF NOT EXISTS cards_au AFTER UPDATE ON cards BEGIN
    INSERT INTO cards_fts (cards_fts, rowid, headline, company_name, symbol)
    VALUES ('delete', old.rowid, old.headline, old.company_name, old.symbol);
    INSERT INTO cards_fts (rowid, headline, company_name, symbol)
    VALUES (new.rowid, new.headline, new.company_name, new.symbol);
END;
CREATE TRIGGER IF NOT EXISTS cards_ad AFTER DELETE ON cards BEGIN
    INSERT INTO cards_fts (cards_fts, rowid, headline, company_name, symbol)
    VALUES ('delete', old.rowid, old.headline, old.company_name, old.symbol);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS companies_fts USING fts5 (
    company_name, symbol, scrip_code,
    content = 'companies', content_rowid = 'rowid', tokenize = 'unicode61'
);
CREATE TRIGGER IF NOT EXISTS companies_ai AFTER INSERT ON companies BEGIN
    INSERT INTO companies_fts (rowid, company_name, symbol, scrip_code)
    VALUES (new.rowid, new.company_name, new.symbol, new.scrip_code);
END;
CREATE TRIGGER IF NOT EXISTS companies_au AFTER UPDATE OF company_name, symbol ON companies BEGIN
    INSERT INTO companies_fts (companies_fts, rowid, company_name, symbol, scrip_code)
    VALUES ('delete', old.rowid, old.company_name, old.symbol, old.scrip_code);
    INSERT INTO companies_fts (rowid, company_name, symbol, scrip_code)
    VALUES (new.rowid, new.company_name, new.symbol, new.scrip_code);
END;

-- Future-dated catalysts for the calendar view (record dates, AGMs, rights windows...).
CREATE TABLE IF NOT EXISTS catalysts (
    id             TEXT PRIMARY KEY,     -- hash(scrip_code, event_type, event_date)
    scrip_code     TEXT NOT NULL,
    company_name   TEXT,
    symbol         TEXT,
    event_type     TEXT NOT NULL,
    event_date     TEXT NOT NULL,        -- YYYY-MM-DD
    description    TEXT,
    source_news_id TEXT,
    created_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_catalysts_date ON catalysts (event_date);

-- One row per pipeline invocation, for the System Monitor view.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id      TEXT PRIMARY KEY,
    mode        TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL,           -- RUNNING | OK | PARTIAL | ERROR
    stats_json  TEXT,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_started ON pipeline_runs (started_at DESC);

-- Daily AI usage per provider/model. Persisted so quota-aware routing
-- survives across stateless runner invocations. Pipeline posts deltas.
CREATE TABLE IF NOT EXISTS provider_usage (
    day           TEXT NOT NULL,         -- YYYY-MM-DD (UTC; most providers reset at 00:00 UTC)
    provider      TEXT NOT NULL,
    model         TEXT NOT NULL,
    requests      INTEGER NOT NULL DEFAULT 0,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    failures      INTEGER NOT NULL DEFAULT 0,
    rate_limited  INTEGER NOT NULL DEFAULT 0,
    limit_rpd     INTEGER,
    limit_tpd     INTEGER,
    last_error    TEXT,
    updated_at    TEXT,
    PRIMARY KEY (day, provider, model)
);

-- Small key/value store: backfill watermark, D1 write counters, etc.
CREATE TABLE IF NOT EXISTS kv (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT
);
