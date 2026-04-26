import pandas as pd

from app.config import (
    ALLOWED_RECOMMENDATION_READINESS,
    ALLOWED_TRUST_CATEGORIES,
    CSV_FILENAMES,
    DATA_DIR,
    EXPECTED_ROW_COUNTS,
    MAIN_FACILITY_CSV,
    REQUIRED_FACILITY_COLUMNS,
)
from app.data_loader import DataStore


def test_data_store_can_be_instantiated() -> None:
    store = DataStore()

    assert store.data_dir == DATA_DIR
    assert store.is_loaded is False


def test_required_columns_include_facility_id() -> None:
    assert "facility_id" in REQUIRED_FACILITY_COLUMNS


def test_allowed_trust_categories_include_exact_values() -> None:
    assert ALLOWED_TRUST_CATEGORIES == {
        "High Trust / Evidence Supported",
        "Moderate Trust / Verify Before Use",
        "Low Trust / Needs Human Verification",
        "High Risk / Insufficient Evidence",
    }


def test_allowed_readiness_values_include_exact_values() -> None:
    assert ALLOWED_RECOMMENDATION_READINESS == {
        "Ready for recommendation",
        "Usable with verification",
        "Do not recommend without human review",
    }


def test_load_all_returns_dataframes_when_csv_files_exist() -> None:
    if not all((DATA_DIR / filename).exists() for filename in CSV_FILENAMES):
        return

    store = DataStore()
    loaded_data = store.load_all()

    assert set(loaded_data) == set(CSV_FILENAMES)
    assert all(isinstance(dataframe, pd.DataFrame) for dataframe in loaded_data.values())


def test_loaded_facilities_have_expected_rows_and_unique_ids() -> None:
    if not (DATA_DIR / MAIN_FACILITY_CSV).exists():
        return

    store = DataStore()
    facilities = store.load_facilities()

    assert len(facilities) == EXPECTED_ROW_COUNTS[MAIN_FACILITY_CSV]
    assert facilities["facility_id"].is_unique
