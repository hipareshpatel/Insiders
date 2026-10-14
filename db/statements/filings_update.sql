-- ?1 = JSON array of {news_id, status, event_type?, reason?, last_error?, attempt_inc?, updated_at}
UPDATE filings
   SET status     = json_extract(j.value, '$.status'),
       event_type = coalesce(json_extract(j.value, '$.event_type'), filings.event_type),
       reason     = coalesce(json_extract(j.value, '$.reason'), filings.reason),
       last_error = json_extract(j.value, '$.last_error'),
       attempts   = filings.attempts + coalesce(json_extract(j.value, '$.attempt_inc'), 0),
       updated_at = json_extract(j.value, '$.updated_at')
  FROM json_each(?1) AS j
 WHERE filings.news_id = json_extract(j.value, '$.news_id');
