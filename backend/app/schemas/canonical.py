from pydantic import BaseModel


class CanonicalTypesResponse(BaseModel):
    types: list[str]


class CanonicalSchemaSummary(BaseModel):
    id: str
    version: str
    name: str
    field_count: int


class CanonicalSchemasResponse(BaseModel):
    schemas: list[CanonicalSchemaSummary]
