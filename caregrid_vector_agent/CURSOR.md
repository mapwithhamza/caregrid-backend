# CareGrid Vector Agent — Cursor Context

## Project Identity
- **Project name:** caregrid_vector_agent
- **Organisation:** CareGrid India
- **Purpose:** Standalone AI agent intelligence package — NOT part of any backend app or frontend.
- **Layer:** Agent intelligence layer only (no FastAPI, no REST endpoints, no UI).

---

## What This Package Does
CareGrid India is an agentic healthcare intelligence system.
This package builds the **agent intelligence layer** responsible for:
- Parsing user intent / queries about healthcare facilities in India
- Retrieving relevant facility records via Databricks Mosaic AI Vector Search (primary) or local fallback
- Building structured evidence from `combined_medical_evidence` text fields
- Validating evidence against contradiction rules
- Scoring and recommending facilities using trust scores
- Optionally verifying shortlisted facilities via Tavily external web search
- Tracing all agent decisions with MLflow

---

## Architecture Rules
| Rule | Detail |
|------|--------|
| Vector DB | **Databricks Mosaic AI Vector Search only** |
| Graph DB | **Not used — do not add Neo4j or any graph database** |
| Tavily | Optional external verification layer — agent must work without it |
| Vector Search | Optional — agent must work without it via `local_retriever.py` |
| FastAPI | **Not used** — this is not a web service |
| Frontend | **Not used** — no HTML, React, or templates |

---

## Data Contract
- **Dataset size:** 10,000 healthcare facility records
- **Primary key:** `facility_id`
- **Main evidence field:** `combined_medical_evidence` (dense text used for vector indexing and evidence building)
- **Critical fields — DO NOT rename:**
  - `trust_score` — float, 0.0–1.0
  - `trust_category` — string (e.g., "High", "Medium", "Low")
  - `recommendation_readiness` — string or bool flag

---

## Agent Output Contract
Every agent response must include:
- `evidence` — structured citations from `combined_medical_evidence`
- `warnings` — any data quality or contradiction flags
- `reasoning` — step-by-step chain of thought
- `safety_note` — human-readable safety/disclaimer statement

---

## Module Map
| Module | Role |
|--------|------|
| `config/settings.py` | Pydantic-settings config, loads all env vars from `.env` |
| `agent_core/schemas.py` | Pydantic models for all agent inputs and outputs |
| `agent_core/capability_taxonomy.py` | Healthcare capability taxonomy (ICU, NICU, dialysis, etc.) |
| `agent_core/intent_parser.py` | Parse raw user query into structured `AgentIntent` |
| `agent_core/evidence_builder.py` | Build `EvidenceBlock` list from facility records |
| `agent_core/vector_source_builder.py` | Prepare and export data for Databricks vector index |
| `agent_core/vector_retriever.py` | Query Databricks Mosaic AI Vector Search |
| `agent_core/local_retriever.py` | Keyword/pandas-based fallback retriever (no vector DB needed) |
| `agent_core/evidence_citation.py` | Format and cite evidence blocks |
| `agent_core/validator.py` | Validate agent output against rules |
| `agent_core/contradiction_rules.py` | Rules for detecting contradictions in evidence |
| `agent_core/recommendation_engine.py` | Score and rank facilities, produce recommendations |
| `agent_core/tavily_verifier.py` | Optional: verify shortlisted facilities via Tavily |
| `agent_core/tavily_cache.py` | Cache Tavily results to `data/tavily_cache/` |
| `agent_core/audit_logger.py` | Append-only audit log for all agent decisions |
| `agent_core/mlflow_tracing.py` | MLflow experiment tracking and run tracing |
| `agent_core/demo_queries.py` | Curated demo queries for evaluation and demos |

---

## Environment Flags
| Variable | Default | Meaning |
|----------|---------|---------|
| `ENABLE_VECTOR_SEARCH` | `false` | Use Databricks vector search (requires credentials) |
| `ENABLE_TAVILY` | `false` | Enable Tavily external verification |
| `TRUST_SCORE_THRESHOLD` | `0.6` | Minimum trust score for a recommendation |
| `MAX_RESULTS` | `10` | Max facilities returned per query |

---

## Development Rules for Cursor / AI Assistants
1. Never modify any external backend app.
2. Never create FastAPI routes or frontend components.
3. Never rename `trust_score`, `trust_category`, or `recommendation_readiness`.
4. `facility_id` is always the primary key — never drop or alias it.
5. All retrieval must degrade gracefully: vector search → local retriever.
6. Tavily calls must be wrapped in try/except; failures must not crash the agent.
7. Every agent run must produce `evidence`, `warnings`, `reasoning`, and `safety_note`.
8. Update `docs/PROGRESS.md` after every significant prompt/change.
9. Tests live in `tests/` — use `pytest` and `pytest-mock`.
10. MLflow tracing is mandatory for every production agent run.
