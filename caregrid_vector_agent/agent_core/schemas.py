from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


class FacilityRecord(BaseModel):
    """Raw facility record as loaded from the data source."""
    facility_id: str
    name: str = ""
    location: str = ""
    combined_medical_evidence: str = ""
    trust_score: float = 0.0
    trust_category: str = ""
    recommendation_readiness: str = ""
    capabilities: list[str] = []


class AgentQuery(BaseModel):
    """Structured query passed into the agent pipeline."""
    query: str
    location: Optional[str] = None
    required_capabilities: list[str] = []
    min_trust_score: float = 0.0
    top_k: int = 10


class AgentIntent(BaseModel):
    """Parsed representation of a user query."""
    # Core identity — raw_query kept for backward compatibility
    raw_query: str
    original_query: str = ""
    normalized_query: str = ""

    # What
    capabilities_required: list[str] = []
    facility_type: Optional[str] = None  # hospital / clinic / doctor / pharmacy / dentist

    # Where
    location: Optional[str] = None      # city if known, else state (backward compat)
    state: Optional[str] = None
    city: Optional[str] = None

    # Qualifiers
    trust_preference: str = "unspecified"   # trusted / verification_ok / risky_allowed / unspecified
    urgency: str = "unspecified"            # emergency / urgent / routine / unspecified
    min_trust_score: Optional[float] = None
    proximity_requested: bool = False
    web_verification_requested: bool = False
    vector_search_requested: bool = False


class EvidenceSnippet(BaseModel):
    """A single evidence item extracted from a facility record.

    `support_level` is one of `strong` / `moderate` / `weak` / `contradiction`
    and is set by `agent_core.evidence_citation.extract_evidence_snippets()`.
    The contradiction level is reserved for use by `contradiction_rules.py`.
    """
    facility_id: str
    excerpt: str
    source_field: str = "combined_medical_evidence"
    relevance_score: Optional[float] = None

    # Citation metadata (added in Stage 10) — all optional for backward compat
    support_level: str = "weak"
    capability_id: Optional[str] = None
    matched_terms: list[str] = []


class ValidationFinding(BaseModel):
    """A single validation result from the validator module.

    Severity scale (Stage 11):
      ``info``   — claim is supported, no action needed.
      ``low``    — minor issue, recommendation unaffected.
      ``medium`` — weak / moderate evidence only.
      ``high``   — claim has no supporting evidence, or a contradiction was found.
    """
    facility_id: str
    rule: str
    severity: str  # "info" | "low" | "medium" | "high" (legacy: "warning"/"error" still accepted)
    message: str

    # Per-capability validation context (added in Stage 11) — all optional
    capability: Optional[str] = None
    finding_type: str = ""
    evidence_used: list[str] = []
    missing_evidence: list[str] = []
    recommendation_impact: str = "none"


class WebVerificationResult(BaseModel):
    """Result of a Tavily external web verification for one facility.

    Stage 12: extended with verification status, scoring, matched metadata,
    and credit estimation. The original fields (`facility_id`, `query_used`,
    `verified`, `sources`, `summary`, `cached`) remain for backward
    compatibility; new fields are optional with safe defaults.

    `verification_status` values:
      ``verified``    — score >= 0.7, name + location strongly matched.
      ``partial``     — 0.4 <= score < 0.7, partial match.
      ``unverified``  — score < 0.4, no clear external evidence.
      ``skipped``     — Tavily disabled or API key missing (no API call made).
      ``error``       — Tavily call attempted but failed; see ``error_message``.
    """
    facility_id: str
    query_used: str = ""
    verified: bool = False
    sources: list[str] = []
    summary: str = ""
    cached: bool = False

    # New fields (Stage 12) — all optional, all backward-compatible
    web_checked: bool = False
    web_available: bool = False
    matched_name: str = ""
    matched_location: str = ""
    matched_capability: list[str] = []
    top_url: str = ""
    top_snippet: str = ""
    verification_score: float = 0.0
    verification_status: str = "skipped"
    verification_notes: list[str] = []
    error_message: Optional[str] = None
    credits_estimated: Optional[int] = None


class ScoreBreakdown(BaseModel):
    """Per-recommendation score components (Stage 13).

    The recommendation engine computes each component independently and
    sums them into ``final_score`` (clipped to ``[0, 1]``). Penalty
    components are negative-or-zero; positive components are zero-or-positive.
    """
    trust_score_component: float = 0.0
    readiness_component: float = 0.0
    capability_match_component: float = 0.0
    evidence_strength_component: float = 0.0
    validation_penalty: float = 0.0
    warning_penalty: float = 0.0
    vector_similarity_component: float = 0.0
    tavily_verification_component: float = 0.0
    final_score: float = 0.0


class AgentRecommendation(BaseModel):
    """A single ranked facility recommendation with supporting evidence."""
    facility_id: str
    name: str = ""
    trust_score: float
    trust_category: str
    recommendation_readiness: str
    evidence_snippets: list[EvidenceSnippet] = []
    warnings: list[str] = []
    web_verification: Optional[WebVerificationResult] = None

    # Stage 13 — full recommendation contract; all optional / defaulted
    facility_type: str = ""
    city: str = ""
    state: str = ""
    matched_capabilities: list[str] = []
    matched_fields: list[str] = []
    validation_findings: list[ValidationFinding] = []
    warning_flags: list[str] = []
    score_breakdown: Optional[ScoreBreakdown] = None
    reason_for_recommendation: str = ""
    human_next_steps: list[str] = []


class AgentResponse(BaseModel):
    """Standard agent output — all top-level fields are required by the trace contract."""
    query: str = ""
    intent: Optional[AgentIntent] = None
    recommendations: list[AgentRecommendation] = []
    evidence: list[EvidenceSnippet] = []
    warnings: list[str] = []
    reasoning: str = ""
    safety_note: str = ""
    validation_findings: list[ValidationFinding] = []

    # Stage 13 — final response contract; all optional / defaulted
    interpreted_intent: Optional[AgentIntent] = None
    retrieval_summary: dict[str, Any] = Field(default_factory=dict)
    total_candidates: int = 0
    returned: int = 0
    fallback_message: str = ""
    trace_summary: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Backward-compatibility alias — remove once all callers use EvidenceSnippet
# ---------------------------------------------------------------------------
EvidenceBlock = EvidenceSnippet
