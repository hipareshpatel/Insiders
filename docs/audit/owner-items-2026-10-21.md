# Owner's requests, 16-21 Oct 2026: every message read back, and what is still open

Read back message by message from the session transcript on 21 Oct 2026 (151 messages from the owner since 16 Oct;
system notices and check-ins left out). Items that were questions and got their answer, and setup steps the owner
did (Cloudflare, secrets, public repo), are not listed. Status is checked against the code and docs, not taken from
earlier replies. "#n" is the owner's message number in that read-back.

## Open, in the order they will be done

| # | Request (short) | From | Status |
|---|---|---|---|
| 1 | **Consolidated figures wherever they exist; never mixed with standalone** | #150 (21 Oct) | In progress. Measured: 13 of 52 results cards published since 20 Sep use a standalone XBRL. The pipeline prefers the consolidated file only if NSE already lists it when the card is written (`_results_xbrl_url`). The AI-quality plan's item 2 ("basis on every metric line, one basis only") was never built. |
| 2 | Previous quarter missing on cards (E2E) | #150 | Partly done (8429077): a quarter is now derived from H1/9M/FY. The full fix is the XBRL history seed, which is still running. |
| 3 | "What these numbers mean", "For the decision", "Our reading": the three sections that matter, used wrongly; benchmark Indian and international sites | #150 | Open |
| 4 | One place for company memory: drop the half-window, the company page with full ordered financials, operating notes complete | #150 | Open |
| 5 | Explain "Recent pipeline runs" columns | #150 | Open |
| 6 | Tighten the AI's instructions and the data passed to it (the "weakest area") | #137 (20 Oct) | Partly done. The plan (`ai-quality-plan-2026-10-21.md`, 8 changes) is done for item 1 (live reserve). Partly done: item 3 (critic, shadow only), item 5 (short prompt A/B on 30%, not per-event with examples) and item 8 (raw replies stored, F55; no fact tables or critic verdicts per card). **Not built:** 2 (one basis per metric line in memory, period columns out of memory, same-event markers, page headers), 4 (facts table first), 6 (blind second vote on enumerated fields), 7 (end-of-day sweep on spare quota) |
| 7 | Use AI for call cards, connecting facts across calls, results and announcements | #135 | Partly done (3d69c9c): the model's takeaways, checked against the filing and memory. Linking to earlier calls and results is not measured. |
| 8 | A number should match even when a quote is reworded | #136 | Tried twice and refused by the audit each time (20 Oct: 3 of 15 wrong; 21 Oct: 2 of 7 wrong). Next: label memory figures and check them against the dossier entry they cite. |
| 9 | Re-run Yes Bank AT1 and the Vedanta/HZL card; older duplicates (Sunteck Q1FY27, Sun Pharma Q4FY26) | 20 Oct items 3, 8, 23 | Open: re-runs to be dispatched with the requeue in `actions-pending.md` |
| 10 | Slow, in-depth audit of every code line, website and workflow | #139 | In progress: `deep-audit-2026-10-21.md` (sections A intake, F website, G tests and docs still to do) |
| 11 | Queue merges for 05:45 IST | #136 | Superseded: merges are now done by the lead session when CI is green. The owner said on 21 Oct "do not merge" until today's list is done. |
| 12 | ~$5 of DeepSeek for the historical backfill | #126 | Answered. Superseded on 21 Oct by "use deepseek for pending" (drain until 23 Oct). |

## Done (checked)

- 21 Oct:
  - **Signals:** fixed: the snapshot window, 7/30-day tabs, results sized by their own change (audited), and a Turnarounds tab.
  - **Noise:** press releases, shareholder letters and monthly volumes are now read whole.
  - **Card display:**
    - the full analysis redrawn as panels;
    - the image export now carries the whole card at 4K;
    - the "computed" tags removed;
    - the industry path and 1W/1M/3M returns added;
    - figures in the text face.
  - **"To verify":** explained (Feed → "Held for review only" with owner mode).
  - **Page differences:** Today / Signals / All filings explained.
  - **Backfill counters:** explained and relabelled.
- 20 Oct: items 1-33 of `owner-items-2026-10-20.md`, except those carried into the Open table above (5, 8, 23, 3's older pairs).
- 16-19 Oct:
  - **OCR and documents:** RapidOCR in the pipeline (20 pages, measured dpi); DATA_QUALITY.md and raw saving.
  - **NSE-only and online:** NSE-only online pipeline (D34); NSE company master and new listings; annual-report XBRL catch-up scheduled; docs rewritten for online/NSE.
  - **Site:** redesign (Today, company page, cards); owner token and verdicts.
  - **Reviews:** live-only reviews (no round 7).
  - **Scheduling:** 15-minute autonomous runs; the daily audit routine.
