-- ?1 = filed on or after (ISO), ?2 = limit. Held cards of the live window, newest first, for the end-of-day sweep
-- (pipeline/src/bse_intel/sweep.py): their card_json says why each was held.
SELECT news_id, filed_at, card_json FROM cards WHERE held = 1 AND filed_at >= ?1 ORDER BY filed_at DESC LIMIT ?2;
