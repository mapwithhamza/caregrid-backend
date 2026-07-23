from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


def clean_nan(value: Any) -> Any:
    """Convert pandas missing scalar values into JSON-safe None."""
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return value

    return value


def clean_pin_code(value: Any) -> Optional[str]:
    """Normalize API PIN code display without modifying the source dataframe."""
    cleaned_value = clean_nan(value)
    if cleaned_value is None:
        return None

    pin_code = str(cleaned_value).strip()
    if not pin_code:
        return None

    if pin_code.endswith(".0"):
        candidate = pin_code[:-2]
        if candidate.isdigit() and len(candidate) == 6:
            return candidate

    try:
        numeric_value = float(pin_code)
    except ValueError:
        return pin_code

    if numeric_value.is_integer():
        candidate = str(int(numeric_value))
        if len(candidate) == 6:
            return candidate

    return pin_code


class CareGridModel(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)


class FacilityListItem(CareGridModel):
    facility_id: str
    name: str
    facility_type: Optional[str] = None
    city: Optional[str] = None
    state: str
    pin_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    trust_score: Optional[float] = None
    trust_category: str
    recommendation_readiness: str
    specialties: Optional[str] = None
    evidence_summary: Optional[str] = None
    flag_icu_claim_without_equipment: Optional[bool] = None
    flag_surgery_claim_without_support: Optional[bool] = None
    flag_dialysis_claim_without_machine: Optional[bool] = None
    flag_oncology_claim_without_support: Optional[bool] = None


class FacilityDetail(FacilityListItem):
    phone: Optional[str] = None
    email: Optional[str] = None
    official_website: Optional[str] = None
    websites: Optional[str] = None
    procedures: Optional[str] = None
    equipment: Optional[str] = None
    capabilities_raw: Optional[str] = None
    combined_medical_evidence: Optional[str] = None
    evidence_length_chars: Optional[int] = None
    v2_positive_score: Optional[float] = None
    v2_total_penalty: Optional[float] = None
    v2_identity_location_score: Optional[float] = None
    v2_contact_verification_score: Optional[float] = None
    v2_medical_evidence_score: Optional[float] = None
    v2_digital_social_score: Optional[float] = None
    v2_data_richness_score: Optional[float] = None
    claims_emergency_or_high_acuity: Optional[bool] = None
    has_high_acuity_supporting_evidence: Optional[bool] = None


class PaginatedFacilitiesResponse(CareGridModel):
    total: int
    page: int
    limit: int
    total_pages: int
    results: list[FacilityListItem]


class FacilityFiltersMeta(CareGridModel):
    states: list[str]
    facility_types: list[str]
    trust_categories: list[str]
    recommendation_readiness_values: list[str]


class DashboardOverview(CareGridModel):
    total_facilities: Optional[int] = None
    states_covered: Optional[int] = None
    average_trust_score: Optional[float] = None
    high_trust_count: Optional[int] = None
    moderate_trust_count: Optional[int] = None
    low_trust_count: Optional[int] = None
    high_risk_count: Optional[int] = None
    ready_for_recommendation_count: Optional[int] = None
    usable_with_verification_count: Optional[int] = None
    do_not_recommend_count: Optional[int] = None


class TrustDistributionItem(CareGridModel):
    trust_category: str
    facility_count: Optional[int] = None
    percent_of_total: Optional[float] = None
    avg_trust_score: Optional[float] = None


class ReadinessDistributionItem(CareGridModel):
    recommendation_readiness: str
    facility_count: Optional[int] = None
    percent_of_total: Optional[float] = None
    avg_trust_score: Optional[float] = None


class StateSummaryItem(CareGridModel):
    state: str
    total_facilities: Optional[int] = None
    high_trust_facilities: Optional[int] = None
    moderate_trust_facilities: Optional[int] = None
    low_trust_facilities: Optional[int] = None
    high_risk_facilities: Optional[int] = None
    ready_for_recommendation: Optional[int] = None
    avg_trust_score: Optional[float] = None
    high_risk_percent: Optional[float] = None
    ready_percent: Optional[float] = None
    state_risk_level: Optional[str] = None


class FacilityTypeSummaryItem(CareGridModel):
    facility_type: str
    facility_count: Optional[int] = None
    avg_trust_score: Optional[float] = None
    ready_for_recommendation: Optional[int] = None
    high_risk_facilities: Optional[int] = None


class TrustGapSummary(CareGridModel):
    total_facilities: Optional[int] = None
    states_covered: Optional[int] = None
    average_trust_score: Optional[float] = None
    high_trust_facilities: Optional[int] = None
    moderate_trust_facilities: Optional[int] = None
    low_trust_facilities: Optional[int] = None
    high_risk_facilities: Optional[int] = None
    ready_for_recommendation: Optional[int] = None
    usable_with_verification: Optional[int] = None
    do_not_recommend_without_review: Optional[int] = None
    facilities_with_contradiction_flags: Optional[int] = None
    facilities_with_high_acuity_claims: Optional[int] = None
    unsupported_high_acuity_claims: Optional[int] = None
    high_trust_percent: Optional[float] = None
    high_risk_percent: Optional[float] = None
    ready_percent: Optional[float] = None
    do_not_recommend_percent: Optional[float] = None
    contradiction_flag_percent: Optional[float] = None
    unsupported_high_acuity_percent: Optional[float] = None
    tier1_priority_states: Optional[str] = None
    tier2_priority_states: Optional[str] = None
    headline_insight: Optional[str] = None
    planning_interpretation: Optional[str] = None


class PriorityStateItem(CareGridModel):
    national_priority_rank: Optional[int] = None
    state: str
    calibrated_priority_tier: Optional[str] = None
    analysis_confidence: Optional[str] = None
    risk_level: Optional[str] = None
    overall_priority_score: Optional[float] = None
    trust_desert_risk_index: Optional[float] = None
    verification_burden_index: Optional[float] = None
    verification_burden_count: Optional[int] = None
    total_facilities: Optional[int] = None
    avg_trust_score: Optional[float] = None
    high_risk_facilities: Optional[int] = None
    high_risk_percent: Optional[float] = None
    low_trust_facilities: Optional[int] = None
    do_not_recommend_facilities: Optional[int] = None
    do_not_recommend_percent: Optional[float] = None
    ready_facilities: Optional[int] = None
    ready_percent: Optional[float] = None
    unsupported_high_acuity_count: Optional[int] = None
    unsupported_high_acuity_percent: Optional[float] = None
    priority_reason: Optional[str] = None


class StateRiskIndexItem(CareGridModel):
    state: str
    total_facilities: Optional[int] = None
    high_trust_facilities: Optional[int] = None
    moderate_trust_facilities: Optional[int] = None
    low_trust_facilities: Optional[int] = None
    high_risk_facilities: Optional[int] = None
    ready_facilities: Optional[int] = None
    usable_with_verification_facilities: Optional[int] = None
    do_not_recommend_facilities: Optional[int] = None
    contradiction_flag_count: Optional[int] = None
    high_acuity_claim_count: Optional[int] = None
    unsupported_high_acuity_count: Optional[int] = None
    avg_trust_score: Optional[float] = None
    high_risk_percent: Optional[float] = None
    low_or_high_risk_percent: Optional[float] = None
    ready_percent: Optional[float] = None
    do_not_recommend_percent: Optional[float] = None
    contradiction_percent: Optional[float] = None
    unsupported_high_acuity_percent: Optional[float] = None
    trust_desert_risk_index: Optional[float] = None
    risk_level: Optional[str] = None
    analysis_confidence: Optional[str] = None


class FacilityTypeGapItem(CareGridModel):
    facility_type: str
    total_facilities: Optional[int] = None
    avg_trust_score: Optional[float] = None
    high_trust_facilities: Optional[int] = None
    moderate_trust_facilities: Optional[int] = None
    low_trust_facilities: Optional[int] = None
    high_risk_facilities: Optional[int] = None
    ready_facilities: Optional[int] = None
    usable_with_verification_facilities: Optional[int] = None
    do_not_recommend_facilities: Optional[int] = None
    contradiction_flag_count: Optional[int] = None
    high_risk_percent: Optional[float] = None
    ready_percent: Optional[float] = None
    do_not_recommend_percent: Optional[float] = None
    contradiction_percent: Optional[float] = None
    facility_type_risk_level: Optional[str] = None
    recommended_data_action: Optional[str] = None


class SearchResultItem(CareGridModel):
    facility_id: str
    name: str
    facility_type: Optional[str] = None
    city: Optional[str] = None
    state: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    trust_score: Optional[float] = None
    trust_category: str
    recommendation_readiness: str
    specialties: Optional[str] = None
    evidence_summary: Optional[str] = None
    relevance_score: float
    matched_fields: list[str]
    warning_flags: list[str]


class SearchResponse(CareGridModel):
    query: str
    total_matches: int
    returned: int
    results: list[SearchResultItem]
    applied_filters: dict[str, Optional[str | float]]


class AgentRecommendRequest(CareGridModel):
    query: str
    state: Optional[str] = None
    facility_type: Optional[str] = None
    min_trust_score: Optional[float] = None
    max_results: int = Field(default=5, ge=1, le=20)


class AgentRecommendationItem(CareGridModel):
    facility_id: str
    name: str
    facility_type: Optional[str] = None
    city: Optional[str] = None
    state: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    trust_score: Optional[float] = None
    trust_category: str
    recommendation_readiness: str
    specialties: Optional[str] = None
    evidence_summary: Optional[str] = None
    matched_capabilities: list[str]
    matched_fields: list[str]
    warning_flags: list[str]
    recommendation_score: float
    reason_for_recommendation: str


class AgentRecommendResponse(CareGridModel):
    query: str
    interpreted_intent: dict[str, Any]
    total_candidates: int
    returned: int
    recommendations: list[AgentRecommendationItem]
    reasoning: str
    safety_note: str
    fallback_message: Optional[str] = None
    # AI-generated fields (populated when GEMINI_API_KEY is set)
    agent_mode: str = "rule-based"
    model_used: Optional[str] = None
    model_provider: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_reasoning: Optional[str] = None
    ai_next_steps: Optional[str] = None
