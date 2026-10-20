-- ?1 = JSON array of the verdicts to apply ("WRONG", "RIGHT"). Applies the owner's standing verdicts to the stored
-- cards once (maintenance.yml apply-verdicts): verdicts saved before they acted on the card (O11, 2026-10-20) never
-- held or released it. The rule is cards_upsert.sql's: WRONG holds, with the note as the owner's hold line in
-- review.held; RIGHT releases only the card the owner approved (same headline as the judged snapshot; the Worker
-- already took any owner's hold line out when the verdict was saved). No AI. Idempotent: a card already as its
-- verdict says is not written again.
UPDATE cards SET
       held = CASE WHEN v.verdict = 'WRONG' THEN 1 ELSE 0 END,
       card_json = CASE WHEN v.verdict = 'RIGHT' THEN cards.card_json
            WHEN json_type(cards.card_json, '$.review') = 'object'
            THEN json_set(cards.card_json, '$.review.held', json((
                   SELECT json_group_array(h) FROM (
                     SELECT o.value AS h FROM json_each(cards.card_json, '$.review.held') AS o
                      WHERE instr(o.value, 'Held by the owner (Wrong): ') <> 1
                     UNION ALL
                     SELECT 'Held by the owner (Wrong): ' || coalesce(nullif(trim(v.note, ' ' || char(9, 10, 13)), ''), 'no note yet')))))
            ELSE json_set(cards.card_json, '$.review', json_object('status', 'HELD', 'held',
                   json_array('Held by the owner (Wrong): ' || coalesce(nullif(trim(v.note, ' ' || char(9, 10, 13)), ''), 'no note yet'))))
       END
  FROM card_verdicts AS v
 WHERE v.news_id = cards.news_id
   AND v.verdict IN (SELECT value FROM json_each(?1))
   AND CASE WHEN v.verdict = 'WRONG'
            THEN cards.held = 0 OR NOT EXISTS (
                   SELECT 1 FROM json_each(cards.card_json, '$.review.held') AS o
                    WHERE o.value = 'Held by the owner (Wrong): ' || coalesce(nullif(trim(v.note, ' ' || char(9, 10, 13)), ''), 'no note yet'))
            ELSE cards.held = 1 AND cards.headline = json_extract(v.card_json_snapshot, '$.headline')
       END;
