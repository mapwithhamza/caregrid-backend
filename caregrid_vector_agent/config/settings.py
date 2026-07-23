"""
config.settings — environment-driven application configuration.

Each field is read once from the environment / ``.env`` file at process
start (via ``pydantic-settings``) and exposed as the module-level
``settings`` singleton.

Some env vars accept **two equivalent names** so that older ``.env``
files and external docs keep working alongside the canonical names
used inside the package. The mapping is:

==============================  ============================================================
Field                           Accepted env var names (any one wins; first found takes precedence)
==============================  ============================================================
``tavily_enabled``              ``TAVILY_ENABLED`` *or* ``ENABLE_TAVILY``
``tavily_max_web_verified``     ``TAVILY_MAX_WEB_VERIFIED`` *or* ``TAVILY_MAX_RESULTS``
``vector_search_enabled``       ``VECTOR_SEARCH_ENABLED`` *or* ``ENABLE_VECTOR_SEARCH``
``vector_search_endpoint``      ``VECTOR_SEARCH_ENDPOINT`` *or* ``DATABRICKS_VECTOR_SEARCH_ENDPOINT`` *or* ``DATABRICKS_VECTOR_ENDPOINT``
``vector_search_index``         ``VECTOR_SEARCH_INDEX`` *or* ``DATABRICKS_VECTOR_INDEX_NAME`` *or* ``DATABRICKS_VECTOR_INDEX``
==============================  ============================================================

For dual-name fields, ``populate_by_name=True`` lets unit tests
construct ``Settings(field_name=...)`` directly without going through
the env-var alias.
"""

from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Domain constants — values must match the data contract exactly; do not rename
# ---------------------------------------------------------------------------
TRUST_CATEGORIES: list[str] = [
    "High Trust / Evidence Supported",
    "Moderate Trust / Verify Before Use",
    "Low Trust / Needs Human Verification",
    "High Risk / Insufficient Evidence",
]

RECOMMENDATION_READINESS_VALUES: list[str] = [
    "Ready for recommendation",
    "Usable with verification",
    "Do not recommend without human review",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # --- Paths ---
    local_data_path: str = Field(default="data", description="Root data directory")
    data_raw_dir: str = Field(default="data/raw")
    data_processed_dir: str = Field(default="data/processed")
    vector_source_dir: str = Field(default="data/vector_source")
    outputs_dir: str = Field(default="data/outputs")
    audit_log_path: str = Field(default="data/outputs/audit_log.jsonl")

    # --- Databricks Mosaic AI Vector Search ---
    databricks_host: str = Field(default="", description="Databricks workspace URL")
    databricks_token: str = Field(default="", description="Databricks personal access token")
    databricks_catalog: str = Field(default="main")
    databricks_schema: str = Field(default="caregrid")
    vector_source_table: str = Field(
        default="main.caregrid.facilities",
        description="Source Delta table for vector index sync",
    )
    vector_search_endpoint: str = Field(
        default="",
        description="Mosaic AI Vector Search endpoint name",
        validation_alias=AliasChoices(
            "VECTOR_SEARCH_ENDPOINT",
            "DATABRICKS_VECTOR_SEARCH_ENDPOINT",
            "DATABRICKS_VECTOR_ENDPOINT",
        ),
    )
    vector_search_index: str = Field(
        default="",
        description="Fully qualified vector index name",
        validation_alias=AliasChoices(
            "VECTOR_SEARCH_INDEX",
            "DATABRICKS_VECTOR_INDEX_NAME",
            "DATABRICKS_VECTOR_INDEX",
        ),
    )
    vector_search_enabled: bool = Field(
        default=False,
        description="Use Databricks vector search; falls back to local_retriever if False",
        validation_alias=AliasChoices(
            "VECTOR_SEARCH_ENABLED",
            "ENABLE_VECTOR_SEARCH",
        ),
    )

    # --- Tavily (optional external verification) ---
    tavily_api_key: Optional[str] = Field(
        default=None,
        description="Tavily API key — leave blank to disable",
    )
    tavily_enabled: bool = Field(
        default=False,
        description="Enable Tavily external web verification",
        validation_alias=AliasChoices(
            "TAVILY_ENABLED",
            "ENABLE_TAVILY",
        ),
    )
    tavily_default_depth: str = Field(
        default="basic",
        description="Tavily search depth: basic or advanced",
    )
    tavily_max_web_verified: int = Field(
        default=3,
        description="Max facilities to verify via Tavily per query",
        validation_alias=AliasChoices(
            "TAVILY_MAX_WEB_VERIFIED",
            "TAVILY_MAX_RESULTS",
        ),
    )
    tavily_cache_dir: str = Field(default="data/tavily_cache")

    # --- MLflow ---
    mlflow_enabled: bool = Field(default=False)
    mlflow_tracking_uri: str = Field(default="mlruns")
    mlflow_experiment_name: str = Field(default="caregrid_vector_agent")

    # --- Agent behaviour ---
    max_results: int = Field(default=10, description="Max facilities returned per query")
    trust_score_threshold: float = Field(
        default=0.6,
        description="Minimum trust_score for recommendations",
    )


settings = Settings()
