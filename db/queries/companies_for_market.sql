-- ?1 = limit. Companies worth enriching with prices: those with cards, most recent first.
SELECT scrip_code, symbol, shares_outstanding, shares_updated_at, price_date
  FROM companies
 WHERE card_count > 0
 ORDER BY last_card_at DESC
 LIMIT ?1;
