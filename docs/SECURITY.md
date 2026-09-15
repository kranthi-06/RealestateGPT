# Security Architecture

> **RealEstateGPT** treats security as a first-class production requirement.
> This document catalogues every security control, the threat it mitigates,
> and the module that implements it.

---

## Authentication

| Control | Implementation | Module |
|---------|---------------|--------|
| Password hashing | bcrypt via `passlib[bcrypt]` | `app/core/security.py` |
| Token format | JWT (HS256) via `python-jose` | `app/core/security.py` |
| Token expiry | Configurable (default 24h) | `ACCESS_TOKEN_EXPIRE_MINUTES` |
| Token transport | `Authorization: Bearer <token>` header only | `app/core/security.py` |
| Token storage | `localStorage` (frontend) | `src/lib/auth-context.tsx` |

### Design decisions

- **No cookies** — all auth is Bearer-token based, eliminating CSRF risk for
  API endpoints.
- **No `NEXT_PUBLIC_` secrets** — only `NEXT_PUBLIC_API_URL` is exposed to the
  browser.  All API keys (Groq, MongoDB, etc.) remain server-side only.

---

## Authorization

| Control | Implementation | Module |
|---------|---------------|--------|
| Role-based access | `get_current_user` / `get_current_admin` FastAPI deps | `app/core/security.py` |
| Admin self-protection | Admin cannot modify own account via admin API | `app/api/v1/admin.py` |
| Resource ownership | Saved properties/searches/comparisons scoped to `user.id` | `app/repositories/saved_repo.py` |
| Conversation ownership | Conversations scoped to `user.id` | `app/repositories/platform_repo.py` |

### Key principle

> Authorization is **server-side only**.  No frontend flag, role claim, or UI
> state ever bypasses backend permission checks.

---

## Input Validation

| Control | Implementation | Module |
|---------|---------------|--------|
| Request validation | Pydantic models on all endpoints | All API routes |
| Query param bounds | `Field(ge=0)`, `Field(le=...)`, `max_length` | Schemas |
| Search text | `re.escape()` for regex search, no raw `$` operators | `app/repositories/property_repo.py` |
| AI message length | `max_length=4000` on assistant input | `app/schemas/ai.py` |
| Search query length | `max_length=1000` on AI search | `app/schemas/ai.py` |
| File names/paths | Not yet applicable (document upload planned) | — |

---

## NoSQL Injection Prevention

MongoDB queries are built programmatically with typed Python dictionaries.
User input is never interpolated into query operators:

- Text search uses `re.escape(query)` to prevent regex injection
- No `$where`, `$expr`, or user-controlled `$` operators
- All IDs are integers (from `next_id()` counter), not user-controlled strings
- Pydantic validates all input before it reaches the repository layer

---

## Rate Limiting

| Limiter | Scope | Default | Module |
|---------|-------|---------|--------|
| General | Per IP, sliding window | 60 req/60s | `app/core/rate_limit.py` |
| Auth | Per IP, auth endpoints | 10 req/60s | `app/core/rate_limit.py` |
| AI | Per user ID | 12 req/60s | `app/core/ai_rate_limit.py` |

All limiters are process-local (in-memory sliding window). This is sufficient
for the current single-instance Vercel deployment. Swap to Redis-backed
limiting only when horizontally scaling.

---

## AI Security

### Prompt injection mitigation

1. **System prompt isolation** — system instructions are never mixed with user
   content in the same message.
2. **Anti-hallucination directive** — system prompt explicitly forbids inventing
   property facts, prices, IDs, coordinates, or calling unregistered tools.
3. **Untrusted data boundary** — user messages, property text, and tool output
   are treated as untrusted data, never as instructions.
4. **Closed tool registry** — only 9 pre-registered tools can be called; the
   registry rejects any tool name not in its allowlist.
5. **Bounded execution** — `MAX_AGENT_STEPS=3`, `MAX_TOOL_CALLS=5` prevent
   runaway agent loops.
6. **Grounding enforcement** — `_ground()` filters the final answer to only
   reference property IDs that appeared in actual tool results.
7. **No chain-of-thought leakage** — internal reasoning is never returned to
   the client.

### Tool authorization

- Tools that modify state (`save_property`, `save_search`) require
  authenticated user context.
- The tool registry validates input schemas before execution.

---

## Transport Security

| Control | Implementation |
|---------|---------------|
| HTTPS enforcement | HSTS header in production (`max-age=31536000`) |
| Content-Type sniffing | `X-Content-Type-Options: nosniff` |
| Clickjacking | `X-Frame-Options: DENY` |
| XSS | `X-XSS-Protection: 1; mode=block` |
| Referrer leakage | `Referrer-Policy: strict-origin-when-cross-origin` |
| GZip compression | Enabled for responses ≥ 1024 bytes |

---

## Secret Management

| Secret | Storage | Exposed to browser? |
|--------|---------|---------------------|
| `MONGODB_URI` | `.env` / Vercel env | ❌ Never |
| `GROQ_API_KEY` | `.env` / Vercel env | ❌ Never |
| `SECRET_KEY` | `.env` / Vercel env | ❌ Never |
| `GOOGLE_MAPS_SERVER_KEY` | `.env` / Vercel env | ❌ Never |
| `NEXT_PUBLIC_API_URL` | `.env` / Vercel env | ✅ Intentional (API base URL only) |

### Production validation

`Settings.validate_runtime()` checks at startup that:
- `SECRET_KEY` is not a placeholder outside development
- `MONGODB_URI` is configured
- `GROQ_API_KEY` is set outside development

---

## Observability & Audit

| Feature | Implementation | Module |
|---------|---------------|--------|
| Request correlation | `X-Request-ID` header (generated or honoured) | `app/core/middleware.py` |
| Structured logging | `request_id` attached to every log record | `app/core/logging.py` |
| Access logging | Method, path, status, latency for every request | `app/core/middleware.py` |
| Audit trail | All AI interactions logged to `audit_logs` collection | `app/repositories/platform_repo.py` |

---

## Error Handling

All errors return structured JSON with `{code, message}`.  Internal stack
traces and database details are never leaked to the client.

```json
{
  "code": "NOT_FOUND",
  "message": "Property 42 not found."
}
```

Error codes are defined in `app/core/errors.py` and handled by the global
exception handler in `app/main.py`.
