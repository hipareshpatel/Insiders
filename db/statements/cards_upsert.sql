-- ?1 = JSON array of card rows; `card` is the full card object.
-- A standing owner verdict (card_verdicts, O11) outlives a re-run, read here so it costs no extra statement:
-- WRONG keeps the new version held, with the owner's note as its hold line in review.held (until the owner looks
-- again); RIGHT releases it only when the new version is the card the owner approved (same headline as the judged
-- snapshot), else the checks decide, so an approval of an old version never publishes a different card the checks
-- held. MINOR leaves it to the checks, as in the Worker (owner.ts). cards_apply_verdicts.sql applies the same rule
-- to the stored cards.
INSERT INTO cards (news_id, scrip_code, symbol, company_name, filing_date, filed_at, sector,
                   event_category, impact_level, headline, grounding_score, needs_review,
                   memory_complete, card_json, pdf_url, model, created_at, market_session,
                   actionability_score, is_actionable_signal, post_event_return_json, held)
SELECT json_extract(value, '$.news_id'),
       json_extract(value, '$.scrip_code'),
       json_extract(value, '$.symbol'),
       json_extract(value, '$.company_name'),
       json_extract(value, '$.filing_date'),
       json_extract(value, '$.filed_at'),
       json_extract(value, '$.sector'),
       json_extract(value, '$.event_category'),
       json_extract(value, '$.impact_level'),
       json_extract(value, '$.headline'),
       json_extract(value, '$.grounding_score'),
       coalesce(json_extract(value, '$.needs_review'), 0),
       coalesce(json_extract(value, '$.memory_complete'), 1),
       CASE WHEN v.verdict = 'WRONG' THEN
            CASE WHEN json_type(json_extract(value, '$.card'), '$.review') = 'object'
                 THEN json_set(json_extract(value, '$.card'), '$.review.held', json((
                        SELECT json_group_array(h) FROM (
                          SELECT o.value AS h FROM json_each(json_extract(j.value, '$.card'), '$.review.held') AS o
                           WHERE instr(o.value, 'Held by the owner (Wrong): ') <> 1
                          UNION ALL
                          SELECT 'Held by the owner (Wrong): ' || coalesce(nullif(trim(v.note, ' ' || char(9, 10, 13)), ''), 'no note yet')))))
                 ELSE json_set(json_extract(value, '$.card'), '$.review', json_object('status', 'HELD', 'held',
                        json_array('Held by the owner (Wrong): ' || coalesce(nullif(trim(v.note, ' ' || char(9, 10, 13)), ''), 'no note yet'))))
            END
            ELSE json(json_extract(value, '$.card')) END,
       json_extract(value, '$.pdf_url'),
       json_extract(value, '$.model'),
       json_extract(value, '$.created_at'),
       json_extract(value, '$.market_session'),
       coalesce(json_extract(value, '$.actionability_score'), 0),
       coalesce(json_extract(value, '$.is_actionable_signal'), 0),
       json_extract(value, '$.post_event_return_json'),
       CASE WHEN v.verdict = 'WRONG' THEN 1
            WHEN v.verdict = 'RIGHT'
             AND json_extract(value, '$.headline') = json_extract(v.card_json_snapshot, '$.headline') THEN 0
            ELSE coalesce(json_extract(value, '$.held'), 0) END
FROM json_each(?1) AS j LEFT JOIN card_verdicts AS v ON v.news_id = json_extract(value, '$.news_id')
WHERE true
ON CONFLICT (news_id) DO UPDATE SET
       symbol          = excluded.symbol,
       company_name    = excluded.company_name,
       sector          = excluded.sector,
       event_category  = excluded.event_category,
       impact_level    = excluded.impact_level,
       headline        = excluded.headline,
       grounding_score = excluded.grounding_score,
       needs_review    = excluded.needs_review,
       memory_complete = excluded.memory_complete,
       card_json       = excluded.card_json,
       pdf_url         = excluded.pdf_url,
       model           = excluded.model,
       created_at      = excluded.created_at,
       market_session  = excluded.market_session,
       actionability_score  = excluded.actionability_score,
       is_actionable_signal = excluded.is_actionable_signal,
       held            = excluded.held,
       -- a re-analysis keeps the measured price reaction (Loop 1); sync-to-cloud carries it over
       post_event_return_json = coalesce(excluded.post_event_return_json, cards.post_event_return_json);
