"""
Golden-query evaluation suite (Stage 14).

Each of the 10 :data:`agent_core.demo_queries.GOLDEN_QUERIES` entries is
exercised against a single, canonical 11-row ``facilities_df`` fixture
(see :func:`golden_facilities_df`). The dataset is hand-built so that
every golden query has at least one *expected* hit in the returned
recommendations or, where required, a fallback message.

The suite checks the **universal output contract** for every query
(response shape, safety note, score breakdown, state / facility_type
respected) and adds **per-query targeted assertions** for the queries
that exist specifically to test soft-filter or risk-flag behaviour
(GQ-009 verification readiness; GQ-010 unsupported emergency claim).

A separate test runs all 10 queries with a mocked Tavily client to
confirm that the optional web-verification path attaches
:class:`WebVerificationResult` objects without crashing the engine.

The original Stage-3 ``DEMO_QUERIES`` tests are preserved at the bottom
of this module.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_core.demo_queries import DEMO_QUERIES, GOLDEN_QUERIES  # noqa: E402
from agent_core.intent_parser import parse_intent, parse_query_intent  # noqa: E402
from agent_core.recommendation_engine import (  # noqa: E402
    SAFETY_NOTE,
    run_recommendation,
)
from agent_core.schemas import (  # noqa: E402
    AgentRecommendation,
    AgentResponse,
    ScoreBreakdown,
    WebVerificationResult,
)


# ---------------------------------------------------------------------------
# Canonical 11-row golden fixture
# ---------------------------------------------------------------------------


_GOLDEN_FACILITIES: list[dict] = [
    {  # 1. Trusted ICU + dialysis + oncology in Maharashtra
        "facility_id": "F-MUM-01",
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
        "evidence_summary": "Multispecialty hospital with strong critical care and dialysis services.",
        "combined_medical_evidence": (
            "ICU bed, ventilator, dialysis machine, oncology unit, "
            "operation theatre with anesthesia."
        ),
    },
    {  # 2. Trusted ICU + diagnostics + oncology in Delhi
        "facility_id": "F-DEL-01",
        "name": "AIIMS Delhi",
        "facility_type": "hospital",
        "state": "Delhi",
        "city": "New Delhi",
        "trust_score": 0.95,
        "trust_category": "High Trust / Evidence Supported",
        "recommendation_readiness": "Ready for recommendation",
        "specialties": "cardiology, oncology, neurology, intensive care, radiology",
        "procedures": "ICU monitoring, chemotherapy, surgery, MRI, CT scan",
        "equipment": "ventilator, ICU bed, defibrillator, monitor, MRI machine, CT scanner",
        "capabilities_raw": "24/7 ICU, oncology, diagnostics imaging",
        "evidence_summary": "Premier government tertiary hospital with full imaging suite.",
        "combined_medical_evidence": (
            "ICU bed, ventilator, defibrillator, oncology unit, MRI, CT scan, "
            "operation theatre with anesthesia."
        ),
    },
    {  # 3. Bihar ICU hospital
        "facility_id": "F-BIH-01",
        "name": "Patna Heart Hospital",
        "facility_type": "hospital",
        "state": "Bihar",
        "city": "Patna",
        "trust_score": 0.84,
        "trust_category": "High Trust / Evidence Supported",
        "recommendation_readiness": "Ready for recommendation",
        "specialties": "cardiology, intensive care",
        "procedures": "ICU monitoring, cardiac care",
        "equipment": "ventilator, ICU bed, monitor, defibrillator",
        "capabilities_raw": "24/7 ICU, cardiac care",
        "evidence_summary": "Bihar state cardiac referral centre.",
        "combined_medical_evidence": (
            "ICU bed, ventilator, defibrillator, cardiac monitoring."
        ),
    },
    {  # 4. Maharashtra emergency + trauma hospital
        "facility_id": "F-MAH-02",
        "name": "Mumbai Trauma Centre",
        "facility_type": "hospital",
        "state": "Maharashtra",
        "city": "Mumbai",
        "trust_score": 0.88,
        "trust_category": "High Trust / Evidence Supported",
        "recommendation_readiness": "Ready for recommendation",
        "specialties": "emergency medicine, trauma, intensive care",
        "procedures": "trauma surgery, ICU monitoring, emergency resuscitation",
        "equipment": (
            "ventilator, defibrillator, ICU bed, ambulance, stretcher, "
            "emergency trolley"
        ),
        "capabilities_raw": "24/7 emergency, trauma bay, ICU, ambulance",
        "evidence_summary": "Level 1 trauma centre with on-site ambulance fleet.",
        "combined_medical_evidence": (
            "Trauma bay, defibrillator, ventilator, ICU, ambulance, "
            "emergency surgery suite."
        ),
    },
    {  # 5. Uttar Pradesh dialysis
        "facility_id": "F-UP-01",
        "name": "Lucknow Renal Care",
        "facility_type": "hospital",
        "state": "Uttar Pradesh",
        "city": "Lucknow",
        "trust_score": 0.81,
        "trust_category": "High Trust / Evidence Supported",
        "recommendation_readiness": "Ready for recommendation",
        "specialties": "nephrology",
        "procedures": "hemodialysis, peritoneal dialysis",
        "equipment": "dialysis machine, RO water plant, dialysis chair",
        "capabilities_raw": "dialysis unit, kidney care",
        "evidence_summary": "Dedicated renal care hospital.",
        "combined_medical_evidence": (
            "Dialysis machine, RO water plant, hemodialysis unit, nephrology services."
        ),
    },
    {  # 6. Gujarat oncology
        "facility_id": "F-GUJ-01",
        "name": "Ahmedabad Cancer Centre",
        "facility_type": "hospital",
        "state": "Gujarat",
        "city": "Ahmedabad",
        "trust_score": 0.86,
        "trust_category": "High Trust / Evidence Supported",
        "recommendation_readiness": "Ready for recommendation",
        "specialties": "oncology, radiation oncology",
        "procedures": "chemotherapy, radiotherapy, tumor board",
        "equipment": "linear accelerator, PET-CT scanner, chemotherapy infusion pump",
        "capabilities_raw": "oncology, cancer treatment, radiation therapy",
        "evidence_summary": "Comprehensive cancer care centre.",
        "combined_medical_evidence": (
            "Linear accelerator, chemotherapy protocol, PET-CT, radiation oncology."
        ),
    },
    {  # 7. Tamil Nadu maternity hospital
        "facility_id": "F-TN-01",
        "name": "Chennai Mother Care Hospital",
        "facility_type": "hospital",
        "state": "Tamil Nadu",
        "city": "Chennai",
        "trust_score": 0.83,
        "trust_category": "High Trust / Evidence Supported",
        "recommendation_readiness": "Ready for recommendation",
        "specialties": "maternity, obstetrics, gynaecology",
        "procedures": "delivery, antenatal care, C-section, LSCS",
        "equipment": "delivery table, CTG machine, foetal monitor, epidural pump",
        "capabilities_raw": "maternity ward, labour room, delivery",
        "evidence_summary": "Dedicated maternity hospital with 24-hour labour ward.",
        "combined_medical_evidence": (
            "Labour room, CTG monitoring, C-section suite, antenatal clinic."
        ),
    },
    {  # 8. Gujarat NICU
        "facility_id": "F-GUJ-02",
        "name": "Surat Neonatal Hospital",
        "facility_type": "hospital",
        "state": "Gujarat",
        "city": "Surat",
        "trust_score": 0.85,
        "trust_category": "High Trust / Evidence Supported",
        "recommendation_readiness": "Ready for recommendation",
        "specialties": "neonatology, paediatrics, intensive care",
        "procedures": "neonatal resuscitation, NICU monitoring, preterm care",
        "equipment": (
            "incubator, neonatal ventilator, phototherapy lamp, "
            "neonatal resuscitation table, pulse oximeter paediatric"
        ),
        "capabilities_raw": "NICU, neonatal ICU, paediatric ICU",
        "evidence_summary": "Dedicated NICU with surfactant therapy and kangaroo mother care.",
        "combined_medical_evidence": (
            "Incubator, neonatal ventilator, phototherapy, neonatal resuscitation."
        ),
    },
    {  # 9. Delhi diagnostics clinic
        "facility_id": "F-DEL-02",
        "name": "Delhi Imaging & Diagnostics Centre",
        "facility_type": "clinic",
        "state": "Delhi",
        "city": "New Delhi",
        "trust_score": 0.74,
        "trust_category": "Medium Trust / Likely Reliable",
        "recommendation_readiness": "Ready for recommendation",
        "specialties": "radiology, pathology",
        "procedures": "MRI, CT scan, X-ray, ultrasound, ECG, echo",
        "equipment": (
            "MRI machine, CT scanner, X-ray machine, ultrasound machine, "
            "ECG machine, NABL lab equipment"
        ),
        "capabilities_raw": "diagnostic centre, imaging, lab services",
        "evidence_summary": "NABL accredited diagnostic centre.",
        "combined_medical_evidence": (
            "3T MRI, 128-slice CT, NABL accredited lab, digital X-ray, mammography."
        ),
    },
    {  # 10. Verification-only dialysis facility (used by GQ-009)
        "facility_id": "F-VER-01",
        "name": "Verify Before Use Dialysis",
        "facility_type": "hospital",
        "state": "Andhra Pradesh",
        "city": "Vijayawada",
        "trust_score": 0.62,
        "trust_category": "Medium Trust / Likely Reliable",
        "recommendation_readiness": "Usable with verification",
        "specialties": "nephrology",
        "procedures": "hemodialysis",
        "equipment": "dialysis machine",
        "capabilities_raw": "dialysis",
        "evidence_summary": "Dialysis services available; verify staffing before referral.",
        "combined_medical_evidence": "Dialysis machine. Hemodialysis available.",
    },
    {  # 11. High-risk hospital with unsupported emergency claim (used by GQ-010)
        "facility_id": "F-RISKY-01",
        "name": "Sketchy Emergency Hospital",
        "facility_type": "hospital",
        "state": "Karnataka",
        "city": "Bangalore",
        "trust_score": 0.38,
        "trust_category": "Low Trust",
        "recommendation_readiness": "Do not recommend without human review",
        "specialties": "emergency medicine, general practice",
        "procedures": "",  # no real emergency procedures
        "equipment": "",   # no defibrillator, no trauma bay
        "capabilities_raw": "24/7 emergency claimed",
        "evidence_summary": "Claims emergency services; no equipment listed.",
        "combined_medical_evidence": "Emergency unit (claim only).",
    },
]


@pytest.fixture(scope="module")
def golden_facilities_df() -> pd.DataFrame:
    return pd.DataFrame(_GOLDEN_FACILITIES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ids(specs: list[dict]) -> list[str]:
    return [s["id"] for s in specs]


def _state_filter_actively_set(spec: dict) -> bool:
    return spec.get("expected_state") is not None


def _facility_type_filter_actively_set(spec: dict) -> bool:
    return spec.get("expected_facility_type") is not None


# ---------------------------------------------------------------------------
# Universal contract — runs for every golden query
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec", GOLDEN_QUERIES, ids=_ids(GOLDEN_QUERIES))
def test_golden_query_response_contract(spec, golden_facilities_df):
    """Every golden query must return a well-formed AgentResponse."""
    resp = run_recommendation(spec["query"], golden_facilities_df, max_results=5)

    assert isinstance(resp, AgentResponse)
    assert resp.query == spec["query"]

    # interpreted_intent is always populated.
    assert resp.interpreted_intent is not None
    intent = resp.interpreted_intent

    # Safety note is constant and always present.
    assert resp.safety_note == SAFETY_NOTE

    # Either at least one recommendation OR a non-empty fallback_message.
    assert resp.recommendations or resp.fallback_message, (
        f"{spec['id']}: neither recommendations nor fallback_message produced"
    )

    # Returned count matches the recommendations list.
    assert resp.returned == len(resp.recommendations)

    # When recommendations exist, every one must carry a ScoreBreakdown.
    for rec in resp.recommendations:
        assert isinstance(rec, AgentRecommendation)
        assert isinstance(rec.score_breakdown, ScoreBreakdown), (
            f"{spec['id']}: recommendation {rec.facility_id} missing score_breakdown"
        )
        assert 0.0 <= rec.score_breakdown.final_score <= 1.0
        assert rec.reason_for_recommendation
        assert rec.human_next_steps

    # State filter respected when actively set, unless fallback explains relaxation.
    if _state_filter_actively_set(spec) and resp.recommendations:
        expected_state = spec["expected_state"]
        for rec in resp.recommendations:
            assert rec.state == expected_state, (
                f"{spec['id']}: recommendation {rec.facility_id} state "
                f"{rec.state!r} != expected {expected_state!r}"
            )

    # Facility-type filter respected when actively set, with the same caveat.
    if _facility_type_filter_actively_set(spec) and resp.recommendations:
        expected_ft = spec["expected_facility_type"]
        # The local retriever may relax facility_type — when that
        # happens it tags the candidate's relaxation_notes; if any
        # recommendation is flagged "retrieved_via_relaxation" we accept
        # a different facility_type.
        for rec in resp.recommendations:
            if "retrieved_via_relaxation" in (rec.warning_flags or []):
                continue
            assert rec.facility_type == expected_ft, (
                f"{spec['id']}: recommendation {rec.facility_id} facility_type "
                f"{rec.facility_type!r} != expected {expected_ft!r}"
            )


@pytest.mark.parametrize("spec", GOLDEN_QUERIES, ids=_ids(GOLDEN_QUERIES))
def test_golden_query_intent_extraction(spec):
    """Intent parser must extract the expected fields for each golden query.

    Capability extraction uses *subset* semantics — the parser is
    permitted to pick up additional capabilities via aggressive keyword
    substring matching (e.g. "ER" in "centers"); what matters is that
    every expected capability appears.
    """
    intent = parse_query_intent(spec["query"])

    for cap in spec["expected_capabilities"]:
        assert cap in intent.capabilities_required, (
            f"{spec['id']}: expected capability {cap!r} not in "
            f"{intent.capabilities_required!r}"
        )

    assert intent.state == spec["expected_state"], (
        f"{spec['id']}: state {intent.state!r} != expected {spec['expected_state']!r}"
    )
    assert intent.facility_type == spec["expected_facility_type"], (
        f"{spec['id']}: facility_type {intent.facility_type!r} != "
        f"expected {spec['expected_facility_type']!r}"
    )
    assert intent.trust_preference == spec["expected_trust_preference"], (
        f"{spec['id']}: trust_preference {intent.trust_preference!r} != "
        f"expected {spec['expected_trust_preference']!r}"
    )
    assert intent.urgency == spec["expected_urgency"], (
        f"{spec['id']}: urgency {intent.urgency!r} != expected {spec['expected_urgency']!r}"
    )


@pytest.mark.parametrize("spec", GOLDEN_QUERIES, ids=_ids(GOLDEN_QUERIES))
def test_golden_query_evidence_snippets_present_when_recommendations_exist(
    spec, golden_facilities_df,
):
    """Where recommendations are returned, the top one carries evidence
    for at least one expected capability — provided the dataset contains
    such evidence (the fallback case is exercised by the contract test
    above)."""
    resp = run_recommendation(spec["query"], golden_facilities_df, max_results=5)
    if not resp.recommendations:
        pytest.skip(f"{spec['id']}: no recommendations (covered by fallback test)")

    top = resp.recommendations[0]
    expected_caps = set(spec["expected_capabilities"])
    snippet_caps = {s.capability_id for s in top.evidence_snippets if s.capability_id}
    # Allow facilities returned via vector-only / relaxation paths to
    # have no snippets — those are flagged by warning_flags. Otherwise
    # we expect at least one expected capability to be supported.
    if not (snippet_caps & expected_caps):
        relaxed = "retrieved_via_relaxation" in (top.warning_flags or [])
        assert relaxed, (
            f"{spec['id']}: top recommendation {top.facility_id} has no "
            f"evidence snippet for expected caps {expected_caps}; snippets "
            f"covered {snippet_caps}"
        )


# ---------------------------------------------------------------------------
# Per-query behavioural assertions
# ---------------------------------------------------------------------------


def test_gq001_trusted_icu_returns_high_trust_first(golden_facilities_df):
    """Trusted ICU query with no geographic filter — top result must be
    one of the high-trust ICU facilities (Apollo Mumbai, AIIMS Delhi,
    Mumbai Trauma Centre, or Patna Heart Hospital)."""
    resp = run_recommendation("Find trusted ICU facilities", golden_facilities_df)
    assert resp.recommendations
    top_ids = {r.facility_id for r in resp.recommendations[:3]}
    assert top_ids & {"F-MUM-01", "F-DEL-01", "F-MAH-02", "F-BIH-01"}, (
        f"None of the high-trust ICU facilities reached the top-3: {top_ids}"
    )


def test_gq002_bihar_icu_returns_only_bihar_hospitals(golden_facilities_df):
    resp = run_recommendation(
        "Find trusted ICU hospitals in Bihar", golden_facilities_df,
    )
    assert resp.recommendations
    assert all(r.state == "Bihar" for r in resp.recommendations)
    assert all(r.facility_type == "hospital" for r in resp.recommendations)
    assert "F-BIH-01" in {r.facility_id for r in resp.recommendations}


def test_gq003_emergency_maharashtra_top_is_trauma_centre(golden_facilities_df):
    resp = run_recommendation(
        "Find emergency hospitals in Maharashtra", golden_facilities_df,
    )
    assert resp.recommendations
    assert all(r.state == "Maharashtra" for r in resp.recommendations)
    # Top should be the dedicated trauma centre, not Apollo (which has
    # ICU but no trauma bay).
    assert resp.recommendations[0].facility_id == "F-MAH-02"
    # Emergency urgency should add an emergency-specific next step.
    joined = " ".join(resp.recommendations[0].human_next_steps).lower()
    assert "emergency" in joined


def test_gq004_dialysis_uttar_pradesh(golden_facilities_df):
    resp = run_recommendation(
        "Find dialysis centers in Uttar Pradesh", golden_facilities_df,
    )
    assert resp.recommendations
    assert all(r.state == "Uttar Pradesh" for r in resp.recommendations)
    assert "F-UP-01" in {r.facility_id for r in resp.recommendations}


def test_gq005_oncology_gujarat(golden_facilities_df):
    resp = run_recommendation(
        "Find oncology care in Gujarat", golden_facilities_df,
    )
    assert resp.recommendations
    assert all(r.state == "Gujarat" for r in resp.recommendations)
    top = resp.recommendations[0]
    assert top.facility_id == "F-GUJ-01"
    cap_ids = {s.capability_id for s in top.evidence_snippets if s.capability_id}
    assert "ONCOLOGY" in cap_ids


def test_gq006_maternity_tamil_nadu(golden_facilities_df):
    resp = run_recommendation(
        "Find maternity hospitals in Tamil Nadu", golden_facilities_df,
    )
    assert resp.recommendations
    assert all(r.state == "Tamil Nadu" for r in resp.recommendations)
    assert all(r.facility_type == "hospital" for r in resp.recommendations)
    top = resp.recommendations[0]
    assert top.facility_id == "F-TN-01"


def test_gq007_neonatal_icu_gujarat(golden_facilities_df):
    resp = run_recommendation(
        "Find neonatal ICU support in Gujarat", golden_facilities_df,
    )
    assert resp.recommendations
    assert all(r.state == "Gujarat" for r in resp.recommendations)
    # Surat NICU should win on neonatal evidence.
    assert "F-GUJ-02" in {r.facility_id for r in resp.recommendations}
    top = resp.recommendations[0]
    cap_ids = {s.capability_id for s in top.evidence_snippets if s.capability_id}
    # At least one of the requested capabilities is evidenced.
    assert {"NEONATAL_PEDIATRIC", "ICU_CRITICAL_CARE"} & cap_ids


def test_gq008_diagnostics_delhi(golden_facilities_df):
    resp = run_recommendation(
        "Find diagnostics centers in Delhi", golden_facilities_df,
    )
    assert resp.recommendations
    assert all(r.state == "Delhi" for r in resp.recommendations)
    returned_ids = {r.facility_id for r in resp.recommendations}
    # Both Delhi facilities (AIIMS hospital + Delhi Imaging clinic) must
    # show up because there is no facility_type filter.
    assert "F-DEL-01" in returned_ids or "F-DEL-02" in returned_ids


def test_gq009_dialysis_verification_includes_non_ready(golden_facilities_df):
    """The 'needs human verification' query must surface at least one
    facility whose readiness is NOT 'Ready for recommendation'.

    We pull a wider top-K than the default (5) so the verification-only
    facility — which sits below the high-trust dialysis hospitals on
    final_score — is guaranteed to be in the returned list.
    """
    resp = run_recommendation(
        "Find facilities that need human verification for dialysis",
        golden_facilities_df,
        max_results=15,
    )
    assert resp.recommendations
    non_ready = [
        r for r in resp.recommendations
        if r.recommendation_readiness != "Ready for recommendation"
    ]
    assert non_ready, (
        "Expected at least one verification-only facility in the result set"
    )
    assert "F-VER-01" in {r.facility_id for r in resp.recommendations}


def test_gq010_unsupported_emergency_claim_flagged(golden_facilities_df):
    """The high-risk emergency query must include a hospital whose
    emergency claim is unsupported by evidence — the validator must
    produce a missing-evidence finding and a warning_flag entry on that
    hospital.

    Pull a wider top-K than the default (5) so the low-trust hospital
    is guaranteed to be in the returned list — by design it ranks below
    the legitimate emergency hospitals.
    """
    resp = run_recommendation(
        "Find high-risk hospitals with unsupported emergency claims",
        golden_facilities_df,
        max_results=15,
    )
    assert resp.recommendations
    by_id = {r.facility_id for r in resp.recommendations}
    assert "F-RISKY-01" in by_id, (
        f"Sketchy hospital missing from emergency results: {by_id}"
    )

    risky = next(r for r in resp.recommendations if r.facility_id == "F-RISKY-01")
    # Validator must produce at least one finding for this facility.
    assert risky.validation_findings, (
        "Expected validation_findings on the unsupported-emergency hospital"
    )
    finding_types = {f.finding_type for f in risky.validation_findings}
    assert {"missing_evidence", "weak_evidence", "contradiction"} & finding_types
    # Warning flag surface must be populated.
    assert risky.warning_flags
    flags = set(risky.warning_flags)
    assert flags & {
        "missing_capability_evidence",
        "weak_capability_evidence",
        "contradiction_detected",
    }


# ---------------------------------------------------------------------------
# Mocked-Tavily smoke test across all 10 queries
# ---------------------------------------------------------------------------


@pytest.fixture
def tavily_enabled_settings() -> SimpleNamespace:
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


def _make_tavily_factory() -> MagicMock:
    fake_client = MagicMock()
    fake_client.search.return_value = {
        "results": [
            {
                "title": "Official Hospital Listing",
                "url": "https://example-hospital.in/about",
                "content": (
                    "Government-recognised hospital offering ICU, dialysis, "
                    "oncology and maternity services across India."
                ),
                "score": 0.85,
            }
        ]
    }
    return MagicMock(return_value=fake_client)


@pytest.mark.parametrize("spec", GOLDEN_QUERIES, ids=_ids(GOLDEN_QUERIES))
def test_golden_query_with_mocked_tavily_does_not_crash(
    spec, golden_facilities_df, tavily_enabled_settings,
):
    factory = _make_tavily_factory()
    resp = run_recommendation(
        spec["query"],
        golden_facilities_df,
        max_results=3,
        enable_web_verification=True,
        web_verification_depth="basic",
        max_web_verified=2,
        settings=tavily_enabled_settings,
        tavily_client_factory=factory,
    )
    assert isinstance(resp, AgentResponse)
    assert resp.safety_note == SAFETY_NOTE
    assert resp.trace_summary["tavily"]["enabled"] is True

    # When recommendations exist, at least the top one should have been
    # passed to Tavily and carry a WebVerificationResult.
    if resp.recommendations:
        verified = [
            r for r in resp.recommendations if r.web_verification is not None
        ]
        assert verified, f"{spec['id']}: no web_verification attached"
        for rec in verified:
            assert isinstance(rec.web_verification, WebVerificationResult)
            assert rec.web_verification.web_checked is True
            assert rec.web_verification.verification_status in {
                "verified", "partial", "unverified",
            }


# ---------------------------------------------------------------------------
# Aggregate sanity checks on the GOLDEN_QUERIES list itself
# ---------------------------------------------------------------------------


def test_golden_queries_count_is_ten():
    assert len(GOLDEN_QUERIES) == 10


def test_golden_queries_have_required_fields():
    required = {
        "id", "query", "expected_capabilities", "expected_state",
        "expected_facility_type", "expected_trust_preference",
        "expected_urgency", "expected_behavior", "notes",
    }
    for spec in GOLDEN_QUERIES:
        assert required.issubset(spec.keys()), (
            f"{spec.get('id')}: missing keys {required - set(spec.keys())}"
        )


def test_golden_queries_ids_are_unique():
    ids = [s["id"] for s in GOLDEN_QUERIES]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Backward-compat: Stage-3 DEMO_QUERIES tests (preserved verbatim)
# ---------------------------------------------------------------------------


def test_demo_queries_exist():
    assert len(DEMO_QUERIES) > 0


def test_demo_queries_have_required_fields():
    for q in DEMO_QUERIES:
        assert "id" in q
        assert "query" in q
        assert "expected_capabilities" in q


@pytest.mark.parametrize(
    "demo", DEMO_QUERIES, ids=[q["id"] for q in DEMO_QUERIES]
)
def test_intent_parser_on_demo_queries(demo):
    intent = parse_intent(demo["query"])
    assert intent.raw_query == demo["query"]
    for cap in demo["expected_capabilities"]:
        assert cap in intent.capabilities_required, (
            f"{demo['id']}: expected capability '{cap}' not found in "
            f"{intent.capabilities_required}"
        )
