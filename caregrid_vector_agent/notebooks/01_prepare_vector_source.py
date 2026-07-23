# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # CareGrid — Vector Source Preparation
# MAGIC
# MAGIC **Purpose:** Build `workspace.default.caregrid_vector_source` — the Delta table
# MAGIC that Databricks Mosaic AI Vector Search will index.
# MAGIC
# MAGIC **Steps:**
# MAGIC 1. Load source facility table (primary or fallback)
# MAGIC 2. Select required output columns
# MAGIC 3. Build `vector_text` (embedding-optimised per-row string)
# MAGIC 4. Run quality checks
# MAGIC 5. Save as Delta table
# MAGIC 6. Verify the saved table
# MAGIC
# MAGIC **Do not** create the vector search endpoint or index in this notebook.
# MAGIC See `02_create_vector_index_notes.py` for that step.

# COMMAND ----------

# =============================================================================
# CELL 1 — Setup: imports and table names
# =============================================================================

from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType
from pyspark.sql.functions import col, udf, trim, length, avg

# ── Table names ──────────────────────────────────────────────────────────────
# Switch SOURCE_TABLE to FALLBACK if the primary table is not available.
SOURCE_TABLE_PRIMARY  = "workspace.default.caregrid_india_trust_v2_geo_export_ready"
SOURCE_TABLE_FALLBACK = "workspace.default.caregrid_backend_export_full"
OUTPUT_TABLE          = "workspace.default.caregrid_vector_source"

# ── Required columns in the output table ─────────────────────────────────────
REQUIRED_OUTPUT_COLUMNS = [
    "facility_id",
    "name",
    "city",
    "state",
    "facility_type",
    "latitude",
    "longitude",
    "trust_score",
    "trust_category",
    "recommendation_readiness",
    "vector_text",                  # built in Cell 4
    "combined_medical_evidence",
    "evidence_summary",
]

# ── Extra columns consumed when building vector_text ─────────────────────────
# These are included in the select step but dropped from the final output.
ENRICHMENT_COLUMNS = [
    "specialties",
    "procedures",
    "equipment",
    "capabilities_raw",
]

print(f"Primary source : {SOURCE_TABLE_PRIMARY}")
print(f"Fallback source: {SOURCE_TABLE_FALLBACK}")
print(f"Output table   : {OUTPUT_TABLE}")
print(f"Output columns : {REQUIRED_OUTPUT_COLUMNS}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 2 — Load source table

# COMMAND ----------

# =============================================================================
# CELL 2 — Load source table, print schema and row count, display sample
# =============================================================================

# Try the primary export table; fall back to the full backend export if absent.
try:
    raw_df = spark.read.table(SOURCE_TABLE_PRIMARY)
    active_source = SOURCE_TABLE_PRIMARY
    print(f"✓ Loaded primary table: {active_source}")
except Exception as primary_err:
    print(f"Primary table unavailable ({primary_err})")
    print(f"  → Trying fallback: {SOURCE_TABLE_FALLBACK}")
    raw_df = spark.read.table(SOURCE_TABLE_FALLBACK)
    active_source = SOURCE_TABLE_FALLBACK
    print(f"✓ Loaded fallback table: {active_source}")

row_count_raw = raw_df.count()
print(f"\nRow count : {row_count_raw:,}")
print(f"Columns   : {len(raw_df.columns)}")
print("\nAll columns in source table:")
for c in raw_df.columns:
    print(f"  {c}")

print("\nSample rows (5):")
display(raw_df.limit(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 3 — Select required fields

# COMMAND ----------

# =============================================================================
# CELL 3 — Select required fields
# Handles source tables that are missing optional columns by substituting
# safe null/empty defaults. facility_id must be present.
# =============================================================================

if "facility_id" not in raw_df.columns:
    raise ValueError(
        "Source table is missing 'facility_id'. "
        f"Available columns: {raw_df.columns}"
    )


def _safe_col(df, col_name, default=None, cast_type=None):
    """
    Return a Column expression for col_name.
    If the column is absent, substitute a literal default instead of failing.
    """
    if col_name in df.columns:
        c = F.col(col_name)
    elif default is None:
        c = F.lit(None).cast(StringType())
    else:
        c = F.lit(default)
    if cast_type is not None:
        c = c.cast(cast_type)
    return c.alias(col_name)


select_exprs = [
    # ── Identity ─────────────────────────────────────────────────────────────
    _safe_col(raw_df, "facility_id"),
    _safe_col(raw_df, "name",                        default=""),
    _safe_col(raw_df, "city",                         default=""),
    _safe_col(raw_df, "state",                        default=""),
    _safe_col(raw_df, "facility_type",                default=""),
    # ── Geo ──────────────────────────────────────────────────────────────────
    _safe_col(raw_df, "latitude",                     cast_type=DoubleType()),
    _safe_col(raw_df, "longitude",                    cast_type=DoubleType()),
    # ── Trust ────────────────────────────────────────────────────────────────
    _safe_col(raw_df, "trust_score",                  default=0.0, cast_type=DoubleType()),
    _safe_col(raw_df, "trust_category",               default=""),
    _safe_col(raw_df, "recommendation_readiness",     default=""),
    # ── Evidence ─────────────────────────────────────────────────────────────
    _safe_col(raw_df, "combined_medical_evidence",    default=""),
    _safe_col(raw_df, "evidence_summary",             default=""),
    # ── Enrichment (used to build vector_text; dropped in Cell 4) ────────────
    _safe_col(raw_df, "specialties",                  default=""),
    _safe_col(raw_df, "procedures",                   default=""),
    _safe_col(raw_df, "equipment",                    default=""),
    _safe_col(raw_df, "capabilities_raw",             default=""),
]

selected_df = raw_df.select(select_exprs)

print(f"Selected {len(selected_df.columns)} columns: {selected_df.columns}")
print(f"Row count after select: {selected_df.count():,}")

display(selected_df.limit(3))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 4 — Build vector_text

# COMMAND ----------

# =============================================================================
# CELL 4 — Build vector_text
# Each row is converted to an embedding-optimised string that combines
# facility identity, location, clinical specialties, procedures, equipment,
# capability signals, and evidence narrative.
# Pipe-delimited sections; null/NaN/list-like values are silently cleaned.
# =============================================================================

def _clean(val) -> str:
    """
    Sanitise a single field value for inclusion in vector_text.
    - Returns "" for None, NaN, "null", "nan", "none", "n/a", "<na>"
    - Unwraps list-like strings: "['ICU', 'dialysis']" → "ICU, dialysis"
    """
    if val is None:
        return ""
    s = str(val).strip()
    if not s or s.lower() in ("none", "nan", "null", "n/a", "na", "<na>", "nat"):
        return ""
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].replace("'", "").replace('"', "")
        parts = [p.strip() for p in inner.split(",") if p.strip()]
        return ", ".join(parts)
    return s


def _build_vector_text(
    name, facility_type, city, state,
    specialties, procedures, equipment, capabilities_raw,
    evidence_summary, combined_medical_evidence,
) -> str:
    """
    Assemble the final vector_text string.

    Output structure (pipe-separated, empty sections omitted):
        <name> | <facility_type>
        <city>, <state>
        <specialties>
        <procedures>
        <equipment>
        <capabilities_raw>
        <evidence_summary>
        <combined_medical_evidence>
    """
    sections = []

    # Facility identity
    identity = " | ".join(filter(None, [_clean(name), _clean(facility_type)]))
    if identity:
        sections.append(identity)

    # Location
    location = ", ".join(filter(None, [_clean(city), _clean(state)]))
    if location:
        sections.append(location)

    # Clinical content
    for raw_val in [specialties, procedures, equipment, capabilities_raw]:
        cleaned = _clean(raw_val)
        if cleaned:
            sections.append(cleaned)

    # Evidence narrative (summary first for higher weight in early tokens)
    for ev in [evidence_summary, combined_medical_evidence]:
        cleaned = _clean(ev)
        if cleaned:
            sections.append(cleaned)

    return " | ".join(sections)


build_vector_text_udf = udf(_build_vector_text, StringType())

enriched_df = selected_df.withColumn(
    "vector_text",
    build_vector_text_udf(
        F.col("name"),
        F.col("facility_type"),
        F.col("city"),
        F.col("state"),
        F.col("specialties"),
        F.col("procedures"),
        F.col("equipment"),
        F.col("capabilities_raw"),
        F.col("evidence_summary"),
        F.col("combined_medical_evidence"),
    ),
)

# Drop enrichment columns — not part of the final output schema
final_df = enriched_df.drop(*ENRICHMENT_COLUMNS)

print(f"Final columns ({len(final_df.columns)}): {final_df.columns}")
print("\nvector_text samples:")
display(
    final_df
    .select("facility_id", "name", "city", "state", "vector_text")
    .limit(5)
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 5 — Quality checks

# COMMAND ----------

# =============================================================================
# CELL 5 — Quality checks
# Expected: ~10,000 rows, 0 null facility_id, 0 empty vector_text
# =============================================================================

row_count_final   = final_df.count()
null_facility_ids = final_df.filter(F.col("facility_id").isNull()).count()
empty_vector_text = final_df.filter(
    F.col("vector_text").isNull() | (F.trim(F.col("vector_text")) == "")
).count()
avg_vector_len = (
    final_df
    .select(F.avg(F.length(F.col("vector_text"))).alias("avg_len"))
    .collect()[0]["avg_len"]
) or 0.0
min_vector_len = (
    final_df
    .select(F.min(F.length(F.col("vector_text"))).alias("min_len"))
    .collect()[0]["min_len"]
) or 0

print("=" * 60)
print("Quality report")
print("=" * 60)
print(f"  Row count            : {row_count_final:>8,}   (expected ~10,000)")
print(f"  Null facility_id     : {null_facility_ids:>8}   (must be 0)")
print(f"  Empty vector_text    : {empty_vector_text:>8}   (must be 0)")
print(f"  Avg vector_text len  : {avg_vector_len:>8.0f}   chars")
print(f"  Min vector_text len  : {min_vector_len:>8}   chars")
print("=" * 60)

# Hard failures
if null_facility_ids > 0:
    raise ValueError(f"ABORT: {null_facility_ids} rows have null facility_id.")

# Soft warnings — do not abort; log for investigation
if empty_vector_text > 0:
    print(f"\nWARNING: {empty_vector_text} rows have empty vector_text.")
    print("  These rows may not be retrievable via semantic search.")
    display(final_df.filter(F.col("vector_text").isNull() | (F.trim(F.col("vector_text")) == "")).limit(10))

if row_count_final < 9_000:
    print(f"\nWARNING: Row count ({row_count_final:,}) is well below expected ~10,000.")
    print("  Check that the correct source table was used.")

# trust_category distribution
print("\ntrust_category distribution:")
display(
    final_df
    .groupBy("trust_category")
    .count()
    .orderBy(F.col("count").desc())
)

# recommendation_readiness distribution
print("\nrecommendation_readiness distribution:")
display(
    final_df
    .groupBy("recommendation_readiness")
    .count()
    .orderBy(F.col("count").desc())
)

# trust_score stats
print("\ntrust_score statistics:")
display(
    final_df
    .select(
        F.min("trust_score").alias("min"),
        F.max("trust_score").alias("max"),
        F.avg("trust_score").alias("mean"),
        F.expr("percentile(trust_score, 0.5)").alias("median"),
    )
)

# Final sample
print("\nSample output rows:")
display(
    final_df
    .select(
        "facility_id", "name", "city", "state",
        "trust_score", "trust_category", "recommendation_readiness",
        "vector_text",
    )
    .orderBy(F.col("trust_score").desc())
    .limit(10)
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 6 — Save Delta table

# COMMAND ----------

# =============================================================================
# CELL 6 — Save as Delta table
# Writes workspace.default.caregrid_vector_source.
# Uses overwrite mode so re-runs are idempotent.
# =============================================================================

print(f"Writing to: {OUTPUT_TABLE}")
print(f"Rows to write: {row_count_final:,}")
print(f"Columns: {final_df.columns}")

(
    final_df
    .write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(OUTPUT_TABLE)
)

print(f"\n✓ Saved: {OUTPUT_TABLE}")
print(f"  Source : {active_source}")
print(f"  Rows   : {row_count_final:,}")
print(f"  Columns: {final_df.columns}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 7 — Verify saved table

# COMMAND ----------

# =============================================================================
# CELL 7 — Read the saved table back and verify
# =============================================================================

verified_df    = spark.read.table(OUTPUT_TABLE)
verified_count = verified_df.count()
verified_cols  = verified_df.columns

print(f"Verified table : {OUTPUT_TABLE}")
print(f"Verified rows  : {verified_count:,}")
print(f"Verified cols  : {verified_cols}")

assert verified_count == row_count_final, (
    f"Row count mismatch: wrote {row_count_final:,}, read back {verified_count:,}"
)

missing_cols = [c for c in REQUIRED_OUTPUT_COLUMNS if c not in verified_cols]
if missing_cols:
    raise ValueError(f"Output table is missing expected columns: {missing_cols}")

print("\n✓ All required columns present.")
print(f"✓ Row count matches: {verified_count:,}")

display(
    verified_df
    .select(
        "facility_id", "name", "city", "state",
        "trust_score", "trust_category",
        "vector_text", "combined_medical_evidence",
    )
    .orderBy(F.col("trust_score").desc())
    .limit(10)
)

print(f"\nNext step → notebooks/02_create_vector_index_notes.py")
print(f"Table ready for vector search indexing: {OUTPUT_TABLE}")
