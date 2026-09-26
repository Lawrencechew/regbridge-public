from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_regpack_registry
from app.canonical.models import CanonicalSchema
from app.imports.errors import ImportRequestError
from app.imports.models import ImportIssueCode
from app.regpacks.registry import RegPackRegistry
from app.schemas.regpacks import (
    RegPackListResponse,
    RegPackManifestResponse,
    RegPackSummary,
    RegPackVersionsResponse,
    RegPackWorkflowResponse,
    RegPackWorkflowSectionResponse,
)

router = APIRouter(prefix="/regpacks", tags=["regpacks"])
Registry = Annotated[RegPackRegistry, Depends(get_regpack_registry)]


@router.get("", response_model=RegPackListResponse)
def list_regpacks(registry: Registry) -> RegPackListResponse:
    return RegPackListResponse(
        packs=[
            RegPackSummary(
                id=manifest.id,
                name=manifest.name,
                regulator=manifest.regulator,
                versions=registry.list_versions(manifest.id),
                workflow_versions=[
                    version
                    for version in registry.list_versions(manifest.id)
                    if (
                        (pack := registry.get(manifest.id, version)).canonical_schema
                        is not None
                        and pack.validation_rules is not None
                        and pack.reconciliation_rules is not None
                        or pack.workflow_definition is not None
                    )
                ],
                output_versions=[
                    version
                    for version in registry.list_versions(manifest.id)
                    if registry.get(manifest.id, version).output_definition is not None
                ],
            )
            for manifest in registry.list_packs()
        ]
    )


@router.get("/{pack_id}/versions", response_model=RegPackVersionsResponse)
def list_regpack_versions(pack_id: str, registry: Registry) -> RegPackVersionsResponse:
    return RegPackVersionsResponse(
        pack_id=pack_id,
        versions=registry.list_versions(pack_id),
    )


@router.get(
    "/{pack_id}/versions/{version}",
    response_model=RegPackManifestResponse,
)
def read_regpack_version(
    pack_id: str, version: str, registry: Registry
) -> RegPackManifestResponse:
    pack = registry.get(pack_id, version)
    data = pack.manifest.model_dump(by_alias=True)
    data.update(
        fingerprint=pack.fingerprint,
        canonical_schema_id=getattr(pack.canonical_schema, "id", None),
        canonical_schema_version=getattr(pack.canonical_schema, "version", None),
        validation_rule_set_id=getattr(pack.validation_rules, "id", None),
        validation_rule_set_version=getattr(pack.validation_rules, "version", None),
        validation_rule_count=(
            len(pack.validation_rules.rules) if pack.validation_rules is not None else None
        ),
        reconciliation_rule_set_id=getattr(pack.reconciliation_rules, "id", None),
        reconciliation_rule_set_version=getattr(
            pack.reconciliation_rules, "version", None
        ),
        reconciliation_rule_count=(
            len(pack.reconciliation_rules.rules)
            if pack.reconciliation_rules is not None
            else None
        ),
        output_definition_id=getattr(pack.output_definition, "id", None),
        output_definition_version=getattr(pack.output_definition, "version", None),
        output_type=(
            pack.output_definition.type.value
            if pack.output_definition is not None
            else None
        ),
        output_template_source_id=(
            pack.output_definition.template.source_id
            if pack.output_definition is not None
            else None
        ),
        output_template_sha256=(
            pack.output_definition.template.sha256
            if pack.output_definition is not None
            else None
        ),
        workflow_definition_id=getattr(pack.workflow_definition, "id", None),
        workflow_definition_version=getattr(pack.workflow_definition, "version", None),
        workflow_section_count=(len(pack.sections) if pack.workflow_definition else None),
        runtime_field_count=(
            len(pack.workflow_definition.runtime_fields)
            if pack.workflow_definition is not None
            else None
        ),
    )
    return RegPackManifestResponse.model_validate(data)


@router.get(
    "/{pack_id}/versions/{version}/schema",
    response_model=CanonicalSchema,
)
def read_regpack_schema(
    pack_id: str, version: str, registry: Registry
) -> CanonicalSchema:
    pack = registry.get(pack_id, version)
    if pack.canonical_schema is None:
        raise ImportRequestError(
            ImportIssueCode.INCOMPATIBLE_CONVERSION,
            "The selected RegPack has no canonical schema.",
            422,
        )
    return pack.canonical_schema


@router.get(
    "/{pack_id}/versions/{version}/workflow",
    response_model=RegPackWorkflowResponse,
)
def read_regpack_workflow(
    pack_id: str, version: str, registry: Registry
) -> RegPackWorkflowResponse:
    pack = registry.get(pack_id, version)
    if pack.workflow_definition is not None:
        return RegPackWorkflowResponse(
            id=pack.workflow_definition.id,
            version=pack.workflow_definition.version,
            runtime_fields=pack.workflow_definition.runtime_fields,
            rules=pack.workflow_definition.rules,
            sections=tuple(
                RegPackWorkflowSectionResponse(
                    id=section.id,
                    name=section.name,
                    description=section.description,
                    optional=section.optional,
                    canonical_schema=section.canonical_schema,
                    reconciliation=(
                        "applicable"
                        if section.reconciliation_rules is not None
                        else "not_applicable"
                    ),
                )
                for section in pack.sections
            ),
        )
    if pack.canonical_schema is None:
        raise ImportRequestError(
            ImportIssueCode.INCOMPATIBLE_CONVERSION,
            "The selected RegPack has no executable workflow.",
            422,
        )
    return RegPackWorkflowResponse(
        id=f"{pack.id}-default-workflow",
        version=pack.version,
        runtime_fields=(),
        rules=(),
        sections=(RegPackWorkflowSectionResponse(
            id="default",
            name=pack.canonical_schema.name,
            description=pack.canonical_schema.description,
            optional=False,
            canonical_schema=pack.canonical_schema,
            reconciliation="applicable",
        ),),
    )
