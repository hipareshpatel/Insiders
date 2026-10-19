-- ?1 = JSON array of full ledger rows (sync-to-cloud). Unlike filings_discover, the status and
-- attempts are copied too; a row the destination already holds is updated.
INSERT INTO filings (news_id, scrip_code, company_name, symbol, headline, subject, category, subcategory,
                     filed_at, filing_date, pdf_url, xbrl_url, status, route, event_type, reason, attempts, last_error, updated_at)
SELECT json_extract(value, '$.news_id'), json_extract(value, '$.scrip_code'), json_extract(value, '$.company_name'),
       json_extract(value, '$.symbol'), json_extract(value, '$.headline'), json_extract(value, '$.subject'),
       json_extract(value, '$.category'), json_extract(value, '$.subcategory'), json_extract(value, '$.filed_at'),
       json_extract(value, '$.filing_date'), json_extract(value, '$.pdf_url'), json_extract(value, '$.xbrl_url'), json_extract(value, '$.status'),
       coalesce(json_extract(value, '$.route'), 'NONE'), json_extract(value, '$.event_type'),
       json_extract(value, '$.reason'), coalesce(json_extract(value, '$.attempts'), 0),
       json_extract(value, '$.last_error'), json_extract(value, '$.updated_at')
FROM json_each(?1)
WHERE true
ON CONFLICT (news_id) DO UPDATE SET
       status = excluded.status, event_type = excluded.event_type, reason = excluded.reason,
       attempts = excluded.attempts, last_error = excluded.last_error, updated_at = excluded.updated_at
 WHERE filings.status IS NOT excluded.status OR filings.attempts IS NOT excluded.attempts;
