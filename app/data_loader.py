from pathlib import Path
from typing import Any

import pandas as pd

from app.config import (
    ALLOWED_RECOMMENDATION_READINESS,
    ALLOWED_TRUST_CATEGORIES,
    CSV_FILENAMES,
    DASHBOARD_OVERVIEW_CSV,
    DATA_DIR,
    DESERT_CALIBRATED_PRIORITY_RANKING_CSV,
    DESERT_FACILITY_TYPE_GAP_CSV,
    DESERT_PRIORITY_STATES_CSV,
    DESERT_STATE_RISK_INDEX_CSV,
    DESERT_TRUST_GAP_SUMMARY_CSV,
    EXPECTED_ROW_COUNTS,
    FACILITY_TYPE_SUMMARY_CSV,
    MAIN_FACILITY_CSV,
    READINESS_DISTRIBUTION_CSV,
    REQUIRED_FACILITY_COLUMNS,
    STATE_SUMMARY_CSV,
    TRUST_DISTRIBUTION_CSV,
)


class DataStore:
    """Loads and validates the real CareGrid CSV exports without changing columns."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self._cache: dict[str, pd.DataFrame] = {}
        self.validation_summary: dict[str, Any] | None = None
        self.last_error: str | None = None

    @property
    def is_loaded(self) -> bool:
        return all(filename in self._cache for filename in CSV_FILENAMES)

    @property
    def is_validated(self) -> bool:
        return self.validation_summary is not None and self.validation_summary["status"] == "valid"

    def _csv_path(self, filename: str) -> Path:
        return self.data_dir / filename

    def _load_csv(self, filename: str) -> pd.DataFrame:
        if filename in self._cache:
            return self._cache[filename]

        path = self._csv_path(filename)
        if not path.exists():
            raise FileNotFoundError(f"Required CSV file is missing: {path}")

        dataframe = pd.read_csv(path)
        self._cache[filename] = dataframe
        return dataframe

    def load_facilities(self) -> pd.DataFrame:
        return self._load_csv(MAIN_FACILITY_CSV)

    def load_overview(self) -> pd.DataFrame:
        return self._load_csv(DASHBOARD_OVERVIEW_CSV)

    def load_trust_distribution(self) -> pd.DataFrame:
        return self._load_csv(TRUST_DISTRIBUTION_CSV)

    def load_readiness_distribution(self) -> pd.DataFrame:
        return self._load_csv(READINESS_DISTRIBUTION_CSV)

    def load_state_summary(self) -> pd.DataFrame:
        return self._load_csv(STATE_SUMMARY_CSV)

    def load_facility_type_summary(self) -> pd.DataFrame:
        return self._load_csv(FACILITY_TYPE_SUMMARY_CSV)

    def load_state_risk_index(self) -> pd.DataFrame:
        return self._load_csv(DESERT_STATE_RISK_INDEX_CSV)

    def load_priority_states(self) -> pd.DataFrame:
        return self._load_csv(DESERT_PRIORITY_STATES_CSV)

    def load_calibrated_priority_ranking(self) -> pd.DataFrame:
        return self._load_csv(DESERT_CALIBRATED_PRIORITY_RANKING_CSV)

    def load_trust_gap_summary(self) -> pd.DataFrame:
        return self._load_csv(DESERT_TRUST_GAP_SUMMARY_CSV)

    def load_facility_type_gap(self) -> pd.DataFrame:
        return self._load_csv(DESERT_FACILITY_TYPE_GAP_CSV)

    def load_all(self) -> dict[str, pd.DataFrame]:
        return {filename: self._load_csv(filename) for filename in CSV_FILENAMES}

    def validate_all(self) -> dict[str, Any]:
        self.load_all()
        facilities = self.load_facilities()
        warnings: list[str] = []

        self._validate_expected_row_counts()
        self._validate_facility_columns(facilities)
        self._validate_facility_required_values(facilities)
        self._validate_facility_category_values(facilities)
        self._validate_facility_numeric_values(facilities)

        summary = {
            "files_loaded": list(self._cache.keys()),
            "facility_rows": int(len(facilities)),
            "facility_columns": int(len(facilities.columns)),
            "unique_facility_ids": int(facilities["facility_id"].nunique(dropna=True)),
            "states_covered": int(facilities["state"].nunique(dropna=True)),
            "trust_categories": sorted(facilities["trust_category"].dropna().unique().tolist()),
            "readiness_values": sorted(
                facilities["recommendation_readiness"].dropna().unique().tolist()
            ),
            "warnings": warnings,
            "status": "valid",
        }
        self.validation_summary = summary
        self.last_error = None
        return summary

    def _validate_expected_row_counts(self) -> None:
        for filename, expected_rows in EXPECTED_ROW_COUNTS.items():
            dataframe = self._cache[filename]
            actual_rows = len(dataframe)
            if actual_rows != expected_rows:
                raise ValueError(
                    f"{filename} expected {expected_rows} rows but found {actual_rows} rows."
                )

    def _validate_facility_columns(self, facilities: pd.DataFrame) -> None:
        missing_columns = [
            column for column in REQUIRED_FACILITY_COLUMNS if column not in facilities.columns
        ]
        if missing_columns:
            raise ValueError(
                "caregrid_backend_export_full.csv is missing required columns: "
                + ", ".join(missing_columns)
            )

        expected_columns = len(REQUIRED_FACILITY_COLUMNS)
        actual_columns = len(facilities.columns)
        if actual_columns != expected_columns:
            raise ValueError(
                f"{MAIN_FACILITY_CSV} expected {expected_columns} columns but found "
                f"{actual_columns} columns."
            )

    def _validate_facility_required_values(self, facilities: pd.DataFrame) -> None:
        if facilities["facility_id"].isna().any():
            raise ValueError("caregrid_backend_export_full.csv contains missing facility_id values.")

        if facilities["facility_id"].duplicated().any():
            duplicate_count = int(facilities["facility_id"].duplicated().sum())
            raise ValueError(
                "caregrid_backend_export_full.csv contains duplicate facility_id values: "
                f"{duplicate_count} duplicates found."
            )

        if facilities["state"].isna().any():
            raise ValueError("caregrid_backend_export_full.csv contains missing state values.")

        if facilities["name"].isna().any():
            raise ValueError("caregrid_backend_export_full.csv contains missing name values.")

    def _validate_facility_category_values(self, facilities: pd.DataFrame) -> None:
        trust_values = set(facilities["trust_category"].dropna().unique())
        invalid_trust_values = sorted(trust_values - ALLOWED_TRUST_CATEGORIES)
        if invalid_trust_values:
            raise ValueError(
                "caregrid_backend_export_full.csv contains invalid trust_category values: "
                + ", ".join(invalid_trust_values)
            )

        readiness_values = set(facilities["recommendation_readiness"].dropna().unique())
        invalid_readiness_values = sorted(
            readiness_values - ALLOWED_RECOMMENDATION_READINESS
        )
        if invalid_readiness_values:
            raise ValueError(
                "caregrid_backend_export_full.csv contains invalid "
                "recommendation_readiness values: "
                + ", ".join(invalid_readiness_values)
            )

    def _validate_facility_numeric_values(self, facilities: pd.DataFrame) -> None:
        for column in ("latitude", "longitude"):
            populated = facilities[column].dropna()
            numeric_values = pd.to_numeric(populated, errors="coerce")
            if numeric_values.isna().any():
                raise ValueError(
                    f"caregrid_backend_export_full.csv contains non-numeric {column} values."
                )

        trust_score = pd.to_numeric(facilities["trust_score"], errors="coerce")
        if trust_score.isna().any():
            raise ValueError("caregrid_backend_export_full.csv contains non-numeric trust_score values.")

        if not trust_score.between(0, 100).all():
            raise ValueError("caregrid_backend_export_full.csv contains trust_score values outside 0-100.")


data_store = DataStore()
