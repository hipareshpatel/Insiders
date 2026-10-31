-- The profit before exceptional items beside the reported PAT (owner follow-up, 31 Oct 2026; Ind AS 1 shows exceptional items apart, brokers quote
-- adjusted PAT): the owners' profit less the exceptional item after its tax, and its change on the PAT's own rule (results_table.py). Set only
-- for a quarter with a non-zero exceptional item after tax; null elsewhere, so every earlier row stays valid.
ALTER TABLE results_kpi ADD COLUMN pat_pre REAL;
ALTER TABLE results_kpi ADD COLUMN pat_pre_prev REAL;   -- the same line a year earlier (its own exceptional item taken out)
ALTER TABLE results_kpi ADD COLUMN pat_pre_yoy REAL;
ALTER TABLE results_kpi ADD COLUMN pat_pre_turn TEXT;   -- a named turn across a loss, as pat_turn
