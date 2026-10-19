# Site screenshots on the laptop's real data (T11, 2026-10-20 ~02:00 IST, commit 83ea204)

Local site (`npm run dev`, local D1/R2: audit-round companies plus the go-live seed at ~165 of 1,778). Full-page shots via Chrome's DevTools protocol, light mode at 1280 and 390 px, plus dark for Today and All filings. The card shots are cropped to the card; All filings is its first 5,000 px. Notes are from the shots I opened and the data behind them; a shot with no note was not checked line by line.

| Shot | URL | Notes |
|---|---|---|
| [01-today-1280.png](01-today-1280.png) | `/` | Since close at 01:53 IST: 0 cards, which is right. Overdue promises still lists Prism Johnson's "Ind-Ra expects ..." items, "due FY26-FY27, 203 days" (T6 filters them where the pipeline builds a company's summary; the D1 summary is the old one until the company is processed again). UCO Bank's 26 Oct strike shows twice (Other + Milestone, different wording, so the dedupe misses it). |
| [02-today-390.png](02-today-390.png) | `/` | (as above) |
| [03-today-dark-1280.png](03-today-dark-1280.png) | `/` | (as above) |
| [04-today-dark-390.png](04-today-dark-390.png) | `/` | (as above) |
| [05-feed-all-1280.png](05-feed-all-1280.png) | `/feed?range=all` | First 5,000 px of the page. Cards render; the light and dark themes both read well. |
| [06-feed-all-390.png](06-feed-all-390.png) | `/feed?range=all` | (as above) |
| [07-feed-all-dark-1280.png](07-feed-all-dark-1280.png) | `/feed?range=all` | (as above) |
| [08-feed-all-dark-390.png](08-feed-all-dark-390.png) | `/feed?range=all` | (as above) |
| [09-card-bank-1280.png](09-card-bank-1280.png) | `/feed?card=33717cd4-0f00-47c3-9a26-9c79acb7b4d4` | CSB Q1FY27. The bank table is right against the XBRL (T7). The sticky top bar covers the card's first line in the shot; that's from the crop, not the site. |
| [10-card-bank-390.png](10-card-bank-390.png) | `/feed?card=33717cd4-0f00-47c3-9a26-9c79acb7b4d4` | (as above) |
| [11-card-results-1280.png](11-card-results-1280.png) | `/feed?card=nse-106731799` | Ramco Q1FY27: no P/E line (148.9x hidden, as fixed). |
| [12-card-results-390.png](12-card-results-390.png) | `/feed?card=nse-106731799` | (as above) |
| [13-card-order-1280.png](13-card-order-1280.png) | `/feed?card=nse-106801864` | Ceigall: "Term · 5 years", size bars 22% / 5.3%, stage LOI. |
| [14-card-order-390.png](14-card-order-390.png) | `/feed?card=nse-106801864` | (as above) |
| [15-card-rating-1280.png](15-card-rating-1280.png) | `/feed?card=1a84a2bd-b7a2-440a-90b6-528b621ce310` | **Held card opened from a public link**: `/feed?card=1a84a2bd...` shows the red "Held: not on the public feed. Only you see this card." banner to anyone. `/api/cards/:id` returns held cards without the owner token. The card itself: ladder AA+ -> 1 notch -> AAA right; still held by 3 quote-contract issues (T7). |
| [16-card-rating-390.png](16-card-rating-390.png) | `/feed?card=1a84a2bd-b7a2-440a-90b6-528b621ce310` | (as above) |
| [17-card-regulatory-1280.png](17-card-regulatory-1280.png) | `/feed?card=nse-106729432` | Dabur: case steps show only "Warning letter". The June import alert in the PDF is not marked (T7). |
| [18-card-regulatory-390.png](18-card-regulatory-390.png) | `/feed?card=nse-106729432` | (as above) |
| [19-company-csb-overview-1280.png](19-company-csb-overview-1280.png) | `/company/542867` |  |
| [20-company-csb-overview-390.png](20-company-csb-overview-390.png) | `/company/542867` | (as above) |
| [21-company-csb-results-1280.png](21-company-csb-results-1280.png) | `/company/542867?tab=results` |  |
| [22-company-csb-results-390.png](22-company-csb-results-390.png) | `/company/542867?tab=results` | (as above) |
| [23-company-csb-owners-1280.png](23-company-csb-owners-1280.png) | `/company/542867?tab=owners` | Targets: "Credit cost Q1FY27 ≤ 50" and "Credit cost Q4FY26 ≤ 50" still Open after those results (T5 class). Ownership bars add up to 100; Peers right. |
| [24-company-csb-owners-390.png](24-company-csb-owners-390.png) | `/company/542867?tab=owners` | (as above) |
| [25-company-heritage-overview-1280.png](25-company-heritage-overview-1280.png) | `/company/519552` | On a phone the Overview is 10,040 px long; most of it is "What to track", dozens of items. |
| [26-company-heritage-overview-390.png](26-company-heritage-overview-390.png) | `/company/519552` | (as above) |
| [27-company-heritage-results-1280.png](27-company-heritage-results-1280.png) | `/company/519552?tab=results` | Scorecard Q2FY27 +21.0% / −36.2% and Q4FY26 PAT +16.7% are wrong (T5 item 1: the standalone seed values). |
| [28-company-heritage-results-390.png](28-company-heritage-results-390.png) | `/company/519552?tab=results` | (as above) |
| [29-company-heritage-owners-1280.png](29-company-heritage-owners-1280.png) | `/company/519552?tab=owners` | Targets: three VAP-share targets for Q2FY27 (38 / 48 / 49), all Open (T5 item 3). |
| [30-company-heritage-owners-390.png](30-company-heritage-owners-390.png) | `/company/519552?tab=owners` | (as above) |
| [31-company-jubilant-overview-1280.png](31-company-jubilant-overview-1280.png) | `/company/530019` |  |
| [32-company-jubilant-overview-390.png](32-company-jubilant-overview-390.png) | `/company/530019` | (as above) |
| [33-company-jubilant-results-1280.png](33-company-jubilant-results-1280.png) | `/company/530019?tab=results` | No price chart on any company yet (T9's `market-data` not run). |
| [34-company-jubilant-results-390.png](34-company-jubilant-results-390.png) | `/company/530019?tab=results` | (as above) |
| [35-company-jubilant-owners-1280.png](35-company-jubilant-owners-1280.png) | `/company/530019?tab=owners` | Ownership skips Q4FY26 and Q1FY26 (seed failures; data gap). |
| [36-company-jubilant-owners-390.png](36-company-jubilant-owners-390.png) | `/company/530019?tab=owners` | (as above) |
| [37-calendar-1280.png](37-calendar-1280.png) | `/calendar` | Overdue promises as on Today, plus AHLUCONT "it would be about 15%." (a fragment with no subject). BANDHANBNK "Amitava Goswami's re-appointment as Chief Compliance Officer" as a catalyst (D30 governance). Two "has informed BSE" texts (Newgen, CGCL) on an NSE site. UCO strike twice. Shivam's rights issue is now once. |
| [38-calendar-390.png](38-calendar-390.png) | `/calendar` | (as above) |
| [39-results-page-1280.png](39-results-page-1280.png) | `/results` | HERITGFOOD Q2FY27 +21.0% / −36.2% (wrong, T5). PRSMJOHNSN Q1FY27 PAT "+2127.0%" from a loss: a YoY % on a loss base should read "loss to profit". Worth a check: MILKYMIST PAT +890.5%, SIEMENS +671.5%. Banks and insurers show revenue "—" (UCOBANK, HDFCLIFE). |
| [40-results-page-390.png](40-results-page-390.png) | `/results` | (as above) |
| [41-system-review-1280.jpg](41-system-review-1280.jpg) | `/system` | **At 390 px the page is 822 px wide**: "AI provider health" rows (e.g. gemini-3-flash-preview "1 / 20 req · 27,920 tok · 11 errors · InternalServerError ...") don't wrap. The 390 shot is 822 wide because of it. |
| [42-system-review-390.jpg](42-system-review-390.jpg) | `/system` | (as above) |
