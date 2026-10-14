-- ?1 = day (YYYY-MM-DD, UTC).
SELECT day, provider, model, requests, input_tokens, output_tokens, failures, rate_limited
  FROM provider_usage
 WHERE day = ?1;
