# Location providers

## Production provider: OpenStreetMap

`LOCATION_PROVIDER=osm` is the single production selector. The browser uses
Leaflet with OpenStreetMap tiles. The FastAPI backend is responsible for all
location intelligence and calls the configured external services:

```text
Property coordinates
  -> LocationProvider (OpenStreetMapLocationProvider)
  -> Overpass: nearby POIs
  -> OSRM: walking, cycling, or driving route distance and duration
  -> normalized API response
  -> Leaflet map and nearby-place UI
```

Nominatim performs address-to-coordinate geocoding through `POST /api/v1/locations/geocode`.
It is throttled to one uncached request per second per application process.
Overpass/OSRM results are cached briefly in process to control repeat traffic.
The public services may rate-limit or fail; those cases return clear 429/422/503
API errors. They never trigger Google, seed-data, or mock-data fallback.

OpenStreetMap does not provide commercial place ratings or photos through this
integration. The UI intentionally does not show either.

## Local verification (2026-09-11)

| Provider | Result | Evidence |
| --- | --- | --- |
| Nominatim | PASS | Live HITEC City geocode normalized by FastAPI |
| Overpass | PASS | Live hospital POIs returned and rendered on the property page |
| OSRM | PASS | Live distance and duration returned for nearby POIs |
| Leaflet + OSM tiles | PASS | Interactive map controls and OpenStreetMap attribution rendered locally |
| Google Maps | NOT REQUIRED | Disabled for the OSM production configuration |
| Vercel deployment | NOT TESTED | Requires production environment deployment and a non-demo property |

Configure a truthful `NOMINATIM_USER_AGENT` with an operator contact before
production use, observe each upstream service's usage policy, and move to a
dedicated provider/host if traffic exceeds public-service capacity.

## Optional future provider: Google Maps

`GoogleMapsProvider` remains available only when `LOCATION_PROVIDER=google`
and a backend-only server key is configured. It is never selected by `MAPS_PROVIDER`
and no Google browser key is needed for the OSM production map. This repository
does not fall back to Google when OSM fails.
