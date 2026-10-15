-- Loop 1 and write savings.
-- The cards search index was rewritten on every update of a card (two FTS writes plus its index
-- pages), including updates that touch no searched column, such as the Loop 1 price reaction.
-- Rebuild the trigger so it fires only when a searched column changes, as companies_au does.
DROP TRIGGER IF EXISTS cards_au;
CREATE TRIGGER cards_au AFTER UPDATE OF headline, company_name, symbol ON cards
WHEN old.headline IS NOT new.headline OR old.company_name IS NOT new.company_name OR old.symbol IS NOT new.symbol
BEGIN
    INSERT INTO cards_fts (cards_fts, rowid, headline, company_name, symbol)
    VALUES ('delete', old.rowid, old.headline, old.company_name, old.symbol);
    INSERT INTO cards_fts (rowid, headline, company_name, symbol)
    VALUES (new.rowid, new.headline, new.company_name, new.symbol);
END;
