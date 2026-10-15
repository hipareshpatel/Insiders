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
| D19 | OpenRouter added with one account: two free models (Nemotron 3 Ultra, Nemotron 3.5 Super VL) as spares under its shared daily allowance. No extra accounts at any provider. The owner bought $11 of credits once (2026-10-16), which raises the free models from 50 to 1,000 requests/day, so in the backfill route (`pass2_bulk`) they now take a regular weighted share (weight 1 each) and stay spares elsewhere; only ":free" models are configured, so the credit is not spent (a test enforces it), and the key's spending limit should be kept minimal. Checked and not used: Cerebras (card required, $5 credit expiring in 30 days, no free tier after), Hugging Face (no free credits), GitHub Models (retired July 2026), SambaNova (free but 20 requests/day per model; possible later). | 2026-10-16 |
| D15 | The laptop's Claude Code session is the main engineer (it reaches BSE and sees real logs); `CLAUDE.md` holds the rules and status every session reads. The Worker is named `insiders` (https://insiders.reply-bd3.workers.dev). | 2026-10-16 |

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
| F3: one results announcement filed as 3 different documents (Novartis, 9–10 May 2025) gives 3 near-identical cards | not exact repeats, so D17 keeps them; consider linking same-period results cards | open (owner) |
| F4: arithmetic in prose not checked ("85% + 26% = 111% fully diluted"; "₹585 Cr + ₹555 Cr (₹1.14B total)") | look for a deterministic check of sums and percentages stated in text | open |
| F5: raw rupees shown as ₹ ("₹4,135,498,900" for ₹413.5 Cr); the card was already marked Unverified | prompt and validation: amounts in ₹ crore | open |
| F6: a draft tax order tagged ORDER WIN | event-type check (tax/penalty words) | open |
| F7: the same dividend payout derived differently on two cards (₹308 Cr, ₹125 Cr; about ₹62 Cr from shares outstanding) | derived payouts from shares outstanding in code, not by the model | open |
| Working: sector lenses (auto, pharma), size labels, duplicate skips, memory follow-ups ("Approval met", KPI checks), Unverified marks with reasons | | ok |

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
| Scanned-page OCR (<80 chars) | done | |
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
- Unit/integration tests for every module (current: 239 pipeline tests, typecheck and build for web).
- Fixtures from the 6 case studies (expected numbers, signals, missing disclosures).
- Smoke test on the 5 companies with real BSE data on the laptop.
- Website walk-through locally on desktop and phone widths.
