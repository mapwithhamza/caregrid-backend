# CareGrid India Project Context

CareGrid India is an agentic healthcare intelligence system for India. It uses processed healthcare facility data to help identify reliable providers, surface evidence quality, and support safer healthcare discovery and planning.

## Why It Matters
Healthcare facility information is often fragmented, inconsistent, or difficult to verify. CareGrid India organizes facility-level evidence into trust scores, recommendation readiness labels, warning flags, and state-level risk indicators so users and downstream systems can reason about reliability more clearly.

## Dataset
The current backend is designed around 10,000 healthcare facility records generated from Databricks processing. The main facility source of truth is caregrid_backend_export_full.csv.

## Core Outputs
- Trust score
- Recommendation readiness
- Warning flags
- State risk ranking
- Impact analysis

## Final Product
The final product combines a backend API, frontend dashboard, and agentic recommendation layer. The backend will initially serve the current CSV fields directly from real data files placed in backend/data/.

## Future Plan A Integration
Plan A capability extraction will be integrated later. The current backend should remain compatible with the existing schema while allowing future capability fields to be added without breaking frontend contracts.
