from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.persistence.models import RunState


class PersistenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CreateRunRequest(PersistenceModel):
    pack_id: str = Field(min_length=1, max_length=120)
    pack_version: str = Field(min_length=1, max_length=64)


class RunPack(PersistenceModel):
    id: str
    version: str
    fingerprint: str


class RunSource(PersistenceModel):
    display_name: str | None
    source_type: str | None
    size_bytes: int | None
    sha256: str | None
    selected_sheet: str | None
    header_row: int | None
    header_signature: str | None
    signature_version: str | None


class RunMapping(PersistenceModel):
    canonical_schema_id: str | None
    canonical_schema_version: str | None
    fingerprint: str | None
    definition: dict[str, Any] | None
    confirmed_at: datetime | None
    profile_id: str | None
    profile_version: int | None


class PreflightSummary(PersistenceModel):
    snapshot_id: str | None
    dataset_fingerprint: str | None
    validation_report_fingerprint: str | None
    reconciliation_report_fingerprint: str | None
    blocking_count: int
    review_count: int
    passed_count: int
    skipped_count: int
    ready: bool
    can_generate: bool


class ArtifactSummary(PersistenceModel):
    id: str
    created_at: datetime
    filename: str
    media_type: str
    size_bytes: int
    byte_sha256: str
    logical_generation_fingerprint: str
    retained_bytes: Literal[False] = False
    storage_reference: None = None


class AuditEvent(PersistenceModel):
    id: str
    event_type: str
    run_revision: int
    occurred_at: datetime
    metadata: dict[str, Any]


class RunSummary(PersistenceModel):
    id: str
    state: RunState
    revision: int
    created_at: datetime
    updated_at: datetime
    pack: RunPack
    source_display_name: str | None
    blocking_count: int
    review_count: int
    preflight_ready: bool
    output_generated: bool


class RunDetail(PersistenceModel):
    id: str
    state: RunState
    revision: int
    created_at: datetime
    updated_at: datetime
    pack: RunPack
    source: RunSource
    mapping: RunMapping
    preflight: PreflightSummary
    artifact: ArtifactSummary | None
    invalidation_reason: str | None
    audit_events: tuple[AuditEvent, ...]
    workflow_sections: tuple[dict[str, Any], ...] = ()


class RunList(PersistenceModel):
    runs: tuple[RunSummary, ...]


class MutationMetadata(PersistenceModel):
    run_id: str
    run_state: RunState
    run_revision: int


class SaveMappingProfileRequest(PersistenceModel):
    run_id: str = Field(min_length=36, max_length=36)
    display_name: str | None = Field(default=None, max_length=160)
    base_profile_id: str | None = Field(default=None, min_length=36, max_length=36)
    recommendation_origins: dict[str, Literal["exact", "alias", "manual"]] = Field(default_factory=dict)


class MappingProfileVersion(PersistenceModel):
    profile_id: str
    profile_version: int
    created_at: datetime
    confirmed_at: datetime
    display_name: str | None
    pack: RunPack
    canonical_schema_id: str
    canonical_schema_version: str
    source_header_signature: str
    source_signature_version: str
    mapping_fingerprint: str
    mapping_definition: dict[str, Any]
    recommendation_origins: dict[str, Any]
    section_id: str | None = None


class MappingProfileSummary(PersistenceModel):
    profile_id: str
    display_name: str | None
    latest_version: int
    pack: RunPack
    canonical_schema_id: str
    canonical_schema_version: str
    source_header_signature: str
    created_at: datetime
    updated_at: datetime
    section_id: str | None = None


class MappingProfileDetail(PersistenceModel):
    profile_id: str
    created_at: datetime
    updated_at: datetime
    versions: tuple[MappingProfileVersion, ...]


class MappingProfileList(PersistenceModel):
    profiles: tuple[MappingProfileSummary, ...]


class MappingProfileMatch(PersistenceModel):
    profiles: tuple[MappingProfileVersion, ...]
