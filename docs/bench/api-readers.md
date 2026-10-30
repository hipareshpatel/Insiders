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

## Next

- A second probe with the fixes: Mistral (retry) and nemotron-parse-2.0 (tool named). If either answers, the full 65
  pages, before the artifact expires on 2 Nov.
- The out-of-sample check before any live use (lead): numbers-first first plus guarded nemotron-parse, on the normal key and
  the pdf-oos keys, both orders.
