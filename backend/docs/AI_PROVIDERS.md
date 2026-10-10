# AI provider architecture

RealEstateGPT talks to AI providers through one gateway (`app/ai/gateway.py`).
Providers are adapters behind a single interface, tried in a configured order,
with bounded retries, a circuit breaker and a per-request cost guard.

Nothing in this file, in the code, or in the logs ever contains a credential.

## Verified provider status

Status below was verified live with minimal-cost probes (`maxOutputTokens` /
`max_tokens` of a few dozen, or `max_tokens: 8` for the cheapest chat call) on
the current keys. A model is listed as usable **only** if a real call returned
HTTP 200 with usable content.

| Provider | Model | Chat | Tool calling | Structured output | Tier | Notes |
|---|---|---|---|---|---|---|
| Groq | `qwen/qwen3.8-27b` | yes | yes | yes | free | Primary. Fastest verified (≈0.4–1.5 s). |
| Groq | `openai/gpt-oss-120b` | yes | yes | yes | free | Strongest reasoning; needs ≥2000 output tokens (it thinks first). |
| Gemini | `gemini-2.5-flash` | yes | yes | yes | free | Fallback. A thinking model: needs ≥256 output tokens. |
| Gemini | `gemini-2.0-flash` | — | — | — | — | **Retired by Google** (HTTP 404). Do not use. |
| OpenAI | `gpt-4o-mini` | no | no | no | paid | Key is valid (models list returns 200) but the account has **no credits**: every completion returns HTTP 429. Skipped unless `AI_ALLOW_PAID_FALLBACK=true`. |

Free-tier limits observed:

* **Groq free tier** — works, but rate limited under load; repeated calls in
  quick succession return 429. Single requests succeed reliably.
* **Gemini free tier** — works, and rate limits per minute. `gemini-2.5-flash`
  spends part of its output budget on internal reasoning, so a small
  `maxOutputTokens` returns empty text with `finishReason: MAX_TOKENS`. The
  adapter sets a `thinkingConfig` budget and a 256-token floor to prevent this.
* **OpenAI** — no credits, so no usable free quota. Left configured as a
  documented fallback and excluded by default.

## Selected order and why

```
PRIMARY    groq    qwen/qwen3.8-27b        free, fastest, verified tools + JSON
FALLBACK 1 gemini  gemini-2.5-flash         free, verified tools + JSON
FALLBACK 2 openai  gpt-4o-mini              paid, no credits -> skipped by default
```

Groq is primary because it is the only provider that is simultaneously free,
fast, and verified for **both** tool calling and structured output — the two
capabilities the grounded assistant requires. Gemini is the fallback because it
also supports both on the free tier. OpenAI is last because it costs money and
currently has no balance.

The order is configuration, not a hardcoded ranking: set
`AI_PROVIDER_PRIORITY` to change it.

Capability-aware routing: the agent uses the `fast` tier by default. The
`complex` tier (`openai/gpt-oss-120b` on Groq, verified to correctly compute an
EMI where the fast model was approximate) is selected for reasoning-heavy work
and requires a larger token budget.

## How fallback works

One request flows through `AIGateway.chat()`:

1. Check the configured daily budget. Exhausted → `AIRateLimitError`.
2. Build the candidate list from `AI_PROVIDER_PRIORITY`, skipping:
   * providers with no credential,
   * providers whose circuit breaker is open,
   * providers that would cost money unless `AI_ALLOW_PAID_FALLBACK=true`,
   * providers a *completed* probe proved lack a required capability.
3. For each candidate: bounded retries (default 2 attempts) with exponential
   backoff plus jitter, under a global concurrency limiter.
4. Classify the failure:
   * **permanent** (400/401/403/404/422) → typed error immediately, no retry, no
     fallback (a bad key will fail everywhere).
   * **transient** (429, 408, 409, 425, 5xx, timeout) → try the next provider.
5. All providers failed → `AIUnavailableError` naming what was tried. No
   response is ever fabricated.

A circuit breaker opens after `AI_CIRCUIT_FAILURE_THRESHOLD` consecutive
failures and stays open for `AI_CIRCUIT_COOLDOWN_SECONDS`, after which one trial
request is allowed through. A success resets the counter immediately.

## Grounding and data safety

* The gateway returns only what a provider produced. It never synthesises a
  listing, a price or a financial figure.
* All property data comes from MongoDB through the closed tool registry
  (`app/ai/tool_registry.py`). Tool inputs are Pydantic-validated; tool names
  that are not in the registry are rejected.
* EMI, affordability, yield and ROI are computed by deterministic functions in
  `app/finance/calculators.py`. The `calculate_affordability` tool resolves the
  asking price from `property_id` rather than trusting a model-supplied number.
* A failed AI response is reported as a failure. It is never replaced with a
  plausible-looking answer.
* Saving on a user's behalf always uses the authenticated user id taken from the
  session, never an id from the request or the model.

## Health endpoint

```
GET /api/v1/ai/providers/status      (any signed-in user)
POST /api/v1/ai/providers/probe      (admin only, forces a re-probe)
```

Returns configured providers, the selected primary, the fallback order, each
provider's verified capabilities, availability and cooldown, and aggregate
counters (requests, successes, failures, rate limits, timeouts, average latency,
tokens, estimated cost). It contains no credentials and no request content.

## Cost management

* `AI_DAILY_REQUEST_BUDGET` (0 = disabled) caps requests per UTC day per process.
* `AI_ALLOW_PAID_FALLBACK=false` (default) means a cost-incurring provider is
  never used automatically, even if it is configured and healthy.
* Estimated cost uses published per-million-token prices and is recorded per
  provider in the status endpoint. Free-tier models report 0.

## Configuration

All credentials are server-side environment variables in `backend/.env` (see
`.env.example` for the annotated list). Never create a `NEXT_PUBLIC_` variant.

```
AI_PROVIDER_PRIORITY=groq,gemini,openai
AI_ALLOW_PAID_FALLBACK=false
AI_MAX_ATTEMPTS=2
AI_RETRY_BASE_SECONDS=0.5
AI_RETRY_MAX_SECONDS=8.0
AI_CIRCUIT_FAILURE_THRESHOLD=3
AI_CIRCUIT_COOLDOWN_SECONDS=60
AI_DAILY_REQUEST_BUDGET=0
GROQ_API_KEY / GROQ_MODEL / GROQ_BASE_URL
GEMINI_API_KEY / GEMINI_MODEL / GEMINI_BASE_URL
OPENAI_API_KEY / OPENAI_MODEL / OPENAI_BASE_URL
```

A missing or invalid key disables that provider only. Unrelated features
(auth, search, market intelligence, finance) keep working; only the assistant
reports that no provider is available.

Settings validation errors are masked: a typo in `.env` produces an error that
names the setting but never echoes its value.

## Testing

* `tests/test_ai_provider_fallback.py` — 44 mocked tests: fallback order,
  retry limits, permanent vs transient classification, circuit breaker open and
  recovery, capability gating, paid-fallback refusal, all-providers-down, and
  the Gemini/OpenAI wire-format translation in both directions.
* `tests/test_groq_agent.py` — gateway contracts and grounded tool calls.
* `tests/test_ai_safety.py` — the closed tool allow-list and user scoping.
* `tests/test_ai_agent_grounding.py` — a scripted provider drives the real agent
  end to end against an in-memory catalogue.
* `tests/test_ai_provider_integration.py` — live checks, opt-in:
  `ALLOW_LIVE_DB_TESTS=1 pytest -m integration`.

No real quota is consumed by the failure-path tests.
