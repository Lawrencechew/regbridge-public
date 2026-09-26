from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.persistence.models import (
    ArtifactMetadataRecord,
    AuditEventRecord,
    IdempotencyRecord,
    MappingProfileRecord,
    MappingProfileVersionRecord,
    PreflightSnapshotRecord,
    RegFlowRunRecord,
)


class PersistenceRepository:
    """All SQLAlchemy queries used by Phase 9 orchestration live here."""

    def __init__(self, session: Session, organisation_id: str) -> None:
        self.session = session
        self.organisation_id = organisation_id

    def add(self, record):
        self.session.add(record)
        return record

    def flush(self) -> None:
        self.session.flush()

    def get_run(self, run_id: str, *, lock: bool = False) -> RegFlowRunRecord | None:
        query: Select = select(RegFlowRunRecord).where(RegFlowRunRecord.id == run_id, RegFlowRunRecord.organisation_id == self.organisation_id)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def get_run_detail(self, run_id: str) -> RegFlowRunRecord | None:
        return self.session.scalar(
            select(RegFlowRunRecord)
            .where(RegFlowRunRecord.id == run_id, RegFlowRunRecord.organisation_id == self.organisation_id)
            .options(
                selectinload(RegFlowRunRecord.audit_events),
                selectinload(RegFlowRunRecord.artifacts),
            )
        )

    def list_runs(self, *, limit: int, state: str | None) -> list[RegFlowRunRecord]:
        query = select(RegFlowRunRecord).where(RegFlowRunRecord.organisation_id == self.organisation_id)
        if state is not None:
            query = query.where(RegFlowRunRecord.state == state)
        query = query.order_by(RegFlowRunRecord.updated_at.desc()).limit(limit)
        return list(self.session.scalars(query))

    def idempotency(self, operation: str, key: str) -> IdempotencyRecord | None:
        return self.session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.operation == operation,
                IdempotencyRecord.key == key,
                IdempotencyRecord.organisation_id == self.organisation_id,
            )
        )

    def artifact(self, artifact_id: str) -> ArtifactMetadataRecord | None:
        return self.session.scalar(select(ArtifactMetadataRecord).where(ArtifactMetadataRecord.id == artifact_id, ArtifactMetadataRecord.organisation_id == self.organisation_id))

    def invalidate_snapshots(self, run_id: str) -> None:
        for snapshot in self.session.scalars(
            select(PreflightSnapshotRecord).where(
                PreflightSnapshotRecord.run_id == run_id,
                PreflightSnapshotRecord.organisation_id == self.organisation_id,
                PreflightSnapshotRecord.current.is_(True),
            )
        ):
            snapshot.current = False

    def invalidate_artifacts(self, run_id: str) -> None:
        for artifact in self.session.scalars(
            select(ArtifactMetadataRecord).where(
                ArtifactMetadataRecord.run_id == run_id,
                ArtifactMetadataRecord.organisation_id == self.organisation_id,
                ArtifactMetadataRecord.current.is_(True),
            )
        ):
            artifact.current = False

    def profile(self, profile_id: str) -> MappingProfileRecord | None:
        return self.session.scalar(
            select(MappingProfileRecord)
            .where(MappingProfileRecord.id == profile_id, MappingProfileRecord.organisation_id == self.organisation_id)
            .options(selectinload(MappingProfileRecord.versions))
        )

    def list_profiles(self) -> list[MappingProfileRecord]:
        return list(
            self.session.scalars(
                select(MappingProfileRecord).where(MappingProfileRecord.organisation_id == self.organisation_id)
                .options(selectinload(MappingProfileRecord.versions))
                .order_by(MappingProfileRecord.updated_at.desc())
            )
        )

    def matching_profiles(
        self,
        *,
        pack_id: str,
        pack_version: str,
        pack_fingerprint: str,
        schema_id: str,
        schema_version: str,
        source_signature: str,
        section_id: str | None = None,
    ) -> list[MappingProfileVersionRecord]:
        rows = list(
            self.session.scalars(
                select(MappingProfileVersionRecord)
                .where(
                    MappingProfileVersionRecord.pack_id == pack_id,
                    MappingProfileVersionRecord.organisation_id == self.organisation_id,
                    MappingProfileVersionRecord.pack_version == pack_version,
                    MappingProfileVersionRecord.pack_fingerprint == pack_fingerprint,
                    MappingProfileVersionRecord.canonical_schema_id == schema_id,
                    MappingProfileVersionRecord.canonical_schema_version == schema_version,
                    MappingProfileVersionRecord.source_header_signature == source_signature,
                    MappingProfileVersionRecord.section_id == section_id,
                )
                .order_by(
                    MappingProfileVersionRecord.profile_id,
                    MappingProfileVersionRecord.profile_version.desc(),
                )
            )
        )
        latest: dict[str, MappingProfileVersionRecord] = {}
        for row in rows:
            latest.setdefault(row.profile_id, row)
        return list(latest.values())
