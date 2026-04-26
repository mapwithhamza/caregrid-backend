from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_get_trust_gap_summary_returns_total_facilities() -> None:
    response = client.get("/impact/trust-gap-summary")
    body = response.json()

    assert response.status_code == 200
    assert "total_facilities" in body


def test_get_trust_gap_summary_total_facilities_equals_10000() -> None:
    response = client.get("/impact/trust-gap-summary")
    body = response.json()

    assert response.status_code == 200
    assert body["total_facilities"] == 10000


def test_get_priority_states_returns_list() -> None:
    response = client.get("/impact/priority-states")
    body = response.json()

    assert response.status_code == 200
    assert isinstance(body, list)


def test_get_priority_states_limit_5_returns_no_more_than_5_rows() -> None:
    response = client.get("/impact/priority-states?limit=5")
    body = response.json()

    assert response.status_code == 200
    assert len(body) <= 5


def test_get_priority_states_filters_by_tier() -> None:
    response = client.get("/impact/priority-states", params={"tier": "Tier 1"})
    body = response.json()

    assert response.status_code == 200
    assert body
    assert all("Tier 1" in item["calibrated_priority_tier"] for item in body)


def test_get_state_risk_index_returns_list() -> None:
    response = client.get("/impact/state-risk-index")
    body = response.json()

    assert response.status_code == 200
    assert isinstance(body, list)


def test_get_state_risk_index_supports_sort_order_and_limit() -> None:
    response = client.get("/impact/state-risk-index?sort_by=ready_percent&order=asc&limit=5")
    body = response.json()

    assert response.status_code == 200
    assert len(body) <= 5


def test_get_state_risk_index_rejects_invalid_sort_by() -> None:
    response = client.get("/impact/state-risk-index?sort_by=bad_field")

    assert response.status_code == 400


def test_get_facility_type_gap_returns_facility_type() -> None:
    response = client.get("/impact/facility-type-gap")
    body = response.json()

    assert response.status_code == 200
    assert body
    assert "facility_type" in body[0]


def test_get_facility_type_gap_rejects_invalid_sort_by() -> None:
    response = client.get("/impact/facility-type-gap?sort_by=bad_field")

    assert response.status_code == 400
