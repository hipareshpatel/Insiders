-- ?1 = news_id. Whether a filing's card is held out of the feed: a held card does not own its results
-- quarter (D20), so another document of the quarter may make the card that is published.
SELECT held FROM cards WHERE news_id = ?1;
