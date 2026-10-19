-- ?1 = JSON array of {news_id}. The card of a filing that was read again and now ends without one (not
-- material, or a duplicate of another filing's card): cards_upsert replaces a card but never removes one.
-- (Nothing may follow the final semicolon: D1 reads it as a second statement and refuses parameters.)
DELETE FROM cards
 WHERE news_id IN (SELECT json_extract(j.value, '$.news_id') FROM json_each(?1) AS j);
