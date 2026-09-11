# Google Maps Platform — optional future provider

> Production is configured for `LOCATION_PROVIDER=osm` and does not require
> Google Cloud billing or either Google API key. This document applies only if
> an operator deliberately changes the backend location provider to Google.

RealEstateGPT uses two separate Google API keys. Never copy either key into source control.

## Frontend (Vercel)

If the Google browser map is enabled in a future deployment, set this variable
in the **Vercel frontend service**:

```text
NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY
```

Restrict the browser key by HTTP referrer. Include your production domains and development origin, for example:

```text
https://your-domain.example/*
https://*.vercel.app/*
http://localhost:3000/*
```

Allow only **Maps JavaScript API** for this key.

## Backend service

Set these environment variables wherever FastAPI is deployed (not in Vercel client code):

```text
LOCATION_PROVIDER=google
GOOGLE_MAPS_SERVER_KEY=...
```

Restrict the server key by API to:

- Places API (New)
- Geocoding API
- Routes API

Use an IP restriction as well if the backend has stable outbound IP addresses. The backend must be reachable from the Vercel frontend through `NEXT_PUBLIC_API_URL`, and its CORS allow-list must include the deployed Vercel domain.

## Google policy notes

- Nearby place, rating, route, and photo data is fetched on demand and is not stored in the database.
- Place photos are delivered from a FastAPI proxy so `GOOGLE_MAPS_SERVER_KEY` never reaches a browser. The UI shows Google Maps and photographer attribution when supplied by Google.
- Do not scrape Google Maps or cache Google place payloads outside the terms of the Google Maps Platform agreement.

## Verification

1. Visit `/api/v1/locations/status`; it should return `configured: true` and `provider: google`.
2. Open a property page and use a nearby category.
3. Confirm the response contains Google place names, ratings, map links, photo attribution, straight/route distance, and travel time.
4. If the API returns `403 PERMISSION_DENIED`, enable the listed APIs in the same Google Cloud project and correct the server key's API restrictions.
