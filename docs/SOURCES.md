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

## Annual reports

Read since 2026-10-18 (`annual_xbrl.py`, `NseClient.annual_reports`; to-do item 4, TRACKER F57). The endpoint
is the call the "Annual Reports XBRL" page (`/companies-listing/corporate-filings-annual-reports-xbrl`) makes:

| What | Endpoint | Answer |
|---|---|---|
| Annual report XBRL | `/api/annual-reports-xbrl?index=equities&symbol=X` | `{"data": [{fromYr, toYr, report_type, submission_type, broadcast_dttm, fileName}]}`: one row per financial year and basis (`Standalone` / `Consolidated`), `fileName` a direct `nsearchives.nseindia.com/corporate/xbrl/AR_XBRL_<SYMBOL>_<ddmmyyyyhhmmss>.xml` |

Each file is the company's financial statements as filed with MCA, on the MCA Ind-AS taxonomy
(`in-ci-ent-2017-03-31`), 2.5-4.5 MB for the smoke-test companies: every amount in rupees, the basis in
`NatureOfReportStandaloneConsolidated`, the PDF's printing unit in `LevelOfRoundingUsedInFinancialStatements`,
each related party, key managerial person and consolidated entity a typed member of its own. The
standalone file alone carries the board's report (KMP pay by person) and the auditor's CARO clauses
(statutory dues, defaults to lenders, fraud); the consolidated one carries each group entity's share of the
result. What the pipeline reads and puts in front of an annual report's text is listed in `annual_xbrl.py`.

- **A zero is the filing software's blank.** Kanoria FY25 files `ContingentLiabilities` 0 beside
  `WhetherThereAreAnyContingentLiabilities` "true" and ₹6.82 Cr by class, and `ManagerialRemuneration` 0 while
  its board's report pays the MD ₹3.15 Cr. Zeros are left out, never shown as nil.
- **"Qualified Opinion" can head the report on internal financial controls** (Shivam FY25) while the opinion
  on the statements is unmodified; the opinion is read from its "Basis for ... Opinion" heading.
- **It comes weeks to months after the PDF.** Kanoria FY25: report 2 Sep 2025, XBRL 22 Dec 2025; eMudhra 2.5
  months; Heritage 6 weeks. A report read the day it is filed has none yet. The year is taken from the filing
  (its headline, else the date), never "the newest file listed". `annual-xbrl-catchup` (`annual_catchup.py`),
  run once a day after the close, reads the list again for each company whose annual-report card has no table
  (one request per company, at most weekly, every four weeks while the list is empty, 150 a run at the usual
  3-5 s pace) and re-reads the report when a file for its year was broadcast after the card last read the list
  in full (`card_json.annual_xbrl_checked`). It stops on 401/403/429 and queues nothing then.
- Coverage for the ten smoke-test companies on 2026-10-18: 8 of 10 list files (not Novartis, not CSB Bank);
  FY25 for six, FY26 for three; Shivam and SML file standalone only, Jubilant consolidated only. Ahluwalia's
  FY24 rows carry report_type "ARnull" (not read yet).

## Everything else NSE publishes as data

Found but not yet read. Each would replace something a model currently reads out of a PDF.

| What | Endpoint | Why it matters |
|---|---|---|
| Announcements | `/api/corporate-announcements?index=equities&symbol=X` | every filing with a `desc` category NSE assigns it, plus `attchmntText`. An independent label to check our own event typing against, and a second dedup key (`seq_id`) |
| Pledged data | `/api/corporate-pledgedata?index=equities&symbol=X` | `percSharesPledged`, `percPromoterHolding`. Blueprint module 42 (promoter-group contagion) is recorded as having no data source; this is one |
| Shareholding | `/api/corporate-share-holdings-master?index=equities&symbol=X` | already read (`seed_shareholding`) |

The menu also lists board meetings, corporate actions, voting results, insider trading, SAST
regulations 29/31, secretarial compliance, statements of deviation, investor complaints and credit
ratings, each with its own page under `/companies-listing/`. The endpoint for any of them is the
`/api/...` call that page makes; read it from the page rather than guessing the name.

## Event XBRL (Reg 30 announcements): published with the announcement

Verified 2026-10-18 (cloud session, live calls; the owner pointed at the announcements page). The earlier view that
structured data "arrives after the PDF" and that event XBRL had "no source found" (TRACKER F48 gap 3, PLAN 17) was
wrong for NSE: event XBRL is broadcast within seconds of the announcement.

- `/api/corporate-announcements?index=equities`: every row carries `hasXbrl` (20 of 20 true on 18 Oct 2026) and
  `seq_id`, beside the PDF in `attchmntFile`.
- `/api/XBRL-announcements?index=equities&from_date=dd-mm-yyyy&to_date=dd-mm-yyyy&type=T` (the page's
  "Announcements XBRL" tab) lists the files: `xbrl` (raw `.xml` on nsearchives), `ixbrl` (HTML view), `eventType`,
  `broadcastDateTime`, `typeOfAnn` / `prevAppId` for revisions. Some rows put the file in `attachment` instead
  (`.xml`, or a `.zip`). `type` seen to work: `announcements` (director/KMP/auditor changes, resignations),
  `para-b` (orders and contracts, litigation, ESOPs, product launches: 267 rows 1-18 Oct), `action` (regulatory
  actions and orders: 105), `analyst` (meet schedules, recordings, transcripts: 375). Other types are on the page's
  dropdown; read them from it, not by guessing.
- Example, RailTel order 18 Oct 2026 (`REG30_PARA_B_18826_WebXMLFile_20261018_103857107.xml`, taxonomy `in-capmkt`):
  `AmountOfTheOrdersOrContracts` 189903173 (rupees, so ₹18.99 Cr exactly), `NameOfTheEntityAwardingTheOrdersOrContracts`,
  `DateOfBaggingOrReceivingOfOrdersOrContracts`, `TimePeriodByWhichTheOrdersOrContractsIsToBeExecuted`,
  `WhetherTheOrdersOrContractsIsOrdinaryCourseOfBusiness`, `WhetherTheOrderOrContractWouldFallWithinRelatedPartyTransactions`,
  `TypeOfAnnouncementAsPerRegulation30ParaBOfPartAOfScheduleIII` (New / amendment). A director change gives name,
  designation, type of change and effective date.

So for these events the amount, unit, counterparty, dates and stage need no model reading: they are exact fields.

## Timing checked live (2026-10-18, cloud session)

| Data | Claim in these docs | Measured |
|---|---|---|
| Event XBRL (Reg 30) | "no source found" | Published with the announcement, seconds apart (above) |
| Results XBRL (NSE integrated filing) | "up to 24 hours" after the outcome PDF (TRACKER F48 gap 2) | Same day, **5 minutes to 2 h 40 min** after the board-meeting outcome: Capri Global 5 min (Q1FY27), LTM 49 min (Q2FY27), Newgen 2 h 28 min, Bank of Maharashtra 2 h 39 min. A results card can wait for it or be corrected within hours, not a day |
| Annual-report XBRL | "weeks to months after the PDF" | **True**: LTM ~7 weeks, NTPC ~7.5, Newgen ~8, Hindustan Copper FY25 ~4.5 months; Capri Global FY26 not listed yet |
| Pledged data | `/api/corporate-pledgedata` gives `percSharesPledged` (Pledged data row above) | **Not reproduced**: empty `data` with and without symbol and dates; `/api/corporate-pledge-holding` returns a count of 0. The page's call needs reading again before module 42 relies on it |

## Still open

- BSE's announcement API does carry an XBRL identity we had missed, but it is not a link. The beta
  site reads the same `AnnSubCategoryGetData` endpoint we do, and every row has `XML_NAME`
  (`ANN_<scrip>_<guid>`) - which is why "0 of 1,166 rows had an XBRL link" was true and still
  misleading: we looked for a URL and the field holds a name. Checked 2026-10-17: that name 404s
  under AttachHis, AttachLive, CorpAttachment, Attachbse and AttachXbrl, with and without `.xml`,
  so the serving path is still unknown. NSE's announcement XBRL listing covers the same ground (above).
  **Found 2026-10-18 (owner's link):** `https://www.bseindia.com/Msource/90D/CorpXbrlGen.aspx?Bsenewid=<news_id>&Scripcode=<scrip>`
  serves it (HTTP 200 even from a non-Indian cloud IP, unlike the announcement API, which still answers 403). For a
  board-meeting intimation of Shri Dinesh Mills (503804) it holds only the announcement's own metadata in the
  generic `in-bse-co` taxonomy: subject, description, PDF link, submission time, category, type. No event fields
  (amount, counterparty, dates), unlike NSE's Reg 30 XBRL above. Not checked yet for an order or results row.
  The site's **Financial Results** page (`/corporates/comp_resultsnew`, "Std XBRL" / "Con XBRL" columns) loads
  `api.bseindia.com/BseIndiaAPI/api/Result_Arch_ng/w` (checked in its own JS bundle 2026-10-18): the same endpoint
  and `stand_xbrl_link` / `conso_xbrl_link` fields `bse.py` has read since F33. It is on `api.bseindia.com`, which
  answers 403 outside India (this cloud session, GitHub runners), so an online-only pipeline takes results XBRL
  from NSE's integrated filing instead.
  **GitHub verdict, 2026-10-18** (`online-probe.yml`, run 5, `pipeline/scripts/online_probe.py`): on a GitHub-hosted
  runner every `api.bseindia.com` call the results pages make answers **403 Access Denied**: `Corp_FinanceResult_ng_new`
  (the filter form: today, all companies; and one company, last week), `Corp_Archive_Wthxml_ng_new` (its announcements
  panel), `NSTodayResults_ng` and `Result_Arch_ng`. BSE's file host answers **200**: the owner's
  `www.bseindia.com/XBRLFILES/IFIndasDuplicateUploadDocument/Integrated_Finance_Ind_As_512361_..._IFIndAs.html` gave all
  217 tagged figures, and `CorpXbrlGen` the announcement metadata. So on GitHub BSE's files can be read but not listed;
  a file's address carries its upload time, so it cannot be built without a list. NSE answered every call (announcements,
  event XBRL, results, annual reports, shareholding, PDFs).
- Whether an Integrated Filing instance exists for companies listed only on BSE (NSE has 2,480 of our
  5,111 companies). Those are almost all micro caps.
