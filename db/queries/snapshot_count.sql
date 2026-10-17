-- ?1 = from (YYYY-MM-DD). Cards in the default window, capped like the feed's page count.
SELECT count(*) AS n FROM (SELECT 1 FROM cards WHERE held = 0 AND filed_at >= ?1 LIMIT 2000);
