# RealEstateGPT — architecture audit

> Updated 2026-09-11. Statements below reflect the code and local verification
> performed in this workspace.

## Current architecture

```text
Next.js 16 frontend
  -> FastAPI /api/v1
  -> service / provider / repository layers
  -> MongoDB Atlas and configured external providers
```

The backend uses PyMongo with a shared client, MongoDB Stable API, lifecycle
connection verification and idempotent indexes. The runtime does not use
SQLAlchemy, SQLite or PostgreSQL.

## Production location architecture

```text
Property coordinates
  -> LocationService / configured LocationProvider
  -> OpenStreetMap provider
     -> Nominatim (geocoding)
     -> Overpass (nearby POIs)
     -> OSRM (drive/walk/cycle routing)
  -> typed FastAPI response
  -> Leaflet + OpenStreetMap map and nearby-place UI
```

`LOCATION_PROVIDER=osm` is the only production selector. A request never falls
back to Google Maps, stored seeded nearby places, or mocked values. Google
remains an optional future adapter only.

## Verified results

| Item | Status |
| --- | --- |
| Backend tests | PASS — 25 tests passed locally |
| MongoDB property CRUD/filter/geospatial/API contracts | PASS — integration-tested against configured MongoDB |
| Discovery parser/ranking/API contracts | PASS — database-first candidate selection and typed API response tested |
| Frontend lint | PASS |
| Frontend production build | PASS |
| Nominatim live geocode | PASS |
| Overpass live nearby POIs | PASS |
| OSRM live route | PASS |
| Leaflet map and OSM attribution | PASS — browser verified locally |
| Google Maps | NOT REQUIRED — disabled for production OSM configuration |
| Vercel production vertical slice | NOT TESTED |

## Remaining risks

1. The current property database is empty. The local OSM browser test used a
   temporary property clearly labelled demo data and removed it after testing.
2. Public Nominatim, Overpass and OSRM endpoints are appropriate for bounded
   low-volume use, but production traffic needs monitoring and may require
   dedicated infrastructure.
3. Request-level rate limiting, request IDs and structured observability are
   not complete yet.
4. Assistant orchestration remains deterministic/offline; a bounded Groq
   runtime remains a later phase.
