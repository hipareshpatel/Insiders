-- ?1 = scrip code after which to continue, ?2 = limit. sync-to-cloud.
SELECT scrip_code, symbol, company_name, isin, industry, sector, market_cap_cr, size_category, shares_outstanding,
       shares_updated_at, last_price, price_date, ret_1w, ret_1m, ret_1y, updated_at, median_turnover_cr,
       bse_group, credibility_score, former_names_json
  FROM companies
 WHERE scrip_code > ?1
 ORDER BY scrip_code
 LIMIT ?2;
