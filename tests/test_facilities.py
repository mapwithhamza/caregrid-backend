from fastapi.testclient import TestClient

from app.data_loader import data_store
from app.main import app
from app.models import clean_pin_code


client = TestClient(app)


def test_clean_pin_code_removes_decimal_string_suffix() -> None:
    assert clean_pin_code("322202.0") == "322202"


def test_clean_pin_code_converts_numeric_float_to_string() -> None:
    assert clean_pin_code(380009.0) == "380009"


def test_clean_pin_code_preserves_valid_six_digit_string() -> None:
    assert clean_pin_code("410218") == "410218"


def test_get_facilities_returns_200() -> None:
    response = client.get("/facilities")

    assert response.status_code == 200


def test_get_facilities_response_shape() -> None:
    response = client.get("/facilities")
    body = response.json()

    assert response.status_code == 200
    assert {"total", "page", "limit", "total_pages", "results"}.issubset(body)


def test_get_facilities_default_limit_returns_no_more_than_50_results() -> None:
    response = client.get("/facilities")
    body = response.json()

    assert response.status_code == 200
    assert len(body["results"]) <= 50


def test_get_facilities_limit_10_returns_10_or_fewer_results() -> None:
    response = client.get("/facilities?limit=10")
    body = response.json()

    assert response.status_code == 200
    assert len(body["results"]) <= 10


def test_get_facilities_limit_5_returns_clean_pin_codes() -> None:
    response = client.get("/facilities?limit=5")
    body = response.json()

    assert response.status_code == 200
    for result in body["results"]:
        pin_code = result["pin_code"]
        if pin_code is not None:
            assert not pin_code.endswith(".0")


def test_get_facilities_filters_by_state() -> None:
    response = client.get("/facilities?state=Maharashtra&limit=100")
    body = response.json()

    assert response.status_code == 200
    assert body["results"]
    assert all(result["state"] == "Maharashtra" for result in body["results"])


def test_get_facilities_filters_by_facility_type_case_insensitive() -> None:
    response = client.get("/facilities?facility_type=hospital&limit=100")
    body = response.json()

    assert response.status_code == 200
    assert body["results"]
    assert all(
        result["facility_type"].casefold() == "hospital"
        for result in body["results"]
    )


def test_get_facilities_filters_by_min_trust_score() -> None:
    response = client.get("/facilities?min_trust_score=80&limit=100")
    body = response.json()

    assert response.status_code == 200
    assert body["results"]
    assert all(result["trust_score"] >= 80 for result in body["results"])


def test_get_facilities_rejects_invalid_trust_score_range() -> None:
    response = client.get("/facilities?min_trust_score=90&max_trust_score=80")

    assert response.status_code == 400


def test_get_facility_filters_meta_returns_states_and_trust_categories() -> None:
    response = client.get("/facilities/meta/filters")
    body = response.json()

    assert response.status_code == 200
    assert body["states"]
    assert body["trust_categories"]


def test_get_facility_detail_returns_combined_medical_evidence() -> None:
    facilities = data_store.load_facilities()
    valid_facility_id = str(facilities.iloc[0]["facility_id"])

    response = client.get(f"/facilities/{valid_facility_id}")
    body = response.json()

    assert response.status_code == 200
    assert body["facility_id"] == valid_facility_id
    assert "combined_medical_evidence" in body


def test_get_facility_detail_returns_404_for_missing_id() -> None:
    response = client.get("/facilities/not-a-real-id")

    assert response.status_code == 404
