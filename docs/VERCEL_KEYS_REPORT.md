# Vercel keys report — Tavily free-tier switch (no Fly.io, no Google, no card)

Date: 2026-10-06. Project: `realestate-gpt` → https://realestate-gpt-inky.vercel.app
Method: `vercel env ls` (names + presence only, values never printed) + live
`GET /api/v1/health/web-search` (currently `provider=tavily, configured=true, enabled=true`).

## VERDICT — 1 ADD, 0 urgent changes

| # | Variable | Live state | Action |
|---|---|---|---|
| 1 | `TAVILY_API_KEY` | SET (Secret, Production+Preview) | NONE — do not touch |
| 2 | `WEB_DISCOVERY_ENABLED` | SET (Secret, Production+Preview; live health proves `enabled=true`) | NONE — do not touch |
| 3 | `WEB_SEARCH_PROVIDER` | SET (Secret, Production+Preview; live health proves `tavily`) | NONE — do not touch |
| 4 | `TAVILY_SEARCH_DEPTH` | MISSING | **ADD with value `basic`** (copy-paste below) |
| 5 | `MONGODB_URI`, `MONGODB_DATABASE`, `SECRET_KEY`, `GROQ_API_KEY`, `GROQ_MODEL`, `LOCATION_PROVIDER`, `CORS_ORIGINS`, `CRON_SECRET`, `WORKER_RUN_SECRET` | all SET | NONE |
| 6 | All tuning vars (`WEB_SEARCH_COUNTRY/LANGUAGE/MAX_QUERIES/MAX_RESULTS/CACHE_TTL/TIMEOUT/MAX_RETRIES/CONCURRENCY/OSM_ENRICH_LIMIT`, `PAGE_ENRICHMENT_ENABLED`, rate-limit, pool, AI, OSM, worker/inventory vars) | all SET | NONE |
| 7 | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL` | SET | NONE |
| 8 | `SEARXNG_BASE_URL` (+ `BRAVE_SEARCH_API_KEY` absent, `SEARXNG_AUTH_TOKEN` absent) | legacy/irrelevant while provider=tavily (code ignores them) | NONE — leave as-is; optional cleanup later |
| 9 | `NEXT_PUBLIC_TAVILY_API_KEY`, `NEXT_PUBLIC_SEARXNG_*`, `NEXT_PUBLIC_*SECRET*`, `NEXT_PUBLIC_GROQ_API_KEY`, `NEXT_PUBLIC_MONGODB_URI` | all ABSENT (correct) | NEVER ADD — key stays backend-only |

Why only one add: the backend defaults `TAVILY_SEARCH_DEPTH` to `basic` when
unset, so discovery already works — pinning `basic` explicitly locks 1 credit
per request (free tier = 1000 credits/month) and stops anyone flipping it to
`advanced` (2 credits) by accident.

## COPY-PASTE — the one ADD

Key:   `TAVILY_SEARCH_DEPTH`
Value: `basic`
Target environments: Production (tick Preview too, to match the other vars)

Dashboard (Vercel → project `realestate-gpt` → Settings → Environment Variables):
1. Click **Add New**, Key = `TAVILY_SEARCH_DEPTH`, Value = `basic`.
2. Tick **Production** (and Preview). 3. Save. 4. Redeploy (`vercel --prod`)
so the new value is baked into the build.

CLI alternative (run in `e:\Realestate gpt`):
`vercel env add TAVILY_SEARCH_DEPTH production` → paste `basic` when prompted.

## VERIFY without printing secrets

1. `vercel env ls` → `TAVILY_SEARCH_DEPTH` appears next to the other `WEB_*` vars.
2. `GET https://realestate-gpt-inky.vercel.app/api/v1/health/web-search` →
`provider=tavily, configured=true, enabled=true`.
3. `POST /api/v1/search` `{"query":"2BHK rent Hyderabad","include_web":true}` →
`metadata.provider=tavily`, `web_discoveries[]` with real title/source/url.

## WHERE TO GET EVERY KEY (detail, no secrets inside)

1. **TAVILY_API_KEY** (already SET — only if you ever rotate): sign up at
https://tavily.com → Dashboard → API Keys → Create/Copy (starts `tvly-`).
Free plan = 1,000 credits/month, no card. Backend sends it as
`Authorization: Bearer <key>` to `POST https://api.tavily.com/search`.
2. **MongoDB Atlas** (already SET): https://cloud.mongodb.com → your cluster →
Connect → Drivers (Python) → copy the `mongodb+srv://…` string into
`MONGODB_URI`; `MONGODB_DATABASE=realestate_gpt`. Never use a `NEXT_PUBLIC_` copy.
3. **Groq** (already SET): https://console.groq.com → API Keys → Create →
`GROQ_API_KEY`; model `GROQ_MODEL=qwen/qwen3.8-27b`. Server-side only.
4. **SECRET_KEY / CRON_SECRET / WORKER_RUN_SECRET** (already SET — only if you
rotate): generate with `openssl rand -hex 32`. `SECRET_KEY` signs JWTs;
`CRON_SECRET` is sent by Vercel Cron as `Authorization: Bearer`;
`WORKER_RUN_SECRET` is sent as `X-Worker-Secret` to worker-run endpoints.
5. **CORS_ORIGINS / PRODUCTION_FRONTEND_URL**: literal
`https://realestate-gpt-inky.vercel.app` (already SET).
6. **Location (OSM/Nominatim/Overpass/OSRM)**: no accounts, no keys — URLs only.
7. **Frontend `NEXT_PUBLIC_*`**: public URLs only (`NEXT_PUBLIC_API_URL`,
`NEXT_PUBLIC_SITE_URL`). If a page ever breaks, check these two first.

After the ADD + redeploy, the entire site keeps working: MongoDB search never
depends on Tavily (quota/transport failures degrade to typed errors and normal
inventory search continues), Groq and OSM are untouched, and no secret ever
reaches the browser.
