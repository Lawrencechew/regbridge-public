from datetime import date

import pytest

from app.regpacks.errors import RegPackManifestError, RegPackVersionError
from app.regpacks.loader import RegPackLoader
from tests.helpers import manifest_data, write_manifest


def test_valid_manifest_loads_as_typed_model(tmp_path) -> None:
    manifest = RegPackLoader().load(write_manifest(tmp_path))

    assert manifest.id == "example-sample"
    assert manifest.effective.from_date == date(2026, 1, 1)
    assert str(manifest.sources[0].url) == "https://example.com/regulation"


def test_invalid_yaml_is_rejected(tmp_path) -> None:
    path = tmp_path / "manifest.yaml"
    path.write_text("sources: [unterminated", encoding="utf-8")

    with pytest.raises(RegPackManifestError):
        RegPackLoader().load(path)


def test_missing_required_field_is_rejected(tmp_path) -> None:
    data = manifest_data()
    del data["id"]

    with pytest.raises(RegPackManifestError):
        RegPackLoader().load(write_manifest(tmp_path, data=data))


def test_invalid_pack_id_is_rejected(tmp_path) -> None:
    data = manifest_data(pack_id="INVALID_PACK")

    with pytest.raises(RegPackManifestError):
        RegPackLoader().load(write_manifest(tmp_path, data=data))


@pytest.mark.parametrize("version", ["1.0", "v1.0.0", "latest", "1.0.0-beta"])
def test_invalid_pack_version_is_rejected(tmp_path, version: str) -> None:
    data = manifest_data(version=version)

    with pytest.raises(RegPackVersionError):
        RegPackLoader().load(write_manifest(tmp_path, data=data))


def test_unsupported_manifest_schema_version_is_rejected(tmp_path) -> None:
    data = manifest_data()
    data["schema_version"] = "2.0"

    with pytest.raises(RegPackManifestError):
        RegPackLoader().load(write_manifest(tmp_path, data=data))


def test_effective_end_before_start_is_rejected(tmp_path) -> None:
    data = manifest_data(effective_from="2026-02-01", effective_to="2026-01-31")

    with pytest.raises(RegPackManifestError):
        RegPackLoader().load(write_manifest(tmp_path, data=data))


def test_manifest_requires_at_least_one_source(tmp_path) -> None:
    data = manifest_data()
    data["sources"] = []

    with pytest.raises(RegPackManifestError):
        RegPackLoader().load(write_manifest(tmp_path, data=data))


def test_invalid_source_url_is_rejected(tmp_path) -> None:
    data = manifest_data()
    data["sources"][0]["url"] = "file:///etc/passwd"

    with pytest.raises(RegPackManifestError):
        RegPackLoader().load(write_manifest(tmp_path, data=data))


def test_manifest_schema_1_0_rejects_executable_fields(tmp_path) -> None:
    data = manifest_data()
    data["status"] = "draft"

    with pytest.raises(RegPackManifestError):
        RegPackLoader().load(write_manifest(tmp_path, data=data))


def test_manifest_schema_1_1_requires_all_executable_metadata(tmp_path) -> None:
    data = manifest_data()
    data["schema_version"] = "1.1"

    with pytest.raises(RegPackManifestError):
        RegPackLoader().load(write_manifest(tmp_path, data=data))


def test_duplicate_source_ids_are_rejected(tmp_path) -> None:
    data = manifest_data()
    data["sources"].append(data["sources"][0].copy())

    with pytest.raises(RegPackManifestError):
        RegPackLoader().load(write_manifest(tmp_path, data=data))


@pytest.mark.parametrize("unsafe", ["../../secret.yaml", "C:\\secret.yaml", "/etc/passwd"])
def test_component_paths_must_be_relative_and_confined(tmp_path, unsafe: str) -> None:
    data = manifest_data()
    data.update(
        schema_version="1.1",
        status="draft",
        reporting={
            "frequency": "monthly",
            "submission_deadline": {"type": "day_of_following_period", "day": 7},
        },
        components={
            "canonical_schema": unsafe,
            "validation_rules": "validation.yaml",
            "reconciliation_rules": "reconciliation.yaml",
        },
    )

    with pytest.raises(RegPackManifestError):
        RegPackLoader().load(write_manifest(tmp_path, data=data))
