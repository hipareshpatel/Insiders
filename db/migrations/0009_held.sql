-- A card whose numbers could not be verified is held back from the feed instead of published with a
-- warning. Until now a card that failed its checks, went for a second opinion and still failed was
-- published anyway, marked "Unverified", so that a material filing was never hidden. Measured on the
-- rebuild, that was 117 of 456 cards: 26% of the feed stated figures the code had already found wanting,
-- and a card the checks flagged was judged WRONG 52% of the time against 21% for a clean one (audit
-- round 1). For a feed meant to run unattended the trade is the wrong way round, so such a card is now
-- kept out of the public feed and left for review.
--
-- The row is still written in full: the defect digest, the audit export and the System page all read it,
-- and holding is reversible from the data alone once the card is corrected.
ALTER TABLE cards ADD COLUMN held INTEGER NOT NULL DEFAULT 0;

-- The feed walks filed_at newest first; this is that index restricted to what the feed may show, so the
-- held rows cost the reader nothing to skip.
CREATE INDEX IF NOT EXISTS idx_cards_feed_live ON cards (filed_at DESC) WHERE held = 0;

-- And the reverse, for the review queue.
CREATE INDEX IF NOT EXISTS idx_cards_held ON cards (filed_at DESC) WHERE held = 1;

-- Cards written before this column: hold the ones whose own review block already says the second
-- opinion could not resolve them (117 of 456 on the rebuild).
UPDATE cards SET held = 1 WHERE json_extract(card_json, '$.review.status') = 'UNRESOLVED';
