"""
agent_core.recommendation_engine — End-to-end orchestration.

This is the single entry point a UI / CLI / notebook should call.
Everything else (`intent_parser`, `local_retriever`, `vector_retriever`,
`evidence_citation`, `validator`, `tavily_verifier`, `audit_logger`) is
glued together here into a deterministic, fail-safe pipeline.

Pipeline
--------
1. **Parse intent** from the natural-language ``query``.
   Function-level overrides (``state``, ``facility_type``,
   ``min_trust_score``) take precedence over what the parser found.
2. **Local retrieval** via :func:`agent_core.local_retriever.retrieve_local_candidates`.
3. *(Optional)* **Vector retrieval** via
   :class:`agent_core.vector_retriever.VectorRetriever`. When disabled
   *or* unavailable (no Databricks creds, SDK missing, API failure),
   the pipeline silently proceeds with the local pool only.
4. **Merge** local + vector candidates by ``facility_id``.
5. **Extract evidence snippets** for each merged candidate.
6. **Validate** capability claims against the snippets, emitting
   :class:`agent_core.schemas.ValidationFinding` rows.
7. **Score** each candidate with a 9-component breakdown, sort
   descending, take the top ``max_results``.
8. *(Optional)* **Tavily web verification** of the top
   ``max_web_verified``. Failures map to ``verification_status="error"``
   and never raise.
9. Return a fully-populated :class:`agent_core.schemas.AgentResponse`
   that includes a ``retrieval_summary``, ``trace_summary``,
   ``fallback_message`` (when no recommendations), and a constant
   ``safety_note``.

The function never raises. Any unexpected exception inside a stage is
caught, logged onto the trace, and the pipeline degrades to the
last-known-good state.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import pandas as pd

from agent_core.audit_logger import AuditLogger
from agent_core.evidence_citation import extract_evidence_snippets
from agent_core.intent_parser import parse_query_intent
from agent_core.local_retriever import LocalCandidate, retrieve_local_candidates
from agent_core.schemas import (
    AgentIntent,
    AgentRecommendation,
    AgentResponse,
    EvidenceSnippet,
    ScoreBreakdown,
    ValidationFinding,
)
from agent_core.tavily_verifier import (
    DEPTH_BASIC,
    verify_top_recommendations,
)
from agent_core.validator import (
    FINDING_CONTRADICTION,
    FINDING_MISSING_EVIDENCE,
    FINDING_WEAK_EVIDENCE,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    validate_candidate,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAFETY_NOTE: str = (
    "This recommendation is generated automatically from facility data evidence "
    "and is not medical advice. Always confirm capability, current availability, "
    "and capacity directly with the facility before making any clinical, "
    "admission, or referral decisions — especially for emergency, high-acuity, "
    "or specialty care."
)

# Score weights — tuned so positive components sum to <= 1.0 (vector +
# tavily are *additive* signals capped at 0.15 each so even with full
# trust + readiness + caps + evidence + vector + tavily we never blow
# past 1.0 after clamping).
_W_TRUST            = 0.25
_W_READINESS        = 0.15
_W_CAPABILITY       = 0.15
_W_EVIDENCE         = 0.15
_W_VECTOR           = 0.15
_W_TAVILY           = 0.15
# Stage 16: depth-of-match bonus. The local retriever's relevance score
# captures *how many* capability terms (and how strong) a record matches
# — without this component, two facilities whose binary cap_comp == 1
# rank only by trust score, so a generic high-trust hospital with one
# emergency-relevant term outranks a dedicated trauma centre with ten.
_W_LOCAL_RELEVANCE       = 0.10
_LOCAL_RELEVANCE_SAT     = 15.0   # local_score >= this → full bonus.

# Penalties.
_PENALTY_FINDING_HIGH         = -0.10
_PENALTY_FINDING_MEDIUM       = -0.05
_PENALTY_FINDING_CONTRADICTION = -0.15
_PENALTY_PER_WARNING          = -0.02

# Map evidence support_level → contribution multiplier (mean over snippets).
_EVIDENCE_LEVEL_WEIGHT: dict[str, float] = {
    "strong": 1.0,
    "moderate": 0.6,
    "weak": 0.3,
    "contradiction": 0.0,
}

# Readiness → readiness component (out of _W_READINESS).
_READINESS_FACTOR: dict[str, float] = {
    "Ready for recommendation":           1.0,
    "Usable with verification":           0.5,
    "Do not recommend without human review": 0.0,
}

# Default candidate-pool size before final ranking.
_LOCAL_LIMIT_POOL = 200
_VECTOR_NUM_RESULTS = 20


# ---------------------------------------------------------------------------
# Settings access
# ---------------------------------------------------------------------------

def _get_settings() -> Any:
    """Lazy import of the settings singleton."""
    from config.settings import settings  # noqa: WPS433
    return settings


# ---------------------------------------------------------------------------
# Intent helpers
# ---------------------------------------------------------------------------

def _apply_intent_overrides(
    intent: AgentIntent,
    *,
    state: Optional[str],
    facility_type: Optional[str],
    min_trust_score: Optional[float],
) -> AgentIntent:
    """Apply caller overrides to a freshly-parsed intent (mutates ``intent``)."""
    if state is not None and str(state).strip():
        intent.state = str(state).strip()
        if intent.location is None:
            intent.location = intent.city or intent.state
    if facility_type is not None and str(facility_type).strip():
        intent.facility_type = str(facility_type).strip().lower()
    if min_trust_score is not None:
        try:
            intent.min_trust_score = float(min_trust_score)
        except (TypeError, ValueError):
            pass
    return intent


def _intent_summary(intent: AgentIntent) -> dict:
    """Compact dict view of the intent for trace / response payloads."""
    return {
        "capabilities_required": list(intent.capabilities_required or []),
        "state": intent.state,
        "city": intent.city,
        "facility_type": intent.facility_type,
        "trust_preference": intent.trust_preference,
        "urgency": intent.urgency,
        "min_trust_score": intent.min_trust_score,
    }


# ---------------------------------------------------------------------------
# Merging local + vector candidates
# ---------------------------------------------------------------------------

def _candidate_from_local(lc: LocalCandidate) -> dict:
    return {
        "facility_id": lc.facility_id,
        "raw_record": dict(lc.raw_record or {}),
        "matched_fields": list(lc.matched_fields),
        "matched_capabilities": list(lc.matched_capabilities),
        "local_relevance_score": float(lc.local_relevance_score),
        "vector_similarity": None,
        "relaxation_notes": list(lc.relaxation_notes),
        "evidence_snippets": [],
        "validation_findings": [],
        "warning_flags": [],
        "score_breakdown": None,
        "web_verification": None,
    }


def _record_for_facility(df: pd.DataFrame, facility_id: str) -> Optional[dict]:
    """Look up a row by facility_id and return it as a dict, or None."""
    if df is None or "facility_id" not in df.columns:
        return None
    matches = df.loc[df["facility_id"].astype(str) == str(facility_id)]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()


def _merge_candidates(
    local_candidates: list[LocalCandidate],
    vector_results: list,
    df: pd.DataFrame,
) -> list[dict]:
    """Merge local + vector hits by ``facility_id``.

    - Local pool seeds the merge.
    - Vector hits already in the local pool *boost* the existing entry
      with ``vector_similarity``.
    - Vector hits not in the local pool are added by reading their full
      record from ``df`` (when present) or from ``vr.metadata`` as a
      last resort.
    """
    merged: dict[str, dict] = {}
    for lc in local_candidates:
        merged[str(lc.facility_id)] = _candidate_from_local(lc)

    for vr in vector_results or []:
        fid = str(vr.facility_id)
        sim = float(vr.similarity_score or 0.0)
        if fid in merged:
            merged[fid]["vector_similarity"] = sim
            continue
        record = _record_for_facility(df, fid)
        if record is None:
            record = dict(vr.metadata or {})
            record.setdefault("facility_id", fid)
        merged[fid] = {
            "facility_id": fid,
            "raw_record": record,
            "matched_fields": [],
            "matched_capabilities": [],
            "local_relevance_score": 0.0,
            "vector_similarity": sim,
            "relaxation_notes": ["from_vector_only"],
            "evidence_snippets": [],
            "validation_findings": [],
            "warning_flags": [],
            "score_breakdown": None,
            "web_verification": None,
        }
    return list(merged.values())


# ---------------------------------------------------------------------------
# Per-candidate enrichment
# ---------------------------------------------------------------------------

def _enrich_candidates(
    candidates: list[dict],
    intent: AgentIntent,
) -> list[dict]:
    """Attach evidence snippets, validation findings, and warning flags."""
    requested_caps = list(intent.capabilities_required or [])
    for c in candidates:
        record = c["raw_record"]
        try:
            snippets = extract_evidence_snippets(record, requested_caps)
        except Exception:  # noqa: BLE001 — evidence extraction must never crash
            snippets = []
        try:
            findings = validate_candidate(record, requested_caps, snippets)
        except Exception:  # noqa: BLE001
            findings = []
        c["evidence_snippets"] = snippets
        c["validation_findings"] = findings
        c["warning_flags"] = _collect_warning_flags(record, findings, c)
    return candidates


def _collect_warning_flags(
    record: dict,
    findings: list[ValidationFinding],
    candidate: dict,
) -> list[str]:
    """Lightweight warning surface for the recommendation card."""
    flags: list[str] = []
    if not record.get("trust_category"):
        flags.append("missing_trust_category")
    if any(f.finding_type == FINDING_CONTRADICTION for f in findings):
        flags.append("contradiction_detected")
    if any(f.finding_type == FINDING_MISSING_EVIDENCE for f in findings):
        flags.append("missing_capability_evidence")
    if any(f.finding_type == FINDING_WEAK_EVIDENCE for f in findings):
        flags.append("weak_capability_evidence")
    if candidate.get("relaxation_notes"):
        flags.append("retrieved_via_relaxation")
    return flags


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_candidate(candidate: dict, intent: AgentIntent) -> ScoreBreakdown:
    """Produce a :class:`ScoreBreakdown` and write it onto ``candidate``."""
    record   = candidate["raw_record"]
    snippets = candidate["evidence_snippets"]
    findings = candidate["validation_findings"]

    try:
        trust_score_raw = float(record.get("trust_score") or 0.0)
    except (TypeError, ValueError):
        trust_score_raw = 0.0
    trust_score_raw = max(0.0, min(1.0, trust_score_raw))
    trust_comp = trust_score_raw * _W_TRUST

    readiness_text = (record.get("recommendation_readiness") or "").strip()
    readiness_factor = _READINESS_FACTOR.get(readiness_text, 0.0)
    readiness_comp = _W_READINESS * readiness_factor

    requested = set(intent.capabilities_required or [])
    matched   = set(candidate.get("matched_capabilities") or [])
    if requested:
        ratio = len(requested & matched) / len(requested)
        cap_comp = _W_CAPABILITY * ratio
    else:
        cap_comp = _W_CAPABILITY * 0.5  # neutral when no caps requested

    if snippets:
        avg = sum(
            _EVIDENCE_LEVEL_WEIGHT.get(s.support_level, 0.3) for s in snippets
        ) / len(snippets)
        evidence_comp = _W_EVIDENCE * avg
    else:
        evidence_comp = 0.0

    val_penalty = 0.0
    for f in findings:
        ft = f.finding_type or ""
        sv = f.severity or ""
        if ft == FINDING_CONTRADICTION:
            val_penalty += _PENALTY_FINDING_CONTRADICTION
        elif ft == FINDING_MISSING_EVIDENCE or sv == SEVERITY_HIGH:
            val_penalty += _PENALTY_FINDING_HIGH
        elif ft == FINDING_WEAK_EVIDENCE or sv == SEVERITY_MEDIUM:
            val_penalty += _PENALTY_FINDING_MEDIUM

    warning_count = len(candidate.get("warning_flags") or [])
    warning_penalty = warning_count * _PENALTY_PER_WARNING

    sim = candidate.get("vector_similarity")
    if sim is None:
        vec_comp = 0.0
    else:
        try:
            vec_comp = _W_VECTOR * max(0.0, min(1.0, float(sim)))
        except (TypeError, ValueError):
            vec_comp = 0.0

    # Stage 16: depth-of-match bonus from the local retriever. A
    # facility that hits ten distinct strong capability terms must beat
    # a facility that hits one. Saturate at _LOCAL_RELEVANCE_SAT so the
    # bonus is bounded.
    try:
        local_score = float(candidate.get("local_relevance_score") or 0.0)
    except (TypeError, ValueError):
        local_score = 0.0
    if _LOCAL_RELEVANCE_SAT > 0:
        local_ratio = max(0.0, min(1.0, local_score / _LOCAL_RELEVANCE_SAT))
    else:
        local_ratio = 0.0
    local_comp = _W_LOCAL_RELEVANCE * local_ratio

    final = (
        trust_comp + readiness_comp + cap_comp + evidence_comp +
        val_penalty + warning_penalty + vec_comp + local_comp
    )
    final = max(0.0, min(1.0, final))

    sb = ScoreBreakdown(
        trust_score_component=round(trust_comp, 4),
        readiness_component=round(readiness_comp, 4),
        # Stage 16: capability_match_component now folds in the local
        # depth-of-match bonus so a single ScoreBreakdown row still
        # describes "how well does this facility match the asked-for
        # capability". Schema unchanged for backward-compat.
        capability_match_component=round(cap_comp + local_comp, 4),
        evidence_strength_component=round(evidence_comp, 4),
        validation_penalty=round(val_penalty, 4),
        warning_penalty=round(warning_penalty, 4),
        vector_similarity_component=round(vec_comp, 4),
        tavily_verification_component=0.0,
        final_score=round(final, 4),
    )
    candidate["score_breakdown"] = sb
    return sb


def _apply_tavily_to_score(candidate: dict, web_score: float) -> None:
    """Add the Tavily component to an existing breakdown and re-clip."""
    sb: Optional[ScoreBreakdown] = candidate.get("score_breakdown")
    if sb is None:
        return
    bonus = _W_TAVILY * max(0.0, min(1.0, float(web_score or 0.0)))
    sb.tavily_verification_component = round(bonus, 4)
    sb.final_score = round(min(1.0, max(0.0, sb.final_score + bonus)), 4)


# ---------------------------------------------------------------------------
# Reason / next-steps text
# ---------------------------------------------------------------------------

def _build_reason_for_recommendation(candidate: dict, intent: AgentIntent) -> str:
    parts: list[str] = []
    record = candidate["raw_record"]
    matched = candidate.get("matched_capabilities") or []
    snippets = candidate.get("evidence_snippets") or []
    web = candidate.get("web_verification")
    sim = candidate.get("vector_similarity")

    if matched:
        parts.append(f"matches {', '.join(matched)} capability evidence")
    strong_count = sum(1 for s in snippets if s.support_level == "strong")
    if strong_count:
        parts.append(f"{strong_count} strong evidence snippet(s)")

    trust_cat = (record.get("trust_category") or "").strip()
    if trust_cat:
        parts.append(f"trust category: {trust_cat}")

    if sim is not None:
        parts.append(f"semantic similarity {round(float(sim), 2)}")

    if web is not None and getattr(web, "verification_status", "") == "verified":
        # Stage 16: distinguish identity-only verification from
        # capability-confirming verification. Tavily can confirm a
        # facility exists at the given location without saying anything
        # about whether it actually performs the requested capability.
        web_caps = list(getattr(web, "matched_capability", []) or [])
        score_str = round(float(web.verification_score), 2)
        if web_caps:
            parts.append(
                f"web-verified for {', '.join(web_caps)} ({score_str})"
            )
        else:
            parts.append(
                f"web-verified identity/location only — "
                f"clinical capability not confirmed online ({score_str})"
            )

    if not parts:
        try:
            ts = float(record.get("trust_score") or 0.0)
        except (TypeError, ValueError):
            ts = 0.0
        return f"Retrieved by name/location match (trust score {ts:.2f})."
    return "Recommended because: " + "; ".join(parts) + "."


def _build_human_next_steps(candidate: dict, intent: AgentIntent) -> list[str]:
    steps: list[str] = []
    findings = candidate.get("validation_findings") or []
    web = candidate.get("web_verification")

    has_high   = any(f.severity == SEVERITY_HIGH for f in findings)
    has_medium = any(f.severity == SEVERITY_MEDIUM for f in findings)
    has_contradiction = any(
        f.finding_type == FINDING_CONTRADICTION for f in findings
    )

    if has_high or has_contradiction:
        steps.append(
            "Verify the claimed capabilities directly with the facility "
            "before recommending — at least one validation finding is high severity."
        )
    elif has_medium:
        steps.append(
            "Confirm capabilities and current availability with the facility "
            "before referral."
        )

    if web is None or getattr(web, "verification_status", "skipped") in ("skipped", "error"):
        steps.append(
            "Optional: enable Tavily web verification for an external sanity "
            "check on this facility's online presence."
        )
    elif web.verification_status == "unverified":
        steps.append(
            "Cross-check the facility's official website or Google Business "
            "listing — Tavily found no strong public evidence."
        )
    elif web.verification_status == "partial":
        steps.append(
            "Web evidence is partial — verify the specific capability claims "
            "in person or by phone."
        )
    elif web.verification_status == "verified":
        # Stage 16: when Tavily confirms identity but no clinical
        # capability term is matched in the web snippets, surface that
        # gap so a human knows to phone-confirm the capability.
        web_caps = list(getattr(web, "matched_capability", []) or [])
        if not web_caps:
            steps.append(
                "Web verification confirmed identity/location only — call "
                "the facility directly to confirm the clinical capability "
                "(equipment, staff, on-site availability)."
            )

    if intent.urgency == "emergency":
        steps.append(
            "EMERGENCY: call the facility's casualty/24x7 number now to confirm "
            "they can accept the patient before transit."
        )

    if not steps:
        steps.append(
            "Confirm appointment availability and current capacity with the "
            "facility before booking."
        )
    return steps


# ---------------------------------------------------------------------------
# Reasoning + fallback text
# ---------------------------------------------------------------------------

def _build_reasoning(
    intent: AgentIntent,
    retrieval_summary: dict,
    recommendations: list[AgentRecommendation],
) -> str:
    cap = ", ".join(intent.capabilities_required) if intent.capabilities_required else "none specified"
    loc = intent.city or intent.state or "anywhere"
    ftype = intent.facility_type or "any"
    parts = [
        f"Parsed intent: capabilities=[{cap}], location={loc}, facility_type={ftype}, "
        f"trust_preference={intent.trust_preference}, urgency={intent.urgency}.",
        (
            f"Retrieval: local={retrieval_summary.get('local_count', 0)}, "
            f"vector={retrieval_summary.get('vector_count', 0)}, "
            f"merged={retrieval_summary.get('merged_count', 0)}."
        ),
    ]
    if recommendations:
        top = recommendations[0]
        score = top.score_breakdown.final_score if top.score_breakdown else 0.0
        parts.append(
            f"Top result: {top.name or top.facility_id} (final_score={score:.3f})."
        )
    else:
        parts.append("No candidates passed the scoring threshold.")
    return " ".join(parts)


def _build_fallback_message(
    intent: AgentIntent,
    recommendations: list,
    retrieval_summary: dict,
) -> str:
    if recommendations:
        return ""
    fragments = ["No facilities matched all your filters."]
    tried: list[str] = []
    if intent.state:
        tried.append(f"state '{intent.state}'")
    if intent.city:
        tried.append(f"city '{intent.city}'")
    if intent.facility_type:
        tried.append(f"facility_type '{intent.facility_type}'")
    if intent.min_trust_score is not None:
        tried.append(f"min_trust_score >= {intent.min_trust_score}")
    if tried:
        fragments.append("Tried: " + ", ".join(tried) + ".")
    fragments.append(
        "Consider relaxing filters (broader location or lower trust threshold), "
        "or rephrasing the capability terms (e.g. use 'dialysis' instead of "
        "'renal therapy')."
    )
    return " ".join(fragments)


# ---------------------------------------------------------------------------
# Build AgentRecommendation from internal candidate dict
# ---------------------------------------------------------------------------

def _to_agent_recommendation(
    candidate: dict,
    intent: AgentIntent,
) -> AgentRecommendation:
    record = candidate["raw_record"]
    facility_id = str(candidate.get("facility_id") or record.get("facility_id") or "")

    try:
        trust_score = float(record.get("trust_score") or 0.0)
    except (TypeError, ValueError):
        trust_score = 0.0

    snippets: list[EvidenceSnippet] = candidate.get("evidence_snippets") or []
    findings: list[ValidationFinding] = candidate.get("validation_findings") or []

    reason = _build_reason_for_recommendation(candidate, intent)
    steps  = _build_human_next_steps(candidate, intent)

    return AgentRecommendation(
        facility_id=facility_id,
        name=str(record.get("name") or "").strip(),
        trust_score=trust_score,
        trust_category=str(record.get("trust_category") or "").strip(),
        recommendation_readiness=str(record.get("recommendation_readiness") or "").strip(),
        evidence_snippets=snippets,
        warnings=list(candidate.get("warning_flags") or []),
        web_verification=candidate.get("web_verification"),
        # Stage 13 fields
        facility_type=str(record.get("facility_type") or "").strip(),
        city=str(record.get("city") or "").strip(),
        state=str(record.get("state") or "").strip(),
        matched_capabilities=list(candidate.get("matched_capabilities") or []),
        matched_fields=list(candidate.get("matched_fields") or []),
        validation_findings=findings,
        warning_flags=list(candidate.get("warning_flags") or []),
        score_breakdown=candidate.get("score_breakdown"),
        reason_for_recommendation=reason,
        human_next_steps=steps,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_recommendation(
    query: str,
    facilities_df: pd.DataFrame,
    state: Optional[str] = None,
    facility_type: Optional[str] = None,
    min_trust_score: Optional[float] = None,
    max_results: int = 5,
    enable_vector_search: bool = False,
    enable_web_verification: bool = False,
    web_verification_depth: str = DEPTH_BASIC,
    max_web_verified: int = 3,
    *,
    settings: Any = None,
    vector_retriever: Any = None,
    tavily_cache: Any = None,
    tavily_client_factory: Optional[Callable[[str], Any]] = None,
    audit_logger: Optional[AuditLogger] = None,
) -> AgentResponse:
    """End-to-end agent pipeline. See module docstring for stages.

    Notes
    -----
    - Never raises. Unexpected errors in any stage are caught, logged
      onto ``trace_summary``, and the pipeline degrades gracefully.
    - When ``enable_vector_search`` is False (the default), the vector
      stage is skipped entirely — no Databricks dependency is loaded.
    - When ``enable_web_verification`` is False (the default), Tavily is
      skipped and ``credits_estimated`` stays at zero.
    """
    safe_query = "" if query is None else str(query)
    logger = audit_logger if audit_logger is not None else AuditLogger(persist=False)
    trace_errors: list[dict] = []
    trace_stages: list[dict] = []

    # ------------------------------------------------------------------
    # 1. Parse intent
    # ------------------------------------------------------------------
    try:
        intent = parse_query_intent(safe_query)
    except Exception as exc:  # noqa: BLE001
        intent = AgentIntent(raw_query=safe_query, original_query=safe_query)
        trace_errors.append({"stage": "intent_parse", "error": _short(exc)})

    intent = _apply_intent_overrides(
        intent,
        state=state,
        facility_type=facility_type,
        min_trust_score=min_trust_score,
    )
    logger.log("intent_parsed", _intent_summary(intent))
    trace_stages.append({"stage": "intent_parsed"})

    # ------------------------------------------------------------------
    # 2. Local retrieval
    # ------------------------------------------------------------------
    try:
        local_cands = retrieve_local_candidates(
            facilities_df, intent, limit_pool=_LOCAL_LIMIT_POOL,
        )
    except Exception as exc:  # noqa: BLE001
        local_cands = []
        trace_errors.append({"stage": "local_retrieval", "error": _short(exc)})
    logger.log("local_retrieval", {"count": len(local_cands)})
    trace_stages.append({"stage": "local_retrieval", "count": len(local_cands)})

    # ------------------------------------------------------------------
    # 3. Optional vector retrieval
    # ------------------------------------------------------------------
    vector_results: list = []
    vector_available = False
    vector_reason = "vector_search_disabled"

    vector_filter_applied = False
    vector_endpoint = ""
    vector_index = ""
    vector_filters_used: dict | None = None

    if enable_vector_search:
        try:
            vr = vector_retriever or _build_default_vector_retriever(settings)
            # Stage 17: when the user has narrowed the intent down to a
            # specific state, push that filter into the vector index so
            # we don't waste top-k slots on out-of-state hits. The main
            # team confirmed ``filters={"state": "<Name>"}`` works
            # against the live workspace; the retriever falls back to
            # an unfiltered query if the SDK build refuses the kwarg.
            vector_filters_used = _build_vector_filters(intent)
            response = vr.search(
                query=safe_query,
                filters=vector_filters_used,
                num_results=_VECTOR_NUM_RESULTS,
            )
            vector_available = bool(getattr(response, "available", False))
            vector_reason = str(getattr(response, "reason", "") or "")
            vector_filter_applied = bool(getattr(response, "filter_applied", False))
            vector_endpoint = str(getattr(response, "endpoint", "") or "")
            vector_index = str(getattr(response, "index", "") or "")
            if vector_available:
                vector_results = list(getattr(response, "results", []) or [])
        except Exception as exc:  # noqa: BLE001
            vector_available = False
            vector_reason = f"vector_call_failed: {_short(exc)}"
            trace_errors.append({"stage": "vector_retrieval", "error": _short(exc)})

    logger.log(
        "vector_retrieval",
        {
            "enabled": enable_vector_search,
            "available": vector_available,
            "count": len(vector_results),
            "reason": vector_reason,
            "filter_applied": vector_filter_applied,
            "filters_requested": bool(vector_filters_used),
        },
    )
    trace_stages.append(
        {
            "stage": "vector_retrieval",
            "enabled": enable_vector_search,
            "available": vector_available,
            "count": len(vector_results),
            "filter_applied": vector_filter_applied,
        }
    )

    # ------------------------------------------------------------------
    # 4. Merge
    # ------------------------------------------------------------------
    try:
        merged = _merge_candidates(local_cands, vector_results, facilities_df)
    except Exception as exc:  # noqa: BLE001
        merged = [_candidate_from_local(lc) for lc in local_cands]
        trace_errors.append({"stage": "merge", "error": _short(exc)})
    logger.log("merge", {"count": len(merged)})
    trace_stages.append({"stage": "merge", "count": len(merged)})

    # ------------------------------------------------------------------
    # 5 + 6. Evidence snippets + validation findings
    # ------------------------------------------------------------------
    enriched = _enrich_candidates(merged, intent)
    logger.log(
        "enrich",
        {
            "snippets_total": sum(len(c["evidence_snippets"]) for c in enriched),
            "findings_total": sum(len(c["validation_findings"]) for c in enriched),
        },
    )
    trace_stages.append({"stage": "enrich"})

    # ------------------------------------------------------------------
    # 7. Score + rank + truncate
    # ------------------------------------------------------------------
    for c in enriched:
        try:
            _score_candidate(c, intent)
        except Exception as exc:  # noqa: BLE001
            c["score_breakdown"] = ScoreBreakdown()
            trace_errors.append(
                {"stage": "score", "facility_id": c.get("facility_id"), "error": _short(exc)}
            )
    enriched.sort(
        key=lambda c: (
            c["score_breakdown"].final_score if c.get("score_breakdown") else 0.0
        ),
        reverse=True,
    )
    n_results = max(0, int(max_results))
    top = enriched[:n_results]
    logger.log("score_and_rank", {"top_count": len(top)})
    trace_stages.append({"stage": "score_and_rank", "top_count": len(top)})

    # ------------------------------------------------------------------
    # 8. Optional Tavily verification of the top recommendations
    # ------------------------------------------------------------------
    web_verified_count = 0
    web_total_credits = 0
    if enable_web_verification and top:
        # Tavily helper does flat attribute lookups (`rec.name`, `rec.city`,
        # ...). Build a thin list of dicts with the fields it needs.
        tavily_payload = [
            {
                "facility_id": c["facility_id"],
                "name": str(c["raw_record"].get("name") or "").strip(),
                "city": str(c["raw_record"].get("city") or "").strip() or None,
                "state": str(c["raw_record"].get("state") or "").strip() or None,
                "requested_capabilities": list(intent.capabilities_required or []),
            }
            for c in top
        ]
        try:
            web_results = verify_top_recommendations(
                tavily_payload,
                max_to_verify=max(0, int(max_web_verified)),
                depth=web_verification_depth,
                city=intent.city,
                state=intent.state,
                requested_capabilities=list(intent.capabilities_required or []),
                settings=settings or _get_settings(),
                cache=tavily_cache,
                client_factory=tavily_client_factory,
            )
        except Exception as exc:  # noqa: BLE001
            web_results = []
            trace_errors.append({"stage": "tavily_verify", "error": _short(exc)})

        web_by_id = {r.facility_id: r for r in web_results if r is not None}
        for c in top:
            web = web_by_id.get(c["facility_id"])
            if web is None:
                continue
            c["web_verification"] = web
            web_verified_count += 1
            web_total_credits += int(web.credits_estimated or 0)
            _apply_tavily_to_score(c, web.verification_score)

        # Tavily may flip the order — re-sort by final_score.
        top.sort(
            key=lambda c: (
                c["score_breakdown"].final_score if c.get("score_breakdown") else 0.0
            ),
            reverse=True,
        )

    logger.log(
        "tavily_verification",
        {
            "enabled": enable_web_verification,
            "verified_count": web_verified_count,
            "credits_estimated": web_total_credits,
        },
    )
    trace_stages.append(
        {
            "stage": "tavily_verification",
            "enabled": enable_web_verification,
            "verified_count": web_verified_count,
        }
    )

    # ------------------------------------------------------------------
    # 9. Build response
    # ------------------------------------------------------------------
    recommendations = [_to_agent_recommendation(c, intent) for c in top]

    retrieval_summary = {
        "local_count":  len(local_cands),
        "vector_enabled": enable_vector_search,
        "vector_available": vector_available,
        "vector_count": len(vector_results),
        "vector_reason": vector_reason,
        "vector_filter_applied": vector_filter_applied,
        "vector_filters_requested": dict(vector_filters_used or {}),
        "vector_endpoint": vector_endpoint,
        "vector_index":    vector_index,
        "merged_count": len(enriched),
        "after_top_k_count": len(top),
        "relaxation_used": any(c.get("relaxation_notes") for c in enriched),
        # Stage 18: surface the Tavily summary alongside the vector
        # summary so a single dict tells the operator what each retrieval
        # arm produced. The same numbers are also in
        # ``trace_summary["tavily"]`` (kept for backward compatibility).
        "web_verification_enabled": enable_web_verification,
        "tavily_verified_count":    web_verified_count,
        "tavily_depth":             web_verification_depth,
        "tavily_credits_estimated": web_total_credits,
    }
    fallback_message = _build_fallback_message(
        intent, recommendations, retrieval_summary,
    )
    reasoning = _build_reasoning(intent, retrieval_summary, recommendations)

    flat_evidence: list[EvidenceSnippet] = []
    flat_findings: list[ValidationFinding] = []
    for c in top:
        flat_evidence.extend(c["evidence_snippets"])
        flat_findings.extend(c["validation_findings"])

    # Stage 18: append the final-response marker to ``trace_stages``
    # *before* we wrap them into ``trace_summary`` so every stage in
    # the contract (intent_parsed → final_response) is visible in
    # ``trace_summary["stages"]``. The audit logger also records the
    # same event for downstream replay.
    trace_stages.append(
        {
            "stage": "final_response",
            "returned": len(recommendations),
            "had_fallback": bool(fallback_message),
        }
    )

    trace_summary = {
        "stages": trace_stages,
        "errors": trace_errors,
        "audit_log": logger.to_summary(),
        "tavily": {
            "enabled": enable_web_verification,
            "verified": web_verified_count,
            "credits_estimated": web_total_credits,
            "depth": web_verification_depth,
        },
        "vector": {
            "enabled": enable_vector_search,
            "available": vector_available,
            "reason": vector_reason,
            "filter_applied": vector_filter_applied,
            "filters_requested": dict(vector_filters_used or {}),
            "endpoint": vector_endpoint,
            "index":    vector_index,
            "count":    len(vector_results),
        },
    }

    response = AgentResponse(
        query=safe_query,
        intent=intent,
        interpreted_intent=intent,
        recommendations=recommendations,
        evidence=flat_evidence,
        warnings=[],
        reasoning=reasoning,
        safety_note=SAFETY_NOTE,
        validation_findings=flat_findings,
        retrieval_summary=retrieval_summary,
        total_candidates=len(enriched),
        returned=len(recommendations),
        fallback_message=fallback_message,
        trace_summary=trace_summary,
    )
    logger.log(
        "final_response",
        {
            "returned": response.returned,
            "total_candidates": response.total_candidates,
            "had_fallback": bool(fallback_message),
        },
    )
    return response


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _build_default_vector_retriever(settings: Any) -> Any:
    """Construct a real VectorRetriever from settings (lazy import)."""
    from agent_core.vector_retriever import VectorRetriever  # noqa: WPS433
    return VectorRetriever(settings or _get_settings())


def _build_vector_filters(intent: AgentIntent) -> Optional[dict]:
    """Translate the parsed intent into a Databricks vector-search filter dict.

    Stage 17 contract from the main team: ``filters={"state": "Bihar"}``
    is the call shape that works against the live workspace. We push
    only ``state`` here — it's the one filter the team validated; every
    other narrowing is done locally so a filter mismatch can never
    silently drop results we need.

    Returns ``None`` when there's nothing useful to push, so the
    retriever can skip the filtered code path entirely.
    """
    state = (intent.state or "").strip()
    if not state:
        return None
    return {"state": state}


def _short(exc: BaseException) -> str:
    """Render an exception as a single-line, short, log-safe string."""
    msg = f"{type(exc).__name__}: {exc}"
    return msg.replace("\n", " ").replace("\r", " ").strip()[:200]


# ---------------------------------------------------------------------------
# Backward compatibility — original Stage-1 stub
# ---------------------------------------------------------------------------

def recommend(
    df: pd.DataFrame,
    trust_score_threshold: float = 0.6,
    top_k: int = 10,
) -> pd.DataFrame:
    """Original simple ranker. Kept so the Stage-1 tests still pass."""
    if "trust_score" not in df.columns:
        return df.head(top_k)
    filtered = df[df["trust_score"] >= trust_score_threshold]
    return filtered.sort_values("trust_score", ascending=False).head(top_k)
