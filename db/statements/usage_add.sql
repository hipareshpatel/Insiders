-- ?1 = JSON array of usage deltas; counters are added to the day's totals.
INSERT INTO provider_usage (day, provider, model, requests, input_tokens, output_tokens,
                            failures, rate_limited, limit_rpd, limit_tpd, last_error, updated_at)
SELECT json_extract(value, '$.day'),
       json_extract(value, '$.provider'),
       json_extract(value, '$.model'),
       coalesce(json_extract(value, '$.requests'), 0),
       coalesce(json_extract(value, '$.input_tokens'), 0),
       coalesce(json_extract(value, '$.output_tokens'), 0),
       coalesce(json_extract(value, '$.failures'), 0),
       coalesce(json_extract(value, '$.rate_limited'), 0),
       json_extract(value, '$.limit_rpd'),
       json_extract(value, '$.limit_tpd'),
       json_extract(value, '$.last_error'),
       json_extract(value, '$.updated_at')
FROM json_each(?1)
WHERE true
ON CONFLICT (day, provider, model) DO UPDATE SET
       requests      = provider_usage.requests + excluded.requests,
       input_tokens  = provider_usage.input_tokens + excluded.input_tokens,
       output_tokens = provider_usage.output_tokens + excluded.output_tokens,
       failures      = provider_usage.failures + excluded.failures,
       rate_limited  = provider_usage.rate_limited + excluded.rate_limited,
       limit_rpd     = coalesce(excluded.limit_rpd, provider_usage.limit_rpd),
       limit_tpd     = coalesce(excluded.limit_tpd, provider_usage.limit_tpd),
       last_error    = coalesce(excluded.last_error, provider_usage.last_error),
       updated_at    = excluded.updated_at;
