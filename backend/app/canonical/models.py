import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.regpacks.version import RegPackVersion

FIELD_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
SCHEMA_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

CanonicalFieldId = Annotated[
    str, StringConstraints(pattern=FIELD_ID_PATTERN.pattern)
]
CanonicalSchemaId = Annotated[
    str, StringConstraints(pattern=SCHEMA_ID_PATTERN.pattern)
]


class CanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CanonicalDataType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"


class CanonicalFieldDefinition(CanonicalModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    id: CanonicalFieldId
    name: str = Field(min_length=1)
    data_type: CanonicalDataType
    required: bool = False
    description: str | None = None
    aliases: tuple[str, ...] = ()

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(alias.strip() for alias in value)
        if any(not alias for alias in cleaned):
            raise ValueError("Mapping aliases must not be blank.")
        normalised = [_normalise_mapping_term(alias) for alias in cleaned]
        if len(normalised) != len(set(normalised)):
            raise ValueError("Mapping aliases must be unique for a field.")
        return cleaned


class CanonicalSchema(CanonicalModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    id: CanonicalSchemaId
    version: str
    name: str = Field(min_length=1)
    description: str | None = None
    fields: tuple[CanonicalFieldDefinition, ...] = Field(min_length=1)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        try:
            RegPackVersion.parse(value)
        except Exception as exc:
            raise ValueError("Schema version must use MAJOR.MINOR.PATCH.") from exc
        return value

    @model_validator(mode="after")
    def validate_unique_field_ids(self) -> "CanonicalSchema":
        field_ids = [field.id for field in self.fields]
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("Canonical field IDs must be unique within a schema.")
        mapping_term_owners: dict[str, str] = {}
        for field in self.fields:
            for term in (field.id, field.name, *field.aliases):
                normalised = _normalise_mapping_term(term)
                owner = mapping_term_owners.get(normalised)
                if owner is not None and owner != field.id:
                    raise ValueError(
                        "Canonical field names and mapping aliases must be unique "
                        "after normalisation."
                    )
                mapping_term_owners[normalised] = field.id
        return self

    @property
    def parsed_version(self) -> RegPackVersion:
        return RegPackVersion.parse(self.version)

    @property
    def fields_by_id(self) -> dict[str, CanonicalFieldDefinition]:
        return {field.id: field for field in self.fields}


def _normalise_mapping_term(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in decomposed if character.isalnum())


class SourceReference(CanonicalModel):
    source_name: str | None = None
    sheet: str | None = None
    row: int | None = Field(default=None, gt=0)
    column: str | None = None

    @field_validator("source_name")
    @classmethod
    def reject_absolute_source_paths(cls, value: str | None) -> str | None:
        if value is not None and (
            PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()
        ):
            raise ValueError("source_name must be a logical name, not an absolute path")
        return value


class CanonicalValue(CanonicalModel):
    data_type: CanonicalDataType
    value: object | None
    source: SourceReference | None = None

    @model_validator(mode="before")
    @classmethod
    def decode_json_scalar(cls, data: object, info: ValidationInfo) -> object:
        if info.mode != "json" or not isinstance(data, dict) or data.get("value") is None:
            return data
        decoded = dict(data)
        data_type = decoded.get("data_type")
        value = decoded["value"]
        if data_type == CanonicalDataType.DECIMAL and isinstance(value, str):
            decoded["value"] = Decimal(value)
        elif data_type == CanonicalDataType.DATE and isinstance(value, str):
            decoded["value"] = date.fromisoformat(value)
        elif data_type == CanonicalDataType.DATETIME and isinstance(value, str):
            decoded["value"] = datetime.fromisoformat(value)
        return decoded

    @model_validator(mode="after")
    def validate_scalar_type(self) -> "CanonicalValue":
        if self.value is not None and not canonical_value_matches_type(
            self.value, self.data_type
        ):
            raise ValueError(
                f"value must be a strict {self.data_type.value} canonical value"
            )
        return self


def canonical_value_matches_type(value: object, data_type: CanonicalDataType) -> bool:
    expected = {
        CanonicalDataType.STRING: lambda item: type(item) is str,
        CanonicalDataType.INTEGER: lambda item: type(item) is int,
        CanonicalDataType.DECIMAL: lambda item: isinstance(item, Decimal),
        CanonicalDataType.BOOLEAN: lambda item: type(item) is bool,
        CanonicalDataType.DATE: lambda item: type(item) is date,
        CanonicalDataType.DATETIME: lambda item: type(item) is datetime,
    }
    return expected[data_type](value)


class CanonicalRecord(CanonicalModel):
    record_id: str = Field(min_length=1)
    values: dict[str, CanonicalValue]


class CanonicalDataset(CanonicalModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, validate_by_alias=True, serialize_by_alias=True
    )

    dataset_id: str = Field(min_length=1)
    canonical_schema: CanonicalSchema = Field(alias="schema")
    records: list[CanonicalRecord] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
