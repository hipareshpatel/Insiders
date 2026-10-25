-- ?1 = scrip code after which to continue, ?2 = limit. prune-companies: each company with what it holds in D1
-- (cards counted, not companies.card_count; filing ledger rows). Reads only.
SELECT c.scrip_code, c.symbol, c.company_name, c.isin, c.market_cap_cr, c.watchlist, c.card_count,
       (SELECT count(*) FROM cards k WHERE k.scrip_code = c.scrip_code) AS cards,
       (SELECT count(*) FROM filings f WHERE f.scrip_code = c.scrip_code) AS filings
  FROM companies c
 WHERE c.scrip_code > ?1
 ORDER BY c.scrip_code
 LIMIT ?2;
