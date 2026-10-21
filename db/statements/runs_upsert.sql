-- ?1 = JSON array of pipeline runs.
INSERT INTO pipeline_runs (run_id, mode, started_at, finished_at, status, stats_json, error)
SELECT json_extract(value, '$.run_id'),
       json_extract(value, '$.mode'),
       json_extract(value, '$.started_at'),
       json_extract(value, '$.finished_at'),
       json_extract(value, '$.status'),
       json(coalesce(json_extract(value, '$.stats'), '{}')),
       json_extract(value, '$.error')
FROM json_each(?1)
WHERE true
ON CONFLICT (run_id) DO UPDATE SET
       finished_at = excluded.finished_at,
       status      = excluded.status,
       stats_json  = excluded.stats_json,
       error       = excluded.error
 -- a retried request (a timeout after D1 committed) writes nothing the second time
 WHERE pipeline_runs.finished_at IS NOT excluded.finished_at OR pipeline_runs.status IS NOT excluded.status
    OR pipeline_runs.stats_json IS NOT excluded.stats_json OR pipeline_runs.error IS NOT excluded.error;
