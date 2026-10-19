-- ?1 = month prefix (YYYY-MM). Per-model totals for monthly quota ceilings.
-- A range on the primary key (day, provider, model); LIKE on an expression would scan the table.
SELECT provider, model,
       sum(requests) AS requests, sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens
  FROM provider_usage
 WHERE day BETWEEN ?1 || '-01' AND ?1 || '-31'
 GROUP BY provider, model;
