from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.data_loader import data_store
from app.models import SearchResponse, SearchResultItem, clean_nan


router = APIRouter()

SEARCH_FIELD_WEIGHTS = {
    "name": 5,
    "specialties": 4,
    "capabilities_raw": 4,
    "procedures": 3,
    "equipment": 3,
    "city": 2,
    "state": 2,
    "combined_medical_evidence": 1,
    "evidence_summary": 1,
}

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


def _load_facilities_or_503() -> pd.DataFrame:
    try:
        return data_store.load_facilities()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _text_contains(value: Any, query: str) -> bool:
    cleaned_value = clean_nan(value)
    if cleaned_value is None:
        return False

    return query in str(cleaned_value).casefold()


def _filter_case_insensitive(
    dataframe: pd.DataFrame,
    column: str,
    value: Optional[str],
) -> pd.DataFrame:
    if value is None:
        return dataframe

    return dataframe[dataframe[column].fillna("").astype(str).str.casefold() == value.casefold()]


def _score_row(row: pd.Series, query: str) -> tuple[float, list[str]]:
    relevance_score = 0.0
    matched_fields: list[str] = []

    for field, weight in SEARCH_FIELD_WEIGHTS.items():
        if _text_contains(row[field], query):
            relevance_score += weight
            matched_fields.append(field)

    if row["recommendation_readiness"] == "Ready for recommendation":
        relevance_score += 3
    elif row["recommendation_readiness"] == "Usable with verification":
        relevance_score += 2

    if row["trust_category"] == "High Trust / Evidence Supported":
        relevance_score += 3
    elif row["trust_category"] == "Moderate Trust / Verify Before Use":
        relevance_score += 1

    return relevance_score, matched_fields


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


def _result_payload(row: pd.Series) -> dict[str, Any]:
    return {field: clean_nan(row[field]) for field in RESULT_FIELDS}


@router.get("", response_model=SearchResponse)
def search_facilities(
    q: str,
    state: Optional[str] = None,
    facility_type: Optional[str] = None,
    trust_category: Optional[str] = None,
    recommendation_readiness: Optional[str] = None,
    min_trust_score: Optional[float] = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query q cannot be empty.")

    if min_trust_score is not None and not 0 <= min_trust_score <= 100:
        raise HTTPException(
            status_code=400,
            detail="min_trust_score must be between 0 and 100.",
        )

    facilities = _load_facilities_or_503()
    filtered = _filter_case_insensitive(facilities, "state", state)
    filtered = _filter_case_insensitive(filtered, "facility_type", facility_type)

    if trust_category is not None:
        filtered = filtered[filtered["trust_category"] == trust_category]

    if recommendation_readiness is not None:
        filtered = filtered[
            filtered["recommendation_readiness"] == recommendation_readiness
        ]

    if min_trust_score is not None:
        filtered = filtered[filtered["trust_score"] >= min_trust_score]

    scored_rows: list[dict[str, Any]] = []
    normalized_query = query.casefold()

    for index, row in filtered.iterrows():
        relevance_score, matched_fields = _score_row(row, normalized_query)
        if not matched_fields:
            continue

        scored_rows.append(
            {
                "index": index,
                "relevance_score": relevance_score,
                "matched_fields": matched_fields,
                "trust_score": clean_nan(row["trust_score"]) or 0,
                "name": clean_nan(row["name"]) or "",
            }
        )

    scored_rows.sort(
        key=lambda item: (
            -item["relevance_score"],
            -item["trust_score"],
            str(item["name"]).casefold(),
        )
    )

    limited_rows = scored_rows[:limit]
    results = []
    for scored_row in limited_rows:
        row = filtered.loc[scored_row["index"]]
        payload = _result_payload(row)
        payload["relevance_score"] = scored_row["relevance_score"]
        payload["matched_fields"] = scored_row["matched_fields"]
        payload["warning_flags"] = _warning_flags(row)
        results.append(SearchResultItem(**payload))

    return SearchResponse(
        query=query,
        total_matches=len(scored_rows),
        returned=len(results),
        results=results,
        applied_filters={
            "state": state,
            "facility_type": facility_type,
            "trust_category": trust_category,
            "recommendation_readiness": recommendation_readiness,
            "min_trust_score": min_trust_score,
        },
    )
