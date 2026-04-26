# API Contract

This document tracks implemented and planned backend endpoints. Facility endpoints are backed by the real caregrid_backend_export_full.csv dataset.

## Implemented Health Endpoint

### GET /health
Returns service health, version, data loading status, facility row count when loaded, endpoint readiness, and the expected test command.

## Implemented Facilities Endpoints

### GET /facilities
Returns a paginated list of facility records. The list response intentionally excludes combined_medical_evidence to keep payloads efficient.

Query parameters:
- page: integer, default 1, minimum 1
- limit: integer, default 50, minimum 1, maximum 500
- state: optional exact state filter, case-insensitive
- facility_type: optional exact facility type filter, case-insensitive
- trust_category: optional exact trust category filter
- recommendation_readiness: optional exact recommendation readiness filter
- min_trust_score: optional numeric lower bound
- max_trust_score: optional numeric upper bound

Response shape:
```json
{
  "total": 10000,
  "page": 1,
  "limit": 50,
  "total_pages": 200,
  "results": [
    {
      "facility_id": "string",
      "name": "string",
      "facility_type": "string or null",
      "city": "string or null",
      "state": "string",
      "pin_code": "string or null",
      "latitude": 0.0,
      "longitude": 0.0,
      "trust_score": 0.0,
      "trust_category": "string",
      "recommendation_readiness": "string",
      "specialties": "string or null",
      "evidence_summary": "string or null",
      "flag_icu_claim_without_equipment": false,
      "flag_surgery_claim_without_support": false,
      "flag_dialysis_claim_without_machine": false,
      "flag_oncology_claim_without_support": false
    }
  ]
}
```

### GET /facilities/meta/filters
Returns sorted unique filter values for frontend dropdowns.

Response shape:
```json
{
  "states": ["string"],
  "facility_types": ["string"],
  "trust_categories": ["string"],
  "recommendation_readiness_values": ["string"]
}
```

### GET /facilities/{facility_id}
Returns the full facility detail record for a facility_id. This endpoint includes combined_medical_evidence and detailed scoring fields.

Returns 404 if the facility_id is not found.

## Implemented Stats Endpoints

### GET /stats/overview
Returns the first row from caregrid_final_dashboard_overview.csv as a JSON object.

Response fields may include:
- total_facilities
- states_covered
- average_trust_score
- high_trust_count
- moderate_trust_count
- low_trust_count
- high_risk_count
- ready_for_recommendation_count
- usable_with_verification_count
- do_not_recommend_count

### GET /stats/trust-distribution
Returns rows from caregrid_final_trust_distribution.csv as a list, sorted by facility_count descending.

Response item fields:
- trust_category
- facility_count
- percent_of_total
- avg_trust_score

The trust_category values preserve the exact source category strings.

### GET /stats/readiness-distribution
Returns rows from caregrid_final_readiness_distribution.csv as a list, sorted by facility_count descending.

Response item fields:
- recommendation_readiness
- facility_count
- percent_of_total
- avg_trust_score

The recommendation_readiness values preserve the exact source category strings.

### GET /stats/states
Returns rows from caregrid_final_state_summary.csv as a list of state summary objects.

Query parameters:
- sort_by: default total_facilities
- order: asc or desc, default desc
- limit: optional integer, minimum 1, maximum 100

Allowed sort_by values:
- total_facilities
- avg_trust_score
- high_risk_percent
- ready_percent
- ready_for_recommendation

Returns 400 for invalid sort_by or order values.

### GET /stats/facility-types
Returns rows from caregrid_final_facility_type_summary.csv as a list, sorted by facility_count descending.

Response item fields:
- facility_type
- facility_count
- avg_trust_score
- ready_for_recommendation
- high_risk_facilities

## Implemented Impact Endpoints

### GET /impact/trust-gap-summary
Returns the first row from caregrid_desert_trust_gap_summary.csv as a JSON object.

Response fields may include:
- total_facilities
- states_covered
- average_trust_score
- high_trust_facilities
- moderate_trust_facilities
- low_trust_facilities
- high_risk_facilities
- ready_for_recommendation
- usable_with_verification
- do_not_recommend_without_review
- facilities_with_contradiction_flags
- facilities_with_high_acuity_claims
- unsupported_high_acuity_claims
- high_trust_percent
- high_risk_percent
- ready_percent
- do_not_recommend_percent
- contradiction_flag_percent
- unsupported_high_acuity_percent
- tier1_priority_states
- tier2_priority_states
- headline_insight
- planning_interpretation

### GET /impact/priority-states
Returns rows from caregrid_desert_calibrated_priority_ranking.csv as the preferred priority ranking source. Results are sorted by national_priority_rank ascending with missing ranks last.

Query parameters:
- tier: optional case-insensitive calibrated_priority_tier filter
- confidence: optional case-insensitive analysis_confidence filter
- limit: optional integer, minimum 1, maximum 100

### GET /impact/state-risk-index
Returns rows from caregrid_desert_state_risk_index.csv.

Query parameters:
- risk_level: optional case-insensitive risk_level filter
- confidence: optional case-insensitive analysis_confidence filter
- sort_by: default trust_desert_risk_index
- order: asc or desc, default desc
- limit: optional integer, minimum 1, maximum 100

Allowed sort_by values:
- trust_desert_risk_index
- total_facilities
- avg_trust_score
- high_risk_percent
- ready_percent
- do_not_recommend_percent
- unsupported_high_acuity_percent

Returns 400 for invalid sort_by or order values.

### GET /impact/facility-type-gap
Returns rows from caregrid_desert_facility_type_gap.csv.

Query parameters:
- risk_level: optional case-insensitive facility_type_risk_level filter
- sort_by: default do_not_recommend_percent
- order: asc or desc, default desc

Allowed sort_by values:
- total_facilities
- avg_trust_score
- high_risk_percent
- ready_percent
- do_not_recommend_percent
- contradiction_percent

Returns 400 for invalid sort_by or order values.

## Implemented Search Endpoint

### GET /search
Searches caregrid_backend_export_full.csv facility records across selected text fields and returns compact ranked results.

Query parameters:
- q: required search query
- state: optional exact state filter, case-insensitive
- facility_type: optional exact facility type filter, case-insensitive
- trust_category: optional exact trust category filter
- recommendation_readiness: optional exact recommendation readiness filter
- min_trust_score: optional numeric threshold from 0 to 100
- limit: integer, default 20, minimum 1, maximum 100

Searched fields:
- name
- city
- state
- facility_type
- specialties
- procedures
- equipment
- capabilities_raw
- combined_medical_evidence
- evidence_summary

Ranking:
- Relevance score from matched fields
- Trust and recommendation readiness boosts
- Sort by relevance_score descending, trust_score descending, then name ascending

Response shape:
```json
{
  "query": "dental",
  "total_matches": 100,
  "returned": 20,
  "results": [
    {
      "facility_id": "string",
      "name": "string",
      "facility_type": "string or null",
      "city": "string or null",
      "state": "string",
      "latitude": 0.0,
      "longitude": 0.0,
      "trust_score": 0.0,
      "trust_category": "string",
      "recommendation_readiness": "string",
      "specialties": "string or null",
      "evidence_summary": "string or null",
      "relevance_score": 0.0,
      "matched_fields": ["name"],
      "warning_flags": []
    }
  ],
  "applied_filters": {
    "state": null,
    "facility_type": null,
    "trust_category": null,
    "recommendation_readiness": null,
    "min_trust_score": null
  }
}
```

Search results do not include combined_medical_evidence.

## Implemented Agent Endpoint

### POST /agent/recommend
Returns transparent rule-based facility recommendations from caregrid_backend_export_full.csv. This endpoint does not call an LLM or external API.

Request body:
```json
{
  "query": "Find trusted ICU facilities",
  "state": "Maharashtra",
  "facility_type": "hospital",
  "min_trust_score": 60,
  "max_results": 5
}
```

Request fields:
- query: required natural-language request
- state: optional exact state filter, request body value takes priority over detected state
- facility_type: optional exact facility type filter
- min_trust_score: optional numeric threshold from 0 to 100
- max_results: integer, default 5, minimum 1, maximum 20

Response shape:
```json
{
  "query": "Find trusted ICU facilities",
  "interpreted_intent": {
    "capabilities": ["ICU / critical care"],
    "state": "Maharashtra",
    "prefer_trusted": true,
    "safe_or_recommend": false
  },
  "total_candidates": 10,
  "returned": 5,
  "recommendations": [
    {
      "facility_id": "string",
      "name": "string",
      "facility_type": "string or null",
      "city": "string or null",
      "state": "string",
      "latitude": 0.0,
      "longitude": 0.0,
      "trust_score": 0.0,
      "trust_category": "string",
      "recommendation_readiness": "string",
      "specialties": "string or null",
      "evidence_summary": "string or null",
      "matched_capabilities": ["ICU / critical care"],
      "matched_fields": ["equipment"],
      "warning_flags": [],
      "recommendation_score": 20.0,
      "reason_for_recommendation": "string"
    }
  ],
  "reasoning": "string",
  "safety_note": "CareGrid recommendations are evidence-based decision support only. Emergency medical decisions should be verified with local providers and official emergency channels.",
  "fallback_message": null
}
```

## Compatibility Rule
Keep API responses stable for frontend compatibility once endpoint response shapes are introduced.
