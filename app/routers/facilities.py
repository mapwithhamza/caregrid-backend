import math
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.data_loader import data_store
from app.models import (
    FacilityDetail,
    FacilityFiltersMeta,
    FacilityListItem,
    PaginatedFacilitiesResponse,
    clean_nan,
    clean_pin_code,
)


router = APIRouter()


LIST_COLUMNS = [
    "facility_id",
    "name",
    "facility_type",
    "city",
    "state",
    "pin_code",
    "latitude",
    "longitude",
    "trust_score",
    "trust_category",
    "recommendation_readiness",
    "specialties",
    "evidence_summary",
    "flag_icu_claim_without_equipment",
    "flag_surgery_claim_without_support",
    "flag_dialysis_claim_without_machine",
    "flag_oncology_claim_without_support",
]

DETAIL_COLUMNS = [
    *LIST_COLUMNS,
    "phone",
    "email",
    "official_website",
    "websites",
    "procedures",
    "equipment",
    "capabilities_raw",
    "combined_medical_evidence",
    "evidence_length_chars",
    "v2_positive_score",
    "v2_total_penalty",
    "v2_identity_location_score",
    "v2_contact_verification_score",
    "v2_medical_evidence_score",
    "v2_digital_social_score",
    "v2_data_richness_score",
    "claims_emergency_or_high_acuity",
    "has_high_acuity_supporting_evidence",
]


def _load_facilities_or_503() -> pd.DataFrame:
    try:
        return data_store.load_facilities()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _row_payload(row: pd.Series, columns: list[str]) -> dict[str, Any]:
    payload = {column: clean_nan(row[column]) for column in columns}
    if "pin_code" in payload:
        payload["pin_code"] = clean_pin_code(payload["pin_code"])
    return payload


def _sorted_non_empty_unique(facilities: pd.DataFrame, column: str) -> list[str]:
    values = facilities[column].dropna().astype(str).str.strip()
    values = values[values != ""]
    return sorted(values.unique().tolist())


@router.get("", response_model=PaginatedFacilitiesResponse)
def list_facilities(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    state: Optional[str] = None,
    facility_type: Optional[str] = None,
    trust_category: Optional[str] = None,
    recommendation_readiness: Optional[str] = None,
    min_trust_score: Optional[float] = None,
    max_trust_score: Optional[float] = None,
) -> PaginatedFacilitiesResponse:
    if (
        min_trust_score is not None
        and max_trust_score is not None
        and min_trust_score > max_trust_score
    ):
        raise HTTPException(
            status_code=400,
            detail="min_trust_score cannot be greater than max_trust_score.",
        )

    facilities = _load_facilities_or_503()
    filtered = facilities

    if state:
        filtered = filtered[filtered["state"].str.casefold() == state.casefold()]

    if facility_type:
        filtered = filtered[
            filtered["facility_type"].fillna("").str.casefold() == facility_type.casefold()
        ]

    if trust_category:
        filtered = filtered[filtered["trust_category"] == trust_category]

    if recommendation_readiness:
        filtered = filtered[
            filtered["recommendation_readiness"] == recommendation_readiness
        ]

    if min_trust_score is not None:
        filtered = filtered[filtered["trust_score"] >= min_trust_score]

    if max_trust_score is not None:
        filtered = filtered[filtered["trust_score"] <= max_trust_score]

    sorted_facilities = filtered.sort_values(
        by=["trust_score", "name"],
        ascending=[False, True],
        na_position="last",
    )

    total = int(len(sorted_facilities))
    total_pages = math.ceil(total / limit) if total else 0
    start = (page - 1) * limit
    end = start + limit
    page_rows = sorted_facilities.iloc[start:end]
    results = [
        FacilityListItem(**_row_payload(row, LIST_COLUMNS))
        for _, row in page_rows.iterrows()
    ]

    return PaginatedFacilitiesResponse(
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        results=results,
    )


@router.get("/meta/filters", response_model=FacilityFiltersMeta)
def get_facility_filters_meta() -> FacilityFiltersMeta:
    facilities = _load_facilities_or_503()

    return FacilityFiltersMeta(
        states=_sorted_non_empty_unique(facilities, "state"),
        facility_types=_sorted_non_empty_unique(facilities, "facility_type"),
        trust_categories=_sorted_non_empty_unique(facilities, "trust_category"),
        recommendation_readiness_values=_sorted_non_empty_unique(
            facilities,
            "recommendation_readiness",
        ),
    )


@router.get("/{facility_id}", response_model=FacilityDetail)
def get_facility_detail(facility_id: str) -> FacilityDetail:
    facilities = _load_facilities_or_503()
    matches = facilities[facilities["facility_id"].astype(str) == facility_id]

    if matches.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Facility not found for facility_id: {facility_id}",
        )

    return FacilityDetail(**_row_payload(matches.iloc[0], DETAIL_COLUMNS))
