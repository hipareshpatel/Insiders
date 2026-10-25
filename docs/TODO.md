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
| 2 | When a file is still too large, say "file too large (X MB)" and do not retry it | Today it says "no readable text" and downloads the file 3 times for nothing | Yes | Built (F131), PR #108 |
| 3 | R1: a figure shown as a fact (results table, key numbers, "from memory" figures) comes only from an exchange figure file or a statement page we can point to. What management said (guidance, orders, capex, call remarks) stays in memory as "said on <date> in <document>", never as a checked figure | Old mistakes in our memory repeat on every later card (CIE India, HCL Tech) | Yes | Batch 2 (memory), after 10 |
| 10 | Tag every memory item with: who produced it (exchange figure file / our AI / our own calculation), the kind of document (results statement, call, slides, press release), basis (company alone or group), period, unit as printed, page and quote, and whether it passed our checks. Items with no tag count as "our AI" | Today an item records only which filing and date it came from: an exchange figure and our AI's figure from the same filing look the same, so R1 cannot be applied | Yes | Batch 2 (memory), first |
| 4 | R2: keep the text and figure files of every filing for good (not 8 days) | We cannot re-check old cards; the repeat-filing check misses repeats once the text is gone | No | Owner: no change (25 Oct) |
| 5 | R3: read the `decimals` the XBRL file states (checked live 25 Oct: values are always in rupees; `decimals="-7"` means printed in crore, `-5` in lakh) and use it to match figures at the company's printed precision | We ignore it today. It does **not** catch a file the company itself filed at the wrong scale (Jubilant, F54): our check against the PDF still does that | Yes | Moved to step 2: its only use is matching EBITDA and table figures at the printed precision (items 11, 13); built alone it would do nothing |
| 6 | List the failed filings by reason (70 on 25 Oct) | We do not know how many filings we lose, or why | Yes | Built: `failed-report` (F131); run it from GitHub once PR #108 is merged |
| 7 | Check one busy day's NSE list against a second count | We have never checked that NSE gives us every filing | Yes | To do (a check, no code) |
| 8 | Look at why each run takes ~41 minutes | The "every 15 minutes" schedule really runs every ~42 minutes, so cards come late | Later | Owner: when we reach the AI step (most of a run's time is AI calls) |
| 9 | Cover companies listed only on NSE | Thought to be set aside | Yes | **No work needed**: measured 23 Oct (company-list job log): 2,613 NSE listings, all 2,613 matched, `nse_only` 0; the company master adds NSE listings itself. A company listed after the morning sync is matched the next weekday |

Build order (decided 25 Oct 2026, the owner left it to the lead session): **batch 1** = items 1, 2, 6, 7 (small, independent; 5 moved to step 2, 9 needed no work); **batch 2** = items 10 then 3 (they change how memory works, so they are built and measured on their own).

## Step 2: reading the file (to discuss)

| # | Improvement | What it fixes | Owner | State |
|---|---|---|---|---|
| 11 | EBITDA: when the company prints EBITDA (press release or slides), show theirs with its own label; when it does not, show ours marked "calculated by us". Our formula stays: profit before exceptional items and tax + interest + depreciation − other income (the owner's note of 25 Oct gives the same formula); none for banks and NBFCs | Cards set our EBITDA against a company's printed one with a different definition (Lumax, Bansal Wire, Solara and others) | Yes (owner, 25 Oct): label ours "Operating EBITDA (calculated)" and show what it leaves out (other income ₹X Cr) | Step 2 |
| 12 | Group EBITDA leaves out the share of associates' and joint ventures' profit (owner's note, 25 Oct: Ind AS 28, they are not line-by-line). Subtract it only when the profit we start from includes it, which differs by file; check that per file, never assume | "Profit before vs after associates" was one of the results-table mistakes | Yes (owner, 25 Oct) | Step 2 |
| 13 | Official lines (revenue, profit, interest, tax) come from the figure file; our PDF reading checks them and a disagreement holds the figure | 98.5% per figure is about 64% for a 30-figure table to be all right; the figure file is exact | – | Discuss in step 2 |

Not taken: EBITDA from Yahoo (the owner's note mentions it). It is not an exchange file (item 3), and Yahoo's own
definition is not published.

## The card we are building towards

The owner's target card (25 Oct 2026): `docs/design/target-card-kajaria-q2fy27.md` (Kajaria Ceramics Q2FY27, every
line with its source: Statement, Computed, Filing, Memory). Items 3, 10, 11, 12 and 13 are the groundwork for it.
Fixes to the sample itself, found on review:

| # | Improvement | What it fixes | Owner | State |
|---|---|---|---|---|
| 14 | EBITDA and its margin carry the label "Computed" (ours) or "Filing" (the company's printed figure), never "Statement": EBITDA is not a statement line | The sample marks our EBITDA ₹286.61 Cr as "Statement" while the release prints its own (year-ago ₹212.90 Cr against our ₹213.45 Cr) | – | With item 11 |
| 15 | One profit line, named the same everywhere: the headline's "net profit to shareholders ₹189.52 Cr" and the table's "Net profit ₹190.72 Cr" are two different lines (after and before minority interest) | Two profit figures on one card read as a mistake | – | Proposed |
| 16 | A figure computed from memory (cost per MSM from deal history) only when every input is an exchange-file or quoted-filing item (item 10's tags) | Otherwise "Computed" hides an AI-read input | – | With items 3 and 10 |
| 17 | Measure what more lines cost: a card is WRONG if any one line is wrong, so ~25 lines need each line right about 99.8% of the time to keep cards at 95% | The richer the card, the harder the 95% bar | – | Measure before go-live |
