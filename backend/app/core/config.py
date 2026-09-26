from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.version import __version__


class Settings(BaseSettings):
    app_name: str = "regbridge-api"
    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = Field(default=False, validation_alias="APP_DEBUG")
    log_level: str = "INFO"
    application_secret: str = "development-only-change-me"
    cors_allowed_origins: str = Field(default="http://localhost:5180")
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    https_boundary: bool = False
    hsts_max_age_seconds: int = Field(default=31_536_000, ge=300, le=63_072_000)
    trust_proxy_headers: bool = False
    trusted_proxy_ips: str = ""
    regpacks_path: Path = Path("../regpacks")
    import_max_file_size_mb: int = Field(default=10, ge=1)
    import_max_rows: int = Field(default=50_000, ge=1)
    import_max_columns: int = Field(default=200, ge=1)
    import_max_xlsx_sheets: int = Field(default=20, ge=1)
    import_max_xlsx_zip_entries: int = Field(default=10_000, ge=1)
    import_max_xlsx_uncompressed_mb: int = Field(default=100, ge=1)
    import_max_xlsx_compression_ratio: float = Field(default=100, gt=0)
    import_preview_rows: int = Field(default=20, ge=1, le=100)
    output_max_file_size_mb: int = Field(default=20, ge=1)
    preflight_max_findings: int = Field(default=500, ge=1, le=10_000)
    database_url: str = Field(
        default="postgresql+psycopg://regbridge:regbridge-local-only@localhost:5432/regbridge"
    )
    database_sql_echo: bool = False
    persistence_enabled: bool = True
    auth_enabled: bool = False
    oidc_issuer: str | None = None
    oidc_discovery_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str = "http://localhost:8000/auth/callback"
    frontend_url: str = "http://localhost:5180"
    session_cookie_name: str = "regbridge_session"
    oidc_transaction_cookie_name: str = "regbridge_oidc_transaction"
    session_expiry_seconds: int = Field(default=28_800, ge=300, le=2_592_000)
    oidc_transaction_expiry_seconds: int = Field(default=600, ge=60, le=1800)
    invitation_expiry_hours: int = Field(default=168, ge=1, le=720)
    cookie_secure: bool | None = None
    cookie_samesite: str = Field(default="lax", pattern="^(lax|strict)$")
    csrf_header_name: str = "X-CSRF-Token"
    request_max_body_mb: int = Field(default=24, ge=1, le=100)
    mapping_max_characters: int = Field(default=250_000, ge=1_000, le=2_000_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_auth_requests: int = Field(default=30, ge=1, le=10_000)
    rate_limit_invitation_requests: int = Field(default=30, ge=1, le=10_000)
    rate_limit_expensive_requests: int = Field(default=60, ge=1, le=10_000)
    generation_max_concurrency: int = Field(default=2, ge=1, le=2)
    generation_retry_after_seconds: int = Field(default=5, ge=1, le=300)
    metrics_enabled: bool = True

    @property
    def app_version(self) -> str:
        """Expose the immutable build version without accepting an env override."""
        return __version__

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def secure_cookies(self) -> bool:
        return self.cookie_secure if self.cookie_secure is not None else self.app_env == "production"

    @property
    def allowed_hosts(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def proxy_ips(self) -> list[str]:
        return [item.strip() for item in self.trusted_proxy_ips.split(",") if item.strip()]

    @model_validator(mode="after")
    def validate_authentication(self):
        if self.auth_enabled and not all((self.oidc_issuer, self.oidc_discovery_url, self.oidc_client_id)):
            raise ValueError("OIDC issuer, discovery URL and client ID are required when authentication is enabled.")
        if self.app_env != "production":
            return self

        failures: list[str] = []
        if not self.auth_enabled:
            failures.append("authentication must be enabled")
        if len(self.application_secret) < 32 or self.application_secret == "development-only-change-me":
            failures.append("APPLICATION_SECRET must be a non-default value of at least 32 characters")
        if not self.secure_cookies:
            failures.append("secure cookies must be enabled")
        if not self.https_boundary:
            failures.append("HTTPS_BOUNDARY must be true")
        if self.app_debug:
            failures.append("debug mode must be disabled")
        if self.database_sql_echo:
            failures.append("database SQL echo must be disabled")
        if not self.persistence_enabled:
            failures.append("persistence must be enabled")
        if not self.database_url or self.database_url.startswith("sqlite"):
            failures.append("production DATABASE_URL must use PostgreSQL")
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            failures.append("production DATABASE_URL must be an explicit PostgreSQL URL")
        if not self.cors_origins or any("*" in origin for origin in self.cors_origins):
            failures.append("CORS origins must be explicit and cannot contain a wildcard")
        if any(urlparse(origin).scheme != "https" for origin in self.cors_origins):
            failures.append("production CORS origins must use HTTPS")
        if not self.allowed_hosts or any("*" in host for host in self.allowed_hosts):
            failures.append("TRUSTED_HOSTS must be explicit and cannot contain a wildcard")
        if not 900 <= self.session_expiry_seconds <= 86_400:
            failures.append("session lifetime must be between 15 minutes and 24 hours")
        required_urls = {
            "OIDC_ISSUER": self.oidc_issuer,
            "OIDC_DISCOVERY_URL": self.oidc_discovery_url,
            "OIDC_REDIRECT_URI": self.oidc_redirect_uri,
            "FRONTEND_URL": self.frontend_url,
        }
        for name, value in required_urls.items():
            parsed = urlparse(value or "")
            if parsed.scheme != "https" or not parsed.hostname:
                failures.append(f"{name} must be an absolute HTTPS URL")
            elif parsed.hostname in {"localhost", "127.0.0.1"} or set(parsed.hostname.lower().split(".")) & {"example", "test", "invalid", "localhost"}:
                failures.append(f"{name} cannot use a development or placeholder host")
        if not self.oidc_client_id or self.oidc_client_id in {"replace-me", "regbridge-test"}:
            failures.append("OIDC_CLIENT_ID must be configured")
        if not self.oidc_client_secret or len(self.oidc_client_secret) < 16:
            failures.append("OIDC_CLIENT_SECRET must be configured for the production web client")
        if self.trust_proxy_headers and (not self.proxy_ips or any("*" in item for item in self.proxy_ips)):
            failures.append("trusted proxy IPs must be explicit when proxy headers are enabled")
        if failures:
            raise ValueError("Unsafe production configuration: " + "; ".join(failures) + ".")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
