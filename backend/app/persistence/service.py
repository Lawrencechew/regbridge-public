from __future__ import annotations

import hashlib
import json
import logging
from datetime import timezone
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.imports.models import ImportMapping, SourceFileInspection, WorkflowImportMapping
from app.outputs.models import GeneratedArtifact
from app.persistence.errors import (
    IdempotencyKeyReuseError,
    InvalidRunTransitionError,
    MappingProfileNotFoundError,
    MappingProfileStaleError,
    PersistenceUnavailableError,
    RegPackIntegrityError,
    RunNotFoundError,
    RunRevisionConflictError,
)
from app.persistence.models import (
    ArtifactMetadataRecord,
    AuditEventRecord,
    IdempotencyRecord,
    MappingProfileRecord,
    MappingProfileVersionRecord,
    PreflightSnapshotRecord,
    RegFlowRunRecord,
    RunState,
    utc_now,
)
from app.persistence.repositories import PersistenceRepository
from app.persistence.schemas import (
    ArtifactSummary,
    AuditEvent,
    MappingProfileDetail,
    MappingProfileList,
    MappingProfileMatch,
    MappingProfileSummary,
    MappingProfileVersion,
    MutationMetadata,
    PreflightSummary,
    RunDetail,
    RunList,
    RunMapping,
    RunPack,
    RunSource,
    RunSummary,
)
from app.regflow.models import RegFlowPreflightResult, RegFlowWorkflowPreflightResult
from app.regpacks.models import LoadedRegPack
from app.identity.models import LEGACY_ORGANISATION_ID


logger = logging.getLogger(__name__)


CREATE_RUN_OPERATION = "regflow.run.create"
GENERATE_OPERATION = "regflow.output.generate"


def canonical_fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def logical_generation_fingerprint(
    *, pack_fingerprint: str, dataset_fingerprint: str,
    mapping_fingerprint: str, output_definition_id: str,
    output_definition_version: str,
) -> str:
    return canonical_fingerprint({
        "algorithm": "regbridge-logical-generation-v1",
        "pack_fingerprint": pack_fingerprint,
        "dataset_fingerprint": dataset_fingerprint,
        "mapping_fingerprint": mapping_fingerprint,
        "output_definition": {
            "id": output_definition_id,
            "version": output_definition_version,
        },
    })


class PersistenceService:
    def __init__(self, session: Session, organisation_id: str = LEGACY_ORGANISATION_ID, request_id: str | None = None) -> None:
        self.session = session
        self.organisation_id = organisation_id
        self.request_id = request_id
        self.repository = PersistenceRepository(session, organisation_id)

    def _atomic(self, operation):
        try:
            with self.session.begin():
                return operation()
        except (
            RunNotFoundError, RunRevisionConflictError, InvalidRunTransitionError,
            MappingProfileNotFoundError, MappingProfileStaleError,
            IdempotencyKeyReuseError, RegPackIntegrityError,
        ):
            raise
        except SQLAlchemyError as exc:
            raise PersistenceUnavailableError() from exc

    @staticmethod
    def _check_key(key: str | None) -> str:
        if key is None or not key.strip() or len(key) > 128:
            raise InvalidRunTransitionError(
                "An Idempotency-Key between 1 and 128 characters is required."
            )
        return key

    def create_run(self, pack: LoadedRegPack, key: str | None) -> RunDetail:
        key = self._check_key(key)
        if pack.fingerprint is None:
            raise RegPackIntegrityError()
        request_fp = canonical_fingerprint({"pack_id": pack.id, "pack_version": pack.version})

        def operation():
            existing = self.repository.idempotency(CREATE_RUN_OPERATION, key)
            if existing is not None:
                if existing.request_fingerprint != request_fp:
                    raise IdempotencyKeyReuseError()
                run = self.repository.get_run_detail(existing.resource_id)
                if run is None:
                    raise RunNotFoundError()
                return self._detail(run)
            run = self.repository.add(RegFlowRunRecord(
                organisation_id=self.organisation_id,
                pack_id=pack.id,
                pack_version=pack.version,
                pack_fingerprint=pack.fingerprint,
            ))
            self.repository.flush()
            self._audit(run, "run_created", {
                "pack_id": pack.id,
                "pack_version": pack.version,
                "pack_fingerprint": pack.fingerprint,
                "to_state": RunState.DRAFT.value,
            })
            self.repository.add(IdempotencyRecord(
                organisation_id=self.organisation_id,
                key=key,
                operation=CREATE_RUN_OPERATION,
                request_fingerprint=request_fp,
                resource_id=run.id,
                run_id=run.id,
            ))
            self.repository.flush()
            return self._detail(run)

        try:
            return self._atomic(operation)
        except PersistenceUnavailableError as failure:
            # Two identical creates can both observe an absent idempotency row. The
            # unique constraint selects one winner; after rollback, return that
            # committed result instead of misclassifying the collision as an outage.
            try:
                existing = self.repository.idempotency(CREATE_RUN_OPERATION, key)
                if existing is None:
                    raise failure
                if existing.request_fingerprint != request_fp:
                    raise IdempotencyKeyReuseError()
                run = self.repository.get_run_detail(existing.resource_id)
                if run is None:
                    raise failure
                return self._detail(run)
            except SQLAlchemyError:
                raise failure

    def list_runs(self, *, limit: int, state: RunState | None) -> RunList:
        return RunList(runs=tuple(
            self._summary(run)
            for run in self.repository.list_runs(
                limit=limit, state=state.value if state else None
            )
        ))

    def get_run(self, run_id: str) -> RunDetail:
        run = self.repository.get_run_detail(run_id)
        if run is None:
            raise RunNotFoundError()
        return self._detail(run)

    def delete_run(self, run_id: str) -> None:
        def operation():
            run = self.repository.get_run(run_id, lock=True)
            if run is None:
                raise RunNotFoundError()
            self.session.delete(run)
        self._atomic(operation)

    def persist_inspection(
        self,
        *, run_id: str, expected_revision: int, pack: LoadedRegPack,
        inspection: SourceFileInspection,
    ) -> MutationMetadata:
        def operation():
            run = self._locked_run(run_id, expected_revision, pack)
            incoming = (
                inspection.file_sha256, inspection.selected_sheet,
                inspection.header_row, inspection.source_header_signature,
            )
            current = (
                run.source_sha256, run.selected_sheet, run.header_row,
                run.source_header_signature,
            )
            if run.source_sha256 is not None and incoming == current:
                return self._mutation(run)
            changed = run.source_sha256 is not None and incoming != current
            if changed:
                self._invalidate_downstream(run, "Source input or structure changed.")
                self._audit(run, "run_invalidated", {
                    "reason": "source_changed",
                    "from_state": run.state,
                    "to_state": RunState.SOURCE_INSPECTED.value,
                }, revision=run.revision + 1)
            run.source_display_name = inspection.source_name
            run.source_type = inspection.source_type.value
            run.source_size_bytes = inspection.file_size_bytes
            run.source_sha256 = inspection.file_sha256
            run.selected_sheet = inspection.selected_sheet
            run.header_row = inspection.header_row
            run.source_header_signature = inspection.source_header_signature
            run.source_signature_version = inspection.source_signature_version
            run.state = RunState.SOURCE_INSPECTED.value
            self._advance(run)
            self._audit(run, "source_inspected", {
                "source_type": inspection.source_type.value,
                "source_size_bytes": inspection.file_size_bytes,
                "source_sha256": inspection.file_sha256,
                "source_header_signature": inspection.source_header_signature,
                "selected_sheet": inspection.selected_sheet,
                "header_row": inspection.header_row,
                "to_state": run.state,
            })
            return self._mutation(run)
        return self._atomic(operation)

    def persist_mapping(
        self, *, run_id: str, expected_revision: int, pack: LoadedRegPack,
        inspection: SourceFileInspection, mapping: ImportMapping,
        save_profile: bool = False, base_profile_id: str | None = None,
        profile_display_name: str | None = None,
        recommendation_origins: dict[str, str] | None = None,
    ) -> tuple[MutationMetadata, MappingProfileVersion | None]:
        def operation():
            run = self._locked_run(run_id, expected_revision, pack)
            self._require_source(run, inspection)
            if run.state not in {
                RunState.SOURCE_INSPECTED.value, RunState.MAPPING_CONFIRMED.value,
                RunState.PREFLIGHT_READY.value, RunState.PREFLIGHT_BLOCKED.value,
                RunState.OUTPUT_GENERATED.value,
            }:
                raise InvalidRunTransitionError()
            definition = mapping.model_dump(mode="json")
            changed = run.mapping_fingerprint not in {None, mapping.fingerprint}
            if changed:
                self._invalidate_preflight_and_output(run, "Confirmed mapping changed.")
                self._audit(run, "run_invalidated", {
                    "reason": "mapping_changed", "from_state": run.state,
                    "to_state": RunState.MAPPING_CONFIRMED.value,
                }, revision=run.revision + 1)
            run.canonical_schema_id = str(mapping.target_schema_id)
            run.canonical_schema_version = mapping.target_schema_version
            run.mapping_fingerprint = mapping.fingerprint
            run.mapping_definition = definition
            run.mapping_confirmed_at = utc_now()
            run.state = RunState.MAPPING_CONFIRMED.value
            profile = None
            if save_profile:
                profile = self._save_profile(
                    run=run, pack=pack, display_name=profile_display_name,
                    base_profile_id=base_profile_id,
                    recommendation_origins=recommendation_origins or {},
                )
                run.mapping_profile_id = profile.profile_id
                run.mapping_profile_version = profile.profile_version
            self._advance(run)
            self._audit(run, "mapping_confirmed", {
                "mapping_fingerprint": mapping.fingerprint,
                "canonical_schema_id": str(mapping.target_schema_id),
                "canonical_schema_version": mapping.target_schema_version,
                "profile_id": run.mapping_profile_id,
                "profile_version": run.mapping_profile_version,
                "to_state": run.state,
            })
            return self._mutation(run), profile
        return self._atomic(operation)

    def persist_preflight(
        self, *, run_id: str, expected_revision: int, pack: LoadedRegPack,
        inspection: SourceFileInspection, mapping: ImportMapping,
        result: RegFlowPreflightResult,
    ) -> MutationMetadata:
        if not result.success or result.dataset_fingerprint is None:
            raise InvalidRunTransitionError(
                "Only a successfully computed preflight can be persisted."
            )
        if result.validation is None or result.reconciliation is None:
            raise InvalidRunTransitionError()

        def operation():
            run = self._locked_run(run_id, expected_revision, pack)
            self._require_source(run, inspection)
            if run.mapping_fingerprint != mapping.fingerprint:
                raise MappingProfileStaleError(
                    "The computed mapping does not match the confirmed run mapping."
                )
            if run.state not in {
                RunState.MAPPING_CONFIRMED.value, RunState.PREFLIGHT_READY.value,
                RunState.PREFLIGHT_BLOCKED.value, RunState.OUTPUT_GENERATED.value,
            }:
                raise InvalidRunTransitionError()
            self.repository.invalidate_snapshots(run.id)
            next_revision = run.revision + 1
            skipped = result.validation.skipped_checks + result.reconciliation.skipped_checks
            snapshot = self.repository.add(PreflightSnapshotRecord(
                organisation_id=self.organisation_id,
                run_id=run.id, run_revision=next_revision,
                pack_fingerprint=run.pack_fingerprint,
                source_sha256=inspection.file_sha256,
                source_header_signature=inspection.source_header_signature,
                mapping_fingerprint=mapping.fingerprint,
                dataset_fingerprint=result.dataset_fingerprint,
                validation_report_fingerprint=result.validation.report_fingerprint,
                reconciliation_report_fingerprint=result.reconciliation.report_fingerprint,
                blocking_count=result.blocking_findings,
                review_count=result.review_findings,
                passed_count=result.passed_checks,
                skipped_count=skipped,
                ready=result.ready,
                can_generate=result.can_generate,
            ))
            self.repository.flush()
            run.dataset_fingerprint = result.dataset_fingerprint
            run.validation_report_fingerprint = result.validation.report_fingerprint
            run.reconciliation_report_fingerprint = result.reconciliation.report_fingerprint
            run.latest_blocking_count = result.blocking_findings
            run.latest_review_count = result.review_findings
            run.latest_passed_count = result.passed_checks
            run.latest_skipped_count = skipped
            run.preflight_ready = result.ready
            run.can_generate = result.can_generate
            run.latest_preflight_snapshot_id = snapshot.id
            run.state = (
                RunState.PREFLIGHT_READY.value if result.ready
                else RunState.PREFLIGHT_BLOCKED.value
            )
            self._advance(run)
            self._audit(run, "preflight_completed", {
                "snapshot_id": snapshot.id,
                "dataset_fingerprint": result.dataset_fingerprint,
                "validation_report_fingerprint": result.validation.report_fingerprint,
                "reconciliation_report_fingerprint": result.reconciliation.report_fingerprint,
                "blocking_count": result.blocking_findings,
                "review_count": result.review_findings,
                "passed_count": result.passed_checks,
                "skipped_count": skipped,
                "ready": result.ready,
                "can_generate": result.can_generate,
                "to_state": run.state,
            })
            return self._mutation(run)
        return self._atomic(operation)

    def persist_generation(
        self, *, run_id: str, expected_revision: int, pack: LoadedRegPack,
        inspection: SourceFileInspection, mapping: ImportMapping,
        artifact: GeneratedArtifact, idempotency_key: str | None,
    ) -> tuple[MutationMetadata, ArtifactSummary, bool]:
        key = self._check_key(idempotency_key)
        logical_fp = logical_generation_fingerprint(
            pack_fingerprint=artifact.pack_fingerprint,
            dataset_fingerprint=artifact.dataset_fingerprint,
            mapping_fingerprint=mapping.fingerprint,
            output_definition_id=artifact.output_definition_id,
            output_definition_version=artifact.output_definition_version,
        )
        request_fp = canonical_fingerprint({
            "run_id": run_id,
            "source_sha256": inspection.file_sha256,
            "logical_generation_fingerprint": logical_fp,
        })

        def operation():
            existing = self.repository.idempotency(GENERATE_OPERATION, key)
            if existing is not None:
                if existing.request_fingerprint != request_fp:
                    raise IdempotencyKeyReuseError()
                run = self._run_for_pack(run_id, pack, lock=True)
                stored = self.repository.artifact(existing.resource_id)
                if stored is None:
                    raise InvalidRunTransitionError()
                return self._mutation(run), self._artifact(stored), True
            run = self._locked_run(run_id, expected_revision, pack)
            self._require_source(run, inspection)
            if run.state not in {RunState.PREFLIGHT_READY.value, RunState.OUTPUT_GENERATED.value}:
                raise InvalidRunTransitionError(
                    "The run requires a current ready preflight before generation."
                )
            if run.mapping_fingerprint != mapping.fingerprint:
                raise MappingProfileStaleError()
            if run.dataset_fingerprint != artifact.dataset_fingerprint:
                raise InvalidRunTransitionError(
                    "The regenerated dataset does not match the current preflight."
                )
            self.repository.invalidate_artifacts(run.id)
            next_revision = run.revision + 1
            stored = self.repository.add(ArtifactMetadataRecord(
                organisation_id=self.organisation_id,
                run_id=run.id, run_revision=next_revision,
                filename=artifact.filename, media_type=artifact.media_type,
                size_bytes=artifact.size_bytes, byte_sha256=artifact.sha256,
                pack_id=artifact.pack_id, pack_version=artifact.pack_version,
                pack_fingerprint=artifact.pack_fingerprint,
                dataset_fingerprint=artifact.dataset_fingerprint,
                mapping_fingerprint=mapping.fingerprint,
                output_definition_id=artifact.output_definition_id,
                output_definition_version=artifact.output_definition_version,
                logical_generation_fingerprint=logical_fp,
                retained_bytes=False, storage_reference=None,
            ))
            self.repository.flush()
            run.latest_artifact_id = stored.id
            run.state = RunState.OUTPUT_GENERATED.value
            self._advance(run)
            safe = {
                "artifact_id": stored.id,
                "logical_generation_fingerprint": logical_fp,
                "dataset_fingerprint": artifact.dataset_fingerprint,
                "size_bytes": artifact.size_bytes,
                "to_state": run.state,
            }
            self._audit(run, "generation_requested", {
                "logical_generation_fingerprint": logical_fp
            })
            self._audit(run, "output_generated", safe)
            self.repository.add(IdempotencyRecord(
                organisation_id=self.organisation_id,
                key=key, operation=GENERATE_OPERATION,
                request_fingerprint=request_fp, resource_id=stored.id, run_id=run.id,
            ))
            return self._mutation(run), self._artifact(stored), False
        return self._atomic(operation)

    def persist_workflow_preflight(
        self,
        *,
        run_id: str,
        expected_revision: int,
        pack: LoadedRegPack,
        mapping: WorkflowImportMapping,
        result: RegFlowWorkflowPreflightResult,
        save_profiles: bool = False,
        recommendation_origins: dict[str, dict[str, str]] | None = None,
    ) -> tuple[MutationMetadata, dict[str, MappingProfileVersion]]:
        if (
            not result.success
            or result.bundle_fingerprint is None
            or result.validation_fingerprint is None
            or result.reconciliation_fingerprint is None
            or pack.workflow_definition is None
        ):
            raise InvalidRunTransitionError(
                "Only a successfully computed workflow preflight can be persisted."
            )
        recommendation_origins = recommendation_origins or {}

        def operation():
            run = self._locked_run(run_id, expected_revision, pack)
            mappings = {item.section_id: item.mapping for item in mapping.sections}
            definitions = {item.id: item for item in pack.sections}
            section_metadata: list[dict[str, Any]] = []
            profiles: dict[str, MappingProfileVersion] = {}
            active_sources = [item.source_summary for item in result.sections if item.source_summary]
            if not active_sources:
                raise InvalidRunTransitionError("The workflow has no inspected source section.")
            source = active_sources[0]
            aggregate_signature = canonical_fingerprint({
                item.section_id: (
                    item.source_summary.source_header_signature
                    if item.source_summary is not None
                    else "omitted"
                )
                for item in result.sections
            })
            now = utc_now()
            for item in result.sections:
                section_mapping = mappings[item.section_id]
                definition = definitions[item.section_id]
                profile = None
                origins = recommendation_origins.get(item.section_id, {})
                if save_profiles and section_mapping is not None and item.source_summary is not None:
                    profile = self._save_section_profile(
                        run=run,
                        pack=pack,
                        section_id=item.section_id,
                        schema_id=str(definition.canonical_schema.id),
                        schema_version=definition.canonical_schema.version,
                        source_signature=item.source_summary.source_header_signature,
                        source_signature_version=item.source_summary.source_signature_version,
                        mapping=section_mapping,
                        display_name=f"{pack.name} - {definition.name}",
                        recommendation_origins=origins,
                    )
                    profiles[item.section_id] = profile
                section_metadata.append({
                    "section_id": item.section_id,
                    "omitted": item.omitted,
                    "source": (
                        {
                            "display_name": item.source_summary.source_name,
                            "source_type": item.source_summary.source_type.value,
                            "size_bytes": item.source_summary.file_size_bytes,
                            "sha256": item.source_summary.file_sha256,
                            "selected_sheet": item.source_summary.selected_sheet,
                            "header_signature": item.source_summary.source_header_signature,
                            "signature_version": item.source_summary.source_signature_version,
                        }
                        if item.source_summary is not None else None
                    ),
                    "mapping": {
                        "canonical_schema_id": str(definition.canonical_schema.id),
                        "canonical_schema_version": definition.canonical_schema.version,
                        "fingerprint": item.mapping_fingerprint,
                        "definition": (
                            section_mapping.model_dump(mode="json")
                            if section_mapping is not None else None
                        ),
                        "confirmed_at": now.isoformat(),
                        "profile_id": profile.profile_id if profile else None,
                        "profile_version": profile.profile_version if profile else None,
                    },
                    "dataset": {
                        "fingerprint": item.dataset_fingerprint,
                        "record_count": item.dataset_summary.record_count,
                    },
                    "preflight": {
                        "validation_report_fingerprint": (
                            item.validation.report_fingerprint if item.validation else None
                        ),
                        "reconciliation_status": item.reconciliation_status,
                        "reconciliation_report_fingerprint": (
                            item.reconciliation.report_fingerprint if item.reconciliation else None
                        ),
                        "blocking_count": (
                            item.validation.blocking_findings if item.validation else 0
                        ) + (
                            item.reconciliation.blocking_findings if item.reconciliation else 0
                        ),
                        "review_count": (
                            item.validation.review_findings if item.validation else 0
                        ) + (
                            item.reconciliation.review_findings if item.reconciliation else 0
                        ),
                        "ready": item.ready,
                    },
                })
            self.repository.invalidate_snapshots(run.id)
            next_revision = run.revision + 1
            snapshot = self.repository.add(PreflightSnapshotRecord(
                organisation_id=self.organisation_id,
                run_id=run.id,
                run_revision=next_revision,
                pack_fingerprint=run.pack_fingerprint,
                source_sha256=source.file_sha256,
                source_header_signature=aggregate_signature,
                mapping_fingerprint=mapping.fingerprint,
                dataset_fingerprint=result.bundle_fingerprint,
                validation_report_fingerprint=result.validation_fingerprint,
                reconciliation_report_fingerprint=result.reconciliation_fingerprint,
                blocking_count=result.blocking_findings,
                review_count=result.review_findings,
                passed_count=result.passed_checks,
                skipped_count=0,
                ready=result.ready,
                can_generate=result.can_generate,
                section_summaries=section_metadata,
            ))
            self.repository.flush()
            run.source_display_name = source.source_name
            run.source_type = source.source_type.value
            run.source_size_bytes = source.file_size_bytes
            run.source_sha256 = source.file_sha256
            run.selected_sheet = None
            run.header_row = None
            run.source_header_signature = aggregate_signature
            run.source_signature_version = "workflow-sections-v1"
            run.canonical_schema_id = pack.workflow_definition.id
            run.canonical_schema_version = pack.workflow_definition.version
            run.mapping_fingerprint = mapping.fingerprint
            run.mapping_definition = mapping.model_dump(mode="json")
            run.mapping_confirmed_at = now
            run.mapping_profile_id = None
            run.mapping_profile_version = None
            run.workflow_sections = section_metadata
            run.dataset_fingerprint = result.bundle_fingerprint
            run.validation_report_fingerprint = result.validation_fingerprint
            run.reconciliation_report_fingerprint = result.reconciliation_fingerprint
            run.latest_blocking_count = result.blocking_findings
            run.latest_review_count = result.review_findings
            run.latest_passed_count = result.passed_checks
            run.latest_skipped_count = 0
            run.preflight_ready = result.ready
            run.can_generate = result.can_generate
            run.latest_preflight_snapshot_id = snapshot.id
            run.state = (
                RunState.PREFLIGHT_READY.value if result.ready
                else RunState.PREFLIGHT_BLOCKED.value
            )
            self._advance(run)
            self._audit(run, "workflow_preflight_completed", {
                "snapshot_id": snapshot.id,
                "sections": len(section_metadata),
                "dataset_fingerprint": result.bundle_fingerprint,
                "blocking_count": result.blocking_findings,
                "review_count": result.review_findings,
                "ready": result.ready,
                "profiles_saved": len(profiles),
                "to_state": run.state,
            })
            return self._mutation(run), profiles

        return self._atomic(operation)

    def persist_workflow_generation(
        self,
        *,
        run_id: str,
        expected_revision: int,
        pack: LoadedRegPack,
        mapping: WorkflowImportMapping,
        source_sha256: str,
        artifact: GeneratedArtifact,
        idempotency_key: str | None,
    ) -> tuple[MutationMetadata, ArtifactSummary, bool]:
        key = self._check_key(idempotency_key)
        logical_fp = logical_generation_fingerprint(
            pack_fingerprint=artifact.pack_fingerprint,
            dataset_fingerprint=artifact.dataset_fingerprint,
            mapping_fingerprint=mapping.fingerprint,
            output_definition_id=artifact.output_definition_id,
            output_definition_version=artifact.output_definition_version,
        )
        request_fp = canonical_fingerprint({
            "run_id": run_id,
            "source_sha256": source_sha256,
            "logical_generation_fingerprint": logical_fp,
        })

        def operation():
            existing = self.repository.idempotency(GENERATE_OPERATION, key)
            if existing is not None:
                if existing.request_fingerprint != request_fp:
                    raise IdempotencyKeyReuseError()
                run = self._run_for_pack(run_id, pack, lock=True)
                stored = self.repository.artifact(existing.resource_id)
                if stored is None:
                    raise InvalidRunTransitionError()
                return self._mutation(run), self._artifact(stored), True
            run = self._locked_run(run_id, expected_revision, pack)
            if run.state not in {RunState.PREFLIGHT_READY.value, RunState.OUTPUT_GENERATED.value}:
                raise InvalidRunTransitionError(
                    "The workflow run requires a current ready preflight before generation."
                )
            if run.source_sha256 != source_sha256 or run.mapping_fingerprint != mapping.fingerprint:
                raise MappingProfileStaleError()
            if run.dataset_fingerprint != artifact.dataset_fingerprint:
                raise InvalidRunTransitionError(
                    "The regenerated workflow dataset does not match the current preflight."
                )
            self.repository.invalidate_artifacts(run.id)
            stored = self.repository.add(ArtifactMetadataRecord(
                organisation_id=self.organisation_id,
                run_id=run.id,
                run_revision=run.revision + 1,
                filename=artifact.filename,
                media_type=artifact.media_type,
                size_bytes=artifact.size_bytes,
                byte_sha256=artifact.sha256,
                pack_id=artifact.pack_id,
                pack_version=artifact.pack_version,
                pack_fingerprint=artifact.pack_fingerprint,
                dataset_fingerprint=artifact.dataset_fingerprint,
                mapping_fingerprint=mapping.fingerprint,
                output_definition_id=artifact.output_definition_id,
                output_definition_version=artifact.output_definition_version,
                logical_generation_fingerprint=logical_fp,
                retained_bytes=False,
                storage_reference=None,
            ))
            self.repository.flush()
            run.latest_artifact_id = stored.id
            run.state = RunState.OUTPUT_GENERATED.value
            self._advance(run)
            self._audit(run, "workflow_output_generated", {
                "artifact_id": stored.id,
                "logical_generation_fingerprint": logical_fp,
                "dataset_fingerprint": artifact.dataset_fingerprint,
                "size_bytes": artifact.size_bytes,
                "to_state": run.state,
            })
            self.repository.add(IdempotencyRecord(
                organisation_id=self.organisation_id,
                key=key,
                operation=GENERATE_OPERATION,
                request_fingerprint=request_fp,
                resource_id=stored.id,
                run_id=run.id,
            ))
            return self._mutation(run), self._artifact(stored), False

        return self._atomic(operation)

    def _save_section_profile(
        self,
        *,
        run: RegFlowRunRecord,
        pack: LoadedRegPack,
        section_id: str,
        schema_id: str,
        schema_version: str,
        source_signature: str,
        source_signature_version: str,
        mapping: ImportMapping,
        display_name: str,
        recommendation_origins: dict[str, str],
    ) -> MappingProfileVersion:
        allowed = {str(field.target_field_id) for field in mapping.fields}
        if (
            any(key not in allowed for key in recommendation_origins)
            or any(value not in {"exact", "alias", "manual"} for value in recommendation_origins.values())
        ):
            raise InvalidRunTransitionError("Section recommendation origins are invalid.")
        compatible = self.repository.matching_profiles(
            pack_id=run.pack_id,
            pack_version=run.pack_version,
            pack_fingerprint=run.pack_fingerprint,
            schema_id=schema_id,
            schema_version=schema_version,
            source_signature=source_signature,
            section_id=section_id,
        )
        duplicate = next(
            (item for item in compatible if item.mapping_fingerprint == mapping.fingerprint),
            None,
        )
        if duplicate is not None:
            return self._profile_version(duplicate)
        profile = self.repository.add(MappingProfileRecord(organisation_id=self.organisation_id))
        self.repository.flush()
        record = self.repository.add(MappingProfileVersionRecord(
            organisation_id=self.organisation_id,
            profile_id=profile.id,
            profile_version=1,
            display_name=display_name,
            pack_id=run.pack_id,
            pack_version=run.pack_version,
            pack_fingerprint=run.pack_fingerprint,
            section_id=section_id,
            canonical_schema_id=schema_id,
            canonical_schema_version=schema_version,
            source_header_signature=source_signature,
            source_signature_version=source_signature_version,
            mapping_fingerprint=mapping.fingerprint,
            mapping_definition=mapping.model_dump(mode="json"),
            recommendation_origins=recommendation_origins,
        ))
        self.repository.flush()
        profile.updated_at = record.created_at
        return self._profile_version(record)

    def save_profile_from_run(
        self, *, run_id: str, display_name: str | None,
        base_profile_id: str | None, recommendation_origins: dict[str, str],
        pack_resolver: Callable[[str, str], LoadedRegPack],
    ) -> MappingProfileVersion:
        def operation():
            run = self.repository.get_run(run_id, lock=True)
            if run is None:
                raise RunNotFoundError()
            pack = pack_resolver(run.pack_id, run.pack_version)
            if pack.fingerprint != run.pack_fingerprint:
                raise RegPackIntegrityError()
            if run.mapping_definition is None or run.mapping_fingerprint is None:
                raise InvalidRunTransitionError("The run has no confirmed mapping.")
            return self._save_profile(
                run=run, pack=pack, display_name=display_name,
                base_profile_id=base_profile_id,
                recommendation_origins=recommendation_origins,
            )
        return self._atomic(operation)

    def list_profiles(self) -> MappingProfileList:
        summaries = []
        for profile in self.repository.list_profiles():
            if not profile.versions:
                continue
            latest = max(profile.versions, key=lambda version: version.profile_version)
            summaries.append(self._profile_summary(profile, latest))
        return MappingProfileList(profiles=tuple(summaries))

    def get_profile(self, profile_id: str) -> MappingProfileDetail:
        profile = self.repository.profile(profile_id)
        if profile is None:
            raise MappingProfileNotFoundError()
        return MappingProfileDetail(
            profile_id=profile.id, created_at=profile.created_at,
            updated_at=profile.updated_at,
            versions=tuple(self._profile_version(row) for row in profile.versions),
        )

    def match_profiles(
        self, *, pack: LoadedRegPack, schema_id: str, schema_version: str,
        source_signature: str,
        section_id: str | None = None,
    ) -> MappingProfileMatch:
        if pack.fingerprint is None:
            raise RegPackIntegrityError()
        rows = self.repository.matching_profiles(
            pack_id=pack.id, pack_version=pack.version,
            pack_fingerprint=pack.fingerprint,
            schema_id=schema_id, schema_version=schema_version,
            source_signature=source_signature,
            section_id=section_id,
        )
        return MappingProfileMatch(profiles=tuple(self._profile_version(row) for row in rows))

    def delete_profile(self, profile_id: str) -> None:
        def operation():
            profile = self.repository.profile(profile_id)
            if profile is None:
                raise MappingProfileNotFoundError()
            self.session.delete(profile)
        self._atomic(operation)

    def _save_profile(
        self, *, run: RegFlowRunRecord, pack: LoadedRegPack,
        display_name: str | None, base_profile_id: str | None,
        recommendation_origins: dict[str, str],
    ) -> MappingProfileVersion:
        if (
            run.mapping_definition is None or run.mapping_fingerprint is None
            or run.source_header_signature is None or run.source_signature_version is None
            or run.canonical_schema_id is None or run.canonical_schema_version is None
        ):
            raise InvalidRunTransitionError("The run has no verified reusable mapping.")
        validated = ImportMapping.model_validate_json(
            json.dumps(run.mapping_definition, separators=(",", ":"))
        )
        if validated.fingerprint != run.mapping_fingerprint:
            raise MappingProfileStaleError("The run mapping fingerprint is inconsistent.")
        if pack.canonical_schema is None or (
            str(pack.canonical_schema.id) != run.canonical_schema_id
            or pack.canonical_schema.version != run.canonical_schema_version
        ):
            raise MappingProfileStaleError()
        profile = None
        if base_profile_id:
            profile = self.repository.profile(base_profile_id)
            if profile is None:
                raise MappingProfileNotFoundError()
            for version in profile.versions:
                if version.mapping_fingerprint == run.mapping_fingerprint:
                    return self._profile_version(version)
        else:
            compatible = self.repository.matching_profiles(
                pack_id=run.pack_id, pack_version=run.pack_version,
                pack_fingerprint=run.pack_fingerprint,
                schema_id=run.canonical_schema_id,
                schema_version=run.canonical_schema_version,
                source_signature=run.source_header_signature,
            )
            duplicate = next(
                (version for version in compatible
                 if version.mapping_fingerprint == run.mapping_fingerprint),
                None,
            )
            if duplicate is not None:
                return self._profile_version(duplicate)
        if profile is None:
            profile = self.repository.add(MappingProfileRecord(organisation_id=self.organisation_id))
            self.repository.flush()
        latest_version = max((row.profile_version for row in profile.versions), default=0)
        record = self.repository.add(MappingProfileVersionRecord(
            organisation_id=self.organisation_id,
            profile_id=profile.id, profile_version=latest_version + 1,
            display_name=display_name, pack_id=run.pack_id,
            pack_version=run.pack_version, pack_fingerprint=run.pack_fingerprint,
            canonical_schema_id=run.canonical_schema_id,
            canonical_schema_version=run.canonical_schema_version,
            source_header_signature=run.source_header_signature,
            source_signature_version=run.source_signature_version,
            mapping_fingerprint=run.mapping_fingerprint,
            mapping_definition=run.mapping_definition,
            recommendation_origins=recommendation_origins,
        ))
        profile.updated_at = utc_now()
        self.repository.flush()
        return self._profile_version(record)

    def _locked_run(
        self, run_id: str, expected_revision: int, pack: LoadedRegPack
    ) -> RegFlowRunRecord:
        run = self._run_for_pack(run_id, pack, lock=True)
        if run.revision != expected_revision:
            raise RunRevisionConflictError(metadata={
                "run_id": run.id, "expected_revision": expected_revision,
                "current_revision": run.revision, "current_state": run.state,
            })
        return run

    def _run_for_pack(
        self, run_id: str, pack: LoadedRegPack, *, lock: bool
    ) -> RegFlowRunRecord:
        run = self.repository.get_run(run_id, lock=lock)
        if run is None:
            raise RunNotFoundError()
        if (
            pack.fingerprint is None or run.pack_id != pack.id
            or run.pack_version != pack.version
            or run.pack_fingerprint != pack.fingerprint
        ):
            raise RegPackIntegrityError()
        return run

    @staticmethod
    def _require_source(run: RegFlowRunRecord, inspection: SourceFileInspection) -> None:
        if (
            run.source_sha256 != inspection.file_sha256
            or run.selected_sheet != inspection.selected_sheet
            or run.header_row != inspection.header_row
            or run.source_header_signature != inspection.source_header_signature
        ):
            raise InvalidRunTransitionError(
                "The uploaded source does not match the run's current inspection."
            )

    def _invalidate_downstream(self, run: RegFlowRunRecord, reason: str) -> None:
        run.mapping_fingerprint = None
        run.mapping_definition = None
        run.mapping_confirmed_at = None
        run.mapping_profile_id = None
        run.mapping_profile_version = None
        self._invalidate_preflight_and_output(run, reason)

    def _invalidate_preflight_and_output(self, run: RegFlowRunRecord, reason: str) -> None:
        self.repository.invalidate_snapshots(run.id)
        self.repository.invalidate_artifacts(run.id)
        run.dataset_fingerprint = None
        run.validation_report_fingerprint = None
        run.reconciliation_report_fingerprint = None
        run.latest_blocking_count = 0
        run.latest_review_count = 0
        run.latest_passed_count = 0
        run.latest_skipped_count = 0
        run.preflight_ready = False
        run.can_generate = False
        run.latest_preflight_snapshot_id = None
        run.latest_artifact_id = None
        run.invalidation_reason = reason

    @staticmethod
    def _advance(run: RegFlowRunRecord) -> None:
        run.revision += 1
        run.updated_at = utc_now()

    def _audit(
        self, run: RegFlowRunRecord, event_type: str,
        metadata: dict[str, Any], *, revision: int | None = None,
    ) -> None:
        self.repository.add(AuditEventRecord(
            organisation_id=self.organisation_id,
            run_id=run.id, event_type=event_type,
            run_revision=revision if revision is not None else run.revision,
            metadata_json={**metadata, **({"request_id": self.request_id} if self.request_id else {})},
        ))
        logger.info(
            "regflow_lifecycle",
            extra={
                "event": "regflow_lifecycle",
                "lifecycle_event": event_type,
                "organisation_id": self.organisation_id,
                "run_id": run.id,
                "artifact_id": metadata.get("artifact_id"),
                "run_revision": revision if revision is not None else run.revision,
            },
        )

    @staticmethod
    def _mutation(run: RegFlowRunRecord) -> MutationMetadata:
        return MutationMetadata(
            run_id=run.id, run_state=RunState(run.state), run_revision=run.revision
        )

    @staticmethod
    def _pack(run: RegFlowRunRecord) -> RunPack:
        return RunPack(id=run.pack_id, version=run.pack_version, fingerprint=run.pack_fingerprint)

    def _summary(self, run: RegFlowRunRecord) -> RunSummary:
        return RunSummary(
            id=run.id, state=RunState(run.state), revision=run.revision,
            created_at=run.created_at, updated_at=run.updated_at,
            pack=self._pack(run), source_display_name=run.source_display_name,
            blocking_count=run.latest_blocking_count,
            review_count=run.latest_review_count,
            preflight_ready=run.preflight_ready,
            output_generated=run.latest_artifact_id is not None,
        )

    def _detail(self, run: RegFlowRunRecord) -> RunDetail:
        artifact = next(
            (item for item in getattr(run, "artifacts", []) if item.id == run.latest_artifact_id),
            None,
        )
        events = sorted(getattr(run, "audit_events", []), key=lambda item: item.occurred_at)
        return RunDetail(
            id=run.id, state=RunState(run.state), revision=run.revision,
            created_at=run.created_at, updated_at=run.updated_at, pack=self._pack(run),
            source=RunSource(
                display_name=run.source_display_name, source_type=run.source_type,
                size_bytes=run.source_size_bytes, sha256=run.source_sha256,
                selected_sheet=run.selected_sheet, header_row=run.header_row,
                header_signature=run.source_header_signature,
                signature_version=run.source_signature_version,
            ),
            mapping=RunMapping(
                canonical_schema_id=run.canonical_schema_id,
                canonical_schema_version=run.canonical_schema_version,
                fingerprint=run.mapping_fingerprint, definition=run.mapping_definition,
                confirmed_at=run.mapping_confirmed_at,
                profile_id=run.mapping_profile_id,
                profile_version=run.mapping_profile_version,
            ),
            preflight=PreflightSummary(
                snapshot_id=run.latest_preflight_snapshot_id,
                dataset_fingerprint=run.dataset_fingerprint,
                validation_report_fingerprint=run.validation_report_fingerprint,
                reconciliation_report_fingerprint=run.reconciliation_report_fingerprint,
                blocking_count=run.latest_blocking_count,
                review_count=run.latest_review_count,
                passed_count=run.latest_passed_count,
                skipped_count=run.latest_skipped_count,
                ready=run.preflight_ready, can_generate=run.can_generate,
            ),
            artifact=self._artifact(artifact) if artifact else None,
            invalidation_reason=run.invalidation_reason,
            audit_events=tuple(AuditEvent(
                id=event.id, event_type=event.event_type,
                run_revision=event.run_revision, occurred_at=event.occurred_at,
                metadata=event.metadata_json,
            ) for event in events),
            workflow_sections=tuple(run.workflow_sections or ()),
        )

    @staticmethod
    def _artifact(record: ArtifactMetadataRecord) -> ArtifactSummary:
        return ArtifactSummary(
            id=record.id, created_at=record.created_at, filename=record.filename,
            media_type=record.media_type, size_bytes=record.size_bytes,
            byte_sha256=record.byte_sha256,
            logical_generation_fingerprint=record.logical_generation_fingerprint,
            retained_bytes=False, storage_reference=None,
        )

    def _profile_summary(
        self, profile: MappingProfileRecord, latest: MappingProfileVersionRecord
    ) -> MappingProfileSummary:
        return MappingProfileSummary(
            profile_id=profile.id, display_name=latest.display_name,
            latest_version=latest.profile_version,
            pack=RunPack(id=latest.pack_id, version=latest.pack_version, fingerprint=latest.pack_fingerprint),
            canonical_schema_id=latest.canonical_schema_id,
            canonical_schema_version=latest.canonical_schema_version,
            source_header_signature=latest.source_header_signature,
            created_at=profile.created_at, updated_at=profile.updated_at,
            section_id=latest.section_id,
        )

    @staticmethod
    def _profile_version(record: MappingProfileVersionRecord) -> MappingProfileVersion:
        return MappingProfileVersion(
            profile_id=record.profile_id, profile_version=record.profile_version,
            created_at=record.created_at, confirmed_at=record.confirmed_at,
            display_name=record.display_name,
            pack=RunPack(id=record.pack_id, version=record.pack_version, fingerprint=record.pack_fingerprint),
            canonical_schema_id=record.canonical_schema_id,
            canonical_schema_version=record.canonical_schema_version,
            source_header_signature=record.source_header_signature,
            source_signature_version=record.source_signature_version,
            mapping_fingerprint=record.mapping_fingerprint,
            mapping_definition=record.mapping_definition,
            recommendation_origins=record.recommendation_origins,
            section_id=record.section_id,
        )
