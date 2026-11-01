# Document-parsing APIs on the hard set (30 Oct 2026)

The lead asked (30 Oct) to score Mistral's Document OCR and NVIDIA's nemotron-parse models as more readers on the hard
set (`docs/bench/hardpdf/key.csv`, 340 figures, 21 PDFs). The PDFs are the kept ones from run 40414799620 (artifact
`pdf-ensemble-pdfs`); no exchange is read. Each reader gets the statement pages the other readers were scored on.
Maintenance command `api-reader-hardset`; code `pdf_readers.MistralOcrReader`, `NemotronParseReader` and its
subclasses. Bench only: no live path selects these readers.

## Run 41063175585 (main 2629878, 30 Oct 13:26-13:44 UTC)

| Reader | Right | Wrong | No answer | Pages | Seconds a page | Cost |
|---|---|---|---|---|---|---|
| nemotron-parse (`nvidia/nemotron-parse`) | **155** | **2** | 183 | 77 | 12.9 | $0 (free NVIDIA key) |
| Mistral OCR (`mistral-ocr-latest`) | 0 | 0 | 340 (every PDF refused) | 0 | - | $0 |
| nemotron-parse-2.0 (`nvidia/nemotron-parse-2.0`) | 0 | 0 | 340 (every PDF refused) | 0 | - | $0 |

- **nemotron-parse:** 155 right of 340 is 46%. On the same key no reader of the 11 scored on 27 Oct did better than
  19% (65 right / 10 wrong). Of its 157 answers, 2 are wrong (1.3%):
  - FIVESTAR Q1FY24 standalone PAT: read 0.1837 against the printed 183.71. That is a 1,000x unit slip; the unit line
    is most likely a separate element from the table.
  - SPANDANA Q2FY25 consolidated revenue: read 1,396.27 against the printed 686.38 (another column or table).
- Where it is strong: split tables 30 of 30, rotated and landscape pages 20 of 36, low-quality scans 15 of 28.
- Where it gives nothing: pages with no text layer 0 of 18, side-by-side bases 0 of 36, nine-month columns 0 of 48,
  stamps over the table 0 of 16.
- **Positions (TODO 144):** 966 element boxes on 77 pages. Each element (a title, a paragraph, a table) has a normalised
  box; there is no box per word or per table cell. So a table's place on a slide is usable, but a chart's figure cannot
  be tied to its label unless the chart comes back as its own table element.
- **Mistral OCR and nemotron-parse-2.0 were refused on every PDF.** The scorer kept only the error's type
  (RuntimeError) and the job did not log the HTTP body, so the reason is not known from this run. Likely, not
  measured: the Free plan's tier for Mistral (our key gets 403 "not available in your subscription tier" on
  mistral-large-2512), and no free endpoint for nemotron-parse-2.0 (the owner's NVIDIA catalogue lists it as
  Downloadable only). Since 30 Oct each refusal's status and body are kept as `refused-<n>.json` in the artifact and
  printed in the job log.

## Guards on nemotron-parse (30 Oct 2026, replay)

The run's 77 kept answers were replayed offline: the scoring was run with the API answered from the kept files in their
call order (file times), and the replay reproduces the run exactly (155 / 2 / 183, 77 calls). Each change below was
scored on that replay. **All of this is in-sample**: the guards were written after seeing these wrongs.

| nemotron-parse setting | Right | Wrong | No answer |
|---|---|---|---|
| As run | 155 | 2 | 183 |
| + the title, page-header and short text elements above each table as its header | 197 | 2 | 141 |
| + a figure with two decimal points gives no answer | 194 | 1 | 145 |
| After the blind review and re-review (real dates spared, marks ignored; notes, list items, captions, long text and a short line after a table never a header) | **185** | **1** | 154 |
| Requiring a unit line (rejected) | 150 | 5 | 185 |
| Elements sorted top to bottom (rejected) | 185 | 5 | 150 |

- FIVESTAR's wrong was not a unit. nemotron wrote "18.370.88" for 18,370.88, and it was read as 18.37 lakh.
- Requiring a unit line dropped right tables, and another table on the page answered wrong (GEOJIT x3).
- Sorting by height gave J&KBANK's consolidated table another block's title, a two-column page (4 wrong). The answer's own
  reading order stays.
- The one wrong left is SPANDANA Q2FY25 consolidated revenue: 1,396.27 is the half-year figure (686.38 + 709.89).

**With numbers-first** (frozen re-score se2, 272 / 0 / 68 on this key, also in-sample):

| Order | Right | Wrong | No answer |
|---|---|---|---|
| Numbers-first alone | 272 | 0 | 68 |
| Numbers-first first, guarded nemotron-parse on its no-answers | **294** | **0** | 46 |
| Guarded nemotron-parse first, numbers-first on its no-answers | 293 | 1 | 46 |

## Probe run 41072420377 (limit 2)

- Mistral: HTTP 429 "Rate limit exceeded" (code 1300) on both calls. That is not a tier refusal. The reader now waits
  and retries a 429 (2, 5, 10 s).
- nemotron-parse-2.0: HTTP 400 '"auto" tool choice requires --enable-auto-tool-choice'. The endpoint exists; the reader
  now names its tool in `tool_choice` (v1 is left as measured).
- nemotron-3.5-parse: HTTP 404 "404 page not found" for `nvidia/nemotron-3.5-parse`. The name is not served at this
  endpoint. Assumption, not found by a search on 30 Oct: it may have another id or another URL.

## Mistral OCR and nemotron-parse-2.0: stopped (lead, 1 Nov 2026)

- **Mistral OCR.** HTTP 429 "Rate limit exceeded" (code 1300) on every call in runs 41072420377 (30 Oct), 41076952339
  (30 Oct, with 2, 5 and 10 s retries) and 41267832784 (1 Nov, after the monthly allowance reset).
  - A limit that holds on the first calls of a new month, through ~17 s of retries, is not a rate or budget limit.
  - Owner, 1 Nov: the admin page shows OCR allowed on the Free plan; October cost $4.3.
  - Measured 1 Nov, run 41272136846 (one page, spaced, Retry-After honoured): the 429 carries
    `x-ratelimit-limit-req-minute: 0`. Our key's request limit for the OCR model is zero a minute, so no spacing or retry
    can pass. Unblocking it is an owner setting (the console's per-model limits), if the Free plan allows a non-zero one.
- **nemotron-parse-2.0.** Each request form was refused:
  - Without tool_choice: 400 '"auto" tool choice requires --enable-auto-tool-choice'.
  - Once: 502 Bad Gateway.
  - With the tool named in tool_choice: 400 "requires --tool-call-parser to be set".
  - The hosted endpoint takes no tool calls at all, and NVIDIA's catalogue lists the model as downloadable only. A
    no-tool reader that parses the raw bbox-tagged text would be new code for a model we cannot rely on being hosted.
- **nemotron-3.5-parse.** 404 for `nvidia/nemotron-3.5-parse`. Waiting on the exact model id from the owner.

## Out of sample: run 41077643109 (api-reader-oos, 30 Oct 2026)

`docs/bench/oos/key-union.csv`: 552 figures in 67 kept PDFs, no exchange read, 172 nemotron pages. Fully unseen by both
readers' fixes: run 1 groups 4-6 plus the third run's 52 extra figures (308).

| Order | Fully unseen (308) | Run 1 groups 1-3, seen while fixing numbers-first (244) | All (552) |
|---|---|---|---|
| Numbers-first alone | 129 / 6 / 173 | 117 / 5 / 122 | 246 / 11 / 295 |
| Guarded nemotron-parse alone | 58 / 2 / 248 | 45 / 3 / 196 | 103 / 5 / 444 |
| **Numbers-first first, nemotron on its no-answers** | **148 / 7 / 153** | 130 / 7 / 107 | 278 / 14 / 260 |
| Nemotron first | 147 / 8 / 153 | 129 / 8 / 107 | 276 / 16 / 260 |

The three wrongs nemotron adds in the numbers-first-first order:
- SMARTWORKS consolidated PAT 10.28: the standalone key-figures note under a "NOTES TO ... CONSOLIDATED RESULTS" heading.
- PFOCUS consolidated revenue 1,256.08: the page prints 125,608.42 lakh, and the key's 1,266.82 is not on the page (key
  tag `xbrl:not_found`). The reader matches the page; the key does not.
- DOLATALGO PAT 53.864: printed, against the filed 53.87 (a rounding gap in the key).

## NEMOTRON_BASIS_GUARD (off; lead, 1 Nov 2026)

A nemotron table is read only when its own header rows (the lines above it in the answer, or its first two rows) name
exactly one basis. A "Notes to ..." heading never counts, and the page context never decides. Written after the out-of-sample
misses above, so the replays below are checks only. **The score is a fresh unseen set; the pass mark, set before scoring, is
0 wrong among the readings it adds over numbers-first.**

Replays, offline from the kept answers (each reproduces its run exactly first):
- Out of sample: nemotron alone 103/5/444 → 100/1/451. Only PFOCUS is left, where the reader matches the page (above).
  With numbers-first first, the fully unseen part is 145/7/153 (numbers-first alone 126/6/173 on the same figures).
- Hard set: nemotron alone 185/1/154 → 155/1/184. With numbers-first first, 292/0/48 (alone 272/0/68).

## Next

- A second probe with the fixes: Mistral (retry) and nemotron-parse-2.0 (tool named). If either answers, the full 65
  pages, before the artifact expires on 2 Nov.
- The fresh unseen set for NEMOTRON_BASIS_GUARD (source: the lead's call), then the owner's decision on live use.
