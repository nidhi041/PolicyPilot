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

## Environment & Git Hygiene

- Local environment files (`.env`, `.env.local`, `backend/.env`) are strictly gitignored.
- Uploaded policy documents (`uploads/`, `storage/`, `data/`, `*.pdf`), test coverage, and build artifacts are gitignored.
- Never commit credentials, private keys, or API secrets.
