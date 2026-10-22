# Call-takeaway check, on/off audit (22 Oct 2026)

The change (work queue A): a call takeaway's figure may be (1) said in the same answer as its quote (2,500 characters
either side), (2) one subtraction of the quote's own percentages, or (3) a versus_prior whose figures are in the quote
and whose quarter is named there or nearby. The check runs on every stored call card when its blocks are refreshed
(`card_refresh.recheck_calls`), and it only ever adds passes.

## Round 1: all three parts

`scripts/audit_call_takeaways.py` over the live site's call cards (no AI): 122 cards, 531 takeaways; verified 288 -> 333,
45 newly accepted, 0 newly refused. An independent reviewer read each of the 45 against its transcript:

| verdict | count | what |
|---|---|---|
| RIGHT | 37 | |
| MINOR | 3 | Bosch's deck "Q-on-Q" is Jan-Mar against Jan-Mar (two); DB Corp ₹120-140 Cr capex, ₹120 Cr an analyst's figure |
| WRONG | 5 | HDFC AMC ₹8,700 Cr treasury (the analyst's figure); Tata Comm ₹886 Cr loss (FY25 column, not Q1FY27); CIFL cost of funds 9.38% (FY22 of a series); India Cements' file is UltraTech's call (its ₹240 dividend, 0.94x); Tech Mahindra "115% of dividend" (115% is FCF to PAT) and DSO 91 (it is 89) |

All 5 wrong and all 3 minor came in through part (1). No distance from the quote separates them (wrong at 57-459
characters, right from 8 to 1,525), nor does a question mark between figure and quote, nor a slide-like quote.

## Round 2: part (1) dropped

Parts (2) and (3) only: 144 cards, 646 takeaways; verified 343 -> 345, 2 newly accepted, 0 newly refused. Metro Brands
(versus_prior from its own sentence) was RIGHT in round 1's review; DCW's net-debt takeaway (a card since) went to an
independent reviewer.
