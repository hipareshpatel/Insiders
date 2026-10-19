-- ?1 = earliest filed_at (YYYY-MM-DD), ?2 = limit. Results cards of NSE filings from the last days, with the XBRL file
-- each was made from (null: from the PDF alone): event_catchup.results_catch_up reads a card again when its quarter's
-- file lands or a revision replaces the one it used. A filing already back in the queue is left to it.
SELECT c.news_id, c.scrip_code, coalesce(nullif(co.symbol, ''), f.symbol) AS symbol, c.filed_at, c.filing_date,
       json_extract(c.card_json, '$.xbrl.url') AS xbrl_url, json_extract(c.card_json, '$.xbrl.period') AS period,
       json_extract(c.card_json, '$.xbrl.basis') AS basis, json_extract(c.card_json, '$.xbrl_seen') AS seen
  FROM cards c
  JOIN filings f ON f.news_id = c.news_id
  LEFT JOIN companies co ON co.scrip_code = c.scrip_code
 WHERE c.filed_at >= ?1 AND c.news_id LIKE 'nse-%'
   AND c.event_category = 'RESULTS'
   AND f.status = 'ANALYZED'
 ORDER BY c.filed_at, c.news_id
 LIMIT ?2;
