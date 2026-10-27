# Screener's own rules, and what we measured (27 Oct 2026)

Read from screener's help site on 27 Oct 2026: support.screener.in/article/4-differences ("Why are numbers on Screener
different?"), /article/11-reconciling-numbers, /article/41-standalone-or-consolidated, and
www.screener.in/guides/optimizations. Each rule is set against our checks of revenue, profit and EPS, and against a measured
example where we have one. A rule screener states but our measurement contradicts is marked so: the measurement wins.

| # | Screener's rule (their words, shortened) | Lines it touches | In our checks | Measured |
|---|---|---|---|---|
| 1 | Sales = total revenue - other income - (excise duty + VAT + sales tax), in all cases | revenue | `screener_explain` `excise_netted` (27 Oct); operating profit too (F220, `matches_screener_view:excise`) | PICCADIL Q2FY25: 200.52 with excise 15.61, screener 185 |
| 2 | Sales are net of discounts; discounts some companies put in other expenses are netted from sales | revenue | not checkable: NSE's results XBRL tags no discount line | none found |
| 3 | Only revenue from operations is sales; other income is its own line | revenue, other income | yes: our revenue is revenue from operations | screener support email, 27 Oct (SONACOMS) |
| 4 | Other income also holds exceptional and extraordinary items | other income, PBT | yes since 27 Oct 2026 (F220): other income is compared, class `matches_screener_view:exceptional_in_other_income`; PBT itself is unaffected | ADANIENT Q4FY25: other income 635.78 + exceptional items 3,945.73 = 4,581.51 (statement p12); screener 4,582 |
| 5 | Net Profit is the profit attributable to the owners | profit | **contradicted**: screener's quarterly and yearly Net Profit is the whole profit | ADANIENT Q4FY25 screener 4,015 = whole 4,014.90 (owners 3,844.91); FY25 8,005 = whole 8,004.99; ABREL Q4FY26 screener 5 = whole 5.39 (owners 10.84) |
| 6 | Earlier years are replaced by the figures the next annual report restates | all | `screener_explain` `restated_later` | BENGALASM Q3FY25, SGMART Q2FY25 / Q3FY25, ACC Q2FY26, AMBUJACEM Q1FY25 |
| 7 | (guide) EPS of earlier periods on today's share count after a bonus or split | EPS | `screener_explain` `share_adjusted` | MCX 1:5 split, record date 2 Jan 2026 |
| 8 | Exceptional items are left out of P/E and ROCE only | ratios | not compared (no ratios) | - |
| 9 | Employee cost includes director remuneration | employee cost | not compared (screener's quarterly table has no employee line) | - |
| 10 | Borrowings = long term + short term + current maturities + lease liabilities | balance sheet | not compared | - |
| 11 | Deferred tax shown net; fixed assets include goodwill, intangibles and right-of-use assets, CWIP apart | balance sheet | not compared | - |
| 12 | Consolidated by default; screens fall back to standalone when the two barely differ or standalone is longer or newer | basis | our comparison reads screener's consolidated and standalone pages by name | - |
| 13 | (seen, not stated) EPS worked out from screener's own rounded profit and share count | EPS | within our EPS tolerance, no rule needed | KENNAMET Q1FY26: statement 14.22, screener 14.24 = 313 / 21,978,240 shares |

Not explained by any rule (the company's own figure was checked): screener's 63MOONS revenue (10 against 37.53) and ACC
Q4FY25 (6,115 against 6,066.52 with government grants); KOVAI Q4FY26 is the company's own correction (a corrigendum), which
screener has and BSE's file does not.

## More rules (27 Oct 2026, later the same day)

Read after the owner said the rules sit on several pages: the help site's map lists three more articles
(support.screener.in/article/40-null-values, /42-exceptional-items-calculation, /43-change-log-draft), and 128 pages under
www.screener.in/docs/ (125 change-log notes, 3 guides) were read in full; 55 state a number rule, 73 do not (pages and quotes:
the session scratchpad, `scr/changelog-rules.md`). "Updated on" dates are the last edit (many 2020-11-26/27: one move day).
The rules that bear on the lines we compare:

| # | Screener's rule | Source | Lines | In our checks |
|---|---|---|---|---|
| 14 | Exceptional items after tax = exceptional items - tax x exceptional items / PBT; the whole item when that tax is larger. Example: Graphite India, 954 Cr exceptional, tax 188.5, PBT 992, 773 Cr after tax | article 42 | profit without exceptional items | `screener_view` computes it (recorded; no compared line reads it yet) |
| 15 | Profit or loss on sale of fixed assets is always an exceptional item (not adjusted for tax) | article 42 | other income, exceptional | not separately: our exceptional line is the company's own |
| 16 | Profit from associates is always "other ordinary income"; profit from selling an associate is exceptional | article 42 | other income, PBT | not yet: a gap of exactly the associates' share would be this rule |
| 17 | Net Profit expands to "Profit for EPS", "Exceptional items AT" and "Profit for PE" | change log Netprofit-breakup-screener (2023-07-01) | profit | the page's main Net Profit row is the whole profit (measured, row 5) |
| 18 | "fixed formula for PAT where weird adjustments in minority interest are done" | change log bug-fixes-apr (2021-07-13) | profit | screener had the same owners/minority trouble we found in NSE's files (F219) |
| 19 | Annual figures come from the quarterly filings "till the time annual reports are not available", then from the annual report | change log annual-quarterly-filings (2020-11-26) | annual lines | a later annual-report figure is a restatement (row 6) |
| 20 | Share counts adjusted for an "unprovided bonus" | change log may-20-bug-fixes (2020-11-27) | EPS | `share_adjusted` / `share_adjust` |
| 21 | Quarterly PE = price / (latest quarter's EPS x 4); consolidated PE leaves out exceptional items | change log Quarterly-PE (2025-10-28), bug-fixes-feb-21 | ratios | not compared |

Not stated on any page read: how TTM is built, the definitions of Expenses, Interest, Depreciation, PBT and Tax %, how
bank lines (Revenue, Financing Profit) are built, and how standalone or consolidated is chosen on a company page. A
robots.txt note: screener asks crawlers not to open /company/source/quarter/ pages; none of our tools may.
