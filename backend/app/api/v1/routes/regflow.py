from typing import Annotated
import json

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import (
    get_import_service,
    get_optional_persistence_service,
    get_regflow_preflight_service,
    get_regpack_registry,
)
from app.api.v1.routes.imports import read_bounded_upload, resolve_workflow_pack
from app.imports.errors import ImportRequestError
from app.imports.models import ImportIssueCode, ImportMapping, WorkflowImportMapping
from app.imports.service import ImportService
from app.persistence.service import PersistenceService
from app.regflow.models import RegFlowPreflightResult, RegFlowWorkflowPreflightResult
from app.regflow.service import RegFlowPreflightService
from app.regpacks.registry import RegPackRegistry

router = APIRouter(prefix="/regflow", tags=["regflow"])
Imports = Annotated[ImportService, Depends(get_import_service)]
Preflight = Annotated[RegFlowPreflightService, Depends(get_regflow_preflight_service)]
Registry = Annotated[RegPackRegistry, Depends(get_regpack_registry)]
Persistence = Annotated[PersistenceService | None, Depends(get_optional_persistence_service)]


@router.post("/preflight", response_model=RegFlowPreflightResult)
async def run_preflight(
    imports: Imports,
    service: Preflight,
    registry: Registry,
    persistence: Persistence,
    file: Annotated[UploadFile, File()],
    pack_id: Annotated[str, Form()],
    pack_version: Annotated[str, Form()],
    mapping: Annotated[str, Form()],
    run_id: Annotated[str | None, Form()] = None,
    expected_revision: Annotated[int | None, Form()] = None,
) -> RegFlowPreflightResult:
    imports.enforce_payload_size(mapping)
    try:
        definition = ImportMapping.model_validate_json(mapping)
    except ValidationError as exc:
        raise ImportRequestError(
            ImportIssueCode.INVALID_MAPPING,
            "The import mapping is invalid.",
            422,
        ) from exc
    pack = resolve_workflow_pack(
        registry, pack_id, pack_version, persistent=run_id is not None
    )
    if pack.canonical_schema is None:
        raise ImportRequestError(
            ImportIssueCode.INCOMPATIBLE_CONVERSION,
            "The selected RegPack does not support canonical preflight.",
            422,
        )
    content = await read_bounded_upload(file, imports)
    result = await run_in_threadpool(
        service.run, pack, file.filename or "upload", content, definition
    )
    if run_id is not None and result.success:
        if persistence is None or expected_revision is None:
            raise ImportRequestError(
                ImportIssueCode.INVALID_MAPPING,
                "Persistent preflight requires a run revision.", 422,
            )
        inspection = await run_in_threadpool(
            imports.inspect,
            file.filename or "upload", content,
            sheet_name=definition.sheet_name, header_row=definition.header_row,
        )
        mutation = persistence.persist_preflight(
            run_id=run_id, expected_revision=expected_revision, pack=pack,
            inspection=inspection, mapping=definition, result=result,
        )
        result = result.model_copy(update={
            "run_id": mutation.run_id, "run_state": mutation.run_state.value,
            "run_revision": mutation.run_revision,
        })
    return result


@router.post("/preflight-sections", response_model=RegFlowWorkflowPreflightResult)
async def run_sectioned_preflight(
    imports: Imports,
    service: Preflight,
    registry: Registry,
    persistence: Persistence,
    file: Annotated[UploadFile, File()],
    pack_id: Annotated[str, Form()],
    pack_version: Annotated[str, Form()],
    mapping: Annotated[str, Form()],
    runtime_values: Annotated[str, Form()],
    run_id: Annotated[str | None, Form()] = None,
    expected_revision: Annotated[int | None, Form()] = None,
    save_mapping_profiles: Annotated[bool, Form()] = False,
    recommendation_origins: Annotated[str | None, Form()] = None,
) -> RegFlowWorkflowPreflightResult:
    imports.enforce_payload_size(mapping, runtime_values, recommendation_origins)
    try:
        definition = WorkflowImportMapping.model_validate_json(mapping)
        runtime = json.loads(runtime_values)
        origins = json.loads(recommendation_origins) if recommendation_origins else {}
        if not isinstance(runtime, dict):
            raise ValueError
        if not isinstance(origins, dict):
            raise ValueError
    except (ValidationError, json.JSONDecodeError, ValueError) as exc:
        raise ImportRequestError(
            ImportIssueCode.INVALID_MAPPING,
            "The sectioned workflow request is invalid.",
            422,
        ) from exc
    pack = resolve_workflow_pack(
        registry, pack_id, pack_version, persistent=run_id is not None
    )
    content = await read_bounded_upload(file, imports)
    result = await run_in_threadpool(
        service.run_workflow,
        pack, file.filename or "upload", content, definition, runtime
    )
    if run_id is not None and result.success:
        if persistence is None or expected_revision is None:
            raise ImportRequestError(
                ImportIssueCode.INVALID_MAPPING,
                "Persistent workflow preflight requires a run revision.",
                422,
            )
        mutation, profiles = persistence.persist_workflow_preflight(
            run_id=run_id,
            expected_revision=expected_revision,
            pack=pack,
            mapping=definition,
            result=result,
            save_profiles=save_mapping_profiles,
            recommendation_origins=origins,
        )
        result = result.model_copy(update={
            "run_id": mutation.run_id,
            "run_state": mutation.run_state.value,
            "run_revision": mutation.run_revision,
        })
    return result
