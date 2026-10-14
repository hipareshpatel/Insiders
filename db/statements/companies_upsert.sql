-- ?1 = JSON array of partial company rows. Missing fields never erase
-- existing values, so filings and the market-data job can each send only
-- what they know.
INSERT INTO companies (scrip_code, symbol, company_name, isin, industry, sector, market_cap_cr,
                       size_category, shares_outstanding, shares_updated_at, last_price,
                       price_date, ret_1w, ret_1m, ret_1y, updated_at)
SELECT json_extract(value, '$.scrip_code'),
       json_extract(value, '$.symbol'),
       coalesce(json_extract(value, '$.company_name'), json_extract(value, '$.scrip_code')),
       json_extract(value, '$.isin'),
       json_extract(value, '$.industry'),
       json_extract(value, '$.sector'),
       json_extract(value, '$.market_cap_cr'),
       json_extract(value, '$.size_category'),
       json_extract(value, '$.shares_outstanding'),
       json_extract(value, '$.shares_updated_at'),
       json_extract(value, '$.last_price'),
       json_extract(value, '$.price_date'),
       json_extract(value, '$.ret_1w'),
       json_extract(value, '$.ret_1m'),
       json_extract(value, '$.ret_1y'),
       json_extract(value, '$.updated_at')
FROM json_each(?1)
WHERE true
ON CONFLICT (scrip_code) DO UPDATE SET
       symbol             = coalesce(excluded.symbol, companies.symbol),
       company_name       = CASE WHEN excluded.company_name = excluded.scrip_code
                                 THEN companies.company_name ELSE excluded.company_name END,
       isin               = coalesce(excluded.isin, companies.isin),
       industry           = coalesce(excluded.industry, companies.industry),
       sector             = coalesce(excluded.sector, companies.sector),
       market_cap_cr      = coalesce(excluded.market_cap_cr, companies.market_cap_cr),
       size_category      = coalesce(excluded.size_category, companies.size_category),
       shares_outstanding = coalesce(excluded.shares_outstanding, companies.shares_outstanding),
       shares_updated_at  = coalesce(excluded.shares_updated_at, companies.shares_updated_at),
       last_price         = coalesce(excluded.last_price, companies.last_price),
       price_date         = coalesce(excluded.price_date, companies.price_date),
       ret_1w             = coalesce(excluded.ret_1w, companies.ret_1w),
       ret_1m             = coalesce(excluded.ret_1m, companies.ret_1m),
       ret_1y             = coalesce(excluded.ret_1y, companies.ret_1y),
       updated_at         = coalesce(excluded.updated_at, companies.updated_at);
