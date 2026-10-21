-- ?1 = from date, ?2 = to date (inclusive), ?3 = limit.
-- Filings in a window still waiting to be read, counted up to the limit (the scan stops there): backfill discovers a
-- further day of history only while this is under its limit, so discovery (about 5 rows written a filing) cannot run
-- weeks ahead of the analysis and spend the day's free D1 writes on filings that wait. Uses idx_filings_queue.
SELECT count(*) AS n FROM (SELECT 1 FROM filings
                            WHERE status = 'PENDING' AND filed_at >= ?1 AND filed_at < date(?2, '+1 day')
                            LIMIT ?3);
