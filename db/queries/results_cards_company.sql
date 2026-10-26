-- ?1 = scrip code. One company's results cards with the quarter each was made from (card_json.xbrl.period; null for a card from
-- the PDF alone), newest first: the screener cross-check's referee finds the official results text of a quarter with it
-- (text/<news_id>.json.gz in R2). Read only.
SELECT c.news_id, c.filed_at, json_extract(c.card_json, '$.xbrl.period') AS period,
       json_extract(c.card_json, '$.xbrl.basis') AS basis
  FROM cards c
 WHERE c.scrip_code = ?1
   AND c.event_category = 'RESULTS'
 ORDER BY c.filed_at DESC
 LIMIT 60;
