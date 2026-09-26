from app.canonical.errors import (
    CanonicalSchemaNotFoundError,
    DuplicateCanonicalSchemaError,
)
from app.canonical.models import CanonicalSchema
from app.regpacks.errors import RegPackVersionError
from app.regpacks.version import RegPackVersion


class CanonicalSchemaRegistry:
    def __init__(self) -> None:
        self._schemas: dict[str, dict[RegPackVersion, CanonicalSchema]] = {}

    def register(self, schema: CanonicalSchema) -> None:
        versions = self._schemas.setdefault(schema.id, {})
        if schema.parsed_version in versions:
            raise DuplicateCanonicalSchemaError(
                "The canonical schema ID and version combination is already registered."
            )
        versions[schema.parsed_version] = schema

    def list_schemas(self) -> list[CanonicalSchema]:
        return [
            self._schemas[schema_id][version]
            for schema_id in sorted(self._schemas)
            for version in sorted(self._schemas[schema_id])
        ]

    def get(self, schema_id: str, version: str) -> CanonicalSchema:
        try:
            parsed_version = RegPackVersion.parse(version)
        except RegPackVersionError as exc:
            raise CanonicalSchemaNotFoundError(
                "The requested canonical schema was not found."
            ) from exc
        versions = self._schemas.get(schema_id)
        if versions is None or parsed_version not in versions:
            raise CanonicalSchemaNotFoundError(
                "The requested canonical schema was not found."
            )
        return versions[parsed_version]

    @property
    def schema_count(self) -> int:
        return sum(len(versions) for versions in self._schemas.values())
