# CareGrid India Backend Progress

## Current Stage
**Stage 19 — Standalone CareGrid Vector Agent integrated into the
FastAPI backend.** The completed standalone agent (Stages 1–18, 493
passing tests, real Databricks Vector Search + real Tavily smokes done)
is shipped inside this repo at `caregrid_vector_agent/` and is wired
into `POST /agent/recommend` through a thin adapter at
`app/services/caregrid_agent_service.py`. The backend boots, loads the
10,000-row CSV exactly once via `data_store.load_facilities()`, and
hands the dataframe directly to
`agent_core.recommendation_engine.run_recommendation()` — no second
read, no duplicated data on disk. Vector search and Tavily verification
are both backend-side opt-ins controlled by environment variables;
missing credentials never crash the route. If the standalone agent
fails to import or raises at runtime, the route automatically falls
back to the original simple recommender (`engine: "simple_legacy_fallback"`)
and surfaces a short safe error in `trace_summary.errors`. The original
Stage-1 response shape is preserved 1:1 for frontend compatibility;
new optional fields (`retrieval_summary`, `trace_summary`,
`evidence_snippets`, `validation_findings`, `score_breakdown`,
`web_verification`, `human_next_steps`, `engine`) are additive under
`extra="allow"` on the Pydantic model. Smoke checks completed:
`/health` returns `data_loaded=true`, `facility_rows=10000`;
`POST /agent/recommend` with a Bihar ICU query returns
`engine="caregrid_vector_agent"`, all 8 trace stages, full retrieval
summary (`local_count=164`, `merged_count=164`, vector + Tavily off
by default), and a populated safety note. Files added/changed:
`caregrid_vector_agent/` (full agent package, ~1.2 MB minus the
duplicate CSV),
`app/services/caregrid_agent_service.py` (NEW),
`app/routers/agent.py` (advanced-first, simple-fallback),
`app/models.py` (Stage-19 fields under `extra="allow"`),
`requirements.txt` (added `pydantic-settings`,
`databricks-vectorsearch>=0.40`, `tavily-python>=0.3.0`),
`.env.example` (placeholders for all `DATABRICKS_*` and `TAVILY_*`
keys; no secrets), `.gitignore` (extra rules to keep
`caregrid_vector_agent/.env`, `data/raw/*.csv`, caches, and proof zip
out of git), `README.md` (combined backend + agent docs).

## Stage 18 (within `caregrid_vector_agent/`) — completed before this
Real combined Vector + Tavily smoke proven against the live Databricks
endpoint and live Tavily API. See
`caregrid_vector_agent/docs/COMBINED_AGENT_SMOKE_TEST.md` and the
`data/outputs/combined_vector_tavily_*.{json,md}` proof files.

## Stage 19 next step
Frontend remains AI-ready and continues to call only the backend. No
frontend release required. If the team wants to surface the new
`evidence_snippets` / `score_breakdown` / `web_verification` panels in
the UI, the data is already on the response and just needs rendering.

## Pre-Stage-19 marker
Final backend QA and integration contract completed (pre-Stage-19).

## Completed Before Backend
- Databricks raw dataset loaded.
- Data audit and cleaning completed.
- Clean table created.
- V2 trust scoring completed.
- State normalization completed.
- Backend export table created.
- Backend/frontend package created.
- Plan A handoff file created.
- Impact/desert analysis package created.
- Stages 1 – 18 of the standalone CareGrid Vector Agent (delivered
  inside `caregrid_vector_agent/`).

## Current Backend Task
Prompt 9 — Final Backend QA and Integration Contract.

## Completed Backend
- Backend scaffold setup.
- Context documentation created.
- CSV filename constants created.
- Required facility schema contract added in config.
- Expected CSV row counts added.
- DataStore class implemented.
- All required CSV files load from backend/data/.
- In-memory DataFrame caching implemented.
- Main facility schema validation implemented.
- Facility row count, ID uniqueness, required values, category values, coordinates, and trust_score validation implemented.
- Startup data validation added with development-safe warnings for missing files.
- Health endpoint reports service, version, data load status, and facility rows when loaded.
- Pydantic response models added for facility list, detail, pagination, and filter metadata.
- GET /facilities implemented with pagination, filters, sorting, and trust score range validation.
- GET /facilities/meta/filters implemented for frontend filter values.
- GET /facilities/{facility_id} implemented with full detail response.
- Facilities API tests added against real CSV-backed responses.
- PIN code response serialization now removes safe trailing .0 display artifacts without changing source CSV data.
- Prompt 5 — Stats Endpoints completed.
- GET /stats/overview implemented from caregrid_final_dashboard_overview.csv.
- GET /stats/trust-distribution implemented from caregrid_final_trust_distribution.csv.
- GET /stats/readiness-distribution implemented from caregrid_final_readiness_distribution.csv.
- GET /stats/states implemented with sort_by, order, and limit query parameters.
- GET /stats/facility-types implemented from caregrid_final_facility_type_summary.csv.
- Stats API tests added for overview, distributions, state summaries, invalid query handling, and facility type summaries.
- Prompt 6 — Impact Endpoints completed.
- GET /impact/trust-gap-summary implemented from caregrid_desert_trust_gap_summary.csv.
- GET /impact/priority-states implemented from caregrid_desert_calibrated_priority_ranking.csv.
- GET /impact/state-risk-index implemented with filters, sorting, and limit query parameters.
- GET /impact/facility-type-gap implemented with risk-level filtering and sort parameters.
- Impact API tests added for summary, priority states, state risk index, invalid query handling, and facility type gap.
- Prompt 7 — Search Endpoint completed.
- GET /search implemented against caregrid_backend_export_full.csv.
- Search supports q, state, facility_type, trust_category, recommendation_readiness, min_trust_score, and limit parameters.
- Search relevance scoring, matched fields, and warning flags implemented.
- Search results keep combined_medical_evidence out of response payloads.
- Search API tests added for filtering, validation, scoring metadata, and compact payloads.
- Prompt 8 — Agent Recommendation Endpoint completed.
- POST /agent/recommend implemented as a transparent rule-based recommendation agent.
- Intent extraction added for care capabilities, trust preference, safe/recommend intent, nearby intent, and state detection.
- Agent recommendations rank real facilities by trust score, readiness, matched capabilities, field matches, and warning penalties.
- Agent responses include interpreted_intent, reasoning, safety_note, fallback_message, and per-facility recommendation explanations.
- Agent API tests added for validation, filtering, recommendation payloads, fallback behavior, and safety note.

### Prompt 8B — Facility-Type Intent Patch
- Fixed issue where queries such as "Find emergency hospitals" could return clinics because hospital was treated only as a text term.
- Added query facility-type intent detection for hospital, clinic, doctor, and pharmacy.
- Request body facility_type now takes priority over query-detected facility type.
- Agent reasoning and interpreted_intent now include the applied facility_type filter.
- Fallback behavior can relax facility_type filtering when strict matching finds no recommendations.
- python -m pytest: 66 passed, 2 warnings.

### Prompt 9 — Final Backend QA and Integration Contract
- Final backend QA documentation completed.
- docs/FRONTEND_INTEGRATION_CONTRACT.md created for frontend assumptions, endpoint groups, and component usage.
- docs/ENDPOINT_EXAMPLES.md created with real local endpoint examples.
- docs/QA_CHECKLIST.md created with data loading, API, schema stability, frontend integration, and known limitations checks.
- README updated with implemented endpoints, test command, and frontend integration files.
- /health now includes endpoints_ready and tests_expected metadata.
- Integration contract smoke tests added for health, OpenAPI, stats, impact, search, and agent routes.
- python -m pytest: 72 passed, 2 warnings.

## Not Yet Done
- Deployment setup.

## Next Step
Frontend implementation or deployment preparation.

## Latest Test Result
- python -m pytest: 72 passed, 2 warnings.

## Rules
- Do not rename schema columns.
- Do not rename trust category values.
- Do not rename recommendation readiness values.
- Do not use mock data as final source.
- Use caregrid_backend_export_full.csv as main source of truth.
- Update this file after each completed prompt/task.
