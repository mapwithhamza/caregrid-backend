# CareGrid India Backend Progress

## Current Stage
Final backend QA and integration contract completed.

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
