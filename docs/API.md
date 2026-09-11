# API

All endpoints are rooted at `/api/v1`. FastAPI publishes the current typed
OpenAPI contract at `/docs` while the backend is running.

## AI assistant

`POST /ai/assistant` requires authentication. It invokes Groq only when
`AI_PROVIDER=groq` and `GROQ_API_KEY` are configured. Its typed response has a
validated `answer`, deterministic `results`, backend-generated `citations`, and
safe `tool_calls` summaries. Failures return a user-safe message and an AI error
code in `detail.code`; they never return a fabricated answer.

## Properties

| Method | Endpoint | Access | Purpose |
| --- | --- | --- |
| GET | `/properties` | Public | Paginated catalogue search |
| GET | `/properties/{id}` | Public | Active property by integer ID |
| POST | `/properties` | Admin | Create a provenance-labelled property |
| PATCH | `/properties/{id}` | Admin | Update an active property |
| DELETE | `/properties/{id}` | Admin | Soft-delete an active property |

`GET /properties` validates and supports `city`, `locality`, `min_price`,
`max_price`, `bedrooms`, `bathrooms`, `property_type`, `listing_type`,
`furnishing`, repeated `amenities`, `min_area`, `max_area`, `page`,
`page_size`, `sort_by`, and `sort_order`.

For a radius search, provide all three values: `latitude`, `longitude`, and
`radius_km`. MongoDB orders geospatial results by distance; a separate sort is
not applied to that query. Invalid ranges or incomplete coordinate triplets
return HTTP 422. Missing listings return HTTP 404. Create/update/delete routes
derive authorization on the backend from the bearer token and return HTTP 401
or 403 when the caller is not an admin.

Property responses include provenance and quality fields, so a caller can
distinguish demo inventory from a licensed or partner listing.

## Discovery search

| Method | Endpoint | Access | Purpose |
| --- | --- | --- |
| POST | `/ai/search` | Public | Natural-language property discovery |

The body requires a bounded `query` string and accepts `limit` (1–40) plus
typed `user_filters`. The response includes a validated `SearchIntent`,
database result count, rankings, fact-derived reasons, warnings and latency
metrics. It never accepts MongoDB operators or arbitrary query objects.
