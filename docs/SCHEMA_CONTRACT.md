# Schema Contract

This contract documents important columns for caregrid_backend_export_full.csv. Backend implementation must preserve these names and values exactly.

## Important Columns
- facility_id
- name
- facility_type
- city
- state
- pin_code
- latitude
- longitude
- phone
- email
- official_website
- websites
- specialties
- procedures
- equipment
- capabilities_raw
- combined_medical_evidence
- evidence_length_chars
- trust_score
- trust_category
- recommendation_readiness
- v2_positive_score
- v2_total_penalty
- v2_identity_location_score
- v2_contact_verification_score
- v2_medical_evidence_score
- v2_digital_social_score
- v2_data_richness_score
- flag_icu_claim_without_equipment
- flag_surgery_claim_without_support
- flag_dialysis_claim_without_machine
- flag_oncology_claim_without_support
- claims_emergency_or_high_acuity
- has_high_acuity_supporting_evidence
- evidence_summary

## Column Rules
- facility_id is the primary key.
- state is the final cleaned state field. Use state, not address_stateOrRegion.
- latitude and longitude are used for map plotting.
- combined_medical_evidence is the full medical evidence field.
- evidence_summary is the short preview evidence text.
- trust_score is numeric from 0 to 100.
- trust_category values must remain exact.
- recommendation_readiness values must remain exact.

## Trust Category Values
- High Trust / Evidence Supported
- Moderate Trust / Verify Before Use
- Low Trust / Needs Human Verification
- High Risk / Insufficient Evidence

## Recommendation Readiness Values
- Ready for recommendation
- Usable with verification
- Do not recommend without human review
