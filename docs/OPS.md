# Operations log

One line per lead check-in (every 15 minutes since 2026-10-20, owner): time IST, health, what changed. Newest last.

| Time (IST) | Health | What changed |
|---|---|---|
| 20 Oct 05:51 | Pipeline run 1 (05:19) still running, 0 cards analysed in 25 min, queue at its 1,000 cap; Gemini's free quota out until 12:30 | PR #2 merged into main (b143a79): verified-face fixes, signals off on old cards, watch fix, page design, D39 High impact, refresh-card-blocks; pipeline every 15 min; check-ins every 15 min |
| 20 Oct 06:15 | Run 1 still going; queue at cap | Company page rebuilt to the approved design (agent, 344e2a5); cards to the approved design: old card body gone from List view, Results and low-impact rows, deal block without an amount, results table in the mockup order with lower-is-better colours and loss turns, repeat rules (agent); both verified here (24 site tests, build, screenshots) |
| 20 Oct 06:30 | Run 1 (05:19-06:00) **OK**: 33 analysed, 0 failed, 5 to review, 2,098 discovered (today + backfill 19-23 Apr), 741 dropped by rule, 1,168 queued; Gemini Flash-Lite packed + Mistral + Z.AI carried it (the larger Gemini models were out of quota). The System page showed no stats only because a run writes them at its end | PR #3 merged (company page, cards); next: the third live review on these production cards |
| 20 Oct 06:12 | No run since 06:00: the 15-min schedule had not fired yet (GitHub delays new crons); run 2 started by hand. Queue 1,000 (cap), 22 failed; Mistral carried 39 requests, 2 rate-limited on mistral-small and glm-4.6v | Live review 3 started: 7 blind reviewers on the 27 production cards, face errors marked apart |
| 20 Oct 06:45 | Run 2 going (started by hand); schedule watched | Live review 3 tallied: 7 of 27 production cards WRONG (26%; review 2 had 42% on old stock), all on the face; the cloud fixed deal stages (4 of 7 WRONG), trade-remedy signal, year-ago comparatives, turns, case ladder, capex size (0b6095d, f0093eb); laptop T24 for the rest |
