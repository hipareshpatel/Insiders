-- ?1 = since filed_at, ?2 = minimum cards. Loop 1 false-positive dampener: average T+3 excess return
-- and volume multiple of HIGH-impact cards per (sector, event category); range seek on idx_cards_impact.
SELECT sector, event_category, count(*) AS n,
       round(avg(json_extract(post_event_return_json, '$.t3.excess_pct')), 2) AS avg_t3_excess,
       round(avg(json_extract(post_event_return_json, '$.t3.rvol')), 2) AS avg_t3_rvol
  FROM cards
 WHERE impact_level = 'HIGH' AND filed_at >= ?1
   AND json_extract(post_event_return_json, '$.t3.excess_pct') IS NOT NULL
 GROUP BY sector, event_category
HAVING count(*) >= ?2;
