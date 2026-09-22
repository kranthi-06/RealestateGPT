# RealestateGPT

RealestateGPT is a real-estate search application with a Next.js frontend and a FastAPI backend.

## Local development

### Frontend

```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to the backend URL when it is not running on `http://localhost:8000`.

## Vercel deployment

The root `vercel.json` defines two services: `frontend` (Next.js) and `backend` (FastAPI). Import the repository as a multi-service deployment so Vercel uses that configuration. The backend is available through `/api/backend/*`, while all other routes go to the frontend.

Add these environment variables in the Vercel project settings:

```text
NEXT_PUBLIC_API_URL=https://your-deployed-backend.example.com
```

Configure the backend service environment variables from `backend/.env.example`. Its CORS configuration must include the deployed Vercel URL. For the included multi-service setup, use:

```text
NEXT_PUBLIC_API_URL=https://realestate-gpt-inky.vercel.app/api/backend
LOCATION_PROVIDER=osm
```

If the platform provides a separate backend service URL, use that URL for `NEXT_PUBLIC_API_URL` instead.

### Database on Vercel

The backend uses MongoDB Atlas, not SQLite or PostgreSQL. Set `MONGODB_URI` and
`MONGODB_DATABASE=realestate_gpt` on the backend service. Startup verifies the
MongoDB connection and creates the required indexes; it does not fall back to
a serverless filesystem database.

### Location services

Production maps use Leaflet and OpenStreetMap tiles. The backend uses
Nominatim for geocoding, Overpass for nearby places, and OSRM for routes;
configure `LOCATION_PROVIDER=osm` and the OSM variables in
`backend/.env.example`. Google Maps is optional and disabled by default.

## Property data & workers

**Providers** — production inventory always comes from a licensed/authorized
provider behind `app/providers/property/`. Set `PROPERTY_PROVIDER` (e.g.
`admin_import` + `PROPERTY_PROVIDER_FILE`) to begin ingesting. When no provider
is configured the catalogue is intentionally empty — the UI and the
`/api/v1/workers/status` endpoint say so instead of showing fake listings.
See `backend/data/README.md` for the admin-import file format.

**Workers** — ingestion, listing refresh, geocoding, stale-listing and
price-history workers live in `app/workers/` (thin CLI entry points in
`backend/workers/`). They are single-flight (distributed lock with lease
expiry/recovery), idempotent, bounded-batch, and record every run in
`worker_runs` for monitoring.

- Dev: `python workers/<worker>.py` from `backend/`
- Production: schedule cron (Vercel, GitHub Actions, etc.) to hit
  `POST /api/v1/workers/run/{name}` with header
  `X-Worker-Secret: <WORKER_RUN_SECRET>` (set it to a long random value).
  Worker endpoints reject requests without a valid secret or admin JWT.

**Freshness lifecycle** — active listings that a healthy provider stops
returning become `stale` after `LISTING_STALE_AFTER_HOURS`, then `expired`
(and hidden from search) after `LISTING_EXPIRE_AFTER_DAYS`. Provider/network
failures never mark a listing unavailable; only provider-confirmed states
(`sold`, `rented`, `inactive`) do.

**Monitoring** — sign in as an admin and open `/admin` for a live worker
dashboard (last runs, processed/success/failure/skipped counts, provider
configuration state). API: `GET /api/v1/workers/status`.

**Migrations** — schema backfills (e.g. `source_listing_id`,
`transaction_type`, image objects) run idempotently at startup and are tracked
in `schema_migrations`. The integer-id counters are auto-repaired so restored
or partially-cleaned databases cannot produce duplicate-key errors.
