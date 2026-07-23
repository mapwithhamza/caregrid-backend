# CareGrid Vector Agent — Databricks Mosaic AI Vector Search Plan

> **Scope:** This document is the single source of truth for how the CareGrid
> vector index is created, kept in sync, queried, and bypassed when unavailable.
> It contains **no secrets** — all credentials are referenced as environment
> variables only.

---

## 1. Architecture at a Glance

```text
┌──────────────────────────────────────────────┐
│ data/raw/  (CSV / Parquet — local dev)       │
└──────────────────────┬───────────────────────┘
                       │ vector_source_builder
                       ▼
┌──────────────────────────────────────────────┐
│ workspace.default.caregrid_vector_source     │
│   • Delta table                              │
│   • Built by notebook 01                     │
│   • Contains vector_text + metadata          │
└──────────────────────┬───────────────────────┘
                       │ Delta Sync (TRIGGERED)
                       ▼
┌──────────────────────────────────────────────┐
│ workspace.default.caregrid_vector_index      │
│   • Mosaic AI Vector Search Delta Sync index │
│   • Built by notebook 02                     │
│   • Embedding model: databricks-bge-large-en │
└──────────────────────┬───────────────────────┘
                       │ vector_retriever.retrieve()
                       ▼
┌──────────────────────────────────────────────┐
│ Agent pipeline (intent → evidence → recs)    │
│   ▸ Falls back to local_retriever if         │
│     VECTOR_SEARCH_ENABLED=false or the       │
│     endpoint / index is unreachable.         │
└──────────────────────────────────────────────┘
```

---

## 2. Canonical Names

These names are **locked**. Do not rename them in code, notebooks, or env files
without first updating this document and `config/settings.py`.

| Object              | Name                                              |
| ------------------- | ------------------------------------------------- |
| Source Delta table  | `workspace.default.caregrid_vector_source`        |
| Vector endpoint     | `caregrid-vector-endpoint`                        |
| Vector index        | `workspace.default.caregrid_vector_index`         |
| Primary key column  | `facility_id`                                     |
| Embedding text col  | `vector_text`                                     |
| Embedding model     | `databricks-bge-large-en` (Foundation Model API)  |

---

## 3. Source Table Schema

The Delta table `workspace.default.caregrid_vector_source` is produced by
`notebooks/01_prepare_vector_source.py` and matches the output of
`vector_source_builder.prepare_vector_source_dataframe()`.

| Column                     | Type   | Role                | Notes                                           |
| -------------------------- | ------ | ------------------- | ----------------------------------------------- |
| `facility_id`              | STRING | **Primary key**     | Must be non-null, unique per row                |
| `vector_text`              | STRING | **Embedding input** | Pipe-delimited; consumed by the embedding model |
| `name`                     | STRING | Metadata            | Returned with query results                     |
| `state`                    | STRING | Metadata            | Indian state or UT (filterable)                 |
| `city`                     | STRING | Metadata            | City (filterable)                               |
| `facility_type`            | STRING | Metadata            | hospital / clinic / doctor / pharmacy / dentist |
| `trust_score`              | DOUBLE | Metadata            | 0.0 – 1.0 (filterable)                          |
| `trust_category`           | STRING | Metadata            | One of `TRUST_CATEGORIES`                       |
| `recommendation_readiness` | STRING | Metadata            | One of `RECOMMENDATION_READINESS_VALUES`        |
| `latitude`                 | DOUBLE | Metadata            | Optional                                        |
| `longitude`                | DOUBLE | Metadata            | Optional                                        |
| `combined_medical_evidence`| STRING | Source-only         | Stays in source table; not synced to index      |
| `evidence_summary`         | STRING | Source-only         | Stays in source table; not synced to index      |

**Synced into the index (11 columns):** the primary key, the embedding text
column, and the 9 metadata columns above. `combined_medical_evidence` and
`evidence_summary` remain in the source table and are joined back at retrieval
time when the agent needs full evidence text.

---

## 4. One-Time Endpoint Setup

You can create the endpoint either via the Databricks UI **or** via the SDK. Do
this once per workspace.

### 4a. Via the Databricks UI

1. In the workspace sidebar open **Compute → Vector Search**.
2. Click **Create endpoint**.
3. Fill in:
   - **Name:** `caregrid-vector-endpoint`
   - **Type:** `Standard`
4. Click **Create**.
5. Wait until **State = ONLINE / READY** (typically 5–10 minutes on first
   creation). The page auto-refreshes.

### 4b. Via the Databricks SDK

Run from a Databricks notebook (the `WorkspaceClient` picks up the runtime
identity automatically — no token needed in code):

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
w.vector_search_endpoints.create_endpoint(
    name="caregrid-vector-endpoint",
    endpoint_type="STANDARD",
)
```

Re-running the call after the endpoint exists will raise; wrap in a try / except
or check first with `w.vector_search_endpoints.list_endpoints()`. The notebook
`02_create_vector_index_notes.py` does this idempotently.

---

## 5. Creating the Delta Sync Index

The index is **Delta Sync** so updates to
`workspace.default.caregrid_vector_source` propagate automatically. The
embedding is computed inside Databricks using the
`databricks-bge-large-en` Foundation Model endpoint — no external embedding
service is required.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest,
    EmbeddingSourceColumn,
    VectorIndexType,
    PipelineType,
)

w = WorkspaceClient()
w.vector_search_indexes.create_index(
    name="workspace.default.caregrid_vector_index",
    endpoint_name="caregrid-vector-endpoint",
    primary_key="facility_id",
    index_type=VectorIndexType.DELTA_SYNC,
    delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
        source_table="workspace.default.caregrid_vector_source",
        pipeline_type=PipelineType.TRIGGERED,
        embedding_source_columns=[
            EmbeddingSourceColumn(
                name="vector_text",
                embedding_model_endpoint_name="databricks-bge-large-en",
            )
        ],
        columns_to_sync=[
            "facility_id",
            "vector_text",
            "name",
            "state",
            "city",
            "facility_type",
            "trust_score",
            "trust_category",
            "recommendation_readiness",
            "latitude",
            "longitude",
        ],
    ),
)
```

**Pipeline type:**

- `TRIGGERED` (recommended for CareGrid) — sync runs when you call
  `index.sync()`. Lower cost, predictable.
- `CONTINUOUS` — sync runs constantly. Use only if facility data changes
  many times per day.

---

## 6. Confirming the Index Is Ready

The index is queryable only after both:

1. **Endpoint state** is `ONLINE`.
2. **Index status** has `ready = true` and the initial sync has finished.

Check via the SDK:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

ep = w.vector_search_endpoints.get_endpoint("caregrid-vector-endpoint")
print("Endpoint state:", ep.endpoint_status.state)

idx = w.vector_search_indexes.get_index(
    "workspace.default.caregrid_vector_index"
)
print("Index ready :", idx.status.ready)
print("Index detail:", idx.status.detailed_state)
print("Indexed rows:", getattr(idx.status, "indexed_row_count", None))
```

You can also confirm in the **Compute → Vector Search → caregrid-vector-endpoint**
page in the workspace UI; the index row should show **Status: Online / Ready**.

Initial embedding of ~10,000 rows with `databricks-bge-large-en` typically takes
a few minutes after the endpoint is online.

---

## 7. Testing a Query

A round-trip semantic query against the live index:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

result = w.vector_search_indexes.query_index(
    index_name="workspace.default.caregrid_vector_index",
    query_text="ICU hospital with dialysis in Mumbai",
    columns=[
        "facility_id",
        "name",
        "city",
        "state",
        "facility_type",
        "trust_score",
        "trust_category",
        "recommendation_readiness",
    ],
    num_results=5,
)

for row in result.result.data_array:
    print(row)
```

### Server-Side Filters

Filters are passed as a dict to `filters_json` (the SDK serialises it):

```python
result = w.vector_search_indexes.query_index(
    index_name="workspace.default.caregrid_vector_index",
    query_text="emergency trauma centre",
    columns=["facility_id", "name", "trust_score", "trust_category"],
    num_results=10,
    filters_json='{"state": "Maharashtra", "trust_score >=": 0.6}',
)
```

Supported operators include `=`, `!=`, `>=`, `<=`, `IN`, and `LIKE`. See the
Databricks Mosaic AI Vector Search docs for the full grammar.

---

## 8. Environment Variables

The agent reads these from `.env` via `config/settings.py`. **Never commit
real values.** A token belongs only in the local `.env` or in Databricks
Secrets — never in code or in this document.

| Variable                  | Purpose                                                           | Example value                                  |
| ------------------------- | ----------------------------------------------------------------- | ---------------------------------------------- |
| `DATABRICKS_HOST`         | Workspace URL (no trailing slash)                                 | `https://adb-xxxx.cloud.databricks.com`        |
| `DATABRICKS_TOKEN`        | Personal Access Token (local dev only — prefer OAuth in CI)       | `dapi••••••••••••••••••••••••••••••••`        |
| `VECTOR_SOURCE_TABLE`     | Fully-qualified source Delta table                                | `workspace.default.caregrid_vector_source`     |
| `VECTOR_SEARCH_ENDPOINT`  | Endpoint name                                                     | `caregrid-vector-endpoint`                     |
| `VECTOR_SEARCH_INDEX`     | Fully-qualified index name                                        | `workspace.default.caregrid_vector_index`      |
| `VECTOR_SEARCH_ENABLED`   | Master switch — `false` forces the local fallback                 | `false`                                        |

When running **inside** a Databricks notebook, `WorkspaceClient()` uses the
notebook’s identity automatically and `DATABRICKS_HOST` /
`DATABRICKS_TOKEN` are not required.

---

## 9. Retriever (Python Client)

The agent talks to the index through `agent_core.vector_retriever.VectorRetriever`.
The class is intentionally small, fully optional, and never raises.

### API

```python
from config.settings import settings
from agent_core.vector_retriever import VectorRetriever, VectorSearchResponse

retriever = VectorRetriever(settings)

if retriever.is_available():
    response: VectorSearchResponse = retriever.search(
        query="ICU hospital with dialysis in Mumbai",
        filters={"state": "Maharashtra", "trust_score >=": 0.6},   # optional
        num_results=20,                                            # default 20
    )
    if response.available:
        for hit in response.results:
            print(hit.facility_id, hit.similarity_score, hit.metadata["name"])
    else:
        # Graceful unavailable — fall back to local_retriever
        ...
```

### Models

- **`VectorSearchResult`** — one hit
  - `facility_id: str`
  - `similarity_score: float`
  - `metadata: dict[str, Any]` — `name`, `state`, `city`, `facility_type`,
    `trust_score`, `trust_category`, `recommendation_readiness`,
    `latitude`, `longitude`
  - `source: str` — always `"databricks_vector_search"` for index hits
- **`VectorSearchResponse`** — wrapper
  - `available: bool`
  - `results: list[VectorSearchResult]`
  - `reason: str` — empty when `available=True`, otherwise one of the
    stable codes below
  - `query: str` — the original query for traceability

### Reason codes (stable, log-safe)

| Code                              | When it fires                                                            |
| --------------------------------- | ------------------------------------------------------------------------ |
| `vector_search_disabled`          | `VECTOR_SEARCH_ENABLED=false` (the master switch)                         |
| `missing_databricks_host`         | `DATABRICKS_HOST` is empty                                                |
| `missing_databricks_token`        | `DATABRICKS_TOKEN` is empty                                               |
| `missing_vector_search_endpoint`  | `VECTOR_SEARCH_ENDPOINT` is empty                                         |
| `missing_vector_search_index`     | `VECTOR_SEARCH_INDEX` is empty                                            |
| `databricks_sdk_unavailable`      | `databricks-sdk` not installed in the runtime                             |
| `query_failed: <ExceptionType>: …`| Any exception raised inside the SDK call (network, auth, schema, etc.)   |

### Guarantees

1. **`is_available()`** is a cheap, side-effect-free env-var check —
   it never contacts Databricks.
2. **`search()`** never raises. Any failure (config, SDK import, HTTP,
   auth, parsing) becomes `available=False` with a single-line `reason`.
3. The Databricks SDK is **lazy-imported** inside `_get_client()`, so
   importing `vector_retriever` works on machines that have no Databricks
   SDK installed.
4. Unit tests must never hit a real workspace. Pass a duck-typed
   `SimpleNamespace` for `settings` and patch `_get_client()` with
   `unittest.mock`. See `tests/test_vector_retriever.py`.

---

## 10. Fallback Strategy

The agent must keep working even when Databricks is unreachable, the endpoint
is offline, the index is still building, or the user has not provisioned
Databricks at all.

The contract is:

1. `VectorRetriever(settings).search(query, filters=None, num_results=20)` is
   the primary path. It **never raises** — see Section 9.
2. The response is **graceful unavailable** (`available=False`, with a
   stable `reason` code) when **any** of the following holds:
   - `settings.vector_search_enabled` is `False`
   - `DATABRICKS_HOST` or `DATABRICKS_TOKEN` is empty
   - `VECTOR_SEARCH_ENDPOINT` or `VECTOR_SEARCH_INDEX` is empty
   - The Databricks SDK is not installed
   - The endpoint or index is not `READY`
   - The Databricks SDK call raises any exception (network, auth, schema, …)
3. The orchestrator inspects `response.available`; if `False`, it calls
   `local_retriever.retrieve_local(query, df, top_k)`.
4. `local_retriever` performs case-insensitive keyword scoring against the
   in-memory pandas DataFrame loaded from `data/vector_source/` —
   no Databricks connection required.

This means **all unit tests, all golden queries, and all local development**
work entirely without Databricks credentials. The vector index is an
optional production accelerator, not a hard dependency.

---

## 11. Operational Runbook

| Situation                                  | Action                                                                                          |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| Source data changed                        | Re-run notebook 01, then call `index.sync()` (or wait for the next scheduled trigger)           |
| Schema change in source table              | Drop + recreate the index (Delta Sync indexes do not support live schema migration)             |
| Embedding model upgraded                   | Recreate the index pointing at the new `embedding_model_endpoint_name`                          |
| Endpoint stuck in `PROVISIONING`           | Wait 10 minutes; if still stuck, delete and recreate via the UI                                 |
| Query latency degraded                     | Check endpoint state in UI; consider `STORAGE_OPTIMIZED` endpoint type for very large indexes   |
| Need to disable vector search temporarily  | Set `VECTOR_SEARCH_ENABLED=false` — fallback takes over within the next process restart         |

---

## 12. Cost & Capacity Notes

- **Endpoint:** A `STANDARD` endpoint is billed per hour while running.
- **Embedding compute:** `databricks-bge-large-en` is billed per token; the
  initial sync of ~10,000 rows is a one-time cost, subsequent syncs only
  re-embed changed rows.
- **Storage:** Delta Sync indexes incur storage cost proportional to row count
  × embedding dimensions. For ~10,000 facilities this is negligible.

---

## 13. References

- Databricks Mosaic AI Vector Search docs:
  <https://docs.databricks.com/aws/en/generative-ai/vector-search>
- Foundation Model APIs (embedding):
  <https://docs.databricks.com/aws/en/machine-learning/foundation-models/index.html>
- Databricks SDK for Python — Vector Search:
  <https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/index.html>
