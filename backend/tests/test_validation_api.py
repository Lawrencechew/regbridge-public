from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_validation_rule_types_endpoint(tmp_path) -> None:
    settings = Settings(_env_file=None, regpacks_path=tmp_path, persistence_enabled=False)
    with TestClient(create_app(settings_override=settings)) as client:
        response = client.get("/api/v1/validation/rule-types")

    assert response.status_code == 200
    assert response.json() == {
        "rule_types": [
            "allowed_characters",
            "conditional_required",
            "decimal_places",
            "enum",
            "maximum",
            "minimum",
            "not_blank",
            "regex",
            "required",
            "unique",
        ]
    }
