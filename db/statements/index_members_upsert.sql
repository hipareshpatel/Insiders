-- ?1 = JSON array of {index_id, isin, symbol, company_name, as_of}: the constituents NSE lists today.
INSERT INTO index_members (index_id, isin, symbol, company_name, as_of)
SELECT json_extract(value, '$.index_id'), json_extract(value, '$.isin'), json_extract(value, '$.symbol'),
       json_extract(value, '$.company_name'), json_extract(value, '$.as_of')
FROM json_each(?1)
WHERE true
ON CONFLICT (index_id, isin) DO UPDATE SET
       symbol = excluded.symbol, company_name = excluded.company_name, as_of = excluded.as_of;
