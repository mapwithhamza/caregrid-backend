"""Tests for run_agent_demo.py.

These tests **must not** make real Tavily or Databricks calls. They use
a tiny in-memory DataFrame and rely on the engine's default behaviour
(`enable_web_verification=False`, `enable_vector_search=False`) to
guarantee no external services are reached.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import run_agent_demo  # noqa: E402  (sys.path manipulation must come first)


# ---------------------------------------------------------------------------
# Tiny in-memory dataset that satisfies validate_real_dataset()
# ---------------------------------------------------------------------------

def _tiny_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "facility_id": "F001",
                "name": "Apollo Test Hospital",
                "facility_type": "hospital",
                "city": "Patna",
                "state": "Bihar",
                "latitude": 25.5941,
                "longitude": 85.1376,
                "trust_score": 0.92,
                "trust_category": "High Trust / Evidence Supported",
                "recommendation_readiness": "Ready for recommendation",
                "combined_medical_evidence": (
                    "ICU with ventilator, intensive care unit, critical care beds, "
                    "anaesthesia workstation, dialysis machine, and emergency department."
                ),
                "evidence_summary": "Multispecialty tertiary care.",
                "specialties": "cardiology, nephrology, critical care",
                "procedures": "hemodialysis, cardiac catheterisation, mechanical ventilation",
                "equipment": "ventilator, dialysis machine, ICU beds, defibrillator",
                "capabilities_raw": "ICU, dialysis unit, 24/7 emergency",
            },
            {
                "facility_id": "F002",
                "name": "City Maternity Centre",
                "facility_type": "hospital",
                "city": "Chennai",
                "state": "Tamil Nadu",
                "latitude": 13.0827,
                "longitude": 80.2707,
                "trust_score": 0.78,
                "trust_category": "Moderate Trust / Verify Before Use",
                "recommendation_readiness": "Usable with verification",
                "combined_medical_evidence": (
                    "Labour ward, delivery room, neonatal care, obstetric care, "
                    "C-section operating theatre."
                ),
                "evidence_summary": "Maternity and neonatal services.",
                "specialties": "obstetrics, gynaecology, paediatrics",
                "procedures": "vaginal delivery, caesarean, antenatal care",
                "equipment": "delivery bed, foetal heart monitor, neonatal incubator",
                "capabilities_raw": "labour room, NICU bassinets",
            },
        ]
    )


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------

def test_imports_cleanly():
    """Importing run_agent_demo must not perform any I/O or network calls."""
    assert hasattr(run_agent_demo, "main")
    assert hasattr(run_agent_demo, "load_real_dataset")
    assert hasattr(run_agent_demo, "validate_real_dataset")
    assert hasattr(run_agent_demo, "get_default_demo_queries")
    assert hasattr(run_agent_demo, "run_demo_queries")
    assert hasattr(run_agent_demo, "save_json_output")
    assert hasattr(run_agent_demo, "save_markdown_report")


def test_required_columns_constant_complete():
    required = run_agent_demo.REQUIRED_COLUMNS
    for col in (
        "facility_id", "name", "facility_type", "city", "state",
        "latitude", "longitude", "trust_score", "trust_category",
        "recommendation_readiness", "combined_medical_evidence",
        "evidence_summary",
    ):
        assert col in required, f"REQUIRED_COLUMNS missing {col!r}"


# ---------------------------------------------------------------------------
# get_default_demo_queries
# ---------------------------------------------------------------------------

def test_get_default_demo_queries_returns_five():
    queries = run_agent_demo.get_default_demo_queries()
    assert isinstance(queries, list)
    assert len(queries) == 5


def test_get_default_demo_queries_exact_contents():
    queries = run_agent_demo.get_default_demo_queries()
    assert queries == [
        "Find trusted ICU hospitals in Bihar",
        "Find emergency hospitals in Maharashtra",
        "Find dialysis centers in Uttar Pradesh",
        "Find oncology care in Gujarat",
        "Find maternity hospitals in Tamil Nadu",
    ]


def test_get_default_demo_queries_returns_fresh_copy():
    """Mutating the returned list must not affect subsequent callers."""
    a = run_agent_demo.get_default_demo_queries()
    a.append("BOGUS")
    b = run_agent_demo.get_default_demo_queries()
    assert "BOGUS" not in b
    assert len(b) == 5


# ---------------------------------------------------------------------------
# validate_real_dataset
# ---------------------------------------------------------------------------

def test_validate_real_dataset_passes_with_full_columns(capsys):
    df = _tiny_df()
    # Must not raise / exit
    run_agent_demo.validate_real_dataset(df)
    out = capsys.readouterr().out
    assert "rows" in out
    assert "columns" in out
    assert "required columns OK" in out


def test_validate_real_dataset_catches_missing_columns(capsys):
    df = _tiny_df().drop(columns=["evidence_summary", "trust_category"])
    with pytest.raises(SystemExit) as exc_info:
        run_agent_demo.validate_real_dataset(df)
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "evidence_summary" in err
    assert "trust_category" in err


def test_validate_real_dataset_handles_none(capsys):
    with pytest.raises(SystemExit) as exc_info:
        run_agent_demo.validate_real_dataset(None)  # type: ignore[arg-type]
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "None" in err


# ---------------------------------------------------------------------------
# load_real_dataset
# ---------------------------------------------------------------------------

def test_load_real_dataset_missing_file_exits_cleanly(capsys, tmp_path):
    bogus = str(tmp_path / "does_not_exist.csv")
    with pytest.raises(SystemExit) as exc_info:
        run_agent_demo.load_real_dataset(bogus)
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "Dataset not found" in err


def test_load_real_dataset_reads_a_temp_csv(tmp_path):
    df = _tiny_df()
    csv_path = tmp_path / "tiny.csv"
    df.to_csv(csv_path, index=False)
    loaded = run_agent_demo.load_real_dataset(str(csv_path))
    assert isinstance(loaded, pd.DataFrame)
    assert len(loaded) == len(df)
    assert "facility_id" in loaded.columns


# ---------------------------------------------------------------------------
# save_json_output / save_markdown_report
# ---------------------------------------------------------------------------

def _stub_results(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Run a single quick query through the real engine to get a real
    AgentResponse to serialise. Defaults keep both Tavily and Vector OFF.
    """
    return run_agent_demo.run_demo_queries(
        ["Find trusted ICU hospitals in Bihar"],
        df,
        max_results=2,
        enable_tavily=False,
        enable_vector=False,
    )


def test_save_json_output_writes_file(tmp_path):
    df = _tiny_df()
    results = _stub_results(df)
    target = tmp_path / "out.json"
    written = run_agent_demo.save_json_output(results, str(target))
    assert Path(written).exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["result_count"] == 1
    assert isinstance(payload["results"], list)
    assert payload["results"][0]["query"] == "Find trusted ICU hospitals in Bihar"
    # AgentResponse should serialise as a dict with 'recommendations'
    response = payload["results"][0]["response"]
    assert response is not None
    assert "recommendations" in response
    assert "safety_note" in response


def test_save_json_output_creates_parent_dir(tmp_path):
    df = _tiny_df()
    results = _stub_results(df)
    nested = tmp_path / "deep" / "nested" / "out.json"
    written = run_agent_demo.save_json_output(results, str(nested))
    assert Path(written).exists()


def test_save_markdown_report_writes_file(tmp_path):
    df = _tiny_df()
    results = _stub_results(df)
    target = tmp_path / "out.md"
    written = run_agent_demo.save_markdown_report(results, str(target))
    assert Path(written).exists()
    text = target.read_text(encoding="utf-8")
    assert "# CareGrid Vector Agent — Demo Run Report" in text
    assert "## Interpreted Intent" in text
    assert "## Retrieval Summary" in text
    assert "## Top Recommendations" in text
    assert "## Evidence Snippets" in text
    assert "## Validation Findings" in text
    assert "## Warning Flags" in text
    assert "## Tavily Verification" in text
    assert "## Safety Note" in text


def test_save_markdown_report_includes_query_text(tmp_path):
    df = _tiny_df()
    results = _stub_results(df)
    target = tmp_path / "out.md"
    run_agent_demo.save_markdown_report(results, str(target))
    text = target.read_text(encoding="utf-8")
    assert "Find trusted ICU hospitals in Bihar" in text


def test_save_markdown_report_handles_empty_results(tmp_path):
    target = tmp_path / "empty.md"
    run_agent_demo.save_markdown_report([], str(target))
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "Queries run:** 0" in text


# ---------------------------------------------------------------------------
# Network-isolation guarantees
# ---------------------------------------------------------------------------

def test_run_demo_queries_default_does_not_call_tavily(tmp_path):
    """With defaults (Tavily disabled), the Tavily client factory must
    never be invoked."""
    df = _tiny_df()
    factory = mock.MagicMock(name="tavily_factory_should_not_be_called")
    # Patch the top-level attribute the engine looks up lazily.
    with mock.patch(
        "agent_core.tavily_verifier._default_client_factory",
        factory,
    ):
        results = run_agent_demo.run_demo_queries(
            ["Find trusted ICU hospitals in Bihar"],
            df,
            max_results=2,
            enable_tavily=False,
            enable_vector=False,
        )
    factory.assert_not_called()
    assert len(results) == 1
    response = results[0]["response"]
    assert response is not None
    # Trace block must show Tavily disabled
    assert response.trace_summary.get("tavily", {}).get("enabled") is False


def test_run_demo_queries_default_does_not_call_databricks(tmp_path):
    """With defaults (Vector disabled), no Databricks SDK lookup happens."""
    df = _tiny_df()
    # The engine builds the default vector retriever lazily; if it tries
    # we want a hard signal.
    with mock.patch(
        "agent_core.recommendation_engine._build_default_vector_retriever",
        side_effect=AssertionError("vector retriever must not be built"),
    ):
        results = run_agent_demo.run_demo_queries(
            ["Find dialysis centers in Uttar Pradesh"],
            df,
            max_results=2,
            enable_tavily=False,
            enable_vector=False,
        )
    assert len(results) == 1
    response = results[0]["response"]
    assert response is not None
    assert response.trace_summary.get("vector", {}).get("enabled") is False


def test_run_demo_queries_returns_agent_response_objects():
    df = _tiny_df()
    results = run_agent_demo.run_demo_queries(
        ["Find trusted ICU hospitals in Bihar"],
        df,
        max_results=1,
    )
    assert len(results) == 1
    item = results[0]
    assert "query" in item
    assert "duration_seconds" in item
    assert "response" in item
    assert item["response"] is not None
    # AgentResponse contract
    response = item["response"]
    assert hasattr(response, "recommendations")
    assert hasattr(response, "safety_note")
    assert hasattr(response, "retrieval_summary")
    assert hasattr(response, "trace_summary")


def test_run_demo_queries_unknown_depth_falls_back_to_basic(tmp_path, capsys):
    df = _tiny_df()
    results = run_agent_demo.run_demo_queries(
        ["Find trusted ICU hospitals in Bihar"],
        df,
        max_results=1,
        web_depth="not_a_real_depth",
    )
    out = capsys.readouterr().out
    assert "Unknown --web-depth" in out
    assert results[0]["response"] is not None


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------

def test_cli_help_runs_and_exits_zero(capsys):
    """argparse --help should print and exit 0."""
    with pytest.raises(SystemExit) as exc_info:
        run_agent_demo._build_arg_parser().parse_args(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--enable-tavily" in out
    assert "--enable-vector" in out
    assert "--web-depth" in out


def test_cli_main_default_run(tmp_path, monkeypatch, capsys):
    """Run `main()` with the tiny CSV and a single query — no real
    Tavily / Databricks calls — JSON + Markdown should both be written."""
    df = _tiny_df()
    csv_path = tmp_path / "tiny.csv"
    df.to_csv(csv_path, index=False)

    json_path = tmp_path / "out.json"
    md_path   = tmp_path / "out.md"

    rc = run_agent_demo.main([
        "--query", "Find trusted ICU hospitals in Bihar",
        "--max-results", "1",
        "--dataset-path", str(csv_path),
        "--output-json", str(json_path),
        "--output-md",   str(md_path),
    ])
    assert rc == 0
    assert json_path.exists()
    assert md_path.exists()
    captured = capsys.readouterr().out
    assert "CareGrid Vector Agent — Demo Runner" in captured
    assert "Outputs" in captured


# ---------------------------------------------------------------------------
# Stage 17 — --enable-vector flag wiring
# ---------------------------------------------------------------------------

def test_stage17_enable_vector_flag_passes_through_to_engine(tmp_path):
    """``--enable-vector`` on the CLI must surface as
    ``enable_vector_search=True`` inside ``run_recommendation``.

    We patch the engine entry point so this test does NOT contact
    Databricks, keeping the Stage-17 contract that automated tests
    spend zero credits and make zero real calls."""
    df = _tiny_df()
    csv_path = tmp_path / "tiny.csv"
    df.to_csv(csv_path, index=False)

    # Build a fake response so the demo runner can shape its outputs.
    from agent_core.schemas import AgentIntent, AgentResponse  # local import
    fake_intent = AgentIntent(raw_query="x", original_query="x")
    fake_response = AgentResponse(
        query="x",
        intent=fake_intent,
        interpreted_intent=fake_intent,
        recommendations=[],
        evidence=[],
        warnings=[],
        reasoning="",
        safety_note="",
        validation_findings=[],
        retrieval_summary={
            "local_count": 0,
            "vector_enabled": True,
            "vector_available": True,
            "vector_count": 0,
            "vector_reason": "ok",
            "vector_filter_applied": True,
            "vector_filters_requested": {"state": "Bihar"},
            "vector_endpoint": "caregrid-vector-endpoint",
            "vector_index":    "workspace.default.caregrid_vector_index",
            "merged_count": 0,
            "after_top_k_count": 0,
            "relaxation_used": False,
        },
        total_candidates=0,
        returned=0,
        fallback_message="",
        trace_summary={
            "stages": [],
            "errors": [],
            "audit_log": {},
            "tavily": {"enabled": False, "verified": 0, "credits_estimated": 0, "depth": "basic"},
            "vector": {
                "enabled": True, "available": True, "count": 0, "reason": "ok",
                "filter_applied": True,
                "filters_requested": {"state": "Bihar"},
                "endpoint": "caregrid-vector-endpoint",
                "index":    "workspace.default.caregrid_vector_index",
            },
        },
    )

    with mock.patch(
        "run_agent_demo.run_recommendation",
        return_value=fake_response,
    ) as fake_engine:
        rc = run_agent_demo.main([
            "--query", "Find trusted ICU hospitals in Bihar",
            "--enable-vector",
            "--max-results", "1",
            "--dataset-path", str(csv_path),
            "--output-json", str(tmp_path / "out.json"),
            "--output-md",   str(tmp_path / "out.md"),
        ])

    assert rc == 0
    assert fake_engine.called
    kwargs = fake_engine.call_args.kwargs
    assert kwargs["enable_vector_search"] is True
    assert kwargs["enable_web_verification"] is False  # Tavily must stay off


def test_stage17_no_enable_vector_keeps_engine_vector_off(tmp_path):
    """Without ``--enable-vector`` the engine must be called with
    ``enable_vector_search=False``."""
    df = _tiny_df()
    csv_path = tmp_path / "tiny.csv"
    df.to_csv(csv_path, index=False)

    with mock.patch(
        "agent_core.recommendation_engine._build_default_vector_retriever",
        side_effect=AssertionError("vector retriever must not be built"),
    ):
        rc = run_agent_demo.main([
            "--query", "Find trusted ICU hospitals in Bihar",
            "--max-results", "1",
            "--dataset-path", str(csv_path),
            "--output-json", str(tmp_path / "out.json"),
            "--output-md",   str(tmp_path / "out.md"),
        ])

    assert rc == 0


def test_stage17_markdown_report_has_vector_search_section(tmp_path):
    """Stage 17: the Markdown report must include a ``## Vector Search``
    section with the key fields (enabled / available / count / reason /
    filter_applied / endpoint / index). The contents must reflect the
    engine response, not a hard-coded string."""
    from agent_core.schemas import AgentIntent, AgentResponse, ScoreBreakdown
    fake_intent = AgentIntent(raw_query="x", original_query="x")
    fake_response = AgentResponse(
        query="x",
        intent=fake_intent,
        interpreted_intent=fake_intent,
        recommendations=[],
        evidence=[],
        warnings=[],
        reasoning="",
        safety_note="see safety note",
        validation_findings=[],
        retrieval_summary={
            "local_count": 0,
            "vector_enabled": True,
            "vector_available": True,
            "vector_count": 7,
            "vector_reason": "ok",
            "vector_filter_applied": True,
            "vector_filters_requested": {"state": "Bihar"},
            "vector_endpoint": "caregrid-vector-endpoint",
            "vector_index":    "workspace.default.caregrid_vector_index",
            "merged_count": 0,
            "after_top_k_count": 0,
            "relaxation_used": False,
        },
        total_candidates=0,
        returned=0,
        fallback_message="",
        trace_summary={
            "stages": [],
            "errors": [],
            "audit_log": {},
            "tavily": {"enabled": False, "verified": 0, "credits_estimated": 0, "depth": "basic"},
            "vector": {
                "enabled": True, "available": True, "count": 7, "reason": "ok",
                "filter_applied": True,
                "filters_requested": {"state": "Bihar"},
                "endpoint": "caregrid-vector-endpoint",
                "index":    "workspace.default.caregrid_vector_index",
            },
        },
    )
    md_path = tmp_path / "vec.md"
    run_agent_demo.save_markdown_report(
        [{"query": "Find ICU in Bihar", "started_at": "now",
          "duration_seconds": 0.01, "response": fake_response, "error": None}],
        str(md_path),
    )
    md = md_path.read_text(encoding="utf-8")
    assert "## Vector Search" in md
    assert "**enabled:** True" in md
    assert "**available:** True" in md
    assert "**count:** 7" in md
    assert "caregrid-vector-endpoint" in md
    assert "workspace.default.caregrid_vector_index" in md


# ---------------------------------------------------------------------------
# Stage 18 — Combined Vector + Tavily smoke-test runner
# ---------------------------------------------------------------------------


def _stage18_fake_response(
    *,
    vector_count: int = 5,
    tavily_verified: int = 2,
    tavily_credits: int = 4,
) -> Any:
    """Build a fake :class:`AgentResponse` shaped like a real combined run.

    The response carries the Stage-18 retrieval-summary keys
    (``web_verification_enabled``, ``tavily_verified_count``,
    ``tavily_depth``, ``tavily_credits_estimated``) so demo-runner output
    assertions don't need a real engine call.
    """
    from agent_core.schemas import (
        AgentIntent, AgentRecommendation, AgentResponse,
        ScoreBreakdown, WebVerificationResult,
    )
    intent = AgentIntent(
        raw_query="Find trusted ICU hospitals in Bihar",
        original_query="Find trusted ICU hospitals in Bihar",
        capabilities_required=["ICU_CRITICAL_CARE"],
        state="Bihar",
        urgency="unspecified",
    )
    sb = ScoreBreakdown(
        trust_score_component=0.23,
        readiness_component=0.15,
        capability_match_component=0.12,
        evidence_strength_component=0.10,
        validation_penalty=0.0,
        warning_penalty=0.0,
        vector_similarity_component=0.09,
        tavily_verification_component=0.10,
        final_score=0.79,
    )
    web = WebVerificationResult(
        facility_id="F001",
        web_checked=True,
        web_available=True,
        verification_status="verified",
        verification_score=0.7,
        top_url="https://example.org/",
        top_snippet="An ICU hospital",
        credits_estimated=2,
    )
    rec = AgentRecommendation(
        facility_id="F001",
        name="Apollo Test Hospital",
        trust_score=0.92,
        trust_category="High Trust / Evidence Supported",
        recommendation_readiness="Ready for recommendation",
        score_breakdown=sb,
        web_verification=web,
        reason_for_recommendation="Recommended because: matches ICU.",
        human_next_steps=["Confirm capability with the facility before transit."],
        state="Bihar", city="Patna", facility_type="hospital",
    )
    return AgentResponse(
        query="Find trusted ICU hospitals in Bihar",
        intent=intent, interpreted_intent=intent,
        recommendations=[rec], evidence=[], warnings=[],
        reasoning="ok", safety_note="see safety note",
        validation_findings=[],
        retrieval_summary={
            "local_count": 100,
            "vector_enabled": True,
            "vector_available": True,
            "vector_count": vector_count,
            "vector_reason": "ok",
            "vector_filter_applied": True,
            "vector_filters_requested": {"state": "Bihar"},
            "vector_endpoint": "caregrid-vector-endpoint",
            "vector_index":    "workspace.default.caregrid_vector_index",
            "merged_count": 105,
            "after_top_k_count": 1,
            "relaxation_used": False,
            "web_verification_enabled": True,
            "tavily_verified_count":    tavily_verified,
            "tavily_depth":             "basic",
            "tavily_credits_estimated": tavily_credits,
        },
        total_candidates=105, returned=1, fallback_message="",
        trace_summary={
            "stages": [
                {"stage": "intent_parsed"},
                {"stage": "local_retrieval", "count": 100},
                {"stage": "vector_retrieval", "enabled": True, "available": True,
                 "count": vector_count, "filter_applied": True},
                {"stage": "merge", "count": 105},
                {"stage": "enrich"},
                {"stage": "score_and_rank", "top_count": 1},
                {"stage": "tavily_verification", "enabled": True,
                 "verified_count": tavily_verified},
                {"stage": "final_response", "returned": 1, "had_fallback": False},
            ],
            "errors": [],
            "audit_log": {"event_types": [
                "intent_parsed", "local_retrieval", "vector_retrieval",
                "merge", "enrich", "score_and_rank", "tavily_verification",
                "final_response",
            ]},
            "tavily": {
                "enabled": True,
                "verified": tavily_verified,
                "credits_estimated": tavily_credits,
                "depth": "basic",
            },
            "vector": {
                "enabled": True, "available": True, "count": vector_count,
                "reason": "ok", "filter_applied": True,
                "filters_requested": {"state": "Bihar"},
                "endpoint": "caregrid-vector-endpoint",
                "index":    "workspace.default.caregrid_vector_index",
            },
        },
    )


def test_stage18_combined_flags_pass_through_to_engine(tmp_path):
    """``--enable-vector --enable-tavily`` must call ``run_recommendation``
    with both ``enable_vector_search=True`` AND ``enable_web_verification=True``.

    No real Databricks or Tavily calls are made — the engine is mocked.
    """
    df = _tiny_df()
    csv_path = tmp_path / "tiny.csv"
    df.to_csv(csv_path, index=False)

    fake_response = _stage18_fake_response()
    with mock.patch(
        "run_agent_demo.run_recommendation",
        return_value=fake_response,
    ) as fake_engine:
        rc = run_agent_demo.main([
            "--query", "Find trusted ICU hospitals in Bihar",
            "--enable-vector",
            "--enable-tavily",
            "--web-depth", "basic",
            "--max-web-verified", "2",
            "--max-results", "1",
            "--dataset-path", str(csv_path),
            "--output-json", str(tmp_path / "out.json"),
            "--output-md",   str(tmp_path / "out.md"),
        ])

    assert rc == 0
    assert fake_engine.called
    kwargs = fake_engine.call_args.kwargs
    assert kwargs["enable_vector_search"] is True
    assert kwargs["enable_web_verification"] is True
    assert kwargs["web_verification_depth"] == "basic"
    assert kwargs["max_web_verified"] == 2


def test_stage18_combined_markdown_has_all_required_sections(tmp_path):
    """Stage 18 Markdown must include every panel the runbook calls out:

    * Interpreted Intent
    * Retrieval Summary  (with the Stage-18 Tavily keys surfaced)
    * Top Recommendations
    * Score Breakdown    (new in Stage 18)
    * Evidence Snippets
    * Validation Findings
    * Warning Flags
    * Vector Search
    * Tavily Verification
    * Human Next Steps   (new in Stage 18)
    * Safety Note
    * Debug / Trace Summary  (new in Stage 18)
    """
    md_path = tmp_path / "combined.md"
    run_agent_demo.save_markdown_report(
        [{
            "query": "Find trusted ICU hospitals in Bihar",
            "started_at": "now",
            "duration_seconds": 0.01,
            "response": _stage18_fake_response(),
            "error": None,
        }],
        str(md_path),
    )
    md = md_path.read_text(encoding="utf-8")
    for section in [
        "## Interpreted Intent",
        "## Retrieval Summary",
        "## Top Recommendations",
        "## Score Breakdown",
        "## Evidence Snippets",
        "## Validation Findings",
        "## Warning Flags",
        "## Vector Search",
        "## Tavily Verification",
        "## Human Next Steps",
        "## Safety Note",
        "## Debug / Trace Summary",
    ]:
        assert section in md, f"missing section: {section!r}"
    # Stage-18 retrieval summary keys must be visible
    assert "**web_verification_enabled:** True" in md
    assert "**tavily_verified_count:** 2" in md
    assert "**tavily_depth:**" in md
    assert "**tavily_credits_estimated:** 4" in md
    # Score breakdown table must show both vector + tavily components
    assert "vector" in md.lower() and "tavily" in md.lower()
    # Trace summary block contains the JSON fence
    assert "```json" in md
    # Final response stage is present in the trace
    assert "final_response" in md


def test_stage18_no_combined_flags_keeps_both_off(tmp_path):
    """Bare ``--query`` (no flags) must keep ``enable_vector_search=False``
    AND ``enable_web_verification=False``."""
    df = _tiny_df()
    csv_path = tmp_path / "tiny.csv"
    df.to_csv(csv_path, index=False)

    fake_response = _stage18_fake_response(
        vector_count=0, tavily_verified=0, tavily_credits=0,
    )
    with mock.patch(
        "run_agent_demo.run_recommendation",
        return_value=fake_response,
    ) as fake_engine:
        rc = run_agent_demo.main([
            "--query", "Find ICU hospitals",
            "--max-results", "1",
            "--dataset-path", str(csv_path),
            "--output-json", str(tmp_path / "out.json"),
            "--output-md",   str(tmp_path / "out.md"),
        ])

    assert rc == 0
    kwargs = fake_engine.call_args.kwargs
    assert kwargs["enable_vector_search"] is False
    assert kwargs["enable_web_verification"] is False
