-- ?1 = minimum market cap (₹ Cr). Companies below it and not on the watchlist: their filings are
-- not analysed (blueprint: investable universe). Companies with no market cap yet stay in.
-- Scans companies once; run by market-data / sync-companies, which publish the result to R2.
SELECT scrip_code FROM companies
 WHERE market_cap_cr IS NOT NULL AND market_cap_cr < ?1 AND watchlist = 0;
