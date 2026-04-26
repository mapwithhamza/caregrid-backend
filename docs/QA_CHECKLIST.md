# QA Checklist

## Data Loading QA
- [ ] All 11 CSV files present.
- [ ] Main facility file has 10,000 rows.
- [ ] Main facility file has 35 columns.
- [ ] facility_id is unique.
- [ ] states covered = 34.
- [ ] data_loaded=true in /health.

## API QA
- [ ] /health returns healthy.
- [ ] /facilities returns paginated data.
- [ ] /facilities/{facility_id} returns detail.
- [ ] /facilities/meta/filters returns dropdown values.
- [ ] /stats endpoints return dashboard summaries.
- [ ] /impact endpoints return impact/desert analysis.
- [ ] /search returns ranked results.
- [ ] /agent/recommend returns interpreted intent and recommendations.

## Schema Stability QA
- [ ] Do not rename facility_id.
- [ ] Do not rename trust_score.
- [ ] Do not rename trust_category.
- [ ] Do not rename recommendation_readiness.
- [ ] Do not rename state.
- [ ] Do not rename latitude/longitude.
- [ ] Do not rename evidence_summary.
- [ ] Do not rename combined_medical_evidence.

## Frontend Integration QA
- [ ] CORS is enabled.
- [ ] Base URL is documented.
- [ ] Query parameter examples are documented.
- [ ] Agent POST body examples are documented.
- [ ] Warning badge logic is documented.

## Known Limitations
- Distance/nearest search is not implemented yet.
- Agent is rule-based, not LLM-based.
- Specialty desert analysis will improve after Plan A capability extraction is merged.
- Dataset is evidence-driven; recommendations require real-world verification.
