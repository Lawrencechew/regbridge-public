from typing import Annotated
import json

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import (
    get_import_service, get_optional_persistence_service, get_output_service,
    get_regpack_registry,
)
from app.api.v1.routes.imports import read_bounded_upload, resolve_workflow_pack
from app.imports.errors import ImportRequestError
from app.imports.models import ImportIssueCode, ImportMapping, WorkflowImportMapping
from app.imports.service import ImportService
from app.outputs.errors import OutputRequestError
from app.outputs.models import OutputIssueCode
from app.outputs.service import OutputService
from app.persistence.service import PersistenceService
from app.regpacks.registry import RegPackRegistry

router = APIRouter(prefix="/outputs", tags=["outputs"])
Imports = Annotated[ImportService, Depends(get_import_service)]
Outputs = Annotated[OutputService, Depends(get_output_service)]
Registry = Annotated[RegPackRegistry, Depends(get_regpack_registry)]
Persistence = Annotated[PersistenceService | None, Depends(get_optional_persistence_service)]


class OutputTypesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    output_types: tuple[str, ...]


@router.get("/types", response_model=OutputTypesResponse)
def list_output_types() -> OutputTypesResponse:
    return OutputTypesResponse(output_types=("xlsx_template",))


@router.post("/generate")
async def generate_output(
    request: Request,
    imports: Imports,
    outputs: Outputs,
    registry: Registry,
    persistence: Persistence,
    file: Annotated[UploadFile, File()],
    pack_id: Annotated[str, Form()],
    pack_version: Annotated[str, Form()],
    mapping: Annotated[str, Form()],
    run_id: Annotated[str | None, Form()] = None,
    expected_revision: Annotated[int | None, Form()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Response:
    imports.enforce_payload_size(mapping)
    try:
        definition = ImportMapping.model_validate_json(mapping)
    except ValidationError as exc:
        raise ImportRequestError(
            ImportIssueCode.INVALID_MAPPING,
            "The import mapping is invalid.",
            400,
        ) from exc
    pack = resolve_workflow_pack(
        registry, pack_id, pack_version, persistent=run_id is not None
    )
    if pack.canonical_schema is None:
        raise OutputRequestError(
            OutputIssueCode.OUTPUT_SCHEMA_MISMATCH,
            "The selected RegPack has no canonical schema.",
            422,
        )
    content = await read_bounded_upload(file, imports)
    imported = await run_in_threadpool(
        imports.map, file.filename or "upload", content, definition, pack.canonical_schema
    )
    if not imported.success or imported.dataset is None:
        first = imported.issues[0] if imported.issues else None
        raise ImportRequestError(
            str(first.code if first else ImportIssueCode.INVALID_MAPPING),
            first.message if first else "The source file could not be mapped.",
            422,
        )
    async with request.app.state.generation_limiter.slot():
        generated = await run_in_threadpool(outputs.generate, pack, imported.dataset)
    if not generated.result.success or generated.content is None or generated.result.artifact is None:
        issue = generated.result.issues[0]
        status = 413 if issue.code == OutputIssueCode.OUTPUT_FILE_TOO_LARGE else 422
        raise OutputRequestError(issue.code, issue.message, status)
    artifact = generated.result.artifact
    persistent_headers = {}
    if run_id is not None:
        if persistence is None or expected_revision is None:
            raise ImportRequestError(
                ImportIssueCode.INVALID_MAPPING,
                "Persistent generation requires a run revision.", 422,
            )
        mutation, stored, replayed = persistence.persist_generation(
            run_id=run_id, expected_revision=expected_revision, pack=pack,
            inspection=imported.source, mapping=definition, artifact=artifact,
            idempotency_key=idempotency_key,
        )
        persistent_headers = {
            "X-RegBridge-Run-Id": mutation.run_id,
            "X-RegBridge-Run-State": mutation.run_state.value,
            "X-RegBridge-Run-Revision": str(mutation.run_revision),
            "X-RegBridge-Logical-Artifact-Id": stored.id,
            "X-RegBridge-Logical-Generation-SHA256": stored.logical_generation_fingerprint,
            "X-RegBridge-Idempotent-Replay": str(replayed).lower(),
        }
    return Response(
        content=generated.content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "X-RegBridge-Artifact-Id": artifact.artifact_id,
            "X-RegBridge-Artifact-SHA256": artifact.sha256,
            "X-RegBridge-Pack-Fingerprint": artifact.pack_fingerprint,
            "X-RegBridge-Dataset-Fingerprint": artifact.dataset_fingerprint,
            **persistent_headers,
        },
    )


@router.post("/generate-sections")
async def generate_sectioned_output(
    request: Request,
    imports: Imports,
    outputs: Outputs,
    registry: Registry,
    persistence: Persistence,
    file: Annotated[UploadFile, File()],
    pack_id: Annotated[str, Form()],
    pack_version: Annotated[str, Form()],
    mapping: Annotated[str, Form()],
    runtime_values: Annotated[str, Form()],
    run_id: Annotated[str | None, Form()] = None,
    expected_revision: Annotated[int | None, Form()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Response:
    imports.enforce_payload_size(mapping, runtime_values)
    try:
        definition = WorkflowImportMapping.model_validate_json(mapping)
        runtime = json.loads(runtime_values)
        if not isinstance(runtime, dict):
            raise ValueError
    except (ValidationError, json.JSONDecodeError, ValueError) as exc:
        raise ImportRequestError(
            ImportIssueCode.INVALID_MAPPING,
            "The sectioned output request is invalid.",
            400,
        ) from exc
    pack = resolve_workflow_pack(
        registry, pack_id, pack_version, persistent=run_id is not None
    )
    content = await read_bounded_upload(file, imports)
    imported = await run_in_threadpool(
        imports.map_workflow, file.filename or "upload", content, definition, pack
    )
    if not imported.success:
        first = next(
            (issue for section in imported.sections for issue in section.issues),
            None,
        )
        raise ImportRequestError(
            str(first.code if first else ImportIssueCode.INVALID_MAPPING),
            first.message if first else "The source workbook could not be mapped.",
            422,
        )
    bundle_id = f"workflow-{imported.mapping_fingerprint[:16]}"
    async with request.app.state.generation_limiter.slot():
        generated, _ = await run_in_threadpool(
            outputs.generate_workflow,
            pack, imported.datasets, runtime, bundle_id=bundle_id,
        )
    if not generated.result.success or generated.content is None or generated.result.artifact is None:
        issue = generated.result.issues[0]
        status = 413 if issue.code in {
            OutputIssueCode.OUTPUT_FILE_TOO_LARGE,
            OutputIssueCode.OUTPUT_CAPACITY_EXCEEDED,
        } else 422
        raise OutputRequestError(issue.code, issue.message, status)
    artifact = generated.result.artifact
    persistent_headers = {}
    if run_id is not None:
        if persistence is None or expected_revision is None:
            raise ImportRequestError(
                ImportIssueCode.INVALID_MAPPING,
                "Persistent workflow generation requires a run revision.",
                422,
            )
        first_source = next(
            item.source for item in imported.sections if item.source is not None
        )
        mutation, stored, replayed = persistence.persist_workflow_generation(
            run_id=run_id,
            expected_revision=expected_revision,
            pack=pack,
            mapping=definition,
            source_sha256=first_source.file_sha256,
            artifact=artifact,
            idempotency_key=idempotency_key,
        )
        persistent_headers = {
            "X-RegBridge-Run-Id": mutation.run_id,
            "X-RegBridge-Run-State": mutation.run_state.value,
            "X-RegBridge-Run-Revision": str(mutation.run_revision),
            "X-RegBridge-Logical-Artifact-Id": stored.id,
            "X-RegBridge-Logical-Generation-SHA256": stored.logical_generation_fingerprint,
            "X-RegBridge-Idempotent-Replay": str(replayed).lower(),
        }
    return Response(
        content=generated.content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "X-RegBridge-Artifact-Id": artifact.artifact_id,
            "X-RegBridge-Artifact-SHA256": artifact.sha256,
            "X-RegBridge-Pack-Fingerprint": artifact.pack_fingerprint,
            "X-RegBridge-Dataset-Fingerprint": artifact.dataset_fingerprint,
            **persistent_headers,
        },
    )
