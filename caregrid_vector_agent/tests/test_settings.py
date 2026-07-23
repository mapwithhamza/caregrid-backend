import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.settings import Settings, TRUST_CATEGORIES, RECOMMENDATION_READINESS_VALUES
from agent_core.schemas import (
    FacilityRecord,
    AgentQuery,
    AgentIntent,
    EvidenceSnippet,
    ValidationFinding,
    WebVerificationResult,
    AgentRecommendation,
    AgentResponse,
)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def test_settings_instantiates():
    s = Settings()
    assert s is not None


def test_settings_defaults(monkeypatch):
    """Settings defaults must hold when no env vars and no .env file
    are present. The local developer .env (gitignored) may override
    these at runtime, so we isolate the test by clearing every alias
    env var and disabling env_file loading."""
    for name in (
        "TAVILY_ENABLED", "ENABLE_TAVILY",
        "TAVILY_MAX_WEB_VERIFIED", "TAVILY_MAX_RESULTS",
        "VECTOR_SEARCH_ENABLED", "ENABLE_VECTOR_SEARCH",
        "VECTOR_SEARCH_ENDPOINT", "DATABRICKS_VECTOR_SEARCH_ENDPOINT",
        "VECTOR_SEARCH_INDEX", "DATABRICKS_VECTOR_INDEX_NAME",
        "TAVILY_API_KEY", "MLFLOW_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None)
    assert s.vector_search_enabled is False
    assert s.tavily_enabled is False
    assert s.mlflow_enabled is False
    assert s.max_results == 10
    assert s.trust_score_threshold == 0.6
    assert s.databricks_catalog == "main"
    assert s.databricks_schema == "caregrid"
    assert s.tavily_default_depth == "basic"
    assert s.tavily_max_web_verified == 3
    assert s.mlflow_experiment_name == "caregrid_vector_agent"
    assert s.local_data_path == "data"


def test_settings_required_fields_exist():
    s = Settings()
    # All spec-required attributes must be present
    required = [
        "local_data_path", "tavily_api_key", "tavily_enabled", "tavily_default_depth",
        "tavily_max_web_verified", "databricks_host", "databricks_token",
        "vector_source_table", "vector_search_endpoint", "vector_search_index",
        "vector_search_enabled", "mlflow_enabled", "mlflow_experiment_name",
    ]
    for attr in required:
        assert hasattr(s, attr), f"Settings missing field: {attr}"


# ---------------------------------------------------------------------------
# Dual-name env var aliases — both naming styles must populate the same field
# ---------------------------------------------------------------------------

def _clear_alias_env(monkeypatch):
    """Strip every env var that any of our dual-name fields reads from.

    Required so that one variant doesn't bleed into a test that exercises the
    other.
    """
    for name in (
        "TAVILY_ENABLED", "ENABLE_TAVILY",
        "TAVILY_MAX_WEB_VERIFIED", "TAVILY_MAX_RESULTS",
        "VECTOR_SEARCH_ENABLED", "ENABLE_VECTOR_SEARCH",
        "VECTOR_SEARCH_ENDPOINT", "DATABRICKS_VECTOR_SEARCH_ENDPOINT",
        "VECTOR_SEARCH_INDEX", "DATABRICKS_VECTOR_INDEX_NAME",
        "TAVILY_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def _settings_no_dotenv() -> Settings:
    """Build a Settings without reading the on-disk .env file.

    The user's local .env may set TAVILY_API_KEY and friends, which would
    bleed into these alias tests. Disabling env_file isolates them.
    """
    return Settings(_env_file=None)


def test_tavily_enabled_canonical_name(monkeypatch):
    _clear_alias_env(monkeypatch)
    monkeypatch.setenv("TAVILY_ENABLED", "true")
    s = _settings_no_dotenv()
    assert s.tavily_enabled is True


def test_tavily_enabled_alias_name(monkeypatch):
    _clear_alias_env(monkeypatch)
    monkeypatch.setenv("ENABLE_TAVILY", "true")
    s = _settings_no_dotenv()
    assert s.tavily_enabled is True


def test_tavily_max_web_verified_canonical_name(monkeypatch):
    _clear_alias_env(monkeypatch)
    monkeypatch.setenv("TAVILY_MAX_WEB_VERIFIED", "7")
    s = _settings_no_dotenv()
    assert s.tavily_max_web_verified == 7


def test_tavily_max_web_verified_alias_name(monkeypatch):
    _clear_alias_env(monkeypatch)
    monkeypatch.setenv("TAVILY_MAX_RESULTS", "4")
    s = _settings_no_dotenv()
    assert s.tavily_max_web_verified == 4


def test_vector_search_enabled_canonical_name(monkeypatch):
    _clear_alias_env(monkeypatch)
    monkeypatch.setenv("VECTOR_SEARCH_ENABLED", "true")
    s = _settings_no_dotenv()
    assert s.vector_search_enabled is True


def test_vector_search_enabled_alias_name(monkeypatch):
    _clear_alias_env(monkeypatch)
    monkeypatch.setenv("ENABLE_VECTOR_SEARCH", "true")
    s = _settings_no_dotenv()
    assert s.vector_search_enabled is True


def test_vector_search_endpoint_canonical_name(monkeypatch):
    _clear_alias_env(monkeypatch)
    monkeypatch.setenv("VECTOR_SEARCH_ENDPOINT", "caregrid-vs-endpoint-canonical")
    s = _settings_no_dotenv()
    assert s.vector_search_endpoint == "caregrid-vs-endpoint-canonical"


def test_vector_search_endpoint_alias_name(monkeypatch):
    _clear_alias_env(monkeypatch)
    monkeypatch.setenv(
        "DATABRICKS_VECTOR_SEARCH_ENDPOINT", "caregrid-vs-endpoint-alias",
    )
    s = _settings_no_dotenv()
    assert s.vector_search_endpoint == "caregrid-vs-endpoint-alias"


def test_vector_search_index_canonical_name(monkeypatch):
    _clear_alias_env(monkeypatch)
    monkeypatch.setenv("VECTOR_SEARCH_INDEX", "workspace.default.canonical_index")
    s = _settings_no_dotenv()
    assert s.vector_search_index == "workspace.default.canonical_index"


def test_vector_search_index_alias_name(monkeypatch):
    _clear_alias_env(monkeypatch)
    monkeypatch.setenv(
        "DATABRICKS_VECTOR_INDEX_NAME", "workspace.default.alias_index",
    )
    s = _settings_no_dotenv()
    assert s.vector_search_index == "workspace.default.alias_index"


def test_tavily_api_key_loads_from_env(monkeypatch):
    _clear_alias_env(monkeypatch)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key-do-not-use")
    s = _settings_no_dotenv()
    assert s.tavily_api_key == "tvly-test-key-do-not-use"


# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

def test_trust_categories_exact():
    assert TRUST_CATEGORIES == [
        "High Trust / Evidence Supported",
        "Moderate Trust / Verify Before Use",
        "Low Trust / Needs Human Verification",
        "High Risk / Insufficient Evidence",
    ]


def test_trust_categories_length():
    assert len(TRUST_CATEGORIES) == 4


def test_recommendation_readiness_exact():
    assert RECOMMENDATION_READINESS_VALUES == [
        "Ready for recommendation",
        "Usable with verification",
        "Do not recommend without human review",
    ]


def test_recommendation_readiness_length():
    assert len(RECOMMENDATION_READINESS_VALUES) == 3


# ---------------------------------------------------------------------------
# Schema instantiation
# ---------------------------------------------------------------------------

def test_facility_record_instantiates():
    r = FacilityRecord(facility_id="F001")
    assert r.facility_id == "F001"
    assert r.trust_score == 0.0
    assert r.combined_medical_evidence == ""


def test_agent_query_instantiates():
    q = AgentQuery(query="Find ICU hospitals in Delhi")
    assert q.query == "Find ICU hospitals in Delhi"
    assert q.top_k == 10
    assert q.min_trust_score == 0.0


def test_agent_intent_instantiates():
    i = AgentIntent(raw_query="ICU in Mumbai")
    assert i.raw_query == "ICU in Mumbai"
    assert i.capabilities_required == []
    assert i.location is None


def test_evidence_snippet_instantiates():
    s = EvidenceSnippet(facility_id="F001", excerpt="ICU available with 20 beds.")
    assert s.facility_id == "F001"
    assert s.source_field == "combined_medical_evidence"
    assert s.relevance_score is None


def test_validation_finding_instantiates():
    f = ValidationFinding(facility_id="F001", rule="trust_score_check", severity="warning", message="Low trust score")
    assert f.severity == "warning"
    assert f.rule == "trust_score_check"


def test_web_verification_result_instantiates():
    r = WebVerificationResult(facility_id="F001", query_used="Apollo Hospital Delhi ICU")
    assert r.verified is False
    assert r.cached is False
    assert r.sources == []


def test_agent_recommendation_instantiates():
    rec = AgentRecommendation(
        facility_id="F001",
        trust_score=0.85,
        trust_category="High Trust / Evidence Supported",
        recommendation_readiness="Ready for recommendation",
    )
    assert rec.trust_score == 0.85
    assert rec.evidence_snippets == []
    assert rec.web_verification is None


def test_agent_response_instantiates():
    resp = AgentResponse()
    assert resp.evidence == []
    assert resp.warnings == []
    assert resp.reasoning == ""
    assert resp.safety_note == ""
    assert resp.recommendations == []
    assert resp.validation_findings == []


def test_agent_response_full():
    snippet = EvidenceSnippet(facility_id="F001", excerpt="Has ICU.")
    resp = AgentResponse(
        query="ICU hospitals Delhi",
        evidence=[snippet],
        reasoning="Matched ICU keyword.",
        safety_note="Verify before admission.",
    )
    assert len(resp.evidence) == 1
    assert resp.evidence[0].facility_id == "F001"
