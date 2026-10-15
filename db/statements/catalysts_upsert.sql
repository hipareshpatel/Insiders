-- ?1 = JSON array of catalysts.
INSERT INTO catalysts (id, scrip_code, company_name, symbol, event_type, event_date,
                       description, source_news_id, created_at)
SELECT json_extract(value, '$.id'),
       json_extract(value, '$.scrip_code'),
       json_extract(value, '$.company_name'),
       json_extract(value, '$.symbol'),
       json_extract(value, '$.event_type'),
       json_extract(value, '$.event_date'),
       json_extract(value, '$.description'),
       json_extract(value, '$.source_news_id'),
       json_extract(value, '$.created_at')
FROM json_each(?1)
WHERE true
ON CONFLICT (id) DO UPDATE SET
       description    = excluded.description,
       source_news_id = excluded.source_news_id
 -- Discovery re-reads today's filings on every run; an unchanged catalyst costs no write.
 WHERE catalysts.description IS NOT excluded.description
    OR catalysts.source_news_id IS NOT excluded.source_news_id;
