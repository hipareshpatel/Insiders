-- ?1 = from date, ?2 = to date (inclusive), ?3 = max attempts.
-- 1 while any filing in the window is still to analyse. Stops at the first match.
SELECT EXISTS (SELECT 1 FROM filings
                WHERE status = 'PENDING' AND filed_at >= ?1 AND filed_at < date(?2, '+1 day'))
    OR EXISTS (SELECT 1 FROM filings
                WHERE status = 'FAILED' AND attempts < ?3 AND filed_at >= ?1 AND filed_at < date(?2, '+1 day'))
       AS remaining;
