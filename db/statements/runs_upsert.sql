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
       error       = excluded.error;
