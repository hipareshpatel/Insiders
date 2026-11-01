-- The Results page as a KPI report (owner, 30 Oct 2026): one row per company and quarter with the growth figures worked out from the
-- saved statements (results_table.py), so the page can filter, sort and summarise them in the database. Not a card: nothing is read from one.
-- kind says which statement layout the company files in (corporate, bank, NBFC, insurer): lenders' revenue is interest income or income,
-- an NBFC's ebitda columns hold its financing profit and margin, a bank has no ebitda or margin, an insurer has profit only.
-- *_key is a sort key: the per cent, or a large signed number for a named turn across a loss (a per cent across a loss means nothing).
-- *_prev is the same line a year earlier, so a group's total growth can be worked out from the amounts.
CREATE TABLE IF NOT EXISTS results_kpi (
  scrip_code TEXT NOT NULL,
  period TEXT NOT NULL,            -- the quarter, "Q2FY27"
  basis TEXT NOT NULL,             -- CONSOLIDATED when the statements have it, else STANDALONE
  kind TEXT NOT NULL,              -- company | bank | nbfc | insurer
  source_news_id TEXT,             -- the NSE filing the quarter's file came with (joined to filings for its date and link), when known
  revenue REAL, revenue_prev REAL, revenue_yoy REAL, revenue_qoq REAL,
  ebitda REAL, ebitda_prev REAL, ebitda_yoy REAL, ebitda_qoq REAL, ebitda_turn TEXT, ebitda_key REAL,
  pat REAL, pat_prev REAL, pat_yoy REAL, pat_qoq REAL, pat_turn TEXT, pat_qoq_turn TEXT, pat_key REAL,
  opm REAL, opm_yoy_bps INTEGER, opm_qoq_bps INTEGER,
  nfo INTEGER NOT NULL DEFAULT 0,  -- 1: profit up (or loss turned to profit) while EBITDA fell ("profit not from operations"); never for lenders or insurers
  digest TEXT NOT NULL,            -- of the figures above: an unchanged row is not rewritten (D1 row writes)
  updated_at TEXT NOT NULL,
  PRIMARY KEY (scrip_code, period)
);
CREATE INDEX IF NOT EXISTS idx_results_kpi_period ON results_kpi (period);
