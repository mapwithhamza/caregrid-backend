# Stage 17 — Real Vector-Enabled Agent Smoke Test

This document records the **first end-to-end run** of the standalone
CareGrid Vector Agent against the **live Databricks Mosaic AI Vector
Search index**. Stage 16 fixed clinical matching quality with local
data only; Stage 17 layers real semantic retrieval on top, and proves
the agent can talk to the production vector index without breaking
local fallback or burning Tavily credits.

> Companion to `docs/REAL_INTEGRATION_RUNBOOK.md` (operator runbook),
> `docs/VECTOR_DB_PLAN.md` (index design) and
> `docs/TAVILY_REAL_SMOKE_TEST.md` (Stage 15 Tavily proof).

---

## 1. Databricks setup values

These were confirmed by the main team and used unchanged for Stage 17.

| Item                       | Value |
| --- | --- |
| `VECTOR_SOURCE_TABLE`      | `workspace.default.caregrid_vector_source` |
| `VECTOR_SEARCH_ENDPOINT`   | `caregrid-vector-endpoint` |
| `VECTOR_SEARCH_INDEX`      | `workspace.default.caregrid_vector_index` |
| Primary key                | `facility_id` |
| Embedding source column    | `vector_text` |
| Embedding model            | `databricks-gte-large-en` |
| Index type                 | Delta Sync / Hybrid |
| Sync mode                  | Triggered |
| Rows indexed               | 10,000 |
| `DATABRICKS_HOST`          | `https://dbc-f8a63c0d-8f76.cloud.databricks.com` |

The index columns the agent retrieves are the eight listed in
`agent_core.vector_retriever.DEFAULT_RETURN_COLUMNS`:

```python
[
    "facility_id",
    "name",
    "state",
    "city",
    "facility_type",
    "trust_score",
    "trust_category",
    "recommendation_readiness",
]
```

Databricks **automatically appends a `score` column** to every response
manifest — we deliberately do **not** request it (asking for it returns
`column not found`).

---

## 2. `.env` variables required

Put the following into `.env` (gitignored). Two of every important
variable name are accepted, so the file below works whether you copy
from the runbook or from this doc.

```ini
VECTOR_SEARCH_ENABLED=true
ENABLE_VECTOR_SEARCH=true

DATABRICKS_HOST=https://dbc-f8a63c0d-8f76.cloud.databricks.com
DATABRICKS_TOKEN=<paste your PAT here>

VECTOR_SOURCE_TABLE=workspace.default.caregrid_vector_source

# Endpoint — three accepted env names (canonical first):
VECTOR_SEARCH_ENDPOINT=caregrid-vector-endpoint
DATABRICKS_VECTOR_SEARCH_ENDPOINT=caregrid-vector-endpoint
DATABRICKS_VECTOR_ENDPOINT=caregrid-vector-endpoint

# Index — three accepted env names:
VECTOR_SEARCH_INDEX=workspace.default.caregrid_vector_index
DATABRICKS_VECTOR_INDEX_NAME=workspace.default.caregrid_vector_index
DATABRICKS_VECTOR_INDEX=workspace.default.caregrid_vector_index

# Tavily MUST stay disabled for Stage 17:
TAVILY_ENABLED=false
ENABLE_TAVILY=false
```

Rules enforced by `agent_core.vector_retriever`:

| Missing var                  | Behaviour |
| --- | --- |
| `DATABRICKS_HOST`            | `available=False`, `reason="missing_databricks_host"` |
| `DATABRICKS_TOKEN`           | `available=False`, `reason="missing_databricks_token"` |
| `VECTOR_SEARCH_ENDPOINT`     | `available=False`, `reason="missing_vector_search_endpoint"` |
| `VECTOR_SEARCH_INDEX`        | `available=False`, `reason="missing_vector_search_index"` |
| `VECTOR_SEARCH_ENABLED=false`| `available=False`, `reason="vector_search_disabled"` |

In every one of these cases the agent **falls back to local retrieval**
— no crash, no exception, the run still produces recommendations.

The token is **never printed in full** by the demo runner. The banner
prints `present` or `MISSING / placeholder` only.

---

## 3. Exact commands run

```bash
# Bihar ICU
python run_agent_demo.py \
  --query "Find trusted ICU hospitals in Bihar" \
  --enable-vector --max-results 5 \
  --output-json data/outputs/vector_smoke_bihar_icu.json \
  --output-md   data/outputs/vector_smoke_bihar_icu.md

# Uttar Pradesh dialysis
python run_agent_demo.py \
  --query "Find dialysis centers in Uttar Pradesh" \
  --enable-vector --max-results 5 \
  --output-json data/outputs/vector_smoke_up_dialysis.json \
  --output-md   data/outputs/vector_smoke_up_dialysis.md
```

Tavily is **off** by default; we did not pass `--enable-tavily`.

---

## 4. Result summary — Bihar ICU

Output files:

- `data/outputs/vector_smoke_bihar_icu.json`
- `data/outputs/vector_smoke_bihar_icu.md`

Retrieval summary:

| Field                        | Value |
| --- | --- |
| `vector_enabled`             | `true` |
| `vector_available`           | `true` |
| `vector_count`               | **20** |
| `vector_reason`              | `ok` |
| `vector_filter_applied`      | `true` |
| `vector_filters_requested`   | `{"state": "Bihar"}` |
| `vector_endpoint`            | `caregrid-vector-endpoint` |
| `vector_index`               | `workspace.default.caregrid_vector_index` |
| `local_count`                | 164 |
| `merged_count`               | 165 |
| `returned`                   | 5 |
| Fallback used?               | **No** |
| Tavily credits spent         | 0 |

Top recommendations (state was filtered to Bihar both server- and
client-side, so every result is in Bihar):

| # | Facility | Type | Trust | `final_score` | `vector_similarity_component` |
| --- | --- | --- | --- | --- | --- |
| 1 | Dr Niranjan Sagar Champaran Heart Center | hospital | 0.84 | 0.7633 | 0.0000 |
| 2 | Braham Jyoti Hospital                    | hospital | 0.72 | 0.7333 | **0.0949** |
| 3 | Kalima Child Hospital                    | hospital | 0.69 | 0.6683 | 0.0000 |
| 4 | Dr. R K Thakur Hospital                  | hospital | 0.93 | 0.6683 | 0.0000 |
| 5 | Divisional Railway Hospital Sonpur       | hospital | 0.78 | 0.6517 | 0.0000 |

Stage 17 acceptance check:

- [x] `vector_enabled = true`
- [x] `vector_available = true`
- [x] `vector_count > 0`
- [x] `vector_reason` indicates success (`ok`)
- [x] Recommendations returned (5)
- [x] `score_breakdown` includes `vector_similarity_component`
- [x] At least one recommendation has `vector_similarity_component > 0`
- [x] `safety_note` present in response

---

## 5. Result summary — UP dialysis

Output files:

- `data/outputs/vector_smoke_up_dialysis.json`
- `data/outputs/vector_smoke_up_dialysis.md`

Retrieval summary:

| Field                        | Value |
| --- | --- |
| `vector_enabled`             | `true` |
| `vector_available`           | `true` |
| `vector_count`               | **20** |
| `vector_reason`              | `ok` |
| `vector_filter_applied`      | `true` |
| `vector_filters_requested`   | `{"state": "Uttar Pradesh"}` |
| `vector_endpoint`            | `caregrid-vector-endpoint` |
| `vector_index`               | `workspace.default.caregrid_vector_index` |
| `local_count`                | 200 |
| `merged_count`               | 214 |
| `returned`                   | 5 |
| Fallback used?               | **No** |
| Tavily credits spent         | 0 |

Top recommendations:

| # | Facility | Type | Trust | `final_score` | `vector_similarity_component` |
| --- | --- | --- | --- | --- | --- |
| 1 | **Dr. Mudit Khurana Dialysis Centre**    | clinic   | 0.74 | 0.8241 | **0.0991** |
| 2 | La Friendz Medical Centre                | clinic   | 0.67 | 0.6883 | 0.0000 |
| 3 | Dr Sheela Sharma Memorial Charitable Tru | hospital | 0.62 | 0.6450 | 0.0000 |
| 4 | Indal Advance Lifecare Center            | clinic   | 0.76 | 0.6051 | **0.0935** |
| 5 | Advanced Superspeciality Medical Centre  | hospital | 0.71 | 0.5317 | 0.0000 |

Stage 17 acceptance check (and Stage 16 regression check):

- [x] `vector_enabled = true`
- [x] `vector_available = true`
- [x] `vector_count > 0`
- [x] **`DIALYSIS_RENAL` intent preserved** — Stage 16 patch holds.
- [x] **No false `EMERGENCY_TRAUMA` from "centers"** — top intent is the
  one we asked for (`['DIALYSIS_RENAL']`).
- [x] Dialysis-specific result ranks first
  (`Dr. Mudit Khurana Dialysis Centre`, `vec=0.0991`).
- [x] `safety_note` present.

---

## 6. Known SDK notes

These constraints come from main-team testing of the live workspace
and are baked into `agent_core.vector_retriever`:

1. **Do not request `score` as a column.**
   Databricks adds a `score` column to every response manifest
   automatically. Asking for it returns "column not found". The agent
   only requests the eight columns listed in
   `DEFAULT_RETURN_COLUMNS` and reads the score from the trailing
   `score` entry it finds in the manifest.
2. **Score is parsed from the trailing column.**
   We map `score → VectorSearchResult.similarity_score`. Garbage or
   `NULL` scores are coerced to `0.0` and never raise.
3. **Filter syntax that worked.**
   `index.similarity_search(filters={"state": "Bihar"}, ...)` — a plain
   Python dict, **not** a JSON string.
4. **`filters_json` did NOT work** in the notebook SDK version. It is
   never used as a primary argument by the agent.
5. **Filter retry path.**
   If the SDK build raises `TypeError: ... unexpected keyword argument
   'filters'` (older builds), the retriever transparently retries the
   same query without filters and reports
   `filter_applied=False`, `reason="ok_without_filter"` — the engine
   then surfaces this in `retrieval_summary.vector_filter_applied`
   and `vector_reason`. Local post-filtering still applies because
   the local retriever has already narrowed by `intent.state`.
6. **Reranker is disabled** in the workspace and is not requested by
   the agent.
7. **PAT notice from the SDK.** The SDK prints a `[NOTICE] Using a
   Personal Authentication Token …` line on first use; this is
   informational, the call still succeeds. We pass
   `disable_notice=True` but older SDK builds may ignore that kwarg.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `reason="vector_search_disabled"` | `VECTOR_SEARCH_ENABLED=false` (or `ENABLE_VECTOR_SEARCH=false`) | Set both to `true` in `.env`. |
| `reason="missing_databricks_host"` | `DATABRICKS_HOST` not set or empty | Paste full URL incl. `https://`. |
| `reason="missing_databricks_token"` | `DATABRICKS_TOKEN` not set, empty, or still a placeholder like `<token>` | Paste a real PAT in `.env` (never in chat / screenshots / Cursor). |
| `reason="missing_vector_search_endpoint"` | None of `VECTOR_SEARCH_ENDPOINT`, `DATABRICKS_VECTOR_SEARCH_ENDPOINT`, `DATABRICKS_VECTOR_ENDPOINT` resolved | Add at least one, value `caregrid-vector-endpoint`. |
| `reason="missing_vector_search_index"` | None of `VECTOR_SEARCH_INDEX`, `DATABRICKS_VECTOR_INDEX_NAME`, `DATABRICKS_VECTOR_INDEX` resolved | Add at least one, value `workspace.default.caregrid_vector_index`. |
| `reason="databricks_sdk_unavailable"` | `databricks-vectorsearch` not installed | `pip install -r requirements.txt` (or `pip install "databricks-vectorsearch>=0.40"`). |
| `reason` starts with `query_failed: ConnectionError…` | Workspace unreachable / token revoked / endpoint paused | Check `DATABRICKS_HOST`, regenerate the PAT, confirm the endpoint is online in the Databricks UI. |
| `vector_filter_applied=false` and `reason="ok_without_filter"` | SDK build refused the `filters={...}` kwarg | Upgrade `databricks-vectorsearch` (≥ 0.40 supports it). The agent already produced results, but they were unfiltered server-side; local filtering still applied. |
| `vector_count == 0` while `available=true` | Filter matches no rows, or query text is too narrow | Drop the state filter (omit state in the query) and check if the index returns hits at all. |
| `[NOTICE] Using a Personal Authentication Token …` printed | Older SDK builds emit this on first use | Cosmetic — call still succeeds. Move to a service principal for production. |

### Full local fallback (vector totally absent)

To prove the agent works with **no Databricks credentials at all**,
unset the four vector env vars and re-run the same command. The
output will show:

```
vector_enabled=true  vector_available=false  vector_count=0
vector_reason=missing_databricks_host (or _token / _endpoint / _index)
```

…and the `recommendations[]` block will still be populated from the
local 10,000-row CSV. This path is exercised by
`tests/test_recommendation_engine.py::test_stage17_missing_databricks_env_does_not_crash`.

---

## 8. Where the contract is enforced

| Concern | Code | Test |
| --- | --- | --- |
| Don't request `score` as a column | `agent_core/vector_retriever.py::DEFAULT_RETURN_COLUMNS` | `tests/test_vector_retriever.py::test_search_does_not_request_score_in_columns` |
| `filters={...}` is a dict, not JSON | `agent_core/vector_retriever.py::_do_query` | `tests/test_vector_retriever.py::test_search_with_filters_passes_python_dict` |
| Filter retry on `TypeError` | `agent_core/vector_retriever.py::_do_query` | `tests/test_vector_retriever.py::test_search_filter_typeerror_falls_back_to_no_filter` |
| State pushed into vector filter | `agent_core/recommendation_engine.py::_build_vector_filters` | `tests/test_recommendation_engine.py::test_stage17_filters_pushed_when_state_is_in_intent` |
| `vector_endpoint` / `vector_index` echoed back | `agent_core/vector_retriever.py::search` | `tests/test_vector_retriever.py::test_endpoint_and_index_echoed_back_on_success_response` |
| `vector_similarity_component > 0` for vector hits | `agent_core/recommendation_engine.py::_score_candidate` | `tests/test_recommendation_engine.py::test_stage17_vector_similarity_component_is_positive_for_scored_candidate` |
| Graceful fallback when env is missing | `agent_core/vector_retriever.py::_unavailable_reason` | `tests/test_recommendation_engine.py::test_stage17_missing_databricks_env_does_not_crash` |
| `--enable-vector` wires the flag through | `run_agent_demo.py::main` | `tests/test_run_agent_demo.py::test_stage17_enable_vector_flag_passes_through_to_engine` |
| Vector section rendered in Markdown | `run_agent_demo.py::_format_vector_section` | `tests/test_run_agent_demo.py::test_stage17_markdown_report_has_vector_search_section` |

Run all of them with `python -m pytest`. Every one passes against
**mocked** SDK responses — the real workspace is **never contacted**
during automated tests, and Tavily credits are never spent.
