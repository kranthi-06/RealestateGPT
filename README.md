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

The root `vercel.json` defines two services: `frontend` (Next.js) and `backend` (FastAPI). Import the repository as a multi-service deployment so Vercel uses that configuration. The backend is available through `/api/backend/*`, while all other routes go to the frontend.

Add this environment variable in the Vercel project settings:

```text
NEXT_PUBLIC_API_URL=https://your-deployed-backend.example.com
```

Configure the backend service environment variables from `backend/.env.example`. Its CORS configuration must include the deployed Vercel URL. If the platform provides a separate backend service URL, use that URL for `NEXT_PUBLIC_API_URL`; otherwise use the `/api/backend` route exposed by the multi-service deployment.