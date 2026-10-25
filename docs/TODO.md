# To-do list: improvements waiting to be built together

The owner asked on 25 Oct 2026 to collect the improvements here and build them all together, to save time and
tokens. How it works:

- Each idea is added here as it comes up, with what it fixes, in simple English.
- The owner marks each one **Yes**, **No** or **Later**.
- When the owner says "build", every **Yes** item is built in one go: one set of changes, one test run, one PR.
- Once built, an item moves to `docs/TRACKER.md` (with its F number) and leaves this list.
- Exception: a fix for something live that is being lost or published wrong is built at once, and noted here.

This list holds only the first-principles review's items (`docs/FROM_ZERO.md`). The older lists stay where they are:
`docs/PLAN.md` "Pending work" and `docs/TASKS.md`.

## Step 1: what we collect

| # | Improvement | What it fixes | Owner | State |
|---|---|---|---|---|
| 1 | One 120 MB size limit for every filing | Big results PDFs (NHPC FY26) were skipped at 30 MB and failed | Yes | Built, PR #108 (not merged) |
| 2 | When a file is still too large, say "file too large (X MB)" and do not retry it | Today it says "no readable text" and downloads the file 3 times for nothing | – | Proposed |
| 3 | R1: card figures come only from exchange files, never from what our AI wrote before | Old mistakes in our memory repeat on every later card | – | Proposed |
| 4 | R2: keep the text and figure files of every filing for good (not 8 days) | We cannot re-check old cards; the repeat-filing check misses repeats once the text is gone | – | Proposed; measure the storage size first |
| 5 | R3: read the unit the XBRL file states | We guess the unit today; a wrong guess makes a figure 10 or 100 times off | – | Proposed |
| 6 | List the failed filings by reason (70 on 25 Oct) | We do not know how many filings we lose, or why | – | Proposed (a check, no code) |
| 7 | Check one busy day's NSE list against a second count | We have never checked that NSE gives us every filing | – | Proposed (a check, no code) |
| 8 | Look at why each run takes ~41 minutes | The "every 15 minutes" schedule really runs every ~42 minutes, so cards come late | – | Proposed (a check first) |
| 9 | Cover companies listed only on NSE, and shareholding filings | These filings are set aside today, so they get no card | – | Proposed; decide if wanted |
