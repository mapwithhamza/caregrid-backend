# Data Files

All CSV files should be placed in backend/data/. These files are generated from Databricks processing and are the real backend data sources.

## Required CSV Files
- caregrid_backend_export_full.csv: Main facility dataset. Expected to contain 10,000 rows and 35 columns. This is the source of truth for facility-level responses.
- caregrid_final_dashboard_overview.csv: One-row dashboard KPI summary for high-level stats.
- caregrid_final_trust_distribution.csv: Trust category distribution for dashboard charts.
- caregrid_final_readiness_distribution.csv: Recommendation readiness distribution for dashboard charts.
- caregrid_final_state_summary.csv: State-level summary for geographic and state comparison views.
- caregrid_final_facility_type_summary.csv: Facility type summary for category-level analysis.
- caregrid_desert_state_risk_index.csv: State-level trust desert index for impact views.
- caregrid_desert_priority_states.csv: Action-oriented state priority list.
- caregrid_desert_calibrated_priority_ranking.csv: Final calibrated national priority ranking.
- caregrid_desert_trust_gap_summary.csv: One-row national trust gap summary.
- caregrid_desert_facility_type_gap.csv: Facility type reliability gap analysis.

## Data Source Rules
- Do not replace these files with generated mock data as the final source.
- Do not change CSV schemas in backend code.
- Validate required files and expected row counts before serving data.
