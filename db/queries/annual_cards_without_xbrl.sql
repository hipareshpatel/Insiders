-- ?1 = earliest filed_at (YYYY-MM-DD), ?2 = limit. Annual-report cards made without the company's own XBRL
-- table (card_json.annual_xbrl), of companies with a symbol to ask NSE about, oldest first: annual_catchup.py
-- reads each again once NSE lists the year's file. `checked` is when the pipeline last read NSE's list in full
-- for the card (null: never). A filing already back in the queue is left to it. Served by idx_cards_category.
SELECT c.news_id, c.scrip_code, coalesce(nullif(co.symbol, ''), f.symbol) AS symbol, c.filed_at, c.filing_date,
       c.held, f.headline, f.subject, json_extract(c.card_json, '$.annual_xbrl_checked') AS checked
  FROM cards c
  JOIN filings f ON f.news_id = c.news_id
  LEFT JOIN companies co ON co.scrip_code = c.scrip_code
 WHERE c.event_category = 'ANNUAL_REPORT' AND c.filed_at >= ?1
   AND f.status = 'ANALYZED'
   AND json_extract(c.card_json, '$.annual_xbrl') IS NULL
   AND coalesce(nullif(co.symbol, ''), f.symbol, '') <> ''
 ORDER BY c.filed_at, c.news_id
 LIMIT ?2;
