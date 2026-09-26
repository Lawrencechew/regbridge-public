from typing import Annotated

import json

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import (
    get_import_service, get_optional_persistence_service, get_regpack_registry,
)
from app.imports.errors import ImportRequestError
from app.imports.models import (
    ImportIssueCode,
    ImportMapping,
    ImportResult,
    SourceFileInspection,
    WorkflowImportMapping,
    WorkflowImportResult,
)
from app.imports.service import ImportService
from app.persistence.service import PersistenceService
from app.persistence.errors import RegPackIntegrityError
from app.regpacks.errors import RegPackNotFoundError
from app.regpacks.registry import RegPackRegistry

router = APIRouter(prefix="/imports", tags=["imports"])
Service = Annotated[ImportService, Depends(get_import_service)]
Registry = Annotated[RegPackRegistry, Depends(get_regpack_registry)]
Persistence = Annotated[PersistenceService | None, Depends(get_optional_persistence_service)]


def resolve_workflow_pack(
    registry: RegPackRegistry, pack_id: str, pack_version: str, *, persistent: bool
):
    try:
        return registry.get(pack_id, pack_version)
    except RegPackNotFoundError as exc:
        if persistent:
            raise RegPackIntegrityError() from exc
        raise


class ImportFileTypesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    file_types: tuple[str, ...]


class ImportLimitsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    max_file_size_bytes: int
    max_rows: int
    max_columns: int
    max_xlsx_sheets: int
    preview_rows: int
    min_header_row: int = 1
    max_header_row: int = 50


async def read_bounded_upload(file: UploadFile, service: ImportService) -> bytes:
    try:
        content = await file.read(service.max_file_size_bytes + 1)
    finally:
        await file.close()
    if len(content) > service.max_file_size_bytes:
        raise ImportRequestError(
            ImportIssueCode.FILE_TOO_LARGE,
            "The uploaded source file exceeds the configured size limit.",
            413,
        )
    return content


@router.get("/file-types", response_model=ImportFileTypesResponse)
def list_import_file_types() -> ImportFileTypesResponse:
    return ImportFileTypesResponse(file_types=("csv", "xlsx"))


@router.get("/limits", response_model=ImportLimitsResponse)
def read_import_limits(service: Service) -> ImportLimitsResponse:
    limits = service.inspector.limits
    return ImportLimitsResponse(
        max_file_size_bytes=limits.max_file_size_bytes,
        max_rows=limits.max_rows,
        max_columns=limits.max_columns,
        max_xlsx_sheets=limits.max_xlsx_sheets,
        preview_rows=limits.preview_rows,
    )


@router.post("/inspect", response_model=SourceFileInspection)
async def inspect_source_file(
    service: Service,
    registry: Registry,
    persistence: Persistence,
    file: Annotated[UploadFile, File()],
    sheet_name: Annotated[str | None, Form()] = None,
    header_row: Annotated[int, Form()] = 1,
    run_id: Annotated[str | None, Form()] = None,
    expected_revision: Annotated[int | None, Form()] = None,
    pack_id: Annotated[str | None, Form()] = None,
    pack_version: Annotated[str | None, Form()] = None,
) -> SourceFileInspection:
    content = await read_bounded_upload(file, service)
    result = await run_in_threadpool(
        service.inspect,
        file.filename or "upload",
        content,
        sheet_name=sheet_name,
        header_row=header_row,
    )
    if run_id is not None:
        if persistence is None or expected_revision is None or pack_id is None or pack_version is None:
            raise ImportRequestError(
                ImportIssueCode.INVALID_MAPPING,
                "Persistent inspection requires run, revision, and RegPack identity.", 422,
            )
        mutation = persistence.persist_inspection(
            run_id=run_id, expected_revision=expected_revision,
            pack=resolve_workflow_pack(
                registry, pack_id, pack_version, persistent=True
            ), inspection=result,
        )
        result = result.model_copy(update={
            "run_id": mutation.run_id, "run_state": mutation.run_state.value,
            "run_revision": mutation.run_revision,
        })
    return result


@router.post("/map-sections", response_model=WorkflowImportResult)
async def map_sectioned_source_file(
    service: Service,
    registry: Registry,
    file: Annotated[UploadFile, File()],
    pack_id: Annotated[str, Form()],
    pack_version: Annotated[str, Form()],
    mapping: Annotated[str, Form()],
) -> WorkflowImportResult:
    service.enforce_payload_size(mapping)
    try:
        definition = WorkflowImportMapping.model_validate_json(mapping)
    except ValidationError as exc:
        raise ImportRequestError(
            ImportIssueCode.INVALID_MAPPING,
            "The sectioned import mapping is invalid.",
            422,
        ) from exc
    pack = resolve_workflow_pack(registry, pack_id, pack_version, persistent=False)
    content = await read_bounded_upload(file, service)
    return await run_in_threadpool(
        service.map_workflow, file.filename or "upload", content, definition, pack
    )


@router.post("/map", response_model=ImportResult)
async def map_source_file(
    service: Service,
    registry: Registry,
    persistence: Persistence,
    file: Annotated[UploadFile, File()],
    pack_id: Annotated[str, Form()],
    pack_version: Annotated[str, Form()],
    mapping: Annotated[str, Form()],
    run_id: Annotated[str | None, Form()] = None,
    expected_revision: Annotated[int | None, Form()] = None,
    save_mapping_profile: Annotated[bool, Form()] = False,
    base_profile_id: Annotated[str | None, Form()] = None,
    profile_display_name: Annotated[str | None, Form()] = None,
    recommendation_origins: Annotated[str | None, Form()] = None,
) -> ImportResult:
    service.enforce_payload_size(mapping, recommendation_origins)
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
            "The selected RegPack has no canonical schema.",
            422,
        )
    content = await read_bounded_upload(file, service)
    result = await run_in_threadpool(
        service.map, file.filename or "upload", content, definition, pack.canonical_schema
    )
    if run_id is not None and result.success:
        if persistence is None or expected_revision is None:
            raise ImportRequestError(
                ImportIssueCode.INVALID_MAPPING,
                "Persistent mapping requires a run revision.", 422,
            )
        try:
            origins = json.loads(recommendation_origins) if recommendation_origins else {}
            allowed_fields = {str(field.target_field_id) for field in definition.fields}
            if (
                not isinstance(origins, dict)
                or any(key not in allowed_fields for key in origins)
                or any(value not in {"exact", "alias", "manual"} for value in origins.values())
            ):
                raise ValueError
        except (json.JSONDecodeError, ValueError) as exc:
            raise ImportRequestError(
                ImportIssueCode.INVALID_MAPPING,
                "Mapping recommendation origins are invalid.", 422,
            ) from exc
        mutation, profile = persistence.persist_mapping(
            run_id=run_id, expected_revision=expected_revision, pack=pack,
            inspection=result.source, mapping=definition,
            save_profile=save_mapping_profile, base_profile_id=base_profile_id,
            profile_display_name=profile_display_name,
            recommendation_origins=origins,
        )
        result = result.model_copy(update={
            "run_id": mutation.run_id, "run_state": mutation.run_state.value,
            "run_revision": mutation.run_revision,
            "mapping_profile": profile.model_dump(mode="json") if profile else None,
        })
    return result
