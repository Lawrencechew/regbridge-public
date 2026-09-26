from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_canonical_schema_registry
from app.canonical.models import CanonicalDataType
from app.canonical.registry import CanonicalSchemaRegistry
from app.schemas.canonical import (
    CanonicalSchemasResponse,
    CanonicalSchemaSummary,
    CanonicalTypesResponse,
)

router = APIRouter(prefix="/canonical", tags=["canonical"])
SchemaRegistry = Annotated[
    CanonicalSchemaRegistry, Depends(get_canonical_schema_registry)
]


@router.get("/types", response_model=CanonicalTypesResponse)
def list_canonical_types() -> CanonicalTypesResponse:
    return CanonicalTypesResponse(types=sorted(item.value for item in CanonicalDataType))


@router.get("/schemas", response_model=CanonicalSchemasResponse)
def list_canonical_schemas(registry: SchemaRegistry) -> CanonicalSchemasResponse:
    return CanonicalSchemasResponse(
        schemas=[
            CanonicalSchemaSummary(
                id=schema.id,
                version=schema.version,
                name=schema.name,
                field_count=len(schema.fields),
            )
            for schema in registry.list_schemas()
        ]
    )
