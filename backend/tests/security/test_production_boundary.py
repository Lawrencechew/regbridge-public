from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.http import BodyLimitMiddleware
from app.main import create_app


REGPACKS = Path(__file__).parents[3] / "regpacks"


def production_values() -> dict[str, object]:
    return {
        "_env_file": None,
        "app_env": "production",
        "auth_enabled": True,
        "application_secret": "p" * 48,
        "cookie_secure": True,
        "https_boundary": True,
        "cors_allowed_origins": "https://192.0.2.10",
        "trusted_hosts": "192.0.2.10",
        "database_url": "postgresql+psycopg://user:synthetic-password@database.example.test/regbridge",
        "oidc_issuer": "https://login.microsoftonline.com/12345678-1234-1234-1234-123456789012/v2.0",
        "oidc_discovery_url": "https://login.microsoftonline.com/12345678-1234-1234-1234-123456789012/v2.0/.well-known/openid-configuration",
        "oidc_client_id": "87654321-4321-4321-4321-210987654321",
        "oidc_client_secret": "s" * 32,
        "oidc_redirect_uri": "https://192.0.2.10/auth/callback",
        "frontend_url": "https://192.0.2.10",
        "session_expiry_seconds": 3600,
        "regpacks_path": REGPACKS,
    }


@pytest.mark.parametrize(("field", "value"), [
    ("auth_enabled", False),
    ("application_secret", "development-only-change-me"),
    ("cookie_secure", False),
    ("https_boundary", False),
    ("cors_allowed_origins", "*"),
    ("cors_allowed_origins", "https://*.acme.internal"),
    ("cors_allowed_origins", "http://192.0.2.10"),
    ("trusted_hosts", "*"),
    ("trusted_hosts", "*.acme.internal"),
    ("database_url", "sqlite:///production.db"),
    ("app_debug", True),
    ("database_sql_echo", True),
    ("oidc_client_id", "replace-me"),
    ("oidc_client_secret", "short"),
    ("oidc_redirect_uri", "http://localhost/auth/callback"),
    ("frontend_url", "https://regbridge.acme.invalid"),
    ("session_expiry_seconds", 604800),
])
def test_unsafe_production_configuration_fails_closed(field: str, value: object) -> None:
    values = production_values()
    values[field] = value
    with pytest.raises(ValidationError, match="Unsafe production configuration"):
        Settings(**values)


def test_safe_production_configuration_is_deterministic() -> None:
    settings = Settings(**production_values())
    assert settings.app_env == "production"
    assert settings.secure_cookies is True
    assert settings.allowed_hosts == ["192.0.2.10"]


def test_security_headers_request_ids_metrics_and_body_limit() -> None:
    settings = Settings(
        _env_file=None, app_env="test", persistence_enabled=False,
        regpacks_path=REGPACKS, request_max_body_mb=1,
    )
    with TestClient(create_app(settings_override=settings)) as client:
        response = client.get("/api/v1/health", headers={"X-Request-ID": "phase11-test"})
        assert response.status_code == 200
        assert response.headers["x-request-id"] == "phase11-test"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert "camera=()" in response.headers["permissions-policy"]
        assert "strict-transport-security" not in response.headers

        sensitive = client.get("/auth/session")
        assert sensitive.headers["cache-control"] == "no-store"
        assert client.get("/api/v1/ready").status_code == 503
        metrics = client.get("/api/v1/metrics")
        assert metrics.status_code == 200
        assert "regbridge_http_requests_total" in metrics.text
        assert "user_id" not in metrics.text and "organisation_id" not in metrics.text

        oversized = client.post("/api/v1/does-not-exist", content=b"x" * (1024 * 1024 + 1))
        assert oversized.status_code == 413
        assert oversized.json()["error"]["code"] == "REQUEST_TOO_LARGE"



def test_chunked_transfer_body_limit_does_not_depend_on_content_length() -> None:
    received = iter((
        {"type": "http.request", "body": b"123456", "more_body": True},
        {"type": "http.request", "body": b"789012", "more_body": False},
    ))
    sent: list[dict] = []

    async def receive():
        return next(received)

    async def send(message):
        sent.append(message)

    async def body_consumer(scope, receive, send):
        await receive()
        await receive()

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "https", "path": "/upload", "raw_path": b"/upload",
        "query_string": b"", "headers": [(b"transfer-encoding", b"chunked")],
        "client": ("127.0.0.1", 1234), "server": ("testserver", 443),
        "state": {"request_id": "chunked-limit-test"},
    }
    asyncio.run(BodyLimitMiddleware(body_consumer, max_bytes=10)(scope, receive, send))

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    assert b"REQUEST_TOO_LARGE" in sent[1]["body"]


def test_production_hsts_and_host_rejection_without_starting_dependencies() -> None:
    app = create_app(settings_override=Settings(**production_values()))
    client = TestClient(app)
    accepted = client.get("/api/v1/health", headers={"host": "192.0.2.10"})
    assert accepted.status_code == 200
    assert accepted.headers["strict-transport-security"].startswith("max-age=")
    rejected = client.get("/api/v1/health", headers={"host": "attacker.invalid"})
    assert rejected.status_code == 400


def test_rate_sensitive_endpoint_is_bounded() -> None:
    settings = Settings(
        _env_file=None, app_env="test", persistence_enabled=False,
        regpacks_path=REGPACKS, rate_limit_auth_requests=2,
    )
    with TestClient(create_app(settings_override=settings)) as client:
        assert client.get("/auth/login").status_code == 503
        assert client.get("/auth/login").status_code == 503
        limited = client.get("/auth/login")
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "RATE_LIMITED"
