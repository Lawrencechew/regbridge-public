import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, cast

from app.canonical.models import CanonicalDataset, CanonicalRecord, CanonicalValue
from app.validation.models import (
    AllowedCharactersRule,
    ConditionalRequiredRule,
    DecimalPlacesRule,
    EnumRule,
    MaximumRule,
    MinimumRule,
    NotBlankRule,
    RegexRule,
    RequiredRule,
    RuleOutcome,
    SimpleCondition,
    UniqueRule,
    ValidationFinding,
    ValidationRule,
)


@dataclass(frozen=True)
class Evaluation:
    outcome: RuleOutcome
    finding: ValidationFinding | None = None


class RuleEvaluator(Protocol):
    def evaluate(
        self, rule: ValidationRule, dataset: CanonicalDataset
    ) -> list[Evaluation]: ...


def serialise_scalar(value: object | None) -> object | None:
    if isinstance(value, Decimal):
        return str(value)
    if type(value) is datetime:
        return value.isoformat()
    if type(value) is date:
        return value.isoformat()
    return value


def is_blank(value: object | None) -> bool:
    return value is None or (type(value) is str and not value.strip())


def values_equal(left: object | None, right: object | None) -> bool:
    return type(left) is type(right) and left == right


def get_value(record: CanonicalRecord, field_id: str) -> CanonicalValue | None:
    return record.values.get(field_id)


def finding(
    rule: ValidationRule,
    record: CanonicalRecord,
    *,
    message: str,
    actual: object | None,
    expected: object | None,
) -> ValidationFinding:
    canonical_value = get_value(record, rule.field_id)
    return ValidationFinding(
        rule_id=rule.id,
        rule_type=rule.type,
        rule_name=rule.name,
        severity=rule.severity,
        message=message,
        record_id=record.record_id,
        field_id=rule.field_id,
        actual=serialise_scalar(actual),
        expected=expected,
        source=canonical_value.source if canonical_value is not None else None,
        source_refs=rule.source_refs,
    )


class RequiredEvaluator:
    def evaluate(self, rule: ValidationRule, dataset: CanonicalDataset) -> list[Evaluation]:
        typed_rule = cast(RequiredRule, rule)
        results = []
        for record in dataset.records:
            if typed_rule.field_id in record.values:
                results.append(Evaluation(RuleOutcome.PASSED))
            else:
                results.append(
                    Evaluation(
                        RuleOutcome.FAILED,
                        finding(
                            typed_rule,
                            record,
                            message=f"Required field '{typed_rule.field_id}' is missing.",
                            actual=None,
                            expected="field present",
                        ),
                    )
                )
        return results


class NotBlankEvaluator:
    def evaluate(self, rule: ValidationRule, dataset: CanonicalDataset) -> list[Evaluation]:
        typed_rule = cast(NotBlankRule, rule)
        results = []
        for record in dataset.records:
            canonical_value = get_value(record, typed_rule.field_id)
            value = canonical_value.value if canonical_value is not None else None
            if is_blank(value):
                results.append(
                    Evaluation(
                        RuleOutcome.FAILED,
                        finding(
                            typed_rule,
                            record,
                            message=f"Field '{typed_rule.field_id}' must not be blank.",
                            actual=value,
                            expected="non-blank value",
                        ),
                    )
                )
            else:
                results.append(Evaluation(RuleOutcome.PASSED))
        return results


class EnumEvaluator:
    def evaluate(self, rule: ValidationRule, dataset: CanonicalDataset) -> list[Evaluation]:
        typed_rule = cast(EnumRule, rule)
        results = []
        expected = [serialise_scalar(value) for value in typed_rule.allowed_values]
        for record in dataset.records:
            canonical_value = get_value(record, typed_rule.field_id)
            if canonical_value is None or canonical_value.value is None:
                results.append(Evaluation(RuleOutcome.SKIPPED))
            elif any(
                values_equal(canonical_value.value, allowed)
                for allowed in typed_rule.allowed_values
            ):
                results.append(Evaluation(RuleOutcome.PASSED))
            else:
                results.append(
                    Evaluation(
                        RuleOutcome.FAILED,
                        finding(
                            typed_rule,
                            record,
                            message=f"Field '{typed_rule.field_id}' is not an allowed value.",
                            actual=canonical_value.value,
                            expected=expected,
                        ),
                    )
                )
        return results


class MinimumEvaluator:
    def evaluate(self, rule: ValidationRule, dataset: CanonicalDataset) -> list[Evaluation]:
        typed_rule = cast(MinimumRule, rule)
        results = []
        operator = ">=" if typed_rule.inclusive else ">"
        for record in dataset.records:
            canonical_value = get_value(record, typed_rule.field_id)
            if canonical_value is None or canonical_value.value is None:
                results.append(Evaluation(RuleOutcome.SKIPPED))
                continue
            passed = (
                canonical_value.value >= typed_rule.minimum
                if typed_rule.inclusive
                else canonical_value.value > typed_rule.minimum
            )
            results.append(
                Evaluation(RuleOutcome.PASSED)
                if passed
                else Evaluation(
                    RuleOutcome.FAILED,
                    finding(
                        typed_rule,
                        record,
                        message=f"Field '{typed_rule.field_id}' is below its minimum.",
                        actual=canonical_value.value,
                        expected=f"{operator} {serialise_scalar(typed_rule.minimum)}",
                    ),
                )
            )
        return results


class MaximumEvaluator:
    def evaluate(self, rule: ValidationRule, dataset: CanonicalDataset) -> list[Evaluation]:
        typed_rule = cast(MaximumRule, rule)
        results = []
        operator = "<=" if typed_rule.inclusive else "<"
        for record in dataset.records:
            canonical_value = get_value(record, typed_rule.field_id)
            if canonical_value is None or canonical_value.value is None:
                results.append(Evaluation(RuleOutcome.SKIPPED))
                continue
            passed = (
                canonical_value.value <= typed_rule.maximum
                if typed_rule.inclusive
                else canonical_value.value < typed_rule.maximum
            )
            results.append(
                Evaluation(RuleOutcome.PASSED)
                if passed
                else Evaluation(
                    RuleOutcome.FAILED,
                    finding(
                        typed_rule,
                        record,
                        message=f"Field '{typed_rule.field_id}' exceeds its maximum.",
                        actual=canonical_value.value,
                        expected=f"{operator} {serialise_scalar(typed_rule.maximum)}",
                    ),
                )
            )
        return results


class DecimalPlacesEvaluator:
    def evaluate(self, rule: ValidationRule, dataset: CanonicalDataset) -> list[Evaluation]:
        typed_rule = cast(DecimalPlacesRule, rule)
        results = []
        for record in dataset.records:
            canonical_value = get_value(record, typed_rule.field_id)
            if canonical_value is None or canonical_value.value is None:
                results.append(Evaluation(RuleOutcome.SKIPPED))
                continue
            decimal_value = cast(Decimal, canonical_value.value)
            places = max(0, -decimal_value.as_tuple().exponent)
            results.append(
                Evaluation(RuleOutcome.PASSED)
                if places <= typed_rule.maximum_places
                else Evaluation(
                    RuleOutcome.FAILED,
                    finding(
                        typed_rule,
                        record,
                        message=f"Field '{typed_rule.field_id}' has too many decimal places.",
                        actual=decimal_value,
                        expected=f"maximum {typed_rule.maximum_places} decimal places",
                    ),
                )
            )
        return results


class RegexEvaluator:
    def __init__(self) -> None:
        self._patterns: dict[str, re.Pattern[str]] = {}

    def evaluate(self, rule: ValidationRule, dataset: CanonicalDataset) -> list[Evaluation]:
        typed_rule = cast(RegexRule, rule)
        pattern = self._patterns.setdefault(
            typed_rule.pattern, re.compile(typed_rule.pattern)
        )
        results = []
        for record in dataset.records:
            canonical_value = get_value(record, typed_rule.field_id)
            if canonical_value is None or canonical_value.value is None:
                results.append(Evaluation(RuleOutcome.SKIPPED))
            elif pattern.fullmatch(cast(str, canonical_value.value)) is not None:
                results.append(Evaluation(RuleOutcome.PASSED))
            else:
                results.append(
                    Evaluation(
                        RuleOutcome.FAILED,
                        finding(
                            typed_rule,
                            record,
                            message=f"Field '{typed_rule.field_id}' does not match the required pattern.",
                            actual=canonical_value.value,
                            expected=typed_rule.pattern,
                        ),
                    )
                )
        return results


class AllowedCharactersEvaluator:
    def evaluate(self, rule: ValidationRule, dataset: CanonicalDataset) -> list[Evaluation]:
        typed_rule = cast(AllowedCharactersRule, rule)
        allowed = set(typed_rule.allowed_characters)
        results = []
        for record in dataset.records:
            canonical_value = get_value(record, typed_rule.field_id)
            if canonical_value is None or canonical_value.value is None:
                results.append(Evaluation(RuleOutcome.SKIPPED))
                continue
            value = cast(str, canonical_value.value)
            invalid = sorted(set(value) - allowed)
            results.append(
                Evaluation(RuleOutcome.PASSED)
                if not invalid
                else Evaluation(
                    RuleOutcome.FAILED,
                    finding(
                        typed_rule,
                        record,
                        message=(
                            f"Field '{typed_rule.field_id}' contains invalid characters: "
                            + ", ".join(repr(character) for character in invalid)
                        ),
                        actual=value,
                        expected={"allowed_characters": typed_rule.allowed_characters},
                    ),
                )
            )
        return results


class UniqueEvaluator:
    def evaluate(self, rule: ValidationRule, dataset: CanonicalDataset) -> list[Evaluation]:
        typed_rule = cast(UniqueRule, rule)
        groups: dict[tuple[type, object], list[int]] = {}
        skipped: set[int] = set()
        for index, record in enumerate(dataset.records):
            canonical_value = get_value(record, typed_rule.field_id)
            value = canonical_value.value if canonical_value is not None else None
            if value is None and typed_rule.ignore_null:
                skipped.add(index)
                continue
            groups.setdefault((type(value), value), []).append(index)
        duplicates = {
            index
            for indexes in groups.values()
            if len(indexes) > 1
            for index in indexes
        }
        results = []
        for index, record in enumerate(dataset.records):
            if index in skipped:
                results.append(Evaluation(RuleOutcome.SKIPPED))
            elif index not in duplicates:
                results.append(Evaluation(RuleOutcome.PASSED))
            else:
                canonical_value = get_value(record, typed_rule.field_id)
                value = canonical_value.value if canonical_value is not None else None
                results.append(
                    Evaluation(
                        RuleOutcome.FAILED,
                        finding(
                            typed_rule,
                            record,
                            message=f"Field '{typed_rule.field_id}' contains a duplicate value.",
                            actual=value,
                            expected="unique value",
                        ),
                    )
                )
        return results


def condition_matches(condition: SimpleCondition, record: CanonicalRecord) -> bool:
    canonical_value = get_value(record, condition.field_id)
    actual = canonical_value.value if canonical_value is not None else None
    if condition.operator == "equals":
        return values_equal(actual, condition.value)
    if condition.operator == "not_equals":
        return not values_equal(actual, condition.value)
    if condition.operator == "is_null":
        return actual is None
    return actual is not None


class ConditionalRequiredEvaluator:
    def evaluate(self, rule: ValidationRule, dataset: CanonicalDataset) -> list[Evaluation]:
        typed_rule = cast(ConditionalRequiredRule, rule)
        results = []
        for record in dataset.records:
            if not condition_matches(typed_rule.when, record):
                results.append(Evaluation(RuleOutcome.SKIPPED))
                continue
            canonical_value = get_value(record, typed_rule.field_id)
            value = canonical_value.value if canonical_value is not None else None
            if is_blank(value):
                results.append(
                    Evaluation(
                        RuleOutcome.FAILED,
                        finding(
                            typed_rule,
                            record,
                            message=(
                                f"Field '{typed_rule.field_id}' is required when the "
                                "configured condition matches."
                            ),
                            actual=value,
                            expected="present, non-blank value",
                        ),
                    )
                )
            else:
                results.append(Evaluation(RuleOutcome.PASSED))
        return results
