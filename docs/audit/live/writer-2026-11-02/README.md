# Writer audit, 2 Nov 2026: DeepSeek against Gemini (owner asked)

The sample is 50 published cards filed 15 Oct to 2 Nov 2026: 25 written by deepseek-flash, drawn at random with seed 20261102, and 25 by Gemini (gemini and gemini_2) matched to the same event mix (8 results, 4 call/presentation, 3 M&A, 2 fundraise, 2 governance, 2 other, 1 each of ratings, order, annual report and corporate action).
- **Blind:** every model name was scrubbed from the cards before review.
- **Reviewers:** five independent reviewers (mid model) judged 10 cards each against the filing PDF and live memory, using `pipeline/scripts/daily_audit/reviewer_prompt.txt`.
- **Scoring:** the writer key was read only after all verdicts were in.

| Writer | Cards | RIGHT | MINOR | WRONG on the checked face | 95% interval | Coverage THIN |
|---|---|---|---|---|---|---|
| DeepSeek | 25 | 6 | 11 | 8 (32%) | 17-52% | 9 |
| Gemini | 25 | 7 | 13 | 5 (20%) | 9-39% | 13 |

- **WRONG, DeepSeek:**
  - SWIGGY (wrong period)
  - HATSUN, IIFL (arithmetic)
  - THOMASCOOK (invented)
  - DLF x2 (a one-off gain left out and a spurious distress signal; a standalone net-cash row)
  - ARMEE (wrong period)
  - INDIANB (wrong causes and directions)
- **WRONG, Gemini:**
  - TCI, IOC (associates' share called discontinued: the class DISCONTINUED_NEEDS_FIGURE fixes, on since 1 Nov)
  - BANDHANBNK (ROA bases mixed)
  - HEROMOTOCO (a retail % called dispatches)
  - BETA (H1 EBITDA in a quarter's block)

**Reading.** The intervals overlap, so this does not prove DeepSeek worse. In three audits, though, it has never measured better: 47% of 15 on 16 Oct, 32% of 34 on 21-23 Oct, and 32% of 25 here. Several WRONGs on both sides come from code or memory rather than the writer: the discontinued label, the DLF standalone row, the ROA bases and the signals. Both writers' cards predate some of the 1-2 Nov fixes.
