from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.canonical.models import CanonicalFieldId, SourceReference
from app.regpacks.version import RegPackVersion
from app.validation.models import RuleId, RuleSeverity


class ReconciliationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReconciliationRuleType(StrEnum):
    ROW_EQUATION = "row_equation"
    AGGREGATE_EQUATION = "aggregate_equation"
    GROUPED_AGGREGATE = "grouped_aggregate"


class ArithmeticOperator(StrEnum):
    ADD = "add"
    SUBTRACT = "subtract"


class AggregateFunction(StrEnum):
    SUM = "sum"
    COUNT = "count"


class FieldTerm(ReconciliationModel):
    field_id: CanonicalFieldId
    operator: ArithmeticOperator = ArithmeticOperator.ADD


class FieldOperand(ReconciliationModel):
    field_id: CanonicalFieldId


class AggregateTerm(ReconciliationModel):
    aggregate: AggregateFunction
    field_id: CanonicalFieldId
    operator: ArithmeticOperator = ArithmeticOperator.ADD


class AggregateOperand(ReconciliationModel):
    aggregate: AggregateFunction
    field_id: CanonicalFieldId


class ReconciliationRuleBase(ReconciliationModel):
    id: RuleId
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    severity: RuleSeverity
    source_refs: tuple[str, ...] = ()
    tolerance: Decimal = Field(default=Decimal("0"), ge=0)


class RowEquationRule(ReconciliationRuleBase):
    type: Literal[ReconciliationRuleType.ROW_EQUATION] = ReconciliationRuleType.ROW_EQUATION
    left: tuple[FieldTerm, ...] = Field(min_length=1)
    right: FieldOperand


class AggregateEquationRule(ReconciliationRuleBase):
    type: Literal[ReconciliationRuleType.AGGREGATE_EQUATION] = (
        ReconciliationRuleType.AGGREGATE_EQUATION
    )
    left: tuple[AggregateTerm, ...] = Field(min_length=1)
    right: AggregateOperand


class GroupedAggregateRule(ReconciliationRuleBase):
    type: Literal[ReconciliationRuleType.GROUPED_AGGREGATE] = (
        ReconciliationRuleType.GROUPED_AGGREGATE
    )
    group_by: tuple[CanonicalFieldId, ...] = Field(min_length=1)
    left: tuple[AggregateTerm, ...] = Field(min_length=1)
    right: AggregateOperand

    @model_validator(mode="after")
    def validate_unique_group_fields(self) -> "GroupedAggregateRule":
        if len(self.group_by) != len(set(self.group_by)):
            raise ValueError("group_by fields must be unique")
        return self


ReconciliationRule = Annotated[
    RowEquationRule | AggregateEquationRule | GroupedAggregateRule,
    Field(discriminator="type"),
]


class ReconciliationRuleSet(ReconciliationModel):
    id: RuleId
    version: str
    name: str = Field(min_length=1)
    description: str | None = None
    rules: tuple[ReconciliationRule, ...] = Field(min_length=1)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        try:
            RegPackVersion.parse(value)
        except Exception as exc:
            raise ValueError("ReconciliationRuleSet version must use MAJOR.MINOR.PATCH.") from exc
        return value

    @model_validator(mode="after")
    def validate_unique_rule_ids(self) -> "ReconciliationRuleSet":
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Reconciliation rule IDs must be unique.")
        return self


class ReconciliationSourceValue(ReconciliationModel):
    field_id: str
    value: object | None
    source: SourceReference | None = None


class ReconciliationFinding(ReconciliationModel):
    rule_id: str
    rule_type: ReconciliationRuleType
    rule_name: str
    severity: RuleSeverity
    message: str
    record_id: str | None = None
    group: dict[str, object | None] | None = None
    expected: str
    actual: str
    difference: str
    tolerance: str
    source_refs: tuple[str, ...] = ()
    source_values: tuple[ReconciliationSourceValue, ...] = ()
    records_considered: int | None = None
    records_skipped: int | None = None


class ReconciliationRuleSummary(ReconciliationModel):
    rule_id: str
    rule_type: ReconciliationRuleType
    severity: RuleSeverity
    evaluated_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)


class ReconciliationReportSummary(ReconciliationModel):
    rules: int = Field(ge=0)
    blocking_findings: int = Field(ge=0)
    review_findings: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    skipped_checks: int = Field(ge=0)


class ReconciliationReport(ReconciliationModel):
    dataset_id: str
    dataset_fingerprint: str
    rule_set_id: str
    rule_set_version: str
    valid: bool
    ready: bool
    summary: ReconciliationReportSummary
    rule_summaries: tuple[ReconciliationRuleSummary, ...]
    findings: tuple[ReconciliationFinding, ...]
    evaluated_at: datetime
    fingerprint: str
