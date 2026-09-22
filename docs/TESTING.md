# Testing

Run backend tests from `backend/`:

```text
py -3.13 -m pytest -q --disable-warnings -p no:langsmith
```

## Phase 4 AI tests

`backend/tests/test_groq_agent.py` covers gateway configuration/auth mapping,
closed-tool validation, bounded agent orchestration, structured output parsing,
and citation grounding with a deterministic fake transport. It does not claim a
live Groq result. A live Groq test requires a non-committed `GROQ_API_KEY` and
`AI_PROVIDER=groq`.

The MongoDB integration tests require `MONGODB_URI`; they are skipped only when
that variable is absent. They cover connection verification, property CRUD,
pagination, price/bedroom/city/locality/amenity filters, geospatial search,
invalid property validation, and admin-only property mutation API contracts.

Discovery tests cover lakh/crore/BHK/area/commute normalization, fact-derived
ranking, database-first natural search, and location-provider failure behavior
without fake distance fallbacks.

The Phase 3 live check created one clearly marked temporary demo property,
executed `Find me a 3BHK under 90 lakhs near metro in Hyderabad` through
MongoDB and current Overpass data, then removed the test record. It returned a
validated intent, one database candidate, a live metro distance, and only
fact-derived ranking reasons.

Run frontend checks from `frontend/`:

```text
npm run lint
npm run build
```

For browser smoke tests against an intentionally selected deployment:

```text
E2E_BASE_URL=https://your-deployment.vercel.app npx playwright test
```

The CI workflow must wait until Vercel reports that the deployment for the
tested commit is ready before running this command. Running it immediately
after a push can otherwise test the previous production artifact.

## Local service verification

Use an isolated MongoDB database for the complete backend suite; do not point
tests at a production Atlas database. The local SearXNG compose project is
development-only. A valid JSON response with zero results means the provider
was reached but supplied no listings; it must not be treated as a successful
property-inventory test.

External provider and deployed Vercel checks remain separate live tests. A
passing build alone never demonstrates deployed database, provider, or browser
functionality.
