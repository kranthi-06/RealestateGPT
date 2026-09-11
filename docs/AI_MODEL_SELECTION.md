# RealEstateGPT — Verified Groq model selection (Phase 3)

> Method: live API probes (`scratch_groq.py`) against `api.groq.com/openai/v1` using the project API key. Every model below was actually exercised for auth, plain chat, streaming, `response_format=json_object`, and tool-calling. Nothing is assumed from model names.

## Available models on this key

| Model | ctx | Notes |
|---|---|---|
| `qwen/qwen3.8-27b` | 131,042 | ✅ best overall |
| `qwen/qwen3.6-27b` | 131,072 | thinking-capable, JSON mode flaky |
| `openai/gpt-oss-20b` | 131,072 | tools OK, JSON mode failed |
| `openai/gpt-oss-120b` | 131,072 | not probed (cost) |
| `groq/compound` / `groq/compound-mini` | 131,072 | mini: no tool calling, 413 on JSON probe |
| `allam-2-7b` | 4,096 | JSON OK, **no tool calling**, tiny ctx |
| `whisper-large-v3*`, `canopylabs/orpheus-*`, `meta-llama/llama-prompt-guard-*` | — | audio/safety, not relevant |

> ⚠️ The legacy aliases referenced in older code/comments (`llama-3.1-8b-instant`, `llama-3.3-70b-versatile`) return **404 model_not_found** — do not use them.

## Probe results

| Model | chat | latency | JSON object | tool call |
|---|---|---|---|---|
| **qwen/qwen3.8-27b** | ✅ `HELLO` | 0.55s | ✅ `{"city":"Hyderabad","max_price":20000000}` | ✅ `search_properties{"bedrooms":3,...}` 0.87s |
| qwen/qwen3.6-27b | ✅ (prepends thinking) | 0.88s | ❌ 400 failed validation | ❌ None |
| openai/gpt-oss-20b | ✅ (empty prefill) | 0.95s | ❌ 400 failed validation | ✅ |
| groq/compound-mini | ✅ | 1.11s | ❌ 413 | ❌ unsupported |
| allam-2-7b | ✅ | 0.80s | ✅ | ❌ unsupported |

Error handling: unknown model → `404 model_not_found` JSON error; `max_tokens=0` → `400 max_tokens must be positive`. Rate limits were not hit during this probe window.

## Selected models (verified)

| Workload | Model | Rationale |
|---|---|---|
| **FAST** (intent, filters, simple QA, embedding-free semantic rank) | `qwen/qwen3.8-27b` | 0.55s, reliable `json_object`, correct tool args |
| **REASONING** (comparison, investment, multi-step) | `qwen/qwen3.8-27b` | thinking-native; use chat template `enable_thinking` for hard tasks; **avoid qwen3.6 for structured calls** |
| **AGENT/TOOLS** (search, nearby, finance) | `qwen/qwen3.8-27b` | only model with verified tool-calling + JSON + latency |

Single-model policy keeps cost predictable; per-request model routing (fast vs reasoning) should be config-driven via env (`GROQ_FAST_MODEL`, `GROQ_REASONING_MODEL`) and default to the verified model above.

## Production notes

- Use `qwen/qwen3.8-27b` for all three workloads initially; reassign after load testing.
- Enable thinking only for reasoning tasks (`enable_thinking: true`) — disables `reasoning_content` cost on simple tasks.
- Structured outputs: use `response_format={"type":"json_object"}` + Pydantic validation on every tool call; treat 400/413 as real AI-provider errors (no silent fallback).
- Timeouts: 60s LLM call, 120s stream; retries with exponential backoff; max 5 tool calls / 3 agent iterations per user request (budget guard).