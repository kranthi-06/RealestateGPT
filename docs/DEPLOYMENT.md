# Deployment Guide

> **RealEstateGPT** is deployed as a dual-service application on Vercel:
> Next.js frontend + FastAPI backend, both served from a single repository.

---

## Architecture Overview

```
Browser → Vercel Edge → Next.js (frontend)
                      → FastAPI (backend) → MongoDB Atlas
                                          → Groq API
                                          → OSM / Nominatim / Overpass / OSRM
```

The `vercel.json` at the repository root configures two builds:
- **Frontend**: Next.js app at `frontend/`
- **Backend**: FastAPI app at `backend/app/main.py`

All `/api/backend/*` requests are rewritten to the Python backend.

---

## Prerequisites

| Requirement | Purpose |
|-------------|---------|
| **Vercel account** | Hosting (free tier works) |
| **MongoDB Atlas cluster** | Production database |
| **Groq API key** | LLM provider for the AI assistant |
| **Node.js 20+** | Frontend build |
| **Python 3.11+** | Backend runtime |

---

## Environment Variables

### Backend (Vercel → Environment Variables)

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGODB_URI` | ✅ | MongoDB Atlas connection string |
| `MONGODB_DATABASE` | ✅ | Database name (default: `realestate_gpt`) |
| `SECRET_KEY` | ✅ | Random 32+ character string for JWT signing |
| `GROQ_API_KEY` | ✅ | Groq API key for AI assistant |
| `GROQ_MODEL` | ❌ | Model name (default: `qwen/qwen3.8-27b`) |
| `APP_ENV` | ❌ | `production` enables strict validation |
| `CORS_ORIGINS` | ❌ | Comma-separated allowed origins |
| `LOCATION_PROVIDER` | ❌ | `osm` (default) or `google` |

### Frontend (Vercel → Environment Variables)

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | ✅ | Backend API URL (e.g., `https://your-app.vercel.app`) |

> **⚠️ Security**: Never prefix backend secrets with `NEXT_PUBLIC_`.
> Only `NEXT_PUBLIC_API_URL` should be browser-visible.

---

## Vercel Deployment

### 1. Connect Repository

```bash
vercel link
```

### 2. Set Environment Variables

```bash
vercel env add MONGODB_URI production
vercel env add SECRET_KEY production
vercel env add GROQ_API_KEY production
vercel env add NEXT_PUBLIC_API_URL production
```

### 3. Deploy

```bash
vercel --prod
```

### 4. Seed Database (first deployment only)

```bash
cd backend
python -m app.seed.seed_runner
```

---

## Local Development

### Backend

```bash
cd backend
cp .env.example .env
# Edit .env with your MongoDB URI, Groq key, etc.
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
cp .env.example .env.local
# Edit .env.local: NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev
```

### Full Stack

1. Start backend on port 8000
2. Start frontend on port 3000
3. Open http://localhost:3000

---

## MongoDB Atlas Setup

1. Create a free M0 cluster at [cloud.mongodb.com](https://cloud.mongodb.com)
2. Create a database user with read/write access
3. Whitelist your IP (or `0.0.0.0/0` for Vercel)
4. Copy the connection string to `MONGODB_URI`
5. The application creates all indexes on first startup via `ensure_indexes()`

### Required Indexes (auto-created)

- `users`: unique on `email`
- `properties`: compound on `city`, `property_type`, `listing_type`, `price`;
  `2dsphere` on `location`; text on `title`, `description`
- `saved_properties`: compound on `user_id`, `property_id`
- `conversations`: on `user_id`
- `audit_logs`: on `created_at`

---

## Verification Checklist

After deployment, verify each system:

- [ ] `GET /api/v1/health` returns `{"status": "ok"}`
- [ ] `GET /api/v1/properties?page=1` returns property listing
- [ ] `POST /api/v1/auth/login` returns JWT token
- [ ] `POST /api/v1/ai/search` returns grounded search results
- [ ] `POST /api/v1/ai/assistant` returns tool-backed AI response
- [ ] Frontend loads at root URL with featured properties
- [ ] Search page filters and paginates correctly
- [ ] Property detail page shows map with Leaflet
- [ ] AI assistant responds with citations
