# Integration Notes

The backend will initially use the current CSV fields from the Databricks-generated exports.

Plan A may later provide capability extraction outputs. Future fields may include:
- extracted_capabilities
- capability_confidence
- capability_evidence
- validation_notes

Backend design should allow these fields to be added without breaking existing endpoints or frontend response contracts.
