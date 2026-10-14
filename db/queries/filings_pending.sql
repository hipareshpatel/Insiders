-- ?1 = from date, ?2 = to date (YYYY-MM-DD, inclusive), ?3 = max attempts, ?4 = limit.
-- Oldest first, so dossier memory is built in chronological order. Used for the live window;
-- backfill goes company by company (backfill_companies + filings_pending_company).
SELECT news_id, scrip_code, company_name, headline, category, subcategory, filed_at,
       filing_date, pdf_url, status, route, event_type, reason, attempts
  FROM filings
 WHERE (status = 'PENDING' OR (status = 'FAILED' AND attempts < ?3))
   AND filing_date BETWEEN ?1 AND ?2
 ORDER BY filed_at ASC, news_id ASC
 LIMIT ?4;
