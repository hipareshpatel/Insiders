# Shadow critic scored against the blind review, 24 Oct 2026

The critic export (`critic-2026-10-24.json`, 31 cards) against the independent blind reviewers' verdicts in
`2026-10-23-audit.json` and `2026-10-24-audit.json`. The two sets share 22 cards. The critic never saw the verdicts,
and the reviewers never saw the critic.

| | Critic | Blind reviewers | Agree |
|---|---|---|---|
| Points flagged | 23 (on 8 cards) | 16 faults on 11 cards | 2 (Jyoti Structures' TTM-revenue takeaway, ONGC's "governance gap") |
| Precision (critic flags the reviewers confirm) | 2 of 23 = **9%** | | |
| Recall, all faults | 2 of 16 = **12%** | | |
| Recall, faults on the lines the critic reads (headline, takeaway, what happened, why it matters) | 2 of 5 = **40%** | | |
| Card-level precision / recall | 4 of 8 = 50% / 4 of 11 = 36% | | |
| WRONG cards (Shree Cement's mixed-basis EBITDA, Newgen's SaaS growth from the wrong column) | 0 of 2 flagged | | |

**Reading:**
- 21 of 23 flags are false.
  - STL Tech (5) and SKM Egg (5) were marked INVENTED or WRONG_PERIOD where the figures sit in the filing outside the excerpt the critic was given.
  - Park Hospitality's 5 flags question a scope the filing states.
- 11 of the reviewers' 16 faults sit in blocks the critic does not read:
  - results tables;
  - case_stage;
  - key numbers;
  - track-next.
- **Decision:** the critic stays in shadow mode, the same as on 22 Oct. Point precision is 9% (22 Oct: 12%). It would need the whole filing, not the excerpt, before its INVENTED verdicts could mean anything.
