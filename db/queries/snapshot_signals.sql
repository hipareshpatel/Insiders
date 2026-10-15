-- ?1 = from (YYYY-MM-DD). Top Signals for the R2 snapshot (partial index idx_cards_signals).
-- Columns must match CARD_COLUMNS in web/worker/public.ts.
SELECT c.news_id, c.scrip_code, c.symbol, c.company_name, c.filing_date, c.filed_at, c.sector,
       c.event_category, c.impact_level, c.headline, c.grounding_score, c.needs_review,
       c.memory_complete, c.card_json, c.pdf_url, c.market_session, c.actionability_score, c.is_actionable_signal, c.post_event_return_json,
       co.market_cap_cr, co.size_category, co.last_price, co.ret_1w, co.ret_1m, co.ret_1y,
       co.median_turnover_cr, co.credibility_score, co.watchlist, co.bse_group, co.technicals_json
  FROM cards c LEFT JOIN companies co ON co.scrip_code = c.scrip_code
 WHERE c.is_actionable_signal = 1 AND c.filed_at >= ?1
 ORDER BY c.actionability_score DESC, c.filed_at DESC
 LIMIT 50;
