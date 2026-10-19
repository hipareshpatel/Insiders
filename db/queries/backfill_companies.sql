-- ?1 = from date, ?2 = to date, ?3 = max attempts, ?4 = limit.
-- Companies with historical filings still to analyse, largest market cap first; companies
-- without a market cap yet come last, busiest first. This reads the whole pending queue, so the
-- pipeline runs it about once a day and keeps the order in kv. Counting before the join looks
-- each company up once instead of once per filing.
SELECT g.scrip_code, g.pending, c.market_cap_cr
  FROM (SELECT scrip_code, count(*) AS pending
          FROM (SELECT scrip_code FROM filings
                 WHERE status = 'PENDING' AND filed_at >= ?1 AND filed_at < date(?2, '+1 day')
                UNION ALL
                SELECT scrip_code FROM filings
                 WHERE status = 'FAILED' AND attempts < ?3 AND filed_at >= ?1 AND filed_at < date(?2, '+1 day'))
         GROUP BY scrip_code) g
  LEFT JOIN companies c ON c.scrip_code = g.scrip_code
 ORDER BY c.market_cap_cr IS NULL, c.market_cap_cr DESC, g.pending DESC, g.scrip_code
 LIMIT ?4;
