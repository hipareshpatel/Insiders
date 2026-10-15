-- Optional techno-funda tags (blueprint §11.3) from the market-data job: stage 2, VCP, RS
-- percentile, Clenow slope, RVOL, with the price date they describe.
ALTER TABLE companies ADD COLUMN technicals_json TEXT;
