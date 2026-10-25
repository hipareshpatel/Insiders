# Pass marks for F123 and F124, set before any review (25 Oct 2026)

Owner, 25 Oct: one case or a handful proves nothing, so the checks are judged on every stored card.

**Population.** Every stored card on the live API on 25 Oct: 5,344 cards, of which 2,053 are results or call tables
dating back to Jan 2025.

**Reviewers.** Independent agents, each with the filing PDF. They are blind to the check's reason: each is given the
sentence or the comparative and asked whether it is right against the filing.

**F123 (a comparative against the stated change).** Every removed comparative is reviewed, or a random 120 if there
are more than 120. The check is accepted only if both of these hold:
- at least 80% of the removed comparatives are WRONG, with the lower 95% Wilson bound at 70% or above;
- at most 1 in 5 removals drops a RIGHT comparative.

**F124 (words against the card's own figures).** All 88 flagged sentences, on 73 cards, are reviewed. The check is accepted only if
at least 85% of them are WRONG, with the lower 95% Wilson bound at 75% or above.

**If a check fails.** It does not ship as it is. Either its rule is narrowed and it is re-measured on cards it has not
been tuned on, or it is dropped.
