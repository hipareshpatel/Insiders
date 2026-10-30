-- ?1 = JSON array of {index_id, isin, symbol, company_name, valid_from}: companies that joined an index (or were there when tracking began).
INSERT INTO index_members (index_id, isin, symbol, company_name, valid_from, valid_to)
SELECT json_extract(value, '$.index_id'), json_extract(value, '$.isin'), json_extract(value, '$.symbol'),
       json_extract(value, '$.company_name'), json_extract(value, '$.valid_from'), NULL
FROM json_each(?1)
WHERE true
ON CONFLICT (index_id, isin, valid_from) DO NOTHING;
