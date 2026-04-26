# CareGrid India Backend

FastAPI backend scaffold for CareGrid India, an agentic healthcare intelligence system for India using real Databricks-generated healthcare facility CSV files.

## Current Stage
CSV loading, validation, Pydantic models, facilities endpoints, stats endpoints, impact endpoints, search endpoint, and rule-based agent recommendation endpoint are implemented.

## Folder Structure
```text
backend/
  app/
    main.py
    config.py
    data_loader.py
    models.py
    routers/
  data/
  tests/
  docs/
  requirements.txt
  run.py
```

## Setup
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run Locally
```bash
python run.py
```

The API will run at http://localhost:8000.

## How To Run Tests
```bash
python -m pytest
```

## Data Files
Place the real CSV files in backend/data/ before running data-backed endpoints. The main source-of-truth dataset is caregrid_backend_export_full.csv.

On startup, the backend attempts to load and validate all expected CSV files. Missing files produce a clear warning during development instead of crashing the app immediately.

## Implemented Endpoints
- GET /health
- GET /facilities
- GET /facilities/meta/filters
- GET /facilities/{facility_id}
- GET /stats/overview
- GET /stats/trust-distribution
- GET /stats/readiness-distribution
- GET /stats/states
- GET /stats/facility-types
- GET /impact/trust-gap-summary
- GET /impact/priority-states
- GET /impact/state-risk-index
- GET /impact/facility-type-gap
- GET /search
- POST /agent/recommend

## Frontend Integration Files
- docs/FRONTEND_INTEGRATION_CONTRACT.md
- docs/ENDPOINT_EXAMPLES.md
- docs/QA_CHECKLIST.md

## Development Notes
- Do not use mock data as the final source once real CSVs are available.
- Do not rename schema columns, trust category values, or recommendation readiness values.
- Keep API responses stable for frontend compatibility.
- Keep combined_medical_evidence out of list responses and only return it from facility detail responses.
