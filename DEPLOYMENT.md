# PolicyPilot Production Deployment Guide

This guide details deploying PolicyPilot to production using Supabase (PostgreSQL + pgvector + Private Storage), Render or Docker for the FastAPI backend, and Vercel for the Next.js frontend.

---

## 1. Managed Infrastructure: Supabase

### 1.1 Database Setup & Extensions
1. Create a Supabase project at [supabase.com](https://supabase.com).
2. In the Supabase SQL Editor, verify `vector` and `uuid-ossp` extensions:
   ```sql
   CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
   CREATE EXTENSION IF NOT EXISTS "vector";
   ```

### 1.2 Database Migrations
Run Alembic migrations against the Supabase PostgreSQL connection pooler (port 6543) or direct port (5432):
```bash
cd backend
export DATABASE_URL="postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres"
alembic upgrade head
```

### 1.3 Private Storage Bucket
1. In Supabase Dashboard -> Storage, create bucket: `policy-documents`.
2. Toggle **Public bucket: OFF** (private bucket).
3. Set max upload size to 10MB (`application/pdf`). Access is gated server-side via authenticated `/api/v1/storage/policies/...` endpoints.

---

## 2. Backend Deployment (Render / Container PaaS)

The backend provides a production ASGI runner via `Procfile` and `Dockerfile`.

### Configuration
- **Platform**: Render Web Service, Railway, or Docker
- **Root Directory**: `backend`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path**: `/health` (HTTP 200 = healthy, HTTP 503 = degraded)

### Environment Variables
Configure in the hosting provider dashboard (see [.env.example](.env.example)):
- `ENVIRONMENT`: `production`
- `DATABASE_URL`: `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres`
- `SUPABASE_URL`: `https://<ref>.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY`: Service role secret key
- `SUPABASE_ANON_KEY`: Anon public key
- `POLICY_STORAGE_BUCKET`: `policy-documents`
- `OPENAI_API_KEY`: API key for OpenAI / hosted LLM gateway
- `OPENAI_BASE_URL`: `https://api.openai.com/v1` (or hosted endpoint)
- `EMBEDDING_MODEL`: `text-embedding-3-small` (or configured embedding model)
- `LLM_MODEL`: `gpt-4o-mini`
- `CORS_ORIGINS`: `https://your-frontend.vercel.app` (restricts API traffic to frontend domain)

---

## 3. Frontend Deployment (Vercel)

Next.js frontend deploys natively on Vercel using [frontend/vercel.json](frontend/vercel.json).

### Configuration
- **Framework Preset**: Next.js
- **Root Directory**: `frontend`
- **Build Command**: `npm run build`
- **Output Directory**: `.next`

### Environment Variables
- `NEXT_PUBLIC_API_BASE_URL`: `https://your-backend.onrender.com`
- `NEXT_PUBLIC_SUPABASE_URL`: `https://<ref>.supabase.co`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Supabase anon public key

---

## 4. Production Smoke Verification Checklist

1. **Backend Health Probe**:
   ```bash
   curl -i https://your-backend.onrender.com/health
   # Expected: HTTP 200 {"status":"healthy","environment":"production","database":{"status":"ok"}}
   ```
2. **CORS Enforcement**:
   ```bash
   curl -i -X OPTIONS https://your-backend.onrender.com/health \
     -H "Origin: https://malicious.com" \
     -H "Access-Control-Request-Method: GET"
   # Expected: No Access-Control-Allow-Origin header returned
   ```
3. **Frontend Build & Rendering**:
   Verify frontend routes render without SSR errors: `/`, `/chat`, `/policies`, `/analytics`, `/login`.
