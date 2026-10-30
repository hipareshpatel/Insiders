# Card prompt audit, 30 Oct 2026 (TODO 142)

Read-only audit of how invented claims reach a card, against the 37 WRONG items of the two blind fact-sheet A/B rounds of 30 Oct
(17 filings, both card versions). Findings checked by the lead against the code (pass2.md:6, sectors.toml:72-73,
pipeline.py:1694-1699, grounding.py:288/495).

## What code checks
- Figures: every figure on the card must appear somewhere in the filing (grounding.check_card), but plain whole numbers of 31 or
  less are skipped ("5 USFDA observations", "29 Oct") and a figure counts as grounded anywhere in the filing, not on its own row.
- Quotes: what_happened facts and FILING insights are checked against their quote for figures only, never for words; a missing
  quote is logged, not dropped; insights with basis MEMORY or SECTOR get no quote check.
- Not checked at all, free text straight to the card: track_next (risks, catalysts, milestones, pending approvals),
  core_catalyst's words, notable_changes' "why", takeaway and headline words, SECTOR insights. No check compares the names on a
  card (companies, regulators, schemes, products) with the filing or memory.

## What the prompt does
- It already says "Use only facts in FILING TEXT and COMPANY MEMORY. Never invent numbers, dates, names or guidance" (pass2.md:6);
  the model ignores it where nothing checks.
- It invites outside knowledge: the sector lens lists each sector's KPIs and drivers (sectors.toml: pharma "USFDA status, ANDA
  approvals", aviation "passengers, load factor", NBFC "AUM"), the very items invented; notable_changes asks to compare "with what
  is normal for this sector"; SECTOR insights are free; track_next asks for risks and milestones with no source field.

## The 37 WRONG items by class
| Class | Count | Example | What would stop it |
|---|---|---|---|
| (a) outside knowledge, invented name or driver | 10 | Dalmia Bharat, Merino wool, MSEDCL, USFDA "5 observations", AUM | names and content words must be in the filing or memory |
| (b) invented date or event | 5 | earnings call 30 Oct, MCA approval, H2 approvals | dates must be in the filing or memory |
| (c) mislabelled line | 6 | total comprehensive income as net profit; associate share as discontinued | the label must match the quote's own row |
| (d) unsupported or wrong number | 7 | inventories from the wrong row; borrowings 0.28 not in the filing | a figure tied to its own quote or row |
| (e) other | 9 | growth contradicting the company's stated 19%; a cause the filing contradicts | basis and period checks; prefer stated growth |

## Fixes, smallest first (each behind a switch, on/off over stored cards plus a blind sample before it is live)
1. Support check for unchecked text: every name and content word of a risk, catalyst, milestone, approval, catalyst line,
   change "why" and SECTOR insight must appear in the filing or memory (not peer context); else the item is dropped.
   Prevents up to 15 of 37 (classes a and b). Risk: drops true paraphrase; lenient first (two or more missing words).
2. Small numbers and dates: a whole number of 31 or less beside a noun, and a day-month date, must appear in the filing or memory.
3. Prompt: "never use knowledge outside the filing and memory; every name and date must appear in them"; the sector lens becomes
   "what to look for in the filing; if it has none, say nothing"; track_next "only what the filing's words state"; drop "what is
   normal for this sector". Alone it is weak (the rule exists and is ignored); it supports 1.
4. Label check: "net profit", "to shareholders", "discontinued" on a figure need the same word on its quote's row.
5. Later, if 1 leaves misses: a quote on every risk, catalyst and milestone (schema and UI change).
