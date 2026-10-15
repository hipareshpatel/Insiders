-- ?1 = from (YYYY-MM-DD), ?2 = limit. The homepage's default first page, published to R2 after each
-- run (blueprint §3.3). Columns must match CARD_COLUMNS in web/worker/public.ts.
SELECT c.news_id, c.scrip_code, c.symbol, c.company_name, c.filing_date, c.filed_at, c.sector,
       c.event_category, c.impact_level, c.headline, c.grounding_score, c.needs_review,
       c.memory_complete, c.card_json, c.pdf_url, c.market_session, c.actionability_score, c.is_actionable_signal, c.post_event_return_json,
       co.market_cap_cr, co.size_category, co.last_price, co.ret_1w, co.ret_1m, co.ret_1y,
       co.median_turnover_cr, co.credibility_score, co.watchlist, co.bse_group, co.technicals_json, co.former_names_json
  FROM cards c LEFT JOIN companies co ON co.scrip_code = c.scrip_code
 WHERE c.filed_at >= ?1
 ORDER BY c.filed_at DESC, c.news_id DESC
 LIMIT ?2;
