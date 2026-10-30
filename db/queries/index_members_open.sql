-- The stretches of membership still open: what the weekly job compares NSE's lists with. No parameter.
SELECT index_id, isin, symbol, company_name, valid_from FROM index_members WHERE valid_to IS NULL
