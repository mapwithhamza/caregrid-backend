"""
Unit tests for `agent_core.evidence_citation`.

Two surfaces are exercised:
  1. `extract_evidence_snippets(record, requested_capabilities)` — pulls
     supporting `EvidenceSnippet` objects out of a facility record, one
     bundle per requested capability, classified by support level.
  2. `format_citations(snippets)` — legacy numbered-list renderer, kept
     for backward compatibility with the original Stage-1 stub tests.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_core.evidence_citation import (  # noqa: E402
    EVIDENCE_FIELDS_PRIORITY,
    EVIDENCE_SUPPORT_LEVELS,
    MAX_EXCERPT_LENGTH,
    MAX_SNIPPETS_PER_CAPABILITY,
    SUPPORT_CONTRADICTION,
    SUPPORT_MODERATE,
    SUPPORT_STRONG,
    SUPPORT_WEAK,
    extract_evidence_snippets,
    format_citations,
)
from agent_core.schemas import EvidenceSnippet  # noqa: E402


# ---------------------------------------------------------------------------
# Module surface / constants
# ---------------------------------------------------------------------------

def test_support_level_constants():
    assert SUPPORT_STRONG        == "strong"
    assert SUPPORT_MODERATE      == "moderate"
    assert SUPPORT_WEAK          == "weak"
    assert SUPPORT_CONTRADICTION == "contradiction"
    assert EVIDENCE_SUPPORT_LEVELS == [
        "strong", "moderate", "weak", "contradiction",
    ]


def test_evidence_fields_priority_is_six_fields():
    assert EVIDENCE_FIELDS_PRIORITY == [
        "equipment",
        "procedures",
        "specialties",
        "capabilities_raw",
        "evidence_summary",
        "combined_medical_evidence",
    ]


def test_max_snippets_per_capability_is_three():
    assert MAX_SNIPPETS_PER_CAPABILITY == 3


# ---------------------------------------------------------------------------
# Required spec scenarios
# ---------------------------------------------------------------------------

def test_icu_with_ventilator_returns_strong_evidence():
    """A `strong_evidence_keyword` for ICU (e.g. "ventilator") in any field
    must be classified as strong."""
    record = {
        "facility_id": "F001",
        "equipment": "ventilator, cardiac monitor, defibrillator",
        "combined_medical_evidence":
            "24-bed ICU with ventilators and arterial line monitoring. "
            "Trained intensivists available 24/7.",
    }
    out = extract_evidence_snippets(record, ["ICU_CRITICAL_CARE"])

    assert len(out) >= 1
    assert any(s.support_level == SUPPORT_STRONG for s in out)
    assert all(s.facility_id == "F001" for s in out)
    assert all(s.capability_id == "ICU_CRITICAL_CARE" for s in out)

    # The first snippet (highest-ranked) must be strong
    assert out[0].support_level == SUPPORT_STRONG
    # And must mention the ventilator term
    assert any("ventilator" in s.matched_terms for s in out)


def test_dialysis_machine_returns_strong_evidence():
    """`dialysis machine` is a strong_evidence_keyword for DIALYSIS_RENAL."""
    record = {
        "facility_id": "F002",
        "equipment": "dialysis machine, RO water plant",
        "combined_medical_evidence": "Hemodialysis available 24/7.",
    }
    out = extract_evidence_snippets(record, ["DIALYSIS_RENAL"])

    assert len(out) >= 1
    assert out[0].support_level == SUPPORT_STRONG
    assert any("dialysis machine" in s.matched_terms for s in out)


def test_oncology_with_only_cancer_text_returns_moderate_or_weak():
    """A regular keyword like "cancer" without strong-evidence terms must
    be moderate (specialties / capabilities_raw) or weak (broad text)."""
    record_specialty = {
        "facility_id": "F100",
        "specialties": "Oncology, Cancer Care",
    }
    out = extract_evidence_snippets(record_specialty, ["ONCOLOGY"])
    assert len(out) >= 1
    assert all(s.support_level in {SUPPORT_MODERATE, SUPPORT_WEAK} for s in out)
    assert out[0].support_level == SUPPORT_MODERATE   # specialties → moderate

    record_broad = {
        "facility_id": "F101",
        "combined_medical_evidence":
            "Cancer treatment available with experienced consultants.",
    }
    out2 = extract_evidence_snippets(record_broad, ["ONCOLOGY"])
    assert len(out2) >= 1
    assert all(s.support_level in {SUPPORT_MODERATE, SUPPORT_WEAK} for s in out2)
    assert out2[0].support_level == SUPPORT_WEAK     # combined_medical_evidence → weak


def test_no_evidence_returns_empty_list():
    record = {
        "facility_id": "F999",
        "specialties": "General Medicine",
        "combined_medical_evidence": "Outpatient consultation services only.",
    }
    out = extract_evidence_snippets(record, ["ICU_CRITICAL_CARE"])
    assert out == []


def test_long_evidence_returns_concise_snippets():
    """Long sentences get truncated to <= MAX_EXCERPT_LENGTH chars."""
    long_text = (
        "ICU available with comprehensive intensive care unit support, "
        "including 50 beds, 30 ventilators, advanced cardiac monitoring, "
        "central venous catheter access, arterial line monitoring, "
        "continuous EEG, full intensivist roster, respiratory therapy team, "
        "dedicated nephrology consult, multi-disciplinary rounds, "
        "ECMO capability, sedation protocols, infection control practices, "
        "family communication policies, and end-of-life care planning"
    )
    record = {
        "facility_id": "F500",
        "combined_medical_evidence": long_text,
    }
    out = extract_evidence_snippets(record, ["ICU_CRITICAL_CARE"])
    assert len(out) >= 1
    for s in out:
        assert len(s.excerpt) <= MAX_EXCERPT_LENGTH
    # Long-truncated excerpts end with the ellipsis
    assert any(s.excerpt.endswith("...") for s in out)


# ---------------------------------------------------------------------------
# Per-capability cap and ranking
# ---------------------------------------------------------------------------

def test_max_three_snippets_per_capability():
    """Evidence comes from many fields and many sentences — only 3 are kept."""
    record = {
        "facility_id": "F600",
        "equipment": "ventilator; cardiac monitor; defibrillator; infusion pump",
        "procedures": "mechanical ventilation; invasive monitoring",
        "specialties": "Critical Care; intensive care unit",
        "evidence_summary": "ICU with arterial line capability",
        "combined_medical_evidence":
            "ICU available. Vasopressor-ready. Critical care nurses on duty. "
            "MICU and SICU staffed 24/7.",
    }
    out = extract_evidence_snippets(record, ["ICU_CRITICAL_CARE"])
    assert len(out) == MAX_SNIPPETS_PER_CAPABILITY


def test_strong_snippets_outrank_weak():
    """Within a capability, snippets are ordered strong → moderate → weak."""
    record = {
        "facility_id": "F700",
        "equipment": "ventilator",
        "specialties": "Critical Care",
        "combined_medical_evidence": "Hospital with ICU services available.",
    }
    out = extract_evidence_snippets(record, ["ICU_CRITICAL_CARE"])
    levels = [s.support_level for s in out]
    rank = {SUPPORT_STRONG: 0, SUPPORT_MODERATE: 1, SUPPORT_WEAK: 2}
    assert [rank[l] for l in levels] == sorted(rank[l] for l in levels)


def test_field_priority_breaks_ties_within_a_level():
    """When two snippets share the same level, equipment beats procedures
    beats specialties etc."""
    record = {
        "facility_id": "F701",
        "equipment": "ventilator",                                # strong (strong term)
        "procedures": "mechanical ventilation",                   # strong (strong term)
        "combined_medical_evidence": "Hospital with ICU.",        # weak
    }
    out = extract_evidence_snippets(record, ["ICU_CRITICAL_CARE"])
    # Both equipment + procedures are strong; equipment must win the priority tie
    strong = [s for s in out if s.support_level == SUPPORT_STRONG]
    assert strong[0].source_field == "equipment"
    assert strong[1].source_field == "procedures"


def test_dedup_by_excerpt_text():
    """Identical excerpt text in two fields should be kept only once."""
    record = {
        "facility_id": "F702",
        "evidence_summary":         "ICU with ventilator",
        "combined_medical_evidence":"ICU with ventilator",   # exact dup
    }
    out = extract_evidence_snippets(record, ["ICU_CRITICAL_CARE"])
    excerpts = [s.excerpt.lower() for s in out]
    assert len(excerpts) == len(set(excerpts))


# ---------------------------------------------------------------------------
# Multiple capabilities
# ---------------------------------------------------------------------------

def test_multiple_capabilities_returns_per_capability_snippets():
    record = {
        "facility_id": "F800",
        "equipment": "ventilator, dialysis machine",
        "combined_medical_evidence":
            "ICU with intensive care unit. Hemodialysis available 24/7.",
    }
    out = extract_evidence_snippets(
        record, ["ICU_CRITICAL_CARE", "DIALYSIS_RENAL"],
    )
    cap_ids = {s.capability_id for s in out}
    assert cap_ids == {"ICU_CRITICAL_CARE", "DIALYSIS_RENAL"}
    # Order: ICU snippets must come before dialysis snippets (input order preserved)
    icu_first  = next(i for i, s in enumerate(out) if s.capability_id == "ICU_CRITICAL_CARE")
    dial_first = next(i for i, s in enumerate(out) if s.capability_id == "DIALYSIS_RENAL")
    assert icu_first < dial_first


def test_unknown_capability_id_is_silently_skipped():
    record = {
        "facility_id": "F900",
        "equipment": "ventilator",
        "combined_medical_evidence": "ICU available",
    }
    out = extract_evidence_snippets(
        record, ["NOT_A_REAL_CAPABILITY", "ICU_CRITICAL_CARE"],
    )
    assert all(s.capability_id == "ICU_CRITICAL_CARE" for s in out)
    assert len(out) >= 1


# ---------------------------------------------------------------------------
# Snippet schema fields
# ---------------------------------------------------------------------------

def test_snippet_has_all_expected_fields():
    record = {"facility_id": "F950", "equipment": "ventilator"}
    out = extract_evidence_snippets(record, ["ICU_CRITICAL_CARE"])
    assert len(out) == 1
    s = out[0]
    assert isinstance(s, EvidenceSnippet)
    assert s.facility_id == "F950"
    assert s.source_field == "equipment"
    assert s.support_level == SUPPORT_STRONG
    assert s.capability_id == "ICU_CRITICAL_CARE"
    assert "ventilator" in s.matched_terms
    assert s.relevance_score == 1.0   # strong → 1.0


def test_relevance_score_matches_support_level():
    record = {
        "facility_id": "F951",
        "equipment": "ventilator",                 # strong
        "specialties": "Critical Care",            # moderate
        "combined_medical_evidence": "ICU available.",  # weak
    }
    out = extract_evidence_snippets(record, ["ICU_CRITICAL_CARE"])
    by_level = {s.support_level: s for s in out}
    assert by_level[SUPPORT_STRONG].relevance_score   == 1.0
    if SUPPORT_MODERATE in by_level:
        assert by_level[SUPPORT_MODERATE].relevance_score == 0.6
    if SUPPORT_WEAK in by_level:
        assert by_level[SUPPORT_WEAK].relevance_score     == 0.3


# ---------------------------------------------------------------------------
# Edge cases / robustness
# ---------------------------------------------------------------------------

def test_empty_capability_list_returns_empty():
    record = {"facility_id": "F100", "equipment": "ventilator"}
    assert extract_evidence_snippets(record, []) == []


def test_empty_record_returns_empty():
    assert extract_evidence_snippets({}, ["ICU_CRITICAL_CARE"]) == []


def test_handles_nan_and_nullish_text_cells():
    record = {
        "facility_id": "F110",
        "equipment": float("nan"),
        "procedures": "None",
        "specialties": "null",
        "capabilities_raw": "[]",
        "evidence_summary": "n/a",
        "combined_medical_evidence": "Hospital with ICU and ventilator.",
    }
    out = extract_evidence_snippets(record, ["ICU_CRITICAL_CARE"])
    assert len(out) >= 1
    # Only combined_medical_evidence has real content; matches must come from it.
    sources = {s.source_field for s in out}
    assert sources == {"combined_medical_evidence"}


def test_unwraps_list_like_strings():
    """Inputs like "['ICU', 'critical care']" must be unwrapped before splitting."""
    record = {
        "facility_id": "F120",
        "specialties": "['Critical Care', 'Oncology']",
    }
    out = extract_evidence_snippets(record, ["ICU_CRITICAL_CARE"])
    assert len(out) >= 1
    assert "critical care" in out[0].matched_terms


def test_segment_splitter_handles_pipes_and_newlines():
    """vector_text uses ' | ' separators; combined_medical_evidence uses '\\n'."""
    record = {
        "facility_id": "F130",
        "combined_medical_evidence":
            "Apollo Mumbai\n"
            "ICU with 24 beds | Ventilators available\n"
            "Routine outpatient care also available",
    }
    out = extract_evidence_snippets(record, ["ICU_CRITICAL_CARE"])
    excerpts = [s.excerpt for s in out]
    # The "Routine outpatient care" segment must NOT be returned (no ICU terms).
    assert all("Routine outpatient" not in e for e in excerpts)
    # At least one ICU/ventilator segment is captured.
    assert any("ICU" in e or "Ventilator" in e for e in excerpts)


def test_dental_alone_does_not_trigger_dentist_capability_logic():
    """Sanity: extraction is purely capability-driven; if the caller doesn't
    request a capability, no snippets come back even if related terms appear."""
    record = {"facility_id": "F140", "specialties": "Dental, Orthodontics"}
    # Caller asks for ICU — there's nothing about ICU here.
    assert extract_evidence_snippets(record, ["ICU_CRITICAL_CARE"]) == []


# ---------------------------------------------------------------------------
# Backward-compat: format_citations()
# ---------------------------------------------------------------------------

def test_format_citations_empty():
    result = format_citations([])
    assert result == ""


def test_format_citations_single_block():
    block = EvidenceSnippet(facility_id="F001", excerpt="Has ICU with 20 beds.")
    result = format_citations([block])
    assert "F001" in result
    assert "[1]" in result


def test_format_citations_multiple_blocks():
    blocks = [
        EvidenceSnippet(facility_id="F001", excerpt="ICU available."),
        EvidenceSnippet(facility_id="F002", excerpt="Dialysis unit operational."),
    ]
    result = format_citations(blocks)
    assert "[1]" in result
    assert "[2]" in result
