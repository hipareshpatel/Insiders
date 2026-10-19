-- The owner's verdict on a card, for the private launch (owner, 2026-10-19: "i want you to highlight cards which
-- are held so i can also review and give feedback"). Separate from card_feedback, which holds Star / Noise (what is
-- worth showing); this holds whether the card is right, in the audit's own words, so the owner's reviews can be
-- tallied like a blind review round and each WRONG traced to its error class.
CREATE TABLE IF NOT EXISTS card_verdicts (
    news_id            TEXT PRIMARY KEY,
    scrip_code         TEXT NOT NULL,
    event_category     TEXT,
    verdict            TEXT NOT NULL,       -- RIGHT | MINOR | WRONG
    note               TEXT,
    held               INTEGER NOT NULL,    -- whether the card was held when the owner judged it
    card_json_snapshot TEXT,                -- the card as the owner saw it (a re-run replaces the card)
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_verdicts_recent ON card_verdicts (created_at DESC);
