-- ?1 = sector, ?2 = event category, ?3 = rating (STARRED | NOISE), ?4 = limit.
-- The owner's rated cards for this kind of filing (blueprint Loop 3): starred ones become
-- examples to follow in the Pass 2 prompt, noise ones examples to avoid.
SELECT news_id, card_json_snapshot, user_note
  FROM card_feedback
 WHERE sector IS ?1 AND event_category = ?2 AND rating = ?3
 ORDER BY created_at DESC
 LIMIT ?4;
