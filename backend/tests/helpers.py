from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def manifest_data(
    *,
    pack_id: str = "example-sample",
    version: str = "1.0.0",
    effective_from: str = "2026-01-01",
    effective_to: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "id": pack_id,
        "name": "Synthetic Example RegPack",
        "regulator": {"code": "EXAMPLE", "name": "Synthetic Regulator"},
        "version": version,
        "effective": {"from": effective_from, "to": effective_to},
        "description": "Synthetic manifest used by automated tests.",
        "sources": [
            {
                "id": "SRC-001",
                "title": "Synthetic Official Requirement",
                "publisher": "Synthetic Regulator",
                "url": "https://example.com/regulation",
                "reference": "Section 1",
                "published_date": "2025-12-01",
                "checked_at": "2026-01-01",
            }
        ],
    }


def write_manifest(
    root: Path,
    *,
    regulator_directory: str = "example",
    pack_directory: str = "sample",
    version_directory: str = "1.0.0",
    data: dict[str, Any] | None = None,
) -> Path:
    path = root / regulator_directory / pack_directory / version_directory / "manifest.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(deepcopy(data or manifest_data()), sort_keys=False),
        encoding="utf-8",
    )
    return path
