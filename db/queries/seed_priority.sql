-- ?1 = earliest day, ?2 = latest day. seed-memory --universe: the companies whose results are due (a board meeting
-- in the window) or that filed in it, soonest first, seeded before the rest (owner, 2026-10-21: E2E's card had no
-- earlier quarters because the seed walks scrip codes in order and had not reached it).
SELECT scrip_code, min(day) AS day FROM (
  SELECT scrip_code, event_date AS day FROM catalysts WHERE event_date >= ?1 AND event_date <= ?2
  UNION ALL
  SELECT scrip_code, substr(filed_at, 1, 10) AS day FROM filings WHERE filed_at >= ?1 AND filed_at <= ?2 || 'T99'
)
GROUP BY scrip_code
ORDER BY day
LIMIT 2000;
