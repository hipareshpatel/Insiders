-- ?1 = limit. Every company (market-data --all, run on the laptop before the backfill so the
-- investable-universe filter and size tiers work from the first card).
SELECT scrip_code, symbol, shares_outstanding, shares_updated_at, price_date
  FROM companies
 ORDER BY scrip_code
 LIMIT ?1;
