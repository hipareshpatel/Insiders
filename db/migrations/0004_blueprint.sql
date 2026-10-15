-- Blueprint database dictionary (docs/BLUEPRINT.md §13.4): identity, tradability and credibility on
-- companies; signal scoring and market session on cards; the owner's Star/Noise feedback (Loop 3).

ALTER TABLE companies ADD COLUMN former_names_json TEXT NOT NULL DEFAULT '[]';  -- ["Novartis India Limited"]
ALTER TABLE companies ADD COLUMN bse_group TEXT;            -- A, B, T, XT, Z (+ ASM/GSM stage)
ALTER TABLE companies ADD COLUMN median_turnover_cr REAL;   -- 30-day median daily traded value
ALTER TABLE companies ADD COLUMN credibility_score REAL;    -- delivered / (delivered + breached), 0-100
ALTER TABLE companies ADD COLUMN watchlist INTEGER NOT NULL DEFAULT 0;  -- starred by the owner

ALTER TABLE cards ADD COLUMN market_session TEXT;           -- LIVE_MARKET | PRE_MARKET | AFTER_MARKET | NON_TRADING
ALTER TABLE cards ADD COLUMN actionability_score INTEGER NOT NULL DEFAULT 0;   -- 0-100, deterministic
ALTER TABLE cards ADD COLUMN is_actionable_signal INTEGER NOT NULL DEFAULT 0;  -- cleared the 4 gates
ALTER TABLE cards ADD COLUMN post_event_return_json TEXT;   -- Loop 1: T+1/T+3/T+5 excess returns

-- Top Signals view: actionable cards, best first. Only signal cards are indexed (a partial index
-- costs no write for the other 99%).
CREATE INDEX IF NOT EXISTS idx_cards_signals ON cards (actionability_score DESC, filed_at DESC)
    WHERE is_actionable_signal = 1;

CREATE TABLE IF NOT EXISTS card_feedback (
    news_id            TEXT PRIMARY KEY,
    scrip_code         TEXT NOT NULL,
    sector             TEXT,
    event_category     TEXT,
    rating             TEXT NOT NULL,       -- STARRED | NOISE
    user_note          TEXT,
    card_json_snapshot TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_lookup ON card_feedback (sector, event_category, rating, created_at DESC);
