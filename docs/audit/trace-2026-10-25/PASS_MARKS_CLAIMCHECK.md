# Pass marks for the claim-check trial (MiniCheck, HHEM), set before running (25 Oct 2026)

The owner approved the trial after the results-table measurement. It is read-only and costs $0: the models run on CPU,
and nothing in production changes.

**Models.**
- `lytang/MiniCheck-Flan-T5-Large` (MIT).
- `vectara/hallucination_evaluation_model`, HHEM-2.1-Open (Apache-2.0, on Flan-T5 Base).

**Sentences.**
- WRONG: the writer-stage wrong points of the trace whose sentence can be recovered from the card, plus the 8 WRONG
  sentences of the check-B review.
- RIGHT: the 80 sentences that the check-B review found RIGHT.

Each sentence is scored against its own filing's PyMuPDF text, split into chunks. The sentence's score is its best
chunk score.

**Flag rule, fixed now.** A sentence is flagged when its best support score is below 0.5, which is each model's
documented decision point.

**A model is accepted for a shadow run only if both hold:**
1. It flags at least 50% of the WRONG sentences, with the lower 95% Wilson bound at 35% or above.
2. It flags at most 10% of the RIGHT sentences, with the upper 95% Wilson bound at 20% or below.

No threshold is tuned on these sentences. A model that fails is dropped. A model that passes goes to a shadow run on
new cards: it records a flag but changes no card.
