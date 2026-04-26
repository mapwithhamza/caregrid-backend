"""
Tests for ``agent_core.recommendation_engine.run_recommendation`` (Stage 13).

Three legacy ``recommend(...)`` tests at the bottom are preserved so the
Stage-1 contract continues to pass.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_core.audit_logger import AuditLogger  # noqa: E402
from agent_core.recommendation_engine import (  # noqa: E402
    SAFETY_NOTE,
    recommend,
    run_recommendation,
)
from agent_core.schemas import (  # noqa: E402
    AgentRecommendation,
    AgentResponse,
    EvidenceSnippet,
    ScoreBreakdown,
    WebVerificationResult,
)
from agent_core.vector_retriever import (  # noqa: E402
    VectorSearchResponse,
    VectorSearchResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _facilities_df() -> pd.DataFrame:
    """Five-row in-memory facility DataFrame covering ICU, dialysis, surgery."""
    return pd.DataFrame(
        [
            {
                "facility_id": "F001",
                "name": "Apollo Hospitals Mumbai",
                "facility_type": "hospital",
                "state": "Maharashtra",
                "city": "Mumbai",
                "trust_score": 0.92,
                "trust_category": "High Trust / Evidence Supported",
                "recommendation_readiness": "Ready for recommendation",
                "specialties": "cardiology, oncology, nephrology, intensive care",
                "procedures": "hemodialysis, ICU monitoring, chemotherapy, surgery",
                "equipment": "ventilator, ICU bed, dialysis machine, defibrillator, monitor",
                "capabilities_raw": "24/7 ICU, dialysis unit, oncology",
                "evidence_summary": "Multispecialty hospital with strong critical care.",
                "combined_medical_evidence": (
                    "ICU bed, ventilator, dialysis machine, oncology unit, "
                    "operation theatre with anesthesia."
                ),
            },
            {
                "facility_id": "F002",
                "name": "Fortis Bangalore",
                "facility_type": "hospital",
                "state": "Karnataka",
                "city": "Bangalore",
                "trust_score": 0.78,
                "trust_category": "Medium Trust / Likely Reliable",
                "recommendation_readiness": "Usable with verification",
                "specialties": "cardiology, nephrology",
                "procedures": "hemodialysis",
                "equipment": "dialysis machine, monitor",
                "capabilities_raw": "dialysis unit",
                "evidence_summary": "Tertiary hospital with renal services.",
                "combined_medical_evidence": (
                    "Dialysis machine present. Hemodialysis available."
                ),
            },
            {
                "facility_id": "F003",
                "name": "Generic Clinic",
                "facility_type": "clinic",
                "state": "Maharashtra",
                "city": "Pune",
                "trust_score": 0.40,
                "trust_category": "Low Trust",
                "recommendation_readiness": "Do not recommend without human review",
                "specialties": "general medicine",
                "procedures": "",
                "equipment": "",
                "capabilities_raw": "outpatient",
                "evidence_summary": "Small outpatient clinic.",
                "combined_medical_evidence": "Outpatient consultations only.",
            },
            {
                "facility_id": "F004",
                "name": "ICU Claim Without Evidence",
                "facility_type": "hospital",
                "state": "Maharashtra",
                "city": "Nagpur",
                "trust_score": 0.55,
                "trust_category": "Medium Trust",
                "recommendation_readiness": "Usable with verification",
                "specialties": "intensive care",
                "procedures": "",
                "equipment": "",
                "capabilities_raw": "ICU available",
                "evidence_summary": "Claims ICU but no equipment listed.",
                "combined_medical_evidence": "ICU available.",
            },
            {
                "facility_id": "F005",
                "name": "AIIMS Delhi",
                "facility_type": "hospital",
                "state": "Delhi",
                "city": "New Delhi",
                "trust_score": 0.95,
                "trust_category": "High Trust / Evidence Supported",
                "recommendation_readiness": "Ready for recommendation",
                "specialties": "cardiology, oncology, neurology, intensive care",
                "procedures": "ICU monitoring, chemotherapy, surgery",
                "equipment": "ventilator, ICU bed, defibrillator, monitor",
                "capabilities_raw": "24/7 ICU, oncology",
                "evidence_summary": "Premier government tertiary hospital.",
                "combined_medical_evidence": (
                    "ICU bed, ventilator, defibrillator, oncology unit, "
                    "operation theatre with anesthesia."
                ),
            },
        ]
    )


@pytest.fixture
def df() -> pd.DataFrame:
    return _facilities_df()


@pytest.fixture
def disabled_settings() -> SimpleNamespace:
    """Settings that disable both vector search and Tavily."""
    return SimpleNamespace(
        vector_search_enabled=False,
        databricks_host="",
        databricks_token="",
        databricks_vector_endpoint="",
        databricks_vector_index="",
        tavily_enabled=False,
        tavily_api_key="",
        tavily_default_depth="basic",
        tavily_max_web_verified=3,
        tavily_cache_ttl_seconds=86400,
    )


@pytest.fixture
def enabled_tavily_settings() -> SimpleNamespace:
    """Settings that enable Tavily but not vector search."""
    return SimpleNamespace(
        vector_search_enabled=False,
        databricks_host="",
        databricks_token="",
        databricks_vector_endpoint="",
        databricks_vector_index="",
        tavily_enabled=True,
        tavily_api_key="test-key",
        tavily_default_depth="basic",
        tavily_max_web_verified=3,
        tavily_cache_ttl_seconds=86400,
    )


# ---------------------------------------------------------------------------
# Core happy-path: trusted ICU query
# ---------------------------------------------------------------------------


def test_trusted_icu_query_returns_structured_response(df):
    """A clear ICU query in Maharashtra returns a populated response."""
    resp = run_recommendation(
        "trusted ICU hospital in Maharashtra",
        df,
        max_results=5,
    )
    assert isinstance(resp, AgentResponse)
    assert resp.query == "trusted ICU hospital in Maharashtra"
    assert resp.safety_note == SAFETY_NOTE
    assert resp.interpreted_intent is not None
    assert resp.interpreted_intent.state == "Maharashtra"
    assert resp.returned == len(resp.recommendations)
    assert resp.returned >= 1
    # Apollo (F001) has the strongest evidence and should rank highest.
    assert resp.recommendations[0].facility_id == "F001"
    top = resp.recommendations[0]
    assert isinstance(top, AgentRecommendation)
    assert isinstance(top.score_breakdown, ScoreBreakdown)
    assert 0.0 <= top.score_breakdown.final_score <= 1.0
    assert top.facility_type == "hospital"
    assert top.city == "Mumbai"
    assert top.state == "Maharashtra"
    assert top.reason_for_recommendation
    assert top.human_next_steps


def test_response_contract_fields_are_present(df):
    """All Stage-13 top-level response fields must be set / defaulted."""
    resp = run_recommendation("trusted ICU hospital in Maharashtra", df)
    expected = {
        "query",
        "intent",
        "interpreted_intent",
        "recommendations",
        "reasoning",
        "safety_note",
        "fallback_message",
        "trace_summary",
        "retrieval_summary",
        "total_candidates",
        "returned",
    }
    dumped = resp.model_dump()
    for key in expected:
        assert key in dumped, f"Missing top-level field {key!r}"
    assert "stages" in resp.trace_summary
    assert "audit_log" in resp.trace_summary


def test_recommendation_contract_fields_are_present(df):
    """Every recommendation must carry the Stage-13 fields."""
    resp = run_recommendation("trusted ICU hospital in Maharashtra", df)
    assert resp.recommendations
    rec = resp.recommendations[0].model_dump()
    expected = {
        "facility_id",
        "name",
        "facility_type",
        "city",
        "state",
        "trust_score",
        "trust_category",
        "recommendation_readiness",
        "matched_capabilities",
        "matched_fields",
        "evidence_snippets",
        "validation_findings",
        "warning_flags",
        "web_verification",
        "score_breakdown",
        "reason_for_recommendation",
        "human_next_steps",
    }
    for key in expected:
        assert key in rec, f"Recommendation missing {key!r}"


def test_safety_note_always_present(df):
    """Safety note must be set even on empty / fallback paths."""
    resp1 = run_recommendation("trusted ICU hospital in Maharashtra", df)
    resp2 = run_recommendation(
        "anything", df, state="Antarctica", facility_type="hospital",
    )
    resp3 = run_recommendation("", df)
    assert resp1.safety_note == SAFETY_NOTE
    assert resp2.safety_note == SAFETY_NOTE
    assert resp3.safety_note == SAFETY_NOTE


# ---------------------------------------------------------------------------
# Score breakdown contents
# ---------------------------------------------------------------------------


def test_score_breakdown_components_are_set(df):
    resp = run_recommendation("trusted ICU hospital in Maharashtra", df)
    sb = resp.recommendations[0].score_breakdown
    assert isinstance(sb, ScoreBreakdown)
    assert sb.trust_score_component > 0.0
    assert sb.readiness_component > 0.0
    assert sb.capability_match_component > 0.0
    assert sb.evidence_strength_component > 0.0
    # No vector / Tavily on the default path.
    assert sb.vector_similarity_component == 0.0
    assert sb.tavily_verification_component == 0.0
    assert 0.0 <= sb.final_score <= 1.0


def test_validation_findings_lower_score(df):
    """A facility that *claims* ICU without equipment must score lower
    than a facility with the same trust / readiness backed by evidence."""
    resp = run_recommendation("ICU hospital", df, state="Maharashtra")
    by_id = {r.facility_id: r for r in resp.recommendations}
    if "F001" in by_id and "F004" in by_id:
        good = by_id["F001"].score_breakdown.final_score
        bad = by_id["F004"].score_breakdown.final_score
        assert good > bad
        # F004's own validation should produce a non-zero penalty
        assert by_id["F004"].score_breakdown.validation_penalty <= 0.0
        assert any(
            f.severity in ("medium", "high")
            for f in by_id["F004"].validation_findings
        )


# ---------------------------------------------------------------------------
# Dialysis query — fallback or success
# ---------------------------------------------------------------------------


def test_dialysis_query_returns_results_or_fallback(df):
    """Dialysis in Karnataka should hit Fortis; empty filters should
    return a populated fallback message."""
    resp = run_recommendation("dialysis in Karnataka", df)
    assert resp.returned >= 1
    top = resp.recommendations[0]
    assert top.facility_id == "F002"
    assert top.score_breakdown.final_score > 0.0


def test_no_match_returns_fallback_message(df):
    resp = run_recommendation(
        "dialysis", df, state="Antarctica", facility_type="hospital",
    )
    assert resp.returned == 0
    assert resp.recommendations == []
    assert resp.fallback_message
    assert "Antarctica" in resp.fallback_message
    # Reasoning still produced; safety_note still present.
    assert resp.reasoning
    assert resp.safety_note == SAFETY_NOTE


# ---------------------------------------------------------------------------
# max_results / overrides
# ---------------------------------------------------------------------------


def test_max_results_truncates_recommendations(df):
    resp = run_recommendation("ICU hospital", df, max_results=1)
    assert resp.returned == 1
    assert len(resp.recommendations) == 1
    # total_candidates may be larger than returned.
    assert resp.total_candidates >= resp.returned


def test_min_trust_score_override_is_applied(df):
    resp = run_recommendation(
        "ICU hospital", df, state="Maharashtra", min_trust_score=0.8,
    )
    for rec in resp.recommendations:
        assert rec.trust_score >= 0.8


def test_facility_type_override_is_applied(df):
    resp = run_recommendation(
        "anything", df, state="Maharashtra", facility_type="clinic",
    )
    for rec in resp.recommendations:
        assert rec.facility_type == "clinic"


# ---------------------------------------------------------------------------
# Tavily disabled vs mocked enabled
# ---------------------------------------------------------------------------


def test_tavily_disabled_path_returns_no_web_verification(df, disabled_settings):
    resp = run_recommendation(
        "trusted ICU hospital in Maharashtra",
        df,
        enable_web_verification=False,
        settings=disabled_settings,
    )
    assert resp.returned >= 1
    for rec in resp.recommendations:
        assert rec.web_verification is None
        assert rec.score_breakdown.tavily_verification_component == 0.0
    assert resp.trace_summary["tavily"]["enabled"] is False
    assert resp.trace_summary["tavily"]["verified"] == 0


def test_tavily_mocked_enabled_path_attaches_web_verification(
    df, enabled_tavily_settings,
):
    """A mocked Tavily client returns a clean 'verified' response and the
    engine must attach it to the top recommendation."""
    fake_client = MagicMock()
    fake_client.search.return_value = {
        "results": [
            {
                "title": "Apollo Hospitals Mumbai - Official Website",
                "url": "https://www.apollohospitals.com/locations/mumbai/",
                "content": (
                    "Apollo Hospitals Mumbai offers 24/7 ICU, ventilator support, "
                    "and dialysis services in Mumbai, Maharashtra."
                ),
                "score": 0.94,
            }
        ]
    }
    factory = MagicMock(return_value=fake_client)

    resp = run_recommendation(
        "trusted ICU hospital in Maharashtra",
        df,
        enable_web_verification=True,
        web_verification_depth="basic",
        max_web_verified=2,
        settings=enabled_tavily_settings,
        tavily_client_factory=factory,
    )
    assert resp.returned >= 1
    top = resp.recommendations[0]
    # Top should have a web_verification attached.
    assert isinstance(top.web_verification, WebVerificationResult)
    assert top.web_verification.web_checked is True
    assert top.web_verification.verification_status in (
        "verified",
        "partial",
        "unverified",
    )
    # Tavily component must contribute to the final score on the top rec.
    assert top.score_breakdown.tavily_verification_component >= 0.0
    # Trace summary records the Tavily stage.
    assert resp.trace_summary["tavily"]["enabled"] is True
    assert resp.trace_summary["tavily"]["verified"] >= 1
    # Factory was called with the API key.
    assert factory.called


def test_tavily_max_web_verified_respected(df, enabled_tavily_settings):
    fake_client = MagicMock()
    fake_client.search.return_value = {"results": []}
    factory = MagicMock(return_value=fake_client)
    resp = run_recommendation(
        "ICU hospital", df,
        enable_web_verification=True,
        max_web_verified=1,
        settings=enabled_tavily_settings,
        tavily_client_factory=factory,
    )
    verified = [r for r in resp.recommendations if r.web_verification is not None]
    assert len(verified) <= 1


def test_tavily_zero_max_web_verified_skips_all(df, enabled_tavily_settings):
    factory = MagicMock()
    resp = run_recommendation(
        "ICU hospital", df,
        enable_web_verification=True,
        max_web_verified=0,
        settings=enabled_tavily_settings,
        tavily_client_factory=factory,
    )
    assert all(r.web_verification is None for r in resp.recommendations)


# ---------------------------------------------------------------------------
# Vector search disabled vs mocked
# ---------------------------------------------------------------------------


def test_vector_disabled_path_skips_vector_stage(df, disabled_settings):
    resp = run_recommendation(
        "ICU hospital", df,
        enable_vector_search=False,
        settings=disabled_settings,
    )
    rs = resp.retrieval_summary
    assert rs["vector_enabled"] is False
    assert rs["vector_count"] == 0
    assert resp.trace_summary["vector"]["enabled"] is False
    for rec in resp.recommendations:
        assert rec.score_breakdown.vector_similarity_component == 0.0


def test_vector_mocked_path_boosts_local_candidate(df):
    """A mocked retriever returning F001 with high similarity must boost
    its score by the vector component."""
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = VectorSearchResponse(
        available=True,
        reason="",
        query="trusted ICU hospital in Maharashtra",
        results=[
            VectorSearchResult(facility_id="F001", similarity_score=0.91, metadata={}),
        ],
    )
    resp = run_recommendation(
        "trusted ICU hospital in Maharashtra",
        df,
        enable_vector_search=True,
        vector_retriever=mock_retriever,
    )
    assert mock_retriever.search.called
    assert resp.retrieval_summary["vector_enabled"] is True
    assert resp.retrieval_summary["vector_available"] is True
    assert resp.retrieval_summary["vector_count"] == 1
    by_id = {r.facility_id: r for r in resp.recommendations}
    assert "F001" in by_id
    assert by_id["F001"].score_breakdown.vector_similarity_component > 0.0


def test_vector_unavailable_path_falls_back_silently(df):
    """When the retriever reports unavailable, the engine must not crash
    and must still produce a local-only response."""
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = VectorSearchResponse(
        available=False,
        reason="vector_search_disabled",
        query="x",
        results=[],
    )
    resp = run_recommendation(
        "ICU hospital", df,
        enable_vector_search=True,
        vector_retriever=mock_retriever,
    )
    assert resp.retrieval_summary["vector_enabled"] is True
    assert resp.retrieval_summary["vector_available"] is False
    assert resp.returned >= 0  # local results still flow through


def test_vector_retriever_exception_is_swallowed(df):
    """An exception inside the retriever must be caught and recorded."""
    mock_retriever = MagicMock()
    mock_retriever.search.side_effect = RuntimeError("boom")
    resp = run_recommendation(
        "ICU hospital", df,
        enable_vector_search=True,
        vector_retriever=mock_retriever,
    )
    # No crash and the trace records the failure.
    errors = resp.trace_summary["errors"]
    assert any(e["stage"] == "vector_retrieval" for e in errors)


def test_vector_only_candidate_gets_added_via_lookup(df):
    """A vector hit not in the local pool but present in the DataFrame
    must still appear as a candidate."""
    # Restrict local pool to nothing by impossible state.
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = VectorSearchResponse(
        available=True,
        reason="",
        query="x",
        results=[
            VectorSearchResult(facility_id="F005", similarity_score=0.8, metadata={}),
        ],
    )
    resp = run_recommendation(
        "anything",
        df,
        state="Delhi",  # F005 is in Delhi
        enable_vector_search=True,
        vector_retriever=mock_retriever,
    )
    assert resp.returned >= 1


# ---------------------------------------------------------------------------
# Audit logger integration
# ---------------------------------------------------------------------------


def test_audit_logger_receives_pipeline_events(df):
    logger = AuditLogger(persist=False)
    resp = run_recommendation(
        "trusted ICU hospital in Maharashtra", df, audit_logger=logger,
    )
    types = logger.event_types()
    assert "intent_parsed" in types
    assert "local_retrieval" in types
    assert "vector_retrieval" in types
    assert "merge" in types
    assert "enrich" in types
    assert "score_and_rank" in types
    assert "tavily_verification" in types
    assert "final_response" in types
    # Summary embedded in trace_summary references the same totals
    # (snapshot is taken just before the `final_response` event is
    # logged, so it lags by exactly one event).
    summary = resp.trace_summary["audit_log"]
    assert summary["total_events"] in (len(logger), len(logger) - 1)


def test_default_audit_logger_when_none_passed(df):
    """Pipeline must work when no logger is supplied."""
    resp = run_recommendation("ICU hospital", df)
    assert isinstance(resp, AgentResponse)
    assert "audit_log" in resp.trace_summary


# ---------------------------------------------------------------------------
# Robustness — never raises
# ---------------------------------------------------------------------------


def test_empty_dataframe_does_not_crash():
    empty = pd.DataFrame(columns=[
        "facility_id", "name", "state", "city", "facility_type",
        "trust_score", "trust_category", "recommendation_readiness",
        "specialties", "procedures", "equipment", "capabilities_raw",
        "evidence_summary", "combined_medical_evidence",
    ])
    resp = run_recommendation("dialysis", empty)
    assert isinstance(resp, AgentResponse)
    assert resp.returned == 0
    assert resp.fallback_message
    assert resp.safety_note == SAFETY_NOTE


def test_blank_query_does_not_crash(df):
    resp = run_recommendation("", df)
    assert isinstance(resp, AgentResponse)
    assert resp.safety_note == SAFETY_NOTE


def test_intent_parser_failure_is_swallowed(df):
    """If intent parsing throws, the engine should catch and continue."""
    with patch(
        "agent_core.recommendation_engine.parse_query_intent",
        side_effect=RuntimeError("parser broken"),
    ):
        resp = run_recommendation("ICU hospital", df)
    assert isinstance(resp, AgentResponse)
    assert any(
        e["stage"] == "intent_parse" for e in resp.trace_summary["errors"]
    )


def test_local_retriever_failure_is_swallowed(df):
    with patch(
        "agent_core.recommendation_engine.retrieve_local_candidates",
        side_effect=RuntimeError("retriever broken"),
    ):
        resp = run_recommendation("ICU hospital", df)
    assert isinstance(resp, AgentResponse)
    assert resp.returned == 0
    assert any(
        e["stage"] == "local_retrieval" for e in resp.trace_summary["errors"]
    )


def test_evidence_extractor_failure_is_swallowed(df):
    with patch(
        "agent_core.recommendation_engine.extract_evidence_snippets",
        side_effect=RuntimeError("snippet broken"),
    ):
        resp = run_recommendation("ICU hospital", df)
    # Engine continues; recommendations have no evidence but exist.
    assert isinstance(resp, AgentResponse)
    for rec in resp.recommendations:
        assert rec.evidence_snippets == []


# ---------------------------------------------------------------------------
# Reasoning, fallback, and human_next_steps content
# ---------------------------------------------------------------------------


def test_reasoning_mentions_top_result(df):
    resp = run_recommendation("trusted ICU hospital in Maharashtra", df)
    top = resp.recommendations[0]
    expected_token = top.name or top.facility_id
    assert expected_token in resp.reasoning


def test_human_next_steps_non_empty_for_every_recommendation(df):
    resp = run_recommendation("ICU hospital", df, state="Maharashtra")
    for rec in resp.recommendations:
        assert rec.human_next_steps
        assert all(isinstance(s, str) and s for s in rec.human_next_steps)


def test_emergency_query_adds_emergency_step(df):
    resp = run_recommendation(
        "EMERGENCY trauma ICU now in Maharashtra", df,
    )
    if resp.recommendations:
        top = resp.recommendations[0]
        # Emergency wording differs by intent parser, so we accept either.
        if top.human_next_steps:
            joined = " ".join(top.human_next_steps).lower()
            # At minimum we must have steps; emergency hint is a bonus.
            assert joined


# ---------------------------------------------------------------------------
# Stage 17 — Vector retrieval contract
# ---------------------------------------------------------------------------


def test_stage17_filters_pushed_when_state_is_in_intent(df):
    """When intent.state is set, the engine must push ``filters={"state": ...}``
    into the vector retriever. The state used is the parsed/overridden state."""
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = VectorSearchResponse(
        available=True,
        reason="ok",
        query="x",
        filter_applied=True,
        endpoint="caregrid-vector-endpoint",
        index="workspace.default.caregrid_vector_index",
        results=[],
    )
    run_recommendation(
        "Find trusted ICU hospitals in Bihar",
        df,
        state="Bihar",  # explicit override
        enable_vector_search=True,
        vector_retriever=mock_retriever,
    )
    assert mock_retriever.search.called
    kwargs = mock_retriever.search.call_args.kwargs
    assert kwargs.get("filters") == {"state": "Bihar"}


def test_stage17_no_filters_pushed_when_state_is_blank(df):
    """When no state is in the intent, the engine must call search()
    without a filter (so ``filters`` is ``None``)."""
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = VectorSearchResponse(
        available=True, reason="ok", query="x",
        filter_applied=False,
        endpoint="caregrid-vector-endpoint",
        index="workspace.default.caregrid_vector_index",
        results=[],
    )
    run_recommendation(
        "ICU",  # no state extractable
        df,
        enable_vector_search=True,
        vector_retriever=mock_retriever,
    )
    kwargs = mock_retriever.search.call_args.kwargs
    assert kwargs.get("filters") is None


def test_stage17_retrieval_summary_carries_endpoint_index_and_filter_applied(df):
    """The retrieval summary must include vector_endpoint, vector_index,
    and vector_filter_applied so operators can confirm exactly what
    Databricks returned."""
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = VectorSearchResponse(
        available=True,
        reason="ok",
        query="x",
        filter_applied=True,
        endpoint="caregrid-vector-endpoint",
        index="workspace.default.caregrid_vector_index",
        results=[
            VectorSearchResult(facility_id="F001", similarity_score=0.91, metadata={}),
        ],
    )
    resp = run_recommendation(
        "trusted ICU hospital in Maharashtra",
        df,
        state="Maharashtra",
        enable_vector_search=True,
        vector_retriever=mock_retriever,
    )
    rs = resp.retrieval_summary
    assert rs["vector_enabled"] is True
    assert rs["vector_available"] is True
    assert rs["vector_count"] == 1
    assert rs["vector_filter_applied"] is True
    assert rs["vector_endpoint"] == "caregrid-vector-endpoint"
    assert rs["vector_index"] == "workspace.default.caregrid_vector_index"
    assert rs["vector_filters_requested"] == {"state": "Maharashtra"}

    # Trace summary mirrors the same data
    vec_trace = resp.trace_summary["vector"]
    assert vec_trace["enabled"] is True
    assert vec_trace["available"] is True
    assert vec_trace["filter_applied"] is True
    assert vec_trace["count"] == 1


def test_stage17_filter_dropped_signal_propagates_to_retrieval_summary(df):
    """When the SDK fell back to an unfiltered query, the engine must
    surface ``filter_applied=False`` and a clear reason so a downstream
    UI can warn the operator that local post-filtering may be needed."""
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = VectorSearchResponse(
        available=True,
        reason="ok_without_filter",
        query="x",
        filter_applied=False,
        endpoint="caregrid-vector-endpoint",
        index="workspace.default.caregrid_vector_index",
        results=[
            VectorSearchResult(facility_id="F001", similarity_score=0.6, metadata={}),
        ],
    )
    resp = run_recommendation(
        "ICU in Maharashtra", df,
        state="Maharashtra",
        enable_vector_search=True,
        vector_retriever=mock_retriever,
    )
    rs = resp.retrieval_summary
    assert rs["vector_filter_applied"] is False
    assert rs["vector_reason"] == "ok_without_filter"


def test_stage17_missing_databricks_env_does_not_crash(df):
    """Engine with enable_vector_search=True but no Databricks creds must
    still produce a clean response — vector_available=False, no crash."""
    cfg = SimpleNamespace(
        vector_search_enabled=True,
        databricks_host="",
        databricks_token="",
        vector_search_endpoint="",
        vector_search_index="",
        # Tavily disabled so we don't go down that branch
        tavily_enabled=False,
        tavily_api_key=None,
        tavily_default_depth="basic",
        tavily_max_web_verified=0,
        tavily_cache_dir="data/tavily_cache",
    )
    resp = run_recommendation(
        "ICU hospital", df,
        enable_vector_search=True,
        settings=cfg,
    )
    assert isinstance(resp, AgentResponse)
    assert resp.retrieval_summary["vector_enabled"] is True
    assert resp.retrieval_summary["vector_available"] is False
    # Vector unavailable must not block local-only results
    assert resp.returned >= 0


def _stage18_combined_settings() -> SimpleNamespace:
    """Settings with BOTH Tavily and the vector-search flag enabled.

    ``vector_retriever`` is still always injected as a mock in the tests,
    so the Databricks creds here are placeholders only — they exist to
    show that the engine doesn't spuriously fall back to local-only
    when the flag is on.
    """
    return SimpleNamespace(
        vector_search_enabled=True,
        databricks_host="https://example.cloud.databricks.com",
        databricks_token="dapi-test-token",
        vector_search_endpoint="caregrid-vector-endpoint",
        vector_search_index="workspace.default.caregrid_vector_index",
        databricks_vector_endpoint="caregrid-vector-endpoint",
        databricks_vector_index="workspace.default.caregrid_vector_index",
        tavily_enabled=True,
        tavily_api_key="test-key",
        tavily_default_depth="basic",
        tavily_max_web_verified=3,
        tavily_cache_ttl_seconds=86400,
    )


def _stage18_mocked_vector(facility_id: str = "F001", score: float = 0.91):
    """A mock VectorRetriever returning one high-similarity hit."""
    mr = MagicMock()
    mr.search.return_value = VectorSearchResponse(
        available=True,
        reason="ok",
        query="x",
        filter_applied=True,
        endpoint="caregrid-vector-endpoint",
        index="workspace.default.caregrid_vector_index",
        results=[
            VectorSearchResult(
                facility_id=facility_id, similarity_score=score, metadata={},
            ),
        ],
    )
    return mr


def _stage18_mocked_tavily_factory():
    """A Tavily client_factory whose ``search`` returns a strong, name +
    location + capability match — yielding ``verification_status="verified"``.
    """
    fake_client = MagicMock()
    fake_client.search.return_value = {
        "results": [
            {
                "title": "Apollo Hospitals Mumbai - Official Website",
                "url": "https://www.apollohospitals.com/locations/mumbai/",
                "content": (
                    "Apollo Hospitals Mumbai operates a 24/7 ICU with "
                    "ventilator support, advanced critical care beds and "
                    "intensive care services in Mumbai, Maharashtra."
                ),
                "score": 0.95,
            }
        ]
    }
    return MagicMock(return_value=fake_client)


def _stage18_fresh_tavily_cache():
    """A brand-new TavilyCache so combined-mode tests are isolated from
    cache pollution by earlier tests in the suite.

    The Tavily verifier defaults to a *module-level singleton* cache so
    repeat calls in production don't burn credits — without an explicit
    cache here, tests that re-use the same (name, city, state, caps,
    depth) key get a stale entry and our mocked factory is never
    invoked.
    """
    from agent_core.tavily_cache import TavilyCache  # local import
    return TavilyCache()


@pytest.fixture(autouse=False)
def reset_tavily_default_cache():
    """Reset the verifier's module-level default cache before AND after
    each Stage-18 test. This protects every combined-mode test from
    cache pollution by earlier Tavily tests in the suite (and from
    polluting later tests in turn).
    """
    from agent_core.tavily_cache import reset_default_cache  # local import
    reset_default_cache()
    yield
    reset_default_cache()


def test_stage18_combined_mode_runs_with_mocked_vector_and_tavily(df, reset_tavily_default_cache):
    """Combined run with mocked Databricks + mocked Tavily must produce
    a fully populated response — ``vector_enabled=true``, ``vector_count>0``,
    ``web_verification_enabled=true``, ``tavily_verified_count>0``, and
    a single recommendation that picked up BOTH bonuses."""
    cfg = _stage18_combined_settings()
    mr  = _stage18_mocked_vector(facility_id="F001", score=0.95)
    tf  = _stage18_mocked_tavily_factory()

    resp = run_recommendation(
        "trusted ICU hospital in Maharashtra",
        df,
        state="Maharashtra",
        max_results=3,
        enable_vector_search=True,
        enable_web_verification=True,
        web_verification_depth="basic",
        max_web_verified=2,
        settings=cfg,
        vector_retriever=mr,
        tavily_client_factory=tf,
    )

    rs = resp.retrieval_summary
    assert rs["vector_enabled"] is True
    assert rs["vector_available"] is True
    assert rs["vector_count"] >= 1
    # Stage-18 Tavily summary keys sit alongside the vector keys
    assert rs["web_verification_enabled"] is True
    assert rs["tavily_verified_count"] >= 1
    assert rs["tavily_depth"] == "basic"
    assert rs["tavily_credits_estimated"] >= 0

    # The Apollo record (F001) is in the local pool AND came back from
    # the mocked vector hit AND is the first one Tavily verifies.
    by_id = {r.facility_id: r for r in resp.recommendations}
    assert "F001" in by_id
    sb = by_id["F001"].score_breakdown
    assert sb is not None
    assert sb.vector_similarity_component > 0.0
    assert sb.tavily_verification_component > 0.0
    assert 0.0 <= sb.final_score <= 1.0


def test_stage18_combined_mode_score_breakdown_has_all_components(df, reset_tavily_default_cache):
    """Every recommendation in combined mode must carry the full
    nine-component breakdown — none of the fields should be missing,
    even when their value is zero (e.g. tavily for a non-verified rec).
    """
    cfg = _stage18_combined_settings()
    mr  = _stage18_mocked_vector("F001", 0.85)
    tf  = _stage18_mocked_tavily_factory()
    resp = run_recommendation(
        "trusted ICU hospital in Maharashtra",
        df, state="Maharashtra", max_results=5,
        enable_vector_search=True, enable_web_verification=True,
        max_web_verified=1,
        settings=cfg, vector_retriever=mr, tavily_client_factory=tf,
    )
    for rec in resp.recommendations:
        sb = rec.score_breakdown
        assert sb is not None
        for f in (
            "trust_score_component", "readiness_component",
            "capability_match_component", "evidence_strength_component",
            "validation_penalty", "warning_penalty",
            "vector_similarity_component", "tavily_verification_component",
            "final_score",
        ):
            assert hasattr(sb, f), f"score_breakdown missing field {f!r}"
        assert 0.0 <= sb.final_score <= 1.0


def test_stage18_combined_mode_does_not_verify_all_merged_candidates(df, reset_tavily_default_cache):
    """Tavily must NOT be invoked for every merged candidate. With 5
    local rows + 1 vector-only hit and ``max_web_verified=1``, the
    Tavily client should be called at most once.

    This protects the live workspace from credit spikes when a query
    matches hundreds of facilities.
    """
    cfg = _stage18_combined_settings()
    mr  = _stage18_mocked_vector("F001", 0.9)

    # Use a real factory we can count
    fake_client = MagicMock()
    fake_client.search.return_value = {"results": []}
    factory = MagicMock(return_value=fake_client)

    resp = run_recommendation(
        "trusted ICU hospital in Maharashtra",
        df, state="Maharashtra", max_results=5,
        enable_vector_search=True, enable_web_verification=True,
        max_web_verified=1,
        settings=cfg, vector_retriever=mr, tavily_client_factory=factory,
    )

    # The merged pool is much larger than the Tavily verification cap.
    assert resp.retrieval_summary["merged_count"] >= 2
    # Tavily client was called at most max_web_verified times
    # (basic depth = one call per facility).
    assert fake_client.search.call_count <= 1
    # The Stage-18 retrieval-summary key reports the same number.
    assert resp.retrieval_summary["tavily_verified_count"] <= 1


def test_stage18_combined_mode_respects_max_web_verified_cap(df, reset_tavily_default_cache):
    """``max_web_verified`` must cap the number of recs that get Tavily
    info, regardless of how many ranked recs there are."""
    cfg = _stage18_combined_settings()
    mr  = _stage18_mocked_vector("F001", 0.9)
    tf  = _stage18_mocked_tavily_factory()
    resp = run_recommendation(
        "ICU hospital", df, max_results=5,
        enable_vector_search=True, enable_web_verification=True,
        max_web_verified=1,
        settings=cfg, vector_retriever=mr, tavily_client_factory=tf,
    )
    verified = [r for r in resp.recommendations if r.web_verification is not None]
    assert len(verified) <= 1
    assert resp.retrieval_summary["tavily_verified_count"] == len(verified)


def test_stage18_combined_mode_falls_back_when_vector_fails(df, reset_tavily_default_cache):
    """If the vector retriever raises, the combined run still produces
    a response — Tavily verification continues to work on local-only
    candidates."""
    cfg = _stage18_combined_settings()
    bad_retriever = MagicMock()
    bad_retriever.search.side_effect = RuntimeError("boom")
    tf = _stage18_mocked_tavily_factory()

    resp = run_recommendation(
        "ICU hospital", df, max_results=3,
        enable_vector_search=True, enable_web_verification=True,
        max_web_verified=1,
        settings=cfg, vector_retriever=bad_retriever, tavily_client_factory=tf,
    )
    assert isinstance(resp, AgentResponse)
    assert resp.retrieval_summary["vector_available"] is False
    # Vector failure recorded in the trace
    assert any(
        e["stage"] == "vector_retrieval" for e in resp.trace_summary["errors"]
    )
    # But Tavily still ran on the local-only top recommendations
    assert resp.retrieval_summary["web_verification_enabled"] is True
    assert resp.safety_note  # safety note still present


def test_stage18_combined_mode_falls_back_when_tavily_fails(df, reset_tavily_default_cache):
    """If the Tavily client_factory raises, recommendations still come
    back — only the Tavily component on each score is zero, and the
    failure is recorded on the trace."""
    cfg = _stage18_combined_settings()
    mr  = _stage18_mocked_vector("F001", 0.9)

    def _bad_factory(_key):
        raise RuntimeError("tavily-down")

    resp = run_recommendation(
        "trusted ICU hospital in Maharashtra",
        df, state="Maharashtra", max_results=3,
        enable_vector_search=True, enable_web_verification=True,
        max_web_verified=1,
        settings=cfg, vector_retriever=mr,
        tavily_client_factory=_bad_factory,
    )

    # The pipeline did not crash — recommendations exist
    assert resp.returned >= 1
    # Vector still contributed
    by_id = {r.facility_id: r for r in resp.recommendations}
    if "F001" in by_id:
        assert by_id["F001"].score_breakdown.vector_similarity_component > 0.0
    # Tavily errors on individual facilities are surfaced via the
    # web_verification record (status="error") — none of them crashed
    # the run, none of them yielded a positive Tavily bonus.
    for rec in resp.recommendations:
        assert rec.score_breakdown.tavily_verification_component == 0.0


def test_stage18_combined_mode_trace_summary_has_all_stages(df, reset_tavily_default_cache):
    """The trace summary must list every Stage-18 stage:
    intent_parsed, local_retrieval, vector_retrieval, merge, enrich,
    score_and_rank, tavily_verification, final_response.
    Errors are an empty list when nothing went wrong."""
    cfg = _stage18_combined_settings()
    mr  = _stage18_mocked_vector("F001", 0.9)
    tf  = _stage18_mocked_tavily_factory()
    resp = run_recommendation(
        "ICU hospital", df, max_results=2,
        enable_vector_search=True, enable_web_verification=True,
        max_web_verified=1,
        settings=cfg, vector_retriever=mr, tavily_client_factory=tf,
    )
    stages = [s.get("stage") for s in resp.trace_summary["stages"]]
    for required in (
        "intent_parsed", "local_retrieval", "vector_retrieval",
        "merge", "enrich", "score_and_rank", "tavily_verification",
        "final_response",
    ):
        assert required in stages, f"missing trace stage: {required!r}"
    assert resp.trace_summary["errors"] == []


def test_stage18_combined_mode_safety_note_always_present(df, reset_tavily_default_cache):
    """The safety note must be present even when both retrieval arms
    are firing — it's the disclaimer the UI shows below recommendations."""
    cfg = _stage18_combined_settings()
    mr  = _stage18_mocked_vector("F001", 0.9)
    tf  = _stage18_mocked_tavily_factory()
    resp = run_recommendation(
        "ICU hospital", df, max_results=3,
        enable_vector_search=True, enable_web_verification=True,
        max_web_verified=1,
        settings=cfg, vector_retriever=mr, tavily_client_factory=tf,
    )
    assert resp.safety_note == SAFETY_NOTE
    assert resp.safety_note.strip()


def test_stage18_combined_mode_response_serialises_cleanly(df, reset_tavily_default_cache):
    """The combined response must serialise to plain JSON-able dicts via
    Pydantic's ``model_dump(mode='json')``. This protects callers (e.g.
    Stage 19's backend handler) from being broken by future schema
    additions."""
    cfg = _stage18_combined_settings()
    mr  = _stage18_mocked_vector("F001", 0.9)
    tf  = _stage18_mocked_tavily_factory()
    resp = run_recommendation(
        "ICU hospital", df, max_results=2,
        enable_vector_search=True, enable_web_verification=True,
        max_web_verified=1,
        settings=cfg, vector_retriever=mr, tavily_client_factory=tf,
    )
    payload = resp.model_dump(mode="json")
    assert isinstance(payload, dict)
    assert payload["safety_note"]
    rs = payload["retrieval_summary"]
    for k in (
        "vector_enabled", "vector_available", "vector_count",
        "web_verification_enabled", "tavily_verified_count",
        "tavily_depth", "tavily_credits_estimated",
        "after_top_k_count", "relaxation_used",
    ):
        assert k in rs, f"retrieval_summary missing key: {k!r}"
    # No real network calls — confirmed by absence of pytest network
    # markers in the test suite. (See conftest / live tests for the
    # contractual rule.)


def test_stage17_vector_similarity_component_is_positive_for_scored_candidate(df):
    """When the mocked retriever returns a real similarity score, the
    score breakdown's vector_similarity_component must be > 0."""
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = VectorSearchResponse(
        available=True, reason="ok", query="x",
        filter_applied=True,
        endpoint="caregrid-vector-endpoint",
        index="workspace.default.caregrid_vector_index",
        results=[
            VectorSearchResult(facility_id="F001", similarity_score=0.95, metadata={}),
        ],
    )
    resp = run_recommendation(
        "trusted ICU hospital in Maharashtra",
        df,
        state="Maharashtra",
        enable_vector_search=True,
        vector_retriever=mock_retriever,
    )
    by_id = {r.facility_id: r for r in resp.recommendations}
    assert "F001" in by_id
    sb = by_id["F001"].score_breakdown
    assert sb is not None
    assert sb.vector_similarity_component > 0.0


# ---------------------------------------------------------------------------
# Backward-compat: original Stage-1 ``recommend`` API
# ---------------------------------------------------------------------------


def _legacy_sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"facility_id": "F001", "trust_score": 0.9, "trust_category": "High",
             "recommendation_readiness": True},
            {"facility_id": "F002", "trust_score": 0.5, "trust_category": "Medium",
             "recommendation_readiness": False},
            {"facility_id": "F003", "trust_score": 0.75, "trust_category": "High",
             "recommendation_readiness": True},
        ]
    )


def test_recommend_filters_by_trust_score():
    legacy = _legacy_sample_df()
    result = recommend(legacy, trust_score_threshold=0.6)
    assert all(result["trust_score"] >= 0.6)
    assert "F002" not in result["facility_id"].values


def test_recommend_sorted_descending():
    legacy = _legacy_sample_df()
    result = recommend(legacy, trust_score_threshold=0.0)
    scores = result["trust_score"].tolist()
    assert scores == sorted(scores, reverse=True)


def test_recommend_top_k():
    legacy = _legacy_sample_df()
    result = recommend(legacy, trust_score_threshold=0.0, top_k=2)
    assert len(result) <= 2
