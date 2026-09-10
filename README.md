# RealestateGPT

RealestateGPT is a real-estate search application with a Next.js frontend and a FastAPI backend.

## Local development

### Frontend

```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to the backend URL when it is not running on `http://localhost:8000`.

## Vercel deployment

The Vercel project should use `frontend` as its **Root Directory**. Vercel will detect Next.js and use `npm run build` automatically.

Add this environment variable in the Vercel project settings:

```text
NEXT_PUBLIC_API_URL=https://your-deployed-backend.example.com
```

The FastAPI backend must be deployed separately on a Python-capable host, and its CORS configuration must include the deployed Vercel URL.