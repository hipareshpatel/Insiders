# Pass marks for the narrowed memory-grounding rule, set before any code (25 Oct 2026)

**The rule (owner approved, narrowed).**
- **This filing's figures** must be found in the filing, its headline, its subject or the scale block. These are the
  headline, takeaway, points, key numbers and notable changes. Memory no longer grounds them.
- **Memory** grounds figures only in a "why it matters" insight whose basis is MEMORY or BALANCE_SHEET, and in the
  track-next targets.
- Every other check keeps its sources.

**Population.** Every stored card on the live API whose filing PDF can be read. Each is re-checked with its filing's
PyMuPDF text and its memory view as of the filing date, with the rule off and on, and no AI.

**Review.** Every figure that the rule newly makes ungrounded is reviewed, or a random 150 if there are more. Each is
reviewed blind against the filing PDF, and the reviewer judges whether the figure is right for the claim it sits in.

**Accepted only if both hold:**
1. At least 80% of the newly ungrounded figures are WRONG for their claim (a figure from another period, an invented
   figure, a misread), with the lower 95% Wilson bound at 65% or above.
2. The number of cards newly held, or sent to review, is reported. If it exceeds 5% of the cards checked, the result
   goes to the owner before shipping.

**Otherwise** the rule is not shipped as it is.

**Limit.** Production reads with OCR as well, and this measurement reads only the text layer. On scanned filings it
therefore over-counts ungrounded figures. Cards whose PDF has no text layer are excluded and counted.
