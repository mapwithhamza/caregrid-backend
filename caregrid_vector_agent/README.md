# caregrid_vector_agent

Standalone AI agent intelligence package for **CareGrid India**.

## What it does
- Parses natural language queries about healthcare facilities in India
- Retrieves relevant facility records via **Databricks Mosaic AI Vector Search** (or local fallback)
- Builds structured evidence from `combined_medical_evidence` fields
- Validates, scores, and recommends facilities based on `trust_score`
- Optionally verifies shortlisted facilities via **Tavily** external web search
- Traces every agent run with **MLflow**

## Architecture
- Vector DB: Databricks Mosaic AI Vector Search
- No graph database, no FastAPI, no frontend
- Tavily is optional — agent works fully without it
- Local fallback retriever requires no external services

## Setup

```bash
cp .env.example .env
# Fill in your Databricks and Tavily credentials

pip install -r requirements.txt
```

## Run tests

```bash
pytest tests/ -v
```

## Key files
- `CURSOR.md` — full project context for AI assistants
- `config/settings.py` — all configuration via pydantic-settings
- `agent_core/` — all agent logic modules
- `docs/PROGRESS.md` — current development progress

## Data contract
- Primary key: `facility_id`
- Evidence field: `combined_medical_evidence`
- Do not rename: `trust_score`, `trust_category`, `recommendation_readiness`
