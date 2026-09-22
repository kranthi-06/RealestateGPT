# API Endpoint Matrix

| Endpoint | Method | Auth | Role | Success | Failure | DB Effect | Notes |
|----------|--------|------|------|---------|---------|-----------|-------|
| `/` | GET | No | Any | 200 | - | None | App info |
| `/api/v1/health` | GET | No | Any | 200 | 503 | Read | MongoDB ping |
| `/api/v1/auth/register` | POST | No | Any | 200 | 400,409 | Write | Creates user |
| `/api/v1/auth/login` | POST | No | Any | 200 | 401 | Read | Issues JWT |
| `/api/v1/auth/me` | GET | Yes | Any | 200 | 401 | Read | Profile |
| `/api/v1/auth/me` | PUT | Yes | Any | 200 | 401,422 | Write | Update profile |
| `/api/v1/properties` | GET | No | Any | 200 | 422 | Read | Paginated list |
| `/api/v1/properties` | POST | Yes | Admin | 201 | 401,403,422 | Write | Create property |
| `/api/v1/properties/featured` | GET | No | Any | 200 | - | Read | Featured list |
| `/api/v1/properties/cities` | GET | No | Any | 200 | - | Read | City list |
| `/api/v1/properties/localities` | GET | No | Any | 200 | 422 | Read | Locality list |
| `/api/v1/properties/bulk` | POST | No | Any | 200 | 422 | Read | Bulk fetch |
| `/api/v1/properties/{id}` | GET | Opt | Any | 200 | 404 | Read | Property detail |
| `/api/v1/properties/{id}` | PATCH | Yes | Admin | 200 | 401,403,404 | Write | Update property |
| `/api/v1/properties/{id}` | DELETE | Yes | Admin | 200 | 401,403,404 | Write | Delete property |
| `/api/v1/properties/{id}/similar` | GET | No | Any | 200 | 404 | Read | Similar properties |
| `/api/v1/properties/{id}/price-intelligence` | GET | No | Any | 200 | 404 | Read | Price history |
| `/api/v1/search` | POST | Opt | Any | 200 | 422 | Read+Write | Unified search |
| `/api/v1/search/parse` | GET | No | Any | 200 | 422 | None | Parse intent |
| `/api/v1/search/near-me` | POST | No | Any | 200 | 422 | Read | Geo search |
| `/api/v1/search/sections` | GET | Opt | Any | 200 | - | Read | Dynamic sections |
| `/api/v1/search/discoveries/{id}` | GET | Opt | Any | 200 | 404 | Read | Discovery detail |
| `/api/v1/search/discoveries/{id}/save` | POST | Yes | Any | 200 | 401,404 | Write | Save discovery |
| `/api/v1/search/discoveries/{id}/save` | DELETE | Yes | Any | 200 | 401,404 | Write | Unsave discovery |
| `/api/v1/saved/properties` | POST | Yes | Any | 200 | 401,409 | Write | Save property |
| `/api/v1/saved/properties` | GET | Yes | Any | 200 | 401 | Read | List saved |
| `/api/v1/saved/properties/{id}` | DELETE | Yes | Any | 200 | 401,404 | Write | Unsave property |
| `/api/v1/saved/searches` | POST | Yes | Any | 200 | 401 | Write | Save search |
| `/api/v1/saved/searches` | GET | Yes | Any | 200 | 401 | Read | List searches |
| `/api/v1/saved/searches/{id}` | DELETE | Yes | Any | 200 | 401,404 | Write | Delete search |
| `/api/v1/saved/comparisons` | POST | Yes | Any | 200 | 401 | Write | Save comparison |
| `/api/v1/saved/comparisons` | GET | Yes | Any | 200 | 401 | Read | List comparisons |
| `/api/v1/saved/comparisons/{id}` | GET | Yes | Any | 200 | 401,404 | Read | Get comparison |
| `/api/v1/saved/comparisons/{id}` | DELETE | Yes | Any | 200 | 401,404 | Write | Delete comparison |
| `/api/v1/ai/search` | POST | Yes | Any | 200 | 401,422 | Read | AI search |
| `/api/v1/ai/assistant` | POST | Yes | Any | 200 | 401,422 | Write | AI assistant |
| `/api/v1/ai/conversations` | GET | Yes | Any | 200 | 401 | Read | List conversations |
| `/api/v1/finance/emi` | POST | No | Any | 200 | 422 | None | EMI calculator |
| `/api/v1/finance/affordability` | POST | No | Any | 200 | 422 | None | Affordability |
| `/api/v1/finance/rental-yield` | POST | No | Any | 200 | 422 | None | Rental yield |
| `/api/v1/finance/roi` | POST | No | Any | 200 | 422 | None | ROI projection |
| `/api/v1/finance/properties/{id}/estimate` | GET | No | Any | 200 | 404 | Read | Price estimate |
| `/api/v1/finance/properties/{id}/fairness` | GET | No | Any | 200 | 404 | Read | Price fairness |
| `/api/v1/locations/status` | GET | No | Any | 200 | - | None | Map status |
| `/api/v1/locations/properties/{id}/nearby` | GET | Opt | Any | 200 | 404 | Read | Nearby places |
| `/api/v1/locations/places/{id}` | GET | Opt | Any | 200 | 404 | Read | Place detail |
| `/api/v1/locations/geocode` | POST | Opt | Any | 200 | 422 | Read+Write | Geocode |
| `/api/v1/locations/routes` | POST | Opt | Any | 200 | 422 | None | Route calc |
| `/api/v1/admin/stats` | GET | Yes | Admin | 200 | 401,403 | Read | Dashboard stats |
| `/api/v1/admin/users` | GET | Yes | Admin | 200 | 401,403 | Read | User list |
| `/api/v1/admin/users/{id}` | PATCH | Yes | Admin | 200 | 401,403,404 | Write | Update user |
| `/api/v1/admin/properties` | GET | Yes | Admin | 200 | 401,403 | Read | All properties |
| `/api/v1/admin/properties/{id}/verify` | PUT | Yes | Admin | 200 | 401,403,404 | Write | Verify property |
| `/api/v1/admin/audit-logs` | GET | Yes | Admin | 200 | 401,403 | Read | Audit logs |
| `/api/v1/admin/ai-usage` | GET | Yes | Admin | 200 | 401,403 | Read | AI usage stats |
| `/api/v1/workers/status` | GET | No | Any | 200 | - | Read | Worker status |
| `/api/v1/workers/runs` | GET | No | Any | 200 | - | Read | Worker runs |
| `/api/v1/workers/run/{name}` | POST | Secret/Admin | Admin | 200 | 401,403,404 | Write | Trigger worker |
