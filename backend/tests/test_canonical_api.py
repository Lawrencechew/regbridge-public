from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def make_client(regpacks_path) -> TestClient:
    settings = Settings(_env_file=None, regpacks_path=regpacks_path, persistence_enabled=False)
    return TestClient(create_app(settings_override=settings))


def test_canonical_types_endpoint_is_deterministic(tmp_path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/canonical/types")

    assert response.status_code == 200
    assert response.json() == {
        "types": ["boolean", "date", "datetime", "decimal", "integer", "string"]
    }


def test_canonical_schema_registry_is_empty_at_startup(tmp_path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/canonical/schemas")

    assert response.status_code == 200
    assert response.json() == {"schemas": []}
