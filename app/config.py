from pathlib import Path


APP_NAME = "CareGrid India API"
APP_VERSION = "0.1.0"
APP_DESCRIPTION = "Backend API for the CareGrid India healthcare intelligence system."

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

MAIN_FACILITY_CSV = "caregrid_backend_export_full.csv"
DASHBOARD_OVERVIEW_CSV = "caregrid_final_dashboard_overview.csv"
TRUST_DISTRIBUTION_CSV = "caregrid_final_trust_distribution.csv"
READINESS_DISTRIBUTION_CSV = "caregrid_final_readiness_distribution.csv"
STATE_SUMMARY_CSV = "caregrid_final_state_summary.csv"
FACILITY_TYPE_SUMMARY_CSV = "caregrid_final_facility_type_summary.csv"
DESERT_STATE_RISK_INDEX_CSV = "caregrid_desert_state_risk_index.csv"
DESERT_PRIORITY_STATES_CSV = "caregrid_desert_priority_states.csv"
DESERT_CALIBRATED_PRIORITY_RANKING_CSV = "caregrid_desert_calibrated_priority_ranking.csv"
DESERT_TRUST_GAP_SUMMARY_CSV = "caregrid_desert_trust_gap_summary.csv"
DESERT_FACILITY_TYPE_GAP_CSV = "caregrid_desert_facility_type_gap.csv"

EXPECTED_ROW_COUNTS = {
    MAIN_FACILITY_CSV: 10_000,
    DASHBOARD_OVERVIEW_CSV: 1,
    TRUST_DISTRIBUTION_CSV: 4,
    READINESS_DISTRIBUTION_CSV: 3,
    STATE_SUMMARY_CSV: 34,
    FACILITY_TYPE_SUMMARY_CSV: 6,
    DESERT_STATE_RISK_INDEX_CSV: 34,
    DESERT_PRIORITY_STATES_CSV: 34,
    DESERT_CALIBRATED_PRIORITY_RANKING_CSV: 34,
    DESERT_TRUST_GAP_SUMMARY_CSV: 1,
    DESERT_FACILITY_TYPE_GAP_CSV: 6,
}

CSV_FILENAMES = [
    MAIN_FACILITY_CSV,
    DASHBOARD_OVERVIEW_CSV,
    TRUST_DISTRIBUTION_CSV,
    READINESS_DISTRIBUTION_CSV,
    STATE_SUMMARY_CSV,
    FACILITY_TYPE_SUMMARY_CSV,
    DESERT_STATE_RISK_INDEX_CSV,
    DESERT_PRIORITY_STATES_CSV,
    DESERT_CALIBRATED_PRIORITY_RANKING_CSV,
    DESERT_TRUST_GAP_SUMMARY_CSV,
    DESERT_FACILITY_TYPE_GAP_CSV,
]

REQUIRED_FACILITY_COLUMNS = [
    "facility_id",
    "name",
    "facility_type",
    "city",
    "state",
    "pin_code",
    "latitude",
    "longitude",
    "phone",
    "email",
    "official_website",
    "websites",
    "specialties",
    "procedures",
    "equipment",
    "capabilities_raw",
    "combined_medical_evidence",
    "evidence_length_chars",
    "trust_score",
    "trust_category",
    "recommendation_readiness",
    "v2_positive_score",
    "v2_total_penalty",
    "v2_identity_location_score",
    "v2_contact_verification_score",
    "v2_medical_evidence_score",
    "v2_digital_social_score",
    "v2_data_richness_score",
    "flag_icu_claim_without_equipment",
    "flag_surgery_claim_without_support",
    "flag_dialysis_claim_without_machine",
    "flag_oncology_claim_without_support",
    "claims_emergency_or_high_acuity",
    "has_high_acuity_supporting_evidence",
    "evidence_summary",
]

ALLOWED_TRUST_CATEGORIES = {
    "High Trust / Evidence Supported",
    "Moderate Trust / Verify Before Use",
    "Low Trust / Needs Human Verification",
    "High Risk / Insufficient Evidence",
}

ALLOWED_RECOMMENDATION_READINESS = {
    "Ready for recommendation",
    "Usable with verification",
    "Do not recommend without human review",
}
