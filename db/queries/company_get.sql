-- ?1 = scrip code.
SELECT scrip_code, symbol, company_name, isin, industry, sector, market_cap_cr, size_category,
       shares_outstanding, last_price, price_date, ret_1w, ret_1m, ret_1y
  FROM companies
 WHERE scrip_code = ?1;
