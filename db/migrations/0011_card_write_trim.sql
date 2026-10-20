-- D1 writes (O8, owner 2026-10-20: 93,369 of the free 100,000 rows written in a day). D1 counts every index entry
-- and every full-text row a write touches, and a card carried nine indexes and an FTS trigger that fired on any update.
--
-- Indexes no query uses (EXPLAIN QUERY PLAN over every cards query in web/worker/, 2026-10-20):
-- - idx_cards_peer, idx_cards_impact: the feed filters with +c.event_category / +c.impact_level / +c.sector, which
--   keep them off on purpose (the date range is the selective part); the weekly impact count reads idx_cards_feed;
-- - idx_cards_signals: Top Signals takes idx_cards_feed_live (its date range), never this one;
-- - idx_cards_review, idx_cards_held: the review list's OR and its held-first order scan the table either way (a
--   hundred-odd rows at most).
-- Kept: the primary key, idx_cards_feed (owner feed, counts), idx_cards_feed_live (public feed, signals, sector bars)
-- and idx_cards_scrip (company page).
DROP INDEX IF EXISTS idx_cards_peer;
DROP INDEX IF EXISTS idx_cards_impact;
DROP INDEX IF EXISTS idx_cards_signals;
DROP INDEX IF EXISTS idx_cards_review;
DROP INDEX IF EXISTS idx_cards_held;

-- The search index holds a card's headline, company and symbol only, but it was rewritten (a delete and an insert,
-- several rows each) on every update: the nightly price reaction, a held flag, refresh-card-blocks, a re-run with the
-- same headline. Now only when one of those three changes.
DROP TRIGGER IF EXISTS cards_au;
CREATE TRIGGER IF NOT EXISTS cards_au AFTER UPDATE OF headline, company_name, symbol ON cards
WHEN old.headline IS NOT new.headline OR old.company_name IS NOT new.company_name OR old.symbol IS NOT new.symbol
BEGIN
    INSERT INTO cards_fts (cards_fts, rowid, headline, company_name, symbol)
    VALUES ('delete', old.rowid, old.headline, old.company_name, old.symbol);
    INSERT INTO cards_fts (rowid, headline, company_name, symbol)
    VALUES (new.rowid, new.headline, new.company_name, new.symbol);
END;
