# Hard-PDF answer key (F199)

340 public NSE figures from 21 hard results-statement PDFs (scans, rotated pages, lakh and million units, garbled text layers,
standalone and consolidated blocks side by side). Built 2026-10-26 from NSE's own results XBRL, checked against the printed page;
where the page prints another figure than the XBRL, `expected_cr` is the printed one.

`key.csv`: `symbol, scrip (blank), period_end, period (Q2FY25 or FY24, as the referee names them), basis (STANDALONE or
CONSOLIDATED), metric (revenue or pat), expected_cr, unit_printed, pdf_url (NSE archive), tags (difficulty, `|` separated)`.
Only rows the referee can ask are kept: revenue and profit for a quarter or a year. Half-year, nine-month and profit-attributable-to-owners
rows of the full set are left out.

Run (maintenance workflow, read only, no AI): command `pdf-referee-ensemble`, ids `hardset` (`limit` = first N PDFs). The fetch job
downloads each `pdf_url`, each reader reads them in its own job, the settle job asks every reader and the unchanged settle rule each
row and writes `hardset-score.json`, `hardset-score.md` and `hardset-readings.json` to the artifact `pdf-referee-ensemble`: per reader and
for the ensemble right / wrong / abstain (right = within half a unit of the printed decimals, at least 0.005 crore), per difficulty tag,
and the ensemble's false settlements one by one. Code: `pipeline/src/bse_intel/pdf_bench.py`.
