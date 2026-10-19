-- ?1 = JSON array of {scrip_code, company_name, symbol, updated_at} seen in filings.
-- Unchanged companies are not rewritten (saves D1 row writes on every discovery).
INSERT INTO companies (scrip_code, symbol, company_name, updated_at)
SELECT json_extract(value, '$.scrip_code'),
       json_extract(value, '$.symbol'),
       json_extract(value, '$.company_name'),
       json_extract(value, '$.updated_at')
FROM json_each(?1)
WHERE true
ON CONFLICT (scrip_code) DO UPDATE SET
       company_name = excluded.company_name,
       symbol       = coalesce(excluded.symbol, companies.symbol),
       updated_at   = excluded.updated_at
 WHERE companies.company_name IS NOT excluded.company_name
    OR (excluded.symbol IS NOT NULL AND companies.symbol IS NOT excluded.symbol);
