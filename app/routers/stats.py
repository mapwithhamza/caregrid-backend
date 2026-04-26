from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app.data_loader import data_store
from app.models import (
    DashboardOverview,
    FacilityTypeSummaryItem,
    ReadinessDistributionItem,
    StateSummaryItem,
    TrustDistributionItem,
    clean_nan,
)


router = APIRouter()

STATE_SORT_FIELDS = {
    "total_facilities",
    "avg_trust_score",
    "high_risk_percent",
    "ready_percent",
    "ready_for_recommendation",
}


def _load_stats_or_503(loader_name: str) -> pd.DataFrame:
    try:
        loader = getattr(data_store, loader_name)
        return loader()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _row_payload(row: pd.Series) -> dict[str, Any]:
    return {column: clean_nan(row[column]) for column in row.index}


def _records(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    return [_row_payload(row) for _, row in dataframe.iterrows()]


@router.get("/overview", response_model=DashboardOverview)
def get_stats_overview() -> DashboardOverview:
    overview = _load_stats_or_503("load_overview")
    if overview.empty:
        raise HTTPException(status_code=503, detail="Dashboard overview CSV is empty.")

    return DashboardOverview(**_row_payload(overview.iloc[0]))


@router.get("/trust-distribution", response_model=list[TrustDistributionItem])
def get_trust_distribution() -> list[TrustDistributionItem]:
    distribution = _load_stats_or_503("load_trust_distribution")
    distribution = distribution.sort_values(
        by="facility_count",
        ascending=False,
        kind="stable",
    )

    return [TrustDistributionItem(**record) for record in _records(distribution)]


@router.get("/readiness-distribution", response_model=list[ReadinessDistributionItem])
def get_readiness_distribution() -> list[ReadinessDistributionItem]:
    distribution = _load_stats_or_503("load_readiness_distribution")
    distribution = distribution.sort_values(
        by="facility_count",
        ascending=False,
        kind="stable",
    )

    return [ReadinessDistributionItem(**record) for record in _records(distribution)]


@router.get("/states", response_model=list[StateSummaryItem])
def get_state_summaries(
    sort_by: str = Query(default="total_facilities"),
    order: str = Query(default="desc"),
    limit: Optional[int] = Query(default=None, ge=1, le=100),
) -> list[StateSummaryItem]:
    if sort_by not in STATE_SORT_FIELDS:
        allowed_fields = ", ".join(sorted(STATE_SORT_FIELDS))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by value. Allowed values: {allowed_fields}.",
        )

    if order not in {"asc", "desc"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid order value. Allowed values: asc, desc.",
        )

    states = _load_stats_or_503("load_state_summary")
    sorted_states = states.sort_values(
        by=sort_by,
        ascending=order == "asc",
        kind="stable",
        na_position="last",
    )

    if limit is not None:
        sorted_states = sorted_states.head(limit)

    return [StateSummaryItem(**record) for record in _records(sorted_states)]


@router.get("/facility-types", response_model=list[FacilityTypeSummaryItem])
def get_facility_type_summaries() -> list[FacilityTypeSummaryItem]:
    facility_types = _load_stats_or_503("load_facility_type_summary")
    facility_types = facility_types.sort_values(
        by="facility_count",
        ascending=False,
        kind="stable",
    )

    return [FacilityTypeSummaryItem(**record) for record in _records(facility_types)]
