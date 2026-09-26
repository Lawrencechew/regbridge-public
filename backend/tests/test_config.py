from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.version import __version__


def test_application_version_is_not_runtime_configurable(monkeypatch) -> None:
    monkeypatch.setenv("APP_VERSION", "9.9.9")

    settings = Settings(_env_file=None)

    assert settings.app_version == __version__


def test_settings_read_environment_and_parse_cors(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "https://console.example.test, https://admin.example.test",
    )

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.cors_origins == [
        "https://console.example.test",
        "https://admin.example.test",
    ]


def test_regpacks_path_can_be_configured_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("REGPACKS_PATH", "C:/regbridge-test-packs")

    settings = Settings(_env_file=None)

    assert settings.regpacks_path == Path("C:/regbridge-test-packs")


def test_import_security_limits_have_safe_defaults_and_are_configurable(monkeypatch) -> None:
    monkeypatch.setenv("IMPORT_MAX_ROWS", "123")
    settings = Settings(_env_file=None)

    assert settings.import_max_file_size_mb == 10
    assert settings.import_max_rows == 123
    assert settings.import_max_columns == 200
    assert settings.import_max_xlsx_sheets == 20
    assert settings.import_max_xlsx_zip_entries == 10_000
    assert settings.import_max_xlsx_uncompressed_mb == 100
    assert settings.import_max_xlsx_compression_ratio == 100
    assert settings.import_preview_rows == 20


def test_generation_capacity_uses_the_measured_ceiling(monkeypatch) -> None:
    monkeypatch.setenv("GENERATION_MAX_CONCURRENCY", "1")
    monkeypatch.setenv("GENERATION_RETRY_AFTER_SECONDS", "12")
    settings = Settings(_env_file=None)

    assert settings.generation_max_concurrency == 1
    assert settings.generation_retry_after_seconds == 12

    monkeypatch.setenv("GENERATION_MAX_CONCURRENCY", "3")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
