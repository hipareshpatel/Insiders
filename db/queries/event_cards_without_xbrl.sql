-- ?1 = earliest filed_at (YYYY-MM-DD), ?2 = limit. Cards of NSE filings made from the PDF alone although NSE was
-- asked for their event XBRL (card_json.event_xbrl set, no file matched), newest window only: event_catchup.py reads
-- each again once a file of the company's lands that the card was not checked against (`checked`, the app ids seen).
-- A filing already back in the queue is left to it. Served by idx_cards_feed.
SELECT c.news_id, c.scrip_code, coalesce(nullif(co.symbol, ''), f.symbol) AS symbol, c.filed_at, c.filing_date,
       f.subject, f.pdf_url, json_extract(c.card_json, '$.event_xbrl.checked') AS checked
  FROM cards c
  JOIN filings f ON f.news_id = c.news_id
  LEFT JOIN companies co ON co.scrip_code = c.scrip_code
 WHERE c.filed_at >= ?1 AND c.news_id LIKE 'nse-%'
   AND f.status = 'ANALYZED'
   AND json_extract(c.card_json, '$.event_xbrl') IS NOT NULL
   AND json_extract(c.card_json, '$.event_xbrl.files[0]') IS NULL
 ORDER BY c.filed_at, c.news_id
 LIMIT ?2;
