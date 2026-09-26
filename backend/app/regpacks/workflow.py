from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.canonical.models import CanonicalDataType, CanonicalFieldId, CanonicalSchema
from app.reconciliation.models import ReconciliationRuleSet
from app.regpacks.version import RegPackVersion
from app.validation.models import RuleSeverity, RuleSet

SECTION_ID_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"
SectionId = Annotated[str, StringConstraints(pattern=SECTION_ID_PATTERN)]


class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RuntimeFieldDefinition(WorkflowModel):
    id: CanonicalFieldId
    name: str = Field(min_length=1)
    data_type: Literal[CanonicalDataType.STRING, CanonicalDataType.DATE]
    required: bool = False
    sensitive: bool = False
    description: str | None = None
    max_length: int | None = Field(default=None, ge=1)
    source_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_constraints(self) -> "RuntimeFieldDefinition":
        if self.max_length is not None and self.data_type != CanonicalDataType.STRING:
            raise ValueError("max_length is only valid for string runtime fields")
        return self


class WorkflowSectionDefinition(WorkflowModel):
    id: SectionId
    name: str = Field(min_length=1)
    description: str | None = None
    optional: bool = False
    canonical_schema: str
    validation_rules: str
    reconciliation_rules: str | None = None

    @model_validator(mode="after")
    def validate_paths(self) -> "WorkflowSectionDefinition":
        for value in (
            self.canonical_schema,
            self.validation_rules,
            *(() if self.reconciliation_rules is None else (self.reconciliation_rules,)),
        ):
            posix = PurePosixPath(value)
            windows = PureWindowsPath(value)
            if posix.is_absolute() or windows.is_absolute() or ".." in posix.parts or ".." in windows.parts:
                raise ValueError("Workflow component paths must remain relative to the pack")
        return self


class WorkflowRuleType(StrEnum):
    DATE_ORDER = "date_order"
    RECORD_DATE_RANGE = "record_date_range"


class WorkflowRuleBase(WorkflowModel):
    id: str = Field(pattern=r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    severity: RuleSeverity
    source_refs: tuple[str, ...] = Field(min_length=1)


class DateOrderWorkflowRule(WorkflowRuleBase):
    type: Literal[WorkflowRuleType.DATE_ORDER] = WorkflowRuleType.DATE_ORDER
    start_field_id: CanonicalFieldId
    end_field_id: CanonicalFieldId


class RecordDateRangeWorkflowRule(WorkflowRuleBase):
    type: Literal[WorkflowRuleType.RECORD_DATE_RANGE] = WorkflowRuleType.RECORD_DATE_RANGE
    section_id: SectionId
    field_id: CanonicalFieldId
    start_field_id: CanonicalFieldId
    end_field_id: CanonicalFieldId


WorkflowRule = Annotated[
    DateOrderWorkflowRule | RecordDateRangeWorkflowRule,
    Field(discriminator="type"),
]


class WorkflowDefinition(WorkflowModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    version: str
    runtime_fields: tuple[RuntimeFieldDefinition, ...] = ()
    sections: tuple[WorkflowSectionDefinition, ...] = Field(min_length=1)
    rules: tuple[WorkflowRule, ...] = ()

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        RegPackVersion.parse(value)
        return value

    @model_validator(mode="after")
    def validate_identifiers(self) -> "WorkflowDefinition":
        section_ids = [section.id for section in self.sections]
        field_ids = [field.id for field in self.runtime_fields]
        rule_ids = [rule.id for rule in self.rules]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("Workflow section IDs must be unique")
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("Runtime field IDs must be unique")
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("Workflow rule IDs must be unique")
        sections = set(section_ids)
        fields = set(field_ids)
        for rule in self.rules:
            if rule.start_field_id not in fields or rule.end_field_id not in fields:
                raise ValueError("Workflow rules reference unknown runtime fields")
            if isinstance(rule, RecordDateRangeWorkflowRule) and rule.section_id not in sections:
                raise ValueError("Workflow rules reference an unknown section")
        return self


@dataclass(frozen=True)
class LoadedRegPackSection:
    id: str
    name: str
    description: str | None
    optional: bool
    canonical_schema: CanonicalSchema
    validation_rules: RuleSet
    reconciliation_rules: ReconciliationRuleSet | None


class RuntimeFieldIssue(WorkflowModel):
    rule_id: str
    severity: RuleSeverity
    message: str
    field_id: str | None = None
    section_id: str | None = None
    record_id: str | None = None
    source_refs: tuple[str, ...]


class RuntimeValidationResult(WorkflowModel):
    valid: bool
    ready: bool
    blocking_findings: int = Field(ge=0)
    review_findings: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    findings: tuple[RuntimeFieldIssue, ...]
    fingerprint: str


def parse_runtime_value(field: RuntimeFieldDefinition, value: object) -> str | date:
    if field.data_type == CanonicalDataType.STRING:
        if not isinstance(value, str):
            raise ValueError("must be text")
        return value
    if isinstance(value, date) and not hasattr(value, "hour"):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError("must be an ISO date")
