# Backfill readiness: free tiers, the investable universe, and backfill time (2026-10-18)

M = measured, A = assumed. Sources: round-2 run `backfill-companies-20261018-1024.log` (finished, PARTIAL) plus the 8 requests of the crashed `-1018` run; the D1 `filings`/`cards`/`provider_usage` tables; `providers.toml`.

## 1. AI requests and tokens per filing (round 2: 14 companies, 322 filings, M)

- **Total: 663 AI requests, 2.06 per filing; 6.87 M input / 1.03 M output tokens, about 21.3k in and 3.2k out per filing** (the coordinator's figures; my count of HTTP lines is 691 including 23 x 429 and 5 x 5xx).
- How the 322 filings ended (D1): 49 exact or near duplicates (no AI call); 104 rejected by pass 1; 13 timeline-only; 131 cards; 14 not material at pass 2; 1 failed.
- Requests by stage. The logs do not label stages, so I split them by route membership and D1 outcomes:

| Stage | Requests | Per filing | Basis |
|---|---|---|---|
| Pass 1 | ~144 | 0.45 | PASS1-route filings minus exact duplicates (M) |
| Timeline | ~23 | 0.07 | TIMELINE-route filings minus exact duplicates (M) |
| Repeat check, plus pass-1 repairs and retries | ~120 | 0.37 | Residual of 287 pass-1-route successes (ministral-8b 282, Groq 1, Flash-Lite 4). Only the 8 positive repeat checks are logged (inferred) |
| Pass 2 (first reply) | 145 | 0.45 | 131 cards + 14 not material (M) |
| Second opinion | 58 | 0.18 | 42 UNRESOLVED + 16 CORRECTED in `card_json.review` (M). That is **44% of cards**; the run's stats say 87 of 185, or 47% |
| Pass-2 repairs, empty replies, failovers | ~190 | 0.6 | Pass-2-route HTTP (DeepSeek 134, NVIDIA 148, OpenRouter 39, Z.ai ~70) minus the two lines above (inferred). OpenRouter VL returned empty replies 12 times, and its breaker opened 3 times |
| Vision | ~10 | 0.03 | glm-4.6v and mistral-small, almost all 429s. RapidOCR read 537 pages on the CPU (M) |

- Tokens. Pass-1-route calls are about 1.4k tokens (ministral-8b: 580,720 / 426, M). Pass-2-route calls are about 23k in and 2.6k out (Nemotron: 9.0 M / 389, M). **Pass 2 is about 95% of the tokens and almost all the wall-clock time.**

## 2. Throughput and 429s (M)

- **165 filings an hour with 5 workers** (322 in 1.95 h). DeepSeek was 1/3 of pass-2 requests and wrote 41% of the cards.
- **429 share: 3.3%** (23 of 691). Z.ai accounts for 17 (code 1305, overloaded) and mistral-small vision for 5. Other recent re-runs were 2.8–6.5%.
- No daily ceiling was reached. No model was retired for the day.

## 3. Daily free capacity per route (providers.toml x 0.95)

| Route / model | Daily cap | Filings a day at the measured use |
|---|---|---|
| Mistral (all models) | 1B tokens a month = 31.7 M tokens a day | ~24,000 (1.3k tokens a filing) |
| ministral-8b | 150 RPM | not binding |
| Groq gpt-oss-20b | 950 RPD, 190k TPD | ~135 calls (**TPD binds**, a spare in practice) |
| Gemini Flash-Lite x2 | 475 RPD each (unconfirmed) | spare |
| Gemini 3.6 Flash | 19 RPD | spare |
| Workers AI | 150k / 60k TPD | 2–3 pass-2 calls |
| OpenRouter free models | 950 RPD shared | 0.12 a filing, so ~7,900 filings (~4,700 without DeepSeek) |
| NVIDIA Nemotron Super | 40 RPM, **no daily cap configured** | bound by latency (23–68 s a reply) |
| Z.ai GLM-4.5/4.7 | 60 RPM, **concurrency 1**, no daily cap | ~40 s a reply, so ≤ ~2,000 calls a day, serialised |

**Which binds first:** no daily token or request quota. The limit is **wall-clock throughput**: Nemotron latency, one GLM request in flight at a time, and 5 workers on one laptop. Among daily caps, OpenRouter's 950 would bind next, at about 4,700–7,900 filings a day, which is above what the laptop can process. Nemotron has no configured daily limit, so its real free-tier ceiling is the biggest unknown (A).

## 4. Live flow and backfill

Volume: 2,894 companies x 7.5 filings a month = **21,700 a month, or ~720 a day** (A: the rate comes from 14 companies, large-cap heavy, so small caps likely file less).

Throughput without DeepSeek is **~130 an hour (A)**. Moving DeepSeek's third of the pass-2 calls to Nemotron and GLM adds about 15–25 s a filing per worker (109 s becomes ~125–135 s).

**Live (must be $0 under the rules, so no DeepSeek):** 720 / 130 = **5.5 h a day** (4.4 h if DeepSeek were allowed). Free-tier use is about 1 day of quota per day: Mistral ~0.9 M of 31.7 M tokens, OpenRouter ~90–145 of 950. A results season at 2–3x volume needs **11–17 h a day**. It fits, with little room.

**Backfill from 2025-01-01 (21.5 months):** 21,700 x 21.5 = **466,700 filings**. Each day of running costs one day of quota at most, because no daily cap binds.

| Scope | Filings | With DeepSeek (165/h) | Free only (130/h) |
|---|---|---|---|
| Full universe, 21.5 mo | 466,700 | 2,830 h = **118 days** at 24 h | 3,590 h = **150 days** |
| Rs 1,000–10,000 Cr band (983) | 158,500 | 960 h = 40 d | 1,220 h = 51 d |
| >= Rs 1,000 Cr (1,562) | 251,900 | 1,530 h = 64 d | 1,940 h = 81 d |
| Full universe, 12 months | 260,500 | 1,580 h = 66 d | 2,000 h = 83 d |
| Full universe, 6 months | 130,200 | 790 h = 33 d | 1,000 h = 42 d |

All rows are full 24-hour days with the laptop awake. The live flow needs 4–6 of those hours each day, so the backfill gets about 18–20.

DeepSeek cost: 0.42 requests a filing x $0.0032 a request (D24: $6.10 for 1,889 requests, off-peak) = about **$600 for the full backfill** at weight 3, against about $200 for the 1,000–10,000 Cr band (A: the D24 price per request).

## 5. What would make it fit

1. **Throughput, not quota, is the lever.** At 3.3% 429s with no daily cap reached, try 8 workers on a 1-day A/B (D18 allows going back). Gain A: up to ~1.5x, limited by GLM's concurrency of 1.
2. **Fewer second opinions:** they are 0.18 requests a filing plus their share of repairs, and ~23k tokens each. Dropping them or tightening the trigger cuts pass-2 calls by ~29%, for about **+25% throughput (A)**. That cost must be weighed against the 16 cards they corrected.
3. **Cut wasted calls:** ~0.6 pass-2 requests a filing are repairs, empty replies or failovers. Demoting OpenRouter VL (27 failures today) to a spare would recover part of that.
4. **Narrower first:** the Rs 1,000–10,000 Cr band in 40–51 days, then >= 10,000 Cr (579 companies, ~93k filings, ~24–30 days), then small caps last or with a shorter history.
5. **Shorter history:** 12 months for the full universe takes 66–83 days, and 6 months for small caps.

**Verdict:** on free tiers the live flow fits, with about 5.5 h a day of running. The full 21.5-month backfill does not fit in any reasonable time: 4–5 months of continuous running on one laptop. A band-first order with a 12-month cap for small caps brings it to about 2–3 months.
