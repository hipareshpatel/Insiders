# Where the structured data comes from

BSE's announcement feed carries PDFs: 0 of 1,166 rows had an XBRL link. Everything machine-tagged
therefore comes from somewhere else, and this is the map of what has been found and verified,
written down because finding it again costs an afternoon each time.

Verified by reading the pages' own network calls on 2026-10-17 (the owner pointed at the pages; the
endpoints are what those pages actually fetch, not guesses). NSE rate-limits by IP: see `nse.py` for
the pacing rules. A date filter is `from_date`/`to_date` as `dd-mm-yyyy`.

## Results

| What | Endpoint | Covers |
|---|---|---|
| Results, old format | `/api/corporates-financial-results?index=equities&symbol=X&period=Quarterly` | up to the changeover; still current for SME, debt and REIT/InvIT |
| **Integrated Filing (Financials)** | `/api/integrated-filing-results?symbol=X&type=Integrated Filing- Financials&page=1&size=50` | **quarters from March 2025 on, every company** |
| Integrated Filing (Governance) | same, `type=Integrated Filing- Governance` | not read yet |

SEBI's Integrated Filing replaced the standalone results filing for quarters from March 2025. That
is why the older list appears to stop dead in January 2025 — nothing is missing, the filings moved.
Both are read and merged in `NseClient.financial_results`.

Each instance names its template in its own namespace (`IntegratedFinance_<family>`), and
`xbrl.taxonomy()` reads it:

| Family | Who files it | Parses to |
|---|---|---|
| `INDAS` | ordinary companies | 23 metrics |
| `NBFC_INDAS` | NBFCs | 23 metrics |
| `BANKING` | banks (RBI Form B) | 28 metrics |
| `GI` | general insurers | 30 metrics |
| `LI` | life insurers | 30 metrics |

Banking and the two insurance maps are overlays on the commercial one, because the same name means
different things: `ProvisionForTax` is a general insurer's tax on profit and a life insurer's
*policyholders'* tax, twenty times larger and unrelated to the result it would be read against.

## Everything else NSE publishes as data

Found but not yet read. Each would replace something a model currently reads out of a PDF.

| What | Endpoint | Why it matters |
|---|---|---|
| Annual report XBRL | `/api/annual-reports-xbrl?index=equities&symbol=X` | the whole annual report tagged: 631 numeric and 332 text facts. Carries related-party transactions, auditors and their signatories, significant investments in subsidiaries, managerial remuneration, CSR, **continuing defaults on principal and interest**, and **loans and receivables due from directors**. Three of the four buckets PLAN item 2 wanted a model to read, machine-tagged instead. Example: `AR_XBRL_GOKULAGRO_16102026164404.xml`, 3.9 MB |
| Announcements | `/api/corporate-announcements?index=equities&symbol=X` | every filing with a `desc` category NSE assigns it, plus `attchmntText`. An independent label to check our own event typing against, and a second dedup key (`seq_id`) |
| Pledged data | `/api/corporate-pledgedata?index=equities&symbol=X` | `percSharesPledged`, `percPromoterHolding`. Blueprint module 42 (promoter-group contagion) is recorded as having no data source; this is one |
| Shareholding | `/api/corporate-share-holdings-master?index=equities&symbol=X` | already read (`seed_shareholding`) |

The menu also lists board meetings, corporate actions, voting results, insider trading, SAST
regulations 29/31, secretarial compliance, statements of deviation, investor complaints and credit
ratings, each with its own page under `/companies-listing/`. The endpoint for any of them is the
`/api/...` call that page makes; read it from the page rather than guessing the name.

## Still open

- BSE's announcement API does carry an XBRL identity we had missed, but it is not a link. The beta
  site reads the same `AnnSubCategoryGetData` endpoint we do, and every row has `XML_NAME`
  (`ANN_<scrip>_<guid>`) - which is why "0 of 1,166 rows had an XBRL link" was true and still
  misleading: we looked for a URL and the field holds a name. Checked 2026-10-17: that name 404s
  under AttachHis, AttachLive, CorpAttachment, Attachbse and AttachXbrl, with and without `.xml`,
  so the serving path is still unknown. NSE's announcement XBRL listing covers the same ground.
- Whether an Integrated Filing instance exists for companies listed only on BSE (NSE has 2,480 of our
  5,111 companies). Those are almost all micro caps.
