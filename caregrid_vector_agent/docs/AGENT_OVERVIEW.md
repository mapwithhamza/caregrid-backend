# CareGrid Vector Agent — Overview

## Purpose

`caregrid_vector_agent` is the standalone AI agent intelligence layer for CareGrid India. It parses natural language queries about healthcare facilities, retrieves and ranks evidence-backed records, and returns structured recommendations with warnings and safety notes.

## Architecture

```text
User Query
    │
    ▼
intent_parser         → AgentIntent (capabilities, location, min_trust_score)
    │
    ▼
vector_retriever      → Databricks Mosaic AI Vector Search
  OR local_retriever  → pandas keyword fallback (no external services)
    │
    ▼
evidence_builder      → EvidenceSnippet list from combined_medical_evidence
    │
    ▼
validator             → ValidationFinding list (trust_score, readiness, contradictions)
    │
    ▼
recommendation_engine → AgentRecommendation list (ranked by trust_score)
    │
    ▼
tavily_verifier       → WebVerificationResult (optional — skipped if not configured)
    │
    ▼
AgentResponse         → evidence, recommendations, warnings, reasoning, safety_note
```

## Data Contract

| Field | Type | Notes |
| --- | --- | --- |
| `facility_id` | str | Primary key — never null |
| `combined_medical_evidence` | str | Main text for retrieval and evidence extraction |
| `trust_score` | float | 0.0–1.0; minimum threshold configurable via `TRUST_SCORE_THRESHOLD` |
| `trust_category` | str | One of `TRUST_CATEGORIES` in `config/settings.py` |
| `recommendation_readiness` | str | One of `RECOMMENDATION_READINESS_VALUES` in `config/settings.py` |

**Do not rename** `trust_score`, `trust_category`, or `recommendation_readiness`.

## Trust Categories

```python
TRUST_CATEGORIES = [
    "High Trust / Evidence Supported",
    "Moderate Trust / Verify Before Use",
    "Low Trust / Needs Human Verification",
    "High Risk / Insufficient Evidence",
]
```

## Recommendation Readiness Values

```python
RECOMMENDATION_READINESS_VALUES = [
    "Ready for recommendation",
    "Usable with verification",
    "Do not recommend without human review",
]
```

## Key Modules

| Module | Responsibility |
| --- | --- |
| `config/settings.py` | All env-driven config via pydantic-settings |
| `agent_core/schemas.py` | Pydantic data models for all inputs and outputs |
| `agent_core/capability_taxonomy.py` | Healthcare capability keyword map |
| `agent_core/intent_parser.py` | Raw query → AgentIntent |
| `agent_core/evidence_builder.py` | Facility record → EvidenceSnippet list |
| `agent_core/vector_retriever.py` | Databricks Mosaic AI Vector Search queries |
| `agent_core/local_retriever.py` | pandas keyword fallback (no services needed) |
| `agent_core/evidence_citation.py` | Format EvidenceSnippet list as numbered citations |
| `agent_core/validator.py` | Business rule validation on AgentResponse |
| `agent_core/contradiction_rules.py` | Detect conflicting evidence signals |
| `agent_core/recommendation_engine.py` | Filter + rank facilities by trust_score |
| `agent_core/tavily_verifier.py` | Optional Tavily external web verification |
| `agent_core/tavily_cache.py` | Cache Tavily results to disk |
| `agent_core/audit_logger.py` | Append-only JSONL audit log |
| `agent_core/mlflow_tracing.py` | MLflow experiment tracking |
| `agent_core/demo_queries.py` | Curated golden queries for evaluation |

## Agent Output Contract

Every `AgentResponse` must include:

- `evidence` — list of `EvidenceSnippet`
- `recommendations` — list of `AgentRecommendation`
- `warnings` — list of human-readable warning strings
- `reasoning` — narrative explaining why these facilities were selected
- `safety_note` — mandatory human verification reminder
- `validation_findings` — structured `ValidationFinding` list

## Fallback Strategy

The agent operates in three modes depending on available services:

1. **Full mode** — vector search + Tavily enabled
2. **Vector-only mode** — vector search enabled, Tavily disabled
3. **Local mode** — both disabled; uses `local_retriever` (pandas keyword search on loaded CSV/parquet)

Local mode requires no credentials and is the default out-of-the-box.
