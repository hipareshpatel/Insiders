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
