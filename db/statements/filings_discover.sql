-- ?1 = JSON array of filings. New filings are inserted; already-known
-- filings are left untouched (their status may have advanced).
INSERT INTO filings (news_id, scrip_code, company_name, headline, category, subcategory,
                     filed_at, filing_date, pdf_url, status, route, event_type, reason, updated_at)
SELECT json_extract(value, '$.news_id'),
       json_extract(value, '$.scrip_code'),
       json_extract(value, '$.company_name'),
       json_extract(value, '$.headline'),
       json_extract(value, '$.category'),
       json_extract(value, '$.subcategory'),
       json_extract(value, '$.filed_at'),
       json_extract(value, '$.filing_date'),
       json_extract(value, '$.pdf_url'),
       json_extract(value, '$.status'),
       coalesce(json_extract(value, '$.route'), 'NONE'),
       json_extract(value, '$.event_type'),
       json_extract(value, '$.reason'),
       json_extract(value, '$.updated_at')
FROM json_each(?1)
WHERE true
ON CONFLICT (news_id) DO NOTHING;
