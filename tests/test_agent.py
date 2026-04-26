from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_agent_recommend_trusted_icu_returns_200() -> None:
    response = client.post(
        "/agent/recommend",
        json={"query": "Find trusted ICU facilities", "max_results": 5},
    )

    assert response.status_code == 200


def test_agent_recommend_response_shape() -> None:
    response = client.post(
        "/agent/recommend",
        json={"query": "Find trusted ICU facilities", "max_results": 5},
    )
    body = response.json()

    assert response.status_code == 200
    assert {"interpreted_intent", "recommendations", "reasoning", "safety_note"}.issubset(body)


def test_agent_recommend_returned_is_limited_by_max_results() -> None:
    response = client.post(
        "/agent/recommend",
        json={"query": "Find trusted ICU facilities", "max_results": 5},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["returned"] <= 5


def test_agent_recommend_dialysis_returns_results_or_fallback() -> None:
    response = client.post(
        "/agent/recommend",
        json={"query": "Find dialysis centers", "max_results": 5},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["recommendations"] or body["fallback_message"]


def test_agent_recommend_state_filter_returns_only_state_when_results_exist() -> None:
    response = client.post(
        "/agent/recommend",
        json={"query": "Find emergency hospitals", "state": "Maharashtra", "max_results": 5},
    )
    body = response.json()

    assert response.status_code == 200
    if body["recommendations"]:
        assert all(item["state"] == "Maharashtra" for item in body["recommendations"])


def test_agent_recommend_detects_hospital_facility_type_intent() -> None:
    response = client.post(
        "/agent/recommend",
        json={"query": "Find emergency hospitals", "state": "Maharashtra", "max_results": 5},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["interpreted_intent"]["facility_type"] == "hospital"
    if body["recommendations"] and not body["fallback_message"]:
        assert all(item["facility_type"].casefold() == "hospital" for item in body["recommendations"])


def test_agent_recommend_detects_clinic_facility_type_intent() -> None:
    response = client.post(
        "/agent/recommend",
        json={"query": "Find emergency clinics", "state": "Maharashtra", "max_results": 5},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["interpreted_intent"]["facility_type"] == "clinic"
    if body["recommendations"] and not body["fallback_message"]:
        assert all(item["facility_type"].casefold() == "clinic" for item in body["recommendations"])


def test_agent_recommend_request_facility_type_overrides_query_intent() -> None:
    response = client.post(
        "/agent/recommend",
        json={
            "query": "Find emergency hospitals",
            "state": "Maharashtra",
            "facility_type": "clinic",
            "max_results": 5,
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["interpreted_intent"]["facility_type"] == "clinic"
    assert body["interpreted_intent"]["facility_type_source"] == "request"
    if body["recommendations"] and not body["fallback_message"]:
        assert all(item["facility_type"].casefold() == "clinic" for item in body["recommendations"])


def test_agent_recommend_min_trust_score_filters_results_when_results_exist() -> None:
    response = client.post(
        "/agent/recommend",
        json={"query": "Find dental facilities", "min_trust_score": 80, "max_results": 5},
    )
    body = response.json()

    assert response.status_code == 200
    if body["recommendations"]:
        assert all(item["trust_score"] >= 80 for item in body["recommendations"])


def test_agent_recommend_rejects_empty_query() -> None:
    response = client.post("/agent/recommend", json={"query": "   "})

    assert response.status_code == 400


def test_agent_recommend_rejects_max_results_greater_than_20() -> None:
    response = client.post(
        "/agent/recommend",
        json={"query": "Find ICU facilities", "max_results": 21},
    )

    assert response.status_code == 422


def test_agent_recommend_item_contains_reasoning_fields() -> None:
    response = client.post(
        "/agent/recommend",
        json={"query": "Find trusted ICU facilities", "max_results": 1},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["recommendations"]
    item = body["recommendations"][0]
    assert "recommendation_score" in item
    assert "matched_capabilities" in item
    assert "matched_fields" in item
    assert "warning_flags" in item
    assert "reason_for_recommendation" in item


def test_agent_recommend_safety_note_is_always_present() -> None:
    response = client.post(
        "/agent/recommend",
        json={"query": "Find oncology facilities", "max_results": 5},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["safety_note"]
