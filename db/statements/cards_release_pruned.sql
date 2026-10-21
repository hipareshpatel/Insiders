-- ?1 = JSON array of {news_id, card_json}. A held card whose only faults were points their quote did not carry,
-- published without those points (release-pruned, pipeline/src/bse_intel/prune.py; owner, 2026-10-21: "Needs review
-- · 475"). Only a card still held is written, so a re-run or an owner's verdict since is never overwritten.
-- (Nothing may follow the final semicolon: D1 reads it as a second statement and refuses parameters.)
UPDATE cards SET held = 0, needs_review = 0,
       card_json = (SELECT json_extract(j.value, '$.card_json') FROM json_each(?1) AS j
                     WHERE json_extract(j.value, '$.news_id') = cards.news_id)
 WHERE held = 1
   AND news_id IN (SELECT json_extract(j.value, '$.news_id') FROM json_each(?1) AS j)
   AND NOT EXISTS (SELECT 1 FROM card_verdicts AS v WHERE v.news_id = cards.news_id AND v.verdict = 'WRONG');
