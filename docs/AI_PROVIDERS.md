# AI providers: what each is for, its limits, what was measured (2026-10-19)

The steady state costs $0: free tiers only (DeepSeek's prepaid key is off in free mode, `FREE_ONLY=1`; OpenRouter only
`:free` models). Limits are as configured in `pipeline/config/providers.toml`; "measured" means from our own runs or the
provider's own 429 detail, "assumption" otherwise (CLAUDE.md rule 0).

| Provider | Model | Free limit | Used for | Measured |
|---|---|---|---|---|
| Google Gemini | 3.6 / 3.7 / 3.8 Flash | 20 requests a day each, 5 a minute (measured: Google's 429 detail, `GenerateRequestsPerDayPerProjectPerModel-FreeTier` 20) | packed cards (6 filings a request), long documents | round 6: 3 WRONG of 55 published (5.5%); arm B: 3.7 Flash 0 of 33 |
| Google Gemini | 3.5 Flash, 3 Flash preview | 20 a day each (3.5 measured by 429 detail; preview assumption) | packed cards, after the three above | new: round 7 measures |
| Google Gemini | 3.5 Flash Lite | 500 a day (measured: AI Studio Rate Limit page, owner, 2026-10-19), 15 a minute | pass 1; last in the packed rotation | probed right; round 7 measures |
| Google Gemini | 3.1 Flash Lite | 500 a day (measured: AI Studio Rate Limit page, owner, 2026-10-19), 15 a minute | pass 1, vision | probed right |
| Google Gemini | 3.1 Pro, pro-latest, Gemini 4 Argon, Omni Flash, Omni 1.1, Deep Research, Computer Use | **0 on the free tier** (429 at once) | - | probed 2026-10-19 |
| Google Gemini | 2.0 / 2.5 Flash, 2.5 Pro, 2.5 Flash Lite | retired for new users (404) | - | probed |
| Mistral | Ministral 8B | 150 a minute, 625k tokens a minute | pass 1 workhorse | 2,505 requests in 2 days, 11 failures |
| Groq | gpt-oss-20b | 1,000 a day, 8k tokens a minute | pass 1 | small prompts only |
| Z.AI | GLM-4.5 Flash | one request at a time | pass 1, cards (regular route, second opinions) | round 5: 3 WRONG of 32 (9%); round 6: 0 of 3 |
| Z.AI | GLM-4.7 Flash, GLM-4.6V Flash | one at a time | vision (4.6V) | GLM-4.7 off card routes (round 6: 1 of 1 WRONG; 179 429s in 2 days) |
| NVIDIA | Nemotron 3 Super | no stated daily limit, ~40 a minute | off card routes | round 6: 12 of 36 WRONG (33%) |
| NVIDIA | DeepSeek V4.1 Flash, GLM-5.3, Kimi K2.6, GLM-5.3 Flash | listed | - | probed: timeouts, 404 (Kimi), 10x unit slip (GLM-5.3 Flash) |
| OpenRouter | Nemotron 3.5 Super VL (free) | 1,000 a day for all free models together, 20 a minute | cards (small share), long documents (after Gemini) | round 6: 1 of 6 WRONG; **240 failures in 573 requests** (empty answers) |
| OpenRouter | MiniMax M3.1 Flash, Gemma 4 31B (free) | inside the same 1,000 a day | off card routes | evening trial: 16 empty answers (MiniMax), 28 429s (Gemma) |
| Cloudflare | Llama 3.3 70B, 3.1 8B | 10k neurons a day | spares | small context |

| SambaNova | Gemma 4 31B | free tier: 20 a minute, 20 a day, 200k tokens a day per model (docs.sambanova.ai rate limits, read 2026-10-19) | not used yet (a 20-a-day spare at most) | probed right in 2.2 s |
| SambaNova | DeepSeek V3.1 / V3.2, gpt-oss-120b, Llama 3.3 70B | listed at 20 a day free, but this account gets **402 PAYMENT_METHOD_REQUIRED** (V3.1 timed out) | - | probed 2026-10-19 |
| SiliconFlow | 80 models, nearly all billed per token (L0 tier 1,000 a minute is a paid-use rate, not a free allowance) | free only for small models | - | Qwen3 8B right but 25 s; Qwen2.5 7B 100x unit slip (probed 2026-10-19) |

**"Google 1,500 a day"** was the free tier of the older Gemini 1.5 and 2.0 Flash, which are retired; today's Flash models
are 20 a day each by Google's own 429 detail. Lite models are 500 a day each (AI Studio Rate Limit page, 2026-10-19).

## The combination (2026-10-19)

- **Pass 1 (is it news?)**: Mistral Ministral 8B, Groq gpt-oss-20b, Gemini 3.1/3.5 Flash Lite. Cheap, fast, plenty of quota.
- **Cards**: packed Gemini Flash (3.6, 3.7, 3.8, then 3.5 and 3 Flash preview, then 3.5 Flash Lite): about 500 cards a day
  for a daily need of about 120 card requests (measured from arm B), so the daily run has headroom.
- **Long documents** (transcripts, annual reports): Gemini 3.6 Flash first (1M-token window), then Nemotron 3.5 Super VL.
- **Fallbacks and second opinions**: GLM-4.5 Flash (the best measured non-Gemini writer), Nemotron 3.5 Super VL (small
  share: it fails often under load).
- **Off card routes**: Nemotron 3 Super, GLM-4.7 Flash, MiniMax, Gemma (quality or supply).
- **When every writer is out**: the filing stays queued with no attempt spent and is written after Gemini's reset
  (12:30 IST).

Each round reports WRONG per writer; a writer above about 8% comes off the card routes.
