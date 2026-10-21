# Reworded quotes answering to the filing's lines or memory: tried and reverted (2026-10-21)

**The proposal** (owner said yes, 21 Oct): a key number, notable change or "why it matters" point whose quote is not
the filing's own words passes when each of its figures is on a filing line naming it, or is in company memory.

**On/off replay:** `pipeline/scripts/held_onoff/quote_sources.py`, no AI. It was run over this morning's held export
(`docs/audit/live/held-2026-10-21.json`, 328 cards):
- 107 cards were held only for this reason.
- 104 had readable PDFs.
- The rule released 7 of them.
- The replay has no XBRL block and no memory, so it under-counts.

**Independent blind review** of the 7 (`held_release_review.json`): **2 RIGHT, 3 MINOR, 2 WRONG (29%)**.
- **Bharat Electronics:** an order-book ratio from memory ("over double its order book") that the filing does not support.
- **Ceigall:** standalone EBITDA and margin labelled as consolidated.
- **Two of the MINOR cards** also carried claims from memory that the filing cannot confirm.

**Decision:** reverted. The go-live bar is 5% WRONG, and a held card's quote failure often travels with another fault
the quote check was the only thing catching.

**What is left, as the owner's queue:**
- Held cards stay in the owner's queue (Feed → "Held for review only", verdict bar).
- The next attempt should label memory figures on the card itself and check them against the dossier entry they cite
  (date and filing), not loosen the filing check.
