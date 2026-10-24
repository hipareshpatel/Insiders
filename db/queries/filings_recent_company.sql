-- ?1 = scrip code, ?2 = from filed_at (inclusive), ?3 = to filed_at (exclusive), ?4 = limit. The window spans both sides of the
-- filing being checked: a repeat analysed before its original (listed late, or retried) still counts.
-- A company's recently finished filings, newest first, for the duplicate check (index idx_filings_scrip).
SELECT news_id, filed_at
  FROM filings
 WHERE scrip_code = ?1
   AND status IN ('ANALYZED', 'NOT_MATERIAL')
   AND filed_at >= ?2 AND filed_at < ?3
 ORDER BY filed_at DESC
 LIMIT ?4;
