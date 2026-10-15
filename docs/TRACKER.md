# Build tracker

The single list of what the platform must do, where each item stands, and what the owner decided.
The full specification is [BLUEPRINT.md](BLUEPRINT.md) (owner's master prompt, verbatim). Pre-launch
audit findings are in [AUDIT.md](AUDIT.md). Architecture as built is in [SPEC.md](SPEC.md).

Status: **done** (built and tested), **partial** (built, gaps listed), **todo** (not built).
Every item is pre-launch: the owner decided everything is built and tested locally before go-live.

## Owner decisions (override the blueprint where they differ)

| # | Decision | Date |
|---|---|---|
| D1 | One API key per provider (no `_1`/`_2` dual-key pool). The cross-provider second check on cards that fail verification stays. | 2026-10-15 |
| D2 | Everything is built, run and fixed on the laptop with the website running locally; go-live only after that. | 2026-10-15 |
| D3 | History (2025-01-01 to today) is filled on the laptop (local SQLite + local R2 folder), then synced to Cloudflare. Only AI token limits apply locally. | 2026-10-15 |
| D4 | Feed uses page-numbered pagination (50 cards a page), not endless scrolling; filters (dates, company, event, sector, size, impact) find older filings. | 2026-10-15 |
| D5 | The blueprint lives in `docs/`; the GitHub repo is to be made private (owner action). | 2026-10-15 |
| D6 | Never test the backfill at scale before the 5-company smoke test (506525, 532776, 505192, 500672, 530019) looks right. | 2026-10-15 |
| D7 | No Telegram, WhatsApp or X distribution. EquiSense is a design benchmark only (no name, logo or score). | earlier |
| D8 | Market data from yfinance (no bhavcopy pipeline). | earlier |
| D9 | Cards that fail checks are never hidden: second check by another provider, then published with an Unverified mark. | earlier |
| D10 | Sector-specific footer metrics (bank GNPA/NIM, cement EBITDA/t, telecom ARPU, hotel RevPAR...). | earlier |
| D11 | Minimise multi-agent runs (token budget); keep docs current so context compaction loses nothing. | 2026-10-15 |

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
| 5 providers, 95% ceiling, pacing, failover, Workers AI spare | done | |
| Dual-key pool | dropped | D1 |
| Task-aware routing: long documents (>12k tokens) to long-context models | todo | |
| Vision OCR: glm-4.6v-flash, then pixtral | partial | thinking off for glm-4.6v, check pixtral id (audit B16) |
| Second opinion from another provider | done | adopts only the card (audit B1) |

### §5 Ingestion
| Item | Status | Notes |
|---|---|---|
| Polite BSE session, paging pace, PDF pace with jitter | partial | page delay 1 s; add PDF download jitter 1.2–2.0 s |
| Explicit 403 / HTML-challenge detection ("BSE_IP_BLOCKED") | partial | API 403 → SourceBlockedError; attachments → per-file, 3 in a row stop the run |
| Stop paging at known filings | done | |
| XBRL fast path (results, shareholding) | todo | |
| Rule blacklist (certificates, trading window, Reg 74(5), newspaper, investor grievance, IEPF, small ESOP allotments, meet schedules) | partial | compound-headline overrides needed (audit A16); IEPF/ESOP/meet-schedule rules to add |
| Reg 30 Schedule III Para A/B legal clue | todo | |
| Board-meeting duration forensics | todo | |
| Pass 1 gatekeeper on subject + page 1 | done | subject now stored on the ledger |
| Scanned-page OCR (<80 chars) | partial | threshold is 50 chars |
| Smart section chunking for 40–150 page documents | partial | keyword page ranking; concall/presentation/annual-report section rules to add |
| Boilerplate stripping | partial | over-strips factual lines (audit A17) |
| Local text cache `./data/text_cache/{news_id}.json.gz` | done | |

### §6 Memory (dossier)
| Item | Status | Notes |
|---|---|---|
| Per-company R2 dossier, provenance, time travel | done | |
| 10 compartments as specified | partial | have: identity, financial metrics, balance sheet, segments, guidance/watchlist, deals (orders, projects), events, timeline, concerns, operating notes. Missing: former names/entities tree, monthly operational ledger, ownership/governance, calibration/peer context, pending predictions |
| `known_since` = earliest, never moved forward (bi-temporal) | done | per-figure sources; value = latest restatement |
| Signals, footer, dilution read memory as of the filing date | done | `dossier_as_of`; today's price not used for old filings |
| Partition by period kind, newest period first; OPEN items never evicted | done | |
| Atomic local writes (tmp + replace) | done | dossiers, text cache, sync progress |

### §7 Prompts and output contract
| Item | Status | Notes |
|---|---|---|
| Boilerplate-free, 4-bucket distillation for long documents | partial | |
| Core catalyst line (📌) | todo | |
| Memory link, quantified narrative, peer/feedstock context, missing disclosure (memory first) | partial | as why_it_matters insights with basis; missing disclosures checked against memory |
| Math checks with FILING/MEMORY/ASSUMPTION provenance | done | formula hardening still due (audit M8) |
| Milestones, KPI to verify, pending approvals, invalidation risk | done | KPI → pending_predictions todo |
| Headline ₹ figure ungrounded forces review | todo | audit M1 |

### §8 Card (8 zones)
| Item | Status | Notes |
|---|---|---|
| Header: symbol, scrip, mcap + tier, timestamp, session tag | partial | session tag in Full analysis; tiers to match blueprint (Micro <500, Small 500–5,000, Mid 5,000–20,000, Large >20,000 ₹ Cr) |
| Former-name badge, watchlist ★, credibility score, liquidity, ASM/T2T | todo | |
| Event/sector pills, impact badge, actionability score | partial | score todo |
| What happened + adaptive table (results P&L, monthly volume strip) | partial | monthly volume strip todo |
| Why it matters box with Show Working | done | |
| What to track next | done | |
| Sector-aware footer | done | |
| Verification bar: "Numbers verified (N/N)" / "X of Y" | done | add N/N count to the verified label |
| Star / Noise feedback buttons | todo | |
| 6 case studies as test fixtures | todo | smoke test |

### §9 50 forensic modules
Built: SCALE (order/capex vs revenue, fundraise vs market cap), ORDER_FLOW (repeat orders, stage
updates such as LoI to LoA), DILUTION, PROMISE_DELIVERED, GUIDANCE_BREACH, WATCH_RESOLVED,
WORKING_CAPITAL_STRAIN, METRIC_SHIFT. All other modules are **todo**; they are to be built as
deterministic checks in `signals.py` where the data exists (results, balance sheet, ratings, shareholding),
and as prompt rules otherwise. The per-module list is in BLUEPRINT §9.

### §10 Sector lenses
| Item | Status | Notes |
|---|---|---|
| Sector lenses with KPIs and footer | done | 26 lenses (superset of the 22) |
| Asset-turn bands, seasonality, feedstock, red flags per sector | todo | add to sectors.toml and the prompt |

### §11 4-gate funnel and 0–100 actionability score
| Item | Status |
|---|---|
| Gates 1–4 deterministic (scoring.py) | done |
| 0–100 score, impact mapping (≥70 high, 40–69 moderate, <40 low) | done |
| Top Signals view (≥70 and Gate 4 clean and 2 of gates 1–3) | done |
| Techno-funda tags (trend template, VCP, RS percentile, RVOL) | todo |

### §12 Learning loops
| Item | Status |
|---|---|
| Loop 1 price post-mortem (T+1/3/5 excess return, 15:30 IST rule) | todo |
| Loop 2 predictions vs reality, credibility score | todo |
| Loop 3 Star/Noise golden set injected as few-shot | todo |

### §13 Website
| Item | Status | Notes |
|---|---|---|
| Live feed with filters | done | 50 a page with page numbers (D4); session filter |
| Top Signals + pre-market brief, "Since 3:30 PM close" | done | default view at `/`; feed moved to `/feed` |
| Company directory, Inflection Radar | partial | directory done |
| Catalyst calendar, overdue promises panel | partial | calendar done |
| System monitor (two progress bars, per-provider quota, needs-review queue) | partial | review queue todo |
| 360° memory drawer (slide-over), split-screen PDF verifier | partial | company page exists; drawer and verifier todo |
| Palette and typography per blueprint (warm light, OLED dark, Plus Jakarta Sans) | todo | current theme is EquiSense-like |
| Search across former names | todo | |
| DB dictionary (companies extra columns, cards score columns, card_feedback table) | todo | |

### §14 Audit invariants
Tracked in AUDIT.md. Fixed so far: D1 read/write cost, orchestration resilience, gateway outages,
second opinion merge, Worker hardening, frontend honesty/Safari/error boundary. Open: memory
bi-temporal (M1–M15), triage overrides (A16), boilerplate (A17), prompt items (B2, B4, B7–B9),
docs, sync-companies workflow.

### §15 Playbook commands
| Step | Command | Status |
|---|---|---|
| Smoke test (5 companies) | `python -m bse_intel backfill-companies --scrips 506525,532776,505192,500672,530019` | done (command) |
| Company master + market caps | `python -m bse_intel sync-companies` then `market-data --all` | done |
| Universe ≥ ₹100 Cr | `UNIVERSE_MIN_MCAP_CR` (default 100); starred companies always in | done |
| Pass A + B backfill | `python -m bse_intel run --mode backfill` repeatedly (resumable) | done |
| Cloud sync | `python -m bse_intel sync-to-cloud` (repeat daily until complete) | done |

### §15 Playbook (how go-live happens)
1. All tests green; `.env` with one key per provider; `BSE_INTEL_SINK=local`.
2. Smoke test: 5 companies, 2025-01-01 → today, local website, compare with the case studies.
3. `sync-companies` + market caps; universe = active and market cap ≥ ₹100 Cr (plus starred).
4. Pass A: 2025 baseline. Pass B: 2026 → today. Resumable.
5. `sync-to-cloud` (several days, budget-aware), then daily live runs.

## Test plan before go-live
- Unit/integration tests for every module (current: 121 pipeline tests, typecheck and build for web).
- Fixtures from the 6 case studies (expected numbers, signals, missing disclosures).
- Smoke test on the 5 companies with real BSE data on the laptop.
- Website walk-through locally on desktop and phone widths.
