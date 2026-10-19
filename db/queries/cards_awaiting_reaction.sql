-- ?1 = from filed_at, ?2 = until filed_at, ?3 = keyset filed_at, ?4 = keyset news_id, ?5 = limit.
-- Cards whose Loop 1 price reaction (T+1..T+5) is missing or incomplete; a range seek on idx_cards_feed.
SELECT news_id, scrip_code, filed_at, impact_level, sector, event_category, post_event_return_json
  FROM cards
 WHERE filed_at >= ?1 AND filed_at < ?2
   AND (filed_at > ?3 OR (filed_at = ?3 AND news_id > ?4))
   AND (post_event_return_json IS NULL OR json_extract(post_event_return_json, '$.complete') = 0)
 ORDER BY filed_at, news_id
 LIMIT ?5;
