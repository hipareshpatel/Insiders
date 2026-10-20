-- ?1 = from date (YYYY-MM-DD), ?2 = max attempts, ?3 = limit.
-- Filings that used every attempt (status FAILED, attempts >= ?2) filed on or after ?1, newest first: the ones no
-- run will try again until they are requeued (requeue.py). A range seek on idx_filings_queue (status, filed_at).
SELECT news_id, scrip_code, company_name, symbol, headline, filed_at, filing_date, event_type, attempts, last_error,
       updated_at
  FROM filings
 WHERE status = 'FAILED' AND filed_at >= ?1 AND attempts >= ?2
 ORDER BY filed_at DESC
 LIMIT ?3;
