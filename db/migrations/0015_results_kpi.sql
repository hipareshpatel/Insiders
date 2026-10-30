-- The Results page as a KPI report (owner, 30 Oct 2026): one row per company and quarter with the growth numbers worked out from the
-- saved statements (results_table.py), so the page can filter and sort them in the database. Not a card: nothing here is read from one.
-- *_key is a sort key: the per cent, or a large signed number for a named turn across a loss (a per cent across a loss means nothing).
CREATE TABLE IF NOT EXISTS results_kpi (
  scrip_code TEXT NOT NULL,
  period TEXT NOT NULL,            -- the quarter, "Q2FY27"
  basis TEXT NOT NULL,             -- CONSOLIDATED when the statements have it, else STANDALONE
  revenue REAL, revenue_yoy REAL, revenue_qoq REAL,
  ebitda REAL, ebitda_yoy REAL, ebitda_qoq REAL, ebitda_turn TEXT, ebitda_key REAL,
  pat REAL, pat_yoy REAL, pat_qoq REAL, pat_turn TEXT, pat_key REAL,
  opm REAL, opm_yoy_bps INTEGER, opm_qoq_bps INTEGER,
  digest TEXT NOT NULL,            -- of the figures above: an unchanged row is not rewritten (D1 row writes)
  updated_at TEXT NOT NULL,
  PRIMARY KEY (scrip_code, period)
);
CREATE INDEX IF NOT EXISTS idx_results_kpi_period ON results_kpi (period);
