from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.canonical.models import CanonicalFieldId
from app.reconciliation.models import ReconciliationReport
from app.regpacks.version import RegPackVersion
from app.validation.models import RuleScalar, ValidationReport

OUTPUT_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
OutputId = Annotated[str, StringConstraints(pattern=OUTPUT_ID_PATTERN)]


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OutputType(StrEnum):
    XLSX_TEMPLATE = "xlsx_template"


class OutputConditionOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class OutputCondition(OutputModel):
    field_id: CanonicalFieldId
    operator: OutputConditionOperator
    value: RuleScalar | None = None

    @model_validator(mode="after")
    def validate_value(self) -> "OutputCondition":
        needs_value = self.operator in {
            OutputConditionOperator.EQUALS,
            OutputConditionOperator.NOT_EQUALS,
        }
        if needs_value != (self.value is not None):
            raise ValueError("equals/not_equals require a value; null operators do not")
        return self


class RecordSelection(OutputModel):
    where: tuple[OutputCondition, ...] = ()


class LiteralSource(OutputModel):
    type: Literal["literal"] = "literal"
    value: RuleScalar | None


class DatasetFieldSource(OutputModel):
    type: Literal["dataset_field"] = "dataset_field"
    field_id: CanonicalFieldId
    selection: RecordSelection | None = None
    aggregation: Literal["unique"] = "unique"
    section_id: str | None = None


class RuntimeFieldSource(OutputModel):
    type: Literal["runtime_field"] = "runtime_field"
    field_id: CanonicalFieldId


ScalarSource = Annotated[
    LiteralSource | DatasetFieldSource | RuntimeFieldSource,
    Field(discriminator="type"),
]


class CellTarget(OutputModel):
    sheet: str = Field(min_length=1)
    cell: str

    @field_validator("cell")
    @classmethod
    def validate_cell(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]*", value):
            raise ValueError("cell must be an absolute A1-style coordinate without '$'")
        return value


class ScalarCellMapping(OutputModel):
    type: Literal["scalar_cell"] = "scalar_cell"
    source: ScalarSource
    target: CellTarget


class TableColumn(OutputModel):
    field_id: CanonicalFieldId | None = None
    literal: RuleScalar | None = None
    sequence: bool = False
    column: str

    @field_validator("column")
    @classmethod
    def validate_column(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Z]{1,3}", value):
            raise ValueError("column must be an Excel column label")
        return value

    @model_validator(mode="after")
    def validate_source(self) -> "TableColumn":
        sources = sum((self.field_id is not None, self.literal is not None, self.sequence))
        if sources != 1:
            raise ValueError("table columns require exactly one source")
        return self


class RowLookup(OutputModel):
    field_id: CanonicalFieldId
    template_column: str
    start_row: int = Field(ge=1)
    end_row: int = Field(ge=1)
    excluded_rows: tuple[int, ...] = ()

    @field_validator("template_column")
    @classmethod
    def validate_column(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Z]{1,3}", value):
            raise ValueError("template_column must be an Excel column label")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> "RowLookup":
        if self.end_row < self.start_row:
            raise ValueError("row lookup end_row must not precede start_row")
        if any(row < self.start_row or row > self.end_row for row in self.excluded_rows):
            raise ValueError("excluded rows must lie within the lookup range")
        return self


class RecordTableMapping(OutputModel):
    type: Literal["record_table"] = "record_table"
    records: RecordSelection = Field(default_factory=RecordSelection)
    sheet: str = Field(min_length=1)
    start_row: int | None = Field(default=None, ge=1)
    end_row: int | None = Field(default=None, ge=1)
    row_lookup: RowLookup | None = None
    columns: tuple[TableColumn, ...] = Field(min_length=1)
    copy_row_style: bool = True
    section_id: str | None = None

    @model_validator(mode="after")
    def validate_rows(self) -> "RecordTableMapping":
        if (self.start_row is None) == (self.row_lookup is None):
            raise ValueError("record_table requires exactly one of start_row or row_lookup")
        if self.start_row is not None and self.end_row is None:
            raise ValueError("sequential record_table mappings require a declared end_row")
        if self.start_row is not None and self.end_row is not None and self.end_row < self.start_row:
            raise ValueError("end_row must not precede start_row")
        columns = [column.column for column in self.columns]
        if len(columns) != len(set(columns)):
            raise ValueError("record_table target columns must be unique")
        return self


class ColumnLookup(OutputModel):
    field_id: CanonicalFieldId
    template_row: int = Field(ge=1)
    start_column: str
    end_column: str

    @field_validator("start_column", "end_column")
    @classmethod
    def validate_column(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Z]{1,3}", value):
            raise ValueError("lookup columns must be Excel column labels")
        return value


class MatrixCellMapping(OutputModel):
    type: Literal["matrix_cells"] = "matrix_cells"
    records: RecordSelection = Field(default_factory=RecordSelection)
    sheet: str = Field(min_length=1)
    value_field_id: CanonicalFieldId
    row_lookup: RowLookup
    column_lookup: ColumnLookup
    section_id: str | None = None


OutputMapping = Annotated[
    ScalarCellMapping | RecordTableMapping | MatrixCellMapping,
    Field(discriminator="type"),
]


class XlsxTemplateMetadata(OutputModel):
    source_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    local_path: str = Field(min_length=1)


class OutputFilename(OutputModel):
    pattern: str = Field(min_length=1, max_length=180)


class OutputDefinition(OutputModel):
    id: OutputId
    version: str
    type: Literal[OutputType.XLSX_TEMPLATE] = OutputType.XLSX_TEMPLATE
    template: XlsxTemplateMetadata
    mappings: tuple[OutputMapping, ...] = Field(min_length=1)
    filename: OutputFilename
    source_refs: tuple[str, ...] = ()

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        try:
            RegPackVersion.parse(value)
        except Exception as exc:
            raise ValueError("OutputDefinition version must use MAJOR.MINOR.PATCH.") from exc
        return value


class OutputIssueCode(StrEnum):
    OUTPUT_NOT_CONFIGURED = "OUTPUT_NOT_CONFIGURED"
    OUTPUT_TEMPLATE_NOT_FOUND = "OUTPUT_TEMPLATE_NOT_FOUND"
    OUTPUT_TEMPLATE_INTEGRITY_FAILED = "OUTPUT_TEMPLATE_INTEGRITY_FAILED"
    OUTPUT_TEMPLATE_INVALID = "OUTPUT_TEMPLATE_INVALID"
    OUTPUT_STRUCTURAL_VALIDATION_FAILED = "OUTPUT_STRUCTURAL_VALIDATION_FAILED"
    OUTPUT_SCHEMA_MISMATCH = "OUTPUT_SCHEMA_MISMATCH"
    OUTPUT_BLOCKED_BY_VALIDATION = "OUTPUT_BLOCKED_BY_VALIDATION"
    OUTPUT_BLOCKED_BY_RECONCILIATION = "OUTPUT_BLOCKED_BY_RECONCILIATION"
    OUTPUT_MAPPING_INVALID = "OUTPUT_MAPPING_INVALID"
    OUTPUT_TARGET_NOT_FOUND = "OUTPUT_TARGET_NOT_FOUND"
    OUTPUT_TARGET_NOT_WRITABLE = "OUTPUT_TARGET_NOT_WRITABLE"
    OUTPUT_VALUE_SERIALISATION_FAILED = "OUTPUT_VALUE_SERIALISATION_FAILED"
    OUTPUT_FILE_TOO_LARGE = "OUTPUT_FILE_TOO_LARGE"
    OUTPUT_GENERATION_FAILED = "OUTPUT_GENERATION_FAILED"
    OUTPUT_CAPACITY_EXCEEDED = "OUTPUT_CAPACITY_EXCEEDED"


class OutputIssue(OutputModel):
    code: OutputIssueCode
    message: str


class GeneratedArtifact(OutputModel):
    artifact_id: str
    filename: str
    media_type: str
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pack_id: str
    pack_version: str
    pack_fingerprint: str
    dataset_id: str
    dataset_fingerprint: str
    output_definition_id: str
    output_definition_version: str


class OutputGenerationResult(OutputModel):
    success: bool
    artifact: GeneratedArtifact | None = None
    validation_report: ValidationReport | None = None
    reconciliation_report: ReconciliationReport | None = None
    issues: tuple[OutputIssue, ...] = ()


class GeneratedOutput:
    def __init__(self, result: OutputGenerationResult, content: bytes | None = None) -> None:
        self.result = result
        self.content = content


OutputScalar = str | int | Decimal | bool | date | datetime | None
