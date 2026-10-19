-- ?1 = scrip code after which to continue, ?2 = limit. The NSE universe (universe.build_nse): each company's
-- ISIN and symbol to join NSE's equity list on, its market cap for the floor and the owner's watchlist star.
SELECT scrip_code, symbol, isin, market_cap_cr, watchlist
  FROM companies
 WHERE scrip_code > ?1
 ORDER BY scrip_code
 LIMIT ?2;
