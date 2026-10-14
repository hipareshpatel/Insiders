-- ?1 = from date, ?2 = to date, ?3 = max attempts, ?4 = limit.
-- Companies with historical filings still to analyse, largest market cap first; companies
-- without a market cap yet come last, busiest first. This scans the pending queue, so the
-- pipeline runs it at most once a day and caches the order in kv.
SELECT f.scrip_code, count(*) AS pending, max(c.market_cap_cr) AS market_cap_cr
  FROM filings f
  LEFT JOIN companies c ON c.scrip_code = f.scrip_code
 WHERE (f.status = 'PENDING' OR (f.status = 'FAILED' AND f.attempts < ?3))
   AND f.filing_date BETWEEN ?1 AND ?2
 GROUP BY f.scrip_code
 ORDER BY max(c.market_cap_cr) IS NULL, max(c.market_cap_cr) DESC, count(*) DESC, f.scrip_code
 LIMIT ?4;
