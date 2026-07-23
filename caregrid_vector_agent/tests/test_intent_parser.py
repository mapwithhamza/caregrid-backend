import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agent_core.intent_parser import parse_intent, parse_query_intent
from agent_core.schemas import AgentIntent


# ===========================================================================
# Backward-compat: parse_intent() must still work exactly as before
# ===========================================================================

def test_parse_intent_returns_agent_intent():
    result = parse_intent("Find ICU hospitals in Mumbai")
    assert result.raw_query == "Find ICU hospitals in Mumbai"


def test_parse_intent_detects_icu():
    result = parse_intent("ICU beds available in Chennai")
    assert "ICU_CRITICAL_CARE" in result.capabilities_required


def test_parse_intent_detects_dialysis():
    result = parse_intent("dialysis centres in Delhi")
    assert "DIALYSIS_RENAL" in result.capabilities_required


def test_parse_intent_detects_emergency():
    result = parse_intent("emergency and trauma care in Hyderabad")
    assert "EMERGENCY_TRAUMA" in result.capabilities_required


def test_parse_intent_detects_neonatal():
    result = parse_intent("NICU facilities for newborns in Bangalore")
    assert "NEONATAL_PEDIATRIC" in result.capabilities_required


def test_parse_intent_detects_oncology():
    result = parse_intent("cancer chemotherapy hospitals in Pune")
    assert "ONCOLOGY" in result.capabilities_required


def test_parse_intent_multiple_capabilities():
    result = parse_intent("ICU with dialysis and blood bank in Delhi")
    caps = result.capabilities_required
    assert "ICU_CRITICAL_CARE" in caps
    assert "DIALYSIS_RENAL" in caps
    assert "BLOOD_BANK" in caps


def test_parse_intent_empty_query():
    result = parse_intent("")
    assert result.raw_query == ""
    assert result.capabilities_required == []


# ===========================================================================
# parse_query_intent() — return type and field population
# ===========================================================================

def test_parse_query_intent_returns_agent_intent():
    intent = parse_query_intent("Find ICU hospitals in Mumbai")
    assert isinstance(intent, AgentIntent)


def test_original_query_preserved():
    q = "  Find ICU hospitals in Mumbai  "
    intent = parse_query_intent(q)
    assert intent.original_query == q


def test_normalized_query_lowercase_stripped():
    intent = parse_query_intent("  ICU Hospitals in DELHI  ")
    assert intent.normalized_query == "icu hospitals in delhi"


def test_normalized_query_collapses_whitespace():
    intent = parse_query_intent("dialysis  centers   in   Delhi")
    assert "  " not in intent.normalized_query


# ===========================================================================
# State detection — all spec scenarios
# ===========================================================================

@pytest.mark.parametrize("query,expected_state", [
    ("trusted ICU hospitals in Bihar", "Bihar"),
    ("emergency hospitals in Maharashtra", "Maharashtra"),
    ("dialysis centers in Uttar Pradesh", "Uttar Pradesh"),
    ("oncology care in Gujarat", "Gujarat"),
    ("maternity hospital in Tamil Nadu", "Tamil Nadu"),
    ("diagnostics centers in Delhi", "Delhi"),
])
def test_state_detection(query, expected_state):
    intent = parse_query_intent(query)
    assert intent.state == expected_state, (
        f"Expected state '{expected_state}' in: {query!r}, got: {intent.state!r}"
    )


def test_state_none_when_absent():
    intent = parse_query_intent("ICU hospitals with dialysis")
    assert intent.state is None


# ===========================================================================
# City detection
# ===========================================================================

def test_city_detected_mumbai():
    intent = parse_query_intent("Find ICU hospitals in Mumbai")
    assert intent.city == "Mumbai"


def test_city_detected_bangalore():
    intent = parse_query_intent("NICU facilities in Bangalore")
    assert intent.city == "Bangalore"


def test_city_none_when_only_state():
    intent = parse_query_intent("dialysis centers in Uttar Pradesh")
    assert intent.city is None


def test_location_prefers_city_over_state():
    intent = parse_query_intent("ICU hospitals in Mumbai, Maharashtra")
    assert intent.location == "Mumbai"


def test_location_falls_back_to_state():
    intent = parse_query_intent("ICU hospitals in Bihar")
    assert intent.location == "Bihar"


# ===========================================================================
# Trust preference
# ===========================================================================

def test_trust_preferred_trusted_keyword():
    intent = parse_query_intent("trusted ICU hospitals in Bihar")
    assert intent.trust_preference == "trusted"


def test_trust_high_trust_phrase():
    intent = parse_query_intent("ICU hospitals in Bihar with high trust score")
    assert intent.trust_preference == "trusted"


def test_trust_reliable():
    intent = parse_query_intent("reliable dialysis centers in Maharashtra")
    assert intent.trust_preference == "trusted"


def test_trust_verification_ok():
    intent = parse_query_intent("dialysis centers in Delhi, verify before use")
    assert intent.trust_preference == "verification_ok"


def test_trust_unspecified():
    intent = parse_query_intent("dialysis centers in Uttar Pradesh")
    assert intent.trust_preference == "unspecified"


# ===========================================================================
# Urgency
# ===========================================================================

def test_urgency_emergency():
    intent = parse_query_intent("emergency hospitals in Maharashtra")
    assert intent.urgency == "emergency"


def test_urgency_urgent_keyword():
    intent = parse_query_intent("urgent dialysis centre in Pune needed today")
    assert intent.urgency in ("urgent", "emergency")


def test_urgency_routine():
    intent = parse_query_intent("routine dialysis centers in Uttar Pradesh")
    assert intent.urgency == "routine"


def test_urgency_unspecified():
    intent = parse_query_intent("oncology care in Gujarat")
    assert intent.urgency == "unspecified"


def test_urgency_emergency_also_detects_capability():
    intent = parse_query_intent("emergency hospitals in Maharashtra")
    assert intent.urgency == "emergency"
    assert "EMERGENCY_TRAUMA" in intent.capabilities_required


# ===========================================================================
# Facility type
# ===========================================================================

def test_facility_type_hospital_singular():
    intent = parse_query_intent("maternity hospital in Tamil Nadu")
    assert intent.facility_type == "hospital"


def test_facility_type_hospital_plural():
    intent = parse_query_intent("trusted ICU hospitals in Bihar")
    assert intent.facility_type == "hospital"


def test_facility_type_clinic():
    intent = parse_query_intent("dialysis clinic in Chennai")
    assert intent.facility_type == "clinic"


def test_facility_type_doctor():
    intent = parse_query_intent("find a doctor in Hyderabad")
    assert intent.facility_type == "doctor"


def test_facility_type_pharmacy():
    intent = parse_query_intent("pharmacy in Mumbai")
    assert intent.facility_type == "pharmacy"


def test_facility_type_dentist_keyword():
    intent = parse_query_intent("find a dentist in Mumbai")
    assert intent.facility_type == "dentist"


def test_facility_type_dental_alone_is_not_dentist():
    """'dental' without 'dentist' is a specialty term, not a facility type."""
    intent = parse_query_intent("dental care services in Pune")
    assert intent.facility_type is None


def test_facility_type_dental_clinic_is_clinic():
    """'dental clinic' should yield clinic, not dentist."""
    intent = parse_query_intent("dental clinic in Chennai")
    assert intent.facility_type == "clinic"


def test_facility_type_none_for_centers():
    """'centers'/'centres' are not in the recognised facility-type list."""
    intent = parse_query_intent("diagnostics centers in Delhi")
    assert intent.facility_type is None


# ===========================================================================
# Capabilities — all spec scenarios
# ===========================================================================

@pytest.mark.parametrize("query,expected_cap", [
    ("trusted ICU hospitals in Bihar", "ICU_CRITICAL_CARE"),
    ("emergency hospitals in Maharashtra", "EMERGENCY_TRAUMA"),
    ("dialysis centers in Uttar Pradesh", "DIALYSIS_RENAL"),
    ("oncology care in Gujarat", "ONCOLOGY"),
    ("maternity hospital in Tamil Nadu", "MATERNAL_CARE"),
    ("diagnostics centers in Delhi", "DIAGNOSTICS"),
])
def test_capability_detected(query, expected_cap):
    intent = parse_query_intent(query)
    assert expected_cap in intent.capabilities_required, (
        f"Expected '{expected_cap}' in: {query!r}, got: {intent.capabilities_required}"
    )


# ===========================================================================
# Proximity
# ===========================================================================

def test_proximity_near_me():
    intent = parse_query_intent("nearest dialysis center near me in Mumbai")
    assert intent.proximity_requested is True


def test_proximity_nearest():
    intent = parse_query_intent("nearest ICU hospital in Delhi")
    assert intent.proximity_requested is True


def test_proximity_not_requested():
    intent = parse_query_intent("dialysis centers in Uttar Pradesh")
    assert intent.proximity_requested is False


# ===========================================================================
# Web verification and vector search flags
# ===========================================================================

def test_web_verification_requested():
    intent = parse_query_intent("verify online ICU hospitals in Delhi")
    assert intent.web_verification_requested is True


def test_web_verification_not_requested():
    intent = parse_query_intent("ICU hospitals in Bihar")
    assert intent.web_verification_requested is False


def test_vector_search_requested():
    intent = parse_query_intent("semantic search dialysis centers in Maharashtra")
    assert intent.vector_search_requested is True


def test_vector_search_not_requested():
    intent = parse_query_intent("dialysis centers in Uttar Pradesh")
    assert intent.vector_search_requested is False


# ===========================================================================
# Min trust score extraction
# ===========================================================================

def test_min_trust_score_extracted():
    intent = parse_query_intent("NICU facilities with trust_score above 0.8")
    assert intent.min_trust_score == 0.8


def test_min_trust_score_none_when_absent():
    intent = parse_query_intent("ICU hospitals in Bihar")
    assert intent.min_trust_score is None


# ===========================================================================
# known_states parameter
# ===========================================================================

def test_known_states_restricts_detection():
    intent = parse_query_intent("ICU in Maharashtra", known_states=["Bihar", "Gujarat"])
    assert intent.state is None


def test_known_states_detects_when_present():
    intent = parse_query_intent("ICU in Gujarat", known_states=["Bihar", "Gujarat"])
    assert intent.state == "Gujarat"


# ===========================================================================
# known_facility_types parameter
# ===========================================================================

def test_known_facility_types_restricts_detection():
    intent = parse_query_intent("ICU hospital in Bihar", known_facility_types=["clinic"])
    assert intent.facility_type is None


def test_known_facility_types_detects_when_present():
    intent = parse_query_intent("ICU hospital in Bihar", known_facility_types=["hospital", "clinic"])
    assert intent.facility_type == "hospital"


# ===========================================================================
# Empty / edge cases
# ===========================================================================

def test_empty_query_all_defaults():
    intent = parse_query_intent("")
    assert intent.original_query == ""
    assert intent.normalized_query == ""
    assert intent.capabilities_required == []
    assert intent.state is None
    assert intent.city is None
    assert intent.facility_type is None
    assert intent.trust_preference == "unspecified"
    assert intent.urgency == "unspecified"
    assert intent.proximity_requested is False
    assert intent.web_verification_requested is False
    assert intent.vector_search_requested is False
    assert intent.min_trust_score is None


def test_whitespace_only_query():
    intent = parse_query_intent("   ")
    assert intent.normalized_query == ""
    assert intent.capabilities_required == []
