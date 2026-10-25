-- ?1 = JSON array of filings. New filings are inserted; already-known filings are left untouched (their status may
-- have advanced), unless the exchange now serves another attachment under the same filing: discovery sends such a
-- filing again only when the attachment's file name changed (pipeline._record), and it is queued to be read again
-- with every attempt. Same attachment, no write. (Nothing may follow the final semicolon: D1 reads it as a second
-- statement and refuses parameters.)
INSERT INTO filings (news_id, scrip_code, company_name, symbol, headline, subject, category, subcategory,
                     filed_at, filing_date, pdf_url, xbrl_url, status, route, event_type, reason, updated_at)
SELECT json_extract(value, '$.news_id'),
       json_extract(value, '$.scrip_code'),
       json_extract(value, '$.company_name'),
       json_extract(value, '$.symbol'),
       json_extract(value, '$.headline'),
       json_extract(value, '$.subject'),
       json_extract(value, '$.category'),
       json_extract(value, '$.subcategory'),
       json_extract(value, '$.filed_at'),
       json_extract(value, '$.filing_date'),
       json_extract(value, '$.pdf_url'),
       json_extract(value, '$.xbrl_url'),
       json_extract(value, '$.status'),
       coalesce(json_extract(value, '$.route'), 'NONE'),
       json_extract(value, '$.event_type'),
       json_extract(value, '$.reason'),
       json_extract(value, '$.updated_at')
FROM json_each(?1)
WHERE true
ON CONFLICT (news_id) DO UPDATE SET
       pdf_url    = excluded.pdf_url,
       xbrl_url   = coalesce(excluded.xbrl_url, filings.xbrl_url),
       status     = 'PENDING',
       attempts   = 0,
       last_error = 'attachment changed: ' || coalesce(filings.pdf_url, ''),
       updated_at = excluded.updated_at
 -- the file name after the last '/': BSE moves an attachment from AttachLive/ to AttachHis/ under the same name
 -- or the filing had no file and now has one (NSE added it after listing the filing; owner, 25 Oct 2026)
 WHERE excluded.pdf_url IS NOT NULL AND (filings.pdf_url IS NULL OR filings.pdf_url = ''
   OR substr(filings.pdf_url, length(rtrim(filings.pdf_url, replace(filings.pdf_url, '/', ''))) + 1)
       IS NOT substr(excluded.pdf_url, length(rtrim(excluded.pdf_url, replace(excluded.pdf_url, '/', ''))) + 1));
