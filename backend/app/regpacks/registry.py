import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from app.regpacks.errors import (
    DuplicateRegPackError,
    RegPackEffectivePeriodError,
    RegPackNotFoundError,
    RegPackVersionError,
)
from app.regpacks.loader import RegPackLoader
from app.regpacks.models import LoadedRegPack
from app.regpacks.version import RegPackVersion


class RegPackRegistry:
    def __init__(self, root: Path, loader: RegPackLoader | None = None) -> None:
        self.root = root
        self.loader = loader or RegPackLoader()
        self._packs: dict[str, dict[RegPackVersion, LoadedRegPack]] = {}

    def discover(self) -> None:
        root = self.root.resolve()
        if not root.exists():
            raise RegPackNotFoundError("The configured RegPack root does not exist.")
        if not root.is_dir():
            raise RegPackNotFoundError("The configured RegPack root is not a directory.")

        discovered: dict[str, dict[RegPackVersion, LoadedRegPack]] = {}
        for manifest_path in self._manifest_paths(root):
            pack = self.loader.load_pack(manifest_path)
            parsed_version = pack.parsed_version
            if manifest_path.parent.name != pack.version:
                raise RegPackVersionError(
                    "The RegPack version directory does not match the manifest version."
                )
            versions = discovered.setdefault(pack.id, {})
            if parsed_version in versions:
                raise DuplicateRegPackError(
                    "The RegPack ID and version combination must be unique."
                )
            versions[parsed_version] = pack

        self._packs = discovered

    @staticmethod
    def _manifest_paths(root: Path) -> Iterator[Path]:
        for current, directories, files in os.walk(root, followlinks=False):
            directories[:] = [
                name
                for name in directories
                if not name.startswith(".") and not (Path(current) / name).is_symlink()
            ]
            if "manifest.yaml" not in files:
                continue
            manifest_file = Path(current) / "manifest.yaml"
            if manifest_file.is_symlink():
                continue
            candidate = manifest_file.resolve()
            if candidate.is_relative_to(root):
                yield candidate

    def list_packs(self) -> list[LoadedRegPack]:
        return [
            self._packs[pack_id][max(self._packs[pack_id])]
            for pack_id in sorted(self._packs)
        ]

    def list_loaded_versions(self) -> list[LoadedRegPack]:
        return [
            self._packs[pack_id][version]
            for pack_id in sorted(self._packs)
            for version in sorted(self._packs[pack_id])
        ]

    def list_versions(self, pack_id: str) -> list[str]:
        versions = self._packs.get(pack_id)
        if versions is None:
            raise RegPackNotFoundError("The requested RegPack was not found.")
        return [str(version) for version in sorted(versions)]

    def get(self, pack_id: str, version: str) -> LoadedRegPack:
        parsed_version = RegPackVersion.parse(version)
        versions = self._packs.get(pack_id)
        if versions is None or parsed_version not in versions:
            raise RegPackNotFoundError("The requested RegPack was not found.")
        return versions[parsed_version]

    def get_effective(self, pack_id: str, effective_on: date) -> LoadedRegPack:
        versions = self._packs.get(pack_id)
        if versions is None:
            raise RegPackNotFoundError("The requested RegPack was not found.")
        matches = [
            pack
            for pack in versions.values()
            if pack.effective.includes(effective_on)
        ]
        if not matches:
            raise RegPackEffectivePeriodError(
                "No RegPack version is effective on the requested date."
            )
        if len(matches) > 1:
            raise RegPackEffectivePeriodError(
                "Multiple RegPack versions are effective on the requested date."
            )
        return matches[0]

    @property
    def pack_count(self) -> int:
        return len(self._packs)

    @property
    def version_count(self) -> int:
        return sum(len(versions) for versions in self._packs.values())
