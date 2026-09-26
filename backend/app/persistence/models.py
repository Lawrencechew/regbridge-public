from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def opaque_id() -> str:
    return str(uuid4())


class RunState(StrEnum):
    DRAFT = "DRAFT"
    SOURCE_INSPECTED = "SOURCE_INSPECTED"
    MAPPING_CONFIRMED = "MAPPING_CONFIRMED"
    PREFLIGHT_READY = "PREFLIGHT_READY"
    PREFLIGHT_BLOCKED = "PREFLIGHT_BLOCKED"
    OUTPUT_GENERATED = "OUTPUT_GENERATED"
    INVALIDATED = "INVALIDATED"


class Base(DeclarativeBase):
    pass


class RegFlowRunRecord(Base):
    __tablename__ = "regflow_runs"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_regflow_runs_revision"),
        CheckConstraint("latest_blocking_count >= 0", name="ck_regflow_runs_blocking"),
        CheckConstraint("latest_review_count >= 0", name="ck_regflow_runs_review"),
        CheckConstraint("latest_passed_count >= 0", name="ck_regflow_runs_passed"),
        CheckConstraint("latest_skipped_count >= 0", name="ck_regflow_runs_skipped"),
        Index("ix_regflow_runs_updated_at", "updated_at"),
        Index("ix_regflow_runs_state", "state"),
        Index("ix_regflow_runs_source_sha256", "source_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=opaque_id)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default=RunState.DRAFT.value)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    pack_id: Mapped[str] = mapped_column(String(120), nullable=False)
    pack_version: Mapped[str] = mapped_column(String(64), nullable=False)
    pack_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    source_display_name: Mapped[str | None] = mapped_column(String(255))
    source_type: Mapped[str | None] = mapped_column(String(16))
    source_size_bytes: Mapped[int | None] = mapped_column(Integer)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    selected_sheet: Mapped[str | None] = mapped_column(String(255))
    header_row: Mapped[int | None] = mapped_column(Integer)
    source_header_signature: Mapped[str | None] = mapped_column(String(64))
    source_signature_version: Mapped[str | None] = mapped_column(String(40))

    canonical_schema_id: Mapped[str | None] = mapped_column(String(120))
    canonical_schema_version: Mapped[str | None] = mapped_column(String(64))
    mapping_fingerprint: Mapped[str | None] = mapped_column(String(64))
    mapping_definition: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    mapping_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mapping_profile_id: Mapped[str | None] = mapped_column(String(36))
    mapping_profile_version: Mapped[int | None] = mapped_column(Integer)

    dataset_fingerprint: Mapped[str | None] = mapped_column(String(64))
    validation_report_fingerprint: Mapped[str | None] = mapped_column(String(64))
    reconciliation_report_fingerprint: Mapped[str | None] = mapped_column(String(64))
    latest_blocking_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_passed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    preflight_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_generate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latest_preflight_snapshot_id: Mapped[str | None] = mapped_column(String(36))
    latest_artifact_id: Mapped[str | None] = mapped_column(String(36))
    invalidation_reason: Mapped[str | None] = mapped_column(String(255))
    workflow_sections: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)

    preflight_snapshots: Mapped[list[PreflightSnapshotRecord]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    artifacts: Mapped[list[ArtifactMetadataRecord]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    audit_events: Mapped[list[AuditEventRecord]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    idempotency_records: Mapped[list[IdempotencyRecord]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class PreflightSnapshotRecord(Base):
    __tablename__ = "preflight_snapshots"
    __table_args__ = (
        CheckConstraint("run_revision >= 1", name="ck_preflight_revision"),
        CheckConstraint("blocking_count >= 0", name="ck_preflight_blocking"),
        CheckConstraint("review_count >= 0", name="ck_preflight_review"),
        CheckConstraint("passed_count >= 0", name="ck_preflight_passed"),
        CheckConstraint("skipped_count >= 0", name="ck_preflight_skipped"),
        Index("ix_preflight_run_created", "run_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=opaque_id)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("regflow_runs.id", ondelete="CASCADE"), nullable=False)
    run_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    pack_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_header_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_report_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    reconciliation_report_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    blocking_count: Mapped[int] = mapped_column(Integer, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False)
    passed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ready: Mapped[bool] = mapped_column(Boolean, nullable=False)
    can_generate: Mapped[bool] = mapped_column(Boolean, nullable=False)
    current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    section_summaries: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    run: Mapped[RegFlowRunRecord] = relationship(back_populates="preflight_snapshots")


class ArtifactMetadataRecord(Base):
    __tablename__ = "artifact_metadata"
    __table_args__ = (Index("ix_artifact_run_created", "run_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=opaque_id)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("regflow_runs.id", ondelete="CASCADE"), nullable=False)
    run_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    pack_id: Mapped[str] = mapped_column(String(120), nullable=False)
    pack_version: Mapped[str] = mapped_column(String(64), nullable=False)
    pack_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    output_definition_id: Mapped[str] = mapped_column(String(120), nullable=False)
    output_definition_version: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_generation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    retained_bytes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage_reference: Mapped[str | None] = mapped_column(String(500))
    current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    run: Mapped[RegFlowRunRecord] = relationship(back_populates="artifacts")


class AuditEventRecord(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_run_occurred", "run_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=opaque_id)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("regflow_runs.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    run_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    run: Mapped[RegFlowRunRecord] = relationship(back_populates="audit_events")


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("organisation_id", "operation", "key", name="uq_idempotency_organisation_operation_key"),
        Index("ix_idempotency_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=opaque_id)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("regflow_runs.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    run: Mapped[RegFlowRunRecord | None] = relationship(back_populates="idempotency_records")


class MappingProfileRecord(Base):
    __tablename__ = "mapping_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=opaque_id)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    versions: Mapped[list[MappingProfileVersionRecord]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True,
        order_by="MappingProfileVersionRecord.profile_version",
    )


class MappingProfileVersionRecord(Base):
    __tablename__ = "mapping_profile_versions"
    __table_args__ = (
        CheckConstraint("profile_version >= 1", name="ck_mapping_profile_version"),
        UniqueConstraint("profile_id", "profile_version", name="uq_mapping_profile_version"),
        Index("ix_profile_signature", "source_header_signature"),
        Index("ix_profile_pack", "pack_id", "pack_version"),
        Index(
            "ix_profile_section_compatibility",
            "pack_id", "pack_version", "section_id", "canonical_schema_id",
            "canonical_schema_version", "source_header_signature",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=opaque_id)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=False)
    profile_id: Mapped[str] = mapped_column(ForeignKey("mapping_profiles.id", ondelete="CASCADE"), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    display_name: Mapped[str | None] = mapped_column(String(160))
    pack_id: Mapped[str] = mapped_column(String(120), nullable=False)
    pack_version: Mapped[str] = mapped_column(String(64), nullable=False)
    pack_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_schema_id: Mapped[str] = mapped_column(String(120), nullable=False)
    canonical_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    section_id: Mapped[str | None] = mapped_column(String(120))
    source_header_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    source_signature_version: Mapped[str] = mapped_column(String(40), nullable=False)
    mapping_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    recommendation_origins: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    profile: Mapped[MappingProfileRecord] = relationship(back_populates="versions")
