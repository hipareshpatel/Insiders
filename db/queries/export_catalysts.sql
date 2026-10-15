-- ?1 = earliest event date to copy, ?2 = id after which to continue, ?3 = limit. sync-to-cloud.
SELECT id, scrip_code, company_name, symbol, event_type, event_date, description, source_news_id, created_at
  FROM catalysts
 WHERE event_date >= ?1 AND id > ?2
 ORDER BY id
 LIMIT ?3;
