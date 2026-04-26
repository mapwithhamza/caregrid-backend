from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_backend_metadata() -> None:
    response = client.get("/health")
    body = response.json()

    assert response.status_code == 200
    assert body["service"] == "CareGrid India API"
    assert body["endpoints_ready"] is True
    assert body["tests_expected"] == "python -m pytest"
