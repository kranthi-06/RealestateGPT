# SearXNG Deployment Guide (RealEstateGPT)

RealEstateGPT's web discovery provider (`WEB_SEARCH_PROVIDER=searxng`) talks to a
self-hosted SearXNG instance over its JSON API. This directory holds the local
development compose file and the **production deployment package**
(`Dockerfile.prod`, `settings.production.yml`, `fly.toml`).

Production requires a separately deployed, externally reachable HTTPS instance —
the exact steps are in §3. Nothing in production may depend on this (or any)
developer workstation staying on.

---

## 1. Local development (this machine)

```bash
docker compose -f infra/searxng/docker-compose.yml up -d
curl "http://localhost:8080/search?q=test&format=json"
```

The backend `.env` then points at it:

```
WEB_SEARCH_PROVIDER=searxng
SEARXNG_BASE_URL=http://localhost:8080
```

Notes:
- `settings.yml` ships with `base_url: http://localhost:8080/` and a placeholder
  `secret_key`. Both are fine for local dev only.
- Loopback `SEARXNG_BASE_URL` values are rejected by config validation outside
  `APP_ENV=development`, so a localhost URL can never leak into production.

## 2. Production requirements (hard rules)

The master-prompt constraints make these non-negotiable:

1. **Externally reachable HTTPS URL.** Deploy SearXNG to an always-on Docker
   host with a public TLS endpoint. The prepared package targets **Fly.io**;
   the same image runs on Render, Railway, or any VPS behind Caddy/nginx.
2. **Rotate the secret key.** Generate a long random value and inject it at
   runtime via `SEARXNG_SECRET` (see §3, step 5). The committed placeholder in
   `settings.production.yml` is public and must not be reused.
3. **Set `SEARXNG_BASE_URL=https://<your-instance>` and
   `WEB_SEARCH_PROVIDER=searxng`** in the Vercel backend environment (§4).
   Never commit the real URL to the repo.
4. **Set a shared `SEARXNG_AUTH_TOKEN`** — a long random value, identical on
   the Fly app (`flyctl secrets set`) and in the Vercel backend environment.
   It is the only credential that grants access to the JSON API; never commit
   it.

Security posture of the deployed instance:
- **Token-authenticated edge (restricted access).** The production image runs
  Caddy in front of SearXNG: every request except `/healthz` must carry
  `Authorization: Bearer <SEARXNG_AUTH_TOKEN>`, or it is rejected with 401
  before reaching SearXNG. SearXNG/Granian binds to `127.0.0.1:8081` inside the
  container and is never exposed directly. The container **refuses to start**
  when `SEARXNG_AUTH_TOKEN` is unset (fail closed). The backend sends the same
  token automatically when its `SEARXNG_AUTH_TOKEN` setting is non-empty.
- **Why not SearXNG's built-in limiter?** It is designed to block bots, not to
  serve a headless API client: `format=json` traffic is capped at **4 requests
  per hour per IP** (`API_MAX` in `searx/botdetection/ip_limit.py`) and
  non-browser user agents are 429'd outright. Enabling it would break this
  platform's own backend. `settings.production.yml` therefore sets
  `limiter: false` and documents the reason. Rate limiting is enforced
  platform-side by the backend's verified web-search limiter (global RPM floor,
  per-user limits, concurrency cap); the token edge keeps third parties out.
- `public_instance: false` and the restrictive `default_http_headers` are kept.
- `secret_key` is injected at runtime via the `SEARXNG_SECRET` env var, which
  SearXNG's settings layer reads natively (`server.secret_key` override); it is
  never baked into the image or committed.
- The backend never sends `categories`/`safesearch` overrides and validates
  every result URL through the SSRF guard, so the instance's own defaults
  govern engine selection.

## 3. Deploy on Fly.io (prepared configuration)

Prerequisites: `flyctl` installed and authenticated; Docker running locally.

Validate the package locally (no daemon needed):

```bash
docker compose -f infra/searxng/docker-compose.yml config -q
docker build -f infra/searxng/Dockerfile.prod -t realestategpt-searxng:local infra/searxng
```

Smoke-test the production image locally (secret/base_url placeholders are fine
for the smoke test; `SEARXNG_AUTH_TOKEN` is **required** — the container
refuses to start without it):

```bash
docker run --rm -p 8081:8080 \
  -e SEARXNG_SECRET=smoke-only -e SEARXNG_AUTH_TOKEN=smoke-token \
  realestategpt-searxng:local

curl "http://localhost:8081/healthz"                                   # 200 OK
curl "http://localhost:8081/search?q=test&format=json"                 # 401
curl -H "Authorization: Bearer smoke-token" \
  "http://localhost:8081/search?q=test&format=json"                    # 200 JSON
```

Deploy for real:

```bash
cp infra/searxng/fly.toml infra/searxng/fly.toml.local   # gitignored
# edit fly.toml.local: replace CHANGE_ME_APP_NAME with a globally unique name

flyctl apps create <app-name>
flyctl deploy -c infra/searxng/fly.toml.local
flyctl secrets set SEARXNG_SECRET="$(openssl rand -hex 32)" \
                   SEARXNG_AUTH_TOKEN="$(openssl rand -hex 32)"
flyctl apps restart <app-name>        # secrets apply on restart
```

Record the `SEARXNG_AUTH_TOKEN` value you set — the backend needs the same one
(§4). The instance is now served at `https://<app-name>.fly.dev` (Fly
terminates TLS automatically; `force_https = true` in fly.toml). The fly.toml
keeps the machine always on (`auto_stop_machines = "off"`,
`min_machines_running = 1`), checks health on `/healthz` every 30s (the only
unauthenticated route), and auto-restarts failures.

Operations:

```bash
flyctl status             # deployment state
flyctl logs               # container logs
flyctl ssh console        # shell into the machine
```

Equivalent one-container setups work on Render (Docker deploy from
`Dockerfile.prod`) and Railway (`railway up` with the same Dockerfile). Any
host that keeps the container running and terminates TLS in front of it is
acceptable.

## 4. Point the production backend at the instance (Vercel)

Set these in the **existing** Vercel project (`realestate-gpt-inky`), backend
environment — dashboard → Settings → Environment Variables, or:

```bash
vercel env add SEARXNG_BASE_URL production      # value: https://<app-name>.fly.dev
vercel env add WEB_SEARCH_PROVIDER production   # value: searxng
vercel env add SEARXNG_AUTH_TOKEN production    # value: the token set on the Fly app
```

Full backend variable contract (see `backend/.env.example`):

| Variable | Production value |
| --- | --- |
| `APP_ENV` | `production` |
| `MONGODB_URI` / `MONGODB_DATABASE` | existing Atlas values |
| `SECRET_KEY` / `CRON_SECRET` / `WORKER_RUN_SECRET` | existing random values |
| `GROQ_API_KEY` / `GROQ_MODEL` | existing values |
| `LOCATION_PROVIDER` | `osm` |
| `WEB_DISCOVERY_ENABLED` | `true` |
| `WEB_SEARCH_PROVIDER` | `searxng` |
| `SEARXNG_BASE_URL` | `https://<app-name>.fly.dev` |
| `SEARXNG_AUTH_TOKEN` | the same token set via `flyctl secrets` |
| `CORS_ORIGINS` | `https://realestate-gpt-inky.vercel.app` |

Then redeploy the existing project (`vercel --prod` or a push to `main`).
**Never** put `GROQ_API_KEY`, `MONGODB_URI`, `SECRET_KEY`, `CRON_SECRET`, or
`WORKER_RUN_SECRET` into any `NEXT_PUBLIC_*` variable.

Frontend keeps only:
- `NEXT_PUBLIC_API_URL=https://realestate-gpt-inky.vercel.app/api/backend`
- `NEXT_PUBLIC_SITE_URL=https://realestate-gpt-inky.vercel.app`

## 5. Verifying the production instance

From any machine:

```bash
# Restricted access: unauthenticated requests must be rejected.
curl -o /dev/null -w "%{http_code}\n" \
  "https://<app-name>.fly.dev/search?q=test&format=json"          # -> 401

# Authenticated JSON API works.
curl -H "Authorization: Bearer <SEARXNG_AUTH_TOKEN>" \
  "https://<app-name>.fly.dev/search?q=2bhk%20hyderabad&format=json" \
  | jq '.results | length'                                        # -> > 0

# Health endpoint (the only public route).
curl "https://<app-name>.fly.dev/healthz"                         # -> OK
```

Then run one live autonomous query against the deployed backend and confirm
`metadata.provider == "searxng"` and non-zero `web_discoveries` in the
`/api/v1/search/autonomous` response (see
docs/AUTONOMOUS_DISCOVERY_PRODUCTION_REPORT.md for the full checklist).
