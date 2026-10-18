# Repeat cards: measurement and a narrow rule (read-only, 2026-10-18)

Working files are in this folder. `clusters.txt` lists every cluster. `rule.py` runs the proposed rule over every
SAST filing.

## 1. Measurement

There are 507 published cards. Same company, same type, within 3 days: **34 clusters, 82 cards**.

| Class | Surplus cards |
|---|---|
| **SAST disclosures of a transfer already in the feed**: SML 08-04 (Sumitomo 29(2), Isuzu 29(2), M&M 29(1), M&M 18(6) after the 08-01 completion); eMudhra 03-05 (Mythili 29(1), 29(2), 29(2)) | **6** |
| Open offer, manager's copy plus company's "received" intimation (Novartis DPS, draft LoF, LoF) | 3 |
| Order intimation plus press release (Magellanic x7, HEG "Revised Disclosure"; ORDER_WIN) | 8 |
| Other same-stage pairs (Prism ballot, Jubilant rectification, Novartis completion and directors, Magellanic objects, Heritage deck and transcript, CSB results) | 7 |
| **Separate events**: Prism's two orders under one headline "Update on ongoing litigation" 5 min apart; Bandhan ICRA vs Crisil, both "Update on Credit Ratings."; eMudhra's two acquisitions 4 min apart; Novartis SPA vs open-offer PA; daily tender counts | 0 |

What the measurement shows:
- **The model repeat check has never seen these cards.** The SML and eMudhra cards date from 2026-10-16. The model
  repeat check's first duplicate is logged at 10-18 02:45. Its prompt's "different party's position" clause would
  likely keep Sumitomo, Isuzu and M&M anyway.
- **The current checks drop real purchases.** JSL Overseas bought 9,97,696 shares on 09-19 and 8,61,553 on 09-22.
  Both were marked repeats of the 09-16 buy of 6,19,678 shares, though they were separate trades.
- **Headline, subcategory and timing alone cannot tell repeats from separate events.** Identical headlines minutes
  apart were different events. Any broad merge would drop real cards.

## 2. Signals that tell repeats apart before pass 2 (all 37 SAST filings)

- **Subcategory.** `Disclosures under Reg. 29/18(6)/10(6)/31`. Open-offer documents arrive under other subcategories:
  'Open Offer', 'Public Announcement-Open Offer', 'Open Offer - Updates', 'General'. So the draft LoF, LoF and opening
  at 26% and Rs 1,554.60 are outside the rule by construction.
- **Letter date.** This is the first date on page 1, written within 2 working days of the transfer. SML's letters
  say "August 01,2025"; BSE posted them on 08-04. A feed entry dated on or after the letter date was written after
  the transfer happened. SPA and open-offer entries predate it.
- **Share counts and 2-decimal percentages.** These matched eMudhra (1,27,50,000) and M&M 18(6) (58.96%). They did
  not match Sumitomo or Isuzu, because the 08-01 entries do not state their counts. For those two the filer's name
  must match.
- **Different share counts on both sides mean a different trade.** This is how JSL's purchases are told apart.

## 3. Rule `sast_echo` (no model call)

A filing is a duplicate of a timeline entry E when all of these hold:
1. The subcategory matches `^Disclosures under Reg\. (29\(1\)|29\(2\)|18\(6\)|10\(6\)|31)`.
2. E is 0-3 days earlier.
3. The letter date is found in `doc.first_page_text(2000)`, and E is dated on or after it.
4. E's summary contains either:
   - a share count or percentage from the opening, or
   - the headline's filer. The filer is the text after "for", without "& PACs/Others", the company's own name
     words or generic words. The initials of an "A & B" filer also count ("M&M").
5. If both sides carry share counts, at least one is shared.

**Where the code goes**
- Add a pure function in `dossier.py` beside `similar_timeline_entry`.
- Call it in `pipeline.py` `analyze()` before `_repeat_check` (line ~1795), on every route. Reason: "duplicate of X
  (SAST disclosure of a transfer already in the feed)".
- Also apply condition 5 as a guard in `_repeat_check` and the post-pass-2 `similar_timeline_entry`.

**Effect (37 SAST filings, re-run in filing order)**
- **6 cards merged.** Sumitomo and Isuzu by name; M&M 18(6) by 58.96%. M&M 29(1) matches only through the "M&M"
  initials clause: its opening lacks 58.96%, and "Mahindra" is the company's own word. eMudhra 14:08 by figure,
  16:43 by name.
- **No separate stage dropped.** WaveRise's 29(1) is kept: it is Novartis's first news of the completion. LIC, SBI MF
  x2, GQG, Adani and East Bridge are kept.
- **JSL's two purchases come back.**
- **Remaining risk.** Two transfers by one filer within 3 days, with letters on or before an entry naming them, and
  no share count on page 1. There is no case among the 37. A garbled scan with no letter date does nothing (fails
  safe).

**Left out on purpose:** the open-offer, order and other same-stage pairs. Each needs its own narrow key.

## 4. Test cases (real headlines)

Merge:
- "...Regulation 29(2)... for Sumitomo Corporation", letter "August 01,2025", posted 08-04. Entry 08-01: "SML Mahindra
  disclosed the termination of the Sumitomo-Isuzu shareholders' agreement..."
- "...Regulation 29(1)... for Mahindra & Mahindra Ltd". Entry: "M&M completed the purchase of 58.96% of SML Isuzu from
  Sumitomo and Isuzu..."
- "...Regulation 18(6)... for Mahindra & Mahindra Ltd". Same entry, matched on 58.96%.
- "...Regulation 29(2)... for Mythili Srinivasan", opening 1,27,50,000. Entry: "promoter Mythili Srinivasan acquired
  1,27,50,000 shares (15.40%)..."

Keep:
- "...Regulation 29(1)... for WaveRise Investments Ltd" (07-29). The DPS and LoF entries predate the letter.
- "...29(2)... for JSL Overseas Holding Ltd & PACs", 9,97,696 shares. Entry 09-16: "...open market purchase of 6,19,678
  shares".
- "Update on ongoing litigation" x2 (Prism): not SAST.
- "Kotak Mahindra Capital ... submitted to BSE a copy of Letter of Offer": subcategory 'General'.
