# Build tracker

The single list of what the platform must do, where each item stands, and what the owner decided.
The full specification is [BLUEPRINT.md](BLUEPRINT.md) (owner's master prompt, verbatim). Pre-launch
audit findings are in [AUDIT.md](AUDIT.md). Architecture as built is in [SPEC.md](SPEC.md). The order of work to go-live is [PLAN.md](PLAN.md).

Status: **done** (built and tested), **partial** (built, gaps listed), **todo** (not built).
Every item is pre-launch: the owner decided everything is built and tested locally before go-live.

## Owner decisions (override the blueprint where they differ)

| # | Decision | Date |
|---|---|---|
| D1 | One API key per provider (no `_1`/`_2` dual-key pool). The cross-provider second check on cards that fail verification stays. | 2026-10-15 |
| D2 | Everything is built, run and fixed on the laptop with the website running locally; go-live only after that. | 2026-10-15 |
| D3 | History (2025-01-01 to today) is filled on the laptop (local SQLite + local R2 folder), then synced to Cloudflare. Only AI token limits apply locally. | 2026-10-15 |
| D4 | Feed uses page-numbered pagination (50 cards a page), not endless scrolling; filters (dates, company, event, sector, size, impact) find older filings. | 2026-10-15 |
| D5 | The blueprint lives in `docs/`; the GitHub repo is private (done by the owner). | 2026-10-15 |
| D6 | Never test the backfill at scale before the 5-company smoke test (506525, 532776, 505192, 500672, 530019) looks right. | 2026-10-15 |
| D7 | No Telegram, WhatsApp or X distribution. EquiSense is a design benchmark only (no name, logo or score). | earlier |
| D8 | Market data from yfinance (no bhavcopy pipeline). | earlier |
| D9 | Cards that fail checks are never hidden: second check by another provider, then published with an Unverified mark. | earlier |
| D10 | Sector-specific footer metrics (bank GNPA/NIM, cement EBITDA/t, telecom ARPU, hotel RevPAR...). | earlier |
| D12 | Data is built in dependency order: company master → market caps → daily price history → filings/memory (2025 baseline, then 2026) → signals. Prices stay on yfinance (D8): its close is split/bonus-adjusted, so close × today's shares gives the day's market cap without a corporate-action adjustment table. If bhavcopy is ever needed, BSE's files are now in the UDiFF format. | 2026-10-15 |
| D11 | Minimise multi-agent runs (token budget); keep docs current so context compaction loses nothing. | 2026-10-15 |
| D13 | AI providers: Groq, NVIDIA, Mistral (Free plan, never pay-as-you-go, no phone verification), Z.AI, Google Gemini (free tier) and Workers AI. Prefer established models to the newest; check `models` / `ai-check` and the provider's docs before changing one. | 2026-10-16 |
| D14 | API keys only in `C:\Users\Quali\insiders-keys.ps1` on the laptop: never in chat, logs or the repo, even though it is private. | 2026-10-16 |
| D16 | Stick with the blueprint: every material filing gets the full Pass 2 analysis (no cheap one-call tier for routine filings). | 2026-10-16 |
| D17 | Repeat submissions: skip only an exact body match, or a near-identical body with every number the same, from the same company within 3 days; never corrigenda, revised or corrected filings; keep the skipped filing as DUPLICATE linked to the original. | 2026-10-16 |
| D18 | Backfill with 5 AI workers (`PIPELINE_WORKERS=5`, was 3). The gateway keeps pacing each model to 95% of its free limits; watch the 429 share and the daily ceilings on the System page and go back to 3 if extra workers only reach the daily quota sooner. | 2026-10-16 |
| D19 | OpenRouter added with one account: two free models (Nemotron 3 Ultra, Nemotron 3.5 Super VL) as spares under its shared daily allowance. No extra accounts at any provider. The owner bought $11 of credits once (2026-10-16), which raises the free models from 50 to 1,000 requests/day, so in the backfill route (`pass2_bulk`) they now take a regular weighted share (weight 1 each) and stay spares elsewhere; only ":free" models are configured, so the credit is not spent (a test enforces it), and the key's spending limit should be kept minimal. Checked and not used: Cerebras (card required, $5 credit expiring in 30 days, no free tier after), Hugging Face (no free credits), GitHub Models (retired July 2026), SambaNova (free but 20 requests/day per model; possible later). | 2026-10-16 **Amended 2026-10-16 (owner):** Nemotron 3 Ultra is a spare on every route, superseding its weighted share in the backfill route (the round-0 audit found 53% of its cards wrong against 20% for Nemotron 3 Super); 3.5 Super VL keeps its share. | 2026-10-16 |
| D15 | The laptop's Claude Code session is the main engineer (it reaches BSE and sees real logs); `CLAUDE.md` holds the rules and status every session reads. The Worker is named `insiders` (https://insiders.reply-bd3.workers.dev). | 2026-10-16 |
| D20 | One card per company per results quarter (F3): when several different documents carry the same quarter's results, the fullest one gets the card and one timeline entry; the others are recorded as linked to it ("also filed as ...", with their PDFs) instead of separate cards. | 2026-10-16 |
| D21 | Thinking for the reasoning models: measured, then decided by the owner (2026-10-16) to switch it off for Pass 2 on every route, and to re-measure it as the last item when everything is live and up to date (PLAN 14). Measured on 20 audited filings, same model and prompt, alternating order: thinking on 150–760 s a card and 1 in 3 timed out at 300 s; off 23–68 s, grounding scores similar. | 2026-10-16 |
| D22 | A timeline tier before the card tier (owner, 2026-10-16): routine filings need no card. Dividend recommendations on their own, postal-ballot, AGM and voting results (Reg 44 scrutinizer reports) and promoter encumbrance declarations (Reg 31) are routed by the primary filter (`[[timeline]]` rules in `taxonomy.toml`) to a cheap model that writes one dated timeline line; it sends the filing back for a full card when it is consequential (a pledge created or invoked, results, a fundraise or other business in the same letter, resolutions that failed or drew a large vote against), and defaults to a card when unsure. Management changes keep their card (deemed material under Reg 30, Para A); the same event filed in other words (BSE takes one submission per subcategory) is one card or one line (`similar_timeline_entry`: within 3 days, at least half the content words alike). On the 1,166 filings of the ten smoke-test companies, 85 (7%) go to the timeline tier (65 voting results, 13 dividends, 7 pledge declarations). Blueprint Module 40 (institutional dissent in voting results) is not computed for these until it is rebuilt as a deterministic check on the scrutinizer report. | 2026-10-16 |
| D23 | **Code owns every number; the model quotes the filing** (owner, 2026-10-16, agreed in full). Three parts, built together: (1) a deterministic memory seed with no AI call (`seed-memory`): results XBRL per quarter from BSE's results archive and shareholding XBRL from NSE, so a card is written against real history instead of an empty dossier; (2) every `what_happened` fact carries `quote`, the filing's own sentence, checked in code: a fact whose quote is not in the filing is dropped and the card goes for a second opinion, a fact with no quote is reported (holding those would send every card to a second provider while the models learn the field); (3) the proportions the model may use are computed in code and injected as a SCALE block (market cap, TTM revenue, latest quarter, net worth, net debt or cash, order book, and each large ₹ crore amount in the filing as a share of them), with the filing text fenced in `<filing_text>` as data and never instructions, and a rule that an event under about 2% of those denominators is said to be small. | 2026-10-16 |
| D24 | **One paid provider, for the backfill only** (owner, 2026-10-16): a prepaid DeepSeek balance, `deepseek-flash` (V4.1-Flash) on `pass2`, `pass2_bulk` and `pass2_long` at weight 8, with `thinking = { type = "disabled" }` on every entry, because DeepSeek enables thinking by default at high effort and bills reasoning tokens as output (D21 again). Costed from the usage already recorded in `provider_usage` for the smoke-test workload (1,889 requests, 20.38M input, 5.07M output): $6.10 off-peak, 3.5 cents a card; `ai-check` answers in 1.0 s against 20-60 s on the free reasoning models, and the 1M window means no filing is ever too long for it. Off-peak is every hour outside 01:00-04:00 and 06:00-10:00 UTC on weekdays, so overnight runs here are always off-peak and half price. The steady state stays on free tiers: the same work market-wide would be $150-200 a month (breaking the $0 rule), and 21 months of history for all 5,111 companies about $3,000. No card is on file, so the top-up is the spending cap. Prefix caching is automatic and bills a hit at 2% of a miss, so `pass2_user.md` now puts the blocks that repeat across a company's filings (memory, peers) before those that change with every filing (the header, SCALE, the filing text): measured 4,480 of 4,757 prompt tokens cached, 94%, on the second call of a pair. | 2026-10-16 |
| D25 | **Pass 2 re-weighted from audit round 1, and a fixer may no longer invent a change** (owner, 2026-10-16). Round 1 (98 cards, `docs/audit/round-1.json`) measured the share of cards wrong by writer: GLM-4.5-Flash 0%, Nemotron 3 Super 28%, GLM-4.7-Flash 33%, DeepSeek-Flash 47%, ministral-14b 67% and 3.6 issues a card. So ministral-14b comes off `pass2`, `pass2_bulk` and `pass2_long` altogether (it was already a spare and still wrote 18 of the 98 cards, and it was the worst writer in both rounds), GLM-4.5-Flash rises from 2 to 4, and the paid route drops from the 20 it was raised to for backfill speed to 3, below Nemotron Super; it keeps 4 on `pass2_long`, where its 1M window is the reason it is there. Nemotron Super stays the largest share because free GLM allows one request in flight per key, so a larger share there would serialise pass 2. The same round found the error classes that would not fall were ours: `xbrl_key_numbers` overwrote a correct YoY with one computed from the wrong XBRL comparative (Kanoria Q1FY27 revenue "+129% YoY" rewritten to "+1.5%", the implied year-ago being ₹454 Cr against a real ₹201 Cr), and `fix_change_percentages` computed a change from a figure the model had misread (₹458 Cr for 457.86 million, giving "+965.1% YoY"). Both now check the figures against the filing first: an XBRL YoY is taken only when the year-ago figure it implies is in the filing too, and a change is recomputed only when the filing states both sides. The direction flip in the same function compared lowercase against a value the model writes in capitals, so it had never fired. | 2026-10-16 |
| D26 | **Scanned and unreadable pages are OCR'd on the CPU with RapidOCR, not by a vision model** (owner, 2026-10-17). RapidOCR (`ocr.py`, the optional `[ocr]` extra) is tried first and the `vision` route is the fallback when it is not installed, fails or reads nothing, so without the extra the pipeline behaves as before. Its text boxes are put back into lines by vertical centre, left to right, so a table row reads label then figures. Pages render at **200 dpi**: on the same 17 NSE pages (521 figures) 150 dpi read 85.4%, 200 dpi 87.1% and 300 dpi 84.3%, all about 3 s a page here; the laptop's benchmark agrees (200 beats 150 by 3.6 points, 300 adds nothing). On a GitHub-hosted runner it installed in 16 s and averaged 4.9 s a page (`ocr-probe.yml`). Because a page costs CPU and no quota, `MAX_OCR_PAGES` defaults to **20** with RapidOCR and stays 6 on the vision route, where every page is a free-tier request; the variable still overrides both. | 2026-10-17 |
| D27 | **Aim: the whole chain on GitHub** (owner, 2026-10-17): collection to display without the laptop, with the repo made public (unlimited standard-runner minutes), keys as GitHub secrets and an external free scheduler to start runs on time. Probed from a GitHub-hosted runner (`runner-probe.yml`, Microsoft, Des Moines US, 2026-10-17): NSE answered every call the pipeline makes (Integrated Filing list and XBRL, results list, shareholding, announcements and their PDFs) and so did Yahoo; **BSE refused all nine calls with HTTP 403** (announcements, results archive, quote header, scrip list). The BSE half stays on an Indian connection until that is solved; the owner will re-test once the repo is public. | 2026-10-17 |
| D29 | **A page of figures is read by local OCR first, the text layer second** (owner, 2026-10-17). A page printing 15 or more amounts (19% of 10,957 cached pages: statements, notes, segment and rating tables) goes to RapidOCR, and OCR's rows are checked cell by cell against the text layer (`ocr.merge_with_text_layer`): where a line of the PDF's own text carries exactly the row's figures, that line is the row (exact characters, every nil); otherwise the two readings are aligned, a nil OCR dropped is put back and a figure OCR garbled ("8L6" for 978) is taken from the layer. A scan's invisible OCR layer (render mode 3) fills gaps but never overrules RapidOCR. A sideways page's text layer is rebuilt in rows from its words (`extract.upright_text`). Prose pages keep the text layer; the duplicate check compares text layers only; the vision route is never used for this. On the seven complicated pages: rows intact 77.4% (text layer 48.9%, OCR alone 52.6%, vision route 76.6%), figures in column order 94.9% (62.0 / 90.5 / 84.7%); on the 195 results figures 98.5% on the right row and column (OCR alone 99.0%, text layer 80.0%): the one figure lost was on a scan whose own OCR text is drawn beneath the page image, which was then taken for the PDF's text and its garbled label ("Total e.-.:pcnscs") kept; a page an image covers is now treated as a scan (`SCAN_COVER`). Up to 12 figure pages a document, about 4 s each; cached entries with a figure page are read again once (`local_ocr` marker). Still open: nils on scanned grids (Kanoria's voting grid keeps 4 of 20 rows against the vision route's 14). | 2026-10-17 |
| D28 | **Raw answers kept, and one written routine for bad data** (owner, 2026-10-17). Every JSON answer from BSE and NSE (announcement pages, results archive, quote header, scrip list, NSE lists) is saved exactly as received before it is parsed, under `raw/{bse,nse}/{endpoint}/{day}/` in the object store (`raw.py`; `SAVE_RAW=0` turns it off), so a parsing or cleaning fix is re-run over what was received rather than asked for again. PDFs and XBRL were already kept by the text cache. `docs/DATA_QUALITY.md` sets out the cleaning stages and the routine when data is wrong: name the class, fix it in code with a test, re-run only those filings, compare on the same filings, never edit stored data by hand. | 2026-10-17 |

## Optional, not adopted (cost)
- TypeSafe AI "Jev" (typed decisions with calibrated confidence) would suit the Pass 1 gatekeeper,
  but it has no free tier; it can be added as a provider in `providers.toml` if free credits appear.

## Price source fallback (decide after the first `market-data --all`)
`market-data` records which companies Yahoo has no price for (kv `market:coverage`, System page,
CLI `yahoo_missing`). If the gap matters, candidates in order:
1. BSE UDiFF bhavcopy (`BhavCopy_BSE_CM_0_0_0_{YYYYMMDD}_F_0000.CSV`: FinInstrmId = scrip code,
   ClsPric, PrvsClsPric, TtlTrfVal) into the same `data/prices` store. Raw (unadjusted) closes, so
   splits/bonuses then need BSE's corporate-actions CSV for adjustment factors.
2. Share counts for market cap: BSE's scrip header data (TotalShares, MktCapFull) or the
   shareholding-pattern XBRL total, for companies where Yahoo has no share count.

## Laptop smoke test: findings and fixes (2026-10-16)
| Finding | Fix | Status |
|---|---|---|
| Yahoo priced 10 of 5,111 companies (numeric `500325.BO` no longer served) | `yahoo.py`: try `SYMBOL.BO`, then `SYMBOL.NS`, then `SCRIP.BO` | fixed: `market-data --all` priced 4,988 of 5,111 (97.6%), `price-history` stored 4,995 |
| Retired or tier-blocked models (404/410/403) | models replaced; 410 disables; key-level 403 disables the provider, a tier 403 only the model | fixed |
| Endless 60 s waits when every provider was busy | stop after 4 such filings in a row | fixed |
| Windows paths and a temp-file race in local storage | lexical key check, per-thread temp files | fixed |
| Worker refused `learning/` objects | prefix allowed | fixed |
| Workers AI 502 locally | `remote: true`, wrangler login, workers.dev subdomain; fp8 8B model; object replies stringified; start the dev server with `CF_REMOTE_BINDINGS=1` (vite.config.ts overrides `remote: true`) | fixed: `ai-check --provider cloudflare` passes both models |
| Backfill saved a company only when its whole history finished | saved every 5 filings per company, under a commit lock | fixed |
| Repairs on `dossier_delta.ownership.period` (null period) | an ownership block without a quarter-end is dropped | fixed: 0 such repairs in the first 10 min after the fix (17 before) |
| Tests failed in the half hour after midnight IST | test clock shifted in that window | fixed |
| `ministral-14b-2512` sometimes returns no JSON | watch after the restart | open: 1 in the first 10 min (the repair call recovers it) |
| Gemini free-tier limits (Google publishes no table) | per-minute limits read from Gemini's own 429 quota detail: 15/min for 3.1 and 3.5 Flash-Lite, 5/min for 3.6 Flash; daily limits stay guesses (a per-day 429 retires the model until midnight Pacific and shows its value on the System page) | per-minute fixed; per-day open |
| Every company in sector `default` (no sector lens): BSE's scrip list now returns `INDUSTRY: null` for all 5,111 | `sync-companies` reads each company's classification from BSE's quote header (`ComHeadernew`: Sector > Industry > Group > Sub-group), once per company; lenses match the most specific level first; a stored sector is never overwritten with `default` | fixed |
| Lakh figures written as crore (Kanoria Q3FY25 "loss ₹2,863 Cr" from "(INR in Lakhs)"; 100x) and passed grounding, which matched any scale | the pass-2 prompt names the filing's declared unit and the conversion; grounding requires ₹ crore figures to match a single-unit filing at that unit's scale (the real card now scores 0.30 with both headline amounts flagged, so it goes to the second check) | fixed |
| One event analysed up to 5 times (SML Mahindra's CEO change filed 5 times in 8 minutes, once per BSE subcategory; Shivam's NCD approval twice) | `duplicates.py`: within 3 days and the same company, skip only an exact body match (covering letter and whitespace stripped) or a near-identical body (Jaccard ≥ 0.9) with every number the same; never corrigenda, revised or corrected filings; kept in the ledger as DUPLICATE linked to the original (no AI call, no card). Owner's rule, replacing a looser 85%-overlap rule that could skip same-template filings with new numbers | fixed |
| Wrong-scale and lens-less figures already in the 5 companies' memory | smoke test reset: their cards, catalysts and dossiers deleted and all 543 filings requeued, then rebuilt on the fixed code | done 2026-10-16 |
| Duplicate rule on the 543 smoke-test filings (text without OCR) | 91 skipped (16.8%), all exact repeats of one document under another BSE subcategory (results as "Financial Results" and "Outcome of Board Meeting"; one board outcome attached up to 8 times; annual report as "AGM"); spot checks of differently titled pairs found identical multi-page texts. The old 85% rule would have skipped 26 more, mostly same-template letters with new content (daily open-offer updates, NCD allotments, a re-worded CFO change) | measured 2026-10-16 |
| Smoke-test rate | 15 filings (9 cards, 6 not material) in the first 9.5 min, about 95 filings/hour with 3 workers | measured |
| Figures written beside their own unit ("INR 5445 Million") read at any scale when the filing mixes units (Kanoria RPTs "₹5,445 Cr" for ₹544.5 Cr) | grounding reads each source figure in the unit written after it; the prompt warns when units are mixed (be781a0) | fixed |
| **Review of the site, 2026-10-16 ~03:00 (38 cards), fixes to be batched** | | |
| F1: Novartis statements are "('l in million)": the ₹ sign is mangled in the PDF text, so no unit is declared and every results figure is 10x (revenue "₹839 Cr" for ₹83.9 Cr, RPT "₹3,000 Cr" for ₹300 Cr) | accept a mangled currency mark in a parenthesised "( … in million/lakh)" header | open |
| F2: results for the quarter ended 31 Mar 2025 (filed May 2025) labelled Q1FY26 instead of Q4FY25 by the model; memory is keyed by period | derive the quarter from the statement's "quarter ended <date>" and correct the model's label | open |
| F3: one results announcement filed as 3 different documents (Novartis, 9–10 May 2025) gives 3 near-identical cards | not exact repeats, so D17 keeps them; one card per company per results quarter, others linked (D20) | open (decided) |
| F4: arithmetic in prose not checked ("85% + 26% = 111% fully diluted"; "₹585 Cr + ₹555 Cr (₹1.14B total)") | look for a deterministic check of sums and percentages stated in text | open |
| F5: raw rupees shown as ₹ ("₹4,135,498,900" for ₹413.5 Cr); the card was already marked Unverified | prompt and validation: amounts in ₹ crore | open |
| F6: a draft tax order tagged ORDER WIN | event-type check (tax/penalty words) | open |
| F7: the same dividend payout derived differently on two cards (₹308 Cr, ₹125 Cr; about ₹62 Cr from shares outstanding) | derived payouts from shares outstanding in code, not by the model | open |
| F1 fixed in b1bd8a7: mangled "( … in million)" headers declare the unit, a figure keeps its written unit where it recurs bare, crore figures match only at real conversions; re-grading flags all 7 wrong Novartis cards | | fixed |
| F8: the score treats a quantified *estimate* as the catalyst's size ("Estimated April revenue … is 19% of revenue" passes the size gate) | size from deals/orders/capex only | open |
| F9: an invented comparison base ("Passenger share 74% vs 79% YoY", 79% not in the filing; already listed as not found) | — | note |
| F10/F17: open-offer letters tagged "Rights issue"; the open offer stored as a "Fundraise" deal | event and deal-kind rules for open offers | open |
| F11: memory repeats facts: each operating note twice (with and without a date prefix); group entities doubled ("(Target Company) (Target Company)") | normalise before merging notes and entities | open |
| F12: follow-up marks "Approval met" while its own text says the approval is pending | an approval resolves only on a clear approval verb | open |
| F13: one pending approval (CCI) listed 5 times in different words | merge near-identical pending approvals | open |
| F14: a post-offer *projection* (promoter 85%) stored as the actual May-2025 shareholding; promoter 85% + DII 40.76% > 100% | ownership only from shareholding filings (XBRL) or with a sanity check | open |
| F15/F18: prose comparisons not checked: "₹1,140 Cr exceeds ₹1,627 Cr"; "PAT ₹68.7 Cr vs ₹55.56 Cr, down 20%" (up 24%) | deterministic check of "exceeds/up/down N%" between two amounts in one sentence | open |
| F16: EPS shown as "0.36 INR_PER_SHARE" | display unit labels | open |
| F19: the math check says "unknown input 'Q3FY25_EBITDA'" for input `q3fy25_ebitda`: names are case-sensitive, so the item is "Not checked" | case-insensitive input names | open |
| F20: EBITDA equal to PBT (₹0.75 Cr each, SML Q3FY25): the model likely copied PBT; the 0.23% margin follows | EBITDA ≥ PBT + finance cost + depreciation when those are stated | open |
| F21: company backfills are not recorded as runs (System: "No runs recorded", "0 of 653 days") | record backfill-companies runs | open (display) |
| F22: OpenRouter shows "No daily limit configured"; its shared 1,000/day provider limit is not shown | show provider-level limits | open (display) |
| F23: error rates cost throughput: NVIDIA 21 timeouts in 87 calls, Z.ai 23 x 429 in 44, ministral-14b 12 invalid JSON in 76, OpenRouter Ultra 3/9 no JSON, Super VL 5/11 empty | Cause probed: the Nemotron models think before answering (NVIDIA: 37 s and ~1,400 thinking tokens for a short card), so long filings hit the 180 s timeout or the token cap and answer empty. Safe change made: NVIDIA timeout 300 s, token caps raised (Ultra 12,000, Super VL 8,000, ministral-14b 6,000). Thinking off is 2–4x faster (8–16 s, valid JSON without JSON mode; with JSON mode NVIDIA returns "{}") but may cost accuracy on units and comparisons: owner decision (PLAN 1d) | partly fixed; decision open |
| Working: card full analysis (key numbers, math working, memory signals, track-next, score breakdown, point-in-time price), company page sections, memory drawer over the feed, PDF verifier beside the card, Needs-review list with reasons, sector lenses, size labels, duplicate skips | | ok |
| **Second smoke test (542867, 500338, 519552, 532811, 543533), first review 2026-10-16 03:35 (25 done, 11 cards)** | | |
| F24: 10x figures in a card's body went out unchecked: Ahluwalia Q3FY25 (lakh table) EBITDA "₹756 Cr" on ₹952 Cr revenue at a 7.9% margin (₹75.6 Cr), PAT "₹495 Cr", finance cost "₹145 Cr"; eMudhra QIP "₹1,930 Cr". Grounding flagged every one, but the second opinion ran only when under 70% of the numbers matched (76% and 74% here) | Blueprint §4: any ungrounded number gets a second opinion. Any unmatched amount (not a percentage) now sends the card to another provider, with a hint on converting from the table's unit; it counts as corrected only when no amount is left unmatched. The cards already written are re-run after the test | fixed |
| F25: a Prism Johnson results PDF failed on the vision route (Z.ai and Mistral paced; Gemini Flash-Lite and Super VL empty) | retried by the next run (attempt 1) | watch |
| F26: results-type cards tagged OTHER (Ahluwalia and eMudhra board outcomes carrying results) | event-type rules, with F6 | open |
| F27: the same detail differs between cards of one event (eMudhra's Two95 deal "USD 1.01M" vs "US$10.1M"); prose period "Q4FY25 (Dec-2024)" on a tax-refund card | — | note |
| F28: the 10x figures reach memory and the company page ("PAT down 30% YoY to 495.12 Cr" under The bad; a JV profit note as ₹6 Cr and, from a later copy of the results, ₹0.06 Cr); Ahluwalia's results filed 3 times (16:49, 16:52 exact repeat skipped, 18:12 a different document) give two timeline entries (F3); "₹494 Cr → ₹418 Cr (+15% YoY)" for a fall (F15) | re-run of the F24 cards replaces their memory entries | open |
| **Second review 2026-10-16 04:20 (110 done: 60 analysed, 41 not material, 6 duplicates, 3 failed; ~108 filings/hour)** | | |
| F29: Heritage Foods' scanned statements declare "(,\mount in millions of Z unless otherwise stated)" / "(Amount 111 millions oft …)", which no unit pattern read, so its Q4FY25 card says PAT "₹205 Cr" (₹20.5 Cr) and the JV "₹85 Cr" (Rs.8.50 Crores); the second opinion could not fix it (UNRESOLVED) | "Amount in <unit> of" with the OCR's mangled "Amount"/"in" now declares the unit, so the prompt names ₹ million and the check holds those figures | fixed |
| F30: Prism Johnson's Q4FY25 card shows PAT ₹47.67 Cr (the Q3 column of the same statement) and "net worth ₹2,331 Cr"; its presentation card labels FY25 revenue ₹6,830 Cr as "Q4FY25" | the new second-opinion trigger (F24) sends both to another model; column choice in the prompt to look at with the case studies | open |
| F31: empty answers with HTTP 200 (thinking uses the whole token budget): NVIDIA Super 33 invalid of 93 calls (29 empty), OpenRouter 21 of 58, ministral-14b 9 no-JSON of 135; all 3 failed filings are long documents (pass2_long, every model invalid or busy) and are retried by the next run | evidence for the thinking decision (PLAN 1d): about a third of Nemotron calls are wasted | open (owner) |
| F32: the local site (Vite dev server, remote bindings) exited at ~05:09 without printing a reason; the backfill retried for ~10 min, then stopped (11 filings left PENDING, nothing lost). Restarted both at 05:31 (`backfill-companies-20261016-0531.log`), now on the F24 and F29 fixes; a watcher checks the site every minute | for unattended runs, restart the site automatically (a loop around `npm run dev`) | open |
| F33: the XBRL fast path never fired: BSE's announcement rows have no XBRL link (`XML_NAME` is "ANN_<scrip>_<id>" with no file), so all 148 results filings went to the model alone, and every 10x results figure (F1, F24, F29, F30) followed | results filings now take their XBRL file from the company's results archive (`Result_Arch_ng`, read once a run): the statement's quarter, consolidated when filed, the timely revision. Exact crore figures go on top of the prompt and into memory. On the smoke-test results with text: 53 of 55 found and confirmed against the PDF (one has no stated quarter, one consolidated file not in a standalone-only presentation). Real BSE file kept as a test fixture | fixed |
| F34: no check that a quarter's figures fit the company (PAT "₹495 Cr" where recent quarters made ₹40–60 Cr) | scale check: a profit line above the quarter's revenue, or a figure over 5x the company's recent quarters (revenue under a fifth), holds the card and sends it to the second opinion | fixed |
| F35: a 10x figure still needs a second model to fix it, and may survive it | unit-slip correction in code: in a filing with one declared unit, a card's ₹ crore amount that matches no source but matches exactly one statement figure read at a wrong unit is rewritten (card text, key numbers, timeline, memory metrics) before the checks; not for amounts under ₹10 Cr or within 0.5% of a real figure (a rounding). On the saved smoke-test cards it corrects 18 of 177 (Novartis ₹839→83.9 Cr, Jubilant ₹18,137→1,813.7 Cr, Ahluwalia EBITDA ₹756→75.6 Cr, eMudhra QIP ₹1,930→193 Cr, Heritage PAT ₹205→20.5 Cr); recorded on the card as `grounding.unit_fixes` | fixed |
| F36: margins not checked against their figures (EBITDA ₹756 Cr on ₹952 Cr "at a 7.9% margin") | margin-fit check on the reply's metrics and the card's key numbers (over 1 pp off holds the card and asks a second model) | fixed |
| F37: "KPI check missed: Cement EBITDA/tonne ₹701 in Q2FY26 is below the >=700 target for Q3FY26" (owner): 701 meets the target, and a Q2 figure cannot settle a Q3 check | the model's KPI verdict is checked in code against the watch item's target and quarter, in memory and in the follow-up signal; an earlier quarter's figure keeps it pending | fixed |
| **Card-vs-PDF audit 2026-10-16 ~06:00: all 177 cards of both smoke tests checked figure by figure against their filings (docs/audit/)** | 95 WRONG, 56 MINOR, 26 OK; classes: invented 147, arithmetic 89, unit scale 88, wrong period 64, signal verdict 55, wrong column 43, event type 34, direction 29 | |
| F38: QoQ changes labelled YoY; PBT or segment results called EBITDA; previous-quarter column as current (SML, Prism, Heritage, Novartis) | key numbers from XBRL with exact YoY; YoY/QoQ from the year-ago and previous quarters' XBRL files (BSE's files carry none); a mislabelled % flagged | fixed |
| F39: signal verdicts wrong (D/E 0.6x "missed" a <=2 target; "not disclosed" called missed; concerns labelled approvals; refund amount as a net-worth target; dividend and open offer as dilution; bank other income as low-quality beat; overdue guidance repeated on every card) | checked in code (watch_verdict, plausible targets, issuance-only dilution, lenders exempt, flagged once) | fixed |
| F40: event types (results typed OTHER, open offer as rights issue, tax demand as order win, Reg 29 gift as M&A) | rules from the filing text; 11 of 12 changes on the audited cards match the auditors | fixed |
| F41: invented facts, prose arithmetic, standalone/consolidated mixing, wrong table row, OCR losing brackets, stale market cap | see docs/audit/README.md, PLAN 1f | open |
| Both smoke tests reset 2026-10-16 06:30 for a rebuild on the fixed code (1,088 filings PENDING) | | pending rebuild |
| F42: accuracy gate built (gate.py, from the reference repo review, docs/REFERENCE_REVIEW.md): garbled-scan marker (3+ OCR-mangled number tokens at 0.25%+; all 6 filings it flags on the audited set were WRONG, none OK), crore amounts of 1e7 or more rejected, a deal size equal to the company's revenue, net worth or share capital dropped, a terminated deal marked cancelled, a fundraise size checked against shares x price, and a human hold list (`pipeline/config/card_holds.txt`, `news_id \| reason`, typos stop the run). A card is never hidden: held cards are published marked for review, with the reason, and a second model is not asked for what it cannot fix | on the 177 audited cards it flags 6 (all WRONG), 0 false alarms; most of the audit's error classes are handled by earlier fixes, the rest need the quote requirement (below) | built |
| F43: invented facts (147 of the audit's issues) have no code check; a word-support score (share of a sentence's content words found in the filing) separates them roughly (median 0.44 invented vs 0.80 others, 8 examples) but flags 18% of good sentences at 0.5, too noisy to use | the reference repo's answer is a verbatim quote per claim, checked in code: needs a prompt and schema change (model returns a quote for each fact and number as written, code converts); decision for the owner after the rebuild's audit | open (owner) |
| F44: Novartis India SPA card (19 Feb 2026, shown by the owner): "70.68% sold for ₹660 Cr", "14% of market cap, 85% of net worth", "Verified after a second check". Filing read in full (6 pages, nothing truncated). ₹660.09 Cr (INR 660,09,25,235) is only the instruments the seller subscribes to at Closing, set off against the price; the consideration is the buyers' shares x price, WaveRise 13,938,382 x ₹860.64 + ChrysCapital 2,547,189 x ₹701.25 + Two Infinity 965,109 x ₹701.25 = ₹1,445.89 Cr (implied ₹2,046 Cr for 100%). The figure is in the filing, so the number check passed it: the checks prove a figure exists, not what it means. Also on the card: "sold" for an agreement that closes later, an "open offer price" the filing does not state, "NCLT" approvals, a "currency risk premium", and "no EBITDA of the target" for the listed company itself | the pass-1 gate and the text were fine (right document, all text); the fault was pass 2's choice of amount and no check of meaning. Fixed: the model lists each buyer's shares and price and code computes the consideration (and replaces a stated amount that is more than 3% off); a deal amount that appears in the filing only in a sentence about instruments, set-off, escrow or guarantees is flagged and sent to the second opinion; the badge now says "Numbers re-checked by a second model" (it never verified meaning). Still open: lifecycle wording ("sold" vs "agreed to sell"), invented rationales | partly fixed |
| F45: cards for routine filings (final dividend recommended, director re-appointed by postal ballot, MD/CEO appointed, "no pledge" declared) and several cards for one MD/CEO change (SML Mahindra, three differently worded filings), reported by the owner. The documented primary filter (blueprint §5.2) lists only housekeeping and compliance notices; these were never on it, and "News Paper Cutting" (with a space) slipped past the newspaper rule | newspaper rule fixed (13 clippings out of the ledger); timeline tier (D22); same-event dedupe for management and governance events | fixed |
| F46: the owner's four-bucket filing list (2026-10-16) against the primary filter. **Hard drop (7 categories)**: share certificates (Reg 39(3)), newspaper clippings, Reg 74(5), trading window, Reg 7(3)/40(9)/76 certificates, shareholder tax and KYC reminders, Reg 30(5) contact details: all dropped; added this round: the TDS/PAN/KYC/nomination/unclaimed-dividend reminders, Reg 30(5), Reg 39(3), Reg 47, PCS certificates, and the "News Paper" spelling. **Calendar only**: board-meeting intimations, record dates and book closures go to the calendar; analyst-meet schedules dropped; voting results and scrutinizer reports go to the timeline tier (D22) with a card when a resolution fails or draws heavy dissent. **Conditional**: price/volume clarifications dropped unless they mention a media report, rumour, acquisition, probe or Reg 30(11) (kept: CSB Bank, Heritage, Novartis); nil statements of deviation dropped (others go to Pass 1); ESOP grants, allotments and trust transfers dropped (preferential, rights, QIP and warrant allotments kept; the Reg 24A secretarial report is still dropped whether or not it lists observations, and an unusual surge of investor complaints or an adverse governance remark in the Integrated Filing (Governance) is not detected). **Core memory**: results, orders, capex, M&A, ratings, auditor/CFO/MD exits, SAST and pledge events, as built. Dual-listing dedupe by ISIN is not needed (BSE only). On the ten companies' 1,166 filings the new rules remove 65 more (16 clarifications, 39 ESOP, 10 reminders and contact details) on top of the 13 clippings | rules and tests (314 pass) | done, two conditional gaps open |
| F47: Z.ai text model (owner decision, 2026-10-16): GLM-4.5-Flash replaces GLM-4.7-Flash on Pass 1 and Pass 2 (4.7 stays on the long-document route: 128K against 200K context). Head to head: tiny calls 4.5 answered 20 of 20, 4.7 only 4 of 20 (1302 concurrency, 1305 overloaded, 1234 server error); real Pass 2 prompts 4.5 answered every filing so far at 12–96 s with grounding scores 0.44–0.95, 4.7 refused or failed on all but the first | `providers.toml` | done |
| F48: the owner's XBRL tier guidance (Tier 1 parse from XBRL only, Tier 2 XBRL numbers plus selected PDF pages, Tier 3 PDF only) checked against the pipeline. Built: results XBRL from the results archive (F33), shareholding XBRL parser, Reg 30 hybrid trigger by event rules. **Gaps found: (1) the shareholding-pattern XBRL fast path has never run: BSE's announcement rows carry no XBRL link, so every shareholding filing is dropped as noise (none is in the ledger) and ownership history comes only from model-read text; (2) results day: the PDF outcome arrives first and the XBRL up to 24 hours later, and a card made before the XBRL is listed is never revisited; (3) event-based XBRL for Reg 30 events, voting results, related-party transactions and insider/SAST disclosures is unverified: no source found yet.** The claim that BSE and NSE publish an XBRL twin for almost every structured filing is not confirmed for BSE announcement rows (0 of 1,166 had a link) | PLAN 15–17 | open |
| F49: the writer model decides the error rate (round-0 audit joined to each card's model, old code, thinking on for Nemotron): Nemotron 3 Super 55 cards, 20% wrong, 29% fully right, 1.4 issues a card; Nemotron 3 Ultra 30 cards, 53% wrong, 3.5 issues; GLM-4.7-Flash 30 cards, 73% wrong, 4.9 issues (22 wrong-column errors); ministral-14b 52 cards, 81% wrong, 5.9 issues (51 unit slips, 64 invented); VL 6 cards, 33% wrong; Gemini Flash 4 cards, 50% wrong. The backfill weights gave Super only 29% of the traffic | Pass 2 weights now Super 5 (pass2, pass2_bulk) and 3 (pass2_long), ministral-14b a spare on all three routes, GLM-4.7-Flash 1 on the long route; the audit tally prints a per-model table each round and the weights follow it. Nemotron 3 Ultra made a spare on every route by the owner's decision (D19 amended) | done |
| F50: NSE probed from the laptop (owner's question, 2026-10-16), read-only, polite pacing, hard stop on 401/403/429. **It works and hands us raw XBRL our own parser reads unchanged.** `/api/corporate-share-holdings-master?index=equities`: HTTP 200, 1,369 rows, each with a direct `.xml` link (`nsearchives.nseindia.com/corporate/xbrl/SHP_*.xml`); Prism Johnson's file parsed to promoter 74.87%, FII 2.83%, DII 5.59%, 73,299 retail holders, Q2FY27. `/api/integrated-filing-results?...&type=Integrated Filing- Financials`: HTTP 200 with `xbrl` (raw .xml), `ixbrl`, `qe_Date`, standalone/consolidated and revision fields; one file parsed to RESULTS Q2FY27 STANDALONE with 44 metrics. The warm-up visit answered 403 but the APIs answered anyway (same as the reference repo's note). **Coverage measured against NSE's own equity list (2,605 symbols): 2,480 of our 5,111 companies are on NSE (49%); by market cap, 77% of those above ₹100 Cr, 96% above ₹1,000 Cr (the owner's first backfill band, PLAN 1c), 99% above ₹10,000 Cr. The BSE-only remainder is almost all micro caps (2,230).** BSE's `TabResults/w`, suggested as the BSE-side route to structured results, returned an empty body for every parameter set tried | NSE as the structured source for shareholding and integrated results, BSE's `Result_Arch_ng` as the fallback for BSE-only companies: PLAN 15–17 rewritten | probed, build pending |
| F51: memory seeded for all ten smoke-test companies with no AI call: 143 results quarters (XBRL from BSE's results archive, consolidated preferred) and 120 shareholding quarters (XBRL from NSE), with provenance per figure (`xbrl:res:<scrip>:<period>`). Ahluwalia's Q3FY25 reads revenue ₹951.96 Cr, EBITDA ₹84.43 Cr, PAT ₹49.51 Cr, and its ownership shows FII 12.07% → 14.05% across six quarters | `seed.py`, `nse.py`, `seed-memory` | done |
| F52: the seed's cross-check (the XBRL figure against NSE's own promoter percentage, refusing to store either when they differ by more than 0.5 pp) caught a parser bug on six CSB Bank quarters: the promoter group's **locked-in** shares, 80.45% of its own holding, were read as the promoter's 49.72% shareholding. Percentages of a holder's own stake (locked-in, encumbered, assuming full conversion) are now excluded; the real file is a regression fixture and the 15 quarters re-seeded clean | `xbrl.py` | fixed |
| F53: the quote rule measured on its first real cards. Dropping a fact for a missing quote alone deleted true figures composed from a results table (SML's "Q3FY25 PAT ₹0.53 Cr, down 80% YoY and 98% QoQ" is right, but no one sentence says it): a fact is now dropped only when neither its quote nor its figures are in the filing. The prose drops were then checked against the filing itself and were correct: word overlap with the best-matching sentence was 0.83 for a faithful quote, 0.25 for a claim naming the wrong subsidiary (the card said Kanoria Africa Textiles, the filing says APAG Holding), 0.22 for a claim merging "outside the scheme of arrangement" with "not a related party transaction" (the filing names a related party in the deal) and 0.00 for invented prose and an invented EBITDA. **No fuzzy threshold added: the exact rule discriminates, and the second opinion is told what failed.** First batch: 22 of 22 facts carried a quote, 2.8 facts a card, all scoring 1.0, quotes pointing at real table rows | `check_quotes` | measured |
| F54: Jubilant Pharmova's FY25 cards said revenue +979%, PAT +11,403% YoY (loop round 3a, 2026-10-17). The company's own Q4FY24 XBRL tags every amount at a tenth of its value (revenue 1,758,600,000 INR, rounding declared "Lakhs" for a statement in millions); the seed takes XBRL as exact and `confirm()` accepts a figure at any unit, so memory held FY24 at ₹670 Cr. 1 of 150 cached results files | `xbrl.scale_slip`/`fix_scale`: a file whose revenue and implied share count (PAT/EPS; EPS is not scaled) are both off by the same 10^k against the company's other quarters is multiplied back, in the seed (every quarter read before any is written) and for a card's own file and its comparatives. Flags only that file across all 150; a real fall (a demerger) keeps its share count and is left alone. Jubilant re-seeded | fixed |
| F55: no raw BSE/NSE answer had been kept since D28: the Worker's object whitelist lacked `raw/`, so every copy got 403 (a warning per call) | `raw/` allowed in `web/worker/internal.ts` | fixed |
| F56: audit of every discard and hold path, with a stage funnel over the ten smoke-test companies (owner, 2026-10-18; `docs/audit/discard-paths.md`, `funnel-2026-10-18.md`). 1,861 announcements: 772 dropped by rule, 1,089 filings, 451 cards, 118 held (26%), 333 published. The two largest losses of right cards were in the checks: figures the prompt gave the model (market cap, revenue, net worth) held as unfound (40 of 77 amount-only holds), and D20 letting a held or not-material first document own the results quarter (19 of 43 quarters with no published card). 21 defects found and fixed with tests, among them 10x figures passing their quotes by digit matching, a unit-slip guard defeated by chance neighbours, memory taking a 10x balance sheet, rounding refusals in the quote check, the XBRL year-ago check and the change fixer, held cards on the homepage snapshot, and an unreadable attachment crashing the checks | open items listed in the audit (pass 2's reason, annual reports, memory facts after reclassification, repeat M&A cards) | fixed / open |
| F57: annual reports had no event type (to-do item 4, 2026-10-18). Of 26 annual-report filings for the ten smoke-test companies, 12 went to the "AGM notice" date rule because the report was filed with its AGM notice (no card, no reading), and the rest reached pass 1, which typed them RESULTS (9 cards that restated the year's results) or not material (5). An `ANNUAL_REPORT` type now takes anything filed under Reg 34(1) or titled an annual report: a focus module reads the auditor's report, CARO, related parties, contingent liabilities, remuneration, loss-making subsidiaries and MD&A guidance, with three times the page budget; a clean report is a short LOW card giving the baseline. The letters telling shareholders without e-mail where to download it (Reg 36(1)(b), web links) are dropped as meeting logistics, unless filed under Reg 34(1). NSE's annual-report XBRL is not read yet | `taxonomy.toml`, `events.toml`, `models.py`, `test_ingest.py` | fixed (XBRL open) |
| F58: re-run of the 118 held cards and the 19 card-less results quarters with the discard-path fixes (owner, 2026-10-18; `docs/audit/rerun-held-2026-10-18.md`). Held 118 -> 51, published 333 -> 381; 45 held cards now publish and 10 of the 19 quarters have a card. Six re-run filings were swallowed as duplicates of other events: a board-meeting notice typed RESULTS claimed Ahluwalia's Q3FY25 from its own text, and the repeat check before pass 2, seeing only BSE's boilerplate headline, merged two GST notices of different years, a rights subscription with a mining bid and an acquisition's completion with its signing. Fixed: a quarter is claimed only from XBRL, a statement or a page of figures; BSE-worded notices go to the date rule; the repeat check reads the document's opening; a written date and a quantity printed like a year no longer hold a card. Released cards: 10 read against their filings, facts right on all, 2 with a wrong memory insight (open: check a memory insight's figure against the period it names) | `pipeline.results_quarter`, `taxonomy.toml`, `repeat.md`, `gate.py`, `grounding.py` | fixed / open |
| Working (second test): quarter labels corrected from the statement (Q2FY25 → Q3FY25); 2 exact repeats skipped; bank card (CSB deposits, CASA, advances) reads right; headline amounts all grounded | | ok |

## Points to discuss with the owner

1. **Cloud sync is bounded by D1's 100,000 rows written per day**, including the import. Every card
   costs about 8 row writes (row, 4 indexes, search index), so ~50,000 historical cards take about
   five days to sync. Plan: `sync-to-cloud` is resumable and stops at the daily budget; live runs keep
   working meanwhile. Only cards, upcoming catalysts and companies go to D1. The historical ledger stays local.
2. Naming: the blueprint's statuses (QUEUED, PASS2_DONE...) and event ids (QUARTERLY_RESULTS...) map to
   the existing ones (PENDING, ANALYZED; RESULTS...). The existing names are kept, and the UI shows the blueprint's labels.
3. Blueprint `idx_cards_feed (filed_at, impact, category, size)`: `size_category` lives on companies,
   not cards. It is to be copied onto cards at write time so size filters use the index.

## Blueprint sections

### §3 Architecture and free-tier protection
| Item | Status | Notes |
|---|---|---|
| Cloudflare Workers (Hono) + React/Vite + D1 + R2 | done | |
| Local-first ingestion on an Indian IP | done | Laptop runs the pipeline against the local Worker (`npm run dev`), whose D1/R2 persist in `data/wrangler`; `data/` is git-ignored |
| `sync-to-cloud` (local → D1/R2, resumable, budget-aware) | done | `python -m bse_intel sync-to-cloud`; progress in `data/sync_progress.json` |
| R2 homepage/status snapshot (`daily_feed/latest_snapshot.json`), 0 D1 reads | done | published after each run; default feed page and Top Signals served from it |
| Bounded queue counts (LIMIT, "1,000+") | done | audit D2 |
| No system polling from hidden rail; /api/system cached | done | memo 30 s, rail only on wide screens |
| Noise rows not stored in D1 | done | rule drops kept in R2 `noise/<date>/` chunks + `noise_count:<date>` |

### §4 AI gateway
| Item | Status | Notes |
|---|---|---|
| 7 providers, 95% ceiling, pacing, failover, Workers AI spare | done | Gemini added 2026-10-16; OpenRouter free models as spares 2026-10-16 (D19) |
| Dual-key pool | dropped | D1 |
| Task-aware routing: long documents (>12k tokens) to long-context models | done | `pass2_long` |
| Vision OCR: glm-4.6v-flash, then Mistral, then Gemini | done | thinking off; mistral-small-2603, gemini-3.1-flash-lite |
| Second opinion from another provider | done | adopts only the card (audit B1) |

### §5 Ingestion
| Item | Status | Notes |
|---|---|---|
| Polite BSE session, paging pace, PDF pace with jitter | done | 0.5 s pages, 1.2–2.0 s PDFs |
| Explicit 403 / HTML-challenge detection | done | API 403 → SourceBlockedError; HTML bodies retried; attachments per file |
| Stop paging at known filings | done | |
| XBRL fast path (results, shareholding) | done, verify on laptop | `xbrl.py`: results figures (₹ Cr, YoY/QoQ, EBITDA/margin, balance sheet) top the Pass 2 prompt and overwrite the model's in memory (same basis only; checked against the PDF's scale). Shareholding patterns go to memory with no AI call (route XBRL); without an XBRL file they stay noise. Built to the SEBI/BSE taxonomy without a live file (BSE blocks this cloud machine): the smoke test must confirm BSE's XBRL field name (`XML_NAME`/`XBRL`) and tag names, see System "xbrl" count |
| Rule blacklist (certificates, trading window, Reg 74(5), newspaper, investor grievance, IEPF, meet schedules) | done | plus stop transfer, SH-2/SH-4, listing fees, ISIN/depository, fractional shares, PIT code, Reg 24A/27(2)/57, nil deviation, dispatch notices, audio links; one shared material veto on every drop rule (compound titles); AGM notices and record dates go to the calendar. Small ESOP allotments and deviation statements not marked nil go to Pass 1 (size/content unknown from metadata) |
| Reg 30 Schedule III Para A/B legal clue | done | `forensics.py` (Para B threshold note) |
| Board-meeting duration forensics | done | 6+ hours flagged |
| Pass 1 gatekeeper on subject + page 1 | done | subject now stored on the ledger |
| Scanned-page OCR (<80 chars) | done | RapidOCR on the CPU at 200 dpi, up to 20 pages a document, the vision route as fallback (D26); pages in a broken or shifted font are OCR'd too |
| Smart section chunking for 40–150 page documents | done | `Document.kind()` + per-kind section boosts (transcript opening remarks and Q&A; presentation highlights, segments, capex, order book, guidance; annual report auditor's report, statements, segment / RPT / contingent notes); disclaimers, CSR, macro and agenda pages last; moderator and operator chatter stripped |
| Boilerplate stripping | done | whole-line patterns only |
| Local text cache `./data/text_cache/{news_id}.json.gz` | done | |

### §6 Memory (dossier)
| Item | Status | Notes |
|---|---|---|
| Per-company R2 dossier, provenance, time travel | done | |
| 10 compartments as specified | done | identity (former names, entities), financial history, sector KPIs, segments, capex/projects and orders (stages, brownfield, captive), guidance/watchlist, monthly ledger, corporate actions, ownership/governance, predictions, calibration rule (Loop 2); peer benchmarks via peer cards in the prompt |
| `known_since` = earliest, never moved forward (bi-temporal) | done | per-figure sources; value = latest restatement |
| Signals, footer, dilution read memory as of the filing date | done | `dossier_as_of`; market data as of the filing from `price-history` (`prices.py`), else today's only for recent filings |
| Partition by period kind, newest period first; OPEN items never evicted | done | |
| Atomic local writes (tmp + replace) | done | dossiers, text cache, sync progress |

### §7 Prompts and output contract
| Item | Status | Notes |
|---|---|---|
| Boilerplate-free, 4-bucket distillation for long documents | done | boilerplate and call chatter stripped in code; the 4 buckets in the concall prompt |
| Core catalyst line (📌) | done | |
| Memory link, quantified narrative, peer/feedstock context, missing disclosure (memory first) | done | why_it_matters insights with basis (MEMORY / BALANCE_SHEET / SECTOR / FILING); sector drivers in the lens; missing disclosures checked against memory |
| Math checks with FILING/MEMORY/ASSUMPTION provenance | done | formula hardening still due (audit M8) |
| Milestones, KPI to verify, pending approvals, invalidation risk | done | numeric KPIs become predictions checked against results |
| Headline ₹ figure ungrounded forces review | done | |

### §8 Card (8 zones)
| Item | Status | Notes |
|---|---|---|
| Header: symbol, scrip, mcap + tier, timestamp, session tag | done | tiers per blueprint (market.toml); session tag in the card meta line |
| Former-name badge, watchlist ★, credibility score, liquidity, ASM/T2T | done | "formerly …" beside the symbol; T2T pill from the BSE group; ASM/GSM stage has no free source yet |
| Event/sector pills, impact badge, actionability score | done | |
| What happened + adaptive table (results P&L, monthly volume strip) | done | volume strip: last 6 months of the main volume metric from memory as of the filing |
| Why it matters box with Show Working | done | |
| What to track next | done | |
| Sector-aware footer | done | |
| Verification bar: "Numbers verified" / "X of Y" | done | |
| Star / Noise feedback buttons | done | owner mode |
| 6 case studies as test fixtures | done | tests/test_case_studies.py: session tags, math check (₹100 Cr, 3,960 MTPA), 19:25 → 76.0% / 43.2% dilution, distress, promise delivered, 3-month volume streak and Q2 preview, scale vs market cap, grant-funded brownfield scoring, former names. The real-data check is still the laptop smoke test |

### §9 50 forensic modules
Deterministic (code, from memory as of the filing; the XBRL fast path supplies the detailed P&L):
| Modules | Where | Signal |
|---|---|---|
| 10 L1/LoI → LoA dedup | signals ORDER_FLOW + deal stages | stage update, not a new order (Gate 4 veto) |
| 15 other income / low-quality beat | quality.py | LOW_QUALITY_BEAT (penalty) |
| 16 gross margin vs operating leverage | quality.py | MARGIN_MIX |
| 17 jaws / pre-launch hiring | quality.py | JAWS |
| 18 low cash tax | quality.py | LOW_CASH_TAX |
| 21 Q4 true-up | quality.py | Q4_TRUE_UP (penalty) |
| 22 recurring one-offs | quality.py | RECURRING_ONE_OFFS (penalty) |
| 23 working-capital bloat | signals | WORKING_CAPITAL_STRAIN (Gate 4) |
| 27 debt + cash paradox | quality.py | DEBT_CASH_PARADOX |
| 29 distress (cover < 1.5x, NW ≤ 0) | quality.py | DISTRESS (penalty) |
| 30 dilution, rights ratio | signals | DILUTION |
| 31 18-month warrant clock | quality.py | WARRANT_EXPIRY catalyst |
| 38 short-term rating, outlook, INC | quality.py | RATING_LIQUIDITY (INC veto) |
| 39 auditor ladder | signals | AUDIT_FLAG (Gate 4) |
| 44 overdue promises | radar.py | Calendar panel |
| 45 quarter preview | signals | QUARTER_PREVIEW |
| 46 festive Oct+Nov | quality.py | FESTIVE_SEASON |
| 47 smart money vs retail | signals | OWNERSHIP_SHIFT |
| 49 name / ticker continuity | dossier identity, FTS | former-name search |
| 50 trade-to-trade, liquidity | scoring Gate 3, card pills | needs `bse_group` from sync-companies; ASM/GSM stage has no free source yet |

Prompt rules (`config/events.toml`, only the event type's own rules go into each call): 1 (330/275
operating days), 3 (depreciation/interest cliff), 4-5 (captive / brownfield tags), 6 (qualification
lag), 7 (environmental clearances), 9 (EPC vs O&M split), 11 (BG / working capital), 12 (price
variation clause), 13 (scope cuts, LDs), 14 (bid pipeline in notes), 19-20, 24-26, 28 (results
forensics), 32-34 (M&A Annexure A, RPT, demerger type, subsidiary share), 36 (buyback funding),
37 (rated bank limits), 40 (institutional dissent), 41 (penalty size), 43 (evasion, goalpost
shifting), 48 (insider trades).

Module 2 asset turns: quality.py ASSET_TURN with the sector band. Module 35 ROIIC: quality.py `roiic` compares the
EBITDA run-rate (TTM, else the same quarter a year or more apart, annualised) with capital added (net worth + gross
debt - cash) since January 2025; CAPITAL_COMPOUNDER at 20%+, CAPITAL_DILUTER under 8%, self-funded when capital did
not grow. It sits in the company memory summary and the drawer's execution panel, and becomes meaningful once the
backfill has a year of quarters. Not built (need data we do not have): 8 DGTR duties (needs a product list), 42
promoter-group contagion (needs a group map).

### §10 Sector lenses
| Item | Status | Notes |
|---|---|---|
| Sector lenses with KPIs and footer | done | 26 lenses (superset of the 22) |
| Asset-turn bands, seasonality, feedstock, red flags per sector | done | sectors.toml (all 26 lenses) → prompt lens; module 2 ASSET_TURN check on capex with guided revenue |

### §11 4-gate funnel and 0–100 actionability score
| Item | Status |
|---|---|
| Gates 1–4 deterministic (scoring.py) | done |
| 0–100 score, impact mapping (≥70 high, 40–69 moderate, <40 low) | done |
| Top Signals view (≥70 and Gate 4 clean and 2 of gates 1–3) | done |
| Techno-funda tags (trend template, VCP, RS percentile, RVOL) | done | `technicals.py` in the market-data job → companies.technicals_json (migration 0008); card chips for fresh cards (⚡ coiled spring = HIGH + VCP, Stage 2, RS ≥ 80, volume ≥ 2.5x); display only, not scored |

### §12 Learning loops
| Item | Status |
|---|---|
| Loop 1 price post-mortem (T+1/3/5 excess return, 15:30 IST rule) | done: nightly `post-mortem`; missed alpha re-queued (5 a night) and re-analysed with its reaction, the lesson stored per sector and event in R2 `learning/sector_rules.json` and shown to later prompts; dampener list costs matching cards 5 points |
| Loop 2 predictions vs reality, credibility score | done: predictions, credibility, and the calibration rule (delivery ratio on numeric targets, months late on dated promises) in the memory the model reads and in the drawer |
| Loop 3 Star/Noise golden set injected as few-shot | done |

### §13 Website
| Item | Status | Notes |
|---|---|---|
| Live feed with filters | done | 50 a page with page numbers (D4); session filter |
| Top Signals + pre-market brief, "Since 3:30 PM close" | done | default view at `/`; feed moved to `/feed` |
| Company directory, Inflection Radar | done | directory shows credibility, open promises, active capex, latest quarter; radar = 3+ trigger kinds in 90 days (capex commissioned, volume streak, margin +150 bps, debt -15%, smart money) from `radar.py`, stored on the company row with each card |
| Catalyst calendar, overdue promises panel | done | Module 44: open promises past due, from the company summary (no daily scan needed) |
| System monitor (two progress bars, per-provider quota, needs-review queue) | done | review queue lists the failed checks; owner Re-run requeues the filing |
| 360° memory drawer (slide-over), split-screen PDF verifier | done | `?memory=<scrip>` opens it over any page (feed keeps its scroll): dossier with execution bar, financials, deals; timeline with T+1/T+3 vs index; `&verify=<news_id>` puts the BSE PDF beside the card with each figure marked found / not found and the math working. If BSE refuses framing, "Open on BSE" |
| Palette and typography per blueprint (warm light, OLED dark, Plus Jakarta Sans) | done | §13.1 tokens: alabaster #F8F7F4 canvas, #E6E4DD hairlines, sage #EAF2EE box with #1B4D3E heads, impact #0F766E / #B45309, risk #BE123C; OLED #0B0F17 / #111827 / #1F2937, box #06281E with #34D399. Plus Jakarta Sans headlines, Inter body 1.55, JetBrains Mono tabular figures |
| Search across former names | done | companies_fts includes former names (migration 0007); former names now saved to the company row |
| DB dictionary (companies extra columns, cards score columns, card_feedback table) | done | migration 0004 |

### §14 Audit invariants
Tracked in AUDIT.md: every finding is fixed (commit list there); the few items left open are listed
at its end and in PLAN.md.

**Audit round 1 (2026-10-16, `docs/audit/round-1.json`).** 98 cards over the ten smoke-test companies,
rebuilt on the fixed code and reviewed card-against-filing as in round 0: **32 WRONG (33%), 46 MINOR
(47%), 20 OK (20%)**, 2.0 issues a card, against round 0's 95/56/26 (53% WRONG) and 3.67 issues a
card. Per 100 cards the classes the fixes targeted fell hardest: wrong_period 36 to 5, invented 83 to
31, unit_scale 50 to 22, signal_verdict 31 to 16. Arithmetic (50 to 41) and direction (16 to 17) did
not move, and the cause is ours, not a model's: on four results cards `grounding.change_fixes`
overwrote a correct change with a wrong one (f02fe231 +129% to "+1.5% YoY"; 0758a110 "+14.5% QoQ" to
"-29.4% YoY" against +42.3%; 371cb9bc to "-23.5% YoY" against +47.4%; 5fc5b553 finance cost +6.5% to
"+965.1%"). Fix the fixer before round 2.
Per writer model, WRONG share and issues a card: glm-4.5-flash 0% / 1.0 (18 cards), nemotron-3-super
28% / 2.0 (43), glm-4.7-flash 33% / 2.0 (3), deepseek-flash 47% / 1.9 (15), ministral-14b 67% / 3.6
(18). The samples are thin and the hard filings cluster (three of the five worst cards are Kanoria
results), but ministral-14b is indefensible on pass 2 and the paid route's weight of 20, raised for
backfill speed, is not supported by accuracy.
Also open from this round: filings read without XBRL still carry 10x slips (the annual-report path);
the DISTRESS template prints "barely covers interest" at 0.2x and at -0.0x; a conversion or a
completed allotment is still typed FUNDRAISE and emits a SCALE "raise" signal although no cash
reaches the company. "SML Mahindra Ltd" on scrip 505192 is BSE's current name after the Mahindra
acquisition, not a card error.

### §15 Playbook commands
| Step | Command | Status |
|---|---|---|
| Smoke test (5 companies) | `python -m bse_intel backfill-companies --scrips 506525,532776,505192,500672,530019` | done (command) |
| Company master + market caps | `python -m bse_intel sync-companies` then `market-data --all` | done |
| Daily price history (point-in-time footers) | `python -m bse_intel price-history` | done |
| Loop 1 reactions for history | `python -m bse_intel post-mortem --since 2025-01-01` | done |
| Universe ≥ ₹100 Cr | `UNIVERSE_MIN_MCAP_CR` (default 100); starred companies always in | done |
| Pass A + B backfill | `python -m bse_intel run --mode backfill` repeatedly (resumable) | done |
| Cloud sync | `python -m bse_intel sync-to-cloud` (repeat daily until complete) | done |

### §15 Playbook (how go-live happens)
1. All tests green; `.env` with one key per provider; `BSE_INTEL_SINK=local`.
2. `sync-companies` + `market-data --all` (company master, market caps; universe = active and ≥ ₹100 Cr plus starred).
3. `price-history` (daily prices since a year before BACKFILL_START), so history cards get the price, market cap and returns of their own date (D12).
4. Smoke test: 5 companies, 2025-01-01 → today, local website, compare with the case studies.
5. Pass A: 2025 baseline. Pass B: 2026 → today. Resumable. Then `post-mortem --since 2025-01-01`.
6. `sync-to-cloud` (several days, budget-aware), then daily live runs.

## Test plan before go-live
- Unit/integration tests for every module (current: 343 pipeline tests, typecheck and build for web).
- Fixtures from the 6 case studies (expected numbers, signals, missing disclosures).
- Smoke test on the 5 companies with real BSE data on the laptop.
- Website walk-through locally on desktop and phone widths.
