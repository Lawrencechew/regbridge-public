import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.canonical.models import CanonicalFieldId, SourceReference
from app.regpacks.version import RegPackVersion

RULE_ID_PATTERN = r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$"
RuleId = Annotated[str, StringConstraints(pattern=RULE_ID_PATTERN)]
RuleScalar = StrictStr | StrictInt | Decimal | StrictBool | date | datetime
ComparableScalar = StrictInt | Decimal | date | datetime


class ValidationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RuleType(StrEnum):
    REQUIRED = "required"
    NOT_BLANK = "not_blank"
    ENUM = "enum"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    DECIMAL_PLACES = "decimal_places"
    REGEX = "regex"
    ALLOWED_CHARACTERS = "allowed_characters"
    UNIQUE = "unique"
    CONDITIONAL_REQUIRED = "conditional_required"


class RuleSeverity(StrEnum):
    BLOCKING = "blocking"
    REVIEW = "review"


class RuleOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RuleBase(ValidationModel):
    id: RuleId
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    severity: RuleSeverity
    field_id: CanonicalFieldId
    source_refs: tuple[str, ...] = ()


class RequiredRule(RuleBase):
    type: Literal[RuleType.REQUIRED] = RuleType.REQUIRED


class NotBlankRule(RuleBase):
    type: Literal[RuleType.NOT_BLANK] = RuleType.NOT_BLANK


class EnumRule(RuleBase):
    type: Literal[RuleType.ENUM] = RuleType.ENUM
    allowed_values: tuple[RuleScalar, ...] = Field(min_length=1)


class MinimumRule(RuleBase):
    type: Literal[RuleType.MINIMUM] = RuleType.MINIMUM
    minimum: ComparableScalar
    inclusive: bool = True


class MaximumRule(RuleBase):
    type: Literal[RuleType.MAXIMUM] = RuleType.MAXIMUM
    maximum: ComparableScalar
    inclusive: bool = True


class DecimalPlacesRule(RuleBase):
    type: Literal[RuleType.DECIMAL_PLACES] = RuleType.DECIMAL_PLACES
    maximum_places: int = Field(ge=0)


class RegexRule(RuleBase):
    type: Literal[RuleType.REGEX] = RuleType.REGEX
    pattern: str = Field(min_length=1)

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError("pattern must be a valid Python regular expression") from exc
        return value


class AllowedCharactersRule(RuleBase):
    type: Literal[RuleType.ALLOWED_CHARACTERS] = RuleType.ALLOWED_CHARACTERS
    allowed_characters: str = Field(min_length=1)


class UniqueRule(RuleBase):
    type: Literal[RuleType.UNIQUE] = RuleType.UNIQUE
    ignore_null: bool = True


class ConditionOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class SimpleCondition(ValidationModel):
    field_id: CanonicalFieldId
    operator: ConditionOperator
    value: RuleScalar | None = None

    @model_validator(mode="after")
    def validate_operator_value(self) -> "SimpleCondition":
        value_operators = {ConditionOperator.EQUALS, ConditionOperator.NOT_EQUALS}
        if self.operator in value_operators and self.value is None:
            raise ValueError("equals and not_equals conditions require a value")
        if self.operator not in value_operators and self.value is not None:
            raise ValueError("is_null and is_not_null conditions do not accept a value")
        return self


class ConditionalRequiredRule(RuleBase):
    type: Literal[RuleType.CONDITIONAL_REQUIRED] = RuleType.CONDITIONAL_REQUIRED
    when: SimpleCondition


ValidationRule = Annotated[
    RequiredRule
    | NotBlankRule
    | EnumRule
    | MinimumRule
    | MaximumRule
    | DecimalPlacesRule
    | RegexRule
    | AllowedCharactersRule
    | UniqueRule
    | ConditionalRequiredRule,
    Field(discriminator="type"),
]


class RuleSet(ValidationModel):
    id: RuleId
    version: str
    name: str = Field(min_length=1)
    description: str | None = None
    rules: tuple[ValidationRule, ...] = Field(min_length=1)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        try:
            RegPackVersion.parse(value)
        except Exception as exc:
            raise ValueError("RuleSet version must use MAJOR.MINOR.PATCH.") from exc
        return value

    @model_validator(mode="after")
    def validate_unique_rule_ids(self) -> "RuleSet":
        rule_ids = [rule.id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("Rule IDs must be unique within a RuleSet.")
        return self


class ValidationFinding(ValidationModel):
    rule_id: str
    rule_type: RuleType
    rule_name: str
    severity: RuleSeverity
    message: str
    record_id: str | None = None
    field_id: str | None = None
    actual: object | None = None
    expected: object | None = None
    source: SourceReference | None = None
    source_refs: tuple[str, ...] = ()


class ValidationRuleSummary(ValidationModel):
    rule_id: str
    rule_type: RuleType
    severity: RuleSeverity
    evaluated_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)


class ValidationReportSummary(ValidationModel):
    rules: int = Field(ge=0)
    blocking_findings: int = Field(ge=0)
    review_findings: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    skipped_checks: int = Field(ge=0)


class ValidationReport(ValidationModel):
    dataset_id: str
    dataset_fingerprint: str
    rule_set_id: str
    rule_set_version: str
    valid: bool
    ready: bool
    summary: ValidationReportSummary
    rule_summaries: tuple[ValidationRuleSummary, ...]
    findings: tuple[ValidationFinding, ...]
    report_fingerprint: str
    evaluated_at: datetime
