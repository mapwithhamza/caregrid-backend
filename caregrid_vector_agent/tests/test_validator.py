"""Tests for agent_core.validator (Stage 11)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_core.contradiction_rules import (
    check_contradictions,
    find_contradictions,
    get_rule,
)
from agent_core.schemas import AgentResponse, EvidenceSnippet, ValidationFinding
from agent_core.validator import (
    FINDING_CONTRADICTION,
    FINDING_MISSING_EVIDENCE,
    FINDING_SUPPORTED,
    FINDING_WEAK_EVIDENCE,
    IMPACT_DO_NOT_RECOMMEND,
    IMPACT_DOWNGRADE_TO_VERIFY_BEFORE_USE,
    IMPACT_FLAG_FOR_REVIEW,
    IMPACT_NONE,
    SEVERITY_HIGH,
    SEVERITY_INFO,
    SEVERITY_MEDIUM,
    VALIDATION_RULES,
    validate_candidate,
    validate_response,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _facility(**overrides):
    base = {
        "facility_id": "F001",
        "name": "Sample Hospital",
        "specialties": "",
        "procedures": "",
        "equipment": "",
        "capabilities_raw": "",
        "evidence_summary": "",
        "combined_medical_evidence": "",
    }
    base.update(overrides)
    return base


def _strong_snippet(facility_id, capability_id, excerpt, source_field="equipment"):
    return EvidenceSnippet(
        facility_id=facility_id,
        excerpt=excerpt,
        source_field=source_field,
        support_level="strong",
        capability_id=capability_id,
        matched_terms=[],
    )


def _weak_snippet(facility_id, capability_id, excerpt, source_field="evidence_summary"):
    return EvidenceSnippet(
        facility_id=facility_id,
        excerpt=excerpt,
        source_field=source_field,
        support_level="weak",
        capability_id=capability_id,
        matched_terms=[],
    )


# ---------------------------------------------------------------------------
# Required scenarios from Prompt 11
# ---------------------------------------------------------------------------

def test_icu_claim_without_equipment_triggers_high_severity():
    record = _facility(
        facility_id="F001",
        name="Tiny Clinic",
        specialties="general medicine",
        evidence_summary="Outpatient consultation only.",
    )
    findings = validate_candidate(record, ["ICU_CRITICAL_CARE"], evidence_snippets=[])

    assert len(findings) == 1
    f = findings[0]
    assert f.facility_id == "F001"
    assert f.capability == "ICU_CRITICAL_CARE"
    assert f.finding_type == FINDING_MISSING_EVIDENCE
    assert f.severity == SEVERITY_HIGH
    assert f.recommendation_impact == IMPACT_DO_NOT_RECOMMEND
    assert f.evidence_used == []
    # Missing evidence list should mention some of the required ICU terms.
    joined = " ".join(f.missing_evidence).lower()
    assert any(t in joined for t in ["ventilator", "intensive care", "icu"])


def test_surgery_without_ot_or_anesthesia_triggers_finding():
    record = _facility(
        facility_id="F002",
        name="Generic Hospital",
        specialties="dermatology, general practice",
        evidence_summary="Consults and minor wound care only.",
    )
    findings = validate_candidate(record, ["SURGERY"], evidence_snippets=[])

    assert len(findings) == 1
    f = findings[0]
    assert f.capability == "SURGERY"
    assert f.finding_type == FINDING_MISSING_EVIDENCE
    assert f.severity == SEVERITY_HIGH
    assert f.recommendation_impact == IMPACT_DO_NOT_RECOMMEND
    joined = " ".join(f.missing_evidence).lower()
    assert "operation theatre" in joined or "anaesthesia" in joined or "surgeon" in joined


def test_dialysis_with_machine_passes_support():
    record = _facility(
        facility_id="F003",
        name="Renal Care Hospital",
        specialties="nephrology, internal medicine",
        equipment="dialysis machine, RO water plant",
        procedures="hemodialysis, peritoneal dialysis",
        combined_medical_evidence=(
            "Equipment: dialysis machine and RO water plant. "
            "Procedures: hemodialysis."
        ),
    )
    snippets = [
        _strong_snippet(
            "F003",
            "DIALYSIS_RENAL",
            "dialysis machine, RO water plant",
            source_field="equipment",
        ),
    ]
    findings = validate_candidate(record, ["DIALYSIS_RENAL"], snippets)

    assert len(findings) == 1
    f = findings[0]
    assert f.capability == "DIALYSIS_RENAL"
    assert f.finding_type == FINDING_SUPPORTED
    assert f.severity == SEVERITY_INFO
    assert f.recommendation_impact == IMPACT_NONE
    assert f.evidence_used and "dialysis machine" in f.evidence_used[0].lower()
    assert f.missing_evidence == []


def test_emergency_with_ambulance_and_24x7_passes_support():
    record = _facility(
        facility_id="F004",
        name="City Multispecialty",
        specialties="emergency medicine, trauma",
        equipment="ambulance, oxygen cylinders, defibrillator",
        capabilities_raw="24/7 emergency department, casualty, trauma bay",
        combined_medical_evidence=(
            "24/7 emergency department with ambulance and trauma bay. "
            "Casualty with resuscitation capability."
        ),
    )
    snippets = [
        _strong_snippet(
            "F004",
            "EMERGENCY_TRAUMA",
            "24/7 emergency department with ambulance and trauma bay.",
            source_field="capabilities_raw",
        ),
    ]
    findings = validate_candidate(record, ["EMERGENCY_TRAUMA"], snippets)

    assert len(findings) == 1
    f = findings[0]
    assert f.capability == "EMERGENCY_TRAUMA"
    assert f.finding_type == FINDING_SUPPORTED
    assert f.severity == SEVERITY_INFO
    assert f.recommendation_impact == IMPACT_NONE


# ---------------------------------------------------------------------------
# Weak / moderate evidence path
# ---------------------------------------------------------------------------

def test_oncology_with_only_weak_text_returns_medium_severity():
    record = _facility(
        facility_id="F005",
        name="District General",
        evidence_summary="Provides cancer screening and referrals.",
    )
    snippets = [
        _weak_snippet(
            "F005",
            "ONCOLOGY",
            "Provides cancer screening and referrals.",
            source_field="evidence_summary",
        ),
    ]
    findings = validate_candidate(record, ["ONCOLOGY"], snippets)

    assert len(findings) == 1
    f = findings[0]
    assert f.finding_type == FINDING_WEAK_EVIDENCE
    assert f.severity == SEVERITY_MEDIUM
    assert f.recommendation_impact == IMPACT_DOWNGRADE_TO_VERIFY_BEFORE_USE
    assert f.evidence_used


def test_terms_present_but_no_snippets_yields_weak_finding():
    """Record contains required terms but no snippets were extracted —
    treated as weak/moderate, not as missing entirely."""
    record = _facility(
        facility_id="F006",
        equipment="ventilator, ICU bed, cardiac monitor",
    )
    findings = validate_candidate(record, ["ICU_CRITICAL_CARE"], evidence_snippets=[])

    assert len(findings) == 1
    f = findings[0]
    assert f.finding_type == FINDING_WEAK_EVIDENCE
    assert f.severity == SEVERITY_MEDIUM
    assert f.recommendation_impact == IMPACT_DOWNGRADE_TO_VERIFY_BEFORE_USE
    assert f.evidence_used == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_requested_capabilities_returns_empty():
    record = _facility(facility_id="F007")
    assert validate_candidate(record, [], []) == []


def test_unknown_capability_is_silently_skipped():
    record = _facility(facility_id="F008")
    findings = validate_candidate(record, ["NOT_A_REAL_CAPABILITY"], [])
    assert findings == []


def test_empty_record_returns_empty_findings():
    assert validate_candidate({}, ["ICU_CRITICAL_CARE"], []) == []


def test_neonatal_with_incubator_passes():
    record = _facility(
        facility_id="F009",
        equipment="incubator, neonatal ventilator, warmer",
        specialties="neonatology, paediatrics",
        capabilities_raw="NICU bed, neonatologist on call",
    )
    snippets = [
        _strong_snippet(
            "F009",
            "NEONATAL_PEDIATRIC",
            "incubator, neonatal ventilator, warmer",
            source_field="equipment",
        )
    ]
    findings = validate_candidate(record, ["NEONATAL_PEDIATRIC"], snippets)
    assert len(findings) == 1
    assert findings[0].finding_type == FINDING_SUPPORTED


def test_multiple_capabilities_produce_one_finding_each():
    record = _facility(
        facility_id="F010",
        equipment="dialysis machine",
        capabilities_raw="hemodialysis available",
    )
    snippets = [
        _strong_snippet("F010", "DIALYSIS_RENAL", "dialysis machine", source_field="equipment"),
    ]
    findings = validate_candidate(
        record,
        ["DIALYSIS_RENAL", "ICU_CRITICAL_CARE"],
        snippets,
    )
    assert len(findings) == 2
    by_cap = {f.capability: f for f in findings}
    assert by_cap["DIALYSIS_RENAL"].finding_type == FINDING_SUPPORTED
    assert by_cap["ICU_CRITICAL_CARE"].finding_type == FINDING_MISSING_EVIDENCE


def test_duplicate_requested_capabilities_are_deduped():
    record = _facility(facility_id="F011")
    findings = validate_candidate(
        record,
        ["ICU_CRITICAL_CARE", "ICU_CRITICAL_CARE", "ICU_CRITICAL_CARE"],
        [],
    )
    assert len(findings) == 1


def test_short_token_ot_word_boundary_matching():
    """Bare 'OT' should match operation-theatre context but not random words like 'rotor'."""
    bad_record = _facility(
        facility_id="F012",
        evidence_summary="Maintenance of MRI rotor and elevator motor.",
    )
    findings = validate_candidate(bad_record, ["SURGERY"], [])
    assert findings[0].finding_type == FINDING_MISSING_EVIDENCE

    good_record = _facility(
        facility_id="F013",
        equipment="modular OT, anaesthesia machine",
        capabilities_raw="OT available 24x7",
    )
    findings = validate_candidate(good_record, ["SURGERY"], [])
    # Terms found but no snippets → weak evidence path.
    assert findings[0].finding_type == FINDING_WEAK_EVIDENCE


def test_validation_finding_has_all_fields():
    record = _facility(facility_id="F014")
    findings = validate_candidate(record, ["ICU_CRITICAL_CARE"], [])
    f = findings[0]
    assert isinstance(f, ValidationFinding)
    assert f.facility_id == "F014"
    assert f.capability == "ICU_CRITICAL_CARE"
    assert f.finding_type
    assert f.severity
    assert f.message
    assert isinstance(f.evidence_used, list)
    assert isinstance(f.missing_evidence, list)
    assert f.recommendation_impact in {
        IMPACT_NONE,
        IMPACT_DOWNGRADE_TO_VERIFY_BEFORE_USE,
        IMPACT_DO_NOT_RECOMMEND,
        IMPACT_FLAG_FOR_REVIEW,
    }


def test_validation_rules_cover_six_required_capabilities():
    expected = {
        "ICU_CRITICAL_CARE", "SURGERY", "DIALYSIS_RENAL",
        "ONCOLOGY", "EMERGENCY_TRAUMA", "NEONATAL_PEDIATRIC",
    }
    assert set(VALIDATION_RULES.keys()) == expected
    for cap_id, rule in VALIDATION_RULES.items():
        assert rule["rule_id"]
        assert rule["display_name"]
        assert isinstance(rule["required_evidence_terms"], list)
        assert len(rule["required_evidence_terms"]) >= 5


def test_strong_snippet_outranks_weak_snippet():
    """If both strong and weak snippets exist for a capability,
    the finding should be 'supported', not 'weak_evidence'."""
    record = _facility(
        facility_id="F015",
        equipment="dialysis machine",
    )
    snippets = [
        _weak_snippet("F015", "DIALYSIS_RENAL", "vague mention"),
        _strong_snippet("F015", "DIALYSIS_RENAL", "dialysis machine", source_field="equipment"),
    ]
    findings = validate_candidate(record, ["DIALYSIS_RENAL"], snippets)
    assert findings[0].finding_type == FINDING_SUPPORTED
    assert "dialysis machine" in findings[0].evidence_used[0].lower()


def test_nan_and_null_record_fields_are_tolerated():
    import math
    record = _facility(
        facility_id="F016",
        equipment=float("nan"),
        evidence_summary=None,
        capabilities_raw="None",
    )
    findings = validate_candidate(record, ["ICU_CRITICAL_CARE"], [])
    assert len(findings) == 1
    assert findings[0].finding_type == FINDING_MISSING_EVIDENCE


# ---------------------------------------------------------------------------
# Contradiction tests
# ---------------------------------------------------------------------------

def test_high_score_low_trust_category_is_contradiction():
    record = _facility(
        facility_id="F100",
        trust_score=0.9,
        trust_category="High Risk / Insufficient Evidence",
    )
    findings = validate_candidate(record, [], [])
    assert any(
        f.finding_type == FINDING_CONTRADICTION
        and f.rule == "CR_HIGH_SCORE_LOW_TRUST_CATEGORY"
        for f in findings
    )
    contradiction = next(f for f in findings if f.finding_type == FINDING_CONTRADICTION)
    assert contradiction.severity == SEVERITY_HIGH
    assert contradiction.recommendation_impact == IMPACT_FLAG_FOR_REVIEW


def test_ready_but_low_score_is_contradiction():
    record = _facility(
        facility_id="F101",
        trust_score=0.2,
        trust_category="Moderate Trust / Verify Before Use",
        recommendation_readiness="Ready for recommendation",
    )
    findings = validate_candidate(record, [], [])
    contradictions = [f for f in findings if f.finding_type == FINDING_CONTRADICTION]
    assert any(c.rule == "CR_READY_BUT_LOW_SCORE" for c in contradictions)


def test_contradictions_appear_after_capability_findings():
    record = _facility(
        facility_id="F102",
        trust_score=0.95,
        trust_category="Low Trust / Needs Human Verification",
    )
    findings = validate_candidate(record, ["ICU_CRITICAL_CARE"], [])
    # First finding: capability. Last finding(s): contradictions.
    assert findings[0].finding_type == FINDING_MISSING_EVIDENCE
    assert findings[-1].finding_type == FINDING_CONTRADICTION


def test_no_contradiction_for_clean_record():
    record = _facility(
        facility_id="F103",
        trust_score=0.85,
        trust_category="High Trust / Evidence Supported",
        recommendation_readiness="Ready for recommendation",
    )
    findings = validate_candidate(record, [], [])
    assert findings == []


def test_check_contradictions_returns_string_ids():
    record = _facility(
        facility_id="F104",
        trust_score=0.95,
        trust_category="High Risk / Insufficient Evidence",
    )
    ids = check_contradictions(record)
    assert isinstance(ids, list)
    assert all(isinstance(i, str) for i in ids)
    assert "CR_HIGH_SCORE_LOW_TRUST_CATEGORY" in ids


def test_find_contradictions_returns_dicts_with_severity():
    record = _facility(
        facility_id="F105",
        trust_score=0.3,
        trust_category="High Trust / Evidence Supported",
    )
    results = find_contradictions(record)
    assert any(r["id"] == "CR_LOW_SCORE_HIGH_TRUST_CATEGORY" for r in results)
    for r in results:
        assert "id" in r and "description" in r and "severity" in r


def test_get_rule_returns_rule_or_none():
    rule = get_rule("CR_READY_BUT_LOW_SCORE")
    assert rule is not None
    assert "description" in rule
    assert get_rule("DOES_NOT_EXIST") is None


def test_contradictions_safe_on_empty_record():
    assert find_contradictions({}) == []
    assert check_contradictions({}) == []


# ---------------------------------------------------------------------------
# Backward compatibility: validate_response()
# ---------------------------------------------------------------------------

def test_validate_empty_response_has_warnings():
    response = AgentResponse()
    warnings = validate_response(response)
    assert len(warnings) > 0


def test_validate_complete_response_no_warnings():
    response = AgentResponse(
        evidence=[EvidenceSnippet(facility_id="F001", excerpt="ICU available.")],
        reasoning="Matched ICU capability.",
        safety_note="Verify with facility directly before admission.",
    )
    warnings = validate_response(response)
    assert len(warnings) == 0
