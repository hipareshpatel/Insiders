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
| Pledged data | `/api/corporate-pledgedata?index=equities&symbol=X` | `percSharesPledged`, `percPromoterHolding` (assumption: the page's columns; **empty when called, 2026-10-18**). Use `/api/corporate-pledgedata-sast3132` instead (encumbrance disclosures, measured 2026-10-18, below) for module 42 |
| Shareholding | `/api/corporate-share-holdings-master?index=equities&symbol=X` | already read (`seed_shareholding`) |

The menu also lists board meetings, corporate actions, voting results, insider trading, SAST
regulations 29/31, secretarial compliance, statements of deviation, investor complaints and credit
ratings, each with its own page under `/companies-listing/`. The endpoint for any of them is the
`/api/...` call that page makes; read it from the page rather than guessing the name.

## Event XBRL (Reg 30 announcements): published with the announcement

Verified 2026-10-18 (cloud session, live calls; the owner pointed at the announcements page). The earlier view that
event XBRL had "no source found" (TRACKER F48 gap 3, PLAN 17) was wrong for NSE. **"Within seconds" was wrong too**
(measured 2026-10-18, laptop, `xbrl_lag.py` in the session scratchpad): the rows' `timeTaken` / `difference` of
00:00:01 is NSE's own dissemination delay, not the gap after the PDF. Matching 24 seeded event-XBRL rows of 13-17 Oct
(orders, director changes, regulatory actions) to the company's nearest earlier announcement flagged `hasXbrl`:
median 8 minutes; 14 within 15 minutes, 19 within an hour, 21 within 4 hours, all within 17 hours. RailTel's ₹18.99 Cr
order: PDF 17 Oct 13:37, XBRL 18 Oct 10:38 (21 hours). So a card written from the PDF must be checked against the
XBRL when it lands, as for results (PLAN 16), not assume it is there. **Reproduced on a GitHub runner 2026-10-18**
(`online_probe.py`, 11-18 Oct, 354 files, 320 matched to the nearest earlier `hasXbrl` announcement of the symbol):
median 9 minutes; 50 within a minute, 185 within 15 minutes, 242 within an hour, 278 within 4 hours. **But
`hasXbrl` is true on every row** (515 of 515 on 16 Oct, measured 2026-10-18), so both counts paired a file with the
company's nearest announcement of any kind. Matched on the same event as well (the XBRL's `eventType` starts with the
announcement's `desc`; a director change's announcement says "Appointment", "Change in Management", "Resignation" or
"Cessation"; `_SAME_EVENT` in `online_probe.py`): 261 of 354, **median 8 minutes**; 50 within a minute, 158 within 15
minutes, 205 within an hour (79%), 227 within 4 hours (87%), the longest 92 hours. Not yet paired: frauds/defaults,
guarantees, amendment or termination of agreements, regulatory-framework changes, new lines of business.

- `/api/corporate-announcements?index=equities`: every row carries `hasXbrl`, true on every row (20 of 20 on 18 Oct 2026, 515 of 515 on 16 Oct), so it says nothing, and
  `seq_id`, beside the PDF in `attchmntFile`. **There is no shared key** with the XBRL rows (`seq_id` and `appId` are
  different series; measured 2026-10-18): join by symbol, event type and time, and confirm from the file itself, which
  carries `NSESymbol`, `ScripCode` (BSE's code: our `scrip_code`), `ISIN`, `DateOfOccurrenceOfEventOrInformation` and
  `DateOfReport`. One event can have two PDFs and two XBRL files (RailTel 17-18 Oct).
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
  designation, type of change and effective date. `BroadConsiderationForTheOrdersOrContracts` is free text and says
  whether the amount includes tax (RailTel: "Rs. 18,99,03,173/ (IncludingTax)"); the counterparty's CIN/LEI is a field.

So for these events the amount, unit, counterparty, dates and stage need no model reading: they are exact fields.

### Joining an event file to its announcement (measured 2026-10-18, laptop, `scripts/event_xbrl_join.py`)

13-18 Oct 2026: 2,429 announcements, 130 event files once director changes are left out (D30: they get no card).
- **The announcements page's XML icon is not the event file.** It links `/api/xbrl/<seq_id>`, NSE's generic record of
  the announcement (symbol, company, subject, the one-line description, the PDF's URL, the time; 1.7 KB for RailTel's
  order of 17 Oct, seq 106821056), the same data as the JSON row. No amount, no party, no link to the event file.
- **The same file is the key where it exists.** 45 director-change rows carry the announcement's own attachment URL;
  76 of 82 order, action and litigation rows that carry a PDF carry one of exactly the announcement's size ("409.89 KB"),
  each time one announcement of the symbol; a zip holds the PDF beside the XML. 74 of the 130 files have such a pair.
- **Otherwise the content.** An amount the file states printed in the PDF (crore, lakh, million or rupees, three
  significant digits at least), or for an event without an amount a name it states. On the 74 known pairs this alone
  finds the right announcement for 50 and takes 3 others (product-launch filings of the same company the same day:
  MilkyMist twice, SBI Card's press release; probably the same launch, not checked). The company's own name and an
  authority's name (RBI, SEBI, a tax office) count only under the event's own subject: under "General Updates" they
  paired Yes Bank's action file with its ESG-rating letter and Reliance Power's with an unrelated letter.
- **Together:** 106 of 130 files reach an announcement (79 by the same file, the rest by content); none of the 74
  known pairs is joined elsewhere. By event: orders 28 of 36, legal (actions, litigation) 55 of 61, operations 9 of 13,
  licences 4 of 6, guarantees 3 of 3, ESOPs 3 of 4, agreements 3 of 5. Unjoined files are mostly scanned PDFs without a
  text layer (the check reads the layer) and filings outside the window.

## Integrated filing lists (results and governance), all companies (measured 2026-10-18)

The owner's pages `corporate-integrated-filing?integratedType=integratedfilingfinancials` and `...governance` load
their tables from `/api/integrated-filing-results?type=Integrated%20Filing-%20Financials` (or `...-%20Governance`)
`&page=N&size=M` with no symbol: every company, newest first, `{data, size, page, totalCount}`.
- Financials: totalCount 27,140; `size` up to 1,000 honoured (page 1 reached back to 14 Aug 2026, page 2 to 11 Aug).
  Every one of 1,000 rows had an `.xml`; basis "Standalone" 620, "Consolidated" 380; 219 rows for the September 2026
  quarter by 17 Oct. 321 of 1,000 were revisions (`type_Sub` "Revision"), whose time is `revised_Date`
  ("18-OCT-2026 21:27:17", the page's "Revised Date/Time" column; owner) - `broadcast_Date` is null on them.
- Governance: totalCount 21,021; 727 rows for the September 2026 quarter by 18 Oct (684 companies); 306 of 1,000
  revisions. Its XBRL is read by `governance_xbrl.py` (board, committees, SEBI compliance flags, meeting gaps, fines and
  penalties, tax litigation, loans and guarantees to insiders, cyber incidents); the PDF stays on the drop list.
- The pipeline reads results per company (`/api/integrated-filing-results?symbol=`, `NseClient.financial_results`), which
  also gives the year-ago and previous-quarter files; the all-company list is the cheaper way to sweep a day or a
  backfill (assumption until measured in the NSE round).

## Timing checked live (2026-10-18, cloud session)

| Data | Claim in these docs | Measured |
|---|---|---|
| Event XBRL (Reg 30) | "no source found" | Exists. Published minutes after the announcement as a rule (median 8 min, 19 of 24 within an hour), up to 21 hours (above; laptop, 2026-10-18) |
| Results XBRL (NSE integrated filing) | "up to 24 hours" after the outcome PDF (TRACKER F48 gap 2) | Same day, **5 minutes to 2 h 40 min** after the board-meeting outcome: Capri Global 5 min (Q1FY27), LTM 49 min (Q2FY27), Newgen 2 h 28 min, Bank of Maharashtra 2 h 39 min. A results card can wait for it or be corrected within hours, not a day |
| Annual-report XBRL | "weeks to months after the PDF" | **True**: LTM ~7 weeks, NTPC ~7.5, Newgen ~8, Hindustan Copper FY25 ~4.5 months; Capri Global FY26 not listed yet |
| Pledged data | `/api/corporate-pledgedata` gives `percSharesPledged` (Pledged data row above) | **Not reproduced**: empty `data` with and without symbol and dates; `/api/corporate-pledge-holding` returns a count of 0. **Re-read from the page's own code 2026-10-18 (laptop, Indian IP):** the page calls exactly `/api/corporate-pledgedata?` plus `&symbol=` and dates; still empty. Its neighbour **`/api/corporate-pledgedata-sast3132?&from_date=&to_date=`** (SAST Reg 31 encumbrance disclosures) returns rows: 288 for 1 Jul-18 Oct 2026, each with company, lender (`eventDetailsEntity`), shares encumbered and % (`encumbHolding`, `encumbPerc`), event dates and the filing (`attachment`). That is a promoter-pledge source for module 42, event by event. **Reproduced on a GitHub runner 2026-10-18**: 11 rows for 11-18 Oct, same fields |

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
- Whether an Integrated Filing instance exists for companies listed only on BSE. NSE lists 2,477 of our 5,111
  companies (measured 2026-10-18 against `EQUITY_L.csv`, 2,605 rows, by ISIN; 2,480 on 2026-10-16): 77% of those
  above ₹100 Cr, 96% above ₹1,000 Cr, 99% above ₹10,000 Cr. The rest are almost all micro caps. NSE's SME list is a
  separate file, not counted.
- DGTR (module 8): measured 2026-10-18, `dgtr.gov.in` answers; each anti-dumping case has a page listing its
  initiation, preliminary findings and final findings as dated PDF downloads, and the case list filters by date, HS
  code, country and status. A source, as PDFs; linking a product to listed companies is the open part.
