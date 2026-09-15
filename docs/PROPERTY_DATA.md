# Property Data Architecture

> Every property in RealEstateGPT has clear provenance, quality signals,
> and verification status. No listing is ever presented as verified market
> inventory unless an admin has explicitly approved it.

---

## Data Provenance

Every property document includes:

| Field | Type | Purpose |
|-------|------|---------|
| `source` | `string` | Where the data came from (e.g., `seed_data`, `admin_import`) |
| `source_type` | `Literal["licensed_feed", "partner_api", "admin", "user", "demo"]` | Classification of the data source |
| `source_id` | `string?` | External identifier from the originating system |
| `is_synthetic` | `boolean` | `true` for demo/seed data, `false` for real listings |
| `last_verified_at` | `datetime?` | When the listing was last verified by an admin |
| `imported_at` | `datetime` | When the record entered the system (`created_at`) |

### Source Type Hierarchy

```
licensed_feed   → Data from a licensed property feed (e.g., MagicBricks API)
partner_api     → Data from a partner integration
admin           → Manually entered by an admin user
user            → User-submitted listing (requires verification)
demo            → Seed/synthetic data for development only
```

---

## Verification Status

| Status | Meaning |
|--------|---------|
| `unverified` | Default for all new listings, including seed data |
| `verified` | Admin has confirmed the listing is legitimate |
| `rejected` | Admin has rejected the listing |

### Rules

1. **Demo properties** (`is_synthetic=true`) can never be marked `verified`
   — enforced by a Pydantic model validator in `app/models/property.py`.
2. Only users with the `admin` role can change verification status
   — enforced by `get_current_admin` dependency in `app/api/v1/admin.py`.
3. Verification status is displayed on property cards in the frontend.

---

## Data Quality Score

Each property has a `data_quality_score` (0-100) computed from:

- Completeness of required fields (title, price, city, type)
- Presence of optional enrichment (description, images, amenities, coordinates)
- Area normalization (sqft/sqm/acre/hectare → standardized sqft)
- Image URL validation

The score is used as a ranking component in the search scoring engine
(`app/ai/scoring.py`, component key: `data_quality`).

---

## Property Model

The canonical property model is defined in `app/models/property.py`:

### Core Fields
- `id` (int) — atomic integer from MongoDB counter collection
- `title`, `description`, `slug` — content fields
- `price`, `currency` (default INR), `price_per_sqft`, `maintenance_charge`

### Classification
- `property_type` — apartment, villa, plot, studio, penthouse
- `listing_type` — sale, rent
- `construction_status` — ready, under_construction

### Location
- `address`, `locality`, `city`, `state`, `pincode`
- `latitude`, `longitude` → stored as GeoJSON Point in `location` field
- `2dsphere` index enables `$near` and `$geoWithin` queries

### Amenities
- Embedded array of `{id, name, category, icon}` objects
- Categories: lifestyle, safety, convenience, sustainability, sports, wellness

---

## Authorized Data Sources

Property inventory comes **only** from:

1. ✅ Licensed data feed
2. ✅ Partner API integration
3. ✅ Admin manual import
4. ✅ Seed data (explicitly marked `is_synthetic=true`, `source_type="demo"`)

**Never** from:
- ❌ Unauthorized web scraping
- ❌ LLM-generated property data
- ❌ User-submitted unverified data presented as verified

---

## Seed Data

The seed runner (`app/seed/seed_runner.py`) populates the database with
realistic demo properties across Indian cities. All seeded records are:

- `is_synthetic = true`
- `source = "seed_data"`
- `source_type = "demo"`
- `verification_status = "unverified"`
- `data_quality_score = 0.0`

The seed runner checks if properties already exist before inserting,
preventing duplicate seeding.

---

## Search Pipeline

Property search is **deterministic**, never LLM-driven:

```
User Query → Query Parser (regex/rule-based) → SearchIntent
  → MongoDB Filtering (indexes, geospatial)
  → Location Enrichment (bounded, ThreadPoolExecutor)
  → Deterministic Scoring (weighted components)
  → Ranked Results with Explainable Scores
```

The AI assistant uses `search_properties` tool which delegates to this
same deterministic pipeline. The LLM never constructs MongoDB queries
or re-ranks results.
