# CareGrid India — Backend API + Standalone Vector Agent

A FastAPI backend for CareGrid India, an agentic healthcare-intelligence
system serving 10,000 real Indian healthcare facilities. As of **Stage
19** this repository ships **two integrated codebases**:

1. **`app/`** — the FastAPI backend (CSV loading, validation, search,
   stats, impact, facilities, and the upgraded `/agent/recommend`
   route).
2. **`caregrid_vector_agent/`** — the **standalone CareGrid Vector
   Agent** (Stages 1 – 18): a self-contained Python package that
   mediates raw facility data, an optional Databricks Mosaic AI Vector
   Search index, and optional Tavily web verification, and returns a
   fully-cited, validated, score-broken-down `AgentResponse`.

The frontend continues to call **only the backend** at
`POST /agent/recommend`. The backend in turn calls the standalone
agent via `app/services/caregrid_agent_service.py` (a thin,
fail-graceful adapter). Databricks and Tavily are **only ever**
contacted by the agent — never by the frontend.

```
Frontend (React, AI-ready)
   │
   ▼
FastAPI backend  /agent/recommend          ◄── public surface
   │
   ▼
app/services/caregrid_agent_service.py     ◄── thin adapter
   │
   ▼
caregrid_vector_agent/agent_core/
   recommendation_engine.run_recommendation
   │
   ├─► local CSV (data/caregrid_backend_export_full.csv, 10k rows)
   ├─► (optional) Databricks Vector Search   (env-gated)
   └─► (optional) Tavily web verification    (env-gated)
```

---

## Quick start

```powershell
# 1. Create venv and install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Optional: copy env template (real keys never committed)
Copy-Item .env.example .env

# 3. Place / verify the main CSV
#    data/caregrid_backend_export_full.csv  (10,000 rows, 35 columns)

# 4. Run the API
python run.py
# → http://localhost:8000/docs

# 5. (Optional) Run the standalone agent demo directly
cd caregrid_vector_agent
python run_agent_demo.py --query "Find trusted ICU hospitals in Bihar" --max-results 5
```

The full standalone agent suite (493 tests) is also runnable from
`caregrid_vector_agent/`:

```powershell
cd caregrid_vector_agent
python -m pytest -q
```

---

## API surface (unchanged from Stage 1, plus Stage 19 fields)

`POST /agent/recommend` is **fully backward compatible** — the existing
frontend payload still works. New optional fields opt into the upgraded
pipeline.

### Request

```jsonc
{
  "query": "Find trusted ICU hospitals in Bihar",
  "state": null,                   // optional override
  "facility_type": null,           // optional override
  "min_trust_score": null,         // optional 0–100
  "max_results": 5,                // 1–20

  // Stage 19 additions (all optional)
  "enable_vector": false,          // alias: enable_vector_search
  "enable_web_verification": false, // alias: enable_tavily
  "web_depth": "basic",            // "basic" | "demo"
  "max_web_verified": 2,           // 0–10, cap on Tavily calls per request
  "include_ai_explanation": false  // future LLM-explainer slot
}
```

### Response (additive — original fields preserved)

```jsonc
{
  "query": "...",
  "interpreted_intent": { ... },
  "total_candidates": 164,
  "returned": 5,
  "recommendations": [
    {
      "facility_id": "...",
      "name": "...",
      "state": "...",
      "trust_score": 84.0,
      "trust_category": "High Trust / Evidence Supported",
      "recommendation_readiness": "Ready for recommendation",
      "matched_capabilities": ["ICU_CRITICAL_CARE"],
      "warning_flags": [],
      "recommendation_score": 0.868,
      "reason_for_recommendation": "...",

      // Stage 19 additive fields (only populated by the upgraded agent)
      "evidence_snippets":      [ ... ],
      "validation_findings":    [ ... ],
      "score_breakdown":        { trust_score_component, readiness_component,
                                  capability_match_component, evidence_strength_component,
                                  validation_penalty, warning_penalty,
                                  vector_similarity_component, tavily_verification_component,
                                  final_score },
      "web_verification":       { verified, query_used, sources, ... },
      "human_next_steps":       [ ... ]
    }
  ],
  "reasoning": "...",
  "safety_note": "...",
  "fallback_message": null,

  // Stage 19 additive fields
  "retrieval_summary": { local_count, vector_enabled, vector_available, vector_count,
                         vector_reason, vector_filter_applied,
                         vector_endpoint, vector_index, merged_count, after_top_k_count,
                         relaxation_used,
                         web_verification_enabled, tavily_verified_count,
                         tavily_depth, tavily_credits_estimated },
  "trace_summary":     { stages: [ ... 8 stages ... ], errors, audit_log,
                         tavily, vector },
  "engine": "caregrid_vector_agent"   // or "simple_legacy_fallback"
}
```

The `engine` field tells the frontend (or a reviewer) which path served
the request. If the standalone agent fails to import or raises at
runtime, the route automatically falls back to the legacy simple
recommender (`engine: "simple_legacy_fallback"`) and never returns a
500 for a missing optional integration.

---

## Folder structure

```
care-grid-agent-backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── data_loader.py
│   ├── models.py
│   ├── services/
│   │   └── caregrid_agent_service.py     ← Stage 19 adapter
│   └── routers/
│       ├── agent.py                       ← Stage 19 upgraded route
│       ├── facilities.py
│       ├── impact.py
│       ├── search.py
│       └── stats.py
│
├── caregrid_vector_agent/                 ← Stages 1 – 18 standalone agent
│   ├── agent_core/                         (intent_parser, capability_taxonomy,
│   │                                        local_retriever, vector_retriever,
│   │                                        evidence_builder, evidence_citation,
│   │                                        validator, contradiction_rules,
│   │                                        tavily_verifier, tavily_cache,
│   │                                        recommendation_engine, schemas,
│   │                                        audit_logger, demo_queries)
│   ├── config/settings.py                  pydantic-settings + AliasChoices
│   ├── data/outputs/                       Stage 17 + 18 proof JSON / Markdown
│   ├── docs/                               PROGRESS, COMBINED_AGENT_SMOKE_TEST,
│   │                                        VECTOR_DB_PLAN, VECTOR_REAL_SMOKE_TEST,
│   │                                        TAVILY_PLAN, TAVILY_PROOF, etc.
│   ├── notebooks/                          Databricks notebooks 01 + 02
│   ├── tests/                              493 tests
│   ├── run_agent_demo.py                   CLI driver with full Stage-18 Markdown
│   └── requirements.txt
│
├── data/
│   └── caregrid_backend_export_full.csv    10,000 rows, single source of truth
│
├── docs/
│   ├── FRONTEND_INTEGRATION_CONTRACT.md
│   ├── ENDPOINT_EXAMPLES.md
│   ├── PROGRESS.md                         backend progress log
│   └── QA_CHECKLIST.md
│
├── tests/                                  backend tests
├── .env.example                            placeholder values only — `.env` is git-ignored
├── .gitignore
├── README.md                               this file
├── requirements.txt
└── run.py
```

---

## Backend endpoints

| Endpoint                                | Notes                                                                                  |
| --------------------------------------- | -------------------------------------------------------------------------------------- |
| `GET  /health`                          | `data_loaded`, `facility_rows`                                                         |
| `GET  /facilities`                      | Paginated list with filters                                                            |
| `GET  /facilities/meta/filters`         | States / facility_types / trust_categories / readiness                                 |
| `GET  /facilities/{facility_id}`        | Full detail with evidence + scores                                                     |
| `GET  /stats/overview`                  | Dashboard overview                                                                     |
| `GET  /stats/trust-distribution`        | Trust category counts                                                                  |
| `GET  /stats/readiness-distribution`    | Readiness counts                                                                       |
| `GET  /stats/states`                    | State summary                                                                          |
| `GET  /stats/facility-types`            | Facility-type summary                                                                  |
| `GET  /impact/trust-gap-summary`        | National trust-gap planning view                                                       |
| `GET  /impact/priority-states`          | Calibrated priority ranking                                                            |
| `GET  /impact/state-risk-index`         | Per-state desert risk index                                                            |
| `GET  /impact/facility-type-gap`        | Facility-type gap                                                                      |
| `GET  /search`                          | Multi-field rule search                                                                |
| `POST /agent/recommend`                 | **Upgraded Stage-19 route** — calls standalone agent, falls back to simple recommender |

---

## Environment variables

`.env` is **never committed**. `.env.example` ships placeholders only.

| Variable                       | Used by               | Notes                                                       |
| ------------------------------ | --------------------- | ----------------------------------------------------------- |
| `APP_NAME`, `ENVIRONMENT`, `DATA_DIR` | backend         | Core backend config                                         |
| `VECTOR_SEARCH_ENABLED`        | standalone agent      | Enables Databricks vector retrieval                         |
| `ENABLE_VECTOR_SEARCH`         | standalone agent      | Alias of the above                                          |
| `DATABRICKS_HOST`              | standalone agent      | e.g. `https://dbc-xxxx.cloud.databricks.com`                |
| `DATABRICKS_TOKEN`             | standalone agent      | PAT — **rotate after every demo**                           |
| `VECTOR_SEARCH_ENDPOINT`       | standalone agent      | e.g. `caregrid-vector-endpoint`                             |
| `VECTOR_SEARCH_INDEX`          | standalone agent      | e.g. `workspace.default.caregrid_vector_index`              |
| `DATABRICKS_VECTOR_ENDPOINT`   | standalone agent      | Alias                                                       |
| `DATABRICKS_VECTOR_INDEX`      | standalone agent      | Alias                                                       |
| `TAVILY_ENABLED`               | standalone agent      | Enables Tavily verification                                 |
| `ENABLE_TAVILY`                | standalone agent      | Alias                                                       |
| `TAVILY_API_KEY`               | standalone agent      | **Rotate after every demo**                                 |
| `TAVILY_DEFAULT_DEPTH`         | standalone agent      | `basic` (1 credit) or `demo` (2 credits)                    |
| `TAVILY_MAX_WEB_VERIFIED`      | standalone agent      | Cap on Tavily calls per request (default 2)                 |
| `TAVILY_MAX_RESULTS`           | standalone agent      | Per-search results cap (default 2)                          |
| `LOCAL_DATA_PATH`              | standalone agent      | Only used when running the agent **outside** the backend     |

When a request hits `POST /agent/recommend`, the backend reuses the
already-loaded `data_store.load_facilities()` dataframe — the agent
does not re-read the CSV. Missing or invalid Databricks/Tavily
credentials never crash the route; they simply set the
`vector_available=false` / `verification_status="skipped"` fields and
the request still returns a usable answer.

---

## Frontend compatibility

The original Stage-1 response keys (`query`, `interpreted_intent`,
`total_candidates`, `returned`, `recommendations`, `reasoning`,
`safety_note`, `fallback_message`) are preserved verbatim. Stage-19
adds the optional keys listed above, all under `extra="allow"` on the
Pydantic model — the existing frontend ignores fields it does not
understand.

CORS allows all origins (`["*"]`) in `app/main.py` so the React app at
`http://localhost:5173` continues to call without changes.

---

## Tests

* **Backend tests:** `python -m pytest`  (under `tests/`)
* **Standalone agent tests:** `cd caregrid_vector_agent && python -m pytest`  (493 tests, no real network)

The standalone agent's combined-mode proof artefacts live under
`caregrid_vector_agent/data/outputs/combined_vector_tavily_*.{json,md}`
and the formal write-up is at
`caregrid_vector_agent/docs/COMBINED_AGENT_SMOKE_TEST.md`.

---

## Stage history

* **Stages 1 – 18 (standalone agent).** See
  `caregrid_vector_agent/docs/PROGRESS.md` for the full chronological
  log. Highlights:
  * Stage 14 — golden query evaluation suite
  * Stage 15 — real Tavily smoke (live API)
  * Stage 16 — clinical-matching quality patch (kills `er`-in-stapler
    false positives, restores `DIALYSIS_RENAL` for "centers" queries)
  * Stage 17 — real Databricks Vector Search smoke (live index)
  * Stage 18 — combined real-vector + real-Tavily smoke; 493 tests
    green, 3 proof JSON/Markdown pairs in `data/outputs/`.
* **Stage 19 (this repo).** Standalone agent integrated into the
  FastAPI backend via `app/services/caregrid_agent_service.py`;
  `/agent/recommend` upgraded with graceful fallback; no frontend
  change required.

---

## Safety note (always returned by the API)

> CareGrid recommendations are evidence-based decision support only.
> Emergency medical decisions should be verified with local providers
> and official emergency channels.

Tavily verification confirms identity / location only — it is **not**
a substitute for live phone confirmation of clinical capability. The
upgraded agent surfaces this distinction in `human_next_steps` for
every web-verified recommendation.
