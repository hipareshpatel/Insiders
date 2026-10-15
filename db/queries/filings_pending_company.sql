-- ?1 = scrip code, ?2 = from date, ?3 = to date, ?4 = max attempts, ?5 = limit.
-- One company's unanalysed filings, oldest first (index idx_filings_scrip).
SELECT news_id, scrip_code, company_name, symbol, headline, subject, category, subcategory, filed_at,
       filing_date, pdf_url, xbrl_url, status, route, event_type, reason, attempts
  FROM filings
 WHERE scrip_code = ?1
   AND (status = 'PENDING' OR (status = 'FAILED' AND attempts < ?4))
   AND filing_date BETWEEN ?2 AND ?3
 ORDER BY filed_at ASC, news_id ASC
 LIMIT ?5;
