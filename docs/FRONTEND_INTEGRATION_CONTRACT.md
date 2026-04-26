# Frontend Integration Contract

## Backend Base URL
Local development:
http://localhost:8000

## Main Endpoint Groups
- Health
- Facilities
- Stats
- Impact
- Search
- Agent

## Required Frontend Assumptions
- facility_id is the primary key.
- state is the cleaned final state field.
- latitude and longitude are used for map markers.
- trust_score is numeric 0-100.
- trust_category values must be treated as fixed labels.
- recommendation_readiness values must be treated as fixed labels.
- evidence_summary is safe for cards.
- combined_medical_evidence should be used only in detailed pages/modals.
- warning_flags should be displayed as badges.

## Exact Trust Category Values
- High Trust / Evidence Supported
- Moderate Trust / Verify Before Use
- Low Trust / Needs Human Verification
- High Risk / Insufficient Evidence

## Exact Recommendation Readiness Values
- Ready for recommendation
- Usable with verification
- Do not recommend without human review

## Suggested Frontend Views
- Landing KPI dashboard
- India map with facility markers
- Facility explorer table
- Facility detail drawer/modal
- Trust distribution chart
- Readiness distribution chart
- State risk dashboard
- Impact priority states panel
- Agent recommendation panel
- Search results page

## Endpoint Usage By Frontend Component
- KPI cards -> /stats/overview and /impact/trust-gap-summary
- Trust donut/bar chart -> /stats/trust-distribution
- Readiness chart -> /stats/readiness-distribution
- Map markers -> /facilities with pagination/filters
- Filter dropdowns -> /facilities/meta/filters
- State dashboard -> /stats/states and /impact/state-risk-index
- Facility type chart -> /stats/facility-types and /impact/facility-type-gap
- Search bar -> /search
- Agent panel -> /agent/recommend
- Facility detail modal -> /facilities/{facility_id}

## Response Notes
- /facilities list does not include combined_medical_evidence.
- /facilities/{facility_id} includes combined_medical_evidence.
- /search returns compact results with matched_fields and warning_flags.
- /agent/recommend returns reasoning, interpreted_intent, recommendations, and safety_note.
