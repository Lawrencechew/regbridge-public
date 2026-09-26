from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.canonical.models import (
    CanonicalDataType,
    CanonicalDataset,
    CanonicalFieldId,
    CanonicalRecord,
    CanonicalSchemaId,
    SourceReference,
)


class ImportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceType(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"


class SourceSheet(ImportModel):
    name: str
    visibility: Literal["visible", "hidden", "veryHidden"]
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)


class SourceColumn(ImportModel):
    index: int = Field(ge=1)
    header: str | None
    excel_column: str | None


class SourcePreviewRow(ImportModel):
    source_row: int = Field(ge=1)
    values: tuple[object | None, ...]


class SourceFileInspection(ImportModel):
    source_name: str
    source_type: SourceType
    file_size_bytes: int = Field(ge=0)
    file_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sheets: tuple[SourceSheet, ...]
    selected_sheet: str | None
    selection_required: bool
    header_row: int = Field(ge=1, le=50)
    columns: tuple[SourceColumn, ...]
    data_row_count: int | None = Field(default=None, ge=0)
    preview_rows: tuple[SourcePreviewRow, ...]
    formula_cells_detected: bool
    warnings: tuple[str, ...] = ()
    source_header_signature: str = ""
    source_signature_version: str = "source-header-v1"
    run_id: str | None = None
    run_state: str | None = None
    run_revision: int | None = None

    @model_validator(mode="after")
    def populate_source_header_signature(self) -> "SourceFileInspection":
        expected = source_header_signature(
            source_type=self.source_type,
            selected_sheet=self.selected_sheet,
            header_row=self.header_row,
            columns=self.columns,
        )
        if self.source_header_signature and self.source_header_signature != expected:
            raise ValueError("source_header_signature does not match the inspected structure")
        self.source_header_signature = expected
        return self


class StringConversion(ImportModel):
    type: Literal[CanonicalDataType.STRING] = CanonicalDataType.STRING
    trim_whitespace: bool = False


class IntegerConversion(ImportModel):
    type: Literal[CanonicalDataType.INTEGER] = CanonicalDataType.INTEGER


class DecimalConversion(ImportModel):
    type: Literal[CanonicalDataType.DECIMAL] = CanonicalDataType.DECIMAL
    thousands_separator: str | None = Field(default=None, min_length=1, max_length=1)
    decimal_separator: str = Field(default=".", min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_separators(self) -> "DecimalConversion":
        if self.thousands_separator == self.decimal_separator:
            raise ValueError("Decimal and thousands separators must differ.")
        return self


class BooleanConversion(ImportModel):
    type: Literal[CanonicalDataType.BOOLEAN] = CanonicalDataType.BOOLEAN
    true_values: tuple[str, ...] = ("true", "yes")
    false_values: tuple[str, ...] = ("false", "no")
    case_sensitive: bool = False

    @model_validator(mode="after")
    def validate_tokens(self) -> "BooleanConversion":
        normalise = (lambda item: item) if self.case_sensitive else str.casefold
        true_values = {normalise(item) for item in self.true_values}
        false_values = {normalise(item) for item in self.false_values}
        if not true_values or not false_values or true_values & false_values:
            raise ValueError("Boolean token sets must be non-empty and disjoint.")
        return self


class DateConversion(ImportModel):
    type: Literal[CanonicalDataType.DATE] = CanonicalDataType.DATE
    date_format: str | None = Field(default=None, min_length=1)


class DateTimeConversion(ImportModel):
    type: Literal[CanonicalDataType.DATETIME] = CanonicalDataType.DATETIME
    datetime_format: str | None = Field(default=None, min_length=1)


Conversion = Annotated[
    StringConversion
    | IntegerConversion
    | DecimalConversion
    | BooleanConversion
    | DateConversion
    | DateTimeConversion,
    Field(discriminator="type"),
]


class FieldMapping(ImportModel):
    source_column_index: int = Field(ge=1)
    target_field_id: CanonicalFieldId
    conversion: Conversion


class ImportMapping(ImportModel):
    target_schema_id: CanonicalSchemaId
    target_schema_version: str
    sheet_name: str | None = None
    header_row: int = Field(default=1, ge=1, le=50)
    skip_blank_rows: bool = True
    fields: tuple[FieldMapping, ...] = Field(min_length=1)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class SectionImportMapping(ImportModel):
    section_id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
    mapping: ImportMapping | None = None


class WorkflowImportMapping(ImportModel):
    sections: tuple[SectionImportMapping, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_sections(self) -> "WorkflowImportMapping":
        identifiers = [section.section_id for section in self.sections]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Workflow import section IDs must be unique")
        return self

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class ImportIssueSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"


class ImportIssueCode(StrEnum):
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    INVALID_XLSX = "INVALID_XLSX"
    XLSX_SECURITY_LIMIT_EXCEEDED = "XLSX_SECURITY_LIMIT_EXCEEDED"
    UNSUPPORTED_TEXT_ENCODING = "UNSUPPORTED_TEXT_ENCODING"
    SOURCE_LIMIT_EXCEEDED = "SOURCE_LIMIT_EXCEEDED"
    SHEET_NOT_FOUND = "SHEET_NOT_FOUND"
    SHEET_SELECTION_REQUIRED = "SHEET_SELECTION_REQUIRED"
    INVALID_HEADER_ROW = "INVALID_HEADER_ROW"
    SOURCE_COLUMN_NOT_FOUND = "SOURCE_COLUMN_NOT_FOUND"
    TARGET_FIELD_NOT_FOUND = "TARGET_FIELD_NOT_FOUND"
    MISSING_REQUIRED_MAPPING = "MISSING_REQUIRED_MAPPING"
    DUPLICATE_TARGET_MAPPING = "DUPLICATE_TARGET_MAPPING"
    DUPLICATE_SOURCE_MAPPING = "DUPLICATE_SOURCE_MAPPING"
    INCOMPATIBLE_CONVERSION = "INCOMPATIBLE_CONVERSION"
    FORMULA_CELL_UNSUPPORTED = "FORMULA_CELL_UNSUPPORTED"
    MERGED_CELL_UNSUPPORTED = "MERGED_CELL_UNSUPPORTED"
    IMPORT_VALUE_CONVERSION_FAILED = "IMPORT_VALUE_CONVERSION_FAILED"
    INVALID_MAPPING = "INVALID_MAPPING"


class ImportIssue(ImportModel):
    code: ImportIssueCode
    message: str
    severity: ImportIssueSeverity
    source: SourceReference | None = None
    target_field_id: str | None = None
    expected_type: CanonicalDataType | None = None


class ImportedDatasetSummary(ImportModel):
    dataset_id: str
    schema_id: str
    schema_version: str
    record_count: int = Field(ge=0)
    preview_count: int = Field(ge=0)


class ImportResult(ImportModel):
    success: bool
    source: SourceFileInspection
    mapping_fingerprint: str
    dataset: CanonicalDataset | None = Field(default=None, exclude=True)
    dataset_summary: ImportedDatasetSummary | None
    dataset_preview: tuple[CanonicalRecord, ...] = ()
    issues: tuple[ImportIssue, ...] = ()
    run_id: str | None = None
    run_state: str | None = None
    run_revision: int | None = None
    mapping_profile: dict[str, object] | None = None


class WorkflowSectionImportResult(ImportModel):
    section_id: str
    success: bool
    omitted: bool = False
    source: SourceFileInspection | None = None
    mapping_fingerprint: str | None = None
    dataset_summary: ImportedDatasetSummary
    dataset_preview: tuple[CanonicalRecord, ...] = ()
    issues: tuple[ImportIssue, ...] = ()


class WorkflowImportResult(ImportModel):
    success: bool
    mapping_fingerprint: str
    sections: tuple[WorkflowSectionImportResult, ...]
    datasets: dict[str, CanonicalDataset] = Field(default_factory=dict, exclude=True)
    run_id: str | None = None
    run_state: str | None = None
    run_revision: int | None = None
    mapping_profiles: dict[str, object] = Field(default_factory=dict)


def source_header_signature(
    *, source_type: SourceType, selected_sheet: str | None,
    header_row: int, columns: tuple[SourceColumn, ...],
) -> str:
    """Fingerprint only the ordered, positional source-header structure."""
    canonical = {
        "algorithm": "source-header-v1",
        "source_type": source_type.value,
        "selected_sheet": selected_sheet,
        "header_row": header_row,
        "columns": [
            {"index": column.index, "header": column.header}
            for column in columns
        ],
    }
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def json_safe_source_value(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
