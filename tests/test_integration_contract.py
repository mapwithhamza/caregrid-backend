from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_is_available() -> None:
    response = client.get("/health")

    assert response.status_code == 200


def test_openapi_schema_is_available() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200


def test_stats_overview_is_available() -> None:
    response = client.get("/stats/overview")

    assert response.status_code == 200


def test_impact_trust_gap_summary_is_available() -> None:
    response = client.get("/impact/trust-gap-summary")

    assert response.status_code == 200


def test_search_is_available() -> None:
    response = client.get("/search?q=dental&limit=3")

    assert response.status_code == 200


def test_agent_recommend_is_available() -> None:
    response = client.post(
        "/agent/recommend",
        json={"query": "Find trusted ICU facilities", "max_results": 3},
    )

    assert response.status_code == 200
