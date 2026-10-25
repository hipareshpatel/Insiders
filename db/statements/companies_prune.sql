-- ?1 = JSON array of {scrip_code}. prune-companies --apply: removes company rows that are not on NSE's lists, only those
-- with no card at all and not on the owner's watchlist (the guard is here as well as in the pipeline: a card that
-- appeared after the dry run keeps its company). The search row goes with the company (the companies_ad trigger).
-- (Nothing may follow the final semicolon: D1 reads it as a second statement and refuses parameters.)
DELETE FROM companies
 WHERE scrip_code IN (SELECT json_extract(j.value, '$.scrip_code') FROM json_each(?1) AS j)
   AND watchlist = 0
   AND NOT EXISTS (SELECT 1 FROM cards WHERE cards.scrip_code = companies.scrip_code);
