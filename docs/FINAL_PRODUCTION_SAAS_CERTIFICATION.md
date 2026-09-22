{
  "base_url": "https://realestate-gpt-inky.vercel.app",
  "started_at": "2026-09-22T15:41:15.244652+00:00",
  "finished_at": "2026-09-22T15:42:00.204664+00:00",
  "summary": {
    "PASS": 39,
    "FAIL": 5,
    "WARN": 2,
    "SKIP": 0
  },
  "latency_ms": {
    "count": 46,
    "min": 79.6,
    "median": 446.5,
    "max": 14385.1
  },
  "notes": [
    "Checks are performed against the real deployment. Optional integrations that are not configured are reported as WARN, never as PASS and never as fake data.",
    "health snapshot: {\"version\": \"1.1.0\", \"status\": \"healthy\", \"database\": \"healthy\", \"ai_configured\": true, \"ai_provider\": \"groq\", \"location_provider\": \"osm\", \"web_search\": {\"configured\": null, \"enabled\": null, \"status\": null, \"provider\": null}, \"property_provider\": \"\", \"property_provider_configured\": false}"
  ],
  "checks": [
    {
      "name": "frontend Landing page",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/",
      "status": 200,
      "latency_ms": 485.1,
      "outcome": "PASS",
      "auth": "public",
      "detail": "Landing page",
      "extra": {}
    },
    {
      "name": "frontend Search",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/search",
      "status": 200,
      "latency_ms": 110.0,
      "outcome": "PASS",
      "auth": "public",
      "detail": "Search",
      "extra": {}
    },
    {
      "name": "frontend Login",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/auth/login",
      "status": 200,
      "latency_ms": 88.6,
      "outcome": "PASS",
      "auth": "public",
      "detail": "Login",
      "extra": {}
    },
    {
      "name": "frontend Register",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/auth/register",
      "status": 200,
      "latency_ms": 100.2,
      "outcome": "PASS",
      "auth": "public",
      "detail": "Register",
      "extra": {}
    },
    {
      "name": "frontend AI assistant",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/assistant",
      "status": 200,
      "latency_ms": 84.5,
      "outcome": "PASS",
      "auth": "public",
      "detail": "AI assistant",
      "extra": {}
    },
    {
      "name": "frontend Saved properties",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/saved",
      "status": 200,
      "latency_ms": 93.3,
      "outcome": "PASS",
      "auth": "public",
      "detail": "Saved properties",
      "extra": {}
    },
    {
      "name": "frontend Compare",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/compare",
      "status": 200,
      "latency_ms": 90.6,
      "outcome": "PASS",
      "auth": "public",
      "detail": "Compare",
      "extra": {}
    },
    {
      "name": "frontend Admin",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/admin",
      "status": 404,
      "latency_ms": 86.4,
      "outcome": "FAIL",
      "auth": "public",
      "detail": "expected (200,) -> got 404",
      "extra": {}
    },
    {
      "name": "frontend robots.txt",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/robots.txt",
      "status": 404,
      "latency_ms": 79.6,
      "outcome": "FAIL",
      "auth": "public",
      "detail": "expected (200,) -> got 404",
      "extra": {}
    },
    {
      "name": "frontend sitemap.xml",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/sitemap.xml",
      "status": 404,
      "latency_ms": 99.4,
      "outcome": "FAIL",
      "auth": "public",
      "detail": "expected (200,) -> got 404",
      "extra": {}
    },
    {
      "name": "landing metadata",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/",
      "status": 200,
      "latency_ms": 134.2,
      "outcome": "PASS",
      "auth": "public",
      "detail": "no placeholder domain in canonical/OG",
      "extra": {
        "placeholder_domain_present": false
      }
    },
    {
      "name": "health",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/health",
      "status": 200,
      "latency_ms": 14385.1,
      "outcome": "PASS",
      "auth": "public",
      "detail": "status=healthy version=1.1.0",
      "extra": {
        "status": "healthy",
        "timestamp": "2026-09-22T15:41:30.682968+00:00",
        "service": "RealEstateGPT API",
        "version": "1.1.0"
      }
    },
    {
      "name": "health db (MongoDB Atlas)",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/health/db",
      "status": 200,
      "latency_ms": 613.2,
      "outcome": "PASS",
      "auth": "public",
      "detail": "{\"status\": \"healthy\", \"database\": \"mongodb\"}",
      "extra": {}
    },
    {
      "name": "health ai (Groq)",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/health/ai",
      "status": 200,
      "latency_ms": 409.4,
      "outcome": "PASS",
      "auth": "public",
      "detail": "provider=groq configured=True",
      "extra": {}
    },
    {
      "name": "health location (OSM)",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/health/location",
      "status": 200,
      "latency_ms": 410.7,
      "outcome": "PASS",
      "auth": "public",
      "detail": "provider=osm",
      "extra": {}
    },
    {
      "name": "health web-search",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/health/web-search",
      "status": 404,
      "latency_ms": 298.8,
      "outcome": "WARN",
      "auth": "public",
      "detail": "provider=None configured=None enabled=None status=None",
      "extra": {}
    },
    {
      "name": "workers status",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/workers/status",
      "status": 200,
      "latency_ms": 1341.2,
      "outcome": "PASS",
      "auth": "public",
      "detail": "provider='' configured=False",
      "extra": {}
    },
    {
      "name": "workers run without secret (must be 401)",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/workers/run/stale_listing_worker",
      "status": 401,
      "latency_ms": 303.3,
      "outcome": "PASS",
      "auth": "none",
      "detail": "",
      "extra": {}
    },
    {
      "name": "workers runs list without admin (must be 403)",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/workers/runs?worker_name=stale_listing_worker",
      "status": 403,
      "latency_ms": 512.4,
      "outcome": "PASS",
      "auth": "none",
      "detail": "",
      "extra": {}
    },
    {
      "name": "register weak password (must be 422)",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/auth/register",
      "status": 422,
      "latency_ms": 411.9,
      "outcome": "PASS",
      "auth": "public",
      "detail": "",
      "extra": {}
    },
    {
      "name": "register",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/auth/register",
      "status": 201,
      "latency_ms": 1432.8,
      "outcome": "PASS",
      "auth": "none",
      "detail": "account=prod-verify-8d5ebed34daf@example.com",
      "extra": {
        "email": "prod-verify-8d5ebed34daf@example.com"
      }
    },
    {
      "name": "register duplicate (must be 409)",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/auth/register",
      "status": 409,
      "latency_ms": 818.6,
      "outcome": "PASS",
      "auth": "none",
      "detail": "",
      "extra": {}
    },
    {
      "name": "login wrong password (must be 401)",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/auth/login",
      "status": 401,
      "latency_ms": 817.9,
      "outcome": "PASS",
      "auth": "none",
      "detail": "",
      "extra": {}
    },
    {
      "name": "login",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/auth/login",
      "status": 200,
      "latency_ms": 826.8,
      "outcome": "PASS",
      "auth": "none",
      "detail": "role=user",
      "extra": {}
    },
    {
      "name": "me without token (must be 401)",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/auth/me",
      "status": 401,
      "latency_ms": 308.9,
      "outcome": "PASS",
      "auth": "none",
      "detail": "",
      "extra": {}
    },
    {
      "name": "me with forged token (must be 401)",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/auth/me",
      "status": 401,
      "latency_ms": 502.0,
      "outcome": "PASS",
      "auth": "invalid",
      "detail": "",
      "extra": {}
    },
    {
      "name": "me with valid token",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/auth/me",
      "status": 200,
      "latency_ms": 614.1,
      "outcome": "PASS",
      "auth": "bearer",
      "detail": "",
      "extra": {}
    },
    {
      "name": "admin stats as normal user (must be 403)",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/admin/stats",
      "status": 403,
      "latency_ms": 819.2,
      "outcome": "PASS",
      "auth": "bearer",
      "detail": "",
      "extra": {}
    },
    {
      "name": "admin users as normal user (must be 403)",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/admin/users",
      "status": 403,
      "latency_ms": 613.6,
      "outcome": "PASS",
      "auth": "bearer",
      "detail": "",
      "extra": {}
    },
    {
      "name": "create property as normal user (must be 403)",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/properties",
      "status": 403,
      "latency_ms": 481.1,
      "outcome": "PASS",
      "auth": "bearer",
      "detail": "",
      "extra": {}
    },
    {
      "name": "natural language parse",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/search/parse?q=2BHK%20under%2030k%20rent%20in%20Hyderabad",
      "status": 404,
      "latency_ms": 338.2,
      "outcome": "FAIL",
      "auth": "public",
      "detail": "city=None bedrooms=None listing_type=None max_price=None",
      "extra": {}
    },
    {
      "name": "dynamic result sections",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/search/sections?q=apartment",
      "status": 200,
      "latency_ms": 2155.3,
      "outcome": "PASS",
      "auth": "public",
      "detail": "",
      "extra": {}
    },
    {
      "name": "property list",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/properties?page=1&page_size=5&sort_by=created_at&sort_order=desc",
      "status": 200,
      "latency_ms": 712.6,
      "outcome": "PASS",
      "auth": "public",
      "detail": "",
      "extra": {}
    },
    {
      "name": "featured properties",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/properties/featured?limit=6",
      "status": 200,
      "latency_ms": 613.8,
      "outcome": "PASS",
      "auth": "public",
      "detail": "",
      "extra": {}
    },
    {
      "name": "property not found (must be 404)",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/properties/999999999",
      "status": 404,
      "latency_ms": 819.0,
      "outcome": "PASS",
      "auth": "public",
      "detail": "",
      "extra": {}
    },
    {
      "name": "property validation (must be 422)",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/properties?min_price=abc",
      "status": 422,
      "latency_ms": 307.9,
      "outcome": "PASS",
      "auth": "public",
      "detail": "",
      "extra": {}
    },
    {
      "name": "near-me",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/search/near-me",
      "status": 200,
      "latency_ms": 703.7,
      "outcome": "PASS",
      "auth": "public",
      "detail": "",
      "extra": {}
    },
    {
      "name": "near-me out of range (must be 422)",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/search/near-me",
      "status": 422,
      "latency_ms": 329.7,
      "outcome": "PASS",
      "auth": "public",
      "detail": "",
      "extra": {}
    },
    {
      "name": "unified search",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/search",
      "status": 404,
      "latency_ms": 328.8,
      "outcome": "FAIL",
      "auth": "public",
      "detail": "verified and web result lists are not separated",
      "extra": {
        "metadata": {}
      }
    },
    {
      "name": "geocode (Nominatim)",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/locations/geocode",
      "status": 200,
      "latency_ms": 581.4,
      "outcome": "PASS",
      "auth": "public",
      "detail": "",
      "extra": {}
    },
    {
      "name": "location provider status",
      "method": "GET",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/locations/status",
      "status": 200,
      "latency_ms": 306.8,
      "outcome": "PASS",
      "auth": "public",
      "detail": "",
      "extra": {}
    },
    {
      "name": "finance EMI",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/finance/emi",
      "status": 200,
      "latency_ms": 409.0,
      "outcome": "PASS",
      "auth": "public",
      "detail": "monthly_emi=43391.16 expected=43391.16",
      "extra": {
        "monthly_emi": 43391.16,
        "expected_monthly_emi": 43391.16
      }
    },
    {
      "name": "finance affordability",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/finance/affordability",
      "status": 200,
      "latency_ms": 409.7,
      "outcome": "PASS",
      "auth": "public",
      "detail": "",
      "extra": {}
    },
    {
      "name": "finance rental yield",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/finance/rental-yield",
      "status": 200,
      "latency_ms": 512.4,
      "outcome": "PASS",
      "auth": "public",
      "detail": "",
      "extra": {}
    },
    {
      "name": "ai search",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/ai/search",
      "status": 200,
      "latency_ms": 1433.1,
      "outcome": "PASS",
      "auth": "public",
      "detail": "",
      "extra": {}
    },
    {
      "name": "ai assistant (Groq tool-calling)",
      "method": "POST",
      "url": "https://realestate-gpt-inky.vercel.app/api/backend/api/v1/ai/assistant",
      "status": 429,
      "latency_ms": 7169.0,
      "outcome": "WARN",
      "auth": "bearer",
      "detail": "provider=None tools=0 chars=0",
      "extra": {
        "error_code": "AI_RATE_LIMIT_ERROR"
      }
    }
  ]
}