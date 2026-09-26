from fastapi.testclient import TestClient

from app.main import app
from app.version import __version__

client = TestClient(app)


def test_health_returns_service_status() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "regbridge-api",
        "version": __version__,
    }


def test_unknown_api_route_returns_not_found() -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert response.json()["error"]["request_id"]
