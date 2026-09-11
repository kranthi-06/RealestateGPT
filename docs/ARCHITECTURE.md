# RealEstateGPT architecture

> Audit date: 2026-09-11. This document describes the repository as inspected;
> it does not mark unverified external services as working.

## Current system

```text
Next.js 16 browser application
  -> NEXT_PUBLIC_API_URL
  -> FastAPI /api/v1
  -> service layer
  -> MongoDB repositories / external providers
  -> MongoDB Atlas, Groq, OpenStreetMap services
```

The repository is a two-service application: `frontend/` is a Next.js App
Router client and `backend/` is a FastAPI application. `vercel.json` declares
the services and routes `/api/backend/*` to the backend service.

The backend currently uses a shared PyMongo client, Stable API configuration,
connection-pool limits and idempotent index setup at application startup. Its
application lifespan deliberately fails when MongoDB is unavailable; there is
no SQLite or in-memory fallback in the current runtime.

## Implemented layers

| Area | Current implementation | Status |
| --- | --- | --- |
| UI | Next.js pages for home, search, property details, compare, saved, assistant and authentication | Implemented |
| API | FastAPI routers for auth, properties, saved items, AI, locations, admin and health | Implemented |
| Data | PyMongo repositories for users, properties, saved data and platform records | Implemented |
| Property data | Validated MongoDB document, provenance/quality metadata, admin lifecycle, filters and geospatial search | Phase 2 implemented; seed inventory remains demo data |
| Auth | Password hashing, JWT bearer authentication and ownership-scoped saved-data operations | Implemented; browser token storage needs hardening |
| Finance | Deterministic EMI, affordability, yield and ROI calculators | Implemented |
| Search | MongoDB-first filters/2dsphere candidates, typed SearchIntent, bounded OSM enrichment and deterministic ranking | Phase 3 implemented; remains authoritative |
| Maps | Leaflet + OpenStreetMap tiles and server-side Nominatim/Overpass/OSRM adapter | OSM is the production default; Google remains optional |
| AI | Groq gateway, bounded tool-calling agent, strict four-tool registry and provenance/audit persistence | Implemented locally; live Groq/deployment verification pending |
| Documents/notifications | Models and some repositories | Not a complete vertical slice |

## Dependency direction

The intended and mostly established backend direction is:

```text
FastAPI route -> service/orchestrator -> repository or provider -> database/external API
```

Routes receive typed Pydantic input and dependencies. Repositories own MongoDB
queries. The AI tool layer delegates to services/repositories rather than
allowing model-generated database queries or arbitrary code execution.

## Collections and index strategy

The application creates indexes for users, properties, saved properties,
saved searches, comparisons, conversations, messages, documents, document
chunks, nearby places, property sources and audit logs. `properties.location`
and `nearby_places.location` use `2dsphere` indexes. Index definitions live in
`backend/app/core/database.py` and should be reviewed against Atlas query
metrics before adding new ones.

## Environment and deployment boundary

`NEXT_PUBLIC_*` values are public build-time frontend configuration. The OSM
production map requires no browser API key. MongoDB URI, Groq key, FastAPI
`SECRET_KEY`, and any future Google server key must remain backend-service
variables.

The checked-in deployment examples use the MongoDB variables in
`backend/app/core/config.py`. The backend must receive:

```text
MONGODB_URI
MONGODB_DATABASE=realestate_gpt
SECRET_KEY
CORS_ORIGINS=https://realestate-gpt-inky.vercel.app
AI_PROVIDER=groq                 # only after a live Groq verification
GROQ_API_KEY                     # backend only
LOCATION_PROVIDER=osm
NOMINATIM_BASE_URL=https://nominatim.openstreetmap.org
OVERPASS_URL=https://overpass-api.de/api/interpreter
OSRM_BASE_URL=https://router.project-osrm.org
NOMINATIM_USER_AGENT=RealEstateGPT/1.0
```

The frontend service must receive:

```text
NEXT_PUBLIC_API_URL=https://realestate-gpt-inky.vercel.app/api/backend
```

Changing a `NEXT_PUBLIC_*` variable requires a new frontend build/deployment.

## Verified baseline

| Check | Result |
| --- | --- |
| Backend unit/integration suite | PASS — 28 tests passed locally |
| MongoDB property CRUD, filters and geospatial search | PASS — integration tests against the configured MongoDB database |
| Natural-language discovery parsing/ranking | PASS — deterministic parser and database-first discovery tests |
| Live MongoDB → OSM-enriched discovery query | PASS — temporary demo property returned with metro distance and fact-derived reasons; removed after test |
| Admin-only property mutation API contract | PASS — unauthenticated create rejected; admin create/update/delete verified |
| Frontend lint | PASS |
| Frontend production build | PASS |
| MongoDB repository integration | PASS within the local test suite when configured |
| Live Nominatim geocoding | PASS — HITEC City, Hyderabad response normalized through FastAPI |
| Live Overpass nearby POIs | PASS — hospital results rendered in the property-page UI |
| Live OSRM routing | PASS — route distance/duration rendered for nearby results |
| Leaflet + OpenStreetMap map UI | PASS — interactive map, markers, controls and required attribution rendered locally |
| Google Maps | NOT REQUIRED — optional provider remains disabled |
| Deployed Vercel end-to-end journey | NOT TESTED in this audit |
| Groq runtime through the application | NOT TESTED in this audit |

## Material gaps and risks

1. Seeded properties and places carry `is_synthetic`; the UI must keep them
   labelled as demo inventory until a licensed property provider is available.
2. Rate-limit settings exist but no request middleware enforces them.
3. The global exception response is inconsistent with the requested structured
   error contract and the database health route exposes raw exception text.
4. The assistant has a bounded Groq tool-calling architecture but its deployed
   backend still needs a successful real-environment smoke test.
5. Auth uses bearer tokens stored client-side; a production cookie/session and
   CSRF strategy has not been implemented.
6. Document intelligence, RAG, notifications and admin operations are not yet
   end-to-end features.

## Controlled implementation path

1. Deploy the configured Groq gateway and verify the production backend health
   endpoint before claiming the assistant production-ready.
2. Run a live Groq tool/citation evaluation with a non-committed configured key.
3. Build subsequent property ingestion, comparison, documents and notification
   slices only after their corresponding dependencies are live and testable.

Each phase must pass backend tests, frontend lint/build, and its real vertical
slice before the next phase begins.
