# Property provider data

This directory holds the admin-authored inventory file used by the
`admin_import` property provider when `PROPERTY_PROVIDER=admin_import`.

**Policy**: this platform only ingests listings you are licensed or authorized
to use. It never scrapes third-party listing sites. The `property_provider.jsonl`
file is *written by you* (or by an approved partner integration), not fetched
from anywhere.

## File format

`property_provider.jsonl` — one JSON object per line, canonical fields:

```json
{"source_listing_id": "L-1001", "title": "3BHK in HITEC City", "price": 7500000,
 "property_type": "apartment", "listing_type": "sale", "transaction_type": "sale",
 "city": "Hyderabad", "locality": "HITEC City", "bedrooms": 3, "bathrooms": 3,
 "area": 1200, "area_unit": "sqft", "furnishing": "semi-furnished",
 "address": "HITEC City Main Road, Hyderabad",
 "images": [{"url": "https://your-cdn.example.com/a.jpg", "category": "exterior"}],
 "source_url": "https://your-site.example.com/listing/L-1001",
 "status": "active"}
```

A per-record `status` is honored by the refresh worker:
`active`, `sold`, `rented`, `inactive`, `expired` (provider-confirmed terminal
states). A listing that disappears from the file is **not** treated as sold — it
ages into `stale` and later `expired` via `LISTING_STALE_AFTER_HOURS` /
`LISTING_EXPIRE_AFTER_DAYS`.

CSV and JSON-array variants are supported too (see
`app/providers/property/adapters/admin_import.py`).

## Triggering ingestion

- Dev: `python workers/property_ingestion.py` from `backend/`
- Cron: `POST /api/v1/workers/run/property_ingestion` with header
  `X-Worker-Secret: <WORKER_RUN_SECRET>` (see `.env.example`).