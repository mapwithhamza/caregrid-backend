from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_search_dental_returns_results() -> None:
    response = client.get("/search?q=dental")
    body = response.json()

    assert response.status_code == 200
    assert body["results"]


def test_search_icu_returns_response_shape() -> None:
    response = client.get("/search?q=icu")
    body = response.json()

    assert response.status_code == 200
    assert {"query", "total_matches", "returned", "results", "applied_filters"}.issubset(body)


def test_search_filters_by_min_trust_score() -> None:
    response = client.get("/search?q=dialysis&min_trust_score=60")
    body = response.json()

    assert response.status_code == 200
    assert body["results"]
    assert all(result["trust_score"] >= 60 for result in body["results"])


def test_search_filters_by_state() -> None:
    response = client.get("/search?q=hospital&state=Maharashtra")
    body = response.json()

    assert response.status_code == 200
    assert body["results"]
    assert all(result["state"] == "Maharashtra" for result in body["results"])


def test_search_filters_by_facility_type() -> None:
    response = client.get("/search?q=clinic&facility_type=clinic")
    body = response.json()

    assert response.status_code == 200
    assert body["results"]
    assert all(result["facility_type"].casefold() == "clinic" for result in body["results"])


def test_search_limit_5_returns_no_more_than_5_results() -> None:
    response = client.get("/search?q=dental&limit=5")
    body = response.json()

    assert response.status_code == 200
    assert len(body["results"]) <= 5


def test_search_rejects_blank_query() -> None:
    response = client.get("/search", params={"q": "   "})

    assert response.status_code == 400


def test_search_rejects_min_trust_score_outside_range() -> None:
    response = client.get("/search?q=dental&min_trust_score=120")

    assert response.status_code == 400


def test_search_result_includes_scoring_metadata() -> None:
    response = client.get("/search?q=dental&limit=1")
    body = response.json()

    assert response.status_code == 200
    assert body["results"]
    result = body["results"][0]
    assert "relevance_score" in result
    assert "matched_fields" in result
    assert "warning_flags" in result


def test_search_result_does_not_include_combined_medical_evidence() -> None:
    response = client.get("/search?q=dental&limit=1")
    body = response.json()

    assert response.status_code == 200
    assert body["results"]
    assert "combined_medical_evidence" not in body["results"][0]
