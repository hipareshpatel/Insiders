-- Stage 0 XBRL fast path: the filing's machine-readable XBRL file, when BSE lists one.
ALTER TABLE filings ADD COLUMN xbrl_url TEXT;
