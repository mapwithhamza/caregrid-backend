import logging
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException

load_dotenv()  # load .env so GEMINI_API_KEY is available

from app.data_loader import data_store
from app.models import (
    AgentRecommendationItem,
    AgentRecommendRequest,
    AgentRecommendResponse,
    clean_nan,
)
from app.routers.agent_llm import get_ai_fields

# Import the advanced agent service -- safe fallback if not available
try:
    from app.services.caregrid_agent_service import (
        is_available as advanced_agent_available,
        run_advanced_recommendation,
    )
except Exception as _svc_import_err:  # noqa: BLE001
    logger.warning("Advanced agent service unavailable: %s", _svc_import_err)

    def advanced_agent_available() -> bool:  # type: ignore[misc]
        return False

    def run_advanced_recommendation(*args, **kwargs):  # type: ignore[misc]
        return None, "service not available"

logger = logging.getLogger(__name__)

router = APIRouter()

SAFETY_NOTE = (
    "CareGrid recommendations are evidence-based decision support only. Emergency medical "
    "decisions should be verified with local providers and official emergency channels."
)

CAPABILITY_KEYWORDS = {
    "ICU / critical care": ["icu", "intensive care", "critical care", "ventilator", "ventilators", "nicu"],
    "Emergency": ["emergency", "urgent", "trauma", "casualty", "accident", "24/7", "24x7"],
    "Dialysis": ["dialysis", "hemodialysis", "haemodialysis", "renal", "kidney"],
    "Oncology": ["oncology", "cancer", "chemotherapy", "radiotherapy", "radiation"],
    "Surgery": ["surgery", "surgical", "operation theatre", "operating theatre", "ot", "anesthesia", "anaesthesia"],
    "Maternal": ["maternity", "maternal", "delivery", "obstetric", "gynecology", "gynaecology", "pregnancy", "c-section"],
    "Neonatal / pediatric": ["neonatal", "newborn", "infant", "pediatrics", "paediatrics", "child", "children", "nicu"],
    "Diagnostics": ["diagnostics", "x-ray", "xray", "ct scan", "mri", "ultrasound", "pathology", "lab", "radiology"],
    "Ambulance": ["ambulance", "emergency transport", "paramedic"],
}

SEARCH_FIELDS = [
    "name",
    "city",
    "state",
    "facility_type",
    "specialties",
    "procedures",
    "equipment",
    "capabilities_raw",
    "evidence_summary",
    "combined_medical_evidence",
]

RESULT_FIELDS = [
    "facility_id",
    "name",
    "facility_type",
    "city",
    "state",
    "latitude",
    "longitude",
    "trust_score",
    "trust_category",
    "recommendation_readiness",
    "specialties",
    "evidence_summary",
]

STOP_WORDS = {
    "find",
    "show",
    "need",
    "needs",
    "facility",
    "facilities",
    "center",
    "centers",
    "centre",
    "centres",
    "hospital",
    "hospitals",
    "clinic",
    "clinics",
    "trusted",
    "verified",
    "reliable",
    "safe",
    "recommend",
    "best",
    "near",
    "nearest",
    "with",
}


def _load_facilities_or_503() -> pd.DataFrame:
    try:
        return data_store.load_facilities()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _text(value: Any) -> str:
    cleaned_value = clean_nan(value)
    if cleaned_value is None:
        return ""
    return str(cleaned_value)


def _row_text(row: pd.Series, fields: list[str] = SEARCH_FIELDS) -> str:
    return " ".join(_text(row[field]) for field in fields).casefold()


def _query_terms(query: str) -> list[str]:
    terms = []
    for raw_term in query.casefold().replace("/", " ").replace("-", " ").split():
        term = raw_term.strip(".,;:!?()[]{}")
        if len(term) > 2 and term not in STOP_WORDS:
            terms.append(term)
    return sorted(set(terms))


def _detect_capabilities(query: str) -> dict[str, list[str]]:
    normalized_query = query.casefold()
    detected: dict[str, list[str]] = {}
    for capability, keywords in CAPABILITY_KEYWORDS.items():
        matched_keywords = [keyword for keyword in keywords if keyword in normalized_query]
        if matched_keywords:
            detected[capability] = matched_keywords
    return detected


def _detect_state(query: str, facilities: pd.DataFrame, request_state: Optional[str]) -> Optional[str]:
    if request_state:
        return request_state

    normalized_query = query.casefold()
    states = facilities["state"].dropna().astype(str).unique().tolist()
    for state in sorted(states, key=len, reverse=True):
        if state.casefold() in normalized_query:
            return state
    return None


def _detect_facility_type(query: str, request_facility_type: Optional[str]) -> Optional[str]:
    if request_facility_type:
        return request_facility_type

    normalized_query = query.casefold()
    if "hospital" in normalized_query or "hospitals" in normalized_query:
        return "hospital"
    if "clinic" in normalized_query or "clinics" in normalized_query:
        return "clinic"
    if "doctor" in normalized_query or "doctors" in normalized_query:
        return "doctor"
    if "pharmacy" in normalized_query or "pharmacies" in normalized_query:
        return "pharmacy"
    return None


def _detect_trust_intent(query: str) -> dict[str, bool]:
    normalized_query = query.casefold()
    return {
        "prefer_trusted": any(
            phrase in normalized_query
            for phrase in ["trusted", "verified", "reliable", "high trust", "best"]
        ),
        "nearby_requested": "near" in normalized_query or "nearest" in normalized_query,
        "allow_verification_needed": "with warnings" in normalized_query
        or "needs verification" in normalized_query,
        "safe_or_recommend": "safe" in normalized_query or "recommend" in normalized_query,
    }


def _filter_case_insensitive(
    dataframe: pd.DataFrame,
    column: str,
    value: Optional[str],
) -> pd.DataFrame:
    if value is None:
        return dataframe
    return dataframe[dataframe[column].fillna("").astype(str).str.casefold() == value.casefold()]


def _is_truthy(value: Any) -> bool:
    cleaned_value = clean_nan(value)
    if cleaned_value is None:
        return False
    if isinstance(cleaned_value, bool):
        return cleaned_value
    if isinstance(cleaned_value, (int, float)):
        return bool(cleaned_value)
    return str(cleaned_value).strip().casefold() in {"true", "1", "yes"}


def _warning_flags(row: pd.Series) -> list[str]:
    warnings: list[str] = []
    if _is_truthy(row["flag_icu_claim_without_equipment"]):
        warnings.append("ICU claim needs equipment verification")
    if _is_truthy(row["flag_surgery_claim_without_support"]):
        warnings.append("Surgery claim needs OT/anesthesia verification")
    if _is_truthy(row["flag_dialysis_claim_without_machine"]):
        warnings.append("Dialysis claim needs machine verification")
    if _is_truthy(row["flag_oncology_claim_without_support"]):
        warnings.append("Oncology claim needs specialist/treatment verification")
    if _is_truthy(row["claims_emergency_or_high_acuity"]) and not _is_truthy(
        row["has_high_acuity_supporting_evidence"]
    ):
        warnings.append("High-acuity claim lacks supporting evidence")
    if row["recommendation_readiness"] == "Do not recommend without human review":
        warnings.append("Do not recommend without human review")
    return warnings


def _matched_fields(row: pd.Series, terms: list[str], capability_terms: list[str]) -> list[str]:
    needles = sorted(set(terms + capability_terms))
    matched = []
    for field in SEARCH_FIELDS:
        field_text = _text(row[field]).casefold()
        if any(needle in field_text for needle in needles):
            matched.append(field)
    return matched


def _matched_capabilities(row: pd.Series, detected_capabilities: dict[str, list[str]]) -> list[str]:
    text = _row_text(row)
    matched = []
    for capability, keywords in detected_capabilities.items():
        if any(keyword in text for keyword in keywords):
            matched.append(capability)
    return matched


def _recommendation_score(
    row: pd.Series,
    matched_capabilities: list[str],
    matched_fields: list[str],
    warnings: list[str],
) -> float:
    trust_score = clean_nan(row["trust_score"]) or 0
    score = float(trust_score) / 10

    if row["recommendation_readiness"] == "Ready for recommendation":
        score += 5
    elif row["recommendation_readiness"] == "Usable with verification":
        score += 3
    elif row["recommendation_readiness"] == "Do not recommend without human review":
        score -= 5

    if row["trust_category"] == "High Trust / Evidence Supported":
        score += 4
    elif row["trust_category"] == "Moderate Trust / Verify Before Use":
        score += 2

    score += min(len(matched_capabilities) * 4, 12)

    field_boosts = {
        "name": 2,
        "specialties": 2,
        "capabilities_raw": 2,
        "procedures": 1,
        "equipment": 1,
    }
    score += sum(field_boosts[field] for field in matched_fields if field in field_boosts)
    score -= min(len(warnings) * 3, 9)
    return round(score, 2)


def _reason_for_recommendation(
    row: pd.Series,
    matched_capabilities: list[str],
    warnings: list[str],
) -> str:
    capabilities = ", ".join(matched_capabilities) if matched_capabilities else "the query terms"
    trust_score = clean_nan(row["trust_score"])
    reason = (
        f"Selected because it matched {capabilities} with trust score {trust_score} "
        f"and readiness {row['recommendation_readiness']}."
    )
    if warnings:
        reason += " Warnings: " + "; ".join(warnings) + "."
    return reason


def _result_payload(row: pd.Series) -> dict[str, Any]:
    return {field: clean_nan(row[field]) for field in RESULT_FIELDS}


def _build_recommendations(
    facilities: pd.DataFrame,
    request: AgentRecommendRequest,
    state: Optional[str],
    facility_type: Optional[str],
    terms: list[str],
    detected_capabilities: dict[str, list[str]],
    trust_intent: dict[str, bool],
    relax_trust: bool = False,
    relax_facility_type: bool = False,
) -> list[AgentRecommendationItem]:
    filtered = _filter_case_insensitive(facilities, "state", state)
    if not relax_facility_type:
        filtered = _filter_case_insensitive(filtered, "facility_type", facility_type)

    min_trust_score = request.min_trust_score
    if min_trust_score is None and (trust_intent["prefer_trusted"] or trust_intent["safe_or_recommend"]):
        min_trust_score = 60

    if min_trust_score is not None and not relax_trust:
        filtered = filtered[filtered["trust_score"] >= min_trust_score]

    if trust_intent["safe_or_recommend"] and not relax_trust:
        filtered = filtered[
            filtered["recommendation_readiness"] != "Do not recommend without human review"
        ]

    capability_terms = [
        keyword
        for keywords in detected_capabilities.values()
        for keyword in keywords
    ]
    scored: list[AgentRecommendationItem] = []
    has_explicit_filter = state is not None or facility_type is not None

    for _, row in filtered.iterrows():
        matched_capabilities = _matched_capabilities(row, detected_capabilities)
        matched_fields = _matched_fields(row, terms, capability_terms)
        if not matched_capabilities and not matched_fields and not has_explicit_filter:
            continue

        warnings = _warning_flags(row)
        score = _recommendation_score(row, matched_capabilities, matched_fields, warnings)
        payload = _result_payload(row)
        payload["matched_capabilities"] = matched_capabilities
        payload["matched_fields"] = matched_fields
        payload["warning_flags"] = warnings
        payload["recommendation_score"] = score
        payload["reason_for_recommendation"] = _reason_for_recommendation(
            row,
            matched_capabilities,
            warnings,
        )
        scored.append(AgentRecommendationItem(**payload))

    scored.sort(
        key=lambda item: (
            -item.recommendation_score,
            -(item.trust_score or 0),
            item.name.casefold(),
        )
    )
    return scored


def _global_reasoning(
    detected_capabilities: dict[str, list[str]],
    trust_intent: dict[str, bool],
    state: Optional[str],
    facility_type: Optional[str],
    min_trust_score: Optional[float],
    total_candidates: int,
    fallback_message: Optional[str],
) -> str:
    capabilities = ", ".join(detected_capabilities) if detected_capabilities else "general facility search"
    filters = []
    if state:
        filters.append(f"state={state}")
    if facility_type:
        filters.append(f"facility_type={facility_type}")
    if min_trust_score is not None:
        filters.append(f"min_trust_score={min_trust_score}")
    elif trust_intent["prefer_trusted"] or trust_intent["safe_or_recommend"]:
        filters.append("default min_trust_score=60 for trusted/safe intent")

    reasoning = (
        f"Detected intent: {capabilities}. Applied filters: "
        f"{', '.join(filters) if filters else 'none'}. Found {total_candidates} candidate(s). "
        "Top recommendations are ranked by trust score, recommendation readiness, capability matches, "
        "field matches, and warning penalties."
    )
    if trust_intent["nearby_requested"]:
        reasoning += " Location proximity requires origin coordinates and was not calculated."
    if fallback_message:
        reasoning += " " + fallback_message
    return reasoning


def _build_advanced_response(
    *,
    request: AgentRecommendRequest,
    facilities: pd.DataFrame,
) -> Optional[AgentRecommendResponse]:
    """Try the upgraded standalone CareGrid agent. Return ``None`` on any
    failure so the caller can fall back to the legacy simple recommender."""

    enable_vector = request.resolved_enable_vector()
    enable_web = request.resolved_enable_web_verification()

    payload, error = run_advanced_recommendation(
        query=request.query.strip(),
        facilities_df=facilities,
        state=request.state,
        facility_type=request.facility_type,
        min_trust_score=request.min_trust_score,
        max_results=request.max_results,
        enable_vector_search=enable_vector,
        enable_web_verification=enable_web,
        web_verification_depth=(request.web_depth or "basic"),
        max_web_verified=(request.max_web_verified if request.max_web_verified is not None else 2),
    )

    if payload is None:
        logger.warning("Advanced agent returned no payload (%s); using legacy fallback.", error)
        return None

    interpreted_intent = payload.get("interpreted_intent") or payload.get("intent") or {}
    if not isinstance(interpreted_intent, dict):
        interpreted_intent = {}

    raw_recs = payload.get("recommendations") or []
    if not isinstance(raw_recs, list):
        raw_recs = []

    recommendations: list[AgentRecommendationItem] = []
    for raw in raw_recs:
        if not isinstance(raw, dict):
            continue
        try:
            recommendations.append(AgentRecommendationItem.model_validate(raw))
        except Exception:  # noqa: BLE001
            try:
                minimal = {
                    "facility_id": str(raw.get("facility_id", "")),
                    "name": str(raw.get("name", "")),
                    "state": str(raw.get("state", "")),
                    "trust_category": str(raw.get("trust_category", "")),
                    "recommendation_readiness": str(raw.get("recommendation_readiness", "")),
                    "matched_capabilities": raw.get("matched_capabilities") or [],
                    "matched_fields": raw.get("matched_fields") or [],
                    "warning_flags": raw.get("warning_flags") or raw.get("warnings") or [],
                    "recommendation_score": float(raw.get("recommendation_score", 0.0) or 0.0),
                    "reason_for_recommendation": str(raw.get("reason_for_recommendation", "")),
                }
                recommendations.append(AgentRecommendationItem.model_validate(minimal))
            except Exception:
                continue

    response = AgentRecommendResponse(
        query=str(payload.get("query") or request.query),
        interpreted_intent=interpreted_intent,
        total_candidates=int(payload.get("total_candidates") or len(recommendations)),
        returned=int(payload.get("returned") or len(recommendations)),
        recommendations=recommendations,
        reasoning=str(payload.get("reasoning") or "")
        or "Powered by the standalone CareGrid Vector Agent (local + optional vector + optional web verification).",
        safety_note=str(payload.get("safety_note") or SAFETY_NOTE),
        fallback_message=payload.get("fallback_message"),
        agent_mode="hybrid",
    )
    return response


@router.post("/recommend", response_model=AgentRecommendResponse)
def recommend_facilities(request: AgentRecommendRequest) -> AgentRecommendResponse:
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Recommendation query cannot be empty.")
    if request.min_trust_score is not None and not 0 <= request.min_trust_score <= 100:
        raise HTTPException(
            status_code=400,
            detail="min_trust_score must be between 0 and 100.",
        )

    facilities = _load_facilities_or_503()

    if advanced_agent_available():
        try:
            advanced_response = _build_advanced_response(request=request, facilities=facilities)
            if advanced_response is not None:
                return advanced_response
        except Exception as exc:  # noqa: BLE001
            logger.exception("Advanced agent path raised; falling back to legacy. (%s)", exc)

    state = _detect_state(query, facilities, request.state)
    facility_type = _detect_facility_type(query, request.facility_type)
    detected_capabilities = _detect_capabilities(query)
    trust_intent = _detect_trust_intent(query)
    terms = _query_terms(query)

    recommendations = _build_recommendations(
        facilities,
        request,
        state,
        facility_type,
        terms,
        detected_capabilities,
        trust_intent,
    )
    fallback_message = None

    if not recommendations:
        fallback_message = (
            "No strong result was found after strict filtering; retried with relaxed trust filtering."
        )
        recommendations = _build_recommendations(
            facilities,
            request,
            state,
            facility_type,
            terms,
            detected_capabilities,
            trust_intent,
            relax_trust=True,
        )
        if not recommendations and facility_type is not None:
            fallback_message = (
                "No strong result was found after strict facility_type filtering; "
                "retried with relaxed facility_type filtering."
            )
            recommendations = _build_recommendations(
                facilities,
                request,
                state,
                facility_type,
                terms,
                detected_capabilities,
                trust_intent,
                relax_trust=True,
                relax_facility_type=True,
            )
    elif len(recommendations) < request.max_results and trust_intent["safe_or_recommend"]:
        relaxed = _build_recommendations(
            facilities,
            request,
            state,
            facility_type,
            terms,
            detected_capabilities,
            trust_intent,
            relax_trust=True,
        )
        if len(relaxed) > len(recommendations):
            recommendations = relaxed
            fallback_message = "Included relaxed trust-filter results because strict results were limited."

    total_candidates = len(recommendations)
    limited_recommendations = recommendations[: request.max_results]
    if not limited_recommendations:
        fallback_message = "No matching facility was found in the current dataset."

    interpreted_intent: dict[str, Any] = {
        "capabilities": list(detected_capabilities.keys()),
        "capability_keywords": detected_capabilities,
        "state": state,
        "facility_type": facility_type,
        "facility_type_source": "request" if request.facility_type else "query" if facility_type else None,
        "prefer_trusted": trust_intent["prefer_trusted"],
        "safe_or_recommend": trust_intent["safe_or_recommend"],
        "nearby_requested": trust_intent["nearby_requested"],
        "allow_verification_needed": trust_intent["allow_verification_needed"],
    }

    # Serialize top recommendations for the Gemini prompt
    recs_as_dicts = [
        {
            "name": r.name,
            "facility_type": r.facility_type,
            "city": r.city,
            "state": r.state,
            "trust_score": r.trust_score,
            "trust_category": r.trust_category,
            "recommendation_readiness": r.recommendation_readiness,
            "matched_capabilities": r.matched_capabilities,
            "warning_flags": r.warning_flags,
            "evidence_summary": r.evidence_summary,
        }
        for r in limited_recommendations
    ]

    # Call Gemini for AI summary (gracefully returns None fields if key missing/fails)
    ai_fields = get_ai_fields(query, recs_as_dicts)

    return AgentRecommendResponse(
        query=query,
        interpreted_intent=interpreted_intent,
        total_candidates=total_candidates,
        returned=len(limited_recommendations),
        recommendations=limited_recommendations,
        reasoning=_global_reasoning(
            detected_capabilities,
            trust_intent,
            state,
            facility_type,
            request.min_trust_score,
            total_candidates,
            fallback_message,
        ),
        safety_note=SAFETY_NOTE,
        fallback_message=fallback_message,
        # AI fields from Gemini (all Optional -- safe when not set)
        agent_mode=ai_fields.get("agent_mode", "rule-based"),
        model_used=ai_fields.get("model_used"),
        model_provider=ai_fields.get("model_provider"),
        ai_summary=ai_fields.get("ai_summary"),
        ai_reasoning=ai_fields.get("ai_reasoning"),
        ai_next_steps=ai_fields.get("ai_next_steps"),
    )
