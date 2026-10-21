# Owner's requests, 16-21 Oct 2026: the complete list and where each stands

Every message read back on 21 Oct 2026 (151 owner messages since 16 Oct; system notices and check-ins left out).
Status is checked against the code, not taken from earlier replies.
- "Branch" means the commit is on `claude/nice-goodall-ta0sxs` (PR hipareshpatel/Insiders#45), not merged.
- "Live" means it is on the site now.

## A. Raised on 21 Oct

| # | Request | Status | Where |
|---|---|---|---|
| A1 | Where to verify the "To verify" cards | **Done.** Answered: System → owner token, then Feed → "Held for review only", verdict bar | — |
| A2 | Today vs Signals vs All filings | **Done.** Explained | — |
| A3 | DeepSeek to clear the pending queue | **Live** until 23 Oct (`pipeline/config/drain_until`) | #43 |
| A4 | Signals empty most days; a 30-day option | Snapshot window fix **live** (#44). On the branch: 7/30-day tabs, the snapshot served only for its window (it counted 3 and showed 0), and results sized by their own change (on/off +20 signals, 0 lost; blind review 18 of 20 strong) | #45 |
| A5 | Why the 34 high-impact cards failed | **Done.** Gate 1 could never open on results | `signals-results-size-2026-10-21.md` |
| A6 | Turnarounds tab; acquisitions count as growth | **Branch.** Tab built; acquisitions not excluded | #45 |
| A7 | Noise: monthly updates, press releases, shareholder letters dropped | **Branch.** Read whole now; a re-queued filing takes today's rules; 10 filings listed for a requeue after the merge | #45, `actions-pending.md` |
| A8 | Held cards: memory vs filing; quote rule | **Built, audited, reverted.** 2 of 7 released cards were WRONG (29%) | `held-quote-sources/` |
| A9 | Full analysis section looks off; image export not full or 2K/4K | **Branch.** Panels redesigned; the image holds the whole card at 3,840 px | #45 |
| A10 | Backfill counters confusing | **Branch.** Relabelled; explained (today's company list restarts each morning) | #45 |
| A11 | Unprofessional fonts | **Branch.** Figures in the text face with tabular digits; the monospace face dropped | #45 |
| A12 | No "✓ computed" on cards | **Branch.** Removed | #45 |
| A13 | Industry path and 1W/1M/3M returns on the card | **Branch.** New `ret_3m` column (migration 0012) is filled by the next market-data run | #45 |
| A14 | Previous quarters missing (E2E) | **Branch, partial.** A quarter is derived from H1/9M/FY. The seed now does companies reporting now first (E2E was near the end of the scrip order). The seed is still running: 423 companies this pass, next pass running | #45 |
| A15 | Consolidated not used where it exists / mixed with standalone | **Branch, partial.** 13 of 52 results cards since 20 Sep were standalone-made. Built: (1) a consolidated statement waits for the consolidated XBRL; (2) a standalone-made card is re-read when the consolidated file lands; (3) a standalone figure on a consolidated card is a problem (the standalone file is read beside it). Already built earlier: memory shows one basis per metric and drops standalone where consolidated exists. Open: re-run the 13 standalone-made cards after the merge | #45 |
| A16 | Earnings-call summaries on company pages shallow (UltraTech) | **Live.** 8-15 checked AI takeaways per call under fixed headings (Risks included), "vs earlier" from memory, kept per quarter and shown on the company page | #46 |
| A17 | BSE scrip codes on an NSE site | **Live.** NSE symbols in every company link; old links still resolve | #45 |
| A18 | "What these numbers mean", "For the decision", "Our reading" used wrongly; benchmark similar sites | **PR.** Benchmarked; a rule per box. Housekeeping signals, off-topic "not disclosed" items and procedural memory lines are kept off the face; the reading prompt asks for: expected vs actual, then driver, then what it means for the shareholder. On/off over 400 live cards: 20 changed | `card-sections-2026-10-21.md` |
| A19 | One company view: drop the half-window; company page financials complete and in order; operating notes complete | **Open** | — |
| A20 | Explain "Recent pipeline runs" columns | **Live.** Explained on the System page | #45 |
| A21 | Read the last 5 days back and list what was missed | **Done.** This file | — |
| A22 | Don't merge until the list is shown | List shown; the owner then said to merge (#45-#47 merged) | — |
| A23 | Institutional shareholding (FII, MF, insurers, named holders) and big changes on the company page | **Live** (#47). The whole universe's last two quarters are read in one go (maintenance `fill-memory`, owner: "let it get filled today"), with governance reports, a year of pledges and DGTR cases; the seed passes follow without a market-hours pause | #47 |

## B. Still open from 19-20 Oct

| # | Request | Status |
|---|---|---|
| B1 | Tighten the AI's instructions and inputs (20 Oct, "your weakest area"). Plan of 8 changes (`ai-quality-plan-2026-10-21.md`) | Item 1 (live reserve for the best writer) done. Item 2 (memory with one basis per line, printed periods withheld, same-event markers) mostly done. Items 3 (critic, shadow only) and 5 (short prompt A/B on 30%, no per-event examples) partly done. **Not built:** 4 (facts table first), 6 (blind second vote), 7 (end-of-day sweep on spare quota), 8 (critic verdicts kept per card) |
| B2 | AI for call cards, connecting earlier calls and results | Partly done (the model's takeaways, checked). Becomes A16 |
| B3 | Re-run Yes Bank AT1, Vedanta/HZL; older duplicate pairs Sunteck Q1FY27 and Sun Pharma Q4FY26 | Open: with the requeue after the merge |
| B4 | Deep audit of every code line, website, workflow | In progress (`deep-audit-2026-10-21.md`); sections A intake, F website, G tests and docs not done |
| B5 | Reviews run on live cards only, no AI for testing | Followed. The daily audit runs 4 times a day (`docs/audit/ledger.md`) |
| B6 | Accuracy gate (≥ 95% right) | Not met: the 21 Oct day had 21% right and 77% right-or-minor (48 cards) |

## C. Done earlier (checked)

- 20 Oct: items 1-33 of `owner-items-2026-10-20.md`, except those carried into B. Highlights:
  - scheduled jobs run, with honest statuses;
  - no cards for dividends, call schedules or small fines;
  - duplicate rule (Kapston);
  - no run-rate P/E;
  - "For the decision" from memory;
  - Vedanta/HZL subsidiary results;
  - verdict buttons that act;
  - the restated-comparatives fix;
  - the results table;
  - shareholder direction;
  - the seed-calls schedule;
  - 200-day daily audit.
- 16-19 Oct:
  - RapidOCR in the pipeline (20 pages); DATA_QUALITY.md and raw saving;
  - NSE-only, online (GitHub Actions + Cloudflare); the NSE company master with new listings; annual-report XBRL catch-up scheduled; docs rewritten;
  - redesigned Today, company page and cards; owner token and verdicts;
  - 15-minute autonomous runs.
