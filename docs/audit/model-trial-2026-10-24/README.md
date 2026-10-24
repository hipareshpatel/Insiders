# Model trial, 24 Oct 2026 (owner: Gemma 4 on OpenRouter; Nemotron's empty answers)

Named models on 5 stored filings (order win, NCD, capex, subsidiary investment, investor deck), local sink, nothing
published (`scripts/model_trial.py`, providers-check `trial_models`; runs 12-14 on 14750e7). No company memory in the
trial, so missing history is not counted against a card.

| Model (host) | Level 1 | Card writing | Blind review |
|---|---|---|---|
| Gemma 4 26B (Google, Gemini key) | 5 of 5 answered | - | - |
| Gemma 4 31B (Google, Gemini key) | - | 1 server error, then 429 on 4 (card-sized prompts) | - |
| Gemma 4 26B / 31B (OpenRouter free) | 429 on 5 of 5 ("rate-limited upstream") | not reached | - |
| Nemotron 3.5 Super VL (OpenRouter free), thinking off | (normal level 1) | 5 of 5 written, no empty answer, 12-68 s | 2 RIGHT, 1 MINOR, 2 WRONG: 1.2 crore shares read as 12 crore; an FY26 cash-flow column read as H1FY26; event types off on both |

OpenRouter key (`/api/v1/key`): `is_free_tier` false (credits bought 16 Oct), usage 0, so the 1,000 free requests a day
already apply.
