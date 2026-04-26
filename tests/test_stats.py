from fastapi.testclient import TestClient

from app.config import ALLOWED_RECOMMENDATION_READINESS, ALLOWED_TRUST_CATEGORIES
from app.main import app


client = TestClient(app)


def test_get_stats_overview_returns_total_facilities() -> None:
    response = client.get("/stats/overview")
    body = response.json()

    assert response.status_code == 200
    assert "total_facilities" in body


def test_get_stats_overview_total_facilities_equals_10000() -> None:
    response = client.get("/stats/overview")
    body = response.json()

    assert response.status_code == 200
    assert body["total_facilities"] == 10000


def test_get_trust_distribution_returns_four_rows() -> None:
    response = client.get("/stats/trust-distribution")
    body = response.json()

    assert response.status_code == 200
    assert isinstance(body, list)
    assert len(body) == 4


def test_get_trust_distribution_includes_exact_categories() -> None:
    response = client.get("/stats/trust-distribution")
    body = response.json()
    categories = {item["trust_category"] for item in body}

    assert response.status_code == 200
    assert categories == ALLOWED_TRUST_CATEGORIES


def test_get_readiness_distribution_returns_three_rows() -> None:
    response = client.get("/stats/readiness-distribution")
    body = response.json()

    assert response.status_code == 200
    assert isinstance(body, list)
    assert len(body) == 3


def test_get_readiness_distribution_includes_exact_values() -> None:
    response = client.get("/stats/readiness-distribution")
    body = response.json()
    readiness_values = {item["recommendation_readiness"] for item in body}

    assert response.status_code == 200
    assert readiness_values == ALLOWED_RECOMMENDATION_READINESS


def test_get_states_returns_state_field() -> None:
    response = client.get("/stats/states")
    body = response.json()

    assert response.status_code == 200
    assert body
    assert "state" in body[0]


def test_get_states_supports_sort_order_and_limit() -> None:
    response = client.get("/stats/states?sort_by=ready_percent&order=asc&limit=5")
    body = response.json()

    assert response.status_code == 200
    assert len(body) <= 5


def test_get_states_rejects_invalid_sort_by() -> None:
    response = client.get("/stats/states?sort_by=bad_field")

    assert response.status_code == 400


def test_get_states_rejects_invalid_order() -> None:
    response = client.get("/stats/states?order=sideways")

    assert response.status_code == 400


def test_get_facility_types_returns_facility_type_field() -> None:
    response = client.get("/stats/facility-types")
    body = response.json()

    assert response.status_code == 200
    assert body
    assert "facility_type" in body[0]
