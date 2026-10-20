-- ?1 = JSON array of partial company rows. Missing fields never erase
-- existing values, so filings and the market-data job can each send only
-- what they know.
INSERT INTO companies (scrip_code, symbol, company_name, isin, industry, sector, market_cap_cr,
                       size_category, shares_outstanding, shares_updated_at, last_price,
                       price_date, ret_1w, ret_1m, ret_1y, updated_at, median_turnover_cr, bse_group,
                       credibility_score, former_names_json, memory_summary_json, earliest_open_due, inflection_last_at, technicals_json)
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
       json_extract(value, '$.updated_at'),
       json_extract(value, '$.median_turnover_cr'),
       json_extract(value, '$.bse_group'),
       json_extract(value, '$.credibility_score'),
       coalesce(json_extract(value, '$.former_names_json'), '[]'),
       json_extract(value, '$.memory_summary_json'),
       json_extract(value, '$.earliest_open_due'),
       json_extract(value, '$.inflection_last_at'),
       json_extract(value, '$.technicals_json')
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
       updated_at         = coalesce(excluded.updated_at, companies.updated_at),
       median_turnover_cr = coalesce(excluded.median_turnover_cr, companies.median_turnover_cr),
       bse_group          = coalesce(excluded.bse_group, companies.bse_group),
       credibility_score  = coalesce(excluded.credibility_score, companies.credibility_score),
       -- sent with the memory summary, memory's list is the whole list (an empty one clears a refused name: Vedanta's
       -- auditor); without the summary an empty list says nothing and the stored names stay
       former_names_json  = CASE WHEN excluded.memory_summary_json IS NOT NULL THEN excluded.former_names_json
                                 WHEN excluded.former_names_json = '[]' THEN companies.former_names_json
                                 ELSE excluded.former_names_json END,
       -- the summary is sent whole with each card; due dates and trigger dates go with it
       memory_summary_json = coalesce(excluded.memory_summary_json, companies.memory_summary_json),
       earliest_open_due   = CASE WHEN excluded.memory_summary_json IS NULL THEN companies.earliest_open_due
                                  ELSE excluded.earliest_open_due END,
       inflection_last_at  = CASE WHEN excluded.memory_summary_json IS NULL THEN companies.inflection_last_at
                                  ELSE excluded.inflection_last_at END,
       technicals_json     = coalesce(excluded.technicals_json, companies.technicals_json);
