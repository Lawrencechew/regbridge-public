from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.identity.errors import InvalidOidcResponse
from app.identity.models import OidcTransactionRecord
from app.identity.service import digest, is_expired
from app.persistence.models import utc_now


class OidcClient:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def _metadata(self) -> dict[str, object]:
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await client.get(self.settings.oidc_discovery_url)
                response.raise_for_status()
                metadata = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise InvalidOidcResponse("OIDC discovery failed.") from exc
        if metadata.get("issuer") != self.settings.oidc_issuer:
            raise InvalidOidcResponse("OIDC discovery issuer does not match configuration.")
        for required in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            if not isinstance(metadata.get(required), str):
                raise InvalidOidcResponse("OIDC discovery metadata is incomplete.")
        return metadata

    async def begin(self, return_to: str = "/") -> tuple[str, str]:
        metadata = await self._metadata()
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        transaction = secrets.token_urlsafe(48)
        self.session.add(OidcTransactionRecord(
            transaction_hash=digest(transaction, self.settings.application_secret), state_hash=digest(state, self.settings.application_secret), nonce=nonce,
            code_verifier=verifier, return_to=self._safe_return_to(return_to),
            expires_at=utc_now() + timedelta(seconds=self.settings.oidc_transaction_expiry_seconds),
        ))
        self.session.commit()
        query = urlencode({
            "response_type": "code", "client_id": self.settings.oidc_client_id,
            "redirect_uri": self.settings.oidc_redirect_uri,
            "scope": "openid email profile", "state": state, "nonce": nonce,
            "code_challenge": challenge, "code_challenge_method": "S256",
        })
        return f"{metadata['authorization_endpoint']}?{query}", transaction

    @staticmethod
    def _safe_return_to(value: str) -> str:
        if not value.startswith("/") or value.startswith("//") or "\\" in value or any(ord(character) < 32 for character in value):
            return "/"
        return value

    def cancel(self, transaction_token: str | None, state: str | None) -> str:
        transaction = self.session.scalar(select(OidcTransactionRecord).where(OidcTransactionRecord.transaction_hash == digest(transaction_token or "", self.settings.application_secret)))
        if transaction is None or transaction.consumed_at is not None or is_expired(transaction.expires_at) or not state or not secrets.compare_digest(transaction.state_hash, digest(state, self.settings.application_secret)):
            raise InvalidOidcResponse("OIDC state is invalid, expired, or already used.")
        transaction.consumed_at = utc_now()
        self.session.commit()
        return transaction.return_to

    async def complete(self, transaction_token: str | None, state: str | None, code: str | None) -> tuple[dict[str, object], str]:
        now = utc_now()
        transaction = self.session.scalar(select(OidcTransactionRecord).where(OidcTransactionRecord.transaction_hash == digest(transaction_token or "", self.settings.application_secret)))
        if transaction is None or transaction.consumed_at is not None or is_expired(transaction.expires_at) or not state or not secrets.compare_digest(transaction.state_hash, digest(state, self.settings.application_secret)) or not code:
            raise InvalidOidcResponse("OIDC state is invalid, expired, or already used.")
        metadata = await self._metadata()
        payload = {
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": self.settings.oidc_redirect_uri,
            "client_id": self.settings.oidc_client_id,
            "code_verifier": transaction.code_verifier,
        }
        if self.settings.oidc_client_secret:
            payload["client_secret"] = self.settings.oidc_client_secret
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                token_response = await client.post(str(metadata["token_endpoint"]), data=payload, headers={"Accept": "application/json"})
                token_response.raise_for_status()
                token = token_response.json()
                jwks_response = await client.get(str(metadata["jwks_uri"]))
                jwks_response.raise_for_status()
                jwks = jwks_response.json()
            id_token = token.get("id_token")
            if not isinstance(id_token, str):
                raise InvalidOidcResponse("The token response contained no ID token.")
            allowed = {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"}
            advertised = metadata.get("id_token_signing_alg_values_supported")
            algorithms = allowed.intersection(advertised) if isinstance(advertised, list) else {"RS256"}
            if not algorithms:
                raise InvalidOidcResponse("The provider advertises no supported secure ID-token algorithm.")
            token_object = jwt.decode(id_token, KeySet.import_key_set(jwks), algorithms=algorithms)
            claims = token_object.claims
            if token_object.header.get("alg") in {None, "none"}:
                raise InvalidOidcResponse("Unsigned ID tokens are not accepted.")
            JWTClaimsRegistry(
                iss={"essential": True, "value": self.settings.oidc_issuer},
                sub={"essential": True}, aud={"essential": True},
                exp={"essential": True}, iat={"essential": True},
            ).validate(claims)
            audience = claims.get("aud")
            if isinstance(audience, str):
                audiences = [audience]
            elif isinstance(audience, list) and all(isinstance(item, str) for item in audience):
                audiences = audience
            else:
                raise InvalidOidcResponse("The ID token audience is invalid.")
            if self.settings.oidc_client_id not in audiences:
                raise InvalidOidcResponse("The ID token audience is invalid.")
            if len(audiences) > 1 and claims.get("azp") != self.settings.oidc_client_id:
                raise InvalidOidcResponse("The ID token authorized party is invalid.")
            if not secrets.compare_digest(str(claims.get("nonce") or ""), transaction.nonce):
                raise InvalidOidcResponse("The ID token nonce is invalid.")
        except InvalidOidcResponse:
            raise
        except (httpx.HTTPError, ValueError, KeyError, JoseError) as exc:
            raise InvalidOidcResponse() from exc
        transaction.consumed_at = now
        self.session.commit()
        return dict(claims), transaction.return_to
