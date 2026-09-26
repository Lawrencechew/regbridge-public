import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, cast

from app.canonical.models import CanonicalDataset, CanonicalRecord
from app.reconciliation.models import (
    AggregateEquationRule,
    AggregateFunction,
    AggregateOperand,
    AggregateTerm,
    ArithmeticOperator,
    GroupedAggregateRule,
    ReconciliationFinding,
    ReconciliationRule,
    ReconciliationSourceValue,
    RowEquationRule,
)
from app.validation.models import RuleOutcome


@dataclass(frozen=True)
class ReconciliationEvaluation:
    outcome: RuleOutcome
    finding: ReconciliationFinding | None = None


class ReconciliationEvaluator(Protocol):
    def evaluate(
        self, rule: ReconciliationRule, dataset: CanonicalDataset
    ) -> list[ReconciliationEvaluation]: ...


def as_decimal(value: object) -> Decimal:
    if type(value) is int:
        return Decimal(value)
    if isinstance(value, Decimal):
        return value
    raise TypeError("Reconciliation arithmetic requires integer or Decimal values.")


def display_value(value: object | None) -> object | None:
    if isinstance(value, Decimal):
        return str(value)
    if type(value) in {date, datetime}:
        return value.isoformat()
    return value


def apply_term(total: Decimal, value: Decimal, operator: ArithmeticOperator) -> Decimal:
    return total + value if operator == ArithmeticOperator.ADD else total - value


def equation_passes(expected: Decimal, actual: Decimal, tolerance: Decimal) -> bool:
    return abs(actual - expected) <= tolerance


class RowEquationEvaluator:
    def evaluate(
        self, rule: ReconciliationRule, dataset: CanonicalDataset
    ) -> list[ReconciliationEvaluation]:
        typed_rule = cast(RowEquationRule, rule)
        results = []
        for record in dataset.records:
            field_ids = [term.field_id for term in typed_rule.left] + [
                typed_rule.right.field_id
            ]
            if any(
                field_id not in record.values
                or record.values[field_id].value is None
                for field_id in field_ids
            ):
                results.append(ReconciliationEvaluation(RuleOutcome.SKIPPED))
                continue

            expected = Decimal("0")
            for term in typed_rule.left:
                value = as_decimal(record.values[term.field_id].value)
                expected = apply_term(expected, value, term.operator)
            actual = as_decimal(record.values[typed_rule.right.field_id].value)
            difference = actual - expected
            if equation_passes(expected, actual, typed_rule.tolerance):
                results.append(ReconciliationEvaluation(RuleOutcome.PASSED))
                continue

            unique_fields = tuple(dict.fromkeys(field_ids))
            source_values = tuple(
                ReconciliationSourceValue(
                    field_id=field_id,
                    value=display_value(record.values[field_id].value),
                    source=record.values[field_id].source,
                )
                for field_id in unique_fields
            )
            results.append(
                ReconciliationEvaluation(
                    RuleOutcome.FAILED,
                    ReconciliationFinding(
                        rule_id=typed_rule.id,
                        rule_type=typed_rule.type,
                        rule_name=typed_rule.name,
                        severity=typed_rule.severity,
                        message="Row arithmetic does not reconcile within tolerance.",
                        record_id=record.record_id,
                        expected=str(expected),
                        actual=str(actual),
                        difference=str(difference),
                        tolerance=str(typed_rule.tolerance),
                        source_refs=typed_rule.source_refs,
                        source_values=source_values,
                    ),
                )
            )
        return results


@dataclass(frozen=True)
class AggregateValue:
    value: Decimal | None
    skipped_indexes: frozenset[int]


def aggregate_value(
    records: list[CanonicalRecord], operand: AggregateTerm | AggregateOperand
) -> AggregateValue:
    total = Decimal("0")
    contributing = 0
    skipped: set[int] = set()
    for index, record in enumerate(records):
        canonical_value = record.values.get(operand.field_id)
        if canonical_value is None or canonical_value.value is None:
            skipped.add(index)
            continue
        contributing += 1
        if operand.aggregate == AggregateFunction.SUM:
            total += as_decimal(canonical_value.value)
    if contributing == 0:
        return AggregateValue(None, frozenset(skipped))
    if operand.aggregate == AggregateFunction.COUNT:
        total = Decimal(contributing)
    return AggregateValue(total, frozenset(skipped))


def evaluate_aggregate_expression(
    records: list[CanonicalRecord],
    left: tuple[AggregateTerm, ...],
    right: AggregateOperand,
) -> tuple[Decimal | None, Decimal | None, set[int]]:
    expected = Decimal("0")
    skipped: set[int] = set()
    for term in left:
        aggregate = aggregate_value(records, term)
        skipped.update(aggregate.skipped_indexes)
        if aggregate.value is None:
            return None, None, skipped
        expected = apply_term(expected, aggregate.value, term.operator)
    actual_aggregate = aggregate_value(records, right)
    skipped.update(actual_aggregate.skipped_indexes)
    return expected, actual_aggregate.value, skipped


def aggregate_finding(
    rule: AggregateEquationRule | GroupedAggregateRule,
    *,
    expected: Decimal,
    actual: Decimal,
    records: list[CanonicalRecord],
    skipped: set[int],
    group: dict[str, object | None] | None = None,
) -> ReconciliationFinding:
    return ReconciliationFinding(
        rule_id=rule.id,
        rule_type=rule.type,
        rule_name=rule.name,
        severity=rule.severity,
        message="Aggregate arithmetic does not reconcile within tolerance.",
        group=group,
        expected=str(expected),
        actual=str(actual),
        difference=str(actual - expected),
        tolerance=str(rule.tolerance),
        source_refs=rule.source_refs,
        records_considered=len(records),
        records_skipped=len(skipped),
    )


class AggregateEquationEvaluator:
    def evaluate(
        self, rule: ReconciliationRule, dataset: CanonicalDataset
    ) -> list[ReconciliationEvaluation]:
        typed_rule = cast(AggregateEquationRule, rule)
        expected, actual, skipped = evaluate_aggregate_expression(
            dataset.records, typed_rule.left, typed_rule.right
        )
        if expected is None or actual is None:
            return [ReconciliationEvaluation(RuleOutcome.SKIPPED)]
        if equation_passes(expected, actual, typed_rule.tolerance):
            return [ReconciliationEvaluation(RuleOutcome.PASSED)]
        return [
            ReconciliationEvaluation(
                RuleOutcome.FAILED,
                aggregate_finding(
                    typed_rule,
                    expected=expected,
                    actual=actual,
                    records=dataset.records,
                    skipped=skipped,
                ),
            )
        ]


def group_sort_key(group: tuple[object | None, ...]) -> str:
    return json.dumps(
        [display_value(value) for value in group],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


class GroupedAggregateEvaluator:
    def evaluate(
        self, rule: ReconciliationRule, dataset: CanonicalDataset
    ) -> list[ReconciliationEvaluation]:
        typed_rule = cast(GroupedAggregateRule, rule)
        groups: dict[tuple[object | None, ...], list[CanonicalRecord]] = {}
        for record in dataset.records:
            key = tuple(
                record.values[field_id].value
                if field_id in record.values
                else None
                for field_id in typed_rule.group_by
            )
            groups.setdefault(key, []).append(record)

        results = []
        for key in sorted(groups, key=group_sort_key):
            records = groups[key]
            expected, actual, skipped = evaluate_aggregate_expression(
                records, typed_rule.left, typed_rule.right
            )
            if expected is None or actual is None:
                results.append(ReconciliationEvaluation(RuleOutcome.SKIPPED))
                continue
            if equation_passes(expected, actual, typed_rule.tolerance):
                results.append(ReconciliationEvaluation(RuleOutcome.PASSED))
                continue
            group = {
                field_id: display_value(value)
                for field_id, value in zip(typed_rule.group_by, key, strict=True)
            }
            results.append(
                ReconciliationEvaluation(
                    RuleOutcome.FAILED,
                    aggregate_finding(
                        typed_rule,
                        expected=expected,
                        actual=actual,
                        records=records,
                        skipped=skipped,
                        group=group,
                    ),
                )
            )
        return results
