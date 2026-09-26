from __future__ import annotations

import asyncio
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey

from app.identity.errors import InvalidOidcResponse
from app.identity.oidc import OidcClient
from app.core.config import Settings
from app.main import create_app


REGPACKS = Path(__file__).parents[3] / "regpacks"


def application(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'oidc-adversarial.db').as_posix()}"
    configuration = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(configuration, "head")
    settings = Settings(
        _env_file=None,
        regpacks_path=REGPACKS,
        database_url=database_url,
        persistence_enabled=True,
        auth_enabled=True,
        oidc_issuer="https://issuer.example.test",
        oidc_discovery_url="https://issuer.example.test/.well-known/openid-configuration",
        oidc_client_id="regbridge-test",
        cookie_secure=False,
    )
    return create_app(settings_override=settings), settings


def test_oidc_token_attacks_callback_replay_and_cancellation(tmp_path, monkeypatch) -> None:
    app, settings = application(tmp_path)
    signing_key = RSAKey.generate_key(2048, parameters={"kid": "provider-key"})
    other_key = RSAKey.generate_key(2048, parameters={"kid": "other-key"})
    metadata = {
        "issuer": settings.oidc_issuer,
        "authorization_endpoint": "https://issuer.example.test/authorize",
        "token_endpoint": "https://issuer.example.test/token",
        "jwks_uri": "https://issuer.example.test/jwks",
        "id_token_signing_alg_values_supported": ["RS256"],
    }
    exchange: dict[str, object] = {}

    async def fixed_metadata(self):
        return metadata

    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): return None
        def json(self): return self.payload

    class AsyncClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, url, **kwargs): return Response({"id_token": exchange["token"]})
        async def get(self, url): return Response({"keys": [exchange.get("jwks_key", signing_key).as_dict(is_private=False)]})

    monkeypatch.setattr(OidcClient, "_metadata", fixed_metadata)
    monkeypatch.setattr("app.identity.oidc.httpx.AsyncClient", AsyncClient)

    def transaction(client: OidcClient):
        location, cookie = asyncio.run(client.begin("/organisation?invitation=safe"))
        params = parse_qs(urlparse(location).query)
        return cookie, params["state"][0], params["nonce"][0]

    def signed(nonce: str, **overrides):
        now = int(time.time())
        claims = {
            "iss": settings.oidc_issuer, "sub": "alice", "aud": settings.oidc_client_id,
            "iat": now, "exp": now + 300, "nonce": nonce, "email": "alice@example.test",
            **overrides,
        }
        return jwt.encode({"alg": "RS256", "kid": "provider-key"}, claims, signing_key, algorithms=["RS256"])

    with TestClient(app):
        with app.state.database.session_factory() as session:
            client = OidcClient(session, settings)

            cookie, state, nonce = transaction(client)
            exchange["token"] = "malformed-token"
            with pytest.raises(InvalidOidcResponse):
                asyncio.run(client.complete(cookie, state, "code"))

            cookie, state, nonce = transaction(client)
            exchange["token"] = signed(nonce, exp=int(time.time()) - 1)
            with pytest.raises(InvalidOidcResponse):
                asyncio.run(client.complete(cookie, state, "code"))

            cookie, state, nonce = transaction(client)
            exchange["token"] = signed(nonce, aud="another-client")
            with pytest.raises(InvalidOidcResponse, match="audience"):
                asyncio.run(client.complete(cookie, state, "code"))

            cookie, state, nonce = transaction(client)
            exchange["token"] = signed(nonce, aud=[settings.oidc_client_id, "another-client"])
            with pytest.raises(InvalidOidcResponse, match="authorized party"):
                asyncio.run(client.complete(cookie, state, "code"))

            cookie, state, nonce = transaction(client)
            exchange["token"] = signed(nonce)
            exchange["jwks_key"] = other_key
            with pytest.raises(InvalidOidcResponse):
                asyncio.run(client.complete(cookie, state, "code"))
            exchange["jwks_key"] = signing_key

            cookie, state, nonce = transaction(client)
            exchange["token"] = signed(nonce)
            claims, return_to = asyncio.run(client.complete(cookie, state, "valid-code"))
            assert claims["sub"] == "alice" and return_to.startswith("/organisation")
            with pytest.raises(InvalidOidcResponse, match="already used"):
                asyncio.run(client.complete(cookie, state, "replayed-code"))

            cookie, state, _ = transaction(client)
            assert client.cancel(cookie, state).startswith("/organisation")
            with pytest.raises(InvalidOidcResponse, match="already used"):
                client.cancel(cookie, state)
