"""
Unit tests for `agent_core.local_retriever`.

Two surfaces are exercised:
  1. `retrieve_local_candidates(df, intent, ...)` — the new candidate-style
     retriever with strict-then-relax filtering, capability scoring, and
     relaxation notes. This is the primary fallback path the orchestrator
     uses when Databricks vector search is unavailable.
  2. `retrieve_local(query, df, top_k)` — the legacy single-string
     keyword filter, kept for backward compatibility.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_core.intent_parser import parse_query_intent  # noqa: E402
from agent_core.local_retriever import (  # noqa: E402
    LocalCandidate,
    SEARCH_FIELDS,
    retrieve_local,
    retrieve_local_candidates,
)
from agent_core.schemas import AgentIntent  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _facility(
    facility_id: str,
    *,
    name: str = "Generic Hospital",
    state: str = "Maharashtra",
    facility_type: str = "hospital",
    trust_score: float = 0.7,
    specialties: str = "",
    procedures: str = "",
    equipment: str = "",
    capabilities_raw: str = "",
    evidence_summary: str = "",
    combined_medical_evidence: str = "",
) -> dict:
    return {
        "facility_id": facility_id,
        "name": name,
        "state": state,
        "facility_type": facility_type,
        "trust_score": trust_score,
        "specialties": specialties,
        "procedures": procedures,
        "equipment": equipment,
        "capabilities_raw": capabilities_raw,
        "evidence_summary": evidence_summary,
        "combined_medical_evidence": combined_medical_evidence,
    }


@pytest.fixture
def fixture_df() -> pd.DataFrame:
    """A small but varied facility set covering the main test scenarios."""
    return pd.DataFrame([
        # Maharashtra ICU hospital — strong evidence
        _facility(
            "F001", name="Apollo Mumbai", state="Maharashtra",
            facility_type="hospital", trust_score=0.92,
            specialties="Critical Care, Cardiology",
            equipment="ventilator, cardiac monitor, defibrillator",
            evidence_summary="24-bed ICU with full intensive care unit",
            combined_medical_evidence=(
                "Modern ICU with ventilators and arterial line monitoring. "
                "Trained intensivists available 24/7."
            ),
        ),
        # Maharashtra dialysis hospital
        _facility(
            "F002", name="Fortis Pune", state="Maharashtra",
            facility_type="hospital", trust_score=0.85,
            specialties="Nephrology",
            procedures="hemodialysis, peritoneal dialysis",
            equipment="dialysis machine, RO water plant",
            evidence_summary="Renal dialysis unit with 12 chairs",
            combined_medical_evidence="Hemodialysis available 24/7. CRRT capable.",
        ),
        # Karnataka hospital — should NOT match Maharashtra queries
        _facility(
            "F003", name="Manipal Bangalore", state="Karnataka",
            facility_type="hospital", trust_score=0.88,
            specialties="Oncology",
            equipment="linear accelerator",
            combined_medical_evidence="Cancer hospital with chemotherapy",
        ),
        # Maharashtra clinic (not a hospital) — used to test facility_type relaxation
        _facility(
            "F004", name="Mumbai Diabetes Clinic", state="Maharashtra",
            facility_type="clinic", trust_score=0.65,
            specialties="Endocrinology",
            combined_medical_evidence="Outpatient diabetes management",
        ),
        # Maharashtra ICU hospital — low trust score (used for trust relaxation)
        _facility(
            "F005", name="Sketchy Care Centre", state="Maharashtra",
            facility_type="hospital", trust_score=0.35,
            specialties="ICU, Critical Care",
            equipment="ventilator",
            combined_medical_evidence="ICU available with intensive care unit support",
        ),
        # Tamil Nadu NICU — outside Maharashtra
        _facility(
            "F006", name="Chennai Children Hosp", state="Tamil Nadu",
            facility_type="hospital", trust_score=0.78,
            specialties="Paediatric, Neonatal",
            equipment="incubator, neonatal ventilator",
            combined_medical_evidence="NICU with phototherapy and surfactant therapy",
        ),
        # Maharashtra hospital with no clinical evidence — sanity row
        _facility(
            "F007", name="Plain Hospital", state="Maharashtra",
            facility_type="hospital", trust_score=0.55,
            combined_medical_evidence="General hospital",
        ),
    ])


# ---------------------------------------------------------------------------
# Schema / module surface
# ---------------------------------------------------------------------------

def test_local_candidate_defaults():
    c = LocalCandidate(facility_id="F001")
    assert c.facility_id == "F001"
    assert c.raw_record == {}
    assert c.matched_fields == []
    assert c.matched_capabilities == []
    assert c.local_relevance_score == 0.0
    assert c.relaxation_notes == []


def test_search_fields_constant_is_six_fields():
    assert SEARCH_FIELDS == [
        "specialties",
        "procedures",
        "equipment",
        "capabilities_raw",
        "evidence_summary",
        "combined_medical_evidence",
    ]


# ---------------------------------------------------------------------------
# Required scenarios from the spec
# ---------------------------------------------------------------------------

def test_icu_query_returns_candidates(fixture_df):
    intent = parse_query_intent("ICU hospital in Maharashtra")
    out = retrieve_local_candidates(fixture_df, intent)

    assert len(out) >= 1
    ids = [c.facility_id for c in out]
    # Apollo (F001) and Sketchy (F005) both have ICU evidence in Maharashtra.
    assert "F001" in ids
    assert "F005" in ids

    # ICU_CRITICAL_CARE must be reported on every ICU hit
    icu_hits = [c for c in out if c.facility_id in ("F001", "F005")]
    for c in icu_hits:
        assert "ICU_CRITICAL_CARE" in c.matched_capabilities
        assert c.local_relevance_score > 0
        assert c.relaxation_notes == []   # strict pass succeeded
        assert c.raw_record["facility_id"] == c.facility_id

    # Apollo should outrank Sketchy because it has more strong-evidence terms.
    apollo = next(c for c in out if c.facility_id == "F001")
    sketchy = next(c for c in out if c.facility_id == "F005")
    assert apollo.local_relevance_score >= sketchy.local_relevance_score


def test_dialysis_query_returns_candidates(fixture_df):
    intent = parse_query_intent("dialysis centre in Maharashtra")
    out = retrieve_local_candidates(fixture_df, intent)

    assert len(out) >= 1
    ids = [c.facility_id for c in out]
    assert "F002" in ids                              # Fortis Pune dialysis
    fortis = next(c for c in out if c.facility_id == "F002")
    assert "DIALYSIS_RENAL" in fortis.matched_capabilities
    # Hits across multiple of the 6 search fields
    assert "procedures" in fortis.matched_fields
    assert "equipment"  in fortis.matched_fields


def test_maharashtra_hospital_query_returns_only_hospitals(fixture_df):
    intent = parse_query_intent("hospitals in Maharashtra")
    out = retrieve_local_candidates(fixture_df, intent)

    assert len(out) >= 1
    for c in out:
        assert c.raw_record["state"] == "Maharashtra"
        assert c.raw_record["facility_type"] == "hospital"
    # The Mumbai clinic (F004) is in Maharashtra but is not a hospital — must be excluded.
    assert "F004" not in [c.facility_id for c in out]
    # The Bangalore hospital (F003) is in Karnataka — must be excluded.
    assert "F003" not in [c.facility_id for c in out]
    # Every Maharashtra hospital row should be present.
    assert {"F001", "F002", "F005", "F007"} <= {c.facility_id for c in out}
    for c in out:
        assert c.relaxation_notes == []


def test_fallback_records_relaxation_notes_for_trust_score(fixture_df):
    """
    A min_trust_score so high that no Maharashtra hospital qualifies must
    cause the trust-score filter to be relaxed and noted.
    """
    intent = parse_query_intent("ICU hospital in Maharashtra")
    intent.min_trust_score = 0.99   # nobody in fixture meets this

    out = retrieve_local_candidates(fixture_df, intent)

    assert len(out) >= 1
    note = out[0].relaxation_notes
    assert any("min_trust_score" in n for n in note)
    assert any("0.99" in n for n in note)
    assert all("facility_type" not in n for n in note)   # only trust was relaxed
    assert all("state" not in n for n in note)


def test_fallback_records_relaxation_notes_for_facility_type():
    """
    When no facility of the requested *type* exists in the requested state,
    the type filter must be relaxed and noted (state stays locked).
    """
    df = pd.DataFrame([
        _facility("F100", state="Maharashtra", facility_type="clinic",
                  trust_score=0.7, combined_medical_evidence="ICU available"),
        _facility("F101", state="Maharashtra", facility_type="clinic",
                  trust_score=0.6, combined_medical_evidence="intensive care unit"),
    ])
    intent = parse_query_intent("ICU hospital in Maharashtra")

    out = retrieve_local_candidates(df, intent)

    assert len(out) == 2
    for c in out:
        assert c.raw_record["state"] == "Maharashtra"
        assert any("facility_type" in n for n in c.relaxation_notes)
        assert any("hospital" in n for n in c.relaxation_notes)
    # State must NOT have been relaxed
    for c in out:
        assert all("state" not in n for n in c.relaxation_notes)


def test_fallback_records_both_relaxations_when_needed():
    """Trust relaxation runs first, then facility_type if still empty."""
    df = pd.DataFrame([
        _facility("F200", state="Maharashtra", facility_type="clinic",
                  trust_score=0.4,
                  combined_medical_evidence="ICU intensive care unit"),
    ])
    intent = parse_query_intent("ICU hospital in Maharashtra")
    intent.min_trust_score = 0.9

    out = retrieve_local_candidates(df, intent)

    assert len(out) == 1
    notes = out[0].relaxation_notes
    assert any("min_trust_score" in n for n in notes)
    assert any("facility_type"   in n for n in notes)
    assert all("state" not in n for n in notes)


# ---------------------------------------------------------------------------
# State filter behaviour
# ---------------------------------------------------------------------------

def test_state_filter_is_not_relaxed_by_default(fixture_df):
    """A query for a state with zero matches must return [] — never silently
    spill into other states."""
    intent = parse_query_intent("ICU hospital in Kerala")
    intent.state = "Kerala"   # ensure even if parser picked something else

    out = retrieve_local_candidates(fixture_df, intent)
    assert out == []


def test_state_filter_is_relaxed_when_explicitly_allowed(fixture_df):
    intent = parse_query_intent("ICU hospital in Kerala")
    intent.state = "Kerala"

    out = retrieve_local_candidates(
        fixture_df, intent, allow_state_relaxation=True,
    )

    assert len(out) >= 1
    notes = out[0].relaxation_notes
    assert any("state" in n for n in notes)
    assert any("Kerala" in n for n in notes)


# ---------------------------------------------------------------------------
# Ranking + pool limit
# ---------------------------------------------------------------------------

def test_ranking_is_score_then_trust_score_descending(fixture_df):
    intent = parse_query_intent("ICU hospital in Maharashtra")
    out = retrieve_local_candidates(fixture_df, intent)

    scores = [c.local_relevance_score for c in out]
    assert scores == sorted(scores, reverse=True)


def test_limit_pool_is_respected():
    rows = [
        _facility(
            f"F{i:04d}", state="Maharashtra", facility_type="hospital",
            trust_score=0.5 + (i * 0.001),
            combined_medical_evidence="ICU and intensive care unit available",
        )
        for i in range(50)
    ]
    df = pd.DataFrame(rows)
    intent = parse_query_intent("ICU hospital in Maharashtra")

    out = retrieve_local_candidates(df, intent, limit_pool=10)
    assert len(out) == 10


def test_empty_dataframe_returns_empty_list():
    intent = parse_query_intent("ICU hospital in Maharashtra")
    assert retrieve_local_candidates(pd.DataFrame(), intent) == []


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

def test_handles_missing_optional_columns():
    """The retriever must work against partial schemas — only `facility_id`
    is truly required."""
    df = pd.DataFrame([
        {"facility_id": "F300", "state": "Maharashtra",
         "combined_medical_evidence": "ICU and intensive care unit"},
        {"facility_id": "F301", "state": "Maharashtra",
         "combined_medical_evidence": "Outpatient services only"},
    ])
    intent = parse_query_intent("ICU hospital in Maharashtra")

    out = retrieve_local_candidates(df, intent)
    # facility_type column is missing → that filter is silently skipped.
    # min_trust_score is None on the intent → no trust filter.
    # Only the row with ICU evidence should score > 0; both pass the (no-op)
    # filter, but ranking puts F300 first.
    assert len(out) == 2
    assert out[0].facility_id == "F300"
    assert out[0].local_relevance_score > 0
    assert out[1].local_relevance_score == 0


def test_handles_nan_and_nullish_text_cells():
    df = pd.DataFrame([
        {"facility_id": "F400", "state": "Maharashtra",
         "facility_type": "hospital", "trust_score": 0.7,
         "combined_medical_evidence": float("nan"),
         "specialties": "None",
         "procedures": "null",
         "equipment": "[]",
         "capabilities_raw": "",
         "evidence_summary": "ICU intensive care unit"},
    ])
    intent = parse_query_intent("ICU hospital in Maharashtra")

    out = retrieve_local_candidates(df, intent)
    assert len(out) == 1
    # Hits must come ONLY from evidence_summary; the null-ish columns are skipped.
    assert "evidence_summary" in out[0].matched_fields
    assert "combined_medical_evidence" not in out[0].matched_fields


def test_no_capabilities_falls_back_to_query_tokens(fixture_df):
    """A free-form query with no taxonomy hit still scores against query tokens."""
    intent = AgentIntent(
        raw_query="cardiology cardiac monitor in Maharashtra",
        original_query="cardiology cardiac monitor in Maharashtra",
        normalized_query="cardiology cardiac monitor in maharashtra",
        capabilities_required=[],   # explicitly none
        state="Maharashtra",
    )

    out = retrieve_local_candidates(fixture_df, intent)
    # F001 (Apollo) has "Cardiology" + "cardiac monitor" — should score > 0.
    apollo = next((c for c in out if c.facility_id == "F001"), None)
    assert apollo is not None
    assert apollo.local_relevance_score > 0
    assert apollo.matched_capabilities == []  # no capability scoring path


def test_relaxation_notes_are_per_candidate_not_shared():
    """Notes must be on the candidate; mutating one list must not affect another."""
    df = pd.DataFrame([
        _facility("F500", state="Maharashtra", facility_type="clinic",
                  trust_score=0.7, combined_medical_evidence="ICU"),
        _facility("F501", state="Maharashtra", facility_type="clinic",
                  trust_score=0.6, combined_medical_evidence="ICU"),
    ])
    intent = parse_query_intent("ICU hospital in Maharashtra")

    out = retrieve_local_candidates(df, intent)
    assert len(out) == 2
    out[0].relaxation_notes.append("PROBE")
    assert "PROBE" not in out[1].relaxation_notes


# ---------------------------------------------------------------------------
# Backward-compat: legacy retrieve_local()
# ---------------------------------------------------------------------------

def _sample_df_legacy() -> pd.DataFrame:
    return pd.DataFrame([
        {"facility_id": "F001", "combined_medical_evidence": "ICU with 20 beds, ventilators available."},
        {"facility_id": "F002", "combined_medical_evidence": "Dialysis unit, 10 chairs."},
        {"facility_id": "F003", "combined_medical_evidence": "NICU, maternity ward."},
    ])


def test_legacy_retrieve_local_matches_keyword():
    df = _sample_df_legacy()
    result = retrieve_local("ICU", df)
    # "ICU" matches F001 ("ICU with 20 beds") and F003 ("NICU") via substring search
    assert len(result) == 2
    assert "F001" in result["facility_id"].values


def test_legacy_retrieve_local_no_match_returns_empty():
    df = _sample_df_legacy()
    result = retrieve_local("cardiac cathlab", df)
    assert len(result) == 0


def test_legacy_retrieve_local_top_k():
    df = _sample_df_legacy()
    result = retrieve_local("", df, top_k=2)
    assert len(result) <= 2
