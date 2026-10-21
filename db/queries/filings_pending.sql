-- ?1 = from date, ?2 = to date (YYYY-MM-DD, inclusive), ?3 = max attempts, ?4 = limit,
-- ?5/?6 = (filed_at, news_id) of the last row already returned ('' and '' for the first page).
-- Oldest first, so dossier memory is built in chronological order. Used for the live window;
-- backfill goes company by company (backfill_companies + filings_pending_company).
-- Two range seeks on idx_filings_queue (status, filed_at): D1 keeps no planner statistics, and an
-- OR over status would read every PENDING and FAILED row of every date. Each seek starts at the last row returned
-- (max(?1, ?5)): the keyset OR alone cannot bound the index range, so every page re-read the pages before it (79
-- calls read 924,232 rows on 20-21 Oct 2026, when D1's free 5M rows read a day ran out).
SELECT news_id, scrip_code, company_name, symbol, headline, subject, category, subcategory, filed_at,
       filing_date, pdf_url, xbrl_url, status, route, event_type, reason, attempts, last_error
  FROM filings
 WHERE status = 'PENDING' AND filed_at >= max(?1, ?5) AND filed_at < date(?2, '+1 day')
   AND (filed_at > ?5 OR (filed_at = ?5 AND news_id > ?6))
UNION ALL
SELECT news_id, scrip_code, company_name, symbol, headline, subject, category, subcategory, filed_at,
       filing_date, pdf_url, xbrl_url, status, route, event_type, reason, attempts, last_error
  FROM filings
 WHERE status = 'FAILED' AND attempts < ?3 AND filed_at >= max(?1, ?5) AND filed_at < date(?2, '+1 day')
   AND (filed_at > ?5 OR (filed_at = ?5 AND news_id > ?6))
 ORDER BY filed_at, news_id
 LIMIT ?4;
