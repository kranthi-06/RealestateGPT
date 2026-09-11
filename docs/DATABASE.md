# Database

## Production persistence

MongoDB Atlas is the only production database. The backend creates one shared
PyMongo `MongoClient`, configured with MongoDB Stable API, bounded connection
pooling, timeouts and retryable writes. Application startup verifies MongoDB
connectivity and creates indexes; it fails loudly when Atlas is unavailable.
There is no SQLite, PostgreSQL, or in-memory production fallback.

Required backend variables:

```text
MONGODB_URI=
MONGODB_DATABASE=realestate_gpt
MONGODB_CONNECT_TIMEOUT_MS=10000
MONGODB_SERVER_SELECTION_TIMEOUT_MS=10000
MONGODB_SOCKET_TIMEOUT_MS=30000
MONGODB_MAX_POOL_SIZE=20
```

## Property document

`properties` holds canonical listing documents. Required domain information is
validated before persistence: identity/title, property/listing type, positive
price, currency, city, explicit provenance, timestamps and (when present) a
paired latitude/longitude coordinate. Coordinates are normalized to GeoJSON
`location` (`[longitude, latitude]`).

The document supports canonical `area`/`area_unit` and `images`. Legacy
`area_sqft` and `image_urls` remain as compatibility projections while the
frontend migrates. Provenance includes `source`, `source_id`, `source_url`,
`source_type`, `verification_status`, `last_verified_at`, and
`data_quality_score`.

`source_type` is one of `licensed_feed`, `partner_api`, `admin`, `user`, or
`demo`. Demo records are forced synthetic and may not be verified.

## Indexes

Property indexes are intentionally limited to active query patterns:

| Index | Purpose |
| --- | --- |
| `location` 2dsphere | radius search |
| `price`, `city`, `locality`, `property_type`, `bedrooms`, `listing_type`, `updated_at` | filtering/sorting |
| `amenities.name` | amenity filtering |
| `(source, source_id)` partial unique | feed-level deduplication when a source ID exists |
| `(city, property_type, bedrooms, price)` | common filtered catalogue search |

Indexes are defined in `backend/app/core/database.py`; review Atlas query
metrics before adding more.

## Repository boundary

Only repositories issue MongoDB queries. API handlers use services, and
services use repositories/providers. Property deletes are soft deletes
(`is_active=false`) to retain provenance and audit history.

Natural-language discovery uses the existing filter indexes and `location`
2dsphere index to select a bounded candidate set before ranking. It does not
load the complete collection into application memory.
