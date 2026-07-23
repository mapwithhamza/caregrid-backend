# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # CareGrid — Create Vector Search Endpoint and Index
# MAGIC
# MAGIC **Purpose:** Provision the Mosaic AI Vector Search endpoint and the
# MAGIC Delta Sync index that the CareGrid agent uses for semantic retrieval.
# MAGIC
# MAGIC **Prerequisite:** `notebooks/01_prepare_vector_source.py` has already
# MAGIC produced the source Delta table
# MAGIC `workspace.default.caregrid_vector_source`.
# MAGIC
# MAGIC **What this notebook does:**
# MAGIC 1. Confirm prerequisites (source table exists, has rows, has the
# MAGIC    `vector_text` column).
# MAGIC 2. Create the vector search endpoint `caregrid-vector-endpoint`
# MAGIC    (idempotent — skipped if it already exists).
# MAGIC 3. Wait for the endpoint to become `ONLINE`.
# MAGIC 4. Create the Delta Sync index
# MAGIC    `workspace.default.caregrid_vector_index` (idempotent).
# MAGIC 5. Wait for the index to report `ready = true`.
# MAGIC 6. Run a smoke-test query.
# MAGIC 7. Print the environment variables needed by the agent.
# MAGIC
# MAGIC **Security:** No tokens or secrets appear in this notebook.
# MAGIC `WorkspaceClient()` uses the notebook's runtime identity automatically.
# MAGIC When running outside Databricks, set `DATABRICKS_HOST` and
# MAGIC `DATABRICKS_TOKEN` in the local environment instead.

# COMMAND ----------

# =============================================================================
# CELL 1 — Setup: imports, constants, prerequisite check
# =============================================================================

import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest,
    EmbeddingSourceColumn,
    EndpointType,
    PipelineType,
    VectorIndexType,
)

# ── Canonical names — must match docs/VECTOR_DB_PLAN.md ──────────────────────
SOURCE_TABLE   = "workspace.default.caregrid_vector_source"
ENDPOINT_NAME  = "caregrid-vector-endpoint"
INDEX_NAME     = "workspace.default.caregrid_vector_index"
PRIMARY_KEY    = "facility_id"
TEXT_COLUMN    = "vector_text"
EMBEDDING_MODEL = "databricks-bge-large-en"

# ── Columns synced into the index ────────────────────────────────────────────
# Primary key + embedding text + 9 metadata columns.
# combined_medical_evidence and evidence_summary intentionally stay in the
# source table only and are joined back at retrieval time.
COLUMNS_TO_SYNC = [
    PRIMARY_KEY,
    TEXT_COLUMN,
    "name",
    "state",
    "city",
    "facility_type",
    "trust_score",
    "trust_category",
    "recommendation_readiness",
    "latitude",
    "longitude",
]

# ── Polling settings ─────────────────────────────────────────────────────────
POLL_INTERVAL_SEC   = 30
ENDPOINT_TIMEOUT_SEC = 30 * 60   # 30 min — first-time provisioning can be slow
INDEX_TIMEOUT_SEC    = 60 * 60   # 60 min — initial embedding of 10k rows

w = WorkspaceClient()

print(f"Source table   : {SOURCE_TABLE}")
print(f"Endpoint name  : {ENDPOINT_NAME}")
print(f"Index name     : {INDEX_NAME}")
print(f"Primary key    : {PRIMARY_KEY}")
print(f"Text column    : {TEXT_COLUMN}")
print(f"Embedding model: {EMBEDDING_MODEL}")
print(f"Synced columns : {COLUMNS_TO_SYNC}")

# Prerequisite — source table exists and has the expected columns
src_df = spark.read.table(SOURCE_TABLE)
src_count = src_df.count()
src_cols  = src_df.columns

missing = [c for c in COLUMNS_TO_SYNC if c not in src_cols]
if missing:
    raise ValueError(
        f"Source table {SOURCE_TABLE} is missing required columns: {missing}\n"
        f"Re-run notebooks/01_prepare_vector_source.py."
    )
if src_count == 0:
    raise ValueError(f"Source table {SOURCE_TABLE} is empty. Aborting.")

print(f"\n✓ Source table OK: {src_count:,} rows, all required columns present.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 2 — Create the vector search endpoint (idempotent)
# MAGIC
# MAGIC You can also do this in the UI: **Compute → Vector Search → Create endpoint**.
# MAGIC Pick name `caregrid-vector-endpoint` and type `Standard`.

# COMMAND ----------

# =============================================================================
# CELL 2 — Create or reuse the vector search endpoint
# =============================================================================

existing_endpoints = {
    ep.name for ep in w.vector_search_endpoints.list_endpoints()
}

if ENDPOINT_NAME in existing_endpoints:
    print(f"✓ Endpoint already exists: {ENDPOINT_NAME} — skipping create.")
else:
    print(f"Creating endpoint: {ENDPOINT_NAME} (type=STANDARD) …")
    w.vector_search_endpoints.create_endpoint(
        name=ENDPOINT_NAME,
        endpoint_type=EndpointType.STANDARD,
    )
    print(f"  → Submitted. Initial provisioning can take 5–10 minutes.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 3 — Wait for the endpoint to become ONLINE

# COMMAND ----------

# =============================================================================
# CELL 3 — Poll endpoint state until ONLINE (or timeout)
# =============================================================================

deadline = time.time() + ENDPOINT_TIMEOUT_SEC
last_state = None

while True:
    ep = w.vector_search_endpoints.get_endpoint(ENDPOINT_NAME)
    state = ep.endpoint_status.state
    if state != last_state:
        print(f"  Endpoint state: {state}")
        last_state = state

    if str(state).endswith("ONLINE"):
        print(f"\n✓ Endpoint ONLINE: {ENDPOINT_NAME}")
        break

    if time.time() > deadline:
        raise TimeoutError(
            f"Endpoint {ENDPOINT_NAME} did not reach ONLINE within "
            f"{ENDPOINT_TIMEOUT_SEC}s. Last state: {state}."
        )

    time.sleep(POLL_INTERVAL_SEC)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 4 — Create the Delta Sync index (idempotent)

# COMMAND ----------

# =============================================================================
# CELL 4 — Create the vector index (Delta Sync, TRIGGERED pipeline)
# Embedding is computed inside Databricks via the Foundation Model API.
# =============================================================================

existing_indexes = {
    idx.name for idx in w.vector_search_indexes.list_indexes(
        endpoint_name=ENDPOINT_NAME,
    )
}

if INDEX_NAME in existing_indexes:
    print(f"✓ Index already exists: {INDEX_NAME} — skipping create.")
else:
    print(f"Creating Delta Sync index: {INDEX_NAME} …")
    w.vector_search_indexes.create_index(
        name=INDEX_NAME,
        endpoint_name=ENDPOINT_NAME,
        primary_key=PRIMARY_KEY,
        index_type=VectorIndexType.DELTA_SYNC,
        delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
            source_table=SOURCE_TABLE,
            pipeline_type=PipelineType.TRIGGERED,
            embedding_source_columns=[
                EmbeddingSourceColumn(
                    name=TEXT_COLUMN,
                    embedding_model_endpoint_name=EMBEDDING_MODEL,
                )
            ],
            columns_to_sync=COLUMNS_TO_SYNC,
        ),
    )
    print(f"  → Submitted. Initial embedding of {src_count:,} rows takes a few minutes.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 5 — Wait for the index to be READY

# COMMAND ----------

# =============================================================================
# CELL 5 — Poll index status until ready=true (or timeout)
# =============================================================================

deadline = time.time() + INDEX_TIMEOUT_SEC
last_detail = None

while True:
    idx = w.vector_search_indexes.get_index(INDEX_NAME)
    status = idx.status
    detail = getattr(status, "detailed_state", None) or getattr(status, "message", "")
    ready  = bool(getattr(status, "ready", False))
    indexed_rows = getattr(status, "indexed_row_count", None)

    if detail != last_detail:
        print(f"  Index state: ready={ready}  detail={detail}  indexed_rows={indexed_rows}")
        last_detail = detail

    if ready:
        print(f"\n✓ Index READY: {INDEX_NAME}")
        print(f"  Indexed rows: {indexed_rows}")
        break

    if time.time() > deadline:
        raise TimeoutError(
            f"Index {INDEX_NAME} did not become ready within "
            f"{INDEX_TIMEOUT_SEC}s. Last detail: {detail}."
        )

    time.sleep(POLL_INTERVAL_SEC)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 6 — Smoke-test query
# MAGIC
# MAGIC Runs a representative semantic query and prints the top results. This
# MAGIC confirms the endpoint, the index, and the embedding model are all
# MAGIC wired up correctly end-to-end.

# COMMAND ----------

# =============================================================================
# CELL 6 — Run a smoke-test query against the live index
# =============================================================================

TEST_QUERY = "ICU hospital with dialysis in Mumbai"

print(f"Query: {TEST_QUERY!r}\n")

result = w.vector_search_indexes.query_index(
    index_name=INDEX_NAME,
    query_text=TEST_QUERY,
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

rows = result.result.data_array
print(f"Returned {len(rows)} rows:\n")
for i, row in enumerate(rows, start=1):
    print(f"  {i}. {row}")

if not rows:
    print(
        "\n⚠ No rows returned. Possible causes:\n"
        "  • Initial sync still in progress — wait a minute and retry.\n"
        "  • Source table has no rows matching the query semantics.\n"
        "  • Embedding model endpoint not yet warm — retry once."
    )

# Optional: same query with a server-side filter
print("\nWith filter state=Maharashtra AND trust_score >= 0.6:\n")

filtered = w.vector_search_indexes.query_index(
    index_name=INDEX_NAME,
    query_text=TEST_QUERY,
    columns=["facility_id", "name", "city", "state", "trust_score", "trust_category"],
    num_results=5,
    filters_json='{"state": "Maharashtra", "trust_score >=": 0.6}',
)

for i, row in enumerate(filtered.result.data_array, start=1):
    print(f"  {i}. {row}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 7 — Environment variable summary
# MAGIC
# MAGIC Add these to the agent's local `.env` so the Python package can talk to
# MAGIC the index. **Do not commit `.env` to git.** When running inside
# MAGIC Databricks, `DATABRICKS_HOST` and `DATABRICKS_TOKEN` are not needed —
# MAGIC the runtime identity is used automatically.

# COMMAND ----------

# =============================================================================
# CELL 7 — Print the env-var snippet the agent needs
# =============================================================================

print("# ── Add to .env (do not commit) ─────────────────────────────────────")
print(f'DATABRICKS_HOST=https://<your-workspace>.cloud.databricks.com')
print(f'DATABRICKS_TOKEN=<your-personal-access-token>   # or use OAuth')
print(f'VECTOR_SOURCE_TABLE={SOURCE_TABLE}')
print(f'VECTOR_SEARCH_ENDPOINT={ENDPOINT_NAME}')
print(f'VECTOR_SEARCH_INDEX={INDEX_NAME}')
print(f'VECTOR_SEARCH_ENABLED=true')
print()
print("# ── Fallback ────────────────────────────────────────────────────────")
print("# Set VECTOR_SEARCH_ENABLED=false to bypass Databricks entirely and use")
print("# agent_core/local_retriever.py (in-memory pandas keyword search).")
print("# The agent works fully offline in that mode — no Databricks call is")
print("# made and no credentials are required.")
print()
print(f"\nNext step → wire up agent_core/vector_retriever.py to call:")
print(f"  WorkspaceClient().vector_search_indexes.query_index(")
print(f"      index_name={INDEX_NAME!r}, ...")
print(f"  )")
