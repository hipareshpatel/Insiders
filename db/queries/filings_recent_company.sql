-- ?1 = scrip code, ?2 = from filed_at (inclusive), ?3 = to filed_at (exclusive), ?4 = limit.
-- A company's recently finished filings, newest first, for the duplicate check (index idx_filings_scrip).
SELECT news_id, filed_at
  FROM filings
 WHERE scrip_code = ?1
   AND status IN ('ANALYZED', 'NOT_MATERIAL')
   AND filed_at >= ?2 AND filed_at < ?3
 ORDER BY filed_at DESC
 LIMIT ?4;
