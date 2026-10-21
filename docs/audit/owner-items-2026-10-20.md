# Owner's items, 19-21 Oct 2026, and where each stands

Every item the owner raised in the cloud session over the last 24 hours, read back from the transcript on
21 Oct 2026 01:50 IST. "#n" is the merged pull request; #32 merges after D1's daily write reset (05:30 IST).

| # | Item (owner's words, short) | Status |
|---|---|---|
| 1 | Scheduled jobs all "Never run" | Fixed in #30: a job reads "First run due" until its first slot. First real runs: market-data 06:05, nightly 06:10 IST on 21 Oct - to be confirmed that morning |
| 2 | Dividend-only cards (Hexaware) not needed | Done (#30): memory and timeline only |
| 3 | Duplicate cards (Kapston) | Fixed on #32 (a board outcome with a stock split was typed as a corporate action and skipped the one-card-per-quarter rule); the Kapston copy is re-run after the merge. Open: older pairs Sunteck Q1FY27 and Sun Pharma Q4FY26 (another cause) |
| 4 | Call-schedule cards (Amagi) not needed | Done (#30): memory only |
| 5 | Real transcript analysis, on cards and company pages (HDB shallow) | Company page: "Earnings calls" by quarter and category on #32 (from memory, no AI). Open: the call card itself is still shallow |
| 6 | No run-rate P/E | Done (#30) |
| 7 | "For the decision": 3-4 memory points, useful, relevant and recent | Done (#30, #32): up to 4 dated points; a watch item or note only when on topic and recent |
| 8 | Vedanta card with HZL's results | Fixed (#30); the filing was re-run and is now "Vedanta arm HZL Q2 revenue jumps to ₹15,093 Cr", but held again for one quote - open, in Needs review |
| 9 | "formerly M S K A & Associates" | Done (#30); former names off the card header on #32 (kept for search) |
| 10 | 1,000+ pending | Explained: the queue's cap; almost all backfill (19 Apr-29 May); limited by D1's free writes. Write cuts and an honest counter on #32 |
| 11 | "Needs review · 100" strategy | Count was capped at 100 and re-runs looked like no-ops: fixed on #32. Blind test of 20 held cards: 10 wrong, 6 minor, 4 OK, so no blanket loosening; code repair first. Open: the daily routine below works this list |
| 12 | D1 writes - can GitHub stage them? | Answered: the cap counts rows written (indexes and search rows too); 5 unused indexes dropped and search rewrites narrowed on #32 |
| 13 | Approve / reject buttons | Done (#31): Wrong holds with the note, Right publishes; #32 makes both survive a re-run |
| 14 | DeepSeek for held cards (~$3.50) | Not used: code repair first (agreed) |
| 15 | Are quote-held cards really wrong? blind test | Done: 10 of 20 WRONG (restated comparatives, 10x slips, segment as company, direction) |
| 16 | Quarterly concall summary by category, no greetings | On #32 (company page, Overview) |
| 17 | Drop "Since the filing" | Done (#30) |
| 18 | Jindal "Wrong" verdict did nothing | Fixed (#31); old verdicts applied once by apply-verdicts right after #32 merges |
| 19 | Guidance breach before results are out (Jindal H1FY27) | Done (#31): a period's deadline is its results date (45/60 days) |
| 20 | ICICI Pru Life name change card | Done (#30): memory only; the company row and memory carry over by ISIN |
| 21 | Results table: Revenue, EBITDA, margin, PAT, EPS + one mover | Done (#31) |
| 22 | Small fines (Rashi ₹0.02 Cr, Schneider ₹0.05 Cr) | Done (#30): below 5% of annual profit (min ₹1 lakh) memory only |
| 23 | Cards must give a direction for shareholders (Yes Bank AT1) | Prompt rule (#31); live cards change on their next AI run. Open: re-run the Yes Bank card |
| 24 | Interpretation on the face (TVS Motor rating card) | First rule failed its audit (4 of 20 wrong, mostly memory links framed wrongly); tightened version (filing-based only, stricter wording) 1 of 19 wrong; a 50-point blind review is running before it can ship |
| 25 | Re-run button seems to do nothing | Explained and fixed on #32 (see 11) |
| 26 | Seed-calls schedule missed runs | Fixed (#29): each run starts the next; 65 seeded, 0 failed on the first run after the fix |
| 27 | DeepSeek model, concurrency, cache | Answered; seed runs 6 at a time, cache kept |
| 28 | ~$5 of DeepSeek for the historical backfill | Answered on 20 Oct; no decision recorded - the owner's call |
| 29 | Memory too shallow: seed from transcripts and presentations, no Gemini | Done: seed-calls nightly (DeepSeek with cache, then free models) |
| 30 | Restated comparatives (Kanoria, Star Health) | On #32: a restated column drops whole; a built EBITDA comparison needs its parts printed (Jubilant Agri, Man Industries); 8 of 9 restored figures checked right, the 9th now dropped |
| 31 | Use up to 3 agents, finish fast | Done |
| 32 | Daily card audit (now: 200 days, 10:00-17:00 IST) | Scheduled from the cloud - see docs/audit/ledger.md |
| 33 | Earlier (19-20 Oct): live window, failed filings retried, design gaps, Gemini on System, missing results | Done (#10, #11, #13-#15) |

Found on the way: D1 stopped taking writes at 01:04 IST on 21 Oct (its free 100,000 a day) while our counter said
93,369, because maintenance commands never added theirs; fixed on #32, writes resume at 05:30 IST.

## Update 21 Oct 06:50 IST

- Held cards (O9): code repair measured over all 223 held cards (no AI). Replacing a paraphrased quote with the
  filing's own line that holds every figure releases only 6 cards; dropping the failing point to publish the rest
  would release 15, of which a blind check against the PDFs found 3 WRONG (20%). Neither ships. Held cards are worked
  instead by the daily audit (release candidates for the owner's Right), the owner's verdict buttons, and the planned
  end-of-day re-write on spare free quota (docs/audit/ai-quality-plan-2026-10-21.md item 7).
- D1 writes: no write for an unchanged row (cards, companies, filings, runs, imports); refresh-card-blocks and
  refresh-summaries over unchanged rows now cost 0 rows (were 1,000 per 1,000), a re-run with the same card 0 (was 3),
  seed resume points 200 per 1,000 companies (was 2,000). A changed attachment on a known filing is counted per run
  and not yet re-queued (ATTACHMENT_REQUEUE=1 turns it on once a day's count shows NSE keeps unchanged links).
