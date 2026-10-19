<!-- Source: MASTER_BLUEPRINT_prompt.docx from the owner (Oct 2026). Verbatim text; tables kept as rows.
     Owner decisions that override it are listed in docs/TRACKER.md (e.g. one API key per provider). -->

# MASTER BLUEPRINT: INSTITUTIONAL BSE CORPORATE INTELLIGENCE & PERSISTENT MEMORY PLATFORM (PART 1 OF 3)
Document Scope: Complete End-to-End Functional, Architectural, Forensic & Operational Specification
Target Environment: Local-First Ingestion Engine + Cloudflare Pages/Workers + Cloudflare D1 + Cloudflare R2
Operating Cost: ₹0 / Month (100% Permanent Free-Tier Infrastructure & Multi-Provider AI Pool)
Historical Memory Window: 01 January 2025 – 31 December 2025 (Objective Baseline Initialization)
Live Intelligence Window: 01 January 2026 – Present
MASTER TABLE OF CONTENTS (ACROSS ALL 3 PARTS)

## PART 1 (Contained in This Document):
Section 1: Executive Vision, Core Philosophy & Why Standard AI Summarizers Fail
Section 2: Reverse-Engineered Benchmark of the 5 Reference Filings
Section 3: Zero-Cost Cloud & Local Hybrid Architecture ($0/Month Infrastructure & Storage Math)
Section 4: The 5-Provider Free AI Gateway, Dual-Key Pool & 95% Quota Safety Engine
Section 5: The 5-Stage Ingestion, XBRL Fast-Path, SEBI Reg 30 Legal Triage & Vision OCR Pipeline
Section 6: Bi-Temporal Persistent Memory Architecture (All 10 Dossier Compartments & 12 Integrity Rules)
Section 7: Master Prompt Engineering, Universal Distillation Rules (1-Page to 100-Page Docs) & Output Specification

## PART 2 (Delivered Next):
Section 8: The Complete "Alpha-Matrix" Card Blueprint & 6 Full Worked Case Studies
Section 9: All 50 "Meter-Deep" Forensic & Indian Market Alpha Modules (Full Unabridged Explanations Across 8 Domains)
Section 10: The Complete 22-Industry Sector Lens Dictionary (Exact KPIs, Asset-Turn Norms, Seasonality & Forensic Traps per Industry)

## PART 3 (Delivered After Part 2):
Section 11: The 4-Gate Signal-Over-Noise Funnel, Price-Momentum Convergence & 0–100 Actionability Scoring Matrix
Section 12: The 3 Self-Learning Loops (Market-Truth Post-Mortem, Forecast Calibration & 1-Click Human Golden-Set Learner)
Section 13: Complete Website UI/UX Specification (All 5 Views, 360° Memory Drawer, Catalyst Calendar & Database Dictionary)
Section 14: Complete 360° Audit Hardening & Verification Rules
Section 15: End-to-End Execution Playbook (2025 Baseline → 2026 Live Layer) & The Daily 15-Minute Investor Ritual

## 1. Executive Vision, Core Philosophy & Why Standard AI Summarizers Fail
Every trading day, Indian listed companies file more than 1,500 corporate announcements on the Bombay Stock Exchange (BSE). Roughly 80% to 85% of this daily volume consists of mandatory procedural compliance—duplicate share certificate intimations, insider trading window closures, depository demat certificates, and newspaper advertisement clippings. The remaining 15% to 20% (~200 to 250 filings per day) contain material business disclosures: capacity expansions, new product launches, rights issues, monthly production and sales volumes, order wins, mergers and acquisitions, credit rating revisions, and quarterly financial results.

## 1.1 The Three Structural Failures of Standard AI & RAG Systems
When investors or developers attempt to automate BSE filing analysis using standard Large Language Model (LLM) prompts or Vector Database Retrieval-Augmented Generation (RAG), they hit three walls:
Historical Context Blindness:
Corporate disclosures on BSE are written as terse legal letters under SEBI Regulation 30. A 1-page filing announcing a new chemical plant or a rights issue rarely explains the multi-year strategic backstory, the company's current debt burden, or whether management is on schedule or two years late.
An AI that only reads today's PDF cannot know that a 12 TPD Triacetin plant launched on October 7, 2026 was promised at the September 2026 Annual General Meeting (AGM) to diversify away from bulk commodities, or that a ₹120 Cr Rights Issue is an urgent rescue for a balance sheet whose net worth collapsed to negative ₹61.67 Cr in June 2026 under ₹20.48 Cr of quarterly interest costs and a ₹399 Cr debt pile.
Why Vector Search (RAG) Fails on Financial State:
In a traditional vector database, chunks of text are retrieved based on cosine similarity of words. If Evonile Pharma files a notice on October 8, 2026 approving a ₹900 Cr Rights Issue, a vector similarity search for "Rights Issue" will retrieve boilerplate paragraphs about equity issuance. It will not know to retrieve a September 2026 filing about a "₹1,250 Cr Minipress acquisition", nor will it know to retrieve Jubilant Pharmova's segment footnote showing that "Radiopharma accounts for 44.6% of total company sales".
Financial analysis requires deterministic state retrieval, not keyword guessing. When a company files an announcement, the analyst needs the company's complete, up-to-date financial balance sheet, segment revenue split, active capex projects, pending promises, and last 12 months of operational numbers every single time.
The "High-IQ Noise" Trap:
Even after eliminating the ~1,300 daily regulatory noise filings, reading 200 material summaries every day takes hours.
Out of those 200 material filings, ~160 are Informational Materiality—events that must be recorded in the company's permanent memory (such as a routine credit rating reaffirmation, a minor KMP change, or an in-line monthly update) but do not justify buying or selling the stock today.
Only 3 to 8 filings per day across the entire exchange represent True Actionable Alpha Signals—where economic magnitude relative to market cap, operating leverage inflection, balance sheet de-risking, and a non-extended stock price converge simultaneously.

## 1.2 The Unfair Advantage of an Individual Investor Using This Framework
Large institutional Mutual Funds and Portfolio Management Services (PMS) managing ₹5,000 Cr to ₹50,000 Cr suffer from structural constraints that an individual investor does not have:
The Size & Liquidity Constraint: A ₹10,000 Cr mutual fund cannot take a meaningful 3% position (₹300 Cr) in a ₹500 Cr or ₹800 Cr small-cap like Kanoria Chemicals (₹806 Cr market cap) or Shivam Autotech (₹223 Cr market cap). By the time a company grows large enough for institutional committees to approve (>₹5,000 Cr market cap), the initial 3x–5x turnaround or capex re-rating has already happened.
Zero Committee Delay: An individual investor armed with an automated persistent-memory engine can evaluate a small-cap announcement at 8:45 AM IST against 21 months of verified company memory and act at 9:15 AM IST without waiting for sell-side broker notes.

## 2. Reverse-Engineered Benchmark of the 5 Reference Filings
A forensic comparison between the five raw BSE filings and their processed institutional insight cards reveals the exact data structures the Persistent Memory engine must maintain for every stock:

## 2.1 Benchmark 1: Kanoria Chemicals & Industries Limited (506525 / KANORICHEM)
Facts Present in the Raw Oct 7, 2026 Filing (1-Page Scanned Letter):
Addressed to NSE (KANORICHEM) and BSE (506525), digitally signed by Company Secretary Pratibha Jaiswal at 17:50:47 +05:30 (after market hours).
Discloses under SEBI Regulation 30 the launch of a new 12 Metric Tons per Day (TPD) Triacetin manufacturing facility at its existing manufacturing site in GIDC, Ankleshwar, Gujarat on 07.10.2026.
Table states: Product Name = Triacetin; Launch Date = 07.10.2026; Category = Chemical / Food and Pharma; Market = Both market (India (open for international market)).
Facts Injected From Persistent Memory & Market Data:
Header & Footer Context: Market Cap = ₹806 Cr · Smallcap; Q1 FY27 revenue = ₹460 Cr; Stock performance = 1W -8.9%, 1M +17%, 1Y +134%.
Strategic Roadmap Memory: Management planned to commission Triacetin capacity in FY27 to diversify away from volatile bulk commodity products, a roadmap reiterated at its September 2026 AGM.
Forensic Omission Detection: Notes that the filing does not disclose expected sales or ramp-up timeline, which decides when earnings see the benefit.
Deep Investor Layer Added by Our Framework: Incorporates prior concall guidance (40% capacity utilization target in FY27 adding ~₹100 Cr revenue, with major operating leverage kicking in above 65% utilization to double segment sales), raw material context (glycerin feedstock at lifetime highs potentially inflating top-line pass-through revenue), and peer margin benchmarking (peer Group G reporting ~29% operating margins vs. Kanoria's ~14% baseline, pointing to a potential margin lift toward ~19% and ROE expansion from ~12% to ~14%).

## 2.2 Benchmark 2: Shivam Autotech Limited (532776 / SHIVAMAUTO)
Facts Present in the Raw Oct 8, 2026 Filing (Digital PDF):
Outcome of Board Meeting held on Thursday, October 8, 2026, following in-principle approvals from NSE and BSE dated September 29, 2026.
Approves a Rights Issue of up to 10,00,00,000 (10 Crore) fully paid-up Equity Shares of face value ₹2/- each at an Issue Price of ₹12 per share (including ₹10 premium), for an issue size of up to ₹12,000 Lakhs (₹120 Cr).
Full amount of ₹12/share is payable on application.
Record Date: Thursday, October 15, 2026; Opening Date: Thursday, October 22, 2026; Last Date for On-Market Renunciation of REs: Friday, November 13, 2026.
Facts Injected From Persistent Memory & Annexures:
Header & Footer Context: Market Cap = ₹223 Cr · Smallcap; Q1 FY27 revenue = ₹110 Cr; Stock performance = 1W -2.1%, 1M -3.8%, 1Y -46%.
Entitlement & Closing Date: Eligible shareholders receive 19 rights shares for every 25 shares held (19:25 ratio), closing on November 19, 2026.
Prior Board Timeline: Connects final pricing to the initial equity fundraise approved by the board on July 1, 2026.
Balance Sheet Stress Memory: Reveals that net worth fell to negative ₹61.67 Cr in June 2026, hit by ₹20.48 Cr in quarterly interest costs, and that subscription levels decide how much equity arrives to address the company's ₹399 Cr debt pile.

## 2.3 Benchmark 3: SML Mahindra Limited (505192 / SMLMAH)
Facts Present in the Raw Oct 8, 2026 Filing (1-Page Digital Letter):
Filed by SML Mahindra Limited (Formerly SML Isuzu Limited), digitally signed at 15:41:18 +05:30 (11 minutes after market close).
Reports September 2026 Commercial Vehicle figures comparing FY 2026 vs. FY 2027: Production: 1,049 → 1,257; Sales: 812 → 1,071; Export: 138 → 53.
Facts Injected From Persistent Memory:
Header & Footer Context: Market Cap = ₹8,470 Cr · Midcap; Q1 FY27 revenue = ₹958 Cr; Stock performance = 1W -7.3%, 1M -4.7%, 1Y +98%.
Multi-Month Trend Memory: Calculates that sales grew +32% YoY (and production grew +19.8% YoY), holding above 30% growth for a second straight month after August's 34.4% rise.
Export Reversal Context: Notes that exports falling to 53 units from 138 units last year reversed the export surge seen in August and dragged on overall volume.

## 2.4 Benchmark 4: Evonile Pharma Limited (500672 / NOVARTIND)
Facts Present in the Raw Oct 8, 2026 Filing (Digital PDF):
Filed by Evonile Pharma Limited (formerly known as Novartis India Limited), BSE Scrip Code 500672.
Board approved raising funds via issuance of partly paid-up equity shares of face value ₹5/- each for an aggregate amount not exceeding ₹9,000 million (₹900 Cr) on a rights basis.
Facts Injected From Persistent Memory:
Header & Footer Context: Ticker = NOVARTIND; Market Cap = ₹4,905 Cr · Smallcap; Q1 FY27 revenue = ₹104 Cr; Stock performance = 1W +4.8%, 1M +23%, 1Y +130%.
Governance & M&A Memory: Notes that the board formed a Rights Issue Committee to finalize price/ratio/record date, that the raise is subject to shareholder approval via postal ballot, that it follows the October 5 board meeting notice, and that the ₹900 Cr raise helps refinance debt from the company's ₹1,250 Cr Minipress acquisition in September 2026.

## 2.5 Benchmark 5: Jubilant Pharmova Limited (JUBLPHARMA)
Facts Present in the Raw Oct 8, 2026 Filing (Press Release PDF):
Subsidiary Jubilant Draximage Inc. (subsidiary of wholly owned subsidiary Jubilant Pharma Limited) announced a CAD 94.5 million investment to modernize and expand its Kirkland, Québec facility and double production capacity of its flagship cardiac PET imaging product RUBY-FILL® (Rubidium-82 generator).
The Government of Canada will provide CAD 23.8 million in financial support through its Strategic Response Fund.
Notes that the RUBY-FILL® customer base doubled in the last 3 years and that Kirkland is the only site in Canada producing these categories.
Facts Injected From Persistent Memory:
Header & Footer Context: Market Cap = ₹14,849 Cr · Midcap; Q1 FY27 revenue = ₹2,229 Cr; Stock performance = 1W -6.7%, 1M -6.6%, 1Y -14%.
Segment & Concall Memory: Pulls segment revenue share showing Radiopharma makes up 44.6% of company sales, and connects to the last earnings call where management noted RUBY-FILL® was growing 30%+ even as other radiopharma lines faced supply shortages.
Missing Disclosure: Flags that the filing does not state a completion timeline, which decides when the added capacity starts contributing to sales.

## 3. Zero-Cost Cloud & Local Hybrid Architecture ($0/Month)

## 3.1 Why This Exact Architecture Was Chosen
To host a highly dynamic, filter-intensive financial terminal at $0/month without hitting RAM limits or cold-start delays:
Why Streamlit Was Rejected: Streamlit Community Cloud shares a 1 GB RAM container across users, sleeps when inactive, and reloads data in memory on every filter click.
Why Vercel & Netlify Were Rejected: Vercel's free tier forbids commercial use and adds cross-cloud latency when talking to Cloudflare D1/R2; Netlify's free credit pool depletes rapidly under dynamic queries.
Why Cloudflare Pages + Workers (Hono) + React (Vite) + D1 + R2 Wins:
Zero Network Latency: The Hono API Worker, D1 SQL database, and R2 Object Vault all run inside the exact same Cloudflare edge network across Indian data centers (Mumbai, Delhi, Chennai, Hyderabad).
Unlimited Static Bandwidth & 100,000 Dynamic Requests/Day: Static assets and edge-cached snapshots cost zero Worker invocations.
Native Virtualized Tables (TanStack Virtual): Renders 10,000+ historical announcement cards smoothly at 60 FPS on both mobile phones and desktops.

## 3.2 Solving the BSE 403 Forbidden Firewall & Cloud Quota Limits via Local-First Ingestion
BSE India uses Akamai bot protection that blocks automated requests originating from international or cloud data-center IP addresses (such as GitHub-hosted cloud runners), returning HTTP 403 Forbidden even when browser headers and session warm-up requests are sent.
The Local-First Architecture:
Local Execution on Indian Residential IP: All BSE polling, PDF downloading, and historical backfilling run on your local machine (or a local background watch daemon / self-hosted runner on your Indian home broadband connection), where BSE requests succeed natively.
Local Storage Mirror (STORAGE_MODE=local): During the 2025–2026 backfill, the Python pipeline writes to a local SQLite database (./data/local_d1.sqlite) and a local R2 directory (./data/local_r2/memory/ and ./data/local_r2/daily_feed/) on your SSD. This provides unlimited reads and writes at 0.1 ms speed without touching Cloudflare D1's 100,000 daily write cap or R2's monthly operation quota.
One-Command Cloud Synchronization (sync-to-cloud): Once the local backfill is verified, a single synchronization command batch-imports the SQLite tables into Cloudflare D1 and uploads changed JSON dossiers to Cloudflare R2. Thereafter, live daily runs only push incremental deltas (~150–250 cards/day), consuming < 0.5% of Cloudflare's free daily limits.

## 3.3 Protecting Cloudflare D1's 5,000,000 Daily Row-Read Cap
In Cloudflare D1, cost is measured by rows scanned, not rows returned. An unindexed COUNT(*) query over a 175,000-row filings log scans all 175,000 rows on a single API call—meaning 28 page loads would exhaust the entire 5M daily limit. The architecture enforces four permanent rules:
Static R2 Homepage & Status Snapshot (daily_feed/latest_snapshot.json): At the end of every pipeline batch, the worker writes a single pre-assembled JSON file to R2 containing the first page of latest cards, the pre-market brief, and the system status counters. Default homepage loads read this static snapshot from R2/CDN at 0 D1 row reads.
Bounded Queue Counts: Any live SQL count on filings is strictly capped (LIMIT 1001, displaying "1,000+" in the UI) and filtered exclusively on indexed columns (idx_filings_queue on (status, filed_at) and idx_cards_feed on (filed_at DESC, ...)).
No Background Polling on Hidden Rails: The /api/system endpoint is never called on the main feed side-rail (which is hidden via CSS on mobile screens) and is cached for 60 seconds via the Cloudflare Worker Cache API (caches.default).
Noise Rows Are Not Stored in D1: Filings dropped by the Stage 1 rule blacklist are not inserted as individual rows in D1; only a single daily counter (noise_count) is incremented.

## 4. The 5-Provider Free AI Gateway, Dual-Key Pool & 95% Quota Safety Engine

## 4.1 Why Multi-Provider + Dual-Key Interleaving Is Essential
A single free API key is vulnerable to per-minute rate limits (RPM / TPM) during earnings-season spikes or historical backfills. Because rate limits are enforced per account/organization rather than per key within the same account, using two sets of API keys from two independent accounts across four external providers—plus Cloudflare Workers AI as a fifth native spare—creates 9 independent quota buckets at ₹0 cost.

## 4.2 Complete Provider & Model Specification (providers.toml)
| Provider ID | Active Model Identifiers | Account Keys | Combined Free Quota (at 100%) | Hard 95% Ceiling (Enforced by limits.py) | Primary & Backup Pipeline Roles |
| 1. Groq | • llama-3.1-8b-instant / • llama-3.3-70b-versatile | 2 Keys (GROQ_API_KEY_1, GROQ_API_KEY_2) | • 8B: 28,800 req/day · 60 RPM / • 70B: 2,000 req/day · 60 RPM | • 8B: 27,360 req/day · 57 RPM / • 70B: 1,900 req/day · 57 RPM | Pass 1 Gatekeeper Primary (8B) at 1,000+ tok/sec; Pass 2 Backup (70B). |
| 2. NVIDIA NIM | • deepseek-ai/deepseek-r1 / • meta/llama-3.3-70b-instruct | 2 Keys (NVIDIA_API_KEY_1, NVIDIA_API_KEY_2) | ~80 RPM combined across 2 developer accounts | 76 RPM combined (38 RPM per key) | Pass 2 Primary Deep Analyst: Chain-of-thought financial synthesis, quantified math, and R2 delta creation. |
| 3. Mistral AI | • mistral-large-latest / • mistral-small-latest / • pixtral-12b | 2 Keys (MISTRAL_API_KEY_1, MISTRAL_API_KEY_2) | ~2 Billion tokens/mo · ~120 RPM combined across 2 Experiment accounts | 1.9B tokens/mo · 57 RPM per key | Pass 2 Co-Primary & Backfill Workhorse (mistral-large); Pass 1 Failover (mistral-small); Vision OCR Backup (pixtral-12b). |
| 4. Z.AI (Zhipu) | • glm-4.7-flash (200K context) / • glm-4.6v-flash (Vision OCR) | 2 Keys (ZAI_API_KEY_1, ZAI_API_KEY_2) | Permanently $0/1M tokens · ~2 req/sec combined concurrency | 55 RPM combined (with 1 concurrent request per key) | Primary Vision OCR (glm-4.6v-flash) for scanned PDFs; Long-Document Pass 2 Analyst (glm-4.7-flash) for 40-page concalls/presentations. |
| 5. Cloudflare Workers AI | • @cf/meta/llama-3.1-8b-instruct / • @cf/meta/llama-3.3-70b-instruct | 1 Native Binding (AI) | 10,000 free Neurons/day (~150–300 requests/day) | 9,500 Neurons/day | Warm Standby Last-Resort Spare: Zero external latency; activates only if all external providers are in cooldown. |


## 4.3 Deterministic Routing & Self-Healing Rules (gateway.py)
Weighted Round-Robin with Key Ping-Pong:
If Provider A has two keys (A:1 and A:2), the gateway never drains A:1 before touching A:2. It alternates A:1 → B:1 → C:1 → A:2 → B:2 → C:2. Each account receives maximum idle recovery time between requests.
Task-Aware Model Routing:
Short-to-Medium Filings (< 12,000 tokens): Round-robin across NVIDIA (deepseek-r1), Mistral (mistral-large-latest), and Z.AI (glm-4.7-flash).
Massive Filings (12,000 to 120,000 tokens — Concall Transcripts, Investor Presentations, Annual Reports): Route preferentially to Z.AI (glm-4.7-flash, 200K window) and Mistral (mistral-large-latest, 128K window) so long transcripts are never truncated.
Scanned / Image Pages: Route to Z.AI (glm-4.6v-flash), failing over to Mistral (pixtral-12b).
Automatic Second-Opinion Escalation (SECOND_OPINION):
When a Pass 2 output from Provider A fails deterministic grounding (ungrounded numbers found) or fails the AST math check (FormulaError / math mismatch), the gateway automatically requests one retry ("Second Opinion") from a different provider (e.g., if Mistral produced a math mismatch, retry once on NVIDIA deepseek-r1 with the specific error message injected into the retry prompt). If the second opinion passes 100% verification, the card is marked "Verified after a second check"; if it still fails, the card is saved with needs_review = 1.

## 5. The 5-Stage Ingestion, XBRL Fast-Path, SEBI Reg 30 Legal Triage & Vision OCR Pipeline

## 5.1 Stage 0: BSE Discovery & The XBRL Fast-Path
Polite Session & Anti-Block Handling (bse.py):
Establishes a persistent HTTP session with browser headers (User-Agent, Referer: [https://www.bseindia.com/corporates/ann.html](https://www.bseindia.com/corporates/ann.html), Origin: [https://www.bseindia.com](https://www.bseindia.com)), warms up session cookies, paces pagination at 0.4s–0.6s, and paces PDF downloads at 1.2s–2.0s jitter.
Explicitly detects HTTP 403 or HTML challenge responses, logging a clear "BSE_IP_BLOCKED" diagnostic rather than silently recording "0 filings found".
The BSE XBRL Fast-Path (100% Precision for Financial Results & Shareholding):
Whenever a filing is a Quarterly/Annual Financial Result or Shareholding Pattern, bse.py checks for the structured XBRL (XML) link.
The XML parser extracts exact rupee/crore figures for Revenue, Other Income, Raw Material Cost, Employee Cost, Finance Cost, Depreciation, PBT, Current Tax, Deferred Tax, PAT, EPS, Paid-Up Equity Capital, Reserves (Net Worth), Borrowings (Debt), Trade Receivables, Inventories, Trade Payables, Cash & Bank Balances, and Operating Cash Flow—plus Promoter %, FII %, DII %, Pledge %, and Retail Headcount.
Because XBRL numbers are machine-tagged by the company's Chartered Accountant, this step uses 0 AI tokens, takes 0.01 seconds, and eliminates OCR/unit mistakes completely.

## 5.2 Stage 1: Deterministic Rule Filter & SEBI Regulation 30 Legal Triage
Zero-Cost Noise Blacklist (rules.py):
Instantly drops routine compliance subcategories and headline patterns:
Share Certificates: Reg 39(3), loss/issue of duplicate share certificates, stop-transfer notices.
Routine Certificates: Reg 74(5) depository certificates, Reg 40(9), Reg 7(3), Reconciliation of Share Capital Audit, Investor Grievance statement (Reg 13(3)).
Routine Notices: Closure of Trading Window, Newspaper Clippings (Reg 47), IEPF transfers, routine ESOP exercise allotments < 0.1% of equity, and Analyst/Investor Meet Schedule Invites (skipping the empty calendar invite, while keeping all Investor Presentations, Press Releases, and Audio/Text Concall Transcripts).
SEBI Regulation 30 Legal Clues (New Forensic Layer):
Indian companies must classify Regulation 30 disclosures under Schedule III Part A:
Para A (Deemed Material Events): Must be disclosed regardless of size (Acquisitions, Restructuring, Rights/Bonus/Buybacks, Ratings, Management/Auditor changes, Forensic Audits, Regulatory Penalties).
Para B (Materiality Threshold Events): Product launches, capacity additions, order wins, and litigation are only required to be disclosed under Para B if their expected impact exceeds the SEBI Quantitative Materiality Threshold: the lower of 2% of turnover, 2% of net worth, or 5% of average 3-year absolute PAT!
Why this is a hidden goldmine: When a company like Kanoria Chemicals (with ₹460 Cr quarterly revenue / ~₹1,800 Cr annual turnover and ~₹312 Cr net worth) files a Product Launch notice specifically invoking Regulation 30, the legal act of filing under Reg 30 implies management expects the economic impact of that facility to cross SEBI's materiality threshold (typically > 2% of net worth or > 5% of average PAT), even if they don't print the revenue number in the table!
Board Meeting Duration Forensics (The 30-Minute Rule): Under SEBI LODR, outcomes of Board Meetings must be filed within 30 minutes of the conclusion of the meeting, and the letter typically states "The Board Meeting commenced at HH:MM and concluded at HH:MM". The parser extracts board_meeting_duration_hours: a routine board meeting lasts 1 to 3 hours; a board meeting that stretches 6 to 11 hours (ending at 11:30 PM) before approving results or restructuring flags ⚠️ PROLONGED BOARDROOM DELIBERATION.
Pass 1 AI Gatekeeper (llama-3.1-8b-instant):
Clear-cut categories (Results, Credit Ratings, Orders, M&A, Rights/QIP, USFDA, Plant Commissioning, Monthly Updates, Concalls/Presentations) skip Pass 1 and go straight to Pass 2.
Ambiguous "General / Company Update" filings send their BSE Subject Line (filings.subject) + Page 1 text to Groq (llama-3.1-8b-instant) to classify is_material: true/false.

## 5.3 Stage 2: Hybrid PDF Extraction, Scanned Vision OCR & Smart Section Chunking
Digital vs. Scanned Page Routing (extract.py):
Extracts text per page via PyMuPDF. Any page with < 80 characters of extractable text (such as a physical printed, stamped, and scanned letter like Kanoria Chemicals) is converted to a PNG and transcribed into Markdown tables by Z.AI (glm-4.6v-flash) or Mistral (pixtral-12b).
Smart Section Chunking for Large Documents (40–150 Pages):
Rather than truncating a 60-page Investor Presentation or 45-page Concall Transcript at page 10, extract.py scans page headers/contents and extracts:
For Concall Transcripts: Full Management Opening Remarks + full Analyst Q&A Exchanges (stripping moderator intros and legal disclaimers).
For Investor Presentations: Slides containing Financial Highlights, Segment Performance, Capex / Project Roadmap, Order Book, and FY Guidance (skipping generic macro/CSR slides).
For Annual Reports / Results: Auditor's Report (including Emphasis of Matter & CARO), Consolidated P&L, Balance Sheet, Cash Flow, Segment Footnote, Related Party Footnote, and Contingent Liabilities Footnote.
Local Compressed Text Cache (./data/text_cache/{news_id}.json.gz):
Stores the extracted Markdown text locally so re-analyses and prompt upgrades run in milliseconds without touching BSE servers or OCR quotas.

## 6. Bi-Temporal Persistent Memory Architecture

## 6.1 All 10 Compartments Inside Each Company's R2 Living Dossier (memory/{scrip_code}.json)
Every BSE-listed company has a single JSON dossier in R2 (~5 KB to 20 KB) organized into 10 strictly typed compartments:
| Compartment # | Compartment Key | Exact Fields Stored | How It Compounds & Stays Compact (< 20 KB) |
| 1 | identity_and_aliases | scrip_code ("500672"), symbol ("NOVARTIND"), company_name ("Evonile Pharma Limited"), former_names (["Novartis India Limited"]), industry, sector_lens, promoter_group_id, entities_and_brands ([{"name": "Jubilant Draximage Inc.", "type": "100% Step-Down WOS"}, {"name": "RUBY-FILL", "type": "Product Brand"}]). | Permanent identity anchor; prevents memory fragmentation across corporate rebrands or subsidiary filings. |
| 2 | financial_history | Bucketed into 3 sub-arrays: quarterly (last 12 quarters), annual (last 5 FYs), and half_yearly_bs_cf (last 6 balance sheet & cash flow snapshots). Each entry holds canonical period ("Q1FY27"), period_end ("2026-06-30"), known_since, source_news_id, and normalized ₹ Cr figures: revenue_cr, gross_profit_cr, core_ebitda_cr, ebitda_margin_pct, other_income_cr, finance_cost_cr (₹20.48 Cr), depreciation_cr, pbt_cr, current_tax_cr, deferred_tax_cr, pat_cr, eps_inr, total_debt_cr (₹399 Cr), cash_cr, net_worth_cr (-₹61.67 Cr), cwip_cr, gross_block_cr, intangibles_dev_cr, receivables_cr, inventory_cr, payables_cr, contract_assets_cr, ocf_cr, capex_cash_outflow_cr, and contingent_liabilities_cr. | Partitioned by period_kind and sorted by period_end DESC so a 7-year presentation of annual numbers never evicts recent quarterly rows. |
| 3 | sector_kpis | Stores industry-specific metrics defined in sectors.toml (e.g., nim_pct, gnpa_pct, nnpa_pct, pcr_pct, credit_cost_bps, cd_ratio_pct for Banks/NBFCs; pre_sales_cr, collections_cr for Realty; arpob_inr, occupancy_pct for Hospitals; sssg_pct, store_count for Retail). | Keeps latest 8 periods per KPI with explicit unit tags (%, bps, ₹ Cr, x). |
| 4 | segment_and_geography_mix | Array of segments ([{"segment": "Radiopharma", "revenue_share_pct": 44.6, "margin_pct": 38.0, "period": "Q1FY27", "known_since": "..."}]), export_revenue_share_pct, and top_customer_concentration_pct. | Upserted by canonical segment name; retains prior period value for trend comparison. |
| 5 | capex_and_projects | Keyed by project_id: name ("12 TPD Triacetin Plant"), location ("GIDC Ankleshwar, Gujarat"), expansion_type ("BROWNFIELD" | "GREENFIELD"), usage_type ("MERCHANT_SALE" | "CAPTIVE_INTEGRATION"), status ("PLANNED" | "IN_PROGRESS" | "PARTIALLY_COMMISSIONED" | "COMMISSIONED" | "DELAYED"), total_planned_capacity ("60 MW"), active_commissioned_capacity ("40 MW"), capex_outlay_cr, grant_or_subsidy_cr ("CAD 23.8M"), ec_pollution_clearance_status, target_utilization_notes ("40% in FY27 (~₹100 Cr rev); operating leverage at 65%"), known_since, updated_at, and history. | Active projects kept indefinitely; completed projects older than 4 quarters compacted into a 1-line summary. |
| 6 | guidance_and_watchlist | Keyed by promise_id: statement, category ("REVENUE" | "MARGIN" | "CAPEX_TIMELINE" | "DEBT_REDUCTION" | "UTILIZATION"), target_value, target_period ("FY27"), due_date ("2027-03-31"), given_on ("2026-09-15"), source_event ("Sep 2026 AGM"), status ("OPEN" | "DELIVERED" | "BREACHED" | "REVISED"), and history ([{news_id, filed_at, status, note}]). | OPEN items are never dropped by size limits; resolved items feed the Management Credibility Score (0–100%). |
| 7 | monthly_operational_ledger | Rolling 12-month table (period: "M2026-09", metric: "Commercial Vehicles", production_units: 1257, sales_units: 1071, export_units: 53, yoy_sales_pct: 32.0, known_since). | Automatically aggregates 3-month quarters (Jul+Aug+Sep) for early earnings previews; rolls months older than 18 months into annual totals. |
| 8 | corporate_actions_and_orders | Tracks Rights Issues (ACT-RI-2026: ₹120 Cr, 19:25 @ ₹12, Record Date 2026-10-15, Full payment on application), Acquisitions (₹1,250 Cr Minipress acquisition in Sep 2026), 18-month Preferential Warrant clocks, Stock Split/Bonus multipliers (split_bonus_factor), Credit Rating & Rated Bank Facility Limits (₹ Cr), and active Order Book items (L1_BIDDER vs. FIRM_LOA). | Matches IDs across stages so in-principle approvals, final terms, and L1-to-LoA conversions never double-count. |
| 9 | ownership_and_governance | Quarterly shareholding trend (promoter_pct, pledge_pct, fii_pct, dii_pct, retail_headcount), recent Insider/SAST open-market trades, Auditor name & opinion status (UNMODIFIED / EOM / QUALIFIED), and concall_evasion_flags. | Keeps last 6 quarters of shareholding and active governance flags. |
| 10 | calibration_and_peer_context | Empirical self-learning notes: pending_predictions (for Loop 2 verification), calibration_rules (e.g., historical ramp-up conservatism factor), historical_event_reactions (+1D / +3D average stock move by event type), feedstock_dependencies ("Glycerin"), and peer_margin_benchmarks ("Group G at 29% operating margin"). | Capped at 2 KB of high-signal learned rules. |


## 7. Master Prompt Engineering, Universal Distillation Rules & Output Specification

## 7.1 How the System Processes 1-Page Letters vs. 40-Page Concall Transcripts
To ensure the AI never balloons the R2 dossier or hallucinates numbers, Pass 2 uses a Universal Distillation Contract across all 22 industries and all document lengths:
95% Boilerplate & Fluff Stripping:
Strips all SEBI Regulation 30 headers, exchange addresses, company secretary signatures, safe-harbor disclaimers, operator instructions, and analyst pleasantries.
4-Bucket Distillation for 40-Page Concall Transcripts & Investor Presentations:
Regardless of whether a transcript is 35 pages or 60 pages long, the AI distills the entire document into:
Explicit Numerical Guidance Updates (target revenue, margin band, capacity utilization % by fiscal year, capex outlay, and debt reduction target).
Project & Capex Progress Deltas (commissioning dates, brownfield/greenfield status, active vs. total capacity).
Unit Economics, Feedstock & Order Book Deltas (raw material inflation/deflation, realizations per ton, order book execution duration, and segment revenue shares).
Q&A Forensic Insights (specific analyst questions on balance sheet/margins that management dodged, and any subtle timeline pushbacks vs. prior quarter guidance).

## 7.2 Complete Structured Output Specification (Pass2Output Contract)
Every Pass 2 AI response is validated against this exact field structure before deterministic code touches the database:
| Top-Level Section | Field Name | Type & Allowed Values | Mandatory Validation & Grounding Rule |
| 1. Triage & Classification | is_material | Boolean (true / false) | false only if pure procedural noise with zero fundamental or memory value. |
|  | event_category | Canonical Event ID from events.toml | Must match one of the official SEBI/BSE event classes (PRODUCT_LAUNCH, RIGHTS_ISSUE, CAPEX, MONTHLY_UPDATE, ORDER_WIN, M_AND_A, QUARTERLY_RESULTS, CREDIT_RATING, CONCALL_TRANSCRIPT, REGULATORY_USFDA, GOVERNANCE_AUDITOR). |
|  | impact_level | HIGH IMPACT | MODERATE IMPACT | LOW IMPACT | Refined deterministically by signals.py using the 0–100 Actionability Score. |
| 2. Card Header & Facts | headline | String (max 110 chars) | Active-voice 1-line summary with normalized ₹ Cr, %, or physical units. Any ungrounded ₹ Cr figure in headline forces needs_review = 1. |
|  | core_catalyst | String (max 140 chars) | 1-line executive thesis statement explaining the core economic driver. |
|  | what_happened_bullets | Array of 2–3 Strings | Pure, unadulterated facts from today's filing (zero SEBI Reg 30 legalese; all figures normalized to ₹ Cr or exact units). Every number is grounded against the filing text. |
| 3. Why It Matters (Memory & Forensics) | memory_and_execution_link | String | Connects today's filing to prior AGM/concall promises (promise_id), prior board approvals, or multi-month volume streaks stored in the R2 dossier. |
|  | quantified_impact_narrative | String | Full investor math: baseline revenue/cost from memory → incremental revenue/savings at guided utilization (e.g., 40% in FY27 = ~₹100 Cr; 65% = operating leverage inflection) → EBITDA & ROE impact. |
|  | peer_and_feedstock_context | String | Raw material price dynamics (e.g., glycerin at lifetime highs causing input pass-through inflation vs. volume growth) and margin comparison vs. sector peers in memory (e.g., Group G at 29% vs. 14% baseline). |
|  | missing_disclosure | String or null | Optional. Checked against R2 memory first! Only populated if a critical metric (capex outlay, expected sales, issue price/ratio, or completion timeline) is missing from both today's filing and historical memory. |
| 4. Verified Math Working | quantified_math_checks | Array of Objects (label, formula, variables, expected_result, unit) | Evaluated by Python's AST math checker (round(val, int_digits)). Each variable cites source: FILING (verified in PDF), MEMORY (verified in dossier), or ASSUMPTION. Mismatches hold the card for review. |
| 5. What to Track Next | milestone_dates | Array of {date, title, event_type} | Populates the Catalyst Calendar (2026-10-15 Record Date, 2026-10-22 Issue Opens, 2026-11-19 Issue Closes). |
|  | kpi_to_verify | String + {target_metric, target_period, expected_value} | Logs a verifiable follow-up into dossier.pending_predictions for upcoming quarterly results (e.g., "Verify Q3/Q4 FY27 utilization tracks 40% target (~₹100 Cr rev) and gross margin expands toward 19%"). |
|  | pending_approvals | String | Statutory, pollution board (GPCB/MPCB), shareholder postal ballot, or USFDA/Health Canada clearances required. |
|  | invalidation_risk | String | Specific operational, feedstock spread, working-capital, or under-subscription risk that would invalidate the thesis. |
| 6. Memory Delta | one_line_timeline_entry | String | Dated 1-sentence factual summary appended to the company's chronological timeline. |
|  | memory_delta | Structured Delta Object | Contains only new/updated entries for financial_history, sector_kpis, segment_mix, capex_and_projects, guidance_and_watchlist, monthly_operational_ledger, corporate_actions_and_orders, and ownership_and_governance. |


## 8. The Complete "Alpha-Matrix" Card Blueprint & 6 Full Worked Case Studies

## 8.1 The 8 Structural Zones of the "Alpha-Matrix" Card
Every material announcement card rendered on the website and exported as a shareable PNG image is divided into eight standardized zones so your eye can scan any company in under 5 seconds:

### Zone 1 — Top Telemetry & Tradability Bar:
Displays the Watchlist Star (★), NSE Symbol / BSE 6-Digit Scrip Code, Former Name alias badge if recently rebranded, Market Cap & Size Tier (Microcap <₹500 Cr, Smallcap ₹500–₹5,000 Cr, Midcap ₹5,000–₹20,000 Cr, Largecap >₹20,000 Cr), exact BSE dissemination timestamp down to the minute (DD MMM YYYY, HH:MM IST), Market-Session Tag ([Live Market] vs. [After-Market] vs. [Pre-Market]), Management Credibility Score (🎯 X/Y Promises Delivered), 30-Day Median Liquidity (💧 ₹ Cr/day), and Surveillance/Circuit Warning ([🔒 ASM / T2T] if applicable).

### Zone 2 — Classification & Impact Header:
Displays the Canonical Event Category Pill (PRODUCT LAUNCH, RIGHTS ISSUES, BUSINESS UPDATE, CAPEX, ORDER WIN, M&A, RESULTS), the 22-Industry Sector Pill (CHEMICALS, AUTO ANCILLARY, PHARMA), the Impact Badge (🟢 HIGH IMPACT, 🟠 MODERATE IMPACT, ⚪ LOW IMPACT), and the deterministic 0–100 Actionability Score.

### Zone 3 — Active-Voice Headline & Core Catalyst Abstract:
A punchy, active-voice headline containing exact normalized ₹ Cr or physical units, paired with a 1-line 📌 Core Catalyst summary explaining the underlying economic driver.

### Zone 4 — What Happened (100% Grounded Facts & Adaptive Table):
2 to 3 crisp bullets stating only the concrete facts from today's filing (zero SEBI Regulation 30 legal boilerplate). When a filing reports periodic volumes or multi-column numbers (like SML Mahindra or quarterly results), an adaptive comparison strip renders directly below the bullets.

### Zone 5 — Why It Matters (Persistent Memory, Forensics & Verified Math Working):
The shaded sage-green institutional intelligence box containing four distinct analytical bullets:
Memory & Execution Link: Connects today's filing to prior AGM/concall commitments, cumulative project progress, or prior board approvals stored in the R2 dossier.
Quantified Impact & Operating Leverage Math: Computes exact revenue, EBITDA, dilution, or interest-saving math from baseline memory numbers, accompanied by an expandable [🔢 Show Working] drawer that displays the exact AST-verified formula and the provenance (FILING, MEMORY, ASSUMPTION) of every input.
Feedstock, Peer & Accounting Forensics: Evaluates raw material price spreads, peer margin comparisons, and Ind AS accounting mechanics.
Contextual Missing Disclosure (Optional): Appears only if a critical metric is absent from both today's filing and the R2 memory dossier.

### Zone 6 — What to Track Next (Forward-Looking Triggers):
Isolates the exact future checkpoints: ⏱️ Milestone Dates (auto-synced to the Catalyst Calendar), 📊 KPI to Verify (auto-logged into pending_predictions for next quarter's results), ⚖️ Pending Approvals, and ⚠️ Invalidation Risk.

### Zone 7 — Sector-Aware Financial & Momentum Footer:
Displays latest quarterly revenue (or sector-specific KPIs from sectors.toml like NII / GNPA for banks), Total Debt, Net Worth, Historical Post-Event Reaction (📈 Past Reaction), and 1W / 1M / 1Y stock returns.

### Zone 8 — Verification & Action Bar:
Displays the strict Grounding Badge (✓ Numbers verified (N/N) or ⚠️ X of Y numbers verified), [📄 Official PDF (Np)], [🗂️ 360° Memory Drawer], [📸 Copy Card PNG], and the self-learning feedback buttons ([🔥 Star Signal] / [🗑️ Mark Noise]).

## 8.2 The 6 Complete Gold-Standard Worked Case Studies

### Case Study 1: Kanoria Chemicals & Industries Limited (506525 · Smallcap Specialty Chemicals)
```text
+---------------------------------------------------------------------------------------------------+
| [★] KANORICHEM · 506525 · ₹806 Cr · Smallcap              07 Oct 2026, 17:50 IST [After-Mkt Filing]|
| [PRODUCT LAUNCH]  [CHEMICALS]  [🎯 Credibility: 4/5 (80%)]  [💧 Liq: ₹3.8 Cr/d]     [🟢 HIGH IMPACT]|
+---------------------------------------------------------------------------------------------------+
| Kanoria Chemicals launches 12 TPD Triacetin plant at Ankleshwar                                   |
| 📌 Core Catalyst: Brownfield commercialization of food & pharma-grade specialty ester capacity     |
|                                                                                                   |
| WHAT HAPPENED (VERIFIED FACTS)                                                                    |
| 👉 Launched a new 12 Metric Tons per Day (TPD) (~3,960 MTPA at 330 operating days) Triacetin      |
|    manufacturing facility at its existing GIDC Ankleshwar site in Gujarat on October 7, 2026.     |
| 👉 Categorized under Chemical / Food and Pharma; caters to both domestic and international        |
|    markets, expanding its downstream specialty portfolio across food, pharma, and resins.         |
|                                                                                                   |
| +-----------------------------------------------------------------------------------------------+ |
| | 🧠 WHY IT MATTERS (PERSISTENT MEMORY, FORENSICS & QUANTIFIED IMPACT)                          | |
| | 👉 [✅ Promise Delivered · Sep 2026 AGM]: Management planned to commission Triacetin capacity | |
| |    in FY27 to diversify away from volatile bulk commodity chemicals; this launch executes     | |
| |    the expansion roadmap reiterated at the September 2026 AGM on schedule.                    | |
| | 👉 [Quantified Impact & Operating Leverage]: Management guided in prior calls for a ~40%      | |
| |    capacity utilization ramp-up across FY27 (generating ~₹100 Cr in incremental revenue),     | |
| |    with major operating leverage unlocking at 65% utilization (guided in Q4 FY25 call to      | |
| |    double specialty sales). Benchmarking against specialty peer Group G (printing ~29%        | |
| |    operating margins over trailing quarters vs. Kanoria's ~14% baseline), mix shift toward    | |
| |    value-added esters can structurally lift operating margins toward ~19% and expand ROE      | |
| |    from ~12% to ~14%.                                                                         | |
| |    [🔢 Show Working: full_cap_rev_cr (250.0, MEMORY) * fy27_util (0.40, MEMORY) = ₹100.0 Cr]  | |
| | 👉 [Feedstock & Brownfield Forensics]: Glycerin feedstock prices are sitting near lifetime    | |
| |    highs, which may temporarily inflate headline sales via raw-material cost pass-through     | |
| |    rather than pure volume growth. Because the unit is a brownfield addition inside the       | |
| |    existing GIDC Ankleshwar complex, shared steam/ETP utilities boost incremental ROCE,       | |
| |    though Ind AS 16 depreciation starts hitting the P&L immediately in Q3 FY27.               | |
| +-----------------------------------------------------------------------------------------------+ |
|                                                                                                   |
| 🎯 WHAT TO TRACK NEXT (FORWARD-LOOKING TRIGGERS)                                                  |
| ⏱️ Milestone Date: Q3/Q4 FY27 financial results to verify if utilization tracks the ~40%          |
|    (~₹100 Cr revenue run-rate) FY27 target and progresses toward the 65% leverage inflection.     |
| 📊 KPI to Verify: Gross margin % trajectory relative to top-line revenue growth (isolating true   |
|    specialty margin realization from inflated glycerin feedstock pass-through).                   |
| ⚖️ Pending Approvals: None for launch (built within existing GIDC Ankleshwar site); monitor       |
|    customer batch qualification for export food/pharma grades (typically 3–6 months).             |
| ⚠️ Invalidation Risk: Widening spread between lifetime-high glycerin input costs and sticky       |
|    end-user pricing compressing gross spreads, or utilization lagging below 40% in FY27.          |
|                                                                                                   |
| ₹460 Cr Q1 FY27 Rev | Debt: ₹185 Cr | Net Worth: ₹312 Cr | 1W -8.9% · 1M +17% · 1Y +134%          |
| ------------------------------------------------------------------------------------------------- |
| [✓ Numbers verified (8/8)]   [📄 Official PDF (1p)]  [🗂️ 360° Memory (9)]  [📸 Copy PNG]  [🔥/🗑️]  |
+---------------------------------------------------------------------------------------------------+
```

### Case Study 2: Shivam Autotech Limited (532776 · Smallcap Auto Ancillary)
```text
+---------------------------------------------------------------------------------------------------+
| [★] SHIVAMAUTO · 532776 · ₹223 Cr · Smallcap              08 Oct 2026, 14:58 IST [Live-Mkt Filing] |
| [RIGHTS ISSUES]  [AUTO ANCILLARY]  [🎯 Credibility: 2/5 (40%)]  [💧 Liq: ₹1.1 Cr/d] [🟠 MODERATE]   |
+---------------------------------------------------------------------------------------------------+
| Shivam Autotech sets ₹120 Cr rights issue terms at ₹12 per share                                  |
| 📌 Core Catalyst: Deeply dilutive balance-sheet rescue raise to service ₹399 Cr debt burden       |
|                                                                                                   |
| WHAT HAPPENED (VERIFIED FACTS)                                                                    |
| 👉 Approved terms for a Rights Issue of up to 10 Crore fully paid-up equity shares (Face Value    |
|    ₹2 each) at ₹12 per share (including ₹10 premium) to raise up to ₹120 Cr (₹12,000 Lakhs),      |
|    with the full ₹12/share payable upfront on application.                                        |
| 👉 Eligible shareholders will receive 19 rights shares for every 25 shares held (19:25 ratio)     |
|    as on the October 15, 2026 Record Date.                                                        |
| 👉 Issue opens October 22, 2026, on-market renunciation of Rights Entitlements (REs) closes       |
|    November 13, 2026, and the issue closes November 19, 2026.                                     |
|                                                                                                   |
| +-----------------------------------------------------------------------------------------------+ |
| | 🧠 WHY IT MATTERS (PERSISTENT MEMORY, FORENSICS & QUANTIFIED IMPACT)                          | |
| | 👉 [Memory Link · Jul 1, 2026 Board Approval]: Sets the final price and 19:25 entitlement     | |
| |    ratio for the equity fundraise approved in-principle by the board on July 1, 2026 and      | |
| |    cleared by exchanges on September 29, 2026.                                                | |
| | 👉 [Quantified Dilution & Balance-Sheet Stress]: Expands the equity base by 76.0% (43.2%      | |
| |    post-money dilution). The raise comes as net worth fell to negative ₹61.67 Cr in June      | |
| |    2026, hit by ₹20.48 Cr in quarterly interest costs (~₹81.9 Cr annualized) across a         | |
| |    ₹399 Cr debt pile. Even at 100% subscription, the ₹120 Cr inflow retires ~30.1% of gross   | |
| |    debt, saving ~₹24.6 Cr in annualized interest expense and restoring net worth to ~+₹58 Cr. | |
| |    [🔢 Show Working: 19 / (25 + 19) = 43.18% post-money dilution | Verified: 100% Grounded]   | |
| | 👉 [⚠️ Missing Disclosure]: Filing does not disclose whether promoters will subscribe to      | |
| |    unsubscribed public portions or whether part of the ₹120 Cr represents conversion of       | |
| |    existing promoter unsecured loans (which reduces debt but brings ₹0 fresh cash).           | |
| +-----------------------------------------------------------------------------------------------+ |
|                                                                                                   |
| 🎯 WHAT TO TRACK NEXT (FORWARD-LOOKING TRIGGERS)                                                  |
| ⏱️ Milestone Dates: Oct 15, 2026 (Record Date); Oct 22, 2026 (Issue Opens); Nov 13, 2026 (RE      |
|    Trading Closes); Nov 19, 2026 (Issue Closes).                                                  |
| 📊 KPI to Verify: Final subscription percentage in late November and Q3/Q4 FY27 quarterly         |
|    finance cost reduction (Target: quarterly interest dropping from ₹20.48 Cr toward <₹15 Cr).    |
| ⚖️ Pending Approvals: Letter of Offer filing and final allotment/listing approval post Nov 19.    |
| ⚠️ Invalidation Risk: Under-subscription leaving the ₹399 Cr debt load unresolved and forcing     |
|    further distressed dilution or debt restructuring.                                             |
|                                                                                                   |
| ₹110 Cr Q1 FY27 Rev | Debt: ₹399 Cr | Net Worth: -₹61.67 Cr (Neg) | 1W -2.1% · 1M -3.8% · 1Y -46% |
| ------------------------------------------------------------------------------------------------- |
| [✓ Numbers verified (11/11)]  [📄 Official PDF (1p)]  [🗂️ 360° Memory (7)]  [📸 Copy PNG]  [🔥/🗑️] |
+---------------------------------------------------------------------------------------------------+
```

### Case Study 3: SML Mahindra Limited (505192 · Midcap Commercial Vehicles)
```text
+---------------------------------------------------------------------------------------------------+
| [★] SMLMAH (Formerly SML Isuzu) · 505192 · ₹8,470 Cr · Midcap   08 Oct 2026, 15:41 IST [After-Mkt]|
| [BUSINESS UPDATE]  [AUTOMOBILE / CV]  [🎯 Credibility: 5/5]  [💧 Liq: ₹18.5 Cr/d]    [🟠 MODERATE] |
+---------------------------------------------------------------------------------------------------+
| SML Mahindra sold 1,071 vehicles in September, up 32% YoY                                         |
| 📌 Core Catalyst: Second straight month of >30% domestic CV sales growth offsetting export dip    |
|                                                                                                   |
| WHAT HAPPENED (VERIFIED FACTS)                                                                    |
| 👉 Reported September 2026 Commercial Vehicle volumes: Total Sales rose 31.9% YoY to 1,071 units  |
|    (vs. 812 units in Sep FY26), while Production rose 19.8% YoY to 1,257 units (vs. 1,049 units). |
| 👉 Monthly exports fell 61.6% YoY to 53 units from 138 units last year.                           |
|                                                                                                   |
| +-----------------------------------------------------------------------------------------------+ |
| | THIS MONTH (SEP 2026)                     SEP FY26 (PRIOR)     SEP FY27 (ACTUAL)       YOY %  | |
| | Commercial Vehicles · Production               1,049 units           1,257 units      +19.8%  | |
| | Commercial Vehicles · Total Sales                812 units           1,071 units      +31.9%  | |
| | Commercial Vehicles · Exports                    138 units              53 units      -61.6%  | |
| +-----------------------------------------------------------------------------------------------+ |
|                                                                                                   |
| +-----------------------------------------------------------------------------------------------+ |
| | 🧠 WHY IT MATTERS (PERSISTENT MEMORY, FORENSICS & QUANTIFIED IMPACT)                          | |
| | 👉 [Memory Link · Multi-Month Streak]: Sales grew 32% vs. last year, holding above 30% YoY    | |
| |    growth for a second straight month after August 2026's 34.4% rise.                         | |
| | 👉 [Export Reversal & Inventory Math]: Exports fell to 53 units from 138 units last year,     | |
| |    reversing the export surge seen in August and dragging on overall volume. Production       | |
| |    exceeded sales by 186 units in September, building channel stock ahead of the Oct–Nov      | |
| |    festive bus and cargo delivery window.                                                     | |
| | 👉 [🔮 Q2 FY27 Earnings Preview]: Combining Jul + Aug (+34.4%) + Sep (+31.9%) monthly filings | |
| |    from the dossier confirms strong Q2 FY27 operating leverage ahead of formal Q2 results.    | |
| |    [🔢 Show Working: (1071 - 812) / 812 = +31.90% YoY Sales | Verified: 100% Grounded]        | |
| +-----------------------------------------------------------------------------------------------+ |
|                                                                                                   |
| 🎯 WHAT TO TRACK NEXT (FORWARD-LOOKING TRIGGERS)                                                  |
| ⏱️ Milestone Date: Early November 2026 (October monthly volume release) and Q2 FY27 Results.      |
| 📊 KPI to Verify: Combined Oct+Nov festive volume growth (neutralizing Diwali calendar shift)     |
|    and Q2 FY27 EBITDA margin expansion from >30% Aug–Sep volume operating leverage.               |
| ⚠️ Invalidation Risk: Sustained export weakness in neighbouring South Asian/African markets or    |
|    post-festive inventory destocking if October retail registrations lag wholesale dispatches.    |
|                                                                                                   |
| ₹958 Cr Q1 FY27 Rev | Debt: ₹340 Cr | Net Worth: ₹610 Cr | 1W -7.3% · 1M -4.7% · 1Y +98%          |
| ------------------------------------------------------------------------------------------------- |
| [✓ Numbers verified (9/9)]   [📄 Official PDF (1p)]  [🗂️ 360° Memory (15)]  [📸 Copy PNG]  [🔥/🗑️] |
+---------------------------------------------------------------------------------------------------+
```

### Case Study 4: Evonile Pharma Limited (500672 · Smallcap Pharmaceuticals)
```text
+---------------------------------------------------------------------------------------------------+
| [★] NOVARTIND (Evonile Pharma) · 500672 · ₹4,905 Cr · Smallcap     08 Oct 2026 [After-Mkt Filing] |
| [RIGHTS ISSUES]  [PHARMACEUTICALS]  [🎯 Credibility: 4/4]  [💧 Liq: ₹9.4 Cr/d]       [🟠 MODERATE] |
+---------------------------------------------------------------------------------------------------+
| Evonile Pharma board approves rights issue of up to ₹900 Cr                                       |
| 📌 Core Catalyst: Partly paid-up equity raise to refinance September's ₹1,250 Cr Minipress buyout |
|                                                                                                   |
| WHAT HAPPENED (VERIFIED FACTS)                                                                    |
| 👉 Evonile Pharma (formerly Novartis India Limited) approved raising up to ₹900 Cr (₹9,000        |
|    million) through a rights issue of partly paid-up equity shares of ₹5 face value each.         |
| 👉 The board formed a Rights Issue Committee to finalize the issue price, entitlement ratio,      |
|    payment call schedule, and record date; capital raise is subject to shareholder approval       |
|    via postal ballot.                                                                             |
|                                                                                                   |
| +-----------------------------------------------------------------------------------------------+ |
| | 🧠 WHY IT MATTERS (PERSISTENT MEMORY, FORENSICS & QUANTIFIED IMPACT)                          | |
| | 👉 [Memory Link · Sep 2026 M&A & Oct 5 Notice]: This approval follows the board meeting       | |
| |    notice filed on October 5, 2026, and directly finances the company's ₹1,250 Cr Minipress   | |
| |    brand acquisition announced in September 2026.                                             | |
| | 👉 [Quantified Refinancing & Instrument Forensics]: The ₹900 Cr raise covers 72.0% of the     | |
| |    ₹1,250 Cr Minipress acquisition outlay (~18.3% of current ₹4,905 Cr market cap). Because   | |
| |    the shares are structured as partly paid-up equity shares, cash inflows and bridge-debt    | |
| |    repayment will occur in tranches (application money followed by subsequent calls) rather   | |
| |    than retiring the entire acquisition debt on Day 1.                                        | |
| |    [🔢 Show Working: 900.0 / 1250.0 = 72.0% of Minipress outlay | Verified: 100% Grounded]    | |
| | 👉 [⚠️ Missing Disclosure]: The issue price, upfront application call %, entitlement ratio,   | |
| |    and record date are not yet announced; these terms will decide final shareholder dilution. | |
| +-----------------------------------------------------------------------------------------------+ |
|                                                                                                   |
| 🎯 WHAT TO TRACK NEXT (FORWARD-LOOKING TRIGGERS)                                                  |
| ⏱️ Milestone Date: Postal Ballot notice & voting outcome (within 30 days) and Rights Issue        |
|    Committee meeting announcing the issue price, ratio, and upfront call percentage.              |
| 📊 KPI to Verify: Issue price discount to market price and gross margin accretion from integrating|
|    the high-margin Minipress cardiovascular portfolio against Evonile's ₹104 Cr Q1 revenue base.  |
| ⚖️ Pending Approvals: Shareholder approval via postal ballot and SEBI/BSE in-principle clearance. |
| ⚠️ Invalidation Risk: Deep discount pricing causing higher-than-expected equity dilution, or      |
|    high bridge-loan interest costs eating into PAT if partly paid tranches are spaced far apart.  |
|                                                                                                   |
| ₹104 Cr Q1 FY27 Rev | Debt: Bridge Facility | Net Worth: ₹780 Cr | 1W +4.8% · 1M +23% · 1Y +130%  |
| ------------------------------------------------------------------------------------------------- |
| [✓ Numbers verified (7/7)]   [📄 Official PDF (2p)]  [🗂️ 360° Memory (11)]  [📸 Copy PNG]  [🔥/🗑️] |
+---------------------------------------------------------------------------------------------------+
```

### Case Study 5: Jubilant Pharmova Limited (JUBLPHARMA · Midcap Pharmaceuticals)
```text
+---------------------------------------------------------------------------------------------------+
| [★] JUBLPHARMA · 530019 · ₹14,849 Cr · Midcap                   08 Oct 2026 [Live-Market Filing]  |
| [CAPEX]  [PHARMACEUTICALS / RADIOPHARMA]  [🎯 Credibility: 85%]  [💧 Liq: ₹32 Cr/d]  [🟢 HIGH]    |
+---------------------------------------------------------------------------------------------------+
| Jubilant Pharmova to invest CAD 94.5M to double Ruby-Fill capacity                                |
| 📌 Core Catalyst: Grant-subsidized brownfield doubling of its fastest-growing (30%+) isotope line |
|                                                                                                   |
| WHAT HAPPENED (VERIFIED FACTS)                                                                    |
| 👉 Step-down wholly owned subsidiary Jubilant Draximage Inc. will invest CAD 94.5 million         |
|    (~₹580 Cr) to modernize and expand its Kirkland, Québec facility in Canada.                    |
| 👉 The investment aims to double production capacity of its flagship cardiac PET imaging product  |
|    RUBY-FILL® (Rubidium-82 generator), whose customer base has doubled over the last 3 years.     |
| 👉 The Government of Canada will provide CAD 23.8 million (~₹146 Cr, or 25.2% of project cost)    |
|    in financial support through its Strategic Response Fund.                                      |
|                                                                                                   |
| +-----------------------------------------------------------------------------------------------+ |
| | 🧠 WHY IT MATTERS (PERSISTENT MEMORY, FORENSICS & QUANTIFIED IMPACT)                          | |
| | 👉 [Memory Link · Segment Weight & Concall]: Radiopharma makes up 44.6% of total company      | |
| |    sales. On its last earnings call, management noted RUBY-FILL® was growing 30%+ YoY even    | |
| |    as other radiopharma lines faced global supply shortages.                                  | |
| | 👉 [Quantified Subsidy & Brownfield Economics]: The CAD 23.8M Canadian government grant       | |
| |    subsidizes 25.19% of the gross capex, reducing Jubilant's net outlay to CAD 70.7M          | |
| |    (~₹434 Cr). Because Kirkland is an existing facility (and the sole site in Canada          | |
| |    producing these medical isotopes) and Jubilant Draximage is a 100% step-down subsidiary,   | |
| |    100% of the incremental high-margin specialty cash flows accrue to listed shareholders.    | |
| |    [🔢 Show Working: 94.5 - 23.8 = CAD 70.7M net outlay (25.19% grant) | Verified: 100%]      | |
| | 👉 [⚠️ Missing Disclosure]: The filing does not state a construction completion timeline or   | |
| |    target commissioning year, which decides when the added capacity begins contributing to    | |
| |    consolidated revenue.                                                                      | |
| +-----------------------------------------------------------------------------------------------+ |
|                                                                                                   |
| 🎯 WHAT TO TRACK NEXT (FORWARD-LOOKING TRIGGERS)                                                  |
| ⏱️ Milestone Date: Upcoming Q2 FY27 earnings call / investor presentation to extract the exact    |
|    Kirkland commissioning quarter and annual capex phasing schedule.                              |
| 📊 KPI to Verify: Radiopharma segment EBITDA margin expansion and RUBY-FILL® generator install    |
|    base growth across US/global hospital networks (45 US radiopharmacies).                        |
| ⚖️ Pending Approvals: Health Canada and USFDA cGMP qualification of the new production lines.     |
| ⚠️ Invalidation Risk: Multi-year regulatory commissioning lag or Strontium-82 raw isotope         |
|    feedstock bottlenecks limiting utilization of the doubled generator capacity.                  |
|                                                                                                   |
| ₹2,229 Cr Q1 FY27 Rev | Debt: ₹3,450 Cr | Net Worth: ₹5,620 Cr | 1W -6.7% · 1M -6.6% · 1Y -14%    |
| ------------------------------------------------------------------------------------------------- |
| [✓ Numbers verified (8/8)]   [📄 Official PDF (1p)]  [🗂️ 360° Memory (14)]  [📸 Copy PNG]  [🔥/🗑️] |
+---------------------------------------------------------------------------------------------------+
```

### Case Study 6: Hariom Pipe Industries Limited (543517 · Smallcap Steel Pipes & Tubes)
```text
+---------------------------------------------------------------------------------------------------+
| [★] HARIOMPIPE · 543517 · ₹2,410 Cr · Smallcap                 14 Oct 2026, 20:03 IST [After-Mkt] |
| [CAPEX / COMMISSIONING]  [IRON & STEEL PRODUCTS]  [🎯 Credibility: 90%]          [🟢 HIGH IMPACT] |
+---------------------------------------------------------------------------------------------------+
| Hariom Pipe commissions 10 MW solar units; 40 MW of 60 MW plan now live                           |
| 📌 Core Catalyst: Captive green power backward integration cutting per-ton steel conversion cost  |
|                                                                                                   |
| WHAT HAPPENED (VERIFIED FACTS)                                                                    |
| 👉 Subsidiary commissioned two grid-connected solar power plants totaling 10 MW under the         |
|    Mukhyamantri Saur Krushi Vahini Yojana (MSKVY 2.0) scheme in Maharashtra.                      |
| 👉 Brings cumulative operational renewable energy capacity to 40 MW out of the planned 60 MW      |
|    green power rollout (66.7% of total planned solar capacity now active).                        |
|                                                                                                   |
| +-----------------------------------------------------------------------------------------------+ |
| | 🧠 WHY IT MATTERS (PERSISTENT MEMORY, FORENSICS & QUANTIFIED IMPACT)                          | |
| | 👉 [✅ Promise Delivered · Cumulative Rollout Tracker]: Advances the 60 MW renewable energy   | |
| |    roadmap stored in memory to two-thirds completion (40 MW live, 20 MW remaining),           | |
| |    delivering on Q1 guidance to insulate steel pipe rolling/furnace margins from grid tariffs.| |
| | 👉 [Quantified EBITDA & Margin Math]: TTM power & fuel expenses stand at ~₹92 Cr. Replacing   | |
| |    state grid power with captive/MSKVY solar across the 40 MW active block is modeled to      | |
| |    cut ~15% off annual power overheads, translating directly to ~+₹13.8 Cr in annual EBITDA   | |
| |    accretion (~1.8% operating margin expansion on current revenue base) with zero top-line    | |
| |    dilution.                                                                                  | |
| |    [🔢 Show Working: ttm_power_cr (92.0, MEMORY) * savings_pct (0.15, MEMORY) = ₹13.8 Cr]     | |
| | 👉 [⚠️ Missing Disclosure]: Filing omits the specific capex outlay incurred for this 10 MW    | |
| |    block and the expected commissioning date for the final 20 MW tranche.                     | |
| +-----------------------------------------------------------------------------------------------+ |
|                                                                                                   |
| 🎯 WHAT TO TRACK NEXT (FORWARD-LOOKING TRIGGERS)                                                  |
| ⏱️ Milestone Date: Commissioning notice for the remaining 20 MW solar block and Q3 FY27 results.  |
| 📊 KPI to Verify: Power & Fuel expense as a % of total revenue in Q3 FY27 (Target: compression    |
|    by 150–180 bps YoY) and EBITDA/ton expansion toward peer benchmarks.                           |
| ⚖️ Pending Approvals: MSEDCL grid synchronization and banking/open-access credit settlement.      |
| ⚠️ Invalidation Risk: State discom wheeling/banking charge hikes or monsoon PLF dips in Q2/Q3.    |
|                                                                                                   |
| ₹340 Cr Q1 FY27 Rev | Debt: ₹380 Cr | Net Worth: ₹510 Cr | 1W +2.4% · 1M +12.1% · 1Y +45.2%       |
| ------------------------------------------------------------------------------------------------- |
| [✓ Numbers verified (7/7)]   [📄 Official PDF (2p)]  [🗂️ 360° Memory (12)]  [📸 Copy PNG]  [🔥/🗑️] |
+---------------------------------------------------------------------------------------------------+
```

## 9. All 50 "Meter-Deep" Forensic & Indian Market Alpha Modules (Full Unabridged Explanations)
To give an individual investor a decisive analytical edge over generic institutional screens, the platform implements 50 domain-specific forensic modules across eight domains.

### Domain 1: Capacity, Capex, Environmental & Industrial Physics (Modules 1–8)

### Module 1: Nameplate-to-Effective Capacity Physics (330-Day vs. Batch Conversion)
The Trap: When a company announces a 12 TPD (Tons Per Day) plant, retail investors multiply 12 × 365 = 4,380 tons/year. In real industrial manufacturing, continuous chemical reactors require ~35 days/year of statutory boiler inspection, catalyst regeneration, and preventive maintenance (330 operating days/year), while batch specialty chemical, pharma, and auto-ancillary plants operate 250 to 300 days/year.
The Rule: Deterministic math normalizes TPD to MTPA using 330 days for continuous process industries (12 TPD × 330 = 3,960 MTPA) and 275 days for batch/discrete industries unless the filing explicitly states an annual MTPA figure.

### Module 2: Gross Block Asset-Turnover Sanity Check (Fixed Asset Turns)
The Trap: Promoters sometimes announce a ₹100 Cr capex and claim in a press release that it will generate ₹600 Cr of high-margin revenue (6.0x asset turnover) in an industry where machinery physically cannot produce more than 1.8x asset turns.
The Rule: Every industry in sectors.toml has a normal asset_turn_band (Incremental Peak Revenue / Gross Capex). If management's guided revenue implies an asset turnover exceeding 1.5× the top of the sector band, the card fires 🚨 ASSET-TURN ANOMALY and checks whether assembly is outsourced/contract-manufactured. Conversely, if a filing omits capex outlay, the engine estimates implied capex from guided revenue divided by sector median asset turns and cross-checks it against the balance sheet's Capital Work in Progress (CWIP).

### Module 3: The Ind AS 16 CWIP-to-Gross-Block "Depreciation & Interest Cliff"
The Trap: Under Ind AS 16, while a plant is under construction (sitting in CWIP on the balance sheet), the company capitalizes borrowing interest into CWIP and charges ₹0 depreciation on the P&L. The exact day commercial production is declared (e.g., October 7, 2026 for Kanoria Chemicals), CWIP transfers into Gross Block: 100% of depreciation and 100% of loan interest immediately hit the P&L, even if first-quarter utilization is only 15%.
The Rule: On every PLANT_COMMISSIONING card, the engine calculates the estimated quarterly depreciation + interest step-up and warns that initial quarters may show temporary PAT compression until capacity utilization crosses the fixed-cost breakeven threshold (typically 40%–50%).

### Module 4: Captive Backward Integration vs. External Merchant Capacity
The Trap: A company announces a 30,000 MTPA intermediate chemical plant or a 40 MW solar plant. Naive analysts add 30,000 MTPA × Market Price to next year's revenue forecast. If the output is used internally (captive consumption), external top-line revenue increases by ₹0—all the benefit flows into raw-material or power cost savings (Gross / EBITDA Margin expansion).
The Rule: Every capacity addition is tagged as MERCHANT_SALE (top-line + EBITDA driver), CAPTIVE_INTEGRATION (zero top-line, pure EBITDA margin driver), or HYBRID.

### Module 5: Brownfield vs. Greenfield Economics & ROCE Multiplier
The Trap: Treating all capex equally. A Greenfield factory on raw land requires spending 30%–40% of capex on non-productive civil infrastructure (land, boundary walls, power substation, steam boilers, Effluent Treatment Plant, canteen, admin block) and takes 18–24 months to stabilize. A Brownfield expansion at an existing site (such as Kanoria's GIDC Ankleshwar site or Jubilant's Kirkland site) plugs straight into existing utilities, ETP, and plant leadership.
The Rule: The parser detects phrases like "at its existing manufacturing site" or "expand its Kirkland facility", tags the project BROWNFIELD, and models higher incremental ROCE and faster utilization ramp-up than baseline company averages.

### Module 6: Customer Qualification, PPAP & Stability-Batch Lag
The Trap: Expecting 80% utilization in the quarter immediately following plant launch. In Pharma APIs/Formulations, Food/Pharma Specialty Chemicals, and Auto Ancillaries, institutional buyers require 3 to 6 months of stability batch data, DMF/CEP filings, or PPAP (Production Part Approval Process) audits before commercial bulk dispatches begin.
The Rule: For regulated/OEM end-markets, the timeline tracker automatically models a 1-to-2 quarter qualification ramp before expecting full commercial run-rate.

### Module 7: Pollution Control Board (GPCB / MPCB) & MoEFCC Environmental Clearance (EC / CTE / CTO) Forensics
The Indian Market Reality: In Gujarat (GPCB), Maharashtra (MPCB), and across India, chemical, pharma, bulk drug, and metal factories face a strict three-step regulatory gate: Environmental Clearance (EC) → Consent to Establish (CTE) → Consent to Operate (CTO).
The Rule:
When a company announces a new chemical/API capex, check if EC and CTE are already in hand; without EC, construction cannot legally start (often adding a 9–15 month delay).
Conversely, if a company files a Regulation 30 notice regarding a GPCB/MPCB Closure Notice or Show-Cause Notice at a major plant (like Ankleshwar, Vapi, Dahej, Roha, or Tarapur), compute the daily revenue loss (Plant Revenue Share % × Annual Revenue / 330) and check whether the closure is a temporary 15-day compliance check or a severe Zero Liquid Discharge (ZLD) violation.

### Module 8: DGTR Anti-Dumping Duty (ADD), Safeguard Duty & Minimum Import Price (MIP) Catalyst Engine
The Indian Market Reality: For Indian Specialty & Bulk Chemicals, Steel/Pipes, Solar Modules/Glass, API Pharma, Fibres, and tyre/rubber chemicals, a single notification from the Directorate General of Trade Remedies (DGTR) or Ministry of Finance imposing a 5-year Anti-Dumping Duty (ADD) against Chinese imports can lift a domestic manufacturer's EBITDA margins from 8% to 22% overnight!
The Rule: Whenever a company or sector filing mentions a DGTR investigation initiation, final ADD recommendation, or Ministry of Finance customs notification on a chemical/product in the company's R2 entities_and_brands list, the engine calculates the Import Landed Cost Parity lift (ADD $/MT × Company Domestic Sales Volume MT) to quantify the immediate pricing umbrella.

### Domain 2: Order Book Quality, Execution Physics & Working Capital Traps (Modules 9–14)

### Module 9: Short-Cycle EPC/Supply vs. Multi-Year O&M Split (Book-to-Bill Math)
The Trap: A railway, solar, water, or defence company announces a "₹500 Cr Order Win". Buried in the table is that ₹150 Cr is for equipment supply over 12 months, and ₹350 Cr is for 15-year Operations & Maintenance (O&M) (₹23.3 Cr/year).
The Rule: Every order win is split into Supply/EPC Value vs. O&M/AMC Value, and the card highlights Annualized Order Run-Rate = (EPC / EPC_Years) + (O&M / OM_Years) as a percentage of TTM Revenue.

### Module 10: L1 Bidder vs. LoI vs. Firm LoA / Notice to Proceed (NTP) Deduplication
The Trap: Companies file a celebratory announcement when declared L1 (Lowest Bidder) in a tender, and then file a second celebratory announcement 3 months later when the formal Letter of Award (LoA) arrives for the exact same project.
The Rule: L1 filings are logged in R2 memory with stage = "L1_BIDDER". When a subsequent LoA or Work Order arrives matching the client/tender/value, dossier.py merges it in-place and stamps the card: 🔄 L1-TO-LOA CONVERSION (Previously announced as L1 on [Date] — Not a net new order addition).

### Module 11: The "Working Capital & Bank Guarantee (BG) Starvation" Check
The Trap: A small-cap with ₹200 Cr TTM revenue, ₹280 Cr debt, 195 receivable days, and ₹8 Cr cash announces a ₹400 Cr EPC order. Executing a ₹400 Cr order requires ~₹40 Cr in Bank Guarantee limits (10% PBG) and ~₹120 Cr in working capital. Without fresh capital, the company cannot buy raw materials to execute the order.
The Rule: Cross-checks Annualized New Order Value against Unutilized Bank Limits + Free Cash and Trailing Receivable Days. Fires ⚠️ WORKING CAPITAL BOTTLENECK when balance sheet liquidity cannot support the order's execution cycle.

### Module 12: Fixed-Price Contract vs. Price-Variation Clause (PVC) Margin Risk
The Rule: On orders with execution timelines exceeding 12 months, checks whether the contract includes a Raw Material Price Escalation / Price Variation Clause (PVC). Fixed-price contracts over 18+ months during steel, copper, or aluminum inflation are flagged for margin compression risk.

### Module 13: Friday-Night Order Retraction, Scope Reduction & Liquidated Damages (LD) Tracker
The Rule: Matches vague Regulation 30 contract updates, arbitration notices, or scope revisions against the company's active order_book_items in R2, deducting cancelled amounts and flagging 🚨 ORDER BOOK RETRACTION / LD PENALTY.

### Module 14: Bid-Pipeline-to-Win-Rate Conversion Tracker
The Rule: When management states in a concall "We have bid for ₹3,000 Cr of tenders expected to open this half", the dossier tracks the stated bid_pipeline_cr against cumulative orders_won_cr over the next 2 quarters to compute the company's Empirical Tender Win Rate %.

### Domain 3: P&L Quality of Earnings, Tax & Accounting Forensics (Modules 15–22)

### Module 15: Core Operating EBITDA vs. "Other Income" Low-Quality Beat Detector
The Rule: In signals.py, computes Other Income as % of PBT and compares Core Operating EBITDA YoY/QoQ % against Headline PAT YoY/QoQ %. If PAT beat is driven by treasury mark-to-market gains, scrap/land sales, liability write-backs, or forex gains while Core EBITDA is flat or down, stamps ⚠️ LOW-QUALITY BEAT (Other Income Driven).

### Module 16: Gross Margin vs. Operating Leverage Decomposition
The Rule: Decomposes every quarterly EBITDA margin change (in bps) into two buckets:
Gross Margin Change (1 - COGS/Revenue): Measures raw-material spread, pricing power, or product-mix upgrade.
Fixed-Cost Absorption ((Employee + Other Expenses) / Revenue): Measures pure operating leverage from higher factory utilization.

### Module 17: The "Jaws Ratio" — Pre-Commissioning Employee Hiring Signal
The Rule: When Employee Benefit Expenses grow significantly faster than revenue (> +20% YoY) causing a temporary EBITDA dip, the engine checks capex_and_projects in the R2 dossier. If a major plant is scheduled for commissioning within 1–2 quarters (like Kanoria's Ankleshwar launch), it tags 🟢 PRE-LAUNCH OPEX INVESTMENT rather than treating it as structural margin decay.

### Module 18: Effective Tax Rate (ETR), Zero-Cash-Tax & Carryforward Loss Cliff
The Rule:
Splits total tax expense into Current Tax (cash tax) and Deferred Tax (accounting adjustment). Flags 🚩 LOW CASH TAX ANOMALY if a company reports strong Ind AS PBT over multiple quarters while paying < 10% Current Cash Tax without an active tax holiday or loss carryforward.
Tracks remaining unabsorbed depreciation / tax-loss carryforwards on turnaround stocks to warn 1 quarter before the company's tax rate steps up from 0% to 25.17%.

### Module 19: Ind AS 38 Capitalized R&D & "Intangibles Under Development" Inflation Trap
The Rule: On Q2 and Q4 filings, computes Δ Intangible Assets Under Development / Core EBITDA. If a company is capitalizing more than 15% of its EBITDA into balance-sheet intangibles (capitalizing routine engineer/chemist salaries instead of expensing them), flags 🚩 AGGRESSIVE COST CAPITALIZATION.

### Module 20: PLI, Export Scrips (RoDTEP) & State SGST Subsidy Dependency Ratio
The Rule: Isolates government incentives booked inside Other Operating Revenue or grants, computing Subsidy-Stripped Core EBITDA Margin % and logging the year the state subsidy or PLI scheme expires.

### Module 21: Q4 "Balancing Figure" Audit True-Up Detector
The Rule: Because Q1, Q2, and Q3 undergo only a "Limited Review" while Q4 undergoes a full statutory audit, signals.py compares Q4 Gross Margin, Other Expenses, and Bad-Debt Provisions against the Q1–Q3 average. A sudden > 400 bps margin drop or provision spike in Q4 triggers 🚩 Q4 AUDIT TRUE-UP ANOMALY (indicating Q1–Q3 profits were overstated).

### Module 22: Exceptional Items & "Recurring One-Offs" Detector
The Rule: Tracks how many quarters out of the last 8 a company has booked "Exceptional Items / Restructuring Charges". If a company reports "one-off exceptional losses" in 3 or more of the last 8 quarters, the engine reclassifies them into core operating costs.

### Domain 4: Balance Sheet, Cash Flow & Working Capital Forensics (Modules 23–29)

### Module 23: The Working-Capital "Bloat Ratio" (Δ Receivables + Δ Inventory vs. Δ Revenue)
The Rule: On every Q2 (September) and Q4 (March) balance sheet, computes (Δ Trade Receivables + Δ Inventory) / Δ Annualized Revenue. If receivables and inventory grew by more rupee crores than revenue itself (Ratio > 1.0), or if Receivable Days jumped by > 20%, fires 🚨 WORKING CAPITAL STRAIN / CHANNEL STUFFING.

### Module 24: Unbilled Revenue & "Contract Assets" Creep
The Rule: Tracks Contract Assets / Unbilled Revenue under Other Current Assets in EPC, IT, Railway, and Defence companies. Flags when unbilled revenue grows > 2× faster than billed revenue (a classic sign of booking revenue on uncertified milestones).

### Module 25: Cumulative OCF / EBITDA Cash-Conversion Ratio
The Rule: Computes Operating Cash Flow (after working capital changes and cash taxes) / Core EBITDA on half-yearly and annual filings. Healthy businesses convert > 65%–70% of EBITDA into OCF; conversion below 50% over two consecutive periods triggers ⚠️ POOR CASH CONVERSION (Paper Profits).

### Module 26: Supplier Credit Squeeze, MSME 45-Day Rule & LC Acceptances
The Rule:
Tracks Payable Days and specifically checks the Trade Payables due to MSME line item (governed by the strict 45-day payment rule under Section 43B(h) of the Income Tax Act). A spike in MSME payables alongside low cash signals acute liquidity distress.
Extracts interest-bearing Letter of Credit (LC) Acceptances / Supplier's Credit from footnotes and adds them to Total Debt.

### Module 27: The "High Gross Debt + High Cash" Paradox (Yield & Encumbrance Check)
The Rule: When a company carries significant debt (Debt/EBITDA > 2.5x) while simultaneously reporting large "Cash and Bank Balances", the engine computes Implied Yield on Cash = Interest Income / Average Cash vs. Implied Cost of Debt = Finance Cost / Average Debt. A wide spread (earning 2% on cash while paying 12% on debt) flags that the cash is restricted margin money pledged against Bank Guarantees or window-dressed at quarter-end.

### Module 28: Contingent Liabilities & Off-Balance-Sheet Corporate Guarantees vs. Net Worth
The Rule: Computes (Contingent Liabilities + Corporate Guarantees given to Subsidiaries/JVs) / Net Worth. Crosses 35% of Net Worth → ⚠️ OFF-BALANCE-SHEET LIABILITY OVERHANG.

### Module 29: Negative Net Worth & Interest-Coverage Distress Thermometer
The Rule: Automatically tracks Interest Coverage Ratio = Core EBIT / Finance Cost and Net Worth. When Interest Coverage < 1.5x or Net Worth <= 0 (as in Shivam Autotech's -₹61.67 Cr net worth and ₹20.48 Cr quarterly interest against ₹110 Cr revenue), suppresses standard P/E and ROE ratios and activates the Distressed Turnaround / Debt-Service Lens.

### Domain 5: Capital Structure, Fundraising, Warrants & M&A Forensics (Modules 30–36)

### Module 30: Post-Money Dilution, Terp Discount & Rights Issue Instrument Forensics
The Rule:
Computes Post-Money Dilution (New Shares / (Existing Shares + New Shares)) and Theoretical Ex-Rights Price (TERP).
Distinguishes 100% Upfront Payment on Application (immediate cash inflow, e.g., Shivam Autotech at ₹12/share) vs. Partly Paid-Up Shares (tranche inflows over 12–18 months, e.g., Evonile Pharma's ₹900 Cr raise) vs. Conversion of Promoter Unsecured Loans into Rights Shares (reduces debt on paper, brings ₹0 fresh cash into the bank account).

### Module 31: The 18-Month Preferential Warrant Clock & Forfeiture / Conviction Detector
The Indian Market Reality: Under SEBI ICDR regulations, Preferential Convertible Warrants require paying only 25% upfront, with the remaining 75% due within 18 months.
The Rule:
Logs the warrant_exercise_price, upfront_25pct_date, and 18_month_expiry_date on the Catalyst Calendar.
Bullish Signal: If the promoter or marquee investor pays the remaining 75% cash to convert warrants when the current market price is near or below the warrant exercise price, fires 🔥 HIGH-CONVICTION WARRANT CONVERSION.
Bearish Governance Red Flag: If promoters let warrants lapse/forfeit after 18 months (having enjoyed an 18-month free call option that pumped the stock on announcement day) and then issue new warrants at a lower price, flags 🚨 SERIAL WARRANT FORFEITURE!

### Module 32: SEBI Regulation 30 Annexure-A M&A Valuation & Related-Party Check
The Rule: On every Acquisition / Slump Sale / Share Purchase filing, extracts the mandatory SEBI Reg 30 Annexure A fields:
Target's Last 3 Years' Turnover (checking if the acquired business was growing or shrinking).
Computes Implied EV / Sales and EV / EBITDA paid.
Checks the mandatory RPT line ("Whether the acquisition falls within related party transactions / promoter interest"). If Yes, stamps 🚨 RELATED-PARTY ACQUISITION (Promoter Cash-Out Check).

### Module 33: Demerger Mirror-Shareholding vs. Holding-Company Discount Trap
The Rule: Distinguishes a 100% Mirror-Shareholding Demerger (every shareholder receives direct listed shares in the demerged entity—unlocking sum-of-the-parts value) from a Subsidiary Carve-Out / Slump Sale (where the listed parent becomes a holding company subject to a 30%–50% holding-company discount).

### Module 34: Subsidiary & Step-Down Ownership Leakage Check
The Rule: Whenever capex, order wins, or grants occur inside a subsidiary (like Jubilant Draximage Inc. or Hariom Power & Energy), verifies from the R2 entities_and_brands tree whether the unit is a 100% Wholly Owned Subsidiary (WOS) or a partially owned JV where 26%–49% of profits leak to minority/promoter partners.

### Module 35: 3-Year Rolling Return on Incremental Invested Capital (ROIIC) Loop
The Rule: Tracks cumulative capital raised + retained earnings vs. incremental annual EBITDA added since January 2025 to separate proven Capital Compounders from serial Capital Diluters.

### Module 36: Dividend & Buyback Cash-Reality & Promoter Participation Check
The Rule: Checks whether dividends or buybacks are funded by positive Free Cash Flow (OCF - Capex) or borrowed debt, and whether promoters are participating in tender-offer buybacks (cashing out) or abstaining (increasing skin in the game).

### Domain 6: Corporate Governance, Auditors, Credit Ratings & Legal Materiality (Modules 37–42)

### Module 37: Credit Rating "Bank-Facility Sanction Limit" Leading Indicator
The Rule: Parses the Annexure of Rated Bank Facilities at the bottom of every CRISIL, ICRA, CARE, India Ratings, and Acuité rating letter. Compares Total Sanctioned Bank Limits (₹ Cr) against the prior rating stored in R2 memory. An increase from ₹150 Cr to ₹260 Cr in sanctioned bank limits is flagged as a stealth leading indicator of upcoming order execution or capex before any press release is filed.

### Module 38: Short-Term Credit Rating (A1+ to A4) Liquidity Cliff & INC Detector
The Indian Market Reality: Long-term ratings (BBB+, A-) move slowly, but Short-Term Ratings (A1+, A1, A2, A3, A4, D) measure immediate 90-day working-capital liquidity.
The Rule:
Even a 1-notch downgrade in the Short-Term rating (e.g., A2+ → A3) or a revision of Outlook from Stable to Negative triggers an immediate liquidity warning.
Any rating carrying the tag ISSUER NOT COOPERATING (INC) triggers 🚨 SEVERE GOVERNANCE & CREDIT RED FLAG.

### Module 39: Auditor Opinion Ladder, Emphasis of Matter (EoM), CARO & Big-6 Upgrades
The Rule:
Classifies every results audit report into UNMODIFIED (Clean), EMPHASIS_OF_MATTER (extracting the exact Note number and disputed ₹ Cr figure), or QUALIFIED / ADVERSE / DISCLAIMER.
Checks Q4 CARO (Companies Auditor's Report Order) clauses for variances between Quarterly Stock/Book-Debt Statements submitted to Banks vs. Audited Books of Accounts.
Flags mid-term statutory auditor/CFO resignations as high-risk, while flagging upgrades from small local CA firms to Big-6 Auditors (Deloitte, EY/SR Batliboi, KPMG/BSR, PwC, Grant Thornton/Walker Chandiok, BDO) as 🟢 INSTITUTIONAL GOVERNANCE UPGRADE.

### Module 40: Postal Ballot & AGM "Institutional Dissent" Voting Forensics (Regulation 44)
The Indian Market Reality: Within 48 hours of every AGM, EGM, or Postal Ballot, companies must file Regulation 44 Scrutinizer's Voting Results, which break down % Votes in Favour vs. % Votes Against separately for:
Promoter & Promoter Group
Public — Institutional Holders (Mutual Funds / FIIs)
Public — Non-Institutional (Retail)
The Rule: Promoters always vote 100% in favour of their own resolutions, so a resolution can pass with 76% overall votes even when 85% of Institutional Mutual Funds voted AGAINST it! Whenever Public Institutional Votes Against > 25% on a related-party transaction, royalty, promoter remuneration, or M&A resolution, your engine fires 🚩 INSTITUTIONAL DISSENT ALERT: X% of Mutual Funds/FIIs voted AGAINST Resolution #Y.

### Module 41: SEBI Regulation 30 Penalty, Tax Demand & Show-Cause Materiality Ratio
The Rule: Computes Demand_or_Penalty_Cr / TTM_PAT_Cr. Routine monetary fines < 1% of TTM PAT with zero operational restriction are auto-downgraded to LOW IMPACT (kept out of the main feed), while demands > 10% of PAT or notices involving plant closure, license suspension, or USFDA/pollution board freezes are escalated to HIGH IMPACT.

### Module 42: Promoter Group Cross-Default & Sister-Company Contagion Tracker
The Rule: Uses promoter_group_id in the R2 dossier to check if another listed company run by the same promoter group recently suffered a credit rating downgrade, pledge invocation, or regulatory search.

### Domain 7: Concall Q&A Forensics, Trade Protection & Macro Seasonality (Modules 43–46)

### Module 43: Concall Q&A Evasion & "Goalpost Shifting" Detector
The Rule: Compares analyst questions in Pages 12–40 of concall transcripts against management's responses to flag numerical questions that were deflected (Q&A Evasion), and compares current guidance wording against prior quarter guidance_and_watchlist entries to catch stealth timeline slippages (e.g., shifting "FY27 full-year target" to "Q4 FY27 exit run-rate").

### Module 44: Proactive "Silent Deadline Slippage" Watchdog
The Rule: A daily SQL/dossier check scans all OPEN promises across all companies where due_date < TODAY and no delivery filing has arrived, surfacing ⚠️ OVERDUE MANAGEMENT PROMISE on the Catalyst Calendar even when management stays completely silent.

### Module 45: Full-Quarter Earnings Preview from Monthly Operational Filings
The Rule: When a company files its 3rd monthly operational update of a quarter (June, September, December, March), deterministic code sums all 3 monthly filings in monthly_operational_ledger (Jul + Aug + Sep for Q2) to compute Full-Quarter Physical Volume YoY % and QoQ % on the day the 3rd monthly filing drops—predicting quarterly revenue and operating leverage 30 days before formal financial results are released!

### Module 46: Indian Festive (Oct+Nov Diwali Shift) & Monsoon (Q2) Seasonality Normalizer
The Rule:
Because Navratri/Diwali shifts between October and November across calendar years, October and November monthly volume updates are evaluated alongside the combined Oct + Nov 2-Month Cumulative Festive YoY %.
For monsoon-sensitive sectors (Cement, Steel/Pipes, Infra/EPC, Agrochemicals, Paints), Q2 (Jul–Sep) cards prioritize YoY comparisons over QoQ comparisons so normal monsoon seasonality is never misclassified as a business breakdown.

### Domain 8: Ownership, Continuity & Micro-Cap Market Structure Guards (Modules 47–50)

### Module 47: Quarterly Shareholding "Smart-Money Accumulation vs. Retail Dumping" Matrix
The Rule: Parses quarterly Regulation 31 Shareholding Pattern filings deterministically (via XBRL/table) and compares against the prior quarter in R2 memory:
🟢 SMART-MONEY ACCUMULATION: (Promoter % + FII % + DII Mutual Fund %) increases by >= +1.0% while Small Retail Shareholder (<₹2L) Headcount decreases by >= 5%.
🚨 RETAIL DISTRIBUTION WARNING: Promoter / Institutional stake falls by >= 2.0% while Small Retail Shareholder Headcount surges by >= 25%.
Also logs every new marquee Mutual Fund, AIF, or FII crossing the 1.0% public disclosure threshold.

### Module 48: Insider Trading (SEBI PIT Reg 7) & SAST Reg 29 PR Cross-Check
The Rule: Tracks open-market share purchases or sales by Promoters, CEOs, and CFOs (excluding routine ESOP exercises or inter-se family transfers):
Open-market promoter buying within 30 days of a capex/order announcement triggers 🔥 INSIDER CONVICTION CONFIRMATION.
Open-market promoter/insider selling or pledge invocation within 15 days of a bullish press release triggers 🚨 INSIDER SELLING INTO PR NEWS.

### Module 49: Corporate Name-Change, Ticker-Change & Share-Split / Bonus Continuity Engine
The Rule:
Anchors all memory dossiers and D1 foreign keys to the immutable 6-digit BSE Scrip Code (500672, 505192), while indexing all historical names and tickers (Novartis India ↔ Evonile Pharma / NOVARTIND; SML Isuzu ↔ SML Mahindra / SMLMAH).
Adjusts historical per-share figures (EPS, Book Value/Share, Warrant/Rights Exercise Price) by split_bonus_multiplier whenever a Stock Split or Bonus Issue crosses its Record Date.

### Module 50: Micro-Cap Liquidity, BSE Trading Group (T/XT/Z) & ASM/GSM Circuit Guard
The Rule: Enriches every company with its 30-Day Median Daily Traded Value (₹ Cr/day), BSE Group (A, B, T, XT, Z), and ASM/GSM Stage. Stamps a prominent warning pill on any stock trading in Trade-to-Trade (T/XT with 5% circuit limits) or trading < ₹50 Lakhs/day so you never get trapped in an illiquid upper/lower circuit stock.

## 10. The Complete 22-Industry Sector Lens Dictionary (sectors.toml)
Every company in the companies table is mapped to one of the 22 official NSE/BSE Industry Lenses (sectors.toml). When Pass 2 runs—and when the UI renders the card footer and 360° Company Drawer—the engine automatically loads that industry's specific North-Star KPIs, Asset-Turn Norms, Seasonality Rules, and Forensic Red Flags:
| # | Official NSE/BSE Industry | Sector-Specific Footer & Dossier KPIs (fundamentals.kpis) | Normal Gross Block Asset Turns & Ramp Gestation | Primary Feedstock / Spread Driver & Seasonality Rule | Primary Sector Forensic Red Flag |
| 1 | Chemicals & Specialty Chemicals | EBITDA Margin %, Gross Margin %, Specialty Mix %, CWIP / Gross Block %, Export % | 1.4x – 2.2x (Specialty) · 0.8x – 1.3x (Bulk) · 2–3 qtr qualification ramp | Crude derivatives, Glycerin, Phenol, Caustic Soda, Bromine, Fluorine. Check DGTR Anti-Dumping duties & GPCB clearances. | Feedstock inflation inflating top-line sales while gross spread/kg shrinks; captive vs. merchant confusion. |
| 2 | Healthcare & Pharmaceuticals | US / Regulated Market %, R&D % of Sales, Gross Margin %, EBITDA Margin %, Active USFDA Status | 1.5x – 2.5x (Formulations) · 1.0x – 1.6x (APIs/CDMO) · 4–6 qtr regulatory ramp | KSM / API import dependency on China; US price erosion; Radiopharma isotope supply. Q2/Q3 acute season peak in India. | USFDA OAI / Import Alert; capitalized R&D (Ind AS 38) exceeding 15% of EBITDA; channel stuffing in domestic trade generics. |
| 3 | Automobile & Auto Components | Monthly Volume YoY %, EBITDA / Vehicle (or /kg), Export Share %, EV / Non-Auto Mix %, Capacity Util % | 2.0x – 3.5x (Ancillaries) · 3.0x – 4.5x (OEMs) · 2–4 qtr OEM PPAP approval | Steel, Aluminum, Copper, Natural Rubber, Precious Metals. Strong Oct–Nov Festive (Diwali) & Q4 CV fleet buying peak. | Single-OEM customer concentration > 50%; negative net worth / high interest burden on debt-funded tooling capex. |
| 4 | Financial Services (Banks, NBFCs, HFCs, MFI) | NII YoY %, NIM %, GNPA %, NNPA %, PCR %, Credit Cost (bps), AUM Growth %, CAR / CRAR % | N/A (Evaluated on ROA % [1.5%–3.5%] and ROE % [14%–20%] at 4x–7x leverage) | Repo rate transmission, CASA ratio, Wholesale borrowing cost, CD Ratio. Q4 recovery & disbursement peak; Q1/Q2 rural slippages. | NNPA appearing flat only because Provision Coverage Ratio (PCR) was cut or bad loans were written off / sold to ARCs. |
| 5 | Capital Goods, Engineering & Defence | Order Book (₹ Cr), Book-to-Bill (x), Core EBITDA Margin %, Working Capital Days, Export % | 2.5x – 4.5x (Asset-light assembly) · 12–36 month order execution cycle | Special alloys, Electronics/Semiconductors, Copper, Steel. Heavy Q4 (Jan–Mar) government & industrial billing peak (35%–45% of annual rev). | L1 double-counted as firm LoA; 15-year O&M lumped into EPC order book; Unbilled Revenue / Contract Assets surging. |
| 6 | Metals, Mining & Steel Products | Sales Volume (MT), EBITDA / Ton (₹/MT), Captive Power / Ore %, Net Debt / EBITDA (x) | 0.8x – 1.6x (Integrated) · 3.0x – 5.0x (Conversion pipes/tubes) · 1–2 qtr ramp | Iron ore, Coking coal, HR Coil, Scrap, Grid vs. Captive Solar Power (e.g., Hariom Pipe's 40/60 MW solar). Weak Q2 monsoon quarter. | Inventory valuation losses when steel/metal prices drop; structural vs. value-added tube/pipe margin confusion. |
| 7 | Information Technology (IT & SaaS) | USD / CC Rev YoY %, Deal TCV ($M), EBIT Margin %, Attrition %, DSO (Billed + Unbilled Days) | Asset-light (Evaluated on Revenue / Employee and OCF / EBITDA > 80%) | US/Europe BFSI & Retail tech budgets; INR/USD exchange rate. Q3 (Oct–Dec) furlough quarter weakness. | Capitalizing software development salaries (Intangibles under Development) or surging Unbilled Revenue to mask slow collections. |
| 8 | Construction, Infra & EPC | Order Book / TTM Rev (x), Core EBITDA Margin %, Receivable + Unbilled Days, Gross Debt / Equity | 3.0x – 6.0x (Equipment turns) · Working capital is the true constraint | Bitumen, Cement, Steel, Diesel; NHAI/State Govt budget payouts. Severe Q2 Monsoon dip; Q4 Execution peak. | (Δ Receivables + Δ Unbilled Contract Assets) > Δ Revenue; putting EPC profit into long-term HAM/BOT SPV equity locks. |
| 9 | Power, Renewables & Utilities | Operational Capacity (MW), Under-Construction (MW), PLF / CUF %, Tariff (₹/kWh), Net Debt / EBITDA | 0.20x – 0.30x (Solar/Wind IPP) · 2.5x – 4.0x (Solar EPC) · 75%–85% IPP EBITDA margin | Solar module/cell prices, Wind regime, State Discom PPA payment days (PRAAPTI). Q2 Wind peak; Q1/Q4 Solar peak. | Confusing one-time EPC revenue (12%–15% margin) with recurring 25-year IPP power sale revenue (80% margin). |
| 10 | Fast Moving Consumer Goods (FMCG & Agro-Processing) | Underlying Volume Growth (UVG %), Gross Margin %, A&P Spend % of Sales, Rural vs. Urban Mix | 2.5x – 5.0x (Own manufacturing) · 6.0x+ (Contract outsourced) | Agri-commodities (Palm oil, Wheat, Sugar, Milk, Coffee, Maize, Packaging crude). Festive Q3 & Summer Q1 peaks. | Price-led growth (+10% price, -3% volume) masking market share loss; cuts in Ad & Promotion (A&P) spend used to fake an EBITDA beat. |
| 11 | Consumer Durables, EMS & Electronics | Revenue YoY %, Core EBITDA Margin %, PLI Subsidy Cr, Working Capital Days, ODM vs. OEM % | 3.5x – 7.0x (High-velocity assembly) · Low gross margin (7%–14%), high asset turns | Imported compressors, PCBs, Copper, Aluminum, Plastic resins. Q1 Summer peak (ACs/Cooling); Q3 Festive peak (Appliances/Mobile). | Treating 5%–6% assembly EBITDA margin as high-tech margin when 40% of profit comes from temporary PLI incentives or high payable days. |
| 12 | Real Estate & Property Developers | Pre-Sales / Bookings (₹ Cr), Collections (₹ Cr), Collections / Pre-Sales %, Launch GDV (₹ Cr), Net Debt | N/A (Evaluated on Pre-Sales, Operating Cash Flow Surplus, and Launch Pipeline GDV) | Land/FSI approval timelines (RERA), Cement/Steel construction cost, Mortgage rates. Q3 Festive & Q4 year-end launch peaks. | Judging performance by Ind AS 115 P&L Revenue (which reflects flats sold 4 years ago reaching possession today) instead of current Pre-Sales & Collections. |
| 13 | Construction Materials (Cement, Ceramics, Pipes, Wood Panel) | Sales Volume (MT / MSM), EBITDA / Ton (₹/MT), Capacity Utilization %, Fuel & Power Cost / Ton | 0.7x – 1.1x (Cement) · 1.5x – 2.5x (Tiles/Pipes/MDF) | Petcoke, Imported Coal, Natural Gas, PVC Resin, Timber, Grid vs. WHRS/Solar power. Weak Q2 Monsoon; strong Q4 Construction peak. | Regional price wars eroding EBITDA/ton right as massive new capacity hits the market; channel inventory stuffing in March. |
| 14 | Textiles, Apparel & Footwear | Yarn-Cotton Spread, Garment / Technical Textile Mix %, EBITDA Margin %, US/EU Export Share % | 1.2x – 1.8x (Spinning) · 2.5x – 4.0x (Garments/Apparel) | Indian vs. International Cotton prices, Polyester/Viscose, RoSCTL/RoDTEP export rebates, UK/EU FTA tariffs. | Counting 5%–7% government export rebates (RoSCTL) and state TUF interest subsidies as core textile operating margin. |
| 15 | Consumer Services (Retail, QSR, Jewellery, E-Commerce) | SSSG % (Same-Store Sales Growth), Store Count & Additions, Revenue / Sq.Ft, Pre-Ind AS 116 EBITDA % | 2.5x – 4.5x (Store capex turns; evaluated on Store-Level Payback < 36 months) | Gold lease rates (Jewellery), Commercial retail rents, Food inflation (QSR). Massive Q3 (Dussehra/Diwali/Wedding) peak. | Ind AS 116 Lease Accounting Distortion: Rent is removed from EBITDA and moved to Depreciation + Finance Cost, inflating reported EBITDA margin by 600–900 bps! Always check Pre-Ind AS 116 EBITDA. |
| 16 | Healthcare Services (Hospitals & Diagnostics) | ARPOB (₹/Occupied Bed/Day), Occupancy %, Operational Beds, ALOS (Days), B2C Share % (Diagnostics) | 0.8x – 1.3x (Greenfield Hospital) · 1.8x – 2.5x (Brownfield bed addition) | Payor mix (Cash/Insurance vs. lower-margin CGHS/Scheme patients), Doctor retainer costs. Q2 (Monsoon fever/infections) peak. | New greenfield hospital drag (takes 18–24 months to break even on EBITDA) vs. high-ROCE brownfield bed additions at mature hospitals. |
| 17 | Hotels, Hospitality & Tourism | ARR (Average Room Rate ₹), Occupancy %, RevPAR (₹), Room Keys (Owned vs. Managed), EBITDA % | 0.4x – 0.7x (Owned luxury hotels) · Asset-Light (Managed/Franchise contracts) | Corporate MICE travel, Foreign tourist arrivals, Wedding dates, Airline capacity. Q3 & Q4 (Oct–Mar) generate 65%+ of annual profit; Q1/Q2 are lean. | High debt on owned greenfield hotel construction vs. high-ROCE management-contract room additions. |
| 18 | Oil, Gas & Consumable Fuels (Refining, CGD, Lubricants) | GRM ($/bbl) or EBITDA / SCM (₹/scm), CNG vs. PNG Volume Growth %, APM Gas Allocation % | 1.2x – 2.5x (CGD networks) · Regulated pipeline tariffs | Brent Crude, Henry Hub / Spot LNG prices, Government APM domestic gas allocation %. | Sudden cuts in cheap government APM gas allocation forcing City Gas Distributors (CGDs) to blend expensive imported Spot LNG. |
| 19 | Telecommunication & Digital Infrastructure | ARPU (₹), Subscriber / Tower Additions, Data Usage / Sub, EBITDA Margin %, Capex / Sales % | 0.5x – 0.9x (Spectrum + Network Infrastructure) | Tariff hikes, AGR/Spectrum dues, 5G/Fiber capex intensity, Indus/BSNL tower tenancy receivables. | Massive depreciation and spectrum interest eating up 80% of headline EBITDA; single-tenant receivable concentration. |
| 20 | Media, Entertainment & Printing | Ad Revenue YoY %, Subscription Revenue YoY %, Occupancy / Footfalls, Content Amortization | 1.5x – 3.0x (Multiplexes/Print) | Newsprint prices (Print), Box-office film pipeline (Multiplexes), FMCG ad budgets. Q3 Festive ad peak. | Capitalizing movie/OTT content production costs on the balance sheet instead of writing off flops immediately. |
| 21 | Services (Logistics, Shipping, Ports, Staffing, Aviation) | Cargo Volume (MMT / TEUs), EBITDA / Ton (or Yield), Fleet / Warehouse Utilization %, B2B Express Share | 0.6x – 1.0x (Ports/Shipping) · 3.0x – 5.0x (3PL/Surface Logistics) | Baltic Dry / Container Freight Indices, ATF/Diesel prices, Dedicated Freight Corridor (DFC) shift. | Ind AS 116 lease accounting on aircraft, ships, and warehouses masking true cash rental obligations. |
| 22 | Diversified & Conglomerates | Segment-by-Segment Revenue & EBIT Split, Capital Employed % per Segment, Holding-Company Debt | Evaluated via Sum-of-the-Parts (SOTP) across each segment's respective lens | Cross-subsidization of cash from a high-ROCE cash-cow division into a low-ROCE commodity/infra division. | Capital Misallocation: Taking 100% of the free cash flow from a 30% ROCE specialty division (like Radiopharma or Specialty Chem) and pouring it into a 6% ROCE division, until a demerger unlocks value. |

Ready for Part 3 of 3 (Final Part)?
Part 3 of 3 completes the Master Blueprint with:
Section 11: The 4-Gate Signal-Over-Noise Funnel, Price-Momentum Convergence (Minervini / Clenow / O'Neil Relative Strength integration with BSE Catalysts), and the Exact 0–100 Actionability Scoring Matrix.
Section 12: The 3 Self-Learning Loops (Market-Truth Price Post-Mortem, Forecast-vs-Reality Calibration, and 1-Click Human Golden-Set Learner).
Section 13: Complete Website UI/UX Specification (All 5 Views, the Slide-Over 360° Company Memory Drawer, Catalyst Calendar, Split-Screen PDF Verifier, and Database Dictionary).
Section 14: Complete 360° Audit Hardening & Verification Rules (All 6 Audit Areas).
Section 15: End-to-End Execution Playbook (5-Company Smoke Test → 2025 Objective Baseline → 2026 Live Layer → Cloud Sync) & The Daily 15-Minute Investor Ritual.

## 1. The 4-Gate Signal-Over-Noise Funnel, Techno-Funda Convergence & 0–100 Actionability Scoring Matrix

## 11.1 Separating "Informational Materiality" from "Actionable Alpha"
Out of roughly 1,500 daily BSE announcements:
~1,280 Filings (85%) are discarded at Stage 1 as procedural noise (duplicate share certificates, trading window closures, depository certificates, newspaper clippings).
~220 Filings (15%) pass into Stage 3 as Informationally Material. Every single one of these 220 filings updates the company's R2 Living Dossier (memory/{scrip_code}.json) and is searchable inside the Live Intelligence Feed and Company 360° Drawer.
Only 3 to 8 Filings per Day (~0.3% of total exchange volume) are promoted to the 🔥 Top Actionable Signals view.
To earn promotion into 🔥 Top Actionable Signals, a card must clear Gate 4 unconditionally (zero fatal forensic vetoes) plus at least two of Gates 1, 2, and 3, while scoring ≥70 points on the 0–100 Actionability Matrix.

## 11.2 Deep Architecture of the 4 Signal Promotion Gates
| Gate # | Gate Name | Exact Deterministic Threshold Enforced in signals.py | Why This Gate Exists |
| Gate 1 | Economic Magnitude Relative to Company Scale | • Order Win: Annualized Order Value / TTM Revenue >= 15% (or Total Firm LoA / TTM Revenue >= 25%) / • Capex / Plant Launch: Guided Peak Revenue Addition / TTM Revenue >= 15% OR Capex Outlay / Existing Gross Block >= 20% / • Backward Integration (Solar/Captive): Estimated Annual Cost Savings / TTM EBITDA >= 8% / • M&A / Demerger: Deal EV / Market Cap >= 10% or Target Revenue / TTM Revenue >= 15% / • De-leveraging / Fundraise: Debt Retired / Total Debt >= 25% | Prevents a ₹25 Cr order won by a ₹15,000 Cr mid-cap (0.16% of revenue) from cluttering your top signals, while highlighting a ₹25 Cr order won by a ₹120 Cr micro-cap (20.8% of revenue). |
| Gate 2 | Fundamental Trend Inflection & Execution Delivery | • Earnings Inflection: Quarterly Revenue YoY % >= +20% AND Core EBITDA Margin expansion >= +150 bps YoY (or turnaround from net loss to net profit) / • Volume Streak: ≥2 consecutive months of > 25% YoY physical volume growth in the Monthly Operational Ledger (e.g., SML Mahindra's +34.4% in Aug followed by +31.9% in Sep) / • Promise Verified: Filing resolves an OPEN guidance commitment in R2 memory as ✅ PROMISE DELIVERED on or ahead of schedule (e.g., Kanoria Chemicals' Ankleshwar Triacetin launch or Hariom Pipe's 40 MW / 60 MW solar rollout). | Isolates businesses undergoing a structural step-change in capacity, product mix, or utilization rather than coasting on baseline run-rates. |
| Gate 3 | Price-Structure & Momentum Convergence ("Coiled Spring" Check) | • Not Over-Extended: 1-Month Stock Return <= +15% AND 1-Week Return <= +10% (preventing you from chasing news that was already front-run by +40% in the prior two weeks) / • Tradability Floor: 30-Day Median Daily Traded Turnover >= ₹50 Lakhs/day AND stock is not locked in ASM Stage 4 or GSM. | Ensures the catalyst arrives while the stock is still in a buyable consolidation base (such as Kanoria at 1W -8.9% or Jubilant Pharmova at 1M -6.6%) with sufficient liquidity to enter and exit cleanly. |
| Gate 4 | Forensic & Grounding Cleanliness Veto (Mandatory Pass) | Automatic Veto (is_actionable_signal = 0) if ANY of the following are true: / 1. needs_review == 1 (ungrounded headline rupee figure or AST math mismatch) / 2. Auditor Opinion is QUALIFIED, ADVERSE, or DISCLAIMER, or mid-term Auditor/CFO resignation in trailing 90 days / 3. Credit Rating contains ISSUER NOT COOPERATING (INC) or Short-Term downgrade below A3 / 4. Working Capital Bloat Ratio > 1.0 (Δ Receivables + Δ Inventory > Δ Revenue) / 5. Insider Selling into PR (Promoter open-market disposal or pledge invocation within 15 days) / 6. L1-to-LoA Double Count or routine Monetary Penalty < 1% of TTM PAT. | Acts as your permanent capital-preservation shield—ensuring a flashy headline never tricks you into buying an accounting trap or promoter dump. |


## 11.3 Optional "Techno-Funda Inflection" Layer (Bridging Corporate Catalysts with Quantitative Price Structure)
Because fundamental catalysts produce the fastest compounding when they collide with institutional price accumulation, the company's market-data enrichment job (market_data.py) can compute four lightweight quantitative price-structure tags alongside 1W / 1M / 1Y returns:
Stage-2 Trend Alignment (Minervini Trend Template Filter):
Checks whether Close > 50-DMA > 150-DMA > 200-DMA, 200-DMA slope is positive over 20 trading days, and Close is within 25% of its 52-Week High.
Volatility Contraction Pattern (VCP / Tight Base Detection):
Measures the ratio of the 10-Day Average True Range (ATR%) to the 50-Day ATR% and checks if the 20-day high-low price range has contracted below 12%.
When a 🟢 HIGH IMPACT fundamental catalyst (like a plant commissioning or major order win) drops on a stock that is simultaneously sitting inside a tight Volatility Contraction Base (10D ATR < 0.7 × 50D ATR), the card displays a special badge: ⚡ COILED SPRING: High-Impact Catalyst + Tight Volatility Contraction.
Relative Strength (RS) Percentile vs. Nifty 500 & Volatility-Adjusted Slope:
Computes the stock's 6-month and 12-month O'Neil-style Relative Strength Percentile (0–99) against the Nifty 500 universe, plus the Clenow Volatility-Adjusted Exponential Regression Slope (Annualized Slope × R²).
Volume Breakout Confirmation (RVOL):
During market hours (or on the day after an after-market filing), compares current day volume against the 50-day median volume (Relative Volume = Today_Vol / Median_50D_Vol). A fundamental catalyst accompanied by RVOL >= 2.5x confirms institutional participation.

## 11.4 The Deterministic 0–100 Actionability & Conviction Scoring Matrix
Every card is scored from 0 to 100 by deterministic Python code in signals.py (never guessed by the LLM):
| Scoring Pillar | Max Points | Exact Sub-Component Allocation Rules |
| 1. Economic Magnitude vs. Scale | 30 pts | • 25–30 pts: Catalyst size ≥25% of TTM Revenue, Gross Block, or Market Cap (or ≥15% EBITDA accretion from captive cost savings) / • 15–24 pts: Catalyst size between 15% and 24.9% of baseline scale / • 5–14 pts: Catalyst size between 5% and 14.9% of baseline scale / • 0–4 pts: Routine or sub-5% incremental update |
| 2. Margin, Operating Leverage & ROCE Shift | 25 pts | • 20–25 pts: Structural product-mix upgrade (e.g., bulk commodity to specialty ester/radiopharma with peer margin gap ≥+500 bps), Brownfield expansion at existing site, or operating leverage inflection crossing >50%-65% utilization / • 10–19 pts: Moderate margin expansion (+100 to +300 bps) or multi-month volume acceleration >25% YoY / • 0–9 pts: Margin-neutral capacity replacement or commodity pass-through |
| 3. Balance Sheet, Cash Flow & Funding Quality | 20 pts | • 16–20 pts: Funded via internal accruals, non-dilutive government grants (e.g., Jubilant's 25.2% Canadian grant), or retiring high-cost debt with OCF/EBITDA >= 70% and 100% WOS ownership / • 8–15 pts: Moderate debt/equity funding with comfortable Interest Coverage >= 3.0x and stable working capital days / • 0–7 pts: Heavy equity dilution (>30% post-money dilution), negative net worth rescue (e.g., Shivam Autotech), or elevated receivable days |
| 4. Management Execution Credibility Score | 15 pts | • 12–15 pts: Company's R2 Dossier shows Credibility Score >= 80% (or today's filing directly fulfills a prior dated AGM/concall promise on time) / • 6–11 pts: Credibility Score between 50% and 79%, or neutral baseline history / • 0–5 pts: History of missed/revised timelines (Credibility Score < 50%) or concall Q&A evasion flags |
| 5. Disclosure Completeness & Price Timing | 10 pts | • +5 pts: 100% Grounded numbers (ungrounded == 0) AND zero critical Missing Disclosures (capex outlay, timeline, and utilization all known via filing or memory) / • +5 pts: Unextended price entry (1M return between -10% and +12%, not chasing a vertical spike) |
| Forensic Penalty Deductions | Up to -50 pts | • -20 pts: Working Capital Bloat or Other Income > 25% of PBT / • -25 pts: Related-Party M&A without independent valuation or Public Institutional Dissent > 25% / • -50 pts (Hard Cap at Score 35): Any Gate 4 Veto trigger |

Impact Badge Mapping from Final Score:
Score 70 to 100: 🟢 HIGH IMPACT (Promoted to 🔥 Top Actionable Signals if Gate 4 is clean)
Score 40 to 69: 🟠 MODERATE IMPACT (Displayed in main ⚡ Live Intelligence Feed and updates Company Memory)
Score 0 to 39: ⚪ LOW IMPACT (Silently updates Company Memory Dossier; hidden from default feed unless toggled)

## 12. The 3 Self-Learning & Calibration Loops (learning.py)
To ensure the platform becomes smarter every single week based on real Indian market outcomes, three automated feedback loops run continuously:

## 12.1 Loop 1: Market-Truth Price-Action Post-Mortem (T+1, T+3, T+5 Excess Return Tracker)
Market-Session Timestamp Alignment (15:30 IST Rule):
If a filing is disseminated on BSE between 09:15 IST and 15:30 IST on a trading day ([Live Market]), Day 0 is today's trading session.
If a filing is disseminated after 15:30 IST or on a weekend/holiday ([After-Market], like Kanoria Chemicals at 17:50 IST or SML Mahindra at 15:41 IST), Day 0 is the next trading day's opening/closing session.

### Benchmark-Adjusted Excess Return Calculation:
A nightly job fetches the closing price and volume of every stock that had a filing 1, 3, and 5 trading days ago, and computes Excess Return (Alpha) over the broader market:
Excess ReturnT+3=Stock ReturnT+3-Nifty Smallcap 250 ReturnT+3
Stores the outcome in dossier.historical_event_reactions and cards.post_event_return_json.
Automated Weight Calibration & "Missed Alpha" Re-Analysis:
False-Positive Dampener: If a specific (sector, event_category) pair is marked HIGH IMPACT 10+ times but produces an average T+3 Excess Return between -1% and +1% with RVOL < 1.2x, learning.py flags the category for threshold tightening.
Missed-Alpha Detector: If a filing classified as LOW IMPACT or MODERATE IMPACT is followed by a T+1 or T+2 Excess Return ≥+8% on Volume ≥3.0× the 50-day median, the engine automatically triggers a Missed-Alpha Post-Mortem: it re-runs Pass 2 with the price/volume reaction attached to identify the specific footnote or catalyst that moved the stock and appends that pattern to sector_learned_rules.json.

## 12.2 Loop 2: Forecast-vs-Reality Self-Calibration (Management Conservatism vs. Over-Promise Multiplier)
Logging Testable Predictions:
Whenever a card or concall logs a forward-looking number in What to Track Next (e.g., "Kanoria guided for 40% utilization in FY27 (~₹100 Cr revenue)" or "Shivam Autotech quarterly interest cost expected to drop below ₹16 Cr post rights issue"), dossier.py creates a structured entry in dossier.pending_predictions:
prediction_id, source_news_id, target_period ("FY27" or "Q3FY27"), metric_name ("finance_cost_cr"), predicted_value (16.0), comparison_operator ("<=").
Automatic Verification When Results Arrive:
When the XBRL or PDF financial result for target_period is ingested months later, deterministic code compares actual_reported_value against predicted_value:
Delivery Ratio=Actual Reported ImprovementGuided Target Improvement
Writing the Permanent Calibration Rule into the R2 Dossier:
Updates the company's Management Credibility Score (0–100%) and writes a permanent empirical rule into dossier.calibration_and_peer_context:
Example (Under-Promiser / Out-Performer): "Management historically delivers 1.15x of initial revenue guidance and commissions brownfield plants 1 month ahead of schedule."
Example (Chronic Over-Promiser): "Management ramp-up timelines historically slip by 2–3 quarters (0.60x delivery ratio); apply a 2-quarter conservatism buffer to all new capex guidance."

## 12.3 Loop 3: 1-Click Human-in-the-Loop "Golden-Set" Prompt Learner
Every card in the UI has two instant feedback buttons in the bottom-right corner: [🔥 Star Signal] and [🗑️ Mark Noise].
Clicking either button writes a row to the card_feedback table (news_id, scrip_code, sector, event_category, rating: STARRED | NOISE, user_note, created_at).
Whenever Pass 2 builds a prompt for (sector, event_category), prompts.py automatically injects your top 2 STARRED cards as few-shot positive examples and your most recent NOISE card as a negative guardrail—training the system to match your exact analytical taste without ever editing code.

## 13. Complete Website UI/UX Specification & Database Dictionary

## 13.1 Aesthetic Direction & Typography System
Dual Institutional Palette:
Default Warm Institutional Light Mode: Canvas background #F8F7F4 (Warm Alabaster), Card surface #FFFFFF with 1px solid #E6E4DD, Why-It-Matters intelligence box #EAF2EE (Soft Sage) with #1B4D3E (Deep Forest Green) header text, High-Impact badge #0F766E, Moderate-Impact badge #B45309, Risk/Veto badge #BE123C.
1-Click OLED Midnight Dark Mode: Canvas #0B0F17, Card surface #111827 with #1F2937 border, Intelligence box #06281E with #34D399 emerald accents.
Typography Rules:
Headlines: Plus Jakarta Sans (600/700 weight, tight tracking).
Analytical Body: Inter (400/500 weight, 1.55 line height for effortless reading).
All Financial Figures, Ratios, Dates & Scrip Codes: JetBrains Mono with font-variant-numeric: tabular-nums enforced globally so decimals and columns align vertically down to the pixel.

## 13.2 Functional Specification of All 5 Primary Navigation Views

### View 1: 🔥 Top Signals & Pre-Market Brief (Default Morning Cockpit)
Purpose: Your 5-minute 8:45 AM IST ritual view.
Key Controls:
🌅 SinceYesterday 3:30 PM Close Quick-Toggle: Filters strictly for announcements filed between yesterday's 15:30 IST market close and today's 09:15 IST opening bell.
Top Summary Ribbon: Shows 4 metric tiles: Overnight Filings Scanned, Noise Filtered Out (%), Memory Dossiers Updated, and 🔥 High-Conviction Signals Passing All 4 Gates.
Card Stream: Displays the 3 to 8 daily cards that cleared the 4-Gate Signal Filter, sorted by Actionability Score (100 down to 70).

### View 2: ⚡ Live Intelligence Feed (Full Searchable Material Stream)
Sticky Multi-Filter Ribbon (Responsive & Non-Overlapping on Mobile Viewports):
Global Instant Search (Ctrl+K / /): Searches across company_name, former_names (so typing Novartis finds Evonile Pharma and typing SML Isuzu finds SML Mahindra), symbol, 6-digit scrip_code, and headline keywords.
Date Range Picker: Quick presets (Today, Since 3:30 PM Close, Last 7 Days, Last 30 Days, Q2 FY27, Full 2025–2026 History) + custom calendar range (from / to).
Market Session Filter: All · Live Market (09:15–15:30) · After-Hours & Weekend.
Impact & Verification Filter: All Material · 🟢 High Impact · 🟠 Moderate Impact · ✓ 100% Verified Only · ★ My Watchlist Only.
Event Category & 22-Sector Dropdowns: Multi-select pills for all event types and all 22 NSE/BSE industries.
Market-Cap Tier Pills: All Sizes · Microcap (<₹500 Cr) · Smallcap (₹500–₹5,000 Cr) · Midcap (₹5,000–₹20,000 Cr) · Largecap (>₹20,000 Cr).

### View 3: 🏢 Company Memory Directory & 🚀 Inflection Radar
All-Company Searchable Grid: Lists every tracked BSE company with its Market Cap, Sector Lens, Management Credibility Score (0–100%), Active Capex count, Open Promises count, and Latest Revenue/EBITDA/Debt snapshot.
The 🚀 Inflection Radar Tab: Automatically filters for companies where 3 or more independent positive inflection triggers have occurred within the trailing 90 days inside their R2 Living Dossier:
PLANT_COMMISSIONING or BROWNFIELD_CAPEX completed.
≥2 consecutive months of > 20% YoY monthly volume growth OR Core EBITDA Margin expansion >= +150 bps.
Debt Reduction >= 15%, Credit Rating / Bank Limit Upgrade, OR Smart-Money Institutional Accumulation / Promoter Open-Market Buying.

### View 4: 📅 Corporate Action & Catalyst Calendar
Forward-Looking Timeline View: Plots every upcoming dated event extracted from What to Track Next and corporate_actions_and_orders:
Record Dates & Ex-Dates: Rights Issues (e.g., Shivam Autotech Oct 15 Record Date, Oct 22 Opening, Nov 13 RE Renunciation Close, Nov 19 Issue Close), Stock Splits, Bonus Issues, Demergers, Dividends.
18-Month Warrant Expiry Deadlines: Upcoming dates where promoters must pay the remaining 75% cash to convert preferential warrants.
Guided Plant Commissioning Windows: Upcoming quarters where CWIP projects are scheduled to go live.
⚠️ Overdue Management Promises Panel: Highlights any OPEN promise in any company's R2 dossier whose due_date has passed without a completion filing.

### View 5: ⚙️ System, Backfill & AI Pipeline Monitor
Pipeline Health & Two-Stage Progress Bars:
Bar 1 — Filing Discovery & Noise Triage: Shows total BSE notices fetched, rule-filtered noise count, and Pass 1 queue status.
Bar 2 — Company-by-Company Deep Analysis: Shows Pass 2 completion (Processed Filings / Total Material Filings) and distinct companies updated.
Per-Key 95% AI Quota Telemetry: Live progress gauges for all 9 provider key buckets (Groq Key 1 & 2, NVIDIA Key 1 & 2, Mistral Key 1 & 2, Z.AI Key 1 & 2, Workers AI) showing RPM, RPD, and active cooldown timers.
Needs Review Verification Queue: Displays any card held back with needs_review = 1 (showing the exact ungrounded number or AST formula mismatch alongside a 1-click re-run button).

## 13.3 The Slide-Over "Company 360° Memory Drawer" & Split-Screen PDF Verifier
Clicking any company name or [🗂️ 360° Memory] button on any card slides open a 720px right-hand drawer without losing your scroll position in the main feed:
Tab 1 — Living Dossier & Execution Scorecard:
Identity Header: Current & former names, 6-digit BSE Scrip Code, NSE Symbol, Sector Lens, BSE Trading Group, 30-day liquidity, and Subsidiary/Brand tree (Jubilant Draximage Inc. → RUBY-FILL®).
Management Execution Scorecard: Progress bar showing Delivered vs. Open vs. Breached / Revised promises from AGMs and concalls.
Sector-Aware Financial Table: Displays the last 8 quarters and 4 annuals of normalized ₹ Cr financials plus the company's sector-specific KPIs from sectors.toml (NII, NIM, GNPA, PCR for banks; Pre-Sales, Collections for real estate; ARPOB, Occupancy for hospitals).
Active Capex & Order Book Ledger: Shows every ongoing project (40 MW active of 60 MW planned), Brownfield/Greenfield tag, and active order book (L1 vs. Firm LoA).
Tab 2 — Chronological 2025–2026 Event Timeline:
Vertical timeline of every material filing for that company since January 1, 2025, showing the 1-line summary, impact badge, and the actual post-filing stock reaction (T+1 and T+3 %).
Tab 3 — Split-Screen Official PDF & Grounding Verifier:
Renders the official BSE PDF (AttachLive / AttachHis) on the left and the generated Alpha-Matrix card on the right, highlighting every verified number and displaying the AST math working table.

## 13.4 Complete Cloudflare D1 & Local SQLite Database Dictionary
The relational index (db/schema.sql) uses five normalized, strictly indexed tables:

### Table 1: companies (Master Stock Universe & Alias Registry)
| Column Name | Data Type | Constraints | Description & Invariant |
| scrip_code | TEXT | PRIMARY KEY | Immutable 6-digit BSE Scrip Code ("506525", "500672"). Primary foreign-key anchor across all tables and R2 files. |
| symbol | TEXT | Indexed | Current NSE/BSE ticker symbol ("KANORICHEM", "SMLMAH", "NOVARTIND"). |
| company_name | TEXT | NOT NULL | Current official legal name ("Evonile Pharma Limited"). |
| former_names_json | TEXT | Default '[]' | JSON array of historical names and old symbols (["Novartis India Limited"], ["SML Isuzu Limited"]). |
| industry | TEXT | Indexed | Official BSE/NSE industry classification populated by sync-companies. |
| sector_lens | TEXT | Indexed | Mapped key from sectors.toml (1 of the 22 Sector Lenses). |
| market_cap_cr | REAL | Indexed | Latest market capitalization in ₹ Crores (populated before backfill so size filters and sorting work on every card). |
| size_category | TEXT | Indexed | Microcap, Smallcap, Midcap, or Largecap. |
| bse_group | TEXT | Nullable | BSE trading group (A, B, T, XT, Z) and ASM/GSM stage tag. |
| median_turnover_cr | REAL | Nullable | 30-day median daily traded turnover in ₹ Crores. |
| credibility_score | REAL | Default null | Delivered / (Delivered + Breached) management execution score (0–100). |
| updated_at | TEXT | ISO-8601 | Timestamp of last metadata/market-cap sync. |


### Table 2: filings (Ingestion Queue & Processing Ledger)
| Column Name | Data Type | Constraints | Description & Invariant |
| news_id | TEXT | PRIMARY KEY | Unique BSE announcement UUID / NewsID. |
| scrip_code | TEXT | NOT NULL, Indexed | 6-digit BSE Scrip Code (idx_filings_scrip_date on (scrip_code, filed_at DESC)). |
| symbol | TEXT | Nullable | Stored directly on the ledger row at discovery time so queued items never lose their ticker. |
| company_name | TEXT | Nullable | Stored at discovery time. |
| subject | TEXT | Nullable | Mandatory BSE Headline / Subject Line saved during discover() so Pass 1 and Pass 2 always see the announcement title. |
| category | TEXT | Nullable | Raw BSE category (Company Update, Board Meeting, Result). |
| subcategory | TEXT | Nullable | Raw BSE subcategory (Award of Order, Raising of Funds). |
| filed_at | TEXT | NOT NULL, Indexed | Full ISO-8601 IST dissemination timestamp (2026-10-07T17:50:47+05:30). |
| filing_date | TEXT | NOT NULL, Indexed | YYYY-MM-DD date string. |
| pdf_url | TEXT | Nullable | Permanent BSE AttachLive / AttachHis PDF URL. |
| xbrl_url | TEXT | Nullable | BSE XBRL XML attachment link (when available for Stage 0 Fast-Path). |
| status | TEXT | NOT NULL, Indexed | QUEUED, PASS1_SKIPPED, PASS2_DONE, NEEDS_REVIEW, or FAILED (idx_filings_queue on (status, filed_at)). |
| status_detail | TEXT | Nullable | Diagnostic reason or error message if FAILED or NEEDS_REVIEW. |
| processed_at | TEXT | Nullable | Timestamp when processing finished. |


### Table 3: cards (Published Intelligence Cards & Signal Index)
| Column Name | Data Type | Constraints | Description & Invariant |
| news_id | TEXT | PRIMARY KEY | Matches filings.news_id. |
| scrip_code | TEXT | NOT NULL, Indexed | 6-digit BSE Scrip Code (idx_cards_scrip on (scrip_code, filed_at DESC)). |
| symbol | TEXT | Nullable | Ticker symbol. |
| company_name | TEXT | NOT NULL | Company display name. |
| filing_date | TEXT | NOT NULL | YYYY-MM-DD date string. |
| filed_at | TEXT | NOT NULL, Indexed | Full ISO-8601 timestamp (idx_cards_feed on (filed_at DESC, impact_level, event_category, size_category)). |
| market_session | TEXT | Nullable | LIVE_MARKET, AFTER_MARKET, or PRE_MARKET. |
| market_cap_cr | REAL | Indexed | Market cap in ₹ Cr for sorting (market_cap_desc) and size filtering. |
| size_category | TEXT | Indexed | Microcap, Smallcap, Midcap, Largecap. |
| sector | TEXT | Indexed | Canonical 22-industry sector name. |
| event_category | TEXT | NOT NULL, Indexed | Canonical event category (PRODUCT_LAUNCH, RIGHTS_ISSUE, CAPEX, etc.). |
| impact_level | TEXT | NOT NULL, Indexed | HIGH IMPACT, MODERATE IMPACT, or LOW IMPACT. |
| actionability_score | INTEGER | Default 0, Indexed | Deterministic 0–100 score from signals.py. |
| is_actionable_signal | INTEGER | Default 0, Indexed | 1 if card clears the 4-Gate Signal Filter (idx_cards_signals on (is_actionable_signal, actionability_score DESC, filed_at DESC)). |
| needs_review | INTEGER | Default 0, Indexed | 1 if any headline ₹ Cr is ungrounded or any AST math check failed. |
| headline | TEXT | NOT NULL | 1-line active-voice headline. |
| card_json | TEXT | NOT NULL | Complete serialized JSON payload of the Alpha-Matrix card, grounding stats, and math working. |
| post_event_return_json | TEXT | Nullable | Populated by Loop 1 (T+1, T+3, T+5 excess returns and volume multiples). |
| pdf_url | TEXT | Nullable | Direct link to official BSE PDF. |
| created_at | TEXT | NOT NULL | Creation timestamp. |


### Table 4: catalysts (Forward-Looking Calendar Index)
Columns: catalyst_id (PRIMARY KEY), scrip_code, company_name, event_date (Indexed YYYY-MM-DD), catalyst_type (RECORD_DATE, ISSUE_OPEN, ISSUE_CLOSE, WARRANT_EXPIRY, PROMISE_DUE, COMMISSIONING_TARGET), title, source_news_id, status (UPCOMING, COMPLETED, OVERDUE).

### Table 5: card_feedback (Loop 3 Human Golden-Set Store)
Columns: news_id (PRIMARY KEY), scrip_code, sector, event_category, rating (STARRED | NOISE), user_note, card_json_snapshot, created_at (Indexed on (sector, event_category, rating)).

## 14. Complete 360° Audit Hardening & Verification Rules
Before running any large-scale backfill or deploying to production, these 24 engineering invariants across all 6 audit domains must remain 100% enforced:

### Audit Area 1: Frontend & Browser Compatibility (web/src/)
iOS 16 / Safari URLSearchParams Safety: Never read qs.size (unsupported on Safari < 16.4); always check const qsStr = qs.toString() and append ?${qsStr} only when non-empty.
Safari Clipboard PNG Promise Pattern: Pass a synchronous Promise<Blob> directly into new ClipboardItem({ 'image/png': blobPromise }) inside the click handler before any await, with an automatic fallback to native file download / navigator.share on mobile browsers.
Strict Verification Badge Honesty: Display "Numbers verified" only when ungrounded.length === 0 && !math_mismatch. Whenever ungrounded.length > 0, display "N of M numbers verified" in amber and render a 1-line warning banner inside both the web card and the exported PNG image.
Top-Level React Error Boundary & Non-Destructive Pagination: Wrap all routes in an Error Boundary with a "Try Again" reset button, and ensure transient errors on page N>1 of infinite scroll display an inline retry button without wiping out pages 1…N-1.
Responsive Sticky Filter Bar: Only the top bar sticks on mobile viewports (md:sticky on the filter ribbon) so cards are never covered on phone screens.

### Audit Area 2: Cross-Layer Contracts & Naming (events.toml, sectors.toml, api/index.ts)
Single Source of Truth for Categories & Verdicts: Frontend filter pills, backend SQL queries, and prompt enums must read from the exact same canonical event categories and verdict tokens (PASS, REFINED, SECOND_OPINION, NEEDS_REVIEW).
Complete Card Serialization: engine._build_card() must serialize filing_date, filed_at, market_session, sector, size_category, market_cap_cr, pdf_url, quantified_math_checks, and what_to_track_next into both the D1 row and the R2 daily_feed JSON so R2 snapshot loads and D1 queries return identical card structures.

### Audit Area 3: Persistent Memory, Grounding & Signals (dossier.py, grounding.py, signals.py)
Bi-Temporal known_since Enforcement: Every fact in dossier.py preserves known_since = min(existing.known_since, filing.filed_at). During backfills, compute_signals(), latest_fundamentals(), dilution math, and guidance checks filter strictly by known_since <= filing.filed_at (zero look-ahead bias).
Bucketed Period Slicing (QUARTERLY / ANNUAL / MONTHLY): Partition financial_history by period_kind and sort by canonical period_end DESC so multi-year annual tables in an investor presentation never push recent quarterly results out of the dossier slice. Never evict OPEN watchlist items during compaction.
Unit Scaling Before Stripping (_to_float): Scale Crores (×1), Lakhs (÷100), Millions (÷10), and Thousands (÷10,000) before stripping unit words from strings ("₹12,000 Lakhs" → 120.0 Cr; "₹85.50 Lakh" → 0.855 Cr).
Tight Number Grounding: Scan all card text fields (headline, core_catalyst, what_happened_bullets, why_it_matters, what_to_track_next). Check %, bps, pp, and x only at scale 1 or 0.01; require bps/pp to match direct subtraction (a - b); never exempt small integers (<= 31) when attached to a unit (Cr, lakh, %, MW, TPD, bps, x); and force needs_review = 1 if any headline ₹ Cr figure is ungrounded.
Hardened AST Math Evaluator: Restrict eval_formula() to a 50-node AST whitelist, cap exponents at abs(exp) <= 12, cast the second argument of round(val, ndigits) to int, and wrap evaluation in try/except (ArithmeticError, ValueError, TypeError, OverflowError) raising FormulaError.
Post-Money Dilution & Negative Net Worth Guards: Compute dilution as new_shares / (existing + new_shares), label share reductions as "Buyback / Equity Reduction", and output "N/A (Negative Net Worth)" when Net Worth <= 0.

### Audit Area 4: Ingestion, Orchestration & Concurrency (bse.py, extract.py, engine.py, cli.py)
Persist subject & symbol on Discovery: Save the BSE announcement headline (subject) and symbol directly in the filings table during discover() so queued items processed in later runs always retain their subject line.
Per-Scrip Asynchronous Lock During Concurrent Backfill: When running 5 to 10 async workers in parallel during a local backfill, acquire a per-company lock (asyncio.Lock() keyed by scrip_code) and process each company's filings in strict chronological order (filed_at ASC) so two filings from the same company never overwrite each other's R2 dossier concurrently.
Atomic Local File Writes: Write local JSON dossiers and checkpoints to {filename}.tmp and execute os.replace() so an interrupted run or laptop shutdown can never leave a half-written JSON file.
Explicit BSE 403 Detection: Detect HTTP 403 or Akamai HTML blocks in bse.py and surface a clear "BSE_IP_BLOCKED (Run on Indian residential IP)" status rather than silently returning an empty list.

### Audit Area 5: AI Gateway, Quota Guard & Prompts (gateway.py, limits.py, pass1.md, pass2.md)
Independent Per-Key 95% Quota Buckets: Track RPM, TPM, and RPD per (provider_id, key_index) and ping-pong between Key 1 and Key 2 on consecutive calls. Rotate a key out at 95% usage or on HTTP 429/404.
Cross-Provider Second Opinion: When SECOND_OPINION triggers on a grounding or math failure, route the retry to a different provider family with the exact ungrounded numbers / formula error injected into the prompt.
Prompt Memory-First Omission Check: Instruct Pass 2 to check the injected R2 Living Dossier before populating missing_disclosure so facts already known from prior AGMs or concalls are used rather than flagged as missing.

### Audit Area 6: Cloudflare D1, R2 & Worker API (api/index.ts, storage.py)
Zero Unindexed Full-Table Scans: Cap queue status queries at LIMIT 1001, filter 7-day counts using the indexed filed_at column (filed_at >= datetime('now', '-7 days')), and cache /api/system for 60 seconds via caches.default.
R2 Static Snapshot for Zero-Read Homepage Loads: Serve default unfiltered homepage requests from daily_feed/latest_snapshot.json in R2 so routine visitor traffic consumes 0 D1 row reads.
Pre-Backfill Company Sync: Run sync-companies automatically before backfill so companies.industry, sector_lens, and market_cap_cr are populated before cards are generated.
Strict .gitignore Isolation for Local Data: Keep ./data/ (local_d1.sqlite, local_r2/, text_cache/, backfill_progress.json) in .gitignore so transient local database and cache files are never committed to GitHub.

## 15. End-to-End Execution Playbook & The Daily 15-Minute Investor Ritual
Follow this exact six-phase sequence to take the platform from code completion to daily live operation without wasting time or API quota.

> **Owner addendum (2026-10-15): data dependency order.** Build data in this order so nothing has to
> be re-run: (0) company master by scrip code (`sync-companies`) → (1) market caps and daily price
> history (`market-data --all`, `price-history`) → (2) corporate actions, which arrive inside the
> filings and are read from memory → (3) filings and memory, 2025 baseline then 2026, chronologically
> (`known_since <= filed_at`) → (4) signals, score and Top Signals. Each history card is scored
> with the price, market cap and returns of its own filing date. Prices come from yfinance, whose
> close is already split/bonus-adjusted (no adjustment table needed); BSE bhavcopy files, if ever
> used, are in the UDiFF format. Dual keys (Phase 1) are replaced by one key per provider (TRACKER D1).

### Phase 1: Final Audit Sweep & Dual-Key Setup (30 Minutes)
Have Antigravity apply the combined fixes from all 6 audit reports and verify that all automated unit and integration tests pass (100% green).
Populate your .env file with your dual API keys (GROQ_API_KEY_1, GROQ_API_KEY_2, NVIDIA_API_KEY_1, NVIDIA_API_KEY_2, MISTRAL_API_KEY_1, MISTRAL_API_KEY_2, ZAI_API_KEY_1, ZAI_API_KEY_2) and set STORAGE_MODE=local.
Initialize your local data directories:
./data/text_cache/ (compressed .json.gz extracted text cache)
./data/local_r2/memory/ (local Living Dossiers)
./data/local_r2/daily_feed/ (local daily card arrays)

### Phase 2: The "5-Company Smoke Test" on Your Laptop (15 Minutes)
Never run a 1,200-company backfill before verifying the output on your 5 benchmark companies.
Run the local backfill from 01 January 2025 to 15 October 2026 restricted strictly to the 5 reference scrip codes:
506525 (Kanoria Chemicals)
532776 (Shivam Autotech)
505192 (SML Mahindra)
500672 (Evonile Pharma / Novartis India)
530019 (Jubilant Pharmova)
Open the local web dashboard (http://localhost:5173), click into each of the 5 companies, open their 360° Memory Drawers, and verify:
Did the 2025 AGM, concall, and quarterly balance sheet facts land cleanly inside each company's R2 Living Dossier?
Do the October 2026 cards automatically connect to those 2025/2026 memory entries, show [✓ Numbers verified], and match the 6 Gold-Standard Case Studies in Section 8?

### Phase 3: Build & Filter Your "Investable Universe" (~1,000–1,200 Companies) (5 Minutes)
Run sync-companies locally to populate the companies table with all BSE companies, their 22-industry classifications, and their current market caps.
Configure your backfill universe filter to focus 100% of compute on your true investable universe:
Active trading status (excluding suspended, delisted, or liquidated shell companies).
Market Cap ≥₹100 Crore (plus any custom watchlist stocks under ₹100 Cr you explicitly star).
This eliminates ~3,000 dormant micro-shells and cuts total backfill volume by ~70%.

### Phase 4: Execute Pass A — The 2025 Objective Baseline Run (2025-01-01 to 2025-12-31)
Run the local async backfill across 01 January 2025 to 31 December 2025 with:
5 concurrent async workers (with per-scrip chronological locking).
Stage 0 BSE XBRL Fast-Path enabled (instant 0-token XML parsing for all 4 quarters of 2025 financial results and shareholding patterns).
Objective Baseline Mode: Populates the 10 compartments of every company's R2 Living Dossier (financial_history, sector_kpis, segment_mix, capex_and_projects, guidance_and_watchlist, monthly_operational_ledger, corporate_actions_and_orders) with pure verified facts and known_since timestamps.
Pause & Resume Freedom: Because progress is saved after every company/month in ./data/backfill_progress.json and extracted PDFs are cached in ./data/text_cache/, you can close your laptop lid anytime and resume later from the exact point where it stopped.

### Phase 5: Execute Pass B — The 2026 Live Intelligence Layer (2026-01-01 to Today)
With every company's 2025 baseline dossier sitting on your local SSD, run the pipeline chronologically from 01 January 2026 to 15 October 2026.
Every 2026 announcement now evaluates against the rich 2025–2026 memory vault—automatically verifying promises (✅ Promise Delivered), computing AST-verified quantified impact math, scoring management credibility, and populating the Catalyst Calendar and Inflection Radar.

### Phase 6: One-Command Cloud Migration & Daily Autopilot
Run sync-to-cloud to bulk-upload your verified local SQLite tables to Cloudflare D1 and your /memory/ and /daily_feed/ JSON files to Cloudflare R2.
Your live Cloudflare Pages website (*.pages.dev) is now globally accessible on your phone and laptop with 21+ months of deep institutional memory.
For ongoing daily updates, run the lightweight daily sync on your laptop (or scheduled local daemon), which processes new daily filings in ~3 to 5 minutes and pushes only the incremental deltas to Cloudflare.
Your Daily 15-Minute Investor Ritual
| Time Window | Action Step | What You Look For (The Alpha Checklist) |
| 1. Pre-Market Morning Ritual (08:45 AM – 08:52 AM IST · 7 Mins) | Open your website, click 🔥 Top Signals, and toggle 🌅 Since 3:30 PM Close. | • Review the 3 to 6 overnight cards that cleared all 4 Signal Gates. / • Click [🔢 Show Working] to inspect the quantified revenue/EBITDA impact relative to Market Cap. / • Open the [🗂️ 360° Memory Drawer] on the top 1–2 stocks to check Management Credibility Score (≥75%), Receivable/Working-Capital health, and whether the stock is sitting in a tight consolidation base (1M return < +15%). |
| 2. Market Close Quick Scan (03:45 PM – 03:50 PM IST · 5 Mins) | Check ⚡ Live Intelligence Feed filtered to 🟢 High Impact filed during market hours (09:15–15:30 IST). | • Spot intraday order wins, plant commissionings, or credit rating upgrades where volume (RVOL >= 2.5x) confirmed institutional buying. / • Click [🔥 Star Signal] or [🗑️ Mark Noise] on 1–2 cards to train Loop 3. |
| 3. Weekend Deep-Work Review (Sunday · 10 Mins) | Open 🚀 Inflection Radar and 📅 Catalyst Calendar. | • Inflection Radar: Review the handful of small-caps/mid-caps where Commissioned Capex + Multi-Month Volume Acceleration + Debt Reduction / Smart-Money Buying converged in the last 90 days. / • Catalyst Calendar: Note upcoming Record Dates, Rights Issue windows, 18-month warrant conversion deadlines, and any ⚠️ Overdue Management Promises for the week ahead. |

