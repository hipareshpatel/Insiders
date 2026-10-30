-- NSE's broad index constituents (owner, 30 Oct 2026: "map stocks from NSE broad indices", "update it every Sunday"), one row per index and
-- ISIN, from NSE's own lists (pipeline index_members.py). Joined to companies by ISIN (symbol as the fallback) in the Results KPI report.
-- as_of is the day the list was read: a constituent that left an index is the row whose as_of is older than its index's newest.
CREATE TABLE IF NOT EXISTS index_members (
  index_id TEXT NOT NULL,          -- NIFTY50, NIFTYNEXT50, NIFTY100, NIFTY200, NIFTY500, MIDCAP150, SMALLCAP250, MICROCAP250, ...
  isin TEXT NOT NULL,
  symbol TEXT,
  company_name TEXT,
  as_of TEXT NOT NULL,
  PRIMARY KEY (index_id, isin)
);
CREATE INDEX IF NOT EXISTS idx_index_members_isin ON index_members (isin);
CREATE INDEX IF NOT EXISTS idx_index_members_symbol ON index_members (symbol);
