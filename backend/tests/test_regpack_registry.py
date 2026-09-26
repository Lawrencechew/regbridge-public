import os
from datetime import date

import pytest

from app.regpacks.errors import (
    DuplicateRegPackError,
    RegPackEffectivePeriodError,
    RegPackNotFoundError,
    RegPackVersionError,
)
from app.regpacks.registry import RegPackRegistry
from app.regpacks.version import RegPackVersion
from tests.helpers import manifest_data, write_manifest


def test_empty_registry_is_valid(tmp_path) -> None:
    registry = RegPackRegistry(tmp_path)
    registry.discover()

    assert registry.list_packs() == []
    assert registry.pack_count == 0
    assert registry.version_count == 0


def test_single_pack_is_discovered(tmp_path) -> None:
    write_manifest(tmp_path)
    registry = RegPackRegistry(tmp_path)
    registry.discover()

    assert [pack.id for pack in registry.list_packs()] == ["example-sample"]


def test_hidden_directories_are_ignored(tmp_path) -> None:
    write_manifest(tmp_path, regulator_directory=".hidden")
    registry = RegPackRegistry(tmp_path)
    registry.discover()

    assert registry.list_packs() == []


def test_versions_compare_and_sort_numerically(tmp_path) -> None:
    for version in ["1.9.0", "1.10.0", "2.0.0"]:
        write_manifest(
            tmp_path,
            version_directory=version,
            data=manifest_data(version=version),
        )
    registry = RegPackRegistry(tmp_path)
    registry.discover()

    assert RegPackVersion.parse("1.10.0") > RegPackVersion.parse("1.9.0")
    assert registry.list_versions("example-sample") == ["1.9.0", "1.10.0", "2.0.0"]


def test_duplicate_pack_id_and_version_fails_discovery(tmp_path) -> None:
    write_manifest(tmp_path, regulator_directory="one")
    write_manifest(tmp_path, regulator_directory="two")

    with pytest.raises(DuplicateRegPackError):
        RegPackRegistry(tmp_path).discover()


def test_version_directory_must_match_manifest(tmp_path) -> None:
    write_manifest(
        tmp_path,
        version_directory="1.0.0",
        data=manifest_data(version="1.1.0"),
    )

    with pytest.raises(RegPackVersionError):
        RegPackRegistry(tmp_path).discover()


def test_exact_version_retrieval(tmp_path) -> None:
    write_manifest(tmp_path)
    registry = RegPackRegistry(tmp_path)
    registry.discover()

    assert registry.get("example-sample", "1.0.0").version == "1.0.0"


def test_missing_pack_and_version_are_controlled(tmp_path) -> None:
    write_manifest(tmp_path)
    registry = RegPackRegistry(tmp_path)
    registry.discover()

    with pytest.raises(RegPackNotFoundError):
        registry.get("missing-pack", "1.0.0")
    with pytest.raises(RegPackNotFoundError):
        registry.get("example-sample", "2.0.0")


def test_effective_version_selection(tmp_path) -> None:
    write_manifest(
        tmp_path,
        version_directory="1.0.0",
        data=manifest_data(version="1.0.0", effective_to="2026-06-30"),
    )
    write_manifest(
        tmp_path,
        version_directory="1.1.0",
        data=manifest_data(version="1.1.0", effective_from="2026-07-01"),
    )
    registry = RegPackRegistry(tmp_path)
    registry.discover()

    selected = registry.get_effective("example-sample", date(2026, 8, 14))
    assert selected.version == "1.1.0"


def test_no_effective_version_is_controlled(tmp_path) -> None:
    write_manifest(
        tmp_path,
        data=manifest_data(effective_from="2026-01-01", effective_to="2026-01-31"),
    )
    registry = RegPackRegistry(tmp_path)
    registry.discover()

    with pytest.raises(RegPackEffectivePeriodError):
        registry.get_effective("example-sample", date(2026, 2, 1))


def test_overlapping_effective_versions_are_ambiguous(tmp_path) -> None:
    write_manifest(
        tmp_path,
        version_directory="1.0.0",
        data=manifest_data(version="1.0.0"),
    )
    write_manifest(
        tmp_path,
        version_directory="1.1.0",
        data=manifest_data(version="1.1.0", effective_from="2026-06-01"),
    )
    registry = RegPackRegistry(tmp_path)
    registry.discover()

    with pytest.raises(RegPackEffectivePeriodError):
        registry.get_effective("example-sample", date(2026, 8, 14))


def test_discovery_does_not_follow_directory_symlink(tmp_path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    write_manifest(outside)
    link = tmp_path / "linked"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable on this platform")

    registry = RegPackRegistry(tmp_path)
    registry.discover()

    assert registry.list_packs() == []
