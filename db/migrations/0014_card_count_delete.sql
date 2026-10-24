-- companies.card_count went up for every new card (cards_ai) and never came down: cards_ad only cleared the search
-- row, so a card removed by cards_delete (a re-read filing that ends without one, a duplicate merged away) still
-- counted, and a company whose every card was removed stayed on the companies list (card_count > 0) with an empty
-- page (survey, 24 Oct 2026). The trigger fires on a delete only, so it adds no writes to the daily upserts.
--
-- card_count still counts held cards as well as published ones: counting published only would need a trigger on
-- every held flip, and companies_for_market.sql picks the companies to price by card_count > 0, held cards included.
DROP TRIGGER IF EXISTS cards_ad;
CREATE TRIGGER IF NOT EXISTS cards_ad AFTER DELETE ON cards BEGIN
    INSERT INTO cards_fts (cards_fts, rowid, headline, company_name, symbol)
    VALUES ('delete', old.rowid, old.headline, old.company_name, old.symbol);
    UPDATE companies SET card_count = max(card_count - 1, 0) WHERE scrip_code = old.scrip_code;
END;

-- One recount for the deletes before this: only the rows that differ are written (one seek on idx_cards_scrip each).
UPDATE companies
   SET card_count = (SELECT count(*) FROM cards c WHERE c.scrip_code = companies.scrip_code)
 WHERE card_count <> (SELECT count(*) FROM cards c WHERE c.scrip_code = companies.scrip_code);
