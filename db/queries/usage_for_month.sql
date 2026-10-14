-- ?1 = month prefix (YYYY-MM). Per-model totals for monthly quota ceilings.
SELECT provider, model,
       sum(requests) AS requests, sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens
  FROM provider_usage
 WHERE day LIKE ?1 || '-%'
 GROUP BY provider, model;
