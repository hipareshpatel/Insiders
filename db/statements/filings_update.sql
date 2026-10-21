-- ?1 = JSON array of {news_id, status, event_type?, reason?, last_error?, attempts?, updated_at}.
-- attempts is the new total, not an increment, so a retried request cannot count twice.
-- A filing already as the row says is not written again (owner, 2026-10-21: D1's free 100,000 rows written a day; a
-- status write also rewrites the filing's three ledger indexes): a run cut short re-sends PENDING for filings it never
-- reached, a retried request re-sends the same row, and updated_at alone is no change. (Nothing may follow the final
-- semicolon: D1 reads it as a second statement and refuses parameters.)
UPDATE filings
   SET status     = json_extract(j.value, '$.status'),
       event_type = coalesce(json_extract(j.value, '$.event_type'), filings.event_type),
       reason     = coalesce(json_extract(j.value, '$.reason'), filings.reason),
       last_error = json_extract(j.value, '$.last_error'),
       attempts   = coalesce(json_extract(j.value, '$.attempts'), filings.attempts),
       updated_at = json_extract(j.value, '$.updated_at')
  FROM json_each(?1) AS j
 WHERE filings.news_id = json_extract(j.value, '$.news_id')
   AND (filings.status IS NOT json_extract(j.value, '$.status')
        OR filings.event_type IS NOT coalesce(json_extract(j.value, '$.event_type'), filings.event_type)
        OR filings.reason IS NOT coalesce(json_extract(j.value, '$.reason'), filings.reason)
        OR filings.last_error IS NOT json_extract(j.value, '$.last_error')
        OR filings.attempts IS NOT coalesce(json_extract(j.value, '$.attempts'), filings.attempts));
