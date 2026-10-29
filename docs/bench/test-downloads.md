# Test and download runs: where their files are kept (reuse them, never fetch twice)

Owner, 29 Oct 2026: "Ensure all test files must gets saved else it's double effort of downloading it again. Why don't you save
it in your document so next all such test results we can use." Every download run, a test's too, keeps every file it fetched;
this page says where, so the next run or study reads them from there. Add a row for each new run. Times are IST.

| Date | What | Run | Files kept | Where | Reuse |
|---|---|---|---|---|---|
| 28 Oct | NSE results and annual-report XBRL, every company (`xbrl-facts --from-nse --annual`, 16 shards, resumed) | 40679795489, 40713916803 (20:44-22:44) | results files of 12 quarters (both bases), annual reports FY25-FY26 | R2 `raw/xbrl/` (the XBRL store, 2 GB cap) and their facts at `raw/xbrl-facts/<scrip>/` | complete for NSE; a company is re-listed only when its marker is 7 days old or a quarter is missing |
| 29 Oct | PDF reader benchmark PDFs (both answer keys, 71 PDFs) | 40810936312 (pdf-bench) | 52 normal + 23 hard PDFs | GitHub artifact `pdf-bench-pdfs` of that run, kept 90 days | `gh run download 40810936312 -n pdf-bench-pdfs`; the lead's own re-score read them from there |
| 29 Oct | Screener sub-rows, trial then every company (`screener-schedules`, 12 runners) | 40799555021 (trial), 40800483999 (06:56-10:25) | 1,850 companies, 59,530 answers | R2 `raw/screener-schedules/<day>/<SYMBOL>.json.gz` | complete; a stored company is never asked again |
| 29 Oct | BSE annual-report XBRL, 100-file test | 40817278550 (09:51-10:22) | 100 files (FY21-FY25 of the 17 largest with files) | R2 `raw/bse-annual-xbrl/<scrip>/<file>.gz`, facts as `raw/xbrl-facts/<scrip>/annual-<FY>-<basis>.json.gz`, each company's BSE list as `list.json` | read from R2; the full run skipped them |
| 29 Oct | BSE annual-report XBRL, every company, FY24-FY25 reports | 40820413554 (from 10:25) | running | as above | resumable: a stored year is not asked again |
| 29 Oct | Card filing texts, NSE (`text-backfill`, 6 shards) | 40821126640 | 12 texts (the rest were stored on 26 Oct) | R2 `text/<news_id>.json.gz` | complete for NSE; about 840 cards NSE cannot serve wait for the BSE part |
| 29 Oct | Card filing texts, BSE (`text-backfill-bse`) | 40830944991 (12:13-12:15, its own queue; the queued copy 40821130435 was cancelled before it started) | 2 texts; 8,485 of 8,517 cards now have their text, 32 have no BSE or NSE text to fetch | as above | complete |
| 29 Oct | 10 annual-report PDFs (FY26) for the PDF annual-report reader test (Ambuja, BEL, DLF, Mankind, Maruti, NHPC, Tata Consumer, TMCV, TMPV, Vedanta) | first by hand from the lead session (scratchpad only), then kept by `keep-annual-pdfs` run 40830008889 (12:05 IST) | 10 PDFs, 174 MB; NHPC's NSE copy is cut short at the source (4.96 of 20.5 MB) | R2 `raw/annual-pdf/<SYMBOL>/<file>.pdf.gz` | read from R2; `keep-annual-pdfs --symbols ...` adds companies, a stored file is never fetched again |
| 29 Oct | BSE results XBRL, 100-file test (`bse-results-xbrl`) | 40830948654 (from 12:13) | running | the XBRL store `raw/xbrl/` (as every results file) and facts at `raw/xbrl-facts/<scrip>/<period>-<basis>.json.gz` with `exchange: "BSE"`; each company's BSE archive answer as `raw/bse-results-xbrl/<scrip>/list.json` | resumable; a run stops at once if the store does not keep a file |

Rules every download follows (CLAUDE.md, owner 27-29 Oct 2026): the first test of a new download path is 100 files; every file
it fetches is kept (a dry run's too); a stored file is read from the store, never fetched again; a run saves as it goes and
uploads its results even when stopped by its time budget; any refusal stops it at once.
