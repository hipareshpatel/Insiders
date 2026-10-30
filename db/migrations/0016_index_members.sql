-- NSE's broad index constituents with their history (owner, 30 Oct 2026: "map stocks from NSE broad indices", "track index changes so from
-- next quarter onwards it shows the correct way"). One row per index, ISIN and stretch of membership, from NSE's own lists (pipeline
-- index_members.py, every Sunday). A company that leaves gets valid_to; one that returns gets a new row. Joined to companies by ISIN.
-- A quarter uses the members on its last day: valid_from <= day AND (valid_to IS NULL OR valid_to > day).
-- valid_from '1900-01-01' means "a member when we first read the list" (tracking began on the day of that first read, kept in
-- kv 'index_members:tracking_since'), so quarters before it use that first list and can miss companies that had already left.
CREATE TABLE IF NOT EXISTS index_members (
  index_id TEXT NOT NULL,          -- NIFTY50, NIFTYNEXT50, NIFTY100, NIFTY200, NIFTY500, MIDCAP150, SMALLCAP250, MICROCAP250, ...
  isin TEXT NOT NULL,
  symbol TEXT,
  company_name TEXT,
  valid_from TEXT NOT NULL,        -- YYYY-MM-DD
  valid_to TEXT,                   -- YYYY-MM-DD, NULL while a member
  PRIMARY KEY (index_id, isin, valid_from)
);
CREATE INDEX IF NOT EXISTS idx_index_members_isin ON index_members (isin);
CREATE INDEX IF NOT EXISTS idx_index_members_open ON index_members (index_id, valid_to);
