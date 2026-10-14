# PolicyPilot Backend

FastAPI backend service for PolicyPilot AI.

## Virtual Environment Setup

```bash
# Using Python 3.11+
py -m venv .venv

# Activate on Windows PowerShell
.venv\Scripts\Activate.ps1

# Or activate on Linux/macOS
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Running the Development Server

```bash
uvicorn app.main:app --reload --port 8000
```

## Running Tests

```bash
pytest
```
