# CareGrid India Backend Context

## Project Name
CareGrid India

## Project Purpose
CareGrid India is an agentic healthcare intelligence system for India. It helps evaluate healthcare facility reliability using processed facility records, trust scoring, recommendation readiness, impact analysis, and later agentic recommendation workflows.

## Hackathon Context
This backend supports a global hackathon project. The priority is to preserve the real Databricks-generated data contract, expose stable backend APIs, and keep the system ready for frontend dashboard integration and later agentic recommendations.

## Backend Purpose
The FastAPI backend will serve facility data, trust scores, recommendation readiness, dashboard stats, impact analysis, state risk rankings, search, and future recommendation-agent outputs.

## Source CSV Files
- caregrid_backend_export_full.csv
- caregrid_final_dashboard_overview.csv
- caregrid_final_trust_distribution.csv
- caregrid_final_readiness_distribution.csv
- caregrid_final_state_summary.csv
- caregrid_final_facility_type_summary.csv
- caregrid_desert_state_risk_index.csv
- caregrid_desert_priority_states.csv
- caregrid_desert_calibrated_priority_ranking.csv
- caregrid_desert_trust_gap_summary.csv
- caregrid_desert_facility_type_gap.csv

## Source Of Truth Dataset
caregrid_backend_export_full.csv is the exact source-of-truth dataset for facility-level backend responses.

## Column Names That Must Not Change
- facility_id
- state
- latitude
- longitude
- trust_score
- trust_category
- recommendation_readiness
- combined_medical_evidence
- evidence_summary

## Trust Category Values That Must Not Change
- High Trust / Evidence Supported
- Moderate Trust / Verify Before Use
- Low Trust / Needs Human Verification
- High Risk / Insufficient Evidence

## Recommendation Readiness Values That Must Not Change
- Ready for recommendation
- Usable with verification
- Do not recommend without human review

## Implementation Instructions
- No mock data should be used once real CSV files are available.
- The backend must be built from the real CSV schema.
- Plan A capability extraction may later add more fields, but the current backend must remain compatible with the current schema.
- Update docs/PROGRESS.md after every major implementation step.
- Keep API responses stable for frontend compatibility.
