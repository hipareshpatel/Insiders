# Audit: the four season tiles on the Results page (Q2FY27), 31 Oct 2026

Asked by the owner on 31 Oct 2026 (phone screenshot, about 20:05 IST): "It seems like wrong number". Audit only, no code
changes. Everything below was measured on 31 Oct 2026, 19:30–20:15 IST, from the live site
(`https://insiders.reply-bd3.workers.dev/api/results-kpi`, every page of Q2FY27, Q1FY27, Q2FY26 and Q1FY26, and page 1 of
seven older quarters), read against the code on `main` at `4cc2bbb` (#301).

## 1. Short answer

- **The sums on the screen are right.** Every number on the four tiles and in "What the season says so far" comes
  out the same when worked again by hand from the 645 companies the site holds.
- **Each company's growth is worked out against the right quarter.** For 585 of 587 companies the revenue growth
  matches this year's Sep quarter against last year's Sep quarter, both as we store them. The two that differ are
  basis switches (section 4, item C).
- **Spot checks on large companies agree with what they actually filed a year ago** (TCS, Reliance, Maruti, Bajaj
  Auto: the year-ago revenue the site uses equals what they reported for Sep 2025).
- **The numbers are high, but not because of one bad step.** Median revenue growth has climbed steadily for four
  quarters: 9.2% (Sep 2025) → 10.9% → 13.3% → 17.8% (Jun 2026, full season, 1,846 companies) → 21.0% now. There is no
  sudden jump at one quarter, which is what a broken step usually leaves behind. Early reporters are not the cause either:
  the same 645 companies had 17.9% last quarter, the same as the full season's 17.8%.
- **What is wrong is smaller, and is listed in section 4**: one sentence on the panel that is not true when like is
  compared with like, about 19 companies dropped from "with a year-ago quarter" although we hold that quarter, one
  company with a figure 100 times too small last quarter, and a few wording points.

What this audit could **not** check: the Sep 2026 figures against Screener for a fresh sample. The automatic Screener
fetch was blocked in this session. The repo's own latest Screener check is the best evidence we have: quarterly rows
match Screener exactly 95.9% of the time for FY26 and 98.4% for FY27 (`docs/STATUS.md`, item 15b, run 41174640014).
A hand check of 10–20 companies on Screener (section 6) would close this.

## 2. The screen, worked again

From the live API summary (`quarter=Q2FY27`, nothing filtered):

| Tile | Screen | Worked again from the 645 rows | Same? |
|---|---|---|---|
| Revenue up | 531 of 587 · 90%, median +21.0% | 531 / 587 = 90.5%; median of 587 = 21.0 | Yes |
| EBITDA up | 380 of 493 · 77%, median +23.7% | 380 / 493 = 77.1% | Yes |
| PAT up | 422 of 586 · 72%, median +24.2% | 422 / 586 = 72.0%; median of 523 = 24.2 | Yes |
| Loss to profit | 29 of 53 · 55% | 29 / 53 = 54.7%; 53 = 29 turned + 13 narrowed + 11 widened | Yes |
| Headline | 586 of 645, 422 grew, median +24.2% | 586 = 544 with a % + 29 + 13 | Yes |
| Speeding up / slowing | 212 / 238 | 212 + 238 + 27 steady + 168 not comparable = 645 | Yes |

The 20-step bars also match (90% → 18 filled steps).

How each tile counts (code: `web/shared/resultsStats.ts`, `summarise`):
- "of" counts only companies that can be compared with a year ago (a % or a named turn such as loss to profit).
  645 reported; 58–59 have no year-ago quarter, so the "of" is 586–587.
- PAT up includes the 29 that went from loss to profit. A narrower loss is not counted as "up".
- EBITDA leaves out banks, NBFCs, insurers, REITs and InvITs (539 ordinary companies, 538 with EBITDA).
- Medians use only companies with a %; the 63 whose profit crossed zero are in the counts, not the median.

## 3. Are the high numbers believable?

### 3a. Growth has climbed for four quarters, not jumped at one

Whole season for each quarter, from the live API (the share is "grew" out of "can be compared"):

| Quarter | Companies | Revenue up | Median revenue | PAT up | Median PAT | Median EBITDA |
|---|---|---|---|---|---|---|
| Sep 2024 (Q2FY25) | 1,449 | 74% | 10.6% | 59% | 11.0% | 9.0% |
| Dec 2024 (Q3FY25) | 1,478 | 75% | 10.6% | 56% | 10.9% | 10.3% |
| Mar 2025 (Q4FY25) | 1,464 | 74% | 9.3% | 56% | 11.9% | 10.9% |
| Jun 2025 (Q1FY26) | 1,683 | 72% | 8.7% | 59% | 11.4% | 10.3% |
| Sep 2025 (Q2FY26) | 1,720 | 74% | 9.2% | 57% | 10.9% | 13.6% |
| Dec 2025 (Q3FY26) | 1,766 | 77% | 10.9% | 58% | 11.1% | 15.8% |
| Mar 2026 (Q4FY26) | 1,777 | 80% | 13.3% | 63% | 19.6% | 17.3% |
| Jun 2026 (Q1FY27) | 1,846 | 85% | 17.8% | 68% | 23.2% | 21.7% |
| **Sep 2026 (Q2FY27, so far)** | **645** | **90%** | **21.0%** | **72%** | **24.2%** | **23.7%** |

The same 645 companies, quarter by quarter (from each row's 8-quarter history): median revenue growth 10.0% (Sep 2025),
10.8%, 13.5%, 17.9%, 21.0%. So the companies that have reported so far are not unusually strong: they look like the
full market did last quarter.

### 3b. Large companies look right one by one

- TCS: year-ago revenue used 65,817 Cr (filed Sep 2025: 65,799). Growth now +11.2%.
- Reliance: year-ago 254,700 Cr (filed: about 254,600). Growth +29.8%.
- Maruti: year-ago 42,345 Cr (filed: about 42,300). Growth +26.0%.
- Bajaj Auto: year-ago 15,733 Cr (filed: about 15,735). Growth +59.7%, which follows its new overseas unit coming into
  the consolidated figures from Mar 2026 (its history: +18.8%, +23.1%, +41%, +65.1%, +59.7%).
- Pattern across sectors: IT about +10–11% (Infosys +10.7%, HCL +11.5%, Wipro +9.1%), oil marketers very high
  (IOC +42.2%, Reliance +29.8%), metals high (Hindustan Zinc +76.5%, JSW Steel +20.7%), autos high (TVS +38.6%).
  That looks like a real price and currency effect, not a bug, but it cannot be proven from our data alone.

By size, revenue grew for 95% of large, 91% of mid and 87% of small companies (medians 21.7%, 21.5%, 19.2%).

### 3c. Year-ago figure check, company by company

For every Sep 2026 company with a revenue growth figure, the year-ago revenue it implies was set against our stored
Sep 2025 row: **585 of 587 equal** (within 1%). The two that differ are HATSUN and PITTIENG (item C below).

## 4. What is wrong or weak (no change made)

Ordered by how much it matters to the owner.

**A. "Profit grew faster than sales" is not true like for like (wording, misleading).**
The panel compares three medians taken over three different groups of companies: revenue over 587 (banks
included), EBITDA over ordinary companies only, profit over 523 (turns left out). Taken over the same companies:

| Same companies | Count | Median revenue | Median EBITDA | Median PAT |
|---|---|---|---|---|
| All with revenue and profit % | 518 | 21.2% | – | 24.7% |
| Ordinary companies with all three % | 427 | 22.2% | 23.4% | **21.3%** |

For ordinary companies, profit grew a little **slower** than sales. The sentence holds only when banks and NBFCs are
mixed in. Standard practice is to compare growth over the same set of companies.
Code: `web/src/lib/resultsView.ts`, `seasonLines`.

**B. 6 companies dropped from "with a year-ago quarter" although both quarters are stored on the same basis.**
CHOLAFIN (profit 1,763.61 now, 1,159.61 a year ago), IIFLCAPS (126.9 / 85.15), MONARCH (56.56 / 44.97),
5PAISA (7.06 / 9.48), SPANDANA (18.24 / -249.16, should be "loss to profit"), SEITINVIT (-31.54 / 8.64, should be
"profit to loss"). All are consolidated in both quarters, and revenue growth is there for them, so the year-ago
quarter is stored, but profit growth is blank. Likely cause (not confirmed): the profit line used this quarter (for
example the owners' share) is missing from the year-ago entry, and the code takes the comparative from the same line
only (`pipeline/src/bse_intel/results_table.py`, `table_of`, `pat_row`). Effect: PAT "of" is 6 too low, loss to profit
1 too low.

**C. 13 companies dropped because the basis changed (consolidated now, standalone a year ago).**
ATHERENERG, METROBRAND, TIMKEN, E2E, SGFIN, DHANUKA, RPGLIFE, RATNAVEER, DIAMONDYD, GMBREW, JAGSNPHARM, AHCL,
WELINV. The table takes consolidated first and does not fall back to standalone-against-standalone when the year-ago
consolidated quarter is missing. The reverse also happens (HATSUN, PITTIENG: standalone now, consolidated a year ago,
growth shown on standalone against our standalone base, which is right, but the Sep 2025 row on the site is the
consolidated one). This also leaves 5 of them as "not comparable" for speeding up / slowing. Effect: "of" is about
13 too low on PAT. Whether to compare standalone with standalone here is an owner call.

**D. One company had a figure 100 times too small last quarter.**
IMPAL (India Motor Parts) Jun 2026: revenue 2.34 Cr, profit 0.22 Cr (its usual quarter is about 220 Cr). So the
site shows its Jun 2026 growth as -98.8% and its revenue up 9,363% from Jun to Sep 2026, and counts it as "speeding up".
This is a unit slip in the Jun 2026 row (the class TODO 147 / #295 and #297 deal with). It does not change the
Sep 2026 tiles, but it is wrong on the company row and in last season's numbers.

**E. Some companies with no year-ago quarter are long-listed.**
40 of the 59 with no comparison have no Sep 2025 row at all. Most are new listings (Jio Platforms, Meesho, ICICI AMC,
SBI Funds, Bharat Coal and others), which is correct. A few have been listed for years and should have one: STARHEALTH,
NDTV and a handful of small companies (INDTONER, HORIZONIND, SWASTIKAIN and similar) need a check that the Sep 2025
file was read.

**F. Wording on the tiles (minor).**
- "Banks and NBFCs have no EBITDA": insurers, REITs and InvITs are also left out.
- "Loss to profit" tile shows "of 53 · 55%" and, under it, "No % when last year was a loss". Those read as opposite
  messages; the second means "no growth % for these companies".
- "645 reported" includes 5 REITs and InvITs.

**G. Very large single changes are real filings, not errors, as far as checked.**
The biggest moves (SADHNANIQ revenue +1,483%, ABREL +743%, STLTECH profit +12,825%, EMKAY +6,643%) come from tiny
year-ago bases. They do not move the medians. NETWEB +336% and HFCL +144% follow steady rises over several quarters.

### What each item does to the screen

Fixing B and C would add roughly 19 companies to the "of" of PAT (586 → about 605) and a similar number to revenue.
Most of them grew profit, so the shares would move by about 1 point at most. **No item here changes the picture
"about 9 in 10 grew revenue, about 7 in 10 grew profit, median growth above 20%".** If the owner believes those
levels are wrong, the place to look is the stored Sep 2026 and Sep 2025 figures themselves against Screener
(section 6), not the tile code.

## 5. Past PRs read for this audit

- #265, #272, #274 (30 Oct): the Results page reads saved statements only, one row per company and quarter.
- #281 (31 Oct): the Design E top with these four tiles.
- #288 (31 Oct): "X of Y" counts only comparable companies (before it: 401 of 611 = 65.6%; after: 401 of 553 = 72.5%);
  loss to profit over loss-makers a year ago; median note; 40 companies checked against Screener.
- #289, #290 (31 Oct): profit before exceptional items; owners' plus minority must equal total (ATUL Q2FY26 had shown
  +77.1% profit, truth about -13%); profit on the wrong side of zero from PBT minus tax corrected.
- #291, #298 (31 Oct): year-ago figures as later restated (from the filing PDF, only when the original matches),
  statements matched to Screener, weekly Screener check.
- #295, #297 (31 Oct): unit-slip checks (item D is one more of that class).

None of them changed how the four tiles are added up after #288. The figures under them changed with #290 and #291.

## 6. Suggested next checks (for whoever builds the fix)

1. Hand check on Screener, 15 companies picked at random from the 645 (not only large ones): Sep 2026 and Sep 2025
   Sales and Net Profit. If 14 or 15 agree within 1%, the tiles are right and the season is simply strong.
2. Items B and C: list every company and quarter where revenue growth exists but profit growth is blank on the same
   basis (B), and where the basis changed between the two Sep quarters (C).
3. Item A: work the "faster than sales" line on one set of companies.
4. Item D: run the unit-slip check over every stored quarter, not only the newest.

## 7. How this was measured

Every page of `GET /api/results-kpi?quarter=<Q>&page=<n>` was saved for Q2FY27 (13 pages, 645 rows), Q1FY27 (37),
Q2FY26 (35) and Q1FY26 (34), and page 1 (the summary) for Q2FY25 to Q4FY26. Counts and medians were worked again in a
short Python script with the same rules as `summarise` (median of an even count is the mean of the middle two). The
implied year-ago revenue is `revenue / (1 + revenue_yoy / 100)`, compared with the Sep 2025 row's `revenue`. Year-ago
figures for TCS, Reliance, Maruti and Bajaj Auto were checked against their Sep 2025 filings as known before this
audit, not fetched today.
