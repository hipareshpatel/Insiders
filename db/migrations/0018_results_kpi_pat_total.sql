-- The whole profit (minority partners' share included) beside the owners' profit (owner, 31 Oct 2026 ~21:30 IST: "Both, owners' first";
-- news sites and Screener's Net Profit show the whole profit, so a company with large minority partners read differently, Phoenix Mills
-- Q2FY27 +7.1% owners against +11.2% whole). Set only when the PAT column is the owners' and the whole profit differs; null elsewhere,
-- so every earlier row stays valid.
ALTER TABLE results_kpi ADD COLUMN pat_total REAL;
ALTER TABLE results_kpi ADD COLUMN pat_total_prev REAL;
ALTER TABLE results_kpi ADD COLUMN pat_total_yoy REAL;
ALTER TABLE results_kpi ADD COLUMN pat_total_turn TEXT;   -- a named turn across a loss, as pat_turn
