-- ?1 = date from which every filing is copied (recent days, so live discovery knows them),
-- ?2 = news id after which to continue, ?3 = limit. Older filings are copied only while still
-- queued (PENDING / FAILED): the historical ledger stays local. sync-to-cloud.
SELECT news_id, scrip_code, company_name, symbol, headline, subject, category, subcategory, filed_at,
       filing_date, pdf_url, status, route, event_type, reason, attempts, last_error, updated_at
  FROM filings
 WHERE news_id > ?2 AND (filing_date >= ?1 OR status IN ('PENDING', 'FAILED'))
 ORDER BY news_id
 LIMIT ?3;
