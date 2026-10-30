-- ?1 = JSON array of results_kpi rows (results_table.py). A row whose figures did not change (same digest) is not rewritten.
INSERT INTO results_kpi (scrip_code, period, basis, revenue, revenue_yoy, revenue_qoq, ebitda, ebitda_yoy, ebitda_qoq, ebitda_turn, ebitda_key,
                         pat, pat_yoy, pat_qoq, pat_turn, pat_key, opm, opm_yoy_bps, opm_qoq_bps, digest, updated_at)
SELECT json_extract(value, '$.scrip_code'), json_extract(value, '$.period'), json_extract(value, '$.basis'),
       json_extract(value, '$.revenue'), json_extract(value, '$.revenue_yoy'), json_extract(value, '$.revenue_qoq'),
       json_extract(value, '$.ebitda'), json_extract(value, '$.ebitda_yoy'), json_extract(value, '$.ebitda_qoq'),
       json_extract(value, '$.ebitda_turn'), json_extract(value, '$.ebitda_key'),
       json_extract(value, '$.pat'), json_extract(value, '$.pat_yoy'), json_extract(value, '$.pat_qoq'),
       json_extract(value, '$.pat_turn'), json_extract(value, '$.pat_key'),
       json_extract(value, '$.opm'), json_extract(value, '$.opm_yoy_bps'), json_extract(value, '$.opm_qoq_bps'),
       json_extract(value, '$.digest'), json_extract(value, '$.updated_at')
FROM json_each(?1)
WHERE true
ON CONFLICT (scrip_code, period) DO UPDATE SET
       basis = excluded.basis, revenue = excluded.revenue, revenue_yoy = excluded.revenue_yoy, revenue_qoq = excluded.revenue_qoq,
       ebitda = excluded.ebitda, ebitda_yoy = excluded.ebitda_yoy, ebitda_qoq = excluded.ebitda_qoq,
       ebitda_turn = excluded.ebitda_turn, ebitda_key = excluded.ebitda_key,
       pat = excluded.pat, pat_yoy = excluded.pat_yoy, pat_qoq = excluded.pat_qoq, pat_turn = excluded.pat_turn, pat_key = excluded.pat_key,
       opm = excluded.opm, opm_yoy_bps = excluded.opm_yoy_bps, opm_qoq_bps = excluded.opm_qoq_bps,
       digest = excluded.digest, updated_at = excluded.updated_at
 WHERE results_kpi.digest IS NOT excluded.digest;
