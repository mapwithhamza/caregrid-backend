from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.data_loader import data_store
from app.models import (
    FacilityTypeGapItem,
    PriorityStateItem,
    StateRiskIndexItem,
    TrustGapSummary,
    clean_nan,
)


router = APIRouter()

STATE_RISK_SORT_FIELDS = {
    "trust_desert_risk_index",
    "total_facilities",
    "avg_trust_score",
    "high_risk_percent",
    "ready_percent",
    "do_not_recommend_percent",
    "unsupported_high_acuity_percent",
}

FACILITY_TYPE_GAP_SORT_FIELDS = {
    "total_facilities",
    "avg_trust_score",
    "high_risk_percent",
    "ready_percent",
    "do_not_recommend_percent",
    "contradiction_percent",
}


def _load_impact_or_503(loader_name: str) -> pd.DataFrame:
    try:
        loader = getattr(data_store, loader_name)
        return loader()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _row_payload(row: pd.Series) -> dict[str, Any]:
    return {column: clean_nan(row[column]) for column in row.index}


def _records(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    return [_row_payload(row) for _, row in dataframe.iterrows()]


def _filter_case_insensitive(
    dataframe: pd.DataFrame,
    column: str,
    value: Optional[str],
) -> pd.DataFrame:
    if value is None:
        return dataframe

    return dataframe[dataframe[column].fillna("").astype(str).str.casefold() == value.casefold()]


def _filter_contains_case_insensitive(
    dataframe: pd.DataFrame,
    column: str,
    value: Optional[str],
) -> pd.DataFrame:
    if value is None:
        return dataframe

    return dataframe[
        dataframe[column].fillna("").astype(str).str.contains(value, case=False, regex=False)
    ]


def _validate_sort_by(sort_by: str, allowed_fields: set[str]) -> None:
    if sort_by not in allowed_fields:
        allowed = ", ".join(sorted(allowed_fields))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by value. Allowed values: {allowed}.",
        )


def _validate_order(order: str) -> None:
    if order not in {"asc", "desc"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid order value. Allowed values: asc, desc.",
        )


@router.get("/trust-gap-summary", response_model=TrustGapSummary)
def get_trust_gap_summary() -> TrustGapSummary:
    summary = _load_impact_or_503("load_trust_gap_summary")
    if summary.empty:
        raise HTTPException(status_code=503, detail="Trust gap summary CSV is empty.")

    return TrustGapSummary(**_row_payload(summary.iloc[0]))


@router.get("/priority-states", response_model=list[PriorityStateItem])
def get_priority_states(
    tier: Optional[str] = None,
    confidence: Optional[str] = None,
    limit: Optional[int] = Query(default=None, ge=1, le=100),
) -> list[PriorityStateItem]:
    priority_states = _load_impact_or_503("load_calibrated_priority_ranking")
    filtered = _filter_contains_case_insensitive(
        priority_states,
        "calibrated_priority_tier",
        tier,
    )
    filtered = _filter_case_insensitive(filtered, "analysis_confidence", confidence)
    sorted_states = filtered.sort_values(
        by="national_priority_rank",
        ascending=True,
        kind="stable",
        na_position="last",
    )

    if limit is not None:
        sorted_states = sorted_states.head(limit)

    return [PriorityStateItem(**record) for record in _records(sorted_states)]


@router.get("/state-risk-index", response_model=list[StateRiskIndexItem])
def get_state_risk_index(
    risk_level: Optional[str] = None,
    confidence: Optional[str] = None,
    sort_by: str = Query(default="trust_desert_risk_index"),
    order: str = Query(default="desc"),
    limit: Optional[int] = Query(default=None, ge=1, le=100),
) -> list[StateRiskIndexItem]:
    _validate_sort_by(sort_by, STATE_RISK_SORT_FIELDS)
    _validate_order(order)

    state_risk = _load_impact_or_503("load_state_risk_index")
    filtered = _filter_case_insensitive(state_risk, "risk_level", risk_level)
    filtered = _filter_case_insensitive(filtered, "analysis_confidence", confidence)
    sorted_states = filtered.sort_values(
        by=sort_by,
        ascending=order == "asc",
        kind="stable",
        na_position="last",
    )

    if limit is not None:
        sorted_states = sorted_states.head(limit)

    return [StateRiskIndexItem(**record) for record in _records(sorted_states)]


@router.get("/facility-type-gap", response_model=list[FacilityTypeGapItem])
def get_facility_type_gap(
    risk_level: Optional[str] = None,
    sort_by: str = Query(default="do_not_recommend_percent"),
    order: str = Query(default="desc"),
) -> list[FacilityTypeGapItem]:
    _validate_sort_by(sort_by, FACILITY_TYPE_GAP_SORT_FIELDS)
    _validate_order(order)

    facility_type_gap = _load_impact_or_503("load_facility_type_gap")
    filtered = _filter_case_insensitive(
        facility_type_gap,
        "facility_type_risk_level",
        risk_level,
    )
    sorted_gap = filtered.sort_values(
        by=sort_by,
        ascending=order == "asc",
        kind="stable",
        na_position="last",
    )

    return [FacilityTypeGapItem(**record) for record in _records(sorted_gap)]
