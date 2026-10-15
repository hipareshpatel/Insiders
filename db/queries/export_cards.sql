-- ?1/?2 = (filed_at, news_id) after which to continue ('' and '' to start), ?3 = limit.
-- sync-to-cloud: cards in date order, keyset-paged.
SELECT news_id, scrip_code, symbol, company_name, filing_date, filed_at, sector, event_category, impact_level,
       headline, grounding_score, needs_review, memory_complete, card_json, pdf_url, model, created_at,
       market_session, actionability_score, is_actionable_signal, post_event_return_json
  FROM cards
 WHERE filed_at > ?1 OR (filed_at = ?1 AND news_id > ?2)
 ORDER BY filed_at, news_id
 LIMIT ?3;
