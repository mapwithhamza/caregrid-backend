# Endpoint Examples

Base URL for local development:
http://localhost:8000

## Health
GET /health

## Facilities
GET /facilities?limit=5

GET /facilities?state=Maharashtra&facility_type=hospital&limit=10

GET /facilities/meta/filters

## Stats
GET /stats/overview

GET /stats/trust-distribution

GET /stats/readiness-distribution

GET /stats/states?sort_by=ready_percent&order=asc&limit=5

GET /stats/facility-types

## Impact
GET /impact/trust-gap-summary

GET /impact/priority-states?limit=5

GET /impact/priority-states?tier=Tier%201&limit=5

GET /impact/state-risk-index?sort_by=trust_desert_risk_index&order=desc&limit=5

GET /impact/facility-type-gap

## Search
GET /search?q=dental&limit=5

GET /search?q=icu&limit=5

GET /search?q=dialysis&min_trust_score=60&limit=5

GET /search?q=hospital&state=Maharashtra&facility_type=hospital&limit=5

## Agent
POST /agent/recommend

Body:
```json
{
  "query": "Find trusted ICU facilities",
  "max_results": 5
}
```

POST /agent/recommend

Body:
```json
{
  "query": "Find emergency hospitals",
  "state": "Maharashtra",
  "max_results": 5
}
```

POST /agent/recommend

Body:
```json
{
  "query": "Find dialysis centers in Maharashtra",
  "max_results": 5
}
```
