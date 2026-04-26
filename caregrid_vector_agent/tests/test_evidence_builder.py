import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math
import pytest
import pandas as pd

from agent_core.evidence_builder import (
    _clean_value,
    build_combined_evidence,
    build_evidence,
    build_evidence_from_record,
)
from agent_core.vector_source_builder import (
    build_vector_text,
    prepare_vector_source_dataframe,
    OUTPUT_COLUMNS,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FULL_RECORD: dict = {
    "facility_id": "F001",
    "name": "Apollo Hospital",
    "facility_type": "Hospital",
    "city": "Mumbai",
    "state": "Maharashtra",
    "specialties": "Cardiology, Neurology, Oncology",
    "procedures": "Dialysis, Chemotherapy, CABG",
    "equipment": "Ventilator, MRI, Dialysis Machine",
    "capabilities_raw": "ICU, NICU, Blood Bank",
    "evidence_summary": "Multi-speciality hospital with 500 beds.",
    "combined_medical_evidence": "ICU with 20 ventilators. Dialysis unit with 10 machines.",
    "trust_score": 0.9,
    "trust_category": "High Trust / Evidence Supported",
    "recommendation_readiness": "Ready for recommendation",
    "latitude": 19.076,
    "longitude": 72.877,
}

MINIMAL_RECORD: dict = {
    "facility_id": "F002",
    "name": "City Clinic",
    "trust_score": 0.5,
    "trust_category": "Moderate Trust / Verify Before Use",
    "recommendation_readiness": "Usable with verification",
}

EMPTY_RECORD: dict = {
    "facility_id": "F003",
}


def _df(*records) -> pd.DataFrame:
    return pd.DataFrame(list(records))


# ===========================================================================
# _clean_value
# ===========================================================================

class TestCleanValue:
    def test_none_returns_empty(self):
        assert _clean_value(None) == ""

    def test_float_nan_returns_empty(self):
        assert _clean_value(float("nan")) == ""

    def test_math_nan_returns_empty(self):
        assert _clean_value(math.nan) == ""

    def test_string_nan_returns_empty(self):
        assert _clean_value("nan") == ""

    def test_string_nan_uppercase_returns_empty(self):
        assert _clean_value("NaN") == ""

    def test_string_none_returns_empty(self):
        assert _clean_value("None") == ""

    def test_string_null_returns_empty(self):
        assert _clean_value("null") == ""

    def test_string_na_returns_empty(self):
        assert _clean_value("N/A") == ""

    def test_empty_string_returns_empty(self):
        assert _clean_value("") == ""

    def test_whitespace_string_returns_empty(self):
        assert _clean_value("   ") == ""

    def test_list_like_with_quotes(self):
        assert _clean_value("['ICU', 'dialysis']") == "ICU, dialysis"

    def test_list_like_without_quotes(self):
        assert _clean_value("[ICU, dialysis, blood bank]") == "ICU, dialysis, blood bank"

    def test_list_like_double_quotes(self):
        assert _clean_value('["ICU", "NICU"]') == "ICU, NICU"

    def test_list_like_no_brackets_in_result(self):
        result = _clean_value("['ICU', 'dialysis']")
        assert "[" not in result
        assert "]" not in result

    def test_normal_string_preserved(self):
        assert _clean_value("Apollo Hospital") == "Apollo Hospital"

    def test_strips_whitespace(self):
        assert _clean_value("  Mumbai  ") == "Mumbai"

    def test_integer_value(self):
        assert _clean_value(42) == "42"

    def test_zero_is_not_empty(self):
        assert _clean_value(0) == "0"


# ===========================================================================
# build_combined_evidence
# ===========================================================================

class TestBuildCombinedEvidence:
    def test_contains_facility_name(self):
        text = build_combined_evidence(FULL_RECORD)
        assert "Apollo Hospital" in text

    def test_contains_facility_type(self):
        text = build_combined_evidence(FULL_RECORD)
        assert "Hospital" in text

    def test_contains_city(self):
        text = build_combined_evidence(FULL_RECORD)
        assert "Mumbai" in text

    def test_contains_state(self):
        text = build_combined_evidence(FULL_RECORD)
        assert "Maharashtra" in text

    def test_contains_specialties(self):
        text = build_combined_evidence(FULL_RECORD)
        assert "Cardiology" in text

    def test_contains_procedures(self):
        text = build_combined_evidence(FULL_RECORD)
        assert "Dialysis" in text

    def test_contains_equipment(self):
        text = build_combined_evidence(FULL_RECORD)
        assert "Ventilator" in text

    def test_contains_capabilities(self):
        text = build_combined_evidence(FULL_RECORD)
        assert "ICU" in text

    def test_contains_evidence_summary(self):
        text = build_combined_evidence(FULL_RECORD)
        assert "Multi-speciality hospital" in text

    def test_contains_evidence_text(self):
        text = build_combined_evidence(FULL_RECORD)
        assert "20 ventilators" in text

    def test_returns_string(self):
        assert isinstance(build_combined_evidence(FULL_RECORD), str)

    def test_empty_record_returns_empty_string(self):
        assert build_combined_evidence(EMPTY_RECORD) == ""

    def test_minimal_record_contains_name(self):
        text = build_combined_evidence(MINIMAL_RECORD)
        assert "City Clinic" in text

    def test_none_fields_skipped(self):
        record = {"facility_id": "F001", "name": "Test", "specialties": None}
        text = build_combined_evidence(record)
        assert "Specialties" not in text

    def test_nan_fields_skipped(self):
        record = {"facility_id": "F001", "name": "Test", "equipment": float("nan")}
        text = build_combined_evidence(record)
        assert "Equipment" not in text

    def test_list_like_fields_cleaned(self):
        record = {
            "facility_id": "F001",
            "name": "Test",
            "specialties": "['Cardiology', 'Neurology']",
        }
        text = build_combined_evidence(record)
        assert "[" not in text
        assert "Cardiology" in text

    def test_city_state_combined_in_location(self):
        text = build_combined_evidence(FULL_RECORD)
        assert "Mumbai" in text and "Maharashtra" in text

    def test_city_only_no_extra_comma(self):
        record = {"facility_id": "F001", "name": "A", "city": "Pune", "state": None}
        text = build_combined_evidence(record)
        assert "Pune" in text
        assert "Location: Pune" in text


# ===========================================================================
# build_evidence (legacy function)
# ===========================================================================

class TestBuildEvidence:
    def test_returns_snippet_list(self):
        result = build_evidence("F001", "ICU available with 20 beds.")
        assert len(result) == 1
        assert result[0].facility_id == "F001"
        assert "ICU" in result[0].excerpt

    def test_empty_string_returns_empty_list(self):
        assert build_evidence("F001", "") == []

    def test_none_returns_empty_list(self):
        assert build_evidence("F001", None) == []

    def test_nan_returns_empty_list(self):
        assert build_evidence("F001", float("nan")) == []

    def test_long_text_truncated_at_500(self):
        long_text = "word " * 300
        result = build_evidence("F001", long_text)
        assert len(result[0].excerpt) <= 500

    def test_source_field_default(self):
        result = build_evidence("F001", "Has ICU.")
        assert result[0].source_field == "combined_medical_evidence"


# ===========================================================================
# build_evidence_from_record
# ===========================================================================

class TestBuildEvidenceFromRecord:
    def test_full_record_returns_snippet(self):
        result = build_evidence_from_record(FULL_RECORD)
        assert len(result) == 1
        assert result[0].facility_id == "F001"

    def test_empty_record_no_facility_id_returns_empty(self):
        assert build_evidence_from_record({}) == []

    def test_all_empty_fields_returns_empty(self):
        assert build_evidence_from_record(EMPTY_RECORD) == []

    def test_snippet_contains_name(self):
        result = build_evidence_from_record(FULL_RECORD)
        assert "Apollo Hospital" in result[0].excerpt


# ===========================================================================
# build_vector_text
# ===========================================================================

class TestBuildVectorText:
    def test_contains_facility_name(self):
        text = build_vector_text(FULL_RECORD)
        assert "Apollo Hospital" in text

    def test_contains_city(self):
        text = build_vector_text(FULL_RECORD)
        assert "Mumbai" in text

    def test_contains_state(self):
        text = build_vector_text(FULL_RECORD)
        assert "Maharashtra" in text

    def test_contains_specialties(self):
        text = build_vector_text(FULL_RECORD)
        assert "Cardiology" in text

    def test_contains_equipment(self):
        text = build_vector_text(FULL_RECORD)
        assert "Ventilator" in text

    def test_contains_evidence_text(self):
        text = build_vector_text(FULL_RECORD)
        assert "ICU" in text

    def test_returns_string(self):
        assert isinstance(build_vector_text(FULL_RECORD), str)

    def test_empty_record_returns_string(self):
        text = build_vector_text(EMPTY_RECORD)
        assert isinstance(text, str)

    def test_minimal_record_contains_name(self):
        text = build_vector_text(MINIMAL_RECORD)
        assert "City Clinic" in text

    def test_no_list_brackets_in_output(self):
        record = {**FULL_RECORD, "specialties": "['Cardiology', 'Neurology']"}
        text = build_vector_text(record)
        assert "[" not in text

    def test_no_null_noise(self):
        record = {
            "facility_id": "F001",
            "name": "Test",
            "specialties": None,
            "equipment": "nan",
        }
        text = build_vector_text(record)
        assert "nan" not in text
        assert "None" not in text


# ===========================================================================
# prepare_vector_source_dataframe
# ===========================================================================

class TestPrepareVectorSourceDataframe:

    def test_output_columns_all_present(self):
        df = _df(FULL_RECORD)
        result = prepare_vector_source_dataframe(df)
        for col in OUTPUT_COLUMNS:
            assert col in result.columns, f"Missing output column: {col}"

    def test_output_columns_in_order(self):
        df = _df(FULL_RECORD)
        result = prepare_vector_source_dataframe(df)
        present = [c for c in OUTPUT_COLUMNS if c in result.columns]
        assert list(result.columns) == present

    def test_no_missing_facility_id(self):
        df = _df(FULL_RECORD, MINIMAL_RECORD)
        result = prepare_vector_source_dataframe(df)
        assert result["facility_id"].notna().all()
        assert (result["facility_id"] != "").all()

    def test_vector_text_column_populated(self):
        df = _df(FULL_RECORD)
        result = prepare_vector_source_dataframe(df)
        assert result["vector_text"].iloc[0] != ""

    def test_vector_text_contains_facility_name(self):
        df = _df(FULL_RECORD)
        result = prepare_vector_source_dataframe(df)
        assert "Apollo Hospital" in result["vector_text"].iloc[0]

    def test_vector_text_contains_evidence(self):
        df = _df(FULL_RECORD)
        result = prepare_vector_source_dataframe(df)
        assert "ICU" in result["vector_text"].iloc[0]

    def test_combined_medical_evidence_preserved_when_present(self):
        df = _df(FULL_RECORD)
        result = prepare_vector_source_dataframe(df)
        assert "20 ventilators" in result["combined_medical_evidence"].iloc[0]

    def test_combined_medical_evidence_built_when_absent(self):
        record = {
            "facility_id": "F004",
            "name": "Sun Hospital",
            "city": "Pune",
            "state": "Maharashtra",
            "specialties": "Cardiology",
        }
        df = _df(record)
        result = prepare_vector_source_dataframe(df)
        cme = result["combined_medical_evidence"].iloc[0]
        assert "Sun Hospital" in cme

    def test_missing_columns_filled_with_defaults(self):
        df = _df(MINIMAL_RECORD)
        result = prepare_vector_source_dataframe(df)
        assert result["city"].iloc[0] == ""
        assert result["state"].iloc[0] == ""
        assert result["facility_type"].iloc[0] == ""

    def test_existing_trust_score_preserved(self):
        df = _df(MINIMAL_RECORD)
        result = prepare_vector_source_dataframe(df)
        assert result["trust_score"].iloc[0] == pytest.approx(0.5)

    def test_latitude_longitude_preserved(self):
        df = _df(FULL_RECORD)
        result = prepare_vector_source_dataframe(df)
        assert result["latitude"].iloc[0] == pytest.approx(19.076)
        assert result["longitude"].iloc[0] == pytest.approx(72.877)

    def test_handles_multiple_rows(self):
        df = _df(FULL_RECORD, MINIMAL_RECORD)
        result = prepare_vector_source_dataframe(df)
        assert len(result) == 2

    def test_empty_dataframe_returns_empty_with_columns(self):
        df = pd.DataFrame(columns=["facility_id", "name"])
        result = prepare_vector_source_dataframe(df)
        assert len(result) == 0
        assert "vector_text" in result.columns

    def test_raises_without_facility_id_column(self):
        df = pd.DataFrame([{"name": "Clinic", "trust_score": 0.5}])
        with pytest.raises(ValueError, match="facility_id"):
            prepare_vector_source_dataframe(df)

    def test_raises_with_null_facility_id(self):
        df = pd.DataFrame([{"facility_id": None, "name": "Clinic"}])
        with pytest.raises(ValueError):
            prepare_vector_source_dataframe(df)

    def test_does_not_modify_input_dataframe(self):
        df = _df(FULL_RECORD)
        original_cols = list(df.columns)
        prepare_vector_source_dataframe(df)
        assert list(df.columns) == original_cols

    def test_nan_in_specialties_cleaned(self):
        record = {
            "facility_id": "F005",
            "name": "Test Hospital",
            "specialties": float("nan"),
            "combined_medical_evidence": "Has ICU.",
        }
        df = _df(record)
        result = prepare_vector_source_dataframe(df)
        text = result["vector_text"].iloc[0]
        assert "nan" not in text.lower()
        assert "Test Hospital" in text
