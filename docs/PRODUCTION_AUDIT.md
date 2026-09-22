# RealEstateGPT — Production Audit Report

> Last audited: 2026-09-19

## Architecture

- **Frontend**: Next.js 16.3 (App Router, Turbopack) with React 19, Tailwind CSS v4, Shadcn UI
- **Backend**: FastAPI 0.115 with PyMongo (sync MongoDB driver)
- **Database**: MongoDB Atlas with 29+ indexes across 15 collections
- **AI**: Groq (qwen/qwen3.8-27b) with 10 bounded tools, MAX_STEPS=3, MAX_TOOLS=5
- **Location**: OpenStreetMap (Nominatim + Overpass + OSRM) with Leaflet frontend
- **Web Discovery**: Brave Search API → extraction → deduplication → ranking
- **Auth**: JWT + bcrypt, RBAC (user/admin)
- **Workers**: 7 background workers with distributed locks and run tracking

## Security Status

| Check | Status |
|-------|--------|
| JWT/bcrypt auth | ✅ |
| RBAC enforcement | ✅ |
| SSRF protection | ✅ |
| Security headers | ✅ |
| CORS configuration | ✅ |
| Rate limiting | ✅ |
| NoSQL injection prevention | ✅ |
| Secret exposure prevention | ✅ |
| Prompt injection defense | ✅ |
| Worker auth (hmac.compare_digest) | ✅ |

## Test Status

| Suite | Status |
|-------|--------|
| Backend pytest (165 tests) | 124 pass, 36 skip, 5 error (MongoDB-dependent) |
| Frontend ESLint | 0 errors, 6 warnings |
| Frontend TypeScript | Pass |
| Frontend build (Turbopack) | Pass |
| E2E (Playwright) | Infrastructure added |

## Known Limitations

1. Backend uses synchronous PyMongo in async FastAPI — acceptable for current scale
2. City/locality detection in query parser uses hardcoded lists (India-focused MVP)
3. Page enrichment disabled by default (intentional security choice)
4. No Prometheus/OpenTelemetry metrics endpoint yet
