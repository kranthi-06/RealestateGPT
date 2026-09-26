# RealEstateGPT — Production Activation Status

> **Date**: 2026-09-26 (supersedes the 2026-09-25 session, which stopped at
> the same credential boundary after installing `flyctl` v0.4.107 and
> validating the first version of the deployment package)
> **Scope**: complete the external deployment and production activation of the
> autonomous web-discovery engine on the existing public deployment
> (`https://realestate-gpt-inky.vercel.app`), from
> `PRODUCTION READY — EXTERNAL INFRASTRUCTURE CONFIGURATION REQUIRED` to
> `PRODUCTION VERIFIED`.
> **Method**: live read-only probing of the deployed production site, direct
> credential probing of every candidate host, local Docker validation of the
> real production image, the full backend/frontend regression suites, and a
> real defect fix in the deployment package (no discovery-logic changes beyond
> the transport-header extension the previous README already sanctioned).

---

## 1. FINAL STATUS

**PRODUCTION READY — EXTERNAL INFRASTRUCTURE CONFIGURATION REQUIRED**

`PRODUCTION VERIFIED` is deliberately **not** claimed. The production
deployment is reachable and healthy, but autonomous web discovery is disabled
there (`provider_status: "disabled"`, verified live) because (a) no public
HTTPS SearXNG instance exists yet and (b) the Vercel environment cannot be
changed without an authenticated principal. Both require credentials that do
not exist in this environment — verified by direct probing, not assumed:

| Blocker | Direct evidence (2026-09-26) |
| --- | --- |
| **Fly.io account / token** | `flyctl auth whoami` → `Error: no access token available. Please login with 'flyctl auth login'`. `FLY_API_TOKEN` / `FLYCTL_ACCESS_TOKEN` absent from the environment. |
| **Vercel account / token** | `vercel whoami` → `Logged out.` `VERCEL_TOKEN` / `VERCEL_ORG_ID` / `VERCEL_PROJECT_ID` absent; no `.vercel/` directory in the repo. |
| **Alternative hosts** | `RENDER_API_KEY`, `RAILWAY_TOKEN`, `RAILWAY_API_TOKEN` absent. No VPS credentials present. |

Exact remaining user actions are in §6.

---

## 2. Live production state (read-only probes, 2026-09-26)

| Probe | Result |
| --- | --- |
| `GET https://realestate-gpt-inky.vercel.app/` | **200** |
| `GET /api/v1/health` | **200** — `{"status":"healthy","service":"RealEstateGPT API","version":"1.3.0"}` |
| `GET /api/backend/api/v1/health` | **200** — same payload: the Vercel multi-service rewrite routes `/api/backend/*` to the FastAPI service. Frontend→backend architecture verified live, no localhost dependency (matches `frontend/src/lib/api-base.ts` production resolution to same-origin `/api/backend`). |
| `POST /api/v1/search/autonomous` (anonymous, "Find 2BHK apartments for rent in Hyderabad under 35000") | **200**; `parsed` correct (`city=Hyderabad`, `category=PROPERTY_RENT`, `bedrooms=2`, `max_price=35000`); `metadata.provider_status="disabled"`, `web_message="Web discovery is disabled by the platform configuration."`, `web_discoveries=0`, `verified_properties=0` — the honest disabled state, never a fabricated listing. |
| `GET /api/v1/workers/cron/inventory` (no secret) | **401** `{"detail":"Invalid cron authorization."}` |
| `GET /api/v1/workers/cron/inventory` (`Authorization: Bearer wrong-secret`) | **401** — same. Cron auth rejects missing and invalid secrets in production. |
| `GET /api/v1/workers/status` | **200**; `web_search_provider: {provider:"searxng", configured:true, enabled:false}`, `property_provider_configured:false` with the honest provider message; `location_provider:"osm"`. No secrets in the response body. |

Interpretation: the production backend already carries
`WEB_SEARCH_PROVIDER=searxng` but discovery is **disabled** —
`WEB_DISCOVERY_ENABLED` and a public `SEARXNG_BASE_URL` (+ the new
`SEARXNG_AUTH_TOKEN`, §3) are not set in the Vercel environment, and only an
authenticated Vercel principal can set them.

## 3. Real defect found and fixed in the deployment package

The committed package claimed `server.limiter: true` provides production rate
limiting. Validation of the **real image** proved that false, and worse:

1. SearXNG's limiter is **inert without a Valkey/Redis datastore** — the image
   ships none (`ERROR:searx.limiter: The limiter requires Valkey` on boot).
2. With a Valkey actually attached (verified in Docker: `valkey/valkey:8.1` +
   `SEARXNG_VALKEY_URL`, connection confirmed via `valkey-cli client list`),
   the limiter **breaks the platform's own backend**: `format=json` traffic is
   capped at `API_MAX = 4` requests/hour/IP
   (`searx/botdetection/ip_limit.py`), bot user-agent regexes 429 non-browser
   clients, and browser-imitating clients without link tokens are throttled
   after 2 requests per burst window. Observed live in the smoke test: first
   headless request → **429**, browser-header request → **302** token
   challenge.
3. SearXNG's stock entrypoint does **not** substitute `SEARXNG_SECRET` —
   the secret works only because SearXNG's settings layer maps
   `server.secret_key` → `SEARXNG_SECRET` natively
   (`settings_defaults.py:219`); docs corrected.

Fix implemented (infrastructure + the sanctioned transport-header extension;
**no discovery logic changed**):

- **Token-authenticated Caddy edge inside the production image**
  (`infra/searxng/Caddyfile`, `docker-entrypoint.prod.sh`, `Dockerfile.prod`):
  every request except `/healthz` requires
  `Authorization: Bearer $SEARXNG_AUTH_TOKEN`; SearXNG/Granian is moved to
  `127.0.0.1:8081` (loopback-only, verified via `netstat` inside the
  container); the container **refuses to start** without the token
  (fail-closed, verified). This satisfies "restricted access" — stronger than
  the previous posture — without the self-DoS of the built-in limiter.
- **`settings.production.yml`: `limiter: false`** with a comment explaining the
  `API_MAX=4/h` incompatibility, so nobody re-enables it blindly. Rate limiting
  remains enforced platform-side by the backend's verified web-search limiter
  (global RPM floor, per-user limits, concurrency cap — production report
  §1.9).
- **Backend**: new `SEARXNG_AUTH_TOKEN` setting (`backend/app/core/config.py`,
  documented in `backend/.env.example`); `SearXNGSearchProvider.search` sends
  `Authorization: Bearer <token>` **only when configured** (local dev and all
  existing tests unaffected) and maps 401 to a clear auth-misconfiguration
  error instead of a generic HTTP failure. Two new tests added.
- **`fly.toml`**: health check moved `/` → `/healthz` (the only
  unauthenticated route); secret/deploy comments corrected.
- **`infra/searxng/README.md`**: security posture, deploy commands, Vercel
  variable contract (`SEARXNG_AUTH_TOKEN` row) and verification curls
  (401/200/healthz) updated to reality.
- A Valkey companion app was prototyped (`fly.valkey.toml`) and **removed**
  after the limiter proved incompatible — no dead infrastructure left behind.

### Local Docker validation of the fixed package (all on the real image)

| Step | Result |
| --- | --- |
| `docker compose -f infra/searxng/docker-compose.yml config -q` | exit 0 (one benign obsolete-`version:` warning) |
| `docker build -f infra/searxng/Dockerfile.prod …` | exit 0 |
| Boot without `SEARXNG_AUTH_TOKEN` | exits immediately: `FATAL: SEARXNG_AUTH_TOKEN is not set; refusing to start unprotected.` |
| `GET /healthz` (no token) | **200** `OK` |
| `GET /search?format=json` (no token / wrong token) | **401** |
| `GET /search?format=json` (valid token) | **200** — 35 real results, first `https://www.99acres.com/2-bhk-flats-for-rent-in-hyderabad-ffid` |
| Internal bindings (`netstat` in container) | granian `127.0.0.1:8081` only; caddy `:8080`; caddy admin `127.0.0.1:2019` |
| `SearXNGSearchProvider.search()` against the token-protected instance (real backend code path) | 5 normalized real results (99acres, nobroker, squareyards) |
| Same provider with a wrong token | `WebSearchInternalError: SearXNG rejected the request (HTTP 401)…` — never results |

## 4. Regression suites (2026-09-26)

| Suite | Result |
| --- | --- |
| Backend `pytest -q` (pre-change baseline) | **190 passed** in 100 s |
| Backend `pytest -q` (after all §3 changes) | **192 passed** in 111 s (190 baseline + 2 new SearXNG auth tests) |
| Frontend `npm run lint` | 0 errors (1 pre-existing `<img>` warning) |
| Frontend `tsc --noEmit` | exit 0 |
| Frontend `npm run build` | OK, 15 routes |

Playwright Chromium E2E was green against the live production URL in the
2026-09-25 session; nothing in this session touched frontend code.

## 5. Repository safety

- `git status --porcelain`: only the intended changes (this doc, the infra
  package, the guarded backend token support, the two new tests).
- `vercel.env` (root + frontend) confirmed gitignored (`.gitignore:37`);
  `backend/.env` and `frontend/.env.local` confirmed gitignored.
- No secret values in any committed file: `settings.production.yml` keeps the
  public `CHANGE_ME` placeholders; tokens are runtime-injected
  (`SEARXNG_SECRET`, `SEARXNG_AUTH_TOKEN` via `flyctl secrets` /
  `vercel env`).

## 6. Exact remaining user actions (the only blocked steps)

1. **Authenticate Fly.io** (one-time): `flyctl auth login`.
2. **Deploy SearXNG** per `infra/searxng/README.md` §3:
   `cp infra/searxng/fly.toml infra/searxng/fly.toml.local`, set a unique app
   name, `flyctl apps create <app-name>`,
   `flyctl deploy -c infra/searxng/fly.toml.local`, then
   `flyctl secrets set SEARXNG_SECRET="$(openssl rand -hex 32)" SEARXNG_AUTH_TOKEN="$(openssl rand -hex 32)"`
   and `flyctl apps restart <app-name>`. Verify with the three curls in
   README §5 (401 unauthenticated, 200 with token, `/healthz` OK).
3. **Authenticate Vercel** (one-time): `vercel login`.
4. **Set the production environment** on the existing project
   (`realestate-gpt-inky` — do not create a new project):
   `WEB_DISCOVERY_ENABLED=true`, `WEB_SEARCH_PROVIDER=searxng`,
   `SEARXNG_BASE_URL=https://<app-name>.fly.dev`,
   `SEARXNG_AUTH_TOKEN=<same token as step 2>` (README §4 has the full
   contract). Never any of these as `NEXT_PUBLIC_*`.
5. **Redeploy**: `vercel --prod` or push `main`.
6. **Then the acceptance runs become possible** (agent-executable once the
   above exist): the three production queries (§8–10 of the master checklist),
   cache-hit double-run, DB persistence checks, frontend verification, and the
   `PRODUCTION VERIFIED` certification.
