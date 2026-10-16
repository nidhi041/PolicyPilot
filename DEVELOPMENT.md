# PolicyPilot Developer Workflow

This guide details the development workflow, setup, commands, and testing procedures for PolicyPilot.

## Prerequisites

- **Python**: 3.11+ (Python 3.14 supported)
- **Node.js**: 18+ (Node 24 LTS supported)
- **Git**

## Setup

### 1. Backend Setup

```bash
cd backend
py -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
cd ..
```

### 2. Frontend Setup

```bash
cd frontend
npm install --prefer-offline
cp .env.local.example .env.local
cd ..
```

## Running Development Servers

From the repository root:

- **Frontend** (`http://localhost:3000`):
  ```bash
  npm run dev:frontend
  ```
- **Backend** (`http://localhost:8000`, docs at `/docs`):
  ```bash
  npm run dev:backend
  ```

Alternatively, run each service directly from its own directory:
- Backend: `uvicorn app.main:app --reload --port 8000`
- Frontend: `npm run dev`

## Running Tests & Quality Checks

Run all checks from the root:

```bash
# Run entire test suite (frontend checks + backend tests)
npm test

# Run frontend checks (TypeScript validation & ESLint)
npm run test:frontend

# Run backend Pytest suite
npm run test:backend
```

Run directly in service subdirectories:
- **Backend tests**: `pytest backend` or `cd backend && pytest`
- **Frontend checks**: `cd frontend && npm test`

## Authentication Setup & Verification (Supabase Auth)

### 1. Environment Configuration
In `backend/.env`, configure your Supabase credentials:
```bash
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
DATABASE_URL=postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres
```

### 2. Verification Workflow & Commands
1. Client sends `Authorization: Bearer <token>`.
2. Backend validates identity against Supabase Auth (`/auth/v1/user`).
3. Backend retrieves or provisions the `Profile`. Browser-supplied roles/regions are ignored.

- **Missing credentials** (HTTP 401 `MISSING_CREDENTIALS`): `curl -i http://localhost:8000/api/v1/auth/me`
- **Valid token** (HTTP 200 with user & profile): `curl -i http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer <TOKEN>"`

### 3. Authorization Dependencies & Row Level Security (RLS)
FastAPI endpoints derive caller identity and permissions strictly from verified credentials and server-side profile data:
- `require_authenticated_user`: Verifies caller authentication and returns `AuthenticatedUser`.
- `require_employee`: Verifies active employee privileges.
- `require_hr_admin` / `require_hr_administrator`: Restricts access to verified HR administrators (`is_hr_administrator=True`). Unauthorized access returns HTTP 403 `FORBIDDEN`.
- `require_roles(*roles)`: Configurable role dependency factory.

Supabase PostgreSQL tables enforce Row Level Security (`profiles_select_own` and `profiles_update_own`), ensuring clients can only access their authorized profile rows.

## Environment & Git Hygiene

- Local environment files (`.env`, `.env.local`, `backend/.env`) are strictly gitignored.
- Uploaded policy documents (`uploads/`, `storage/`, `data/`, `*.pdf`), test coverage, and build artifacts are gitignored.
- Never commit credentials, private keys, or API secrets.
