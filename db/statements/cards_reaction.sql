-- ?1 = JSON array of {news_id, reaction}. Loop 1 writes a card's post-event price reaction; an
-- unchanged reaction costs no write.
UPDATE cards
   SET post_event_return_json = json(json_extract(j.value, '$.reaction'))
  FROM json_each(?1) AS j
 WHERE cards.news_id = json_extract(j.value, '$.news_id')
   AND cards.post_event_return_json IS NOT json(json_extract(j.value, '$.reaction'));
