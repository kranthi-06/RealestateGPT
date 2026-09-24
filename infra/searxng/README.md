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

Security posture of the deployed instance:
- `public_instance: false` and the restrictive `default_http_headers` are kept.
- `server.limiter: true` enables SearXNG's built-in per-IP rate limiting.
- The JSON API has no application-level auth (upstream design). Vercel's
  serverless egress uses a pool of IP addresses, so an egress IP allow-list is
  not reliable; the practical controls are the limiter, the rotated secret,
  and the small instance footprint. If stronger restriction is ever required,
  front the instance with a reverse proxy that adds basic auth and extend
  `SearXNGSearchProvider.search` to send an `Authorization` header — no other
  discovery logic needs to change.
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
for the smoke test — SearXNG only needs them non-empty to boot):

```bash
docker run --rm -p 8081:8080 realestategpt-searxng:local
curl "http://localhost:8081/search?q=test&format=json"
```

Deploy for real:

```bash
cp infra/searxng/fly.toml infra/searxng/fly.toml.local   # gitignored
# edit fly.toml.local: replace CHANGE_ME_APP_NAME with a globally unique name

flyctl apps create <app-name>
flyctl deploy -c infra/searxng/fly.toml.local
flyctl secrets set SEARXNG_SECRET="$(openssl rand -hex 32)"
flyctl apps restart <app-name>        # secrets apply on restart
```

The instance is now served at `https://<app-name>.fly.dev` (Fly terminates
TLS automatically; `force_https = true` in fly.toml). The fly.toml keeps the
machine always on (`auto_stop_machines = "off"`, `min_machines_running = 1`),
checks health on `/` every 30s, and auto-restarts failures.

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
vercel env add SEARXNG_BASE_URL production   # value: https://<app-name>.fly.dev
vercel env add WEB_SEARCH_PROVIDER production   # value: searxng
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
curl "https://<app-name>.fly.dev/search?q=2bhk%20hyderabad&format=json" | jq '.results | length'
```

Then run one live autonomous query against the deployed backend and confirm
`metadata.provider == "searxng"` and non-zero `web_discoveries` in the
`/api/v1/search/autonomous` response (see
docs/AUTONOMOUS_DISCOVERY_PRODUCTION_REPORT.md for the full checklist).
