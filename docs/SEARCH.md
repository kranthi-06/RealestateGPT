# Property discovery and search intelligence

## Pipeline

```text
Natural-language query
  -> deterministic parser
  -> validated SearchIntent
  -> MongoDB filters / 2dsphere candidate query (maximum 30 candidates)
  -> bounded OSM enrichment when requested
  -> deterministic ranking + evidence-backed reasons
  -> typed response
```

The parser never creates MongoDB syntax. `SearchIntent` contains only typed
filters such as city, price range, bedrooms, area, nearby requirements and an
optional commute destination. Unsupported or incomplete requirements are not
silently guessed.

## Query normalization

The deterministic parser recognizes BHK/bedrooms, `L`/lakh/lac, crore, INR,
rupee symbols, square feet, square metres, and nearby-place categories. Prices
are normalized to INR and areas to sq.ft. `90L` becomes `9,000,000`; `1.2
crore` becomes `12,000,000`.

## API

`POST /api/v1/ai/search` accepts:

```json
{ "query": "Find me a 3BHK under 90 lakhs near metro in Hyderabad", "limit": 12 }
```

It returns the parsed intent, database-filtered result count, ranked listings,
structured score components, fact-derived reasons, warnings and latency
metrics. The existing `GET /api/v1/properties` remains the filter-first,
paginated catalogue endpoint.

## Ranking

Scores are deterministic and capped at 100. Components are budget, location,
bedrooms, property type, amenities, area, nearby-place fit and property data
quality. Nearby distance reasons appear only when current OSM/Overpass data was
returned. Commute durations are OSRM route estimates, not live traffic.

## Performance and safety

MongoDB performs filter and radius selection. The service never loads the
whole property collection for natural-language ranking. Location enrichment is
limited to 12 candidates, with at most four concurrent OSM calls; commute
routes are limited to 10 candidates. Provider failures become warnings with no
fabricated distance or travel time. Raw MongoDB operators are discarded before
repository calls.
