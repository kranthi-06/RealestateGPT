# SearXNG Deployment Guide (RealEstateGPT)

RealEstateGPT's web discovery provider (`WEB_SEARCH_PROVIDER=searxng`) talks to a
self-hosted SearXNG instance over its JSON API. This directory holds the local
development compose file. **Production requires a separately deployed, externally
reachable HTTPS instance** — see below.

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

The master-prompt constraints make three things non-negotiable:

1. **Externally reachable HTTPS URL.** Production must not depend on this
   (or any) developer workstation staying on. Deploy SearXNG to a always-on
   host with a public TLS endpoint, e.g. Fly.io, Render, Railway, or a VPS
   behind Caddy/nginx.
2. **Set `SEARXNG_BASE_URL=https://<your-instance>` and
   `WEB_SEARCH_PROVIDER=searxng`** in the backend environment (Vercel env
   vars or your server `.env`). Never commit the real URL to the repo.
3. **Rotate the secret key.** Generate a long random value and set it via the
   container environment (`SEARXNG_SECRET_KEY`) or an updated `settings.yml`
   on the host. The placeholder in this repo is public and must not be reused.

Security notes for the deployed instance:
- Keep `public_instance: false` and the restrictive `default_http_headers`.
- SearXNG has no built-in auth for the JSON API; protect it at the edge
  (network-level allow-list of your backend egress IPs, or a reverse-proxy
  basic-auth / mTLS layer) so the open web cannot consume your quota.
- The backend never sends `categories`/`safesearch` overrides and validates
  every result URL through the SSRF guard, so the instance's own defaults
  govern engine selection.

## 3. Deploying on Fly.io (example)

```bash
# one-time
flyctl apps create realestategpt-searxng

# launch with the official image
flyctl deploy --image searxng/searxng:latest \
  --env SEARXNG_BASE_URL=https://realestategpt-searxng.fly.dev/ \
  --env INSTANCE_NAME=RealEstateGPT-SearXNG

# mount a persistent volume and upload your production settings.yml
# (with a real secret_key and https base_url), then:
flyctl secrets set SEARXNG_SECRET_KEY=<random-64-hex>
```

Equivalent one-container setups work on Render (Docker deploy) and Railway.
Any host that keeps the container running and terminates TLS in front of it
is acceptable.

## 4. Verifying the production instance

From any machine:

```bash
curl "https://<your-instance>/search?q=2bhk%20hyderabad&format=json" | jq '.results | length'
```

Then trigger one live discovery run against the deployed backend and confirm
`metadata.provider == "searxng"` and non-zero `web_discoveries` in the
`/api/v1/search/autonomous` response.
